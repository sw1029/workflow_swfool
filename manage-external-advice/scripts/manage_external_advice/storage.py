"""Filesystem layout and append-only registry state projection."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .common import now_iso, rel_path, slugify, stamp
from .contracts import ADVICE_DIR

def advice_root(root: Path) -> Path:
    return root / ADVICE_DIR

def index_jsonl(root: Path) -> Path:
    return advice_root(root) / "index.jsonl"

def index_md(root: Path) -> Path:
    return advice_root(root) / "index.md"

def ensure_dirs(root: Path) -> None:
    base = advice_root(root)
    for name in ("raw", "active", "deferred", "applied", "rejected"):
        (base / name).mkdir(parents=True, exist_ok=True)
    if not index_jsonl(root).exists():
        index_jsonl(root).touch()

def unique_advice_key(root: Path, title: str) -> tuple[str, str]:
    existing = merge_state(load_events(root))
    base = f"{stamp()}-{slugify(title)}"
    candidate = base
    suffix = 2
    while (
        f"adv-{candidate}" in existing
        or (advice_root(root) / "raw" / f"{candidate}.md").exists()
        or (advice_root(root) / "active" / f"{candidate}.md").exists()
    ):
        candidate = f"{base}-{suffix}"
        suffix += 1
    return f"adv-{candidate}", f"{candidate}.md"

def load_events(root: Path) -> list[dict[str, Any]]:
    ensure_dirs(root)
    events: list[dict[str, Any]] = []
    with index_jsonl(root).open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise SystemExit(f"Invalid JSON in {index_jsonl(root)} line {line_no}: {exc}") from exc
            if isinstance(value, dict):
                events.append(value)
    return events

def append_event(root: Path, event: dict[str, Any]) -> None:
    ensure_dirs(root)
    with index_jsonl(root).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")

def merge_state(events: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    state: dict[str, dict[str, Any]] = {}
    for event in events:
        advice_id = event.get("advice_id")
        if not advice_id:
            continue
        current = state.setdefault(str(advice_id), {"advice_id": advice_id, "links": [], "fields": {}})
        current.update({key: value for key, value in event.items() if key not in {"links", "fields"}})
        if isinstance(event.get("fields"), dict):
            current.setdefault("fields", {}).update(event["fields"])
        if isinstance(event.get("links"), list):
            seen = {(link.get("rel"), link.get("id")) for link in current.setdefault("links", [])}
            for link in event["links"]:
                if not isinstance(link, dict):
                    continue
                pair = (link.get("rel"), link.get("id"))
                if pair[0] and pair[1] and pair not in seen:
                    current["links"].append({"rel": pair[0], "id": pair[1]})
                    seen.add(pair)
    return state

def rebuild_index(root: Path) -> dict[str, Any]:
    state = merge_state(load_events(root))
    lines = [
        "# External Advice Index",
        "",
        f"- Generated: {now_iso()}",
        "- Canonical JSONL: `.agent_advice/index.jsonl`",
        f"- Advice count: {len(state)}",
        "",
        "| Advice ID | Status | Title | Normalized Path | Raw Source | Updated |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for item in sorted(state.values(), key=lambda row: (str(row.get("status", "")), str(row.get("advice_id", "")))):
        values = [
            item.get("advice_id", ""),
            item.get("status", ""),
            item.get("title", ""),
            item.get("path", ""),
            item.get("raw_source_path", ""),
            item.get("updated_at", ""),
        ]
        lines.append("| " + " | ".join(str(value).replace("|", "\\|") for value in values) + " |")
    index_md(root).write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return {"index_md": rel_path(root, index_md(root)), "advice_count": len(state)}
