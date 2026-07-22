"""Owner-validated authority settlement dispatcher."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .canonical import object_sha256, read_object
from .evaluator import load_bound_decision
from .execution_results import validate_pre_commit_verification
from .lifecycle import load_reservation
from .owner_validators import invoke_registered_owner_validator
from .owner_validators import load_owner_validation_receipt
from .owner_validators import publish_owner_validation_receipt
from .owner_validation_io import preflight_registered_owner_result
from .settlement_lifecycle import _consume_registered_owner
from .settlement_lifecycle import _release_registered_owner


def _same_owner_boundary(
    current: dict[str, Any], historical: dict[str, Any]
) -> bool:
    """Compare the stable effect proof while excluding phase-local metadata."""

    excluded = {"phase", "descendant_event_count", "receipt_sha256"}
    return (
        {key: value for key, value in current.items() if key not in excluded}
        == {key: value for key, value in historical.items() if key not in excluded}
        and current.get("phase") == "current"
        and historical.get("phase") == "historical"
    )


def _replay_if_settled(
    root: Path,
    reservation_ref: str,
    reservation_sha256: str,
    reservation_binding: dict[str, str],
    request: dict[str, Any],
    owner_result: dict[str, str],
    pre_commit_verification: dict[str, str],
    *,
    settled_at: str,
    expected_version: int,
    idempotency_key: str,
    skills_root: Path | None,
) -> dict[str, Any] | None:
    identity = object_sha256(
        {"reservation": reservation_sha256, "key": idempotency_key}
    )[:24]
    use_path = root / ".task/authorization/use_receipts" / f"authu-{identity}.json"
    release_path = (
        root / ".task/authorization/release_receipts" / f"authx-{identity}.json"
    )
    if use_path.exists():
        settlement = _consume_registered_owner(
            root,
            reservation_ref,
            reservation_sha256,
            owner_result,
            None,
            pre_commit_verification=pre_commit_verification,
            consumed_at=settled_at,
            expected_version=expected_version,
            idempotency_key=idempotency_key,
            skills_root=skills_root,
        )
        typed_binding = settlement["use_receipt"].get("execution_result")
        if not isinstance(typed_binding, dict):
            raise SystemExit("Existing settlement lacks a typed execution result.")
        typed = read_object(
            root / typed_binding["ref"], "authority execution result replay"
        )
        validation_binding = typed.get("owner_validation")
        if not isinstance(validation_binding, dict):
            raise SystemExit(
                "Existing settlement predates registered owner validation; use historical reconciliation."
            )
        validation = load_owner_validation_receipt(
            root,
            validation_binding,
            request=request,
            owner_result=owner_result,
            reservation=reservation_binding,
            pre_commit_verification=pre_commit_verification,
            phase="historical",
        )
        return {
            "status": "consumed",
            "outcome": "confirmed_effect",
            "owner_validation": validation_binding,
            "owner_validation_receipt": validation,
            "settlement": settlement,
        }
    if release_path.exists():
        receipt = read_object(release_path, "authority release receipt replay")
        effect_status = receipt.get("effect_status")
        if effect_status not in {"verified_no_effect", "unknown_effect"}:
            raise SystemExit("Existing release is not an owner-validated settlement.")
        validation_binding = receipt.get("no_effect_evidence")
        if not isinstance(validation_binding, dict):
            raise SystemExit("Existing release lacks owner validation evidence.")
        validation = load_owner_validation_receipt(
            root,
            validation_binding,
            request=request,
            owner_result=owner_result,
            reservation=reservation_binding,
            pre_commit_verification=pre_commit_verification,
            phase="historical",
        )
        settlement = _release_registered_owner(
            root,
            reservation_ref,
            reservation_sha256,
            validation_binding,
            released_at=settled_at,
            expected_version=expected_version,
            idempotency_key=idempotency_key,
            effect_status=effect_status,
            skills_root=skills_root,
        )
        outcome = (
            "confirmed_no_effect"
            if effect_status == "verified_no_effect"
            else "unknown_effect"
        )
        return {
            "status": "released" if outcome == "confirmed_no_effect" else "quarantined",
            "outcome": outcome,
            "owner_validation": validation_binding,
            "owner_validation_receipt": validation,
            "settlement": settlement,
        }
    return None


def settle_owner_result(
    root: Path,
    reservation_ref: str,
    reservation_sha256: str,
    owner_result: dict[str, str],
    pre_commit_verification: dict[str, str],
    *,
    settled_at: str,
    expected_version: int,
    idempotency_key: str,
    skills_root: Path | None,
) -> dict[str, Any]:
    """Validate an owner result and consume, release, or quarantine exactly once."""

    root = root.resolve()
    preflight_registered_owner_result(root, owner_result)
    reservation, reservation_path, state = load_reservation(
        root, reservation_ref, reservation_sha256
    )
    reservation_binding = {
        "ref": reservation_path.relative_to(root).as_posix(),
        "sha256": reservation_sha256,
    }
    decision, _ = load_bound_decision(
        root, reservation["decision"]["ref"], reservation["decision"]["sha256"]
    )
    replay = _replay_if_settled(
        root,
        reservation_ref,
        reservation_sha256,
        reservation_binding,
        decision["request"],
        owner_result,
        pre_commit_verification,
        settled_at=settled_at,
        expected_version=expected_version,
        idempotency_key=idempotency_key,
        skills_root=skills_root,
    )
    if replay is not None:
        return replay
    if state.get("status") != "reserved" or state.get("version") != expected_version:
        raise SystemExit("Owner settlement requires the expected reserved CAS state.")
    validate_pre_commit_verification(
        root,
        reservation,
        reservation_binding,
        pre_commit_verification,
        expected_version=expected_version,
        require_current_state=True,
    )
    current_validation = invoke_registered_owner_validator(
        root,
        decision["request"],
        owner_result,
        reservation_binding,
        pre_commit_verification,
        phase="current",
        skills_root=skills_root,
    )
    validation = invoke_registered_owner_validator(
        root,
        decision["request"],
        owner_result,
        reservation_binding,
        pre_commit_verification,
        phase="historical",
        skills_root=skills_root,
    )
    if not _same_owner_boundary(current_validation, validation):
        raise SystemExit(
            "Current and historical owner validators disagree on the effect boundary."
        )
    validation_binding = publish_owner_validation_receipt(root, validation)
    outcome = validation["outcome"]
    if outcome == "confirmed_effect":
        settlement = _consume_registered_owner(
            root,
            reservation_ref,
            reservation_sha256,
            owner_result,
            validation_binding,
            pre_commit_verification=pre_commit_verification,
            consumed_at=settled_at,
            expected_version=expected_version,
            idempotency_key=idempotency_key,
            skills_root=skills_root,
        )
        status = "consumed"
    else:
        settlement = _release_registered_owner(
            root,
            reservation_ref,
            reservation_sha256,
            validation_binding,
            released_at=settled_at,
            expected_version=expected_version,
            idempotency_key=idempotency_key,
            effect_status=(
                "verified_no_effect"
                if outcome == "confirmed_no_effect"
                else "unknown_effect"
            ),
            skills_root=skills_root,
        )
        status = "released" if outcome == "confirmed_no_effect" else "quarantined"
    return {
        "status": status,
        "outcome": outcome,
        "owner_validation": validation_binding,
        "owner_validation_receipt": validation,
        "settlement": settlement,
    }


__all__ = ("settle_owner_result",)
