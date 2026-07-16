"""Deterministic Markdown projection for task-state events."""
from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any, Callable

from .contracts import INDEX_FORMAT_VERSION, INDEX_SCHEMA_VERSION
from .events import _load_events_unlocked, merge_state
from .storage import atomic_write_bytes, index_lock, markdown_path, now_iso, rel_path

def escape_md(value: Any) -> str:
    text = "" if value is None else str(value)
    return text.replace("|", "\\|").replace("\n", " ")


def _generated_at_from_markdown(payload: bytes) -> str | None:
    try:
        lines = payload.decode("utf-8").splitlines()
    except UnicodeDecodeError:
        return None
    prefix = "- Generated: "
    matches = [line[len(prefix) :].strip() for line in lines if line.startswith(prefix)]
    if len(matches) != 1 or not matches[0]:
        return None
    try:
        parsed = dt.datetime.fromisoformat(matches[0].replace("Z", "+00:00"))
    except ValueError:
        return None
    return matches[0] if parsed.tzinfo is not None else None


def _render_markdown_payload(state: dict[str, dict[str, Any]], generated_at: str) -> bytes:
    groups: dict[str, list[dict[str, Any]]] = {}
    for item in state.values():
        groups.setdefault(str(item.get("type", "unknown")), []).append(item)

    lines = [
        "# Task State Index",
        "",
        f"- Generated: {generated_at}",
        "- Canonical JSONL: `.task/index.jsonl`",
        f"- Format version: {INDEX_FORMAT_VERSION}",
        f"- Schema version: {INDEX_SCHEMA_VERSION}",
        f"- Artifact count: {len(state)}",
        "",
    ]

    for item_type in sorted(groups):
        items = sorted(groups[item_type], key=lambda item: (str(item.get("status", "")), str(item.get("id", ""))))
        lines.extend(
            [
                f"## {item_type}",
                "",
                "| ID | Status | Title | Path | Parent | Links | Updated |",
                "| --- | --- | --- | --- | --- | --- | --- |",
            ]
        )
        for item in items:
            links = ", ".join(f"{link.get('rel')}:{link.get('id')}" for link in item.get("links", []))
            lines.append(
                "| "
                + " | ".join(
                    [
                        escape_md(item.get("id")),
                        escape_md(item.get("status")),
                        escape_md(item.get("title")),
                        escape_md(item.get("path")),
                        escape_md(item.get("parent_id")),
                        escape_md(links),
                        escape_md(item.get("updated_at")),
                    ]
                )
                + " |"
            )
        lines.append("")

    return ("\n".join(lines).rstrip() + "\n").encode("utf-8")


def _markdown_projection_matches(root: Path, state: dict[str, dict[str, Any]]) -> bool:
    path = markdown_path(root)
    if not path.is_file():
        return False
    existing = path.read_bytes()
    generated_at = _generated_at_from_markdown(existing)
    return bool(generated_at and existing == _render_markdown_payload(state, generated_at))


def _rebuild_markdown_unlocked(
    root: Path,
    events: list[dict[str, Any]] | None = None,
    *,
    now_fn: Callable[[], str] = now_iso,
) -> dict[str, Any]:
    state = merge_state(events if events is not None else _load_events_unlocked(root))
    path = markdown_path(root)
    existing = path.read_bytes() if path.is_file() else b""
    generated_at = _generated_at_from_markdown(existing) or now_fn()
    payload = _render_markdown_payload(state, generated_at)
    changed = payload != existing
    if changed:
        generated_at = now_fn()
        payload = _render_markdown_payload(state, generated_at)
        atomic_write_bytes(path, payload)
    return {
        "index_md": rel_path(root, path),
        "index_md_changed": changed,
        "generated_at": generated_at,
        "artifact_count": len(state),
        "format_version": INDEX_FORMAT_VERSION,
        "schema_version": INDEX_SCHEMA_VERSION,
    }


def rebuild_markdown(root: Path, *, now_fn: Callable[[], str] = now_iso) -> dict[str, Any]:
    with index_lock(root):
        return _rebuild_markdown_unlocked(root, now_fn=now_fn)
