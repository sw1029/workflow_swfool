from __future__ import annotations

from pathlib import Path
from typing import Any

from .artifact_store import AUTHORIZATION_ROOT, load_grant, state_path, verify_binding
from .canonical import authority_lock, object_sha256, parse_time, read_object
from .canonical import resolve_workspace_path, sha256_file, write_immutable_json
from .evaluator import evaluate, load_bound_decision
from .contracts import reservation_units
from .execution_results import create_execution_result
from .execution_results import resolve_pre_commit_verification
from .lifecycle_preflight import decision_grant_bindings
from .lifecycle_preflight import subject_preflight
from .lifecycle_preflight import validate_selected_grants
from .lifecycle_preflight import verify_bound_decision_evidence
from .lifecycle_preflight import verify_manifest
from .projection_recovery import apply_projection_changes, projection_change
from .projection_recovery import recover_projection_intents
from .projection_recovery import validated_settled_intent


def _artifact_binding(root: Path, path: Path) -> dict[str, str]:
    return {
        "ref": path.relative_to(root.resolve()).as_posix(),
        "sha256": sha256_file(path),
    }


def _reservation_path(root: Path, reservation_id: str) -> Path:
    return (
        root.resolve() / AUTHORIZATION_ROOT / "reservations" / f"{reservation_id}.json"
    )


def _reservation_state_path(root: Path, reservation_id: str) -> Path:
    return (
        root.resolve()
        / AUTHORIZATION_ROOT
        / "state"
        / "reservations"
        / f"{reservation_id}.json"
    )


