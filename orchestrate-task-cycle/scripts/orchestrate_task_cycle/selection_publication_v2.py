"""Compiler-owned, body-free selection publication protocol v2."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Any

from .selection_decision_receipt import validate_selection_decision_receipt
from .selection_decision_store import (
    canonical_bytes,
    normalize_binding,
    read_bound_bytes,
    read_bound_json,
)
from .selection_publication_plan import MAX_TARGET_BYTES, OPAQUE_ID, SHA256
from .selection_publication_store import (
    _blob_path,
    _canonical_json,
    _sha256_bytes,
    _sha256_file,
    _write_once,
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
TASK_ID_LINE = re.compile(
    r"(?m)^\s*-\s*Task ID:\s*(?:`([^`\r\n]+)`|([^\s`\r\n]+))\s*$"
)


def _closed(value: Any, keys: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise ValueError(f"{label} requires exact fields {sorted(keys)}")
    return value


def _task_id(payload: bytes) -> str:
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("selection task source must be UTF-8 Markdown") from exc
    matches = TASK_ID_LINE.findall(text)
    identifiers = [left or right for left, right in matches]
    if len(identifiers) != 1 or not OPAQUE_ID.fullmatch(identifiers[0]):
        raise ValueError("selection task source requires exactly one bounded Task ID")
    return identifiers[0]


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
        or receipt.get("receipt_kind")
        != "task_state_transition_apply_receipt"
        or not OPAQUE_ID.fullmatch(str(receipt.get("plan_id") or ""))
    ):
        raise ValueError("task-state transition receipt contract is invalid")
    body = {
        key: value
        for key, value in receipt.items()
        if key != "receipt_content_sha256"
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


def _task_event_matches(
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
    root: Path, source_binding_value: Any
) -> tuple[dict[str, str], dict[str, Any]]:
    binding = normalize_binding(source_binding_value, "selection decision receipt")
    _, raw = read_bound_json(root, binding, "selection decision receipt")
    trigger_binding = normalize_binding(
        raw.get("trigger_selection_tick"), "selection trigger tick"
    )
    _, trigger = read_bound_json(root, trigger_binding, "selection trigger tick")
    receipt = validate_selection_decision_receipt(
        root, raw, expected_trigger_tick=trigger
    )
    if receipt.get("outcome") != "selected":
        raise ValueError("selection publication intent requires a selected decision")
    return binding, receipt


def compile_intent(
    root: Path, raw: dict[str, Any]
) -> tuple[dict[str, Any], bytes]:
    """Compile one exact intent into canonical v2 prepare material without writing."""

    root = root.expanduser().resolve(strict=True)
    intent = _closed(raw, INTENT_KEYS, "selection publication intent")
    if (
        intent.get("schema_version") != 1
        or intent.get("kind") != "selection_publication_intent"
        or not isinstance(intent.get("owner_receipts"), list)
    ):
        raise ValueError("selection publication intent contract is invalid")

    source_binding = normalize_binding(
        intent.get("source_decision"), "selection publication source decision"
    )
    _, source = read_bound_json(
        root, source_binding, "selection publication source decision"
    )
    task_binding_value = intent.get("task_source")
    owner_values = intent["owner_receipts"]
    publication_mode: str
    owner_assertions: list[dict[str, Any]]

    if source.get("artifact_kind") == "selection_decision_receipt":
        source_binding, selected = _selected_source(root, source_binding)
        if task_binding_value is None or len(owner_values) != 1:
            raise ValueError(
                "selected publication requires one task source and one task-state owner receipt"
            )
        task_binding = normalize_binding(task_binding_value, "selection task source")
        _, task_payload = read_bound_bytes(root, task_binding, "selection task source")
        selection_id = _task_id(task_payload)
        if selection_id != selected.get("selected_task_id"):
            raise ValueError("selected task source differs from the decision task ID")
        assertion, plan = _transition_assertion(root, owner_values[0])
        if not _task_event_matches(plan, selection_id, task_binding["sha256"]):
            raise ValueError(
                "task-state transition does not bind the exact selected task bytes"
            )
        owner_assertions = [assertion]
        source_decision_id = str(selected["receipt_id"])
        publication_mode = "selected_successor"
    elif source.get("receipt_kind") == "task_state_transition_apply_receipt":
        if task_binding_value is not None or owner_values:
            raise ValueError(
                "task-transition reconciliation requires null task_source and no owner_receipts"
            )
        assertion, plan = _transition_assertion(root, source_binding)
        task_path = root / "task.md"
        current_sha = _sha256_file(task_path)
        if current_sha is None:
            raise ValueError("task-transition reconciliation requires current task.md")
        task_payload = task_path.read_bytes()
        selection_id = _task_id(task_payload)
        if not _task_event_matches(plan, selection_id, current_sha):
            raise ValueError(
                "task-transition reconciliation source does not bind current task.md"
            )
        owner_assertions = [assertion]
        source_decision_id = str(source["plan_id"])
        publication_mode = "task_state_reconciliation"
    else:
        raise ValueError("selection publication source decision kind is unsupported")

    if len(task_payload) > MAX_TARGET_BYTES:
        raise ValueError("selection task source exceeds the size limit")
    task_sha = _sha256_bytes(task_payload)
    target = {
        "role": "task_alias",
        "target_ref": "task.md",
        "before_sha256": _sha256_file(root / "task.md"),
        "after_sha256": task_sha,
        "payload_ref": f".task/selection_publication/blobs/sha256/{task_sha}",
        "payload_sha256": task_sha,
        "payload_size": len(task_payload),
    }
    normalized = {
        "schema_version": 2,
        "kind": "selection_publication_prepare",
        "selection_id": selection_id,
        "source_decision_id": source_decision_id,
        "source_decision_sha256": source_binding["sha256"],
        "source_decision": source_binding,
        "publication_mode": publication_mode,
        "owner_assertions": owner_assertions,
        "targets": [target],
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
    _closed(material, PREPARE_KEYS, "selection publication v2 prepare")
    if material.get("schema_version") != 2 or material.get("kind") != (
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
    }:
        raise ValueError("selection publication v2 mode is invalid")
    assertions = material.get("owner_assertions")
    if not isinstance(assertions, list) or len(assertions) != 1:
        raise ValueError("selection publication v2 requires one owner assertion")
    for assertion in assertions:
        _closed(assertion, ASSERTION_KEYS, "selection publication owner assertion")
        normalize_binding(assertion.get("receipt"), "task-state transition receipt")
        normalize_binding(assertion.get("plan"), "task-state transition plan")
    targets = material.get("targets")
    if not isinstance(targets, list) or len(targets) != 1:
        raise ValueError("selection publication v2 requires one task_alias target")
    target = _closed(targets[0], TARGET_KEYS, "selection publication v2 target")
    if target.get("role") != "task_alias" or target.get("target_ref") != "task.md":
        raise ValueError("selection publication v2 target must be task_alias")
    before = target.get("before_sha256")
    if before is not None and (not isinstance(before, str) or not SHA256.fullmatch(before)):
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
        normalized["predecessor_transaction_id"] = raw.get(
            "predecessor_transaction_id"
        )
    if "transaction_id" in raw:
        normalized["transaction_id"] = raw.get("transaction_id")
    return normalized


def persist_blob(root: Path, payload: bytes) -> tuple[Path, str, bool]:
    digest = _sha256_bytes(payload)
    path = _blob_path(root, digest)
    created = not path.exists()
    _write_once(path, payload, "selection publication task blob")
    return path, digest, created


def payload_for_target(root: Path, target: dict[str, Any]) -> bytes:
    binding = {
        "ref": target["payload_ref"],
        "sha256": target["payload_sha256"],
    }
    _, payload = read_bound_bytes(root, binding, "selection publication task blob")
    if len(payload) != target["payload_size"]:
        raise ValueError("selection publication task blob size is inconsistent")
    return payload


__all__ = (
    "compile_intent",
    "normalize_prepare",
    "payload_for_target",
    "persist_blob",
    "validate_owner_assertion",
)
