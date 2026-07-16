"""Read-only registry listing and active-advice packet rendering."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

from .storage import load_events, merge_state

def active_items(root: Path) -> list[dict[str, Any]]:
    state = merge_state(load_events(root))
    return [item for item in state.values() if item.get("status") == "active"]

def cmd_list(args: argparse.Namespace) -> None:
    root = Path(args.root).resolve()
    state = merge_state(load_events(root))
    items = list(state.values())
    if args.status:
        items = [item for item in items if item.get("status") == args.status]
    print(json.dumps({"status": "ok", "items": items}, ensure_ascii=False, indent=2, sort_keys=True))

def cmd_render_packet(args: argparse.Namespace) -> None:
    root = Path(args.root).resolve()
    items = active_items(root)
    if args.format == "json":
        print(json.dumps({"used_advice": items, "not_goal_truth": True}, ensure_ascii=False, indent=2, sort_keys=True))
        return
    lines = ["# External Advice Packet", "", "- not_goal_truth: true", ""]
    if not items:
        lines.append("- active_advice: none")
    for item in items:
        lines.extend(
            [
                f"## {item.get('advice_id')}",
                "",
                f"- status: {item.get('status')}",
                f"- title: {item.get('title')}",
                f"- path: {item.get('path')}",
                f"- raw_source_path: {item.get('raw_source_path')}",
                f"- priority: {item.get('priority')}",
                f"- fidelity_status: {(item.get('fields') or {}).get('fidelity_status', 'unknown')}",
                f"- raw_direct_reference_required: {(item.get('fields') or {}).get('raw_direct_reference_required', 'unknown')}",
                "- usage: planning evidence only; do not treat as `.agent_goal` GT.",
                "",
            ]
        )
    sys.stdout.write("\n".join(lines).rstrip() + "\n")
