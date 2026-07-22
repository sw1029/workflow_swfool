"""Closed compilation validation and read-only scan-apply preflight."""
from __future__ import annotations

import datetime as dt
from pathlib import Path, PurePosixPath
from typing import Any

from .transition_intent import assert_no_pending_transition_intents
from .transition_plan_contract import (
    canonical_bytes,
    load_transition_plan,
    regular_payload,
    sha256_bytes,
    workspace_path,
)
from .transition_recovery import committed_boundary_valid, matching_events
from .transition_verification import cas_status
from .storage import markdown_path, sha256_file
from .scan_projection_repair import expected_projection_sha256


_HEX = frozenset("0123456789abcdef")
_INVENTORY_FIELDS = frozenset({"artifact_count", "items", "sha256"})
_INVENTORY_ITEM_FIELDS = frozenset(
    {"type", "ref", "status", "title", "sha256"}
)
_REQUEST_FIELDS = frozenset({"schema_version", "updated_at", "render", "events"})
_SNAPSHOT_FIELDS = frozenset(
    {"source_ref", "source_sha256", "target_ref"}
)


def _is_digest(value: Any, *, optional: bool = False) -> bool:
    return (optional and value is None) or (
        isinstance(value, str)
        and len(value) == 64
        and all(character in _HEX for character in value)
    )


def _require_count(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"Scan compilation {label} is invalid")
    return value


def _validate_timestamp(value: Any) -> None:
    if not isinstance(value, str):
        raise ValueError("Scan compilation created_at is invalid")
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("Scan compilation created_at is invalid") from exc
    if parsed.tzinfo is None:
        raise ValueError("Scan compilation created_at is invalid")


def _validate_revision(value: Any, expected_ref: str) -> None:
    if (
        not isinstance(value, dict)
        or set(value) != {"ref", "sha256"}
        or value.get("ref") != expected_ref
        or not _is_digest(value.get("sha256"), optional=True)
    ):
        raise ValueError("Scan compilation revision binding is invalid")


def _validate_binding(value: Any, label: str) -> dict[str, str]:
    if (
        not isinstance(value, dict)
        or set(value) != {"ref", "sha256"}
        or not isinstance(value.get("ref"), str)
        or not value["ref"]
        or not _is_digest(value.get("sha256"))
    ):
        raise ValueError(f"Scan compilation {label} binding is invalid")
    return {"ref": value["ref"], "sha256": value["sha256"]}


def _validate_inventory(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, dict) or set(value) != _INVENTORY_FIELDS:
        raise ValueError("Scan compilation inventory fields are not closed")
    items = value.get("items")
    if not isinstance(items, list):
        raise ValueError("Scan compilation inventory items are invalid")
    for item in items:
        if (
            not isinstance(item, dict)
            or set(item) != _INVENTORY_ITEM_FIELDS
            or not all(
                isinstance(item.get(field), str)
                for field in ("type", "ref", "status", "title")
            )
            or not _is_digest(item.get("sha256"))
        ):
            raise ValueError("Scan compilation inventory item is invalid")
    if _require_count(value.get("artifact_count"), "artifact_count") != len(items):
        raise ValueError("Scan compilation inventory count is invalid")
    if value.get("sha256") != sha256_bytes(canonical_bytes(items)):
        raise ValueError("Scan compilation inventory digest is invalid")
    return items


