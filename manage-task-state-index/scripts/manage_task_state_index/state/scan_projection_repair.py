"""Crash-safe evidence for deterministic task-index Markdown repair."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .events import _load_events_unlocked, merge_state
from .render import _rebuild_markdown_unlocked, _render_markdown_payload
from .storage import index_lock, jsonl_path, markdown_path, rel_path, sha256_file
from .transition_plan_contract import (
    canonical_bytes,
    owned_transition_file,
    publish_immutable,
    regular_payload,
    sha256_bytes,
)


INTENT_FIELDS = frozenset(
    """schema_version artifact_kind compilation compilation_id index_revision
projection_before_sha256 projection_after_sha256 planned_at intent_sha256""".split()
)
RECEIPT_FIELDS = frozenset(
    """schema_version artifact_kind compilation intent compilation_id
index_revision projection_before_sha256 projection_after_sha256 repaired_at
receipt_sha256""".split()
)


def expected_projection_payload(
    events: list[dict[str, Any]], generated_at: str
) -> bytes:
    """Render the historical projection from its exact ledger-prefix state."""

    return _render_markdown_payload(merge_state(events), generated_at)


def expected_projection_sha256(
    events: list[dict[str, Any]], generated_at: str
) -> str:
    return sha256_bytes(expected_projection_payload(events, generated_at))


def _seal(body: dict[str, Any], field: str) -> dict[str, Any]:
    return {**body, field: sha256_bytes(canonical_bytes(body))}


def _binding(root: Path, path: Path) -> dict[str, str]:
    return {"ref": rel_path(root, path), "sha256": str(sha256_file(path))}


def _expected_intent(
    compilation_binding: dict[str, str],
    compilation: dict[str, Any],
    prefix_events: list[dict[str, Any]],
) -> dict[str, Any]:
    body = {
        "schema_version": 1,
        "artifact_kind": "task_state_projection_repair_intent",
        "compilation": compilation_binding,
        "compilation_id": compilation["compilation_id"],
        "index_revision": compilation["index_revision"],
        "projection_before_sha256": compilation["projection_revision"]["sha256"],
        "projection_after_sha256": expected_projection_sha256(
            prefix_events, compilation["created_at"]
        ),
        "planned_at": compilation["created_at"],
    }
    return _seal(body, "intent_sha256")


def _load_exact(path: Path, expected: dict[str, Any], fields: frozenset[str], label: str) -> None:
    payload = regular_payload(path)
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is not canonical JSON") from exc
    if (
        not isinstance(value, dict)
        or set(value) != fields
        or value != expected
        or payload != canonical_bytes(value) + b"\n"
    ):
        raise ValueError(f"{label} integrity check failed")


def projection_repair_intent(
    root: Path,
    compilation_binding: dict[str, str],
    compilation: dict[str, Any],
    prefix_events: list[dict[str, Any]],
    *,
    publish: bool,
) -> tuple[dict[str, str], bool]:
    """Load or publish the exact pre-effect projection-repair intent."""

    expected = _expected_intent(
        compilation_binding, compilation, prefix_events
    )
    path = owned_transition_file(
        root,
        "scan_projection_intents",
        f"{compilation['compilation_id']}.json",
        create_parent=publish,
    )
    payload = canonical_bytes(expected) + b"\n"
    if not path.exists() and not path.is_symlink():
        if not publish:
            return {
                "ref": rel_path(root, path), "sha256": sha256_bytes(payload)
            }, False
        created = publish_immutable(path, payload)
    else:
        _load_exact(path, expected, INTENT_FIELDS, "Projection-repair intent")
        created = False
    return _binding(root, path), created


def inspect_projection_repair(
    root: Path,
    compilation_binding: dict[str, str],
    compilation: dict[str, Any],
    prefix_events: list[dict[str, Any]],
) -> tuple[dict[str, str], bool]:
    """Return the exact intent binding and whether pre-effect intent exists."""

    binding, _ = projection_repair_intent(
        root, compilation_binding, compilation, prefix_events, publish=False
    )
    return binding, (root / binding["ref"]).exists()


def publish_projection_repair_receipt(
    root: Path,
    compilation_binding: dict[str, str],
    compilation: dict[str, Any],
    prefix_events: list[dict[str, Any]],
    intent_binding: dict[str, str],
) -> tuple[dict[str, str], bool]:
    expected_intent, _ = projection_repair_intent(
        root, compilation_binding, compilation, prefix_events, publish=False
    )
    if intent_binding != expected_intent:
        raise ValueError("Projection-repair receipt binds another intent")
    intent_path = root / intent_binding["ref"]
    if sha256_file(intent_path) != intent_binding["sha256"]:
        raise ValueError("Projection-repair intent binding has drifted")
    after_sha256 = expected_projection_sha256(
        prefix_events, compilation["created_at"]
    )
    body = {
        "schema_version": 1,
        "artifact_kind": "task_state_projection_repair_receipt",
        "compilation": compilation_binding,
        "intent": intent_binding,
        "compilation_id": compilation["compilation_id"],
        "index_revision": compilation["index_revision"],
        "projection_before_sha256": compilation["projection_revision"]["sha256"],
        "projection_after_sha256": after_sha256,
        "repaired_at": compilation["created_at"],
    }
    receipt = _seal(body, "receipt_sha256")
    path = owned_transition_file(
        root,
        "scan_projection_receipts",
        f"{compilation['compilation_id']}.json",
        create_parent=True,
    )
    payload = canonical_bytes(receipt) + b"\n"
    created = publish_immutable(path, payload)
    if not created:
        _load_exact(path, receipt, RECEIPT_FIELDS, "Projection-repair receipt")
    return _binding(root, path), created


def apply_or_recover_projection_repair(
    root: Path,
    compilation_binding: dict[str, str],
    compilation: dict[str, Any],
    prefix_events: list[dict[str, Any]],
    intent_binding: dict[str, str],
    *,
    already_applied: bool,
) -> dict[str, str]:
    """Publish intent before effect, or finish an exact interrupted repair."""

    if not already_applied:
        intent_binding, _ = projection_repair_intent(
            root,
            compilation_binding,
            compilation,
            prefix_events,
            publish=True,
        )
    with index_lock(root):
        current_events = _load_events_unlocked(root)
        if current_events != prefix_events:
            raise ValueError("Projection repair ledger changed before exact commit")
        if not already_applied:
            _rebuild_markdown_unlocked(
                root,
                current_events,
                now_fn=lambda: compilation["created_at"],
            )
        expected_after = expected_projection_sha256(
            prefix_events, compilation["created_at"]
        )
        expected_index = compilation["index_revision"]["sha256"]
        current_index = sha256_file(jsonl_path(root))
        empty_recovery = expected_index is None and current_index == sha256_bytes(b"")
        if (
            current_index != expected_index
            and not empty_recovery
        ):
            raise ValueError("Projection repair ledger boundary has drifted")
        if sha256_file(markdown_path(root)) != expected_after:
            raise ValueError("Projection repair did not reach its exact derived bytes")
        receipt, _ = publish_projection_repair_receipt(
            root,
            compilation_binding,
            compilation,
            prefix_events,
            intent_binding,
        )
    return receipt


def validate_projection_repair_receipt(
    root: Path,
    receipt_binding: dict[str, str],
    compilation_binding: dict[str, str],
    compilation: dict[str, Any],
    prefix_events: list[dict[str, Any]],
) -> dict[str, Any]:
    """Reopen both helper-owned artifacts and independently derive after SHA."""

    expected_intent, _ = projection_repair_intent(
        root, compilation_binding, compilation, prefix_events, publish=False
    )
    intent_path = root / expected_intent["ref"]
    if sha256_file(intent_path) != expected_intent["sha256"]:
        raise ValueError("Projection-repair intent is missing or has drifted")
    _load_exact(
        intent_path,
        _expected_intent(compilation_binding, compilation, prefix_events),
        INTENT_FIELDS,
        "Projection-repair intent",
    )
    after_sha256 = expected_projection_sha256(
        prefix_events, compilation["created_at"]
    )
    body = {
        "schema_version": 1,
        "artifact_kind": "task_state_projection_repair_receipt",
        "compilation": compilation_binding,
        "intent": expected_intent,
        "compilation_id": compilation["compilation_id"],
        "index_revision": compilation["index_revision"],
        "projection_before_sha256": compilation["projection_revision"]["sha256"],
        "projection_after_sha256": after_sha256,
        "repaired_at": compilation["created_at"],
    }
    receipt = _seal(body, "receipt_sha256")
    expected_path = owned_transition_file(
        root,
        "scan_projection_receipts",
        f"{compilation['compilation_id']}.json",
        create_parent=False,
    )
    expected_binding = {
        "ref": rel_path(root, expected_path),
        "sha256": sha256_bytes(canonical_bytes(receipt) + b"\n"),
    }
    if receipt_binding != expected_binding:
        raise ValueError("Projection-repair receipt binding is not canonical")
    _load_exact(
        expected_path, receipt, RECEIPT_FIELDS, "Projection-repair receipt"
    )
    return receipt


__all__ = (
    "expected_projection_payload",
    "expected_projection_sha256",
    "inspect_projection_repair",
    "apply_or_recover_projection_repair",
    "projection_repair_intent",
    "publish_projection_repair_receipt",
    "validate_projection_repair_receipt",
)
