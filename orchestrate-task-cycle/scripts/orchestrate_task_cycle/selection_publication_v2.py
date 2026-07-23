"""Compiler-owned, body-free selection publication protocol v2."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .selection_decision_receipt import validate_selection_decision_receipt
from .selection_decision_store import (
    normalize_binding,
    read_bound_bytes,
    read_bound_json,
)
from .selection_publication_plan import MAX_TARGET_BYTES, OPAQUE_ID, SHA256
from .selection_publication_payload import (
    payload_for_target,
    task_id as _task_id,
)
from .selection_publication_external import (
    external_intent_identity,
    prospective_plan_assertion as _prospective_plan_assertion,
    validate_external_pending_assertion,
    validate_external_settlement_assertion,
)
from .selection_publication_store import (
    _sha256_bytes,
    _sha256_file,
)


INTENT_KEYS = {
    "schema_version",
    "kind",
    "source_decision",
    "task_source",
    "owner_receipts",
}
PREPARE_KEYS = {
    "schema_version",
    "kind",
    "selection_id",
    "source_decision_id",
    "source_decision_sha256",
    "source_decision",
    "publication_mode",
    "owner_assertions",
    "targets",
    "compiler_metrics",
}
EXTERNAL_PREPARE_KEYS = PREPARE_KEYS | {"task_state_plan", "intent_sha256"}
TARGET_KEYS = {
    "role",
    "target_ref",
    "before_sha256",
    "after_sha256",
    "payload_ref",
    "payload_sha256",
    "payload_size",
}
ASSERTION_KEYS = {
    "kind",
    "receipt",
    "plan",
    "ledger_ref",
    "ledger_sha256",
    "markdown_ref",
    "markdown_sha256",
}
TRANSITION_RECEIPT_KEYS = {
    "schema_version",
    "receipt_kind",
    "plan_id",
    "plan_ref",
    "plan_sha256",
    "plan_file_sha256",
    "applied_at",
    "ledger_after_sha256",
    "markdown_after_sha256",
    "event_count",
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


def _transition_assertion(
    root: Path, binding_value: Any
) -> tuple[dict[str, Any], dict[str, Any]]:
    binding = normalize_binding(binding_value, "task-state transition receipt")
    _, receipt = read_bound_json(root, binding, "task-state transition receipt")
    _closed(receipt, TRANSITION_RECEIPT_KEYS, "task-state transition receipt")
    if (
        receipt.get("schema_version") != 1
        or receipt.get("receipt_kind") != "task_state_transition_apply_receipt"
        or not OPAQUE_ID.fullmatch(str(receipt.get("plan_id") or ""))
    ):
        raise ValueError("task-state transition receipt contract is invalid")
    body = {
        key: value for key, value in receipt.items() if key != "receipt_content_sha256"
    }
    if receipt.get("receipt_content_sha256") != _compact_sha256(body):
        raise ValueError("task-state transition receipt integrity check failed")

    plan_binding = normalize_binding(
        {
            "ref": receipt["plan_ref"],
            "sha256": receipt["plan_file_sha256"],
        },
        "task-state transition plan",
    )
    _, plan_payload = read_bound_bytes(root, plan_binding, "task-state transition plan")
    try:
        plan = json.loads(plan_payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("task-state transition plan must contain JSON") from exc
    required_plan_keys = {
        "schema_version",
        "plan_kind",
        "plan_id",
        "created_at",
        "request",
        "request_sha256",
        "ledger",
        "markdown",
        "artifact_anchors",
        "events",
        "plan_sha256",
    }
    _closed(plan, required_plan_keys, "task-state transition plan")
    plan_body = {key: value for key, value in plan.items() if key != "plan_sha256"}
    request = plan.get("request")
    events = plan.get("events")
    if (
        plan.get("schema_version") != 1
        or plan.get("plan_kind") != "task_state_transition_plan"
        or plan.get("plan_id") != receipt["plan_id"]
        or plan.get("plan_sha256") != receipt["plan_sha256"]
        or plan.get("plan_sha256") != _compact_sha256(plan_body)
        or plan_payload
        != json.dumps(
            plan, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        + b"\n"
        or not isinstance(request, dict)
        or plan.get("request_sha256") != _compact_sha256(request)
        or not isinstance(events, list)
        or len(events) != receipt.get("event_count")
        or any(
            not isinstance(event, dict)
            or event.get("transition_plan_id") != plan.get("plan_id")
            for event in events
        )
    ):
        raise ValueError("task-state transition plan integrity check failed")
    ledger = plan.get("ledger")
    markdown = plan.get("markdown")
    if not isinstance(ledger, dict) or not isinstance(markdown, dict):
        raise ValueError("task-state transition projection contract is invalid")
    if (
        ledger.get("path") != ".task/index.jsonl"
        or markdown.get("path") != ".task/index.md"
        or ledger.get("after_sha256") != receipt["ledger_after_sha256"]
        or markdown.get("after_sha256") != receipt["markdown_after_sha256"]
        or receipt.get("event_count") != ledger.get("event_count")
    ):
        raise ValueError("task-state transition receipt differs from its plan")
    assertion = {
        "kind": "task_state_transition_apply_receipt",
        "receipt": binding,
        "plan": plan_binding,
        "ledger_ref": ".task/index.jsonl",
        "ledger_sha256": receipt["ledger_after_sha256"],
        "markdown_ref": ".task/index.md",
        "markdown_sha256": receipt["markdown_after_sha256"],
    }
    validate_owner_assertion(root, assertion)
    return assertion, plan


def validate_owner_assertion(root: Path, assertion_value: Any) -> dict[str, Any]:
    assertion = _closed(
        assertion_value, ASSERTION_KEYS, "selection publication owner assertion"
    )
    if assertion.get("kind") != "task_state_transition_apply_receipt":
        raise ValueError("selection publication owner assertion kind is unsupported")
    for field in ("ledger_sha256", "markdown_sha256"):
        if not isinstance(assertion.get(field), str) or not SHA256.fullmatch(
            assertion[field]
        ):
            raise ValueError("selection publication owner assertion digest is invalid")
    normalize_binding(assertion.get("receipt"), "task-state transition receipt")
    normalize_binding(assertion.get("plan"), "task-state transition plan")
    for ref_field, digest_field in (
        ("ledger_ref", "ledger_sha256"),
        ("markdown_ref", "markdown_sha256"),
    ):
        expected_ref = (
            ".task/index.jsonl" if ref_field == "ledger_ref" else ".task/index.md"
        )
        if assertion.get(ref_field) != expected_ref:
            raise ValueError("selection publication owner projection ref is invalid")
        if _sha256_file(root / expected_ref) != assertion[digest_field]:
            raise ValueError("selection publication owner projection has drifted")
    return assertion


def _selected_source(
    root: Path,
    source_binding_value: Any,
    *,
    expected_active_prepare: Any = None,
) -> tuple[dict[str, str], dict[str, Any]]:
    binding = normalize_binding(source_binding_value, "selection decision receipt")
    _, raw = read_bound_json(root, binding, "selection decision receipt")
    schema_version = raw.get("schema_version")
    if not isinstance(schema_version, int) or isinstance(schema_version, bool):
        raise ValueError("selection decision receipt schema_version is unsupported")
    if schema_version == 1:
        trigger_binding = normalize_binding(
            raw.get("trigger_selection_tick"), "selection trigger tick"
        )
        _, trigger = read_bound_json(root, trigger_binding, "selection trigger tick")
        receipt = validate_selection_decision_receipt(
            root, raw, expected_trigger_tick=trigger
        )
    elif schema_version == 2:
        from .selection_decision_receipt_v2 import (
            validate_selection_decision_receipt_v2,
        )

        receipt = validate_selection_decision_receipt_v2(
            root, raw, expected_active_prepare=expected_active_prepare
        )
    elif schema_version == 3:
        from .selection_decision_receipt_v3 import (
            validate_selection_decision_receipt_v3,
        )

        expected_ref = (
            f".task/selection_reentry/receipts/sha256/{binding['sha256']}.json"
        )
        if binding["ref"] != expected_ref:
            raise ValueError(
                "selection decision receipt v3 must use its exact CAS path"
            )
        receipt = validate_selection_decision_receipt_v3(
            root, raw, expected_active_prepare=expected_active_prepare
        )
    else:
        raise ValueError("selection decision receipt schema_version is unsupported")
    if receipt.get("outcome") != "selected":
        raise ValueError("selection publication intent requires a selected decision")
    return binding, receipt


def validate_selected_source(
    root: Path, source_binding_value: Any
) -> tuple[dict[str, str], dict[str, Any]]:
    """Fully validate one selection receipt before any dependent artifact write."""

    binding, receipt = _selected_source(root, source_binding_value)
    if receipt.get("outcome") != "selected":
        raise ValueError("selection publication requires a selected decision")
    return binding, receipt


def compile_intent(root: Path, raw: dict[str, Any]) -> tuple[dict[str, Any], bytes]:
    """Compile one exact intent into canonical v2 prepare material without writing."""

    root = root.expanduser().resolve(strict=True)
    if raw.get("schema_version") != 2:
        raise ValueError(
            "Legacy schema-v1 selection publication intents are recovery-only "
            "and cannot compile new prepares"
        )
    intent, intent_sha256 = external_intent_identity(raw)
    source_binding, selected = _selected_source(root, intent["source_decision"])
    task_binding = normalize_binding(intent["task_source"], "selection task source")
    if selected.get("schema_version") == 3:
        receipt_task_source = normalize_binding(
            selected.get("task_source"), "selection decision receipt task source"
        )
        if task_binding != receipt_task_source:
            raise ValueError(
                "selection task source differs from the exact receipt task source"
            )
    _, task_payload = read_bound_bytes(root, task_binding, "selection task source")
    selection_id = _task_id(task_payload)
    if selection_id != selected.get("selected_task_id"):
        raise ValueError("selected task source differs from the decision task ID")
    plan_binding = _prospective_plan_assertion(
        root, intent["task_state_plan"], task_binding, selection_id
    )
    if len(task_payload) > MAX_TARGET_BYTES:
        raise ValueError("selection task source exceeds the size limit")
    task_sha = _sha256_bytes(task_payload)
    normalized = {
        "schema_version": 3,
        "kind": "selection_publication_prepare",
        "selection_id": selection_id,
        "source_decision_id": str(selected["receipt_id"]),
        "source_decision_sha256": source_binding["sha256"],
        "source_decision": source_binding,
        "publication_mode": "selected_successor_external_settlement",
        "owner_assertions": [],
        "task_state_plan": plan_binding,
        "intent_sha256": intent_sha256,
        "targets": [
            {
                "role": "task_alias",
                "target_ref": "task.md",
                "before_sha256": _sha256_file(root / "task.md"),
                "after_sha256": task_sha,
                "payload_ref": f".task/selection_publication/blobs/sha256/{task_sha}",
                "payload_sha256": task_sha,
                "payload_size": len(task_payload),
            }
        ],
        "compiler_metrics": {
            "inline_payload_bytes": 0,
            "model_authored_mechanical_bytes": 0,
            "task_payload_bytes": len(task_payload),
        },
    }
    return normalized, task_payload


def normalize_prepare(root: Path, raw: dict[str, Any]) -> dict[str, Any]:
    """Validate canonical v2 prepare fields without reopening large payloads."""

    helper = {"transaction_id", "predecessor_transaction_id"}
    material = {key: value for key, value in raw.items() if key not in helper}
    schema_version = material.get("schema_version")
    expected_keys = EXTERNAL_PREPARE_KEYS if schema_version == 3 else PREPARE_KEYS
    _closed(material, expected_keys, "selection publication prepare")
    if schema_version not in {2, 3} or material.get("kind") != (
        "selection_publication_prepare"
    ):
        raise ValueError("selection publication v2 prepare contract is invalid")
    if not OPAQUE_ID.fullmatch(str(material.get("selection_id") or "")) or not (
        OPAQUE_ID.fullmatch(str(material.get("source_decision_id") or ""))
    ):
        raise ValueError("selection publication v2 prepare IDs are invalid")
    source = normalize_binding(
        material.get("source_decision"), "selection publication source decision"
    )
    if source["sha256"] != material.get("source_decision_sha256"):
        raise ValueError("selection publication v2 source binding is inconsistent")
    if material.get("publication_mode") not in {
        "selected_successor",
        "task_state_reconciliation",
        "selected_successor_external_settlement",
    }:
        raise ValueError("selection publication v2 mode is invalid")
    assertions = material.get("owner_assertions")
    expected_assertions = 0 if schema_version == 3 else 1
    if not isinstance(assertions, list) or len(assertions) != expected_assertions:
        raise ValueError("selection publication owner assertion count is invalid")
    for assertion in assertions:
        _closed(assertion, ASSERTION_KEYS, "selection publication owner assertion")
        normalize_binding(assertion.get("receipt"), "task-state transition receipt")
        normalize_binding(assertion.get("plan"), "task-state transition plan")
    if schema_version == 3:
        normalize_binding(
            material.get("task_state_plan"), "prospective task-state transition plan"
        )
        if not isinstance(material.get("intent_sha256"), str) or not SHA256.fullmatch(
            material["intent_sha256"]
        ):
            raise ValueError("selection publication intent digest is invalid")
    targets = material.get("targets")
    if not isinstance(targets, list) or len(targets) != 1:
        raise ValueError("selection publication v2 requires one task_alias target")
    target = _closed(targets[0], TARGET_KEYS, "selection publication v2 target")
    if target.get("role") != "task_alias" or target.get("target_ref") != "task.md":
        raise ValueError("selection publication v2 target must be task_alias")
    before = target.get("before_sha256")
    if before is not None and (
        not isinstance(before, str) or not SHA256.fullmatch(before)
    ):
        raise ValueError("selection publication v2 before digest is invalid")
    after = target.get("after_sha256")
    size = target.get("payload_size")
    expected_ref = f".task/selection_publication/blobs/sha256/{after}"
    if (
        not isinstance(after, str)
        or not SHA256.fullmatch(after)
        or target.get("payload_sha256") != after
        or target.get("payload_ref") != expected_ref
        or not isinstance(size, int)
        or isinstance(size, bool)
        or size < 0
        or size > MAX_TARGET_BYTES
    ):
        raise ValueError("selection publication v2 payload binding is invalid")
    metrics = material.get("compiler_metrics")
    if metrics != {
        "inline_payload_bytes": 0,
        "model_authored_mechanical_bytes": 0,
        "task_payload_bytes": size,
    }:
        raise ValueError("selection publication v2 compiler metrics are invalid")
    normalized = dict(material)
    if "predecessor_transaction_id" in raw:
        normalized["predecessor_transaction_id"] = raw.get("predecessor_transaction_id")
    if "transaction_id" in raw:
        normalized["transaction_id"] = raw.get("transaction_id")
    return normalized


__all__ = (
    "compile_intent",
    "external_intent_identity",
    "normalize_prepare",
    "payload_for_target",
    "validate_external_pending_assertion",
    "validate_external_settlement_assertion",
    "validate_owner_assertion",
    "validate_selected_source",
)
