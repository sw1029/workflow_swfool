"""Separated legacy and registered authority settlement entrypoints."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .artifact_store import AUTHORIZATION_ROOT, load_grant, state_path, verify_binding
from .canonical import authority_lock, object_sha256, parse_time, sha256_file
from .canonical import write_immutable_json
from .execution_results import create_execution_result
from .execution_results import resolve_pre_commit_verification
from .lifecycle_paths import artifact_binding, reservation_state_path
from .projection_recovery import projection_change
from .projection_recovery import recover_projection_intents
from .projection_recovery import validated_settled_intent
from .registered_release import registered_release_required
from .registered_release import validate_registered_owner_receipt
from .registered_release import validate_registered_release


def _apply_projection_changes(root: Path, changes: list[dict[str, Any]]) -> None:
    # Preserve the lifecycle module's fault-injection seam used to prove
    # write-ahead crash recovery while keeping settlement internals separated.
    from . import lifecycle as lifecycle_module

    lifecycle_module.apply_projection_changes(root, changes)


def _reservation(root: Path, ref: str, digest: str) -> tuple[Any, Any, Any]:
    from .lifecycle import load_reservation

    return load_reservation(root, ref, digest)


def _verification(
    root: Path,
    reservation: dict[str, Any],
    state: dict[str, Any],
    *,
    verified_at: str,
    expected_version: int,
    skills_root: Path | None,
) -> dict[str, Any]:
    from .lifecycle import verify_reservation

    return verify_reservation(
        root,
        reservation,
        state,
        verified_at=verified_at,
        expected_version=expected_version,
        skills_root=skills_root,
        verify_subject=False,
    )


def _reject_registered_public(
    root: Path, reservation_ref: str, reservation_sha256: str, action: str
) -> None:
    reservation, _, _ = _reservation(root, reservation_ref, reservation_sha256)
    if registered_release_required(root, reservation):
        raise SystemExit(
            f"Registered owner operations require authority settle; direct {action} is forbidden."
        )


def consume_legacy(
    root: Path,
    reservation_ref: str,
    reservation_sha256: str,
    execution_result: dict[str, str],
    *,
    pre_commit_verification: dict[str, str] | None,
    expected_subject_after_sha256: str | None,
    consumed_at: str,
    expected_version: int,
    idempotency_key: str,
    skills_root: Path | None,
) -> dict[str, Any]:
    """Public schema-v2 compatibility consume; registered owners fail closed."""

    root = root.resolve()
    _reject_registered_public(root, reservation_ref, reservation_sha256, "consume")
    return _consume(
        root,
        reservation_ref,
        reservation_sha256,
        execution_result,
        pre_commit_verification=pre_commit_verification,
        expected_subject_after_sha256=expected_subject_after_sha256,
        owner_validation=None,
        consumed_at=consumed_at,
        expected_version=expected_version,
        idempotency_key=idempotency_key,
        skills_root=skills_root,
        registered=False,
    )


def _consume_registered_owner(
    root: Path,
    reservation_ref: str,
    reservation_sha256: str,
    owner_result: dict[str, str],
    owner_validation: dict[str, str] | None,
    *,
    pre_commit_verification: dict[str, str],
    consumed_at: str,
    expected_version: int,
    idempotency_key: str,
    skills_root: Path | None,
) -> dict[str, Any]:
    """Settlement-only schema-v3 consume entrypoint."""

    root = root.resolve()
    reservation, _, _ = _reservation(
        root, reservation_ref, reservation_sha256
    )
    if not registered_release_required(root, reservation):
        raise SystemExit("Registered owner consume requires a registered operation.")
    return _consume(
        root,
        reservation_ref,
        reservation_sha256,
        owner_result,
        pre_commit_verification=pre_commit_verification,
        expected_subject_after_sha256=None,
        owner_validation=owner_validation,
        consumed_at=consumed_at,
        expected_version=expected_version,
        idempotency_key=idempotency_key,
        skills_root=skills_root,
        registered=True,
    )


def _consume_projection_changes(
    root: Path,
    reservation: dict[str, Any],
    state: dict[str, Any],
    receipt_id: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    updates: list[dict[str, Any]] = []
    changes: list[dict[str, Any]] = []
    for use in reservation["grant_uses"]:
        _, _, grant_state = load_grant(root, use["grant_id"])
        remaining = grant_state["remaining_uses"]
        new_remaining = remaining - use["units"] if remaining is not None else None
        updated = {
            **grant_state,
            "remaining_uses": new_remaining,
            "reserved_uses": grant_state["reserved_uses"] - use["units"],
            "consumed_uses": grant_state["consumed_uses"] + use["units"],
            "status": "exhausted" if new_remaining == 0 else "active",
            "version": grant_state["version"] + 1,
            "last_event_id": receipt_id,
        }
        updates.append(updated)
        changes.append(
            projection_change(
                root, state_path(root, use["grant_id"]), grant_state, updated
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
            reservation_state_path(root, reservation["reservation_id"]),
            state,
            reservation_after,
        )
    )
    return updates, changes


def _consume(
    root: Path,
    reservation_ref: str,
    reservation_sha256: str,
    execution_result: dict[str, str],
    *,
    pre_commit_verification: dict[str, str] | None,
    expected_subject_after_sha256: str | None,
    owner_validation: dict[str, str] | None,
    consumed_at: str,
    expected_version: int,
    idempotency_key: str,
    skills_root: Path | None,
    registered: bool,
) -> dict[str, Any]:
    verify_binding(root, execution_result, "owner execution_result")
    if owner_validation is not None:
        verify_binding(root, owner_validation, "owner_validation")
    receipt_id = "authu-" + object_sha256(
        {"reservation": reservation_sha256, "key": idempotency_key}
    )[:24]
    receipt_path = root / AUTHORIZATION_ROOT / "use_receipts" / f"{receipt_id}.json"
    with authority_lock(root):
        recover_projection_intents(root, skills_root=skills_root)
        reservation, reservation_path, state = _reservation(
            root, reservation_ref, reservation_sha256
        )
        if receipt_path.exists():
            receipt = validated_settled_intent(
                root, receipt_path, skills_root=skills_root
            )
            recorded = receipt.get(
                "owner_execution_result", receipt.get("execution_result")
            )
            if (
                recorded != execution_result
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
        verified = _verification(
            root,
            reservation,
            state,
            verified_at=consumed_at,
            expected_version=expected_version,
            skills_root=skills_root,
        )
        is_registered = registered_release_required(root, reservation)
        if registered != is_registered:
            raise SystemExit("Authority consume settlement route is invalid.")
        reservation_binding = artifact_binding(root, reservation_path)
        verification_binding, _ = resolve_pre_commit_verification(
            root,
            reservation,
            reservation_binding,
            pre_commit_verification,
            expected_version=expected_version,
        )
        if registered:
            assert owner_validation is not None
            validate_registered_owner_receipt(
                root,
                reservation,
                reservation_binding,
                owner_validation,
                expected_version=expected_version,
                require_current_state=True,
                skills_root=skills_root,
                expected_outcomes={"confirmed_effect"},
                owner_result=execution_result,
                pre_commit_verification=verification_binding,
            )
        _, typed_result_binding = create_execution_result(
            root,
            reservation,
            verified["decision"],
            reservation_binding,
            verification_binding,
            execution_result,
            completed_at=consumed_at,
            expected_subject_after_sha256=expected_subject_after_sha256,
            owner_validation=owner_validation,
        )
        updates, changes = _consume_projection_changes(
            root, reservation, state, receipt_id
        )
        receipt = {
            "schema_version": 2,
            "artifact_kind": "authority_use_receipt",
            "receipt_id": receipt_id,
            "reservation": reservation_binding,
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
        _apply_projection_changes(root, changes)
    return {
        "use_receipt": receipt,
        "ref": receipt_path.relative_to(root).as_posix(),
        "sha256": sha256_file(receipt_path),
    }


def release_legacy(
    root: Path,
    reservation_ref: str,
    reservation_sha256: str,
    no_effect_evidence: dict[str, str],
    *,
    released_at: str,
    expected_version: int,
    idempotency_key: str,
    effect_status: str,
    skills_root: Path | None,
) -> dict[str, Any]:
    """Public unregistered release compatibility entrypoint."""

    root = root.resolve()
    _reject_registered_public(root, reservation_ref, reservation_sha256, "release")
    return _release(
        root,
        reservation_ref,
        reservation_sha256,
        no_effect_evidence,
        released_at=released_at,
        expected_version=expected_version,
        idempotency_key=idempotency_key,
        effect_status=effect_status,
        skills_root=skills_root,
        registered=False,
    )


def _release_registered_owner(
    root: Path,
    reservation_ref: str,
    reservation_sha256: str,
    owner_validation: dict[str, str],
    *,
    released_at: str,
    expected_version: int,
    idempotency_key: str,
    effect_status: str,
    skills_root: Path | None,
) -> dict[str, Any]:
    """Settlement-only registered release/quarantine entrypoint."""

    root = root.resolve()
    reservation, _, _ = _reservation(
        root, reservation_ref, reservation_sha256
    )
    if not registered_release_required(root, reservation):
        raise SystemExit("Registered owner release requires a registered operation.")
    return _release(
        root,
        reservation_ref,
        reservation_sha256,
        owner_validation,
        released_at=released_at,
        expected_version=expected_version,
        idempotency_key=idempotency_key,
        effect_status=effect_status,
        skills_root=skills_root,
        registered=True,
    )


def _release(
    root: Path,
    reservation_ref: str,
    reservation_sha256: str,
    no_effect_evidence: dict[str, str],
    *,
    released_at: str,
    expected_version: int,
    idempotency_key: str,
    effect_status: str,
    skills_root: Path | None,
    registered: bool,
) -> dict[str, Any]:
    if effect_status not in {"not_started", "verified_no_effect", "unknown_effect"}:
        raise SystemExit("effect_status is invalid.")
    verify_binding(root, no_effect_evidence, "no_effect_evidence")
    event_id = "authx-" + object_sha256(
        {"reservation": reservation_sha256, "key": idempotency_key}
    )[:24]
    event_path = root / AUTHORIZATION_ROOT / "release_receipts" / f"{event_id}.json"
    with authority_lock(root):
        recover_projection_intents(root, skills_root=skills_root)
        reservation, reservation_path, state = _reservation(
            root, reservation_ref, reservation_sha256
        )
        is_registered = registered_release_required(root, reservation)
        if registered != is_registered:
            raise SystemExit("Authority release settlement route is invalid.")
        if registered:
            validate_registered_release(
                root,
                reservation,
                artifact_binding(root, reservation_path),
                no_effect_evidence,
                effect_status,
                expected_version,
                skills_root,
                require_current_state=not event_path.exists(),
            )
        if event_path.exists():
            event = validated_settled_intent(
                root, event_path, skills_root=skills_root
            )
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
                        root, state_path(root, use["grant_id"]), grant_state, updated
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
                reservation_state_path(root, reservation["reservation_id"]),
                state,
                reservation_after,
            )
        )
        event = {
            "schema_version": 2,
            "artifact_kind": "authority_release_receipt",
            "receipt_id": event_id,
            "reservation": artifact_binding(root, reservation_path),
            "no_effect_evidence": no_effect_evidence,
            "effect_status": effect_status,
            "release_applied": released,
            "released_at": parse_time(released_at, "released_at").isoformat(),
            "idempotency_key": idempotency_key,
            "state_changes": changes,
        }
        write_immutable_json(event_path, event, "authority release receipt")
        _apply_projection_changes(root, changes)
    return {
        "release_receipt": event,
        "ref": event_path.relative_to(root).as_posix(),
        "sha256": sha256_file(event_path),
    }


__all__ = ("consume_legacy", "release_legacy")
