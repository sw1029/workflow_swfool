"""Preflight and immutable draft construction for replacement mutations."""

from __future__ import annotations

import copy
import json
import sys

from .coherence import _coherence_value, validate_pack_coherence_contract
from .contracts import PACK_ID_PATTERN
from .creation import (
    apply_initial_selection_to_new_pack,
    validate_carry_forward_contract,
)
from .ordering import item_order
from .packet_io import load_json, non_empty
from .provenance import mutation_entry
from .receipts import persist_creation_snapshot
from .rendering import bounded_render_path
from .storage import parse_rfc3339, rel_path, resolve_pack_path
from .store import active_pack_candidates, task_pack_store_findings
from .validation import publication_findings


def _prepare_successor_body(args, root, plan, predecessor_path):
    successor = copy.deepcopy(
        plan.get("pack") if isinstance(plan.get("pack"), dict) else {}
    )
    required_successor_fields = {
        "schema_version",
        "pack_id",
        "status",
        "language",
        "goal",
        "current_item_id",
        "created_at",
        "updated_at",
        "items",
        "mutation_log",
        "replacement_contract",
    }
    missing_successor_fields = sorted(required_successor_fields - set(successor))
    if missing_successor_fields:
        raise SystemExit(
            "replace_pack successor requires an exact deterministic body; missing: "
            + ", ".join(missing_successor_fields)
        )
    successor_id = str(successor.get("pack_id") or "").strip()
    if not PACK_ID_PATTERN.fullmatch(successor_id):
        raise SystemExit("replace_pack successor requires a path-safe pack_id token.")
    successor_path = resolve_pack_path(
        root, f".task/task_pack/{successor_id}.json", must_exist=False
    )
    if successor_path.exists() or successor_path == predecessor_path:
        raise SystemExit(
            "replace_pack successor path must be absent and distinct from the predecessor."
        )
    predecessor_render_path = bounded_render_path(root, predecessor_path)
    successor_render_path = bounded_render_path(root, successor_path)
    if args.render and successor_render_path.exists():
        raise SystemExit(
            "replace_pack successor Markdown render path must be absent before publication."
        )
    successor.setdefault("schema_version", 1)
    successor.setdefault("status", "active")
    successor.setdefault("language", args.language)
    if not non_empty(successor.get("created_at")) or not non_empty(
        successor.get("updated_at")
    ):
        raise SystemExit(
            "replace_pack successor requires explicit deterministic created_at and updated_at values."
        )
    parse_rfc3339(successor.get("created_at"), "replace_pack successor created_at")
    parse_rfc3339(successor.get("updated_at"), "replace_pack successor updated_at")
    successor.setdefault("mutation_log", [])
    successor.setdefault("terminal_blocker", None)
    if successor.get("status") != "active":
        raise SystemExit("replace_pack successor must be active.")
    if (
        not successor.get("current_item_id")
        and isinstance(successor.get("items"), list)
        and successor["items"]
    ):
        successor["current_item_id"] = sorted(
            successor["items"], key=lambda item: item.get("order", 0)
        )[0].get("item_id")
    return (successor, successor_path, predecessor_render_path, successor_render_path)


def _prepare_replacement_draft(args, root, plan):
    store_findings = task_pack_store_findings(root)
    if store_findings:
        raise SystemExit(store_findings[0]["message"])
    active = active_pack_candidates(root)
    if len(active) != 1:
        raise SystemExit("replace_pack requires exactly one active predecessor pack.")
    predecessor_path_value = plan.get("pack_path") or _coherence_value(
        plan, "canonical_pack_ref", "pack_path"
    )
    predecessor_path = resolve_pack_path(root, str(predecessor_path_value))
    if predecessor_path != active[0][0]:
        raise SystemExit("replace_pack predecessor is not the unique active pack.")
    predecessor = load_json(predecessor_path)
    coherence = validate_pack_coherence_contract(root, plan, require_declared=True)
    if coherence.get("status") == "block":
        output = {
            "status": "block",
            "action": "replace",
            "pack_path": rel_path(root, predecessor_path),
            "pack_transition_verdict": {
                "status": "blocked",
                "evidence_ref": rel_path(root, predecessor_path),
            },
            "findings": coherence.get("findings", []),
        }
        json.dump(output, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
        sys.stdout.write("\n")
        return 2
    successor, successor_path, predecessor_render_path, successor_render_path = (
        _prepare_successor_body(args, root, plan, predecessor_path)
    )
    create_entry = mutation_entry("create", plan, [], item_order(successor))
    initial_selection = plan.get("initial_selection")
    create_entry["timestamp"] = str(successor["created_at"])
    create_entry["predecessor_pack_ref"] = rel_path(root, predecessor_path)
    successor.setdefault("mutation_log", []).append(create_entry)
    successor_findings = publication_findings(
        successor, successor_path, check_size=False
    )
    if successor_findings:
        output = {
            "status": "block",
            "action": "replace",
            "pack_path": rel_path(root, successor_path),
            "pack_transition_verdict": {
                "status": "blocked",
                "evidence_ref": rel_path(root, successor_path),
            },
            "findings": successor_findings,
        }
        json.dump(output, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
        sys.stdout.write("\n")
        return 2
    durable_creation = persist_creation_snapshot(root, successor_path, successor)
    initial_selection_applied, successor_findings = apply_initial_selection_to_new_pack(
        root,
        successor_path,
        successor,
        initial_selection if isinstance(initial_selection, dict) else None,
        durable_creation,
        check_size=False,
        dry_run=bool(getattr(args, "dry_run", False)),
    )
    carry_findings, carry_bindings = validate_carry_forward_contract(
        root, predecessor_path, predecessor, successor
    )
    successor_findings.extend(carry_findings)
    if successor_findings:
        output = {
            "status": "block",
            "action": "replace",
            "pack_path": rel_path(root, successor_path),
            "pack_transition_verdict": {
                "status": "blocked",
                "evidence_ref": rel_path(root, successor_path),
            },
            "findings": successor_findings,
        }
        json.dump(output, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
        sys.stdout.write("\n")
        return 2
    return (
        predecessor_path,
        predecessor,
        successor_path,
        successor,
        predecessor_render_path,
        successor_render_path,
        durable_creation,
        initial_selection_applied,
        carry_bindings,
    )
