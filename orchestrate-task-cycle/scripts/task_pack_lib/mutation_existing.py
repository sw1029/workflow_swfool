"""Orchestration for mutations against an existing task pack."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .coherence import validate_pack_coherence_contract
from .mutation_actions import (
    apply_insert,
    apply_normalization,
    apply_promote,
    apply_reorder,
    apply_skip,
    apply_supersede,
    apply_terminal_block,
)
from .mutation_finalize import finalize_existing_mutation
from .ordering import item_order, refresh_current_item
from .packet_io import load_json
from .storage import rel_path, resolve_pack_path
from .store import active_pack
from .validation import validate_pack


def apply_existing(args: argparse.Namespace, root: Path, plan: dict[str, Any], action: str) -> int:
    pack_path_value = plan.get("pack_path") or args.pack
    path = resolve_pack_path(root, str(pack_path_value)) if pack_path_value else active_pack(root)[0]
    if path is None:
        raise SystemExit("No active task pack found.")
    data = load_json(path)
    before_order = item_order(data)
    if action == "normalize_initial_selection_provenance":
        supplied_receipt = plan.get("initial_selection_receipt")
        if isinstance(supplied_receipt, dict):
            replay_item_id = str(supplied_receipt.get("initial_item_id") or plan.get("item_id") or "").strip()
            replay_target = next(
                (
                    item
                    for item in data.get("items", [])
                    if isinstance(item, dict) and str(item.get("item_id") or "") == replay_item_id
                ),
                None,
            )
            replay_promotion = (
                replay_target.get("promotion")
                if isinstance(replay_target, dict) and isinstance(replay_target.get("promotion"), dict)
                else {}
            )
            replay_normalization = replay_promotion.get("provenance_normalization")
            if isinstance(replay_normalization, dict):
                if replay_promotion.get("initial_selection_receipt") != supplied_receipt:
                    raise SystemExit("Initial-selection provenance is already normalized with a conflicting receipt.")
                replay_findings = validate_pack(data, path)
                blocking = [finding for finding in replay_findings if finding.get("severity") == "block"]
                if blocking:
                    raise SystemExit(
                        "Stored initial-selection normalization no longer validates: "
                        + "; ".join(str(finding.get("code")) for finding in blocking)
                    )
                output = {
                    "status": "already_normalized",
                    "action": action,
                    "pack_path": rel_path(root, path),
                    "pack_id": data.get("pack_id"),
                    "current_item_id": data.get("current_item_id"),
                    "pack_transition_verdict": {"status": "pass", "evidence_ref": rel_path(root, path)},
                    "historical_authority_verdict": replay_normalization.get("historical_authority_verdict"),
                }
                json.dump(output, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
                sys.stdout.write("\n")
                return 0
    coherence_result = validate_pack_coherence_contract(root, plan, require_declared=True)
    if coherence_result["status"] == "block":
        output = {
            "status": "block",
            "action": action,
            "pack_path": rel_path(root, path),
            "pack_transition_verdict": {
                "status": "blocked",
                "evidence_ref": rel_path(root, path),
            },
            "findings": coherence_result["findings"],
        }
        json.dump(output, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
        sys.stdout.write("\n")
        return 2
    coherence = dict(coherence_result["pack_coherence"] or {})
    items = data.get("items")
    if not isinstance(items, list):
        raise SystemExit("Task pack has invalid `items`.")

    if action == "promote":
        apply_promote(root, path, data, items, plan, coherence, before_order)
    elif action == "normalize_initial_selection_provenance":
        result = apply_normalization(root, path, data, items, plan, coherence, before_order)
        if result is not None:
            return result
    elif action == "insert":
        apply_insert(data, items, plan, before_order)
    elif action == "reorder":
        apply_reorder(data, items, plan, before_order)
    elif action == "skip":
        apply_skip(data, items, plan, before_order)
    elif action == "supersede":
        apply_supersede(data, items, plan, before_order)
    elif action == "terminal_block":
        apply_terminal_block(data, items, plan, before_order)

    if action != "normalize_initial_selection_provenance":
        refresh_current_item(data)
    return finalize_existing_mutation(args, root, path, data, plan, action, coherence, before_order)

