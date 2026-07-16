"""Independent Markdown and current-state projection reconstruction."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .core import (
    INDEX_FORMAT_VERSION,
    INDEX_SCHEMA_VERSION,
    NON_ACTIVE_STATUSES,
    _broken_links,
    _is_sha256,
    _merge_state,
    _require,
    _sha256,
    _workspace_ref,
)


def _render_markdown(events: list[dict[str, Any]], generated_at: str) -> bytes:
    state = _merge_state(events)
    groups: dict[str, list[dict[str, Any]]] = {}
    for item in state.values():
        groups.setdefault(str(item.get("type", "unknown")), []).append(item)
    lines = [
        "# Task State Index", "", f"- Generated: {generated_at}",
        "- Canonical JSONL: `.task/index.jsonl`", f"- Format version: {INDEX_FORMAT_VERSION}",
        f"- Schema version: {INDEX_SCHEMA_VERSION}", f"- Artifact count: {len(state)}", "",
    ]
    for item_type in sorted(groups):
        lines.extend([
            f"## {item_type}", "", "| ID | Status | Title | Path | Parent | Links | Updated |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ])
        for item in sorted(groups[item_type], key=lambda row: (str(row.get("status", "")), str(row.get("id", "")))):
            links = ", ".join(f"{link.get('rel')}:{link.get('id')}" for link in item.get("links", []))
            values = [item.get("id"), item.get("status"), item.get("title"), item.get("path"), item.get("parent_id"), links, item.get("updated_at")]
            escaped = [str(value or "").replace("|", "\\|").replace("\n", " ") for value in values]
            lines.append("| " + " | ".join(escaped) + " |")
        lines.append("")
    return ("\n".join(lines).rstrip() + "\n").encode("utf-8")

def _current_projection(
    state: dict[str, dict[str, Any]], root: Path
) -> tuple[dict[str, Any], dict[str, Any]]:
    tasks = sorted(item_id for item_id, item in state.items() if item.get("type") == "task" and item.get("status") == "active")
    packs = sorted(item_id for item_id, item in state.items() if item.get("type") == "task_pack" and item.get("status") == "active")
    _require(len(tasks) == 1 and len(packs) == 1, "current projection lacks exactly one active task and pack")
    task_id, pack_id = tasks[0], packs[0]
    task, pack = state[task_id], state[pack_id]
    aliases = sorted(
        item_id for item_id, item in state.items()
        if item_id != task_id and item.get("type") == "task" and item.get("path") == task.get("path")
        and item.get("status") not in NON_ACTIVE_STATUSES
    )
    broken = _broken_links(state, task_id)
    _require(not aliases and not broken, "current projection has duplicate aliases or broken task links")
    identities: dict[str, Any] = {}
    for label, item_id, item, expected_type in (
        ("task", task_id, task, "task"), ("pack", pack_id, pack, "task_pack")
    ):
        path_value = item.get("path")
        digest = item.get("content_sha256")
        _require(isinstance(path_value, str) and path_value, f"current {label} path is missing")
        candidate = Path(path_value)
        _require(not candidate.is_absolute() and all(part not in {"", ".", ".."} for part in candidate.parts), f"current {label} path is unsafe")
        path = _workspace_ref(root, path_value, f"current {label} artifact")
        _require(_is_sha256(digest), f"current {label} content hash is missing")
        _require(_sha256(path.read_bytes()) == digest, f"current {label} content hash mismatch")
        if label == "pack":
            try:
                pack_document = json.loads(path.read_text(encoding="utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ValueError("current pack is not valid JSON") from exc
            _require(isinstance(pack_document, dict) and pack_document.get("pack_id") == item_id, "current pack embedded identity mismatch")
        identities[label] = {
            "id": item_id,
            "type": expected_type,
            "path_sha256": _sha256(path_value.encode("utf-8")),
            "content_sha256": digest,
        }
    projection = {
        "active_task_count": 1,
        "active_pack_count": 1,
        "duplicate_active_alias_count": 0,
        "current_broken_link_count": 0,
        "projection_completeness": "complete",
    }
    return projection, identities
