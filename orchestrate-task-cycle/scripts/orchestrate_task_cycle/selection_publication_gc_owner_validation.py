"""Fixed owner-result validation for selection-publication GC effects."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .selection_publication_gc_archive import archive_payloads
from .selection_publication_gc_authority import (
    expected_subject,
    normalize_binding,
    validate_apply_receipt_contract,
    validate_restore_receipt_contract,
)
from .selection_publication_gc_contract import (
    MAX_CANDIDATE_BYTES,
    MAX_SCAN_FILE_BYTES,
    receipt_path,
    restore_receipt_path,
)
from .selection_publication_gc_fs import read_json_relative, read_relative
from .selection_publication_gc_scan import load_plan
from .selection_publication_store import _canonical_json, _sha256_bytes


OPERATIONS = {
    "apply_selection_publication_retention",
    "restore_selection_publication_retention",
}


def _seal(body: dict[str, Any]) -> dict[str, Any]:
    payload = json.dumps(
        body, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return {**body, "receipt_sha256": hashlib.sha256(payload).hexdigest()}


def _authority_request(
    root: Path, reservation_value: dict[str, str]
) -> tuple[dict[str, str], dict[str, Any]]:
    from .selection_decision_store import read_bound_json

    binding = normalize_binding(
        reservation_value, "selection-publication gc authority reservation"
    )
    _, reservation = read_bound_json(
        root, binding, "selection-publication gc authority reservation"
    )
    decision_binding = normalize_binding(
        reservation.get("decision"), "selection-publication gc authority decision"
    )
    _, decision = read_bound_json(
        root, decision_binding, "selection-publication gc authority decision"
    )
    request = decision.get("request") if isinstance(decision, dict) else None
    if not isinstance(request, dict):
        raise ValueError(
            "selection-publication gc authority request is invalid"
        )
    return binding, request


def _operation_subject(
    request: dict[str, Any], operation: str
) -> dict[str, Any]:
    expected = {
        "skill_id": "orchestrate-task-cycle",
        "skill_version": "2.0.0",
        "operation_id": operation,
        "operation_version": "1",
    }
    kinds = {
        "apply_selection_publication_retention":
            "selection_publication_gc_plan",
        "restore_selection_publication_retention":
            "selection_publication_gc_receipt",
    }
    subject = request.get("subject")
    if (
        any(request.get(key) != value for key, value in expected.items())
        or not isinstance(subject, dict)
        or subject.get("kind") != kinds[operation]
    ):
        raise ValueError(
            "selection-publication gc owner operation or subject differs"
        )
    return subject


def _precommit_time(
    root: Path, value: dict[str, str]
) -> tuple[dict[str, str], str]:
    from .selection_decision_store import read_bound_json

    binding = normalize_binding(
        value, "selection-publication gc pre-commit verification"
    )
    _, artifact = read_bound_json(
        root, binding, "selection-publication gc pre-commit verification"
    )
    if (
        artifact.get("artifact_kind") != "authority_verification"
        or artifact.get("stage") != "pre_commit"
        or not isinstance(artifact.get("verified_at"), str)
    ):
        raise ValueError(
            "selection-publication gc pre-commit verification is invalid"
        )
    return binding, artifact["verified_at"]


def _candidate_set_digest(plan: dict[str, Any], *, present: bool) -> str:
    rows = (
        [
            {
                "ref": row["ref"],
                "sha256": row["sha256"],
                "size_bytes": row["size_bytes"],
            }
            for row in plan["candidates"]
        ]
        if present
        else []
    )
    return _sha256_bytes(_canonical_json(rows))


def _validate_authority_projection(
    root: Path,
    receipt: dict[str, Any],
    *,
    operation: str,
    subject: dict[str, Any],
    reservation: dict[str, str],
    precommit: dict[str, str],
) -> None:
    authority = receipt.get("authority")
    if (
        not isinstance(authority, dict)
        or authority.get("reservation") != reservation
        or authority.get("pre_commit_verification") != precommit
        or not isinstance(authority.get("reservation_state_version"), int)
    ):
        raise ValueError(
            "selection-publication gc receipt authority differs"
        )
    try:
        from manage_agent_authority.effect_lease import validate_effect_lease

        validate_effect_lease(
            root,
            authority.get("effect_lease"),
            operation=operation,
            subject=subject,
            reservation=reservation,
            pre_commit_verification=precommit,
        )
    except (ImportError, SystemExit) as exc:
        raise ValueError(
            "selection-publication gc receipt effect lease is invalid"
        ) from exc


def _load_apply_owner(
    root: Path,
    owner_result: dict[str, str],
    request_subject: dict[str, Any],
    *,
    phase: str,
) -> tuple[dict[str, Any], dict[str, Any], str]:
    binding = normalize_binding(
        owner_result, "selection-publication gc apply owner result"
    )
    plan_id = Path(binding["ref"]).stem
    plan, plan_file, plan_sha = load_plan(root, plan_id)
    expected_path = receipt_path(root, plan_id)
    if binding["ref"] != expected_path.relative_to(root).as_posix():
        raise ValueError(
            "selection-publication gc apply owner result path is not canonical"
        )
    receipt, payload = read_json_relative(
        root, binding["ref"], "selection-publication gc apply owner result"
    )
    if _sha256_bytes(payload) != binding["sha256"] or payload != _canonical_json(
        receipt
    ):
        raise ValueError(
            "selection-publication gc apply owner result binding differs"
        )
    validate_apply_receipt_contract(
        receipt,
        plan=plan,
        plan_path=plan_file,
        plan_sha=plan_sha,
        root=root,
    )
    expected = expected_subject(
        root,
        operation="apply_selection_publication_retention",
        plan_id=plan_id,
        plan_path=plan_file,
        plan_sha=plan_sha,
    )
    if request_subject != expected:
        raise ValueError(
            "selection-publication gc apply request subject differs"
        )
    _validate_archive(root, receipt, plan)
    if phase == "current":
        _validate_candidates_absent(root, plan)
    return receipt, plan, plan_id


def _validate_archive(
    root: Path, receipt: dict[str, Any], plan: dict[str, Any]
) -> None:
    binding = normalize_binding(
        receipt.get("archive"), "selection-publication gc archive"
    )
    payload = read_relative(
        root,
        binding["ref"],
        "selection-publication gc archive",
        max_bytes=MAX_CANDIDATE_BYTES + MAX_SCAN_FILE_BYTES,
    )
    assert payload is not None
    if _sha256_bytes(payload) != binding["sha256"]:
        raise ValueError("selection-publication gc archive digest differs")
    archive_payloads(payload, plan)


def _validate_candidates_absent(root: Path, plan: dict[str, Any]) -> None:
    for row in plan["candidates"]:
        if read_relative(
            root,
            row["ref"],
            "selection-publication gc current apply candidate",
            required=False,
            max_bytes=MAX_CANDIDATE_BYTES,
        ) is not None:
            raise ValueError(
                "selection-publication gc apply candidate is still present"
            )


def _load_restore_owner(
    root: Path,
    owner_result: dict[str, str],
    request_subject: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], str, dict[str, str]]:
    binding = normalize_binding(
        owner_result, "selection-publication gc restore owner result"
    )
    plan_id = Path(binding["ref"]).stem
    plan, plan_file, plan_sha = load_plan(root, plan_id)
    expected_path = restore_receipt_path(root, plan_id)
    if binding["ref"] != expected_path.relative_to(root).as_posix():
        raise ValueError(
            "selection-publication gc restore owner result path is not canonical"
        )
    apply_path = receipt_path(root, plan_id)
    apply_receipt, apply_payload = read_json_relative(
        root,
        apply_path.relative_to(root).as_posix(),
        "selection-publication gc apply receipt",
    )
    validate_apply_receipt_contract(
        apply_receipt,
        plan=plan,
        plan_path=plan_file,
        plan_sha=plan_sha,
        root=root,
    )
    gc_binding = {
        "ref": apply_path.relative_to(root).as_posix(),
        "sha256": _sha256_bytes(apply_payload),
    }
    expected = expected_subject(
        root,
        operation="restore_selection_publication_retention",
        plan_id=plan_id,
        plan_path=plan_file,
        plan_sha=plan_sha,
    )
    if request_subject != expected:
        raise ValueError(
            "selection-publication gc restore request subject differs"
        )
    receipt, payload = read_json_relative(
        root, binding["ref"], "selection-publication gc restore owner result"
    )
    if _sha256_bytes(payload) != binding["sha256"] or payload != _canonical_json(
        receipt
    ):
        raise ValueError(
            "selection-publication gc restore owner result binding differs"
        )
    validate_restore_receipt_contract(
        receipt,
        plan_id=plan_id,
        gc_receipt=gc_binding,
        candidate_count=len(plan["candidates"]),
    )
    _validate_restored(root, plan)
    return receipt, plan, plan_id, gc_binding


def _validate_restored(root: Path, plan: dict[str, Any]) -> None:
    for row in plan["candidates"]:
        payload = read_relative(
            root,
            row["ref"],
            "selection-publication gc restored candidate",
            max_bytes=MAX_CANDIDATE_BYTES,
        )
        assert payload is not None
        if (
            len(payload) != row["size_bytes"]
            or _sha256_bytes(payload) != row["sha256"]
        ):
            raise ValueError(
                "selection-publication gc restored candidate differs"
            )


def validate_gc_owner_result(
    root: Path,
    *,
    operation: str,
    owner_result: dict[str, str],
    reservation: dict[str, str],
    pre_commit_verification: dict[str, str],
    phase: str = "current",
) -> dict[str, Any]:
    """Return one closed, reproducible authority owner-validation receipt."""

    if operation not in OPERATIONS or phase not in {"current", "historical"}:
        raise ValueError(
            "selection-publication gc owner validation mode is invalid"
        )
    root = root.resolve()
    reservation_binding, request = _authority_request(root, reservation)
    request_subject = _operation_subject(request, operation)
    precommit, validated_at = _precommit_time(
        root, pre_commit_verification
    )
    binding = normalize_binding(
        owner_result, "selection-publication gc owner result"
    )
    if operation == "apply_selection_publication_retention":
        receipt, plan, plan_id = _load_apply_owner(
            root, binding, request_subject, phase=phase
        )
        before_present, after_present = True, False
        plan_binding = receipt["plan"]
    else:
        receipt, plan, plan_id, plan_binding = _load_restore_owner(
            root, binding, request_subject
        )
        before_present, after_present = False, True
    _validate_authority_projection(
        root,
        receipt,
        operation=operation,
        subject=request_subject,
        reservation=reservation_binding,
        precommit=precommit,
    )
    count = len(plan["candidates"])
    outcome = "confirmed_effect" if count else "confirmed_no_effect"
    return _seal(
        {
            "schema_version": 1,
            "artifact_kind": "owner_validation_receipt",
            "validation_status": "valid",
            "outcome": outcome,
            "operation": operation,
            "owner_result": binding,
            "reservation": reservation_binding,
            "pre_commit_verification": precommit,
            "phase": phase,
            "subject": {
                "kind": "selection_publication_cas_set",
                "ref": ".task/selection_publication/blobs/sha256",
                "before_sha256": _candidate_set_digest(
                    plan, present=before_present
                ),
                "after_sha256": _candidate_set_digest(
                    plan, present=after_present
                ),
            },
            "plan": plan_binding,
            "event_batch": {
                "plan_id": plan_id,
                "before_event_count": count if before_present else 0,
                "event_count": count,
                "event_payload_sha256": binding["sha256"],
            },
            "descendant_event_count": 0,
            "validated_at": validated_at,
        }
    )


__all__ = ("OPERATIONS", "validate_gc_owner_result")