def _validate_request(compilation: dict[str, Any]) -> list[dict[str, Any]]:
    mode = compilation.get("effect_mode")
    if mode not in {"event_batch", "projection_repair", "no_effect"}:
        raise ValueError("Scan compilation effect mode is invalid")
    request = compilation.get("request")
    event_count = _require_count(compilation.get("event_count"), "event_count")
    logical_count = _require_count(
        compilation.get("logical_update_count"), "logical_update_count"
    )
    if compilation.get("request_sha256") != sha256_bytes(canonical_bytes(request)):
        raise ValueError("Scan compilation request digest is invalid")
    if mode != "event_batch":
        if request is not None or compilation.get("plan_binding") is not None:
            raise ValueError("Scan compilation non-event bindings are invalid")
        if event_count != 0 or logical_count != 0:
            raise ValueError("Scan compilation non-event counts are invalid")
        return []
    if (
        not isinstance(request, dict)
        or set(request) != _REQUEST_FIELDS
        or request.get("schema_version") != 1
        or request.get("updated_at") != compilation.get("created_at")
        or request.get("render") is not True
        or not isinstance(request.get("events"), list)
        or not request["events"]
        or not all(isinstance(event, dict) for event in request["events"])
    ):
        raise ValueError("Scan compilation event request is invalid")
    if event_count != len(request["events"]):
        raise ValueError("Scan compilation event count is invalid")
    derived_logical_count = sum(
        event.get("event") == "upsert"
        and isinstance(event.get("type"), str)
        and isinstance(event.get("path"), str)
        for event in request["events"]
    )
    if logical_count != derived_logical_count or logical_count < 1:
        raise ValueError("Scan compilation logical update count is invalid")
    _validate_binding(compilation.get("plan_binding"), "plan")
    return request["events"]


def _expected_snapshots(events: list[dict[str, Any]]) -> list[dict[str, str]]:
    expected: list[dict[str, str]] = []
    for event in events:
        fields = event.get("fields")
        if (
            event.get("type") != "task"
            or event.get("path") != "task.md"
            or not isinstance(fields, dict)
            or fields.get("record_class") != "mutable_alias"
        ):
            continue
        digest = event.get("content_sha256")
        target = fields.get("snapshot_path")
        if (
            not _is_digest(digest)
            or fields.get("snapshot_digest") != digest
            or fields.get("alias_path") != "task.md"
            or not isinstance(target, str)
        ):
            raise ValueError("Scan compilation task snapshot event is invalid")
        expected.append({
            "source_ref": "task.md",
            "source_sha256": digest,
            "target_ref": target,
        })
    return expected


def _validate_snapshots(value: Any, events: list[dict[str, Any]]) -> None:
    if not isinstance(value, list):
        raise ValueError("Scan compilation snapshot materializations are invalid")
    for row in value:
        target = row.get("target_ref") if isinstance(row, dict) else None
        parts = PurePosixPath(target).parts if isinstance(target, str) else ()
        if (
            not isinstance(row, dict)
            or set(row) != _SNAPSHOT_FIELDS
            or row.get("source_ref") != "task.md"
            or not _is_digest(row.get("source_sha256"))
            or len(parts) != 3
            or parts[:2] != (".task", "snapshots")
        ):
            raise ValueError("Scan compilation snapshot materialization is invalid")
    if value != _expected_snapshots(events):
        raise ValueError("Scan compilation snapshot bindings do not match events")


def _validate_focus(value: Any, items: list[dict[str, str]]) -> None:
    if not isinstance(value, list) or len(value) > 1:
        raise ValueError("Scan compilation focus results are invalid")
    if not value:
        return
    row = value[0]
    if not isinstance(row, dict) or not _is_digest(row.get("sha256")):
        raise ValueError("Scan compilation focus result is invalid")
    matches = [item for item in items if item["ref"] == row.get("ref")]
    if not matches:
        expected = {
            "ref": row.get("ref"), "sha256": row.get("sha256"),
            "status": "not_discovered", "artifact_type": None,
        }
    elif len(matches) == 1 and matches[0]["sha256"] == row.get("sha256"):
        item = matches[0]
        expected = {
            "ref": item["ref"], "sha256": item["sha256"],
            "status": item["status"], "artifact_type": item["type"],
            "title": item["title"],
        }
    else:
        raise ValueError("Scan compilation focus result is ambiguous")
    if row != expected:
        raise ValueError("Scan compilation focus result does not match inventory")


