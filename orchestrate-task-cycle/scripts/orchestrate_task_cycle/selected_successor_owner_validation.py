"""Static owner validation for selected-successor authority settlement."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .selection_decision_store import normalize_binding, read_bound_json
from .selection_publication import _load_prepare, validate_receipt


OPERATIONS = {
    "publish_selected_successor_topology",
    "settle_selected_successor_task_state",
}


def _seal(body: dict[str, Any]) -> dict[str, Any]:
    payload = json.dumps(
        body, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return {**body, "receipt_sha256": hashlib.sha256(payload).hexdigest()}


def _authority_request(
    root: Path, reservation_value: dict[str, str]
) -> tuple[dict[str, str], dict[str, Any]]:
    reservation_binding = normalize_binding(
        reservation_value, "authority reservation"
    )
    _, reservation = read_bound_json(
        root, reservation_binding, "authority reservation"
    )
    if (
        reservation.get("schema_version") != 2
        or reservation.get("artifact_kind") != "authority_reservation"
    ):
        raise ValueError("Selected-successor authority reservation is invalid")
    decision_binding = normalize_binding(
        reservation.get("decision"), "authority reservation decision"
    )
    _, decision = read_bound_json(
        root, decision_binding, "authority reservation decision"
    )
    request = decision.get("request") if isinstance(decision, dict) else None
    if not isinstance(request, dict):
        raise ValueError("Selected-successor authority decision request is invalid")
    return reservation_binding, request


def _operation_request(
    request: dict[str, Any], operation: str, subject_kind: str
) -> dict[str, Any]:
    expected = {
        "skill_id": "orchestrate-task-cycle",
        "skill_version": "2.0.0",
        "operation_id": operation,
        "operation_version": "1",
    }
    if any(request.get(key) != value for key, value in expected.items()):
        raise ValueError("Authority request operation differs from the fixed owner validator")
    subject = request.get("subject")
    if not isinstance(subject, dict) or subject.get("kind") != subject_kind:
        raise ValueError("Authority request subject kind differs from the owner contract")
    return subject


def _publication_validation(
    root: Path,
    owner_result: dict[str, str],
    request: dict[str, Any],
    *,
    phase: str,
) -> dict[str, Any]:
    subject = _operation_request(
        request,
        "publish_selected_successor_topology",
        "selection_publication_binding",
    )
    binding = normalize_binding(owner_result, "selection publication owner result")
    path = Path(binding["ref"])
    transaction_id = path.stem
    if path.as_posix() != (
        f".task/selection_publication/receipts/{transaction_id}.json"
    ):
        raise ValueError("Selection publication owner result path is not canonical")
    receipt = validate_receipt(
        root, transaction_id, require_current_targets=phase == "current"
    )
    if (
        receipt.get("receipt_ref") != binding["ref"]
        or receipt.get("receipt_sha256") != binding["sha256"]
    ):
        raise ValueError("Selection publication owner result binding differs")
    prepare, prepare_path, prepare_sha256 = _load_prepare(root, transaction_id)
    prepare_binding = {
        "ref": prepare_path.relative_to(root).as_posix(),
        "sha256": prepare_sha256,
    }
    expected_subject = {
        "kind": "selection_publication_binding",
        "ref": prepare_binding["ref"],
        "digest": prepare_binding["sha256"],
        "revision": transaction_id,
    }
    if subject != expected_subject or prepare.get("schema_version") != 3:
        raise ValueError("Selection publication authority subject differs from its prepare")
    targets = prepare.get("targets")
    target = targets[0] if isinstance(targets, list) and len(targets) == 1 else None
    if not isinstance(target, dict) or target.get("target_ref") != "task.md":
        raise ValueError("Selection publication prepare lacks one task.md CAS target")
    from manage_task_state_index.state.transition_plan_contract import (
        load_transition_plan,
    )

    plan_binding = normalize_binding(
        prepare.get("task_state_plan"), "selected-successor task-state plan"
    )
    _plan_path, plan, plan_sha256 = load_transition_plan(root, plan_binding["ref"])
    if plan_sha256 != plan_binding["sha256"]:
        raise ValueError("Selected-successor task-state plan binding differs")
    return {
        "subject": {
            "kind": "task_alias",
            "ref": "task.md",
            "before_sha256": target.get("before_sha256"),
            "after_sha256": target.get("after_sha256"),
        },
        "projection": {
            "ref": "task.md",
            "before_sha256": target.get("before_sha256"),
            "after_sha256": target.get("after_sha256"),
        },
        "plan": prepare_binding,
        "event_batch": {
            "plan_id": transaction_id,
            "before_event_count": 0,
            "event_count": 1,
            "event_payload_sha256": binding["sha256"],
        },
        "descendant_event_count": 0,
        "validated_at": plan.get("created_at"),
    }


def _settlement_validation(
    root: Path,
    owner_result: dict[str, str],
    request: dict[str, Any],
    *,
    phase: str,
) -> dict[str, Any]:
    subject = _operation_request(
        request,
        "settle_selected_successor_task_state",
        "task_state_transition_plan",
    )
    binding = normalize_binding(owner_result, "selected-successor settlement result")
    from manage_task_state_index.state.owner_validation import (
        validate_external_transition_receipt,
    )

    validated = validate_external_transition_receipt(root, binding, phase=phase)
    plan_binding = validated.get("plan_binding")
    expected_subject = {
        "kind": "task_state_transition_plan",
        "ref": plan_binding.get("ref") if isinstance(plan_binding, dict) else None,
        "digest": plan_binding.get("sha256") if isinstance(plan_binding, dict) else None,
        "revision": validated.get("plan_id"),
    }
    if (
        validated.get("status") != "valid"
        or validated.get("effect_status") != "confirmed_effect"
        or validated.get("receipt_binding") != binding
        or validated.get("selection_consumption_allowed") is not True
        or subject != expected_subject
    ):
        raise ValueError("Selected-successor settlement owner proof is inconsistent")
    return {
        "subject": validated["subject"],
        "projection": validated["projection"],
        "plan": plan_binding,
        "event_batch": validated["event_batch"],
        "descendant_event_count": validated["descendant_event_count"],
        "validated_at": validated["validated_at"],
    }


def validate_selected_successor_owner_result(
    root: Path,
    *,
    operation: str,
    owner_result: dict[str, str],
    reservation: dict[str, str],
    pre_commit_verification: dict[str, str],
    phase: str = "current",
) -> dict[str, Any]:
    """Return one deterministic closed authority owner-validation receipt."""

    if operation not in OPERATIONS:
        raise ValueError("Selected-successor owner operation is unsupported")
    if phase not in {"current", "historical"}:
        raise ValueError("Selected-successor validation phase is invalid")
    root = root.resolve()
    reservation_binding, request = _authority_request(root, reservation)
    precommit_binding = normalize_binding(
        pre_commit_verification, "authority pre-commit verification"
    )
    read_bound_json(root, precommit_binding, "authority pre-commit verification")
    binding = normalize_binding(owner_result, "selected-successor owner result")
    validated = (
        _publication_validation(root, binding, request, phase=phase)
        if operation == "publish_selected_successor_topology"
        else _settlement_validation(root, binding, request, phase=phase)
    )
    return _seal(
        {
            "schema_version": 1,
            "artifact_kind": "owner_validation_receipt",
            "operation": operation,
            "validation_status": "valid",
            "outcome": "confirmed_effect",
            "owner_result": binding,
            "reservation": reservation_binding,
            "pre_commit_verification": precommit_binding,
            "phase": phase,
            **validated,
        }
    )


__all__ = ("OPERATIONS", "validate_selected_successor_owner_result")
