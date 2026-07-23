from __future__ import annotations

from pathlib import Path
from typing import Any

from .artifact_store import state_path
from .canonical import authority_lock, object_sha256, parse_time, read_object
from .canonical import resolve_workspace_path, sha256_file, write_immutable_json
from .decision_integrity import stable_decision_projection
from .evaluator import evaluate, load_bound_decision
from .contracts import reservation_units
from .lifecycle_preflight import decision_grant_bindings
from .lifecycle_preflight import subject_preflight
from .lifecycle_preflight import validate_selected_grants
from .lifecycle_preflight import verify_bound_decision_evidence
from .lifecycle_preflight import verify_manifest
from .lifecycle_paths import artifact_binding as _artifact_binding
from .lifecycle_paths import reservation_path as _reservation_path
from .lifecycle_paths import reservation_state_path as _reservation_state_path
from .projection_recovery import apply_projection_changes, projection_change
from .projection_recovery import recover_projection_intents
from .projection_recovery import validated_settled_intent
from .projection_reservations import validate_decision_artifact
from .projection_reservations import validate_reservation


def _load_reservable_decision(
    root: Path,
    decision_ref: str,
    decision_sha256: str,
    idempotency_key: str,
    skills_root: Path | None,
) -> tuple[dict[str, Any], Path, str, Path, Path]:
    decision, decision_path = load_bound_decision(
        root,
        decision_ref,
        decision_sha256,
    )
    validate_decision_artifact(
        root,
        decision,
        decision_path,
        skills_root=skills_root,
        verify_manifest=False,
    )
    if decision.get("decision") != "allowed" or not decision.get("selected_grants"):
        raise SystemExit(
            "Only an allowed decision with selected grants may be reserved."
        )
    reservation_id = (
        "authz-"
        + object_sha256(
            {
                "request": decision["request_sha256"],
                "key": idempotency_key,
            }
        )[:24]
    )
    return (
        decision,
        decision_path,
        reservation_id,
        _reservation_path(root, reservation_id),
        _reservation_state_path(root, reservation_id),
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
    with authority_lock(root):
        (
            decision,
            decision_path,
            reservation_id,
            artifact_path,
            projection_path,
        ) = _load_reservable_decision(
            root,
            decision_ref,
            decision_sha256,
            idempotency_key,
            skills_root,
        )
        recover_projection_intents(root, skills_root=skills_root)
        if artifact_path.exists():
            existing = validated_settled_intent(
                root, artifact_path, skills_root=skills_root
            )
            # Reopen the immutable decision and its complete selected/lineage
            # grant set at the exact replay boundary. Recovery performs this
            # validation too, but the replay return must not depend on a
            # caller-provided recovery implementation retaining that property.
            validate_reservation(root, existing, artifact_path)
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
        if fresh["decision"] != "allowed" or stable_decision_projection(
            fresh
        ) != stable_decision_projection(decision):
            raise SystemExit(
                "Authority decision is stale at pre-dispatch verification."
            )
        records = validate_selected_grants(
            root,
            decision_grant_bindings(decision),
            request=decision["request"],
            at=reserved_at,
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
    validate_reservation(root, reservation, path)
    projection = _reservation_state_path(root, reservation["reservation_id"])
    if not projection.is_file():
        raise SystemExit("Authority reservation state is missing.")
    return reservation, path, read_object(projection, "authority reservation state")


def _validate_stored_reservation(
    root: Path,
    reservation: dict[str, Any],
) -> None:
    stored_path = _reservation_path(
        root,
        str(reservation.get("reservation_id") or ""),
    )
    if not stored_path.is_file():
        raise SystemExit("Authority reservation artifact is missing.")
    stored = read_object(stored_path, "authority reservation")
    if stored != reservation:
        raise SystemExit("Authority reservation differs from its stored artifact.")
    validate_reservation(root, stored, stored_path)


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
    _validate_stored_reservation(root, reservation)
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
        request=decision["request"],
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
        recover_projection_intents(root, skills_root=skills_root)
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
    """Consume only an unregistered schema-v2 compatibility operation."""

    from .settlement_lifecycle import consume_legacy

    return consume_legacy(
        root,
        reservation_ref,
        reservation_sha256,
        execution_result,
        pre_commit_verification=pre_commit_verification,
        expected_subject_after_sha256=expected_subject_after_sha256,
        consumed_at=consumed_at,
        expected_version=expected_version,
        idempotency_key=idempotency_key,
        skills_root=skills_root,
    )


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
    skills_root: Path | None = None,
) -> dict[str, Any]:
    """Release only an unregistered compatibility operation."""

    from .settlement_lifecycle import release_legacy

    return release_legacy(
        root,
        reservation_ref,
        reservation_sha256,
        no_effect_evidence,
        released_at=released_at,
        expected_version=expected_version,
        idempotency_key=idempotency_key,
        effect_status=effect_status,
        skills_root=skills_root,
    )