def validate_scan_compilation(compilation: dict[str, Any]) -> None:
    """Validate deterministic identity and all derived compilation surfaces."""

    _validate_timestamp(compilation.get("created_at"))
    _validate_revision(compilation.get("index_revision"), ".task/index.jsonl")
    _validate_revision(compilation.get("projection_revision"), ".task/index.md")
    items = _validate_inventory(compilation.get("inventory"))
    events = _validate_request(compilation)
    _validate_snapshots(compilation.get("snapshot_materializations"), events)
    _validate_focus(compilation.get("focus_results"), items)
    identity = {
        "created_at": compilation["created_at"],
        "effect_mode": compilation["effect_mode"],
        "inventory_sha256": compilation["inventory"]["sha256"],
        "index_sha256": compilation["index_revision"]["sha256"],
        "projection_sha256": compilation["projection_revision"]["sha256"],
        "request_sha256": compilation["request_sha256"],
    }
    expected_id = "scan-" + sha256_bytes(canonical_bytes(identity))[:32]
    if compilation.get("compilation_id") != expected_id:
        raise ValueError("Scan compilation deterministic identity is invalid")


def preflight_scan_apply(
    root: Path,
    compilation: dict[str, Any],
    existing: list[dict[str, Any]],
    current_index: str | None,
    *,
    projection_repair_started: bool = False,
) -> tuple[dict[str, Any] | None, bool]:
    """Classify exact recovery or untouched prestate before snapshot writes."""

    if compilation["effect_mode"] != "event_batch":
        expected_index = compilation["index_revision"]["sha256"]
        recovered_empty_index = bool(
            compilation["effect_mode"] == "projection_repair"
            and projection_repair_started
            and expected_index is None
            and current_index == sha256_bytes(b"")
            and not existing
        )
        if current_index != expected_index and not recovered_empty_index:
            raise ValueError("Scan compilation prestate changed; recompile_required")
        current_projection = sha256_file(markdown_path(root))
        before_projection = compilation["projection_revision"]["sha256"]
        if current_projection == before_projection:
            return None, False
        expected_after = expected_projection_sha256(
            existing, compilation["created_at"]
        )
        if (
            compilation["effect_mode"] == "projection_repair"
            and projection_repair_started
            and current_projection == expected_after
        ):
            return None, True
        if current_projection != before_projection:
            raise ValueError(
                "Scan compilation projection prestate changed; recompile_required"
            )
        return None, False
    binding = _validate_binding(compilation["plan_binding"], "plan")
    _path, plan, plan_file_sha256 = load_transition_plan(root, binding["ref"])
    if plan_file_sha256 != binding["sha256"]:
        raise ValueError("Scan compilation plan differs from its binding")
    expected_ledger = compilation["index_revision"]["sha256"] or sha256_bytes(b"")
    expected_projection = compilation["projection_revision"]["sha256"]
    actual_projection = plan.get("markdown", {}).get("before_sha256")
    projection_matches = actual_projection == expected_projection or (
        actual_projection is None and expected_projection == sha256_bytes(b"")
    )
    if (
        plan.get("request") != compilation["request"]
        or plan.get("request_sha256") != compilation["request_sha256"]
        or plan.get("created_at") != compilation["created_at"]
        or plan.get("ledger", {}).get("before_sha256") != expected_ledger
        or plan.get("ledger", {}).get("event_count") != compilation["event_count"]
        or not projection_matches
    ):
        raise ValueError("Scan compilation plan does not match its derived request")
    exact, conflict = matching_events(existing, plan)
    if conflict:
        raise ValueError("Task-state transition plan is partially or conflictingly applied")
    if exact:
        if not committed_boundary_valid(root, plan, existing):
            raise ValueError("Task-state transition committed boundary is invalid")
    else:
        current, defects = cas_status(root, plan, phase="apply")
        if not current:
            raise ValueError(
                "Task-state transition plan CAS mismatch: " + ", ".join(defects)
            )
    assert_no_pending_transition_intents(
        root, allowed_plan_id=str(plan["plan_id"])
    )
    return plan, exact


def validate_committed_snapshots(
    root: Path, rows: list[dict[str, str]]
) -> None:
    """Validate historical snapshot targets without reopening mutable sources."""

    for row in rows:
        target = workspace_path(root, row["target_ref"])
        payload = regular_payload(target)
        if sha256_bytes(payload) != row["source_sha256"]:
            raise ValueError("Committed scan snapshot differs from its exact binding")


__all__ = (
    "preflight_scan_apply", "validate_committed_snapshots",
    "validate_scan_compilation",
)
