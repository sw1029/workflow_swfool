"""Markdown rendering and bounded render publication."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .ordering import sorted_items
from .packet_io import scope_fidelity_records, truthy, write_bytes_atomic
from .storage import _require_within, pack_dir, rel_path

def render_markdown(root: Path, path: Path, data: dict[str, Any], language: str) -> str:
    ko = language.lower().startswith("ko")
    title = "Task Pack" if not ko else "Task Pack"
    labels = {
        "status": "Status" if not ko else "상태",
        "goal": "Goal" if not ko else "목표",
        "current": "Current Item" if not ko else "현재 item",
        "terminal": "Terminal Blocker" if not ko else "terminal blocker",
        "items": "Items" if not ko else "Items",
        "mutations": "Mutation Log" if not ko else "Mutation Log",
    }
    lines = [
        f"# {title}: {data.get('pack_id', path.stem)}",
        "",
        f"- {labels['status']}: {data.get('status')}",
        f"- {labels['goal']}: {data.get('goal')}",
        f"- {labels['current']}: {data.get('current_item_id') or 'none'}",
        f"- JSON: `{rel_path(root, path)}`",
        "",
        f"## {labels['items']}",
        "",
    ]
    for item in sorted_items(data):
        scope_records, _ = scope_fidelity_records(item)
        scope_summary = "none"
        if scope_records:
            parts = []
            for record in scope_records:
                directive_id = str(record.get("directive_id") or "unknown")
                narrowed = "narrowed" if truthy(record.get("narrowed")) else "full"
                residual = str(record.get("residual_item_id") or "none")
                parts.append(f"{directive_id}:{narrowed}:residual={residual}")
            scope_summary = "; ".join(parts)
        lines.extend(
            [
                f"### {item.get('order')}. {item.get('title')}",
                "",
                f"- item_id: `{item.get('item_id')}`",
                f"- status: `{item.get('status')}`",
                f"- progress_target: `{item.get('progress_target')}`",
                f"- progress_kind_expected: `{item.get('progress_kind_expected') or 'none'}`",
                f"- item_kind: `{item.get('item_kind') or 'none'}`",
                f"- validation_profile: `{item.get('validation_profile')}`",
                f"- semantic_signature_expected: `{item.get('semantic_signature_expected') or 'none'}`",
                f"- positive_input_delta_required: `{item.get('positive_input_delta_required', False)}`",
                f"- required_new_input_kinds: {', '.join(str(value) for value in item.get('required_new_input_kinds', [])) or 'none'}",
                f"- scope_fidelity: {scope_summary}",
                "",
                str(item.get("objective") or "").strip(),
                "",
            ]
        )
    if data.get("terminal_blocker"):
        lines.extend([f"## {labels['terminal']}", "", "```json", json.dumps(data["terminal_blocker"], ensure_ascii=False, indent=2, sort_keys=True), "```", ""])
    if data.get("mutation_log"):
        lines.extend([f"## {labels['mutations']}", ""])
        for mutation in data.get("mutation_log", []):
            if isinstance(mutation, dict):
                lines.append(f"- {mutation.get('timestamp')}: {mutation.get('action')} - {mutation.get('reason')}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_path(path: Path) -> Path:
    return path.with_suffix(".md")


def bounded_render_path(root: Path, path: Path) -> Path:
    return _require_within(render_path(path), pack_dir(root), "Task pack Markdown render path")


def write_render(root: Path, path: Path, data: dict[str, Any], language: str) -> Path:
    output = bounded_render_path(root, path)
    write_bytes_atomic(output, render_markdown(root, path, data, language).encode("utf-8"))
    return output

