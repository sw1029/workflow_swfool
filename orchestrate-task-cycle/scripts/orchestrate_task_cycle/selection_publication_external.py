"""External task-state settlement contract for selection publication v3."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .selection_decision_store import (
    normalize_binding,
    read_bound_bytes,
    read_bound_json,
)
from .selection_publication_store import (
    _canonical_json,
    _sha256_file,
)


EXTERNAL_INTENT_KEYS = {
    "schema_version",
    "kind",
    "source_decision",
    "task_source",
    "task_state_plan",
}
PENDING_RECEIPT_KEYS = {
    "schema_version",
    "receipt_kind",
    "activation_status",
    "plan_id",
    "plan_ref",
    "plan_sha256",
    "plan_file_sha256",
    "applied_at",
    "ledger_after_sha256",
    "markdown_after_sha256",
    "event_count",
    "external_prepare",
    "receipt_content_sha256",
}
SETTLED_RECEIPT_KEYS = {
    "schema_version",
    "receipt_kind",
    "activation_status",
    "plan_id",
    "plan_ref",
    "plan_sha256",
    "plan_file_sha256",
    "applied_at",
    "ledger_after_sha256",
    "markdown_after_sha256",
    "event_count",
    "pending_receipt",
    "external_prepare",
    "external_commit",
    "receipt_content_sha256",
}


def _closed(value: Any, keys: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise ValueError(f"{label} requires exact fields {sorted(keys)}")
    return value


def _compact_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()


def task_event_matches(
    plan: dict[str, Any], task_id: str, task_sha256: str
) -> bool:
    events = plan.get("events")
    if not isinstance(events, list):
        return False
    matches = [
        row
        for row in events
        if isinstance(row, dict)
        and row.get("event") == "upsert"
        and row.get("type") == "task"
        and row.get("status") == "active"
        and row.get("path") == "task.md"
        and row.get("id") == task_id
        and row.get("content_sha256") == task_sha256
    ]
    return len(matches) == 1


def external_intent_identity(
    raw: dict[str, Any],
) -> tuple[dict[str, Any], str]:
    """Normalize a v3 source intent without reopening historical dependencies."""

    intent = _closed(
        raw, EXTERNAL_INTENT_KEYS, "external selection publication intent"
    )
    if (
        intent.get("schema_version") != 2
        or intent.get("kind") != "selection_publication_intent"
    ):
        raise ValueError("selection publication intent contract is invalid")
    normalized = {
        "schema_version": 2,
        "kind": "selection_publication_intent",
        "source_decision": normalize_binding(
            intent.get("source_decision"), "selection publication source decision"
        ),
        "task_source": normalize_binding(
            intent.get("task_source"), "selection task source"
        ),
        "task_state_plan": normalize_binding(
            intent.get("task_state_plan"), "prospective task-state transition plan"
        ),
    }
    return normalized, _compact_sha256(normalized)


def prospective_plan_assertion(
    root: Path,
    binding_value: Any,
    task_binding: dict[str, str],
    task_id: str,
) -> dict[str, str]:
    binding = normalize_binding(binding_value, "prospective task-state transition plan")
    _, payload = read_bound_bytes(
        root, binding, "prospective task-state transition plan"
    )
    try:
        plan = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(
            "prospective task-state transition plan must contain JSON"
        ) from exc
    if not isinstance(plan, dict):
        raise ValueError("prospective task-state transition plan must be an object")
    body = {key: value for key, value in plan.items() if key != "plan_sha256"}
    request = plan.get("request")
    sources = request.get("artifact_sources") if isinstance(request, dict) else None
    source_matches = [
        row
        for row in sources or []
        if isinstance(row, dict)
        and row.get("target_ref") == "task.md"
        and row.get("source") == task_binding
    ]
    anchors = [
        row
        for row in plan.get("artifact_anchors", [])
        if isinstance(row, dict)
        and row.get("path") == "task.md"
        and row.get("expectation") == "prospective_source_sha256"
        and row.get("expected_sha256") == task_binding["sha256"]
    ]
    if (
        plan.get("schema_version") != 2
        or plan.get("plan_kind") != "task_state_transition_plan"
        or not isinstance(request, dict)
        or request.get("schema_version") != 2
        or request.get("external_settlement_kind") != "selection_publication"
        or plan.get("plan_sha256") != _compact_sha256(body)
        or payload != _canonical_json(plan)
        or len(source_matches) != 1
        or len(anchors) != 1
        or not task_event_matches(plan, task_id, task_binding["sha256"])
    ):
        raise ValueError(
            "prospective task-state transition plan does not bind the selected task"
        )
    return binding


def validate_external_pending_assertion(
    root: Path,
    prepare: dict[str, Any],
    prepare_binding: dict[str, str],
    *,
    require_current_projections: bool = True,
) -> dict[str, str]:
    """Validate the actual task-state owner's pending activation receipt."""

    plan_binding = normalize_binding(
        prepare.get("task_state_plan"), "prospective task-state transition plan"
    )
    _, plan_payload = read_bound_bytes(
        root, plan_binding, "prospective task-state transition plan"
    )
    try:
        plan = json.loads(plan_payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("prospective task-state transition plan is unreadable") from exc
    plan_id = plan.get("plan_id") if isinstance(plan, dict) else None
    if not isinstance(plan_id, str):
        raise ValueError("prospective task-state transition plan ID is invalid")
    receipt_binding = {
        "ref": f".task/transition_pending_receipts/{plan_id}.json",
        "sha256": _sha256_file(
            root / f".task/transition_pending_receipts/{plan_id}.json"
        ),
    }
    if receipt_binding["sha256"] is None:
        raise ValueError("task-state activation is not pending external settlement")
    binding = normalize_binding(receipt_binding, "task-state pending receipt")
    _, receipt = read_bound_json(root, binding, "task-state pending receipt")
    _closed(receipt, PENDING_RECEIPT_KEYS, "task-state pending receipt")
    body = {
        key: value
        for key, value in receipt.items()
        if key != "receipt_content_sha256"
    }
    ledger = plan.get("ledger") or {}
    markdown = plan.get("markdown") or {}
    if (
        receipt.get("schema_version") != 2
        or receipt.get("receipt_kind")
        != "task_state_transition_pending_receipt"
        or receipt.get("activation_status") != "pending_external_settlement"
        or receipt.get("plan_id") != plan_id
        or receipt.get("plan_ref") != plan_binding["ref"]
        or receipt.get("plan_sha256") != plan.get("plan_sha256")
        or receipt.get("plan_file_sha256") != plan_binding["sha256"]
        or receipt.get("external_prepare") != prepare_binding
        or receipt.get("ledger_after_sha256") != ledger.get("after_sha256")
        or receipt.get("markdown_after_sha256") != markdown.get("after_sha256")
        or receipt.get("event_count") != ledger.get("event_count")
        or receipt.get("receipt_content_sha256") != _compact_sha256(body)
    ):
        raise ValueError(
            "task-state pending receipt does not bind the publication prepare"
        )
    if require_current_projections and (
        _sha256_file(root / ".task/index.jsonl")
        != receipt.get("ledger_after_sha256")
        or _sha256_file(root / ".task/index.md")
        != receipt.get("markdown_after_sha256")
    ):
        raise ValueError("task-state pending receipt projection has drifted")
    return binding


def _settlement_receipt(
    root: Path, plan_id: str
) -> tuple[dict[str, str], dict[str, Any]]:
    binding_value = {
        "ref": f".task/transition_receipts/{plan_id}.json",
        "sha256": _sha256_file(root / f".task/transition_receipts/{plan_id}.json"),
    }
    if binding_value["sha256"] is None:
        raise ValueError("task-state external settlement receipt is missing")
    binding = normalize_binding(
        binding_value, "task-state external settlement receipt"
    )
    _, receipt = read_bound_json(
        root, binding, "task-state external settlement receipt"
    )
    return binding, _closed(
        receipt, SETTLED_RECEIPT_KEYS, "task-state external settlement receipt"
    )


def validate_external_settlement_assertion(
    root: Path,
    publication_receipt: dict[str, Any],
    publication_binding_value: dict[str, str],
    *,
    phase: str = "current",
) -> dict[str, str]:
    """Delegate append-aware settlement proof to the task-index owner."""

    from .selection_publication_v2 import normalize_prepare

    publication_binding = normalize_binding(
        publication_binding_value, "selection publication receipt"
    )
    prepare_binding = normalize_binding(
        {
            "ref": publication_receipt.get("prepare_ref"),
            "sha256": publication_receipt.get("prepare_sha256"),
        },
        "selection publication prepare",
    )
    _, prepare = read_bound_json(root, prepare_binding, "selection publication prepare")
    prepare = normalize_prepare(root, prepare)
    if prepare.get("schema_version") != 3:
        raise ValueError("selection publication does not require external settlement")
    plan_binding = normalize_binding(
        prepare.get("task_state_plan"), "prospective task-state transition plan"
    )
    _, plan = read_bound_json(root, plan_binding, "prospective task-state transition plan")
    request = plan.get("request") if isinstance(plan, dict) else None
    sources = request.get("artifact_sources") if isinstance(request, dict) else None
    task_sources = [
        row.get("source")
        for row in sources or []
        if isinstance(row, dict) and row.get("target_ref") == "task.md"
    ]
    if len(task_sources) != 1:
        raise ValueError("prospective task-state plan has no unique task source")
    task_source = normalize_binding(task_sources[0], "prospective task source")
    prospective_plan_assertion(
        root, plan_binding, task_source, str(prepare.get("selection_id") or "")
    )
    plan_id = plan.get("plan_id")
    if publication_receipt.get("external_settlement_plan_id") != plan_id:
        raise ValueError("selection publication settlement plan binding differs")
    expected_pending = validate_external_pending_assertion(
        root, prepare, prepare_binding, require_current_projections=False
    )
    if publication_receipt.get("owner_pending_receipt") != expected_pending:
        raise ValueError("selection publication pending owner binding differs")
    settlement_binding, settlement = _settlement_receipt(root, str(plan_id))
    body = {
        key: value
        for key, value in settlement.items()
        if key != "receipt_content_sha256"
    }
    ledger = plan.get("ledger") if isinstance(plan.get("ledger"), dict) else {}
    markdown = plan.get("markdown") if isinstance(plan.get("markdown"), dict) else {}
    if (
        settlement.get("schema_version") != 2
        or settlement.get("receipt_kind") != "task_state_transition_apply_receipt"
        or settlement.get("activation_status") != "settled"
        or settlement.get("plan_id") != plan_id
        or settlement.get("plan_ref") != plan_binding["ref"]
        or settlement.get("plan_sha256") != plan.get("plan_sha256")
        or settlement.get("plan_file_sha256") != plan_binding["sha256"]
        or settlement.get("applied_at") != plan.get("created_at")
        or settlement.get("ledger_after_sha256") != ledger.get("after_sha256")
        or settlement.get("markdown_after_sha256") != markdown.get("after_sha256")
        or settlement.get("event_count") != ledger.get("event_count")
        or settlement.get("pending_receipt") != expected_pending
        or settlement.get("external_prepare") != prepare_binding
        or settlement.get("external_commit") != publication_binding
        or settlement.get("receipt_content_sha256") != _compact_sha256(body)
    ):
        raise ValueError("task-state external settlement receipt is inconsistent")
    try:
        from manage_task_state_index.state.owner_validation import (
            validate_external_transition_receipt,
        )
    except ImportError as exc:  # pragma: no cover - packaging failure, not fallback.
        raise ValueError("task-state owner settlement validator is unavailable") from exc
    owner_validation = validate_external_transition_receipt(
        root, settlement_binding, phase=phase
    )
    if (
        owner_validation.get("status") != "valid"
        or owner_validation.get("plan_id") != plan_id
        or owner_validation.get("receipt_binding") != settlement_binding
        or owner_validation.get("selection_consumption_allowed") is not True
    ):
        raise ValueError("task-state owner settlement validation is inconsistent")
    return settlement_binding


__all__ = (
    "external_intent_identity",
    "prospective_plan_assertion",
    "task_event_matches",
    "validate_external_pending_assertion",
    "validate_external_settlement_assertion",
)
