"""Read-only registry listing and active-advice packet rendering."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

from .packet_contract import enrich_item, packet_identity_fields
from .storage import load_events, merge_state


def active_items(root: Path) -> list[dict[str, Any]]:
    state = merge_state(load_events(root))
    return [item for item in state.values() if item.get("status") == "active"]


def _field_bool(value: object) -> bool:
    return value is True or str(value or "").strip().lower() in {"true", "1", "yes"}


def advice_packet(root: Path) -> dict[str, Any]:
    """Render advice with an explicit non-executable normalization guard."""

    items = [enrich_item(item) for item in active_items(root)]
    incomplete = []
    for item in items:
        fields = item.get("fields") if isinstance(item.get("fields"), dict) else {}
        complete = fields.get("fidelity_status") == "ok" and not _field_bool(
            fields.get("raw_direct_reference_required")
        )
        if not complete:
            incomplete.append(item.get("advice_id"))
    return {
        "used_advice": items,
        "not_goal_truth": True,
        "execution_plan_eligible": False,
        "normalized_packet_use": (
            "warning_only_raw_review" if incomplete else "direction_evidence_only"
        ),
        "incomplete_normalization_advice_ids": incomplete,
        **packet_identity_fields(items),
    }


def cmd_list(args: argparse.Namespace) -> None:
    root = Path(args.root).resolve()
    state = merge_state(load_events(root))
    items = list(state.values())
    if args.status:
        items = [item for item in items if item.get("status") == args.status]
    print(
        json.dumps(
            {"status": "ok", "items": items},
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )


def cmd_render_packet(args: argparse.Namespace) -> None:
    root = Path(args.root).resolve()
    packet = advice_packet(root)
    items = packet["used_advice"]
    if args.format == "json":
        print(json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True))
        return
    lines = [
        "# External Advice Packet",
        "",
        "- not_goal_truth: true",
        "- execution_plan_eligible: false",
        f"- applicability: {packet['applicability']}",
        f"- normalized_packet_use: {packet['normalized_packet_use']}",
        f"- canonical_actionable_clause_ids: {json.dumps(packet['canonical_actionable_clause_ids'], ensure_ascii=False)}",
        f"- source_digests: {json.dumps(packet['source_digests'], ensure_ascii=False, sort_keys=True)}",
        f"- advice_packet_digest: {packet['advice_packet_digest']}",
        "",
    ]
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
                f"- normalization_complete: {(item.get('fields') or {}).get('normalization_complete', 'unknown')}",
                f"- source_digest: {item.get('source_digest')}",
                f"- canonical_clause_ids: {json.dumps(item.get('canonical_clause_ids', []), ensure_ascii=False)}",
                f"- actionable_clause_ids: {json.dumps(item.get('actionable_clause_ids', []), ensure_ascii=False)}",
                "- usage: planning evidence only; do not treat as `.agent_goal` GT.",
                "",
            ]
        )
    sys.stdout.write("\n".join(lines).rstrip() + "\n")


__all__ = ["active_items", "advice_packet", "cmd_list", "cmd_render_packet"]