def reserve(
    root: Path,
    decision_ref: str,
    decision_sha256: str,
    *,
    reserved_at: str,
    idempotency_key: str,
    skills_root: Path | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    decision, decision_path = load_bound_decision(root, decision_ref, decision_sha256)
    if decision.get("decision") != "allowed" or not decision.get("selected_grants"):
        raise SystemExit(
            "Only an allowed decision with selected grants may be reserved."
        )
    reservation_id = f"authz-{object_sha256({'request': decision['request_sha256'], 'key': idempotency_key})[:24]}"
    artifact_path = _reservation_path(root, reservation_id)
    projection_path = _reservation_state_path(root, reservation_id)
    with authority_lock(root):
        recover_projection_intents(root)
        if artifact_path.exists():
            existing = validated_settled_intent(root, artifact_path)
            if (
                existing.get("decision") != _artifact_binding(root, decision_path)
                or existing.get("idempotency_key") != idempotency_key
            ):
                raise SystemExit("Reservation idempotency conflict.")
            return {
                "reservation": existing,
                "reservation_ref": artifact_path.relative_to(root).as_posix(),
                "reservation_sha256": sha256_file(artifact_path),
                "state": read_object(projection_path),
            }
        subject_preflight(root, decision["request"])
        verify_manifest(decision, skills_root)
        fresh = evaluate(
            root,
            decision["request"],
            decision["evaluation_context"],
            evaluated_at=reserved_at,
            skills_root=skills_root,
        )
        if (
            fresh["decision"] != "allowed"
            or fresh["effective_authority_fingerprint"]
            != decision["effective_authority_fingerprint"]
        ):
            raise SystemExit(
                "Authority decision is stale at pre-dispatch verification."
            )
        records = validate_selected_grants(
            root, decision_grant_bindings(decision), at=reserved_at
        )
        units = reservation_units(decision["request"])
        grant_uses: list[dict[str, Any]] = []
        changes: list[dict[str, Any]] = []
        for grant, _, state in records:
            available = state["remaining_uses"]
            if available is not None and available - state["reserved_uses"] < units:
                raise SystemExit(
                    f"Authority grant has insufficient unreserved uses: {grant['grant_id']}"
                )
            grant_uses.append(
                {
                    "grant_id": grant["grant_id"],
                    "grant_sha256": state["grant_sha256"],
                    "units": units,
                    "state_version_before": state["version"],
                    "state_version_after": state["version"] + 1,
                }
            )
            updated = {
                **state,
                "reserved_uses": state["reserved_uses"] + units,
                "version": state["version"] + 1,
                "last_event_id": reservation_id,
            }
            changes.append(
                projection_change(
                    root,
                    state_path(root, grant["grant_id"]),
                    state,
                    updated,
                )
            )
        reservation_state = {
            "schema_version": 2,
            "artifact_kind": "authority_reservation_state",
            "reservation_id": reservation_id,
            "status": "reserved",
            "version": 0,
            "last_event_id": reservation_id,
        }
        changes.append(
            projection_change(root, projection_path, None, reservation_state)
        )
        reservation = {
            "schema_version": 2,
            "artifact_kind": "authority_reservation",
            "reservation_id": reservation_id,
            "request_id": decision["request"]["request_id"],
            "request_sha256": decision["request_sha256"],
            "decision": _artifact_binding(root, decision_path),
            "effective_authority_fingerprint": decision[
                "effective_authority_fingerprint"
            ],
            "grant_uses": grant_uses,
            "state_changes": changes,
            "reserved_at": parse_time(reserved_at, "reserved_at").isoformat(),
            "idempotency_key": idempotency_key,
        }
        write_immutable_json(artifact_path, reservation, "authority reservation")
        apply_projection_changes(root, changes)
    return {
        "reservation": reservation,
        "reservation_ref": artifact_path.relative_to(root).as_posix(),
        "reservation_sha256": sha256_file(artifact_path),
        "state": reservation_state,
    }


def load_reservation(
    root: Path, ref: str, digest: str
) -> tuple[dict[str, Any], Path, dict[str, Any]]:
    path = resolve_workspace_path(root, ref, "authority reservation")
    if sha256_file(path) != digest:
        raise SystemExit("Authority reservation digest mismatch.")
    reservation = read_object(path, "authority reservation")
    if (
        reservation.get("schema_version") != 2
        or reservation.get("artifact_kind") != "authority_reservation"
    ):
        raise SystemExit("Authority reservation contract is invalid.")
    projection = _reservation_state_path(root, reservation["reservation_id"])
    if not projection.is_file():
        raise SystemExit("Authority reservation state is missing.")
    return reservation, path, read_object(projection, "authority reservation state")


def verify_reservation(
    root: Path,
    reservation: dict[str, Any],
    state: dict[str, Any],
    *,
    verified_at: str,
    expected_version: int,
    skills_root: Path | None = None,
    verify_subject: bool = True,
) -> dict[str, Any]:
    if state["status"] != "reserved" or state["version"] != expected_version:
        raise SystemExit("Reservation is not in the expected reserved CAS state.")
    decision, _ = load_bound_decision(
        root, reservation["decision"]["ref"], reservation["decision"]["sha256"]
    )
    if verify_subject:
        subject_preflight(root, decision["request"])
    verify_manifest(decision, skills_root)
    verify_bound_decision_evidence(root, decision)
    versions = {
        item["grant_id"]: item["state_version_after"]
        for item in reservation["grant_uses"]
    }
    records = validate_selected_grants(
        root,
        decision_grant_bindings(decision),
        expected_versions=versions,
        minimum_versions=True,
        at=verified_at,
    )
    for grant, _, projection in records:
        units = next(
            item["units"]
            for item in reservation["grant_uses"]
            if item["grant_id"] == grant["grant_id"]
        )
        if projection["reserved_uses"] < units:
            raise SystemExit("Reservation accounting no longer covers the operation.")
    return {
        "decision": decision,
        "grant_states": [
            {
                "grant_id": grant["grant_id"],
                "grant_sha256": digest,
                "state_version": projection["version"],
                "status": projection["status"],
                "remaining_uses": projection["remaining_uses"],
                "reserved_uses": projection["reserved_uses"],
            }
            for grant, digest, projection in records
        ],
    }


def verify_reservation_with_recovery(
    root: Path,
    reservation_ref: str,
    reservation_sha256: str,
    *,
    verified_at: str,
    expected_version: int,
    skills_root: Path | None = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], str]:
    root = root.resolve()
    with authority_lock(root):
        recover_projection_intents(root)
        reservation, _, state = load_reservation(
            root, reservation_ref, reservation_sha256
        )
        verification = verify_reservation(
            root,
            reservation,
            state,
            verified_at=verified_at,
            expected_version=expected_version,
            skills_root=skills_root,
        )
        projection = _reservation_state_path(root, reservation["reservation_id"])
        state_sha256 = sha256_file(projection)
    return reservation, state, verification, state_sha256


def consume(
    root: Path,
    reservation_ref: str,
    reservation_sha256: str,
    execution_result: dict[str, str],
    *,
    pre_commit_verification: dict[str, str] | None = None,
    expected_subject_after_sha256: str | None = None,
    consumed_at: str,
    expected_version: int,
    idempotency_key: str,
    skills_root: Path | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    verify_binding(root, execution_result, "owner execution_result")
    receipt_id = f"authu-{object_sha256({'reservation': reservation_sha256, 'key': idempotency_key})[:24]}"
    receipt_path = root / AUTHORIZATION_ROOT / "use_receipts" / f"{receipt_id}.json"
    with authority_lock(root):
        recover_projection_intents(root)
        reservation, reservation_path, state = load_reservation(
            root, reservation_ref, reservation_sha256
        )
        if receipt_path.exists():
            receipt = validated_settled_intent(root, receipt_path)
            recorded_owner_result = receipt.get(
                "owner_execution_result", receipt.get("execution_result")
            )
            if (
                recorded_owner_result != execution_result
                or receipt.get("idempotency_key") != idempotency_key
                or (
                    pre_commit_verification is not None
                    and receipt.get("pre_commit_verification")
                    != pre_commit_verification
                )
            ):
                raise SystemExit("Use-receipt idempotency conflict.")
            return {
                "use_receipt": receipt,
                "ref": receipt_path.relative_to(root).as_posix(),
                "sha256": sha256_file(receipt_path),
            }
        verification = verify_reservation(
            root,
            reservation,
            state,
            verified_at=consumed_at,
            expected_version=expected_version,
            skills_root=skills_root,
            verify_subject=False,
        )
        reservation_binding = _artifact_binding(root, reservation_path)
        verification_binding, _ = resolve_pre_commit_verification(
            root,
            reservation,
            reservation_binding,
            pre_commit_verification,
            expected_version=expected_version,
        )
        _, typed_result_binding = create_execution_result(
            root,
            reservation,
            verification["decision"],
            reservation_binding,
            verification_binding,
            execution_result,
            completed_at=consumed_at,
            expected_subject_after_sha256=expected_subject_after_sha256,
        )
        updates: list[dict[str, Any]] = []
        changes: list[dict[str, Any]] = []
        for use in reservation["grant_uses"]:
            _, _, grant_state = load_grant(root, use["grant_id"])
            remaining = grant_state["remaining_uses"]
            new_remaining = remaining - use["units"] if remaining is not None else None
            updates.append(
                {
                    **grant_state,
                    "remaining_uses": new_remaining,
                    "reserved_uses": grant_state["reserved_uses"] - use["units"],
                    "consumed_uses": grant_state["consumed_uses"] + use["units"],
                    "status": "exhausted" if new_remaining == 0 else "active",
                    "version": grant_state["version"] + 1,
                    "last_event_id": receipt_id,
                }
            )
            changes.append(
                projection_change(
                    root,
                    state_path(root, use["grant_id"]),
                    grant_state,
                    updates[-1],
                )
            )
        reservation_after = {
            **state,
            "status": "consumed",
            "version": state["version"] + 1,
            "last_event_id": receipt_id,
        }
        changes.append(
            projection_change(
                root,
                _reservation_state_path(root, reservation["reservation_id"]),
                state,
                reservation_after,
            )
        )
        receipt = {
            "schema_version": 2,
            "artifact_kind": "authority_use_receipt",
            "receipt_id": receipt_id,
            "reservation": _artifact_binding(root, reservation_path),
            "execution_result": typed_result_binding,
            "owner_execution_result": execution_result,
            "pre_commit_verification": verification_binding,
            "consumed_at": parse_time(consumed_at, "consumed_at").isoformat(),
            "grant_versions_after": {
                item["grant_id"]: item["version"] for item in updates
            },
            "state_changes": changes,
            "idempotency_key": idempotency_key,
        }
        write_immutable_json(receipt_path, receipt, "authority use receipt")
        apply_projection_changes(root, changes)
    return {
        "use_receipt": receipt,
        "ref": receipt_path.relative_to(root).as_posix(),
        "sha256": sha256_file(receipt_path),
    }


def release(
    root: Path,
    reservation_ref: str,
    reservation_sha256: str,
    no_effect_evidence: dict[str, str],
    *,
    released_at: str,
    expected_version: int,
    idempotency_key: str,
    effect_status: str,
) -> dict[str, Any]:
    if effect_status not in {"not_started", "verified_no_effect", "unknown_effect"}:
        raise SystemExit("effect_status is invalid.")
    root = root.resolve()
    verify_binding(root, no_effect_evidence, "no_effect_evidence")
    event_id = f"authx-{object_sha256({'reservation': reservation_sha256, 'key': idempotency_key})[:24]}"
    event_path = root / AUTHORIZATION_ROOT / "release_receipts" / f"{event_id}.json"
    with authority_lock(root):
        recover_projection_intents(root)
        reservation, reservation_path, state = load_reservation(
            root, reservation_ref, reservation_sha256
        )
        if event_path.exists():
            event = validated_settled_intent(root, event_path)
            if (
                event.get("idempotency_key") != idempotency_key
                or event.get("no_effect_evidence") != no_effect_evidence
                or event.get("effect_status") != effect_status
            ):
                raise SystemExit("Release idempotency conflict.")
            return {
                "release_receipt": event,
                "ref": event_path.relative_to(root).as_posix(),
                "sha256": sha256_file(event_path),
            }
        if state["status"] != "reserved" or state["version"] != expected_version:
            raise SystemExit("Reservation is not in the expected reserved CAS state.")
        released = effect_status != "unknown_effect"
        changes: list[dict[str, Any]] = []
        if released:
            for use in reservation["grant_uses"]:
                _, _, grant_state = load_grant(root, use["grant_id"])
                updated = {
                    **grant_state,
                    "reserved_uses": grant_state["reserved_uses"] - use["units"],
                    "version": grant_state["version"] + 1,
                    "last_event_id": event_id,
                }
                changes.append(
                    projection_change(
                        root,
                        state_path(root, use["grant_id"]),
                        grant_state,
                        updated,
                    )
                )
        next_status = "released" if released else "quarantined_unknown_effect"
        reservation_after = {
            **state,
            "status": next_status,
            "version": state["version"] + 1,
            "last_event_id": event_id,
        }
        changes.append(
            projection_change(
                root,
                _reservation_state_path(root, reservation["reservation_id"]),
                state,
                reservation_after,
            )
        )
        event = {
            "schema_version": 2,
            "artifact_kind": "authority_release_receipt",
            "receipt_id": event_id,
            "reservation": _artifact_binding(root, reservation_path),
            "no_effect_evidence": no_effect_evidence,
            "effect_status": effect_status,
            "release_applied": released,
            "released_at": parse_time(released_at, "released_at").isoformat(),
            "idempotency_key": idempotency_key,
            "state_changes": changes,
        }
        write_immutable_json(event_path, event, "authority release receipt")
        apply_projection_changes(root, changes)
    return {
        "release_receipt": event,
        "ref": event_path.relative_to(root).as_posix(),
        "sha256": sha256_file(event_path),
    }
