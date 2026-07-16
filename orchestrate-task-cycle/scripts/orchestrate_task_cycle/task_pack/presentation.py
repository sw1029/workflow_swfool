"""Read-only task-pack commands and capability presentation."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from . import replacement_engine as task_pack_replacement

from .contracts import PROGRESS_KINDS, PROGRESS_TARGETS, VERDICT_AXES
from .ordering import active_in_flight_items, next_item
from .packet_io import load_json
from .receipts import pack_paths
from .rendering import bounded_render_path, write_render
from .replacement import replacement_postcondition
from .storage import pack_mutation_lock, rel_path, resolve_pack_path
from .store import active_pack, active_pack_candidates, status_from_findings, task_pack_store_findings
from .validation import validate_pack

def command_status(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    with pack_mutation_lock(root, create=False):
        return _command_status_locked(root)


def _command_status_locked(root: Path) -> int:
    store_findings = task_pack_store_findings(root)
    active = active_pack_candidates(root)
    path, data = active[0] if len(active) == 1 else (None, None)
    active_refs = [rel_path(root, candidate) for candidate, _body in active]
    if store_findings:
        output = {
            "status": "block",
            "active_pack": rel_path(root, path) if path else None,
            "active_pack_count": len(active),
            "active_pack_refs": active_refs,
            "pack_count": len(pack_paths(root)),
            "findings": store_findings,
        }
    if not path or not data:
        if not store_findings:
            output = {
                "status": "not_applicable",
                "active_pack": None,
                "active_pack_count": 0,
                "active_pack_refs": [],
                "pack_count": len(pack_paths(root)),
                "findings": [],
            }
    elif not store_findings:
        findings = validate_pack(data, path)
        in_flight = active_in_flight_items(data)
        item = None if in_flight else next_item(data)
        output = {
            "status": status_from_findings(findings),
            "active_pack": rel_path(root, path),
            "render_path": rel_path(root, bounded_render_path(root, path)) if bounded_render_path(root, path).exists() else None,
            "pack_id": data.get("pack_id"),
            "pack_status": data.get("status"),
            "goal": data.get("goal"),
            "current_item_id": data.get("current_item_id"),
            "next_item": item,
            "queue_disposition": "in_flight" if in_flight else "ready" if item else "terminal_candidate",
            "in_flight_item": in_flight[0] if len(in_flight) == 1 else None,
            "planned_item_count": sum(1 for item_data in data.get("items", []) if isinstance(item_data, dict) and item_data.get("status") in {"planned", "inserted", "reordered"}),
            "terminal_blocker": data.get("terminal_blocker"),
            "findings": findings,
            "pack_count": len(pack_paths(root)),
            "active_pack_count": 1,
            "active_pack_refs": active_refs,
        }
    json.dump(output, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0 if output["status"] not in {"block"} else 2


def command_validate(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    with pack_mutation_lock(root, create=False):
        return _command_validate_locked(root, args)


def _command_validate_locked(root: Path, args: argparse.Namespace) -> int:
    paths = [resolve_pack_path(root, args.pack)] if args.pack else pack_paths(root)
    results = []
    store_findings = task_pack_store_findings(root)
    status = status_from_findings(store_findings)
    for path in paths:
        data = load_json(path)
        findings = validate_pack(data, path)
        result_status = status_from_findings(findings)
        if result_status == "block":
            status = "block"
        elif result_status == "warn" and status == "ok":
            status = "warn"
        results.append({"path": rel_path(root, path), "status": result_status, "findings": findings})
    strict = bool(getattr(args, "strict_findings", False))
    output = {
        "status": status,
        "strict_findings": strict,
        "store_findings": store_findings,
        "results": results,
        "pack_count": len(results),
    }
    json.dump(output, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 2 if status == "block" or (strict and status != "ok") else 0


def capability_contract() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "helper": "task_pack_queue",
        "pack_schema_versions": [1],
        "actions": [
            "create_pack",
            "replace_pack",
            "promote_next_item",
            "normalize_initial_selection_provenance",
            "insert_items",
            "reorder_items",
            "skip_items",
            "supersede_pack",
            "terminal_blocked",
        ],
        "canonical_progress_targets": sorted(PROGRESS_TARGETS),
        "canonical_progress_kinds": sorted(PROGRESS_KINDS),
        "verdict_axes": list(VERDICT_AXES),
        "item_kind": {
            "supported": True,
            "required": False,
            "vocabulary": "open",
            "syntax": "bounded_path_safe_token",
            "authoritative_for_progress": False,
        },
        "publication": {
            "create_findings_policy": "clean",
            "replace_successor_findings_policy": "clean",
            "max_active_packs": 1,
            "optional_initial_selection": True,
            "prospective_task_preflight": "hash_bound_workspace_staging_ref",
            "replacement_recovery": "fail_closed_forward_complete",
            "replacement_plan_binding": "content_addressed_plan_and_target_manifest",
            "replacement_receipt_supply": "exact_durable_receipt_with_ref_and_sha256",
            "live_predecessor_retirement": "explicit_reason_and_hash_bound_evidence",
            "atomic_scope": "task_pack_store_and_helper_owned_evidence",
            "task_md_in_atomic_scope": False,
        },
        "size_policy": {
            "new_sequence_min": 2,
            "new_sequence_max": 5,
            "replacement_max_new_items": 5,
            "replacement_over_five_requires_carry_forward_contract": True,
        },
    }
def command_capabilities(_args: argparse.Namespace) -> int:
    json.dump(capability_contract(), sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


def command_recover_replacement(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    with pack_mutation_lock(root):
        pending = task_pack_replacement.pending_transaction_ids(root)
        if len(pending) > 1:
            raise SystemExit("Multiple pending task-pack replacements require manual integrity review.")
        receipts = [
            task_pack_replacement.publish_transaction(
                root,
                transaction_id,
                postcondition=lambda prepare: replacement_postcondition(root, prepare),
            )
            for transaction_id in pending
        ]
    output = {
        "status": "ok",
        "recovered_count": len(receipts),
        "receipts": receipts,
        "remaining_pending_transaction_ids": task_pack_replacement.pending_transaction_ids(root),
    }
    json.dump(output, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


def command_render(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    with pack_mutation_lock(root):
        store_findings = task_pack_store_findings(root)
        if store_findings:
            output = {"status": "block", "rendered": [], "findings": store_findings}
            json.dump(output, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
            sys.stdout.write("\n")
            return 2
        paths = [resolve_pack_path(root, args.pack)] if args.pack else pack_paths(root)
        rendered = []
        for path in paths:
            data = load_json(path)
            findings = validate_pack(data, path)
            if any(item.get("severity") == "block" for item in findings):
                rendered.append({"path": rel_path(root, path), "status": "block", "findings": findings})
                continue
            output_path = write_render(root, path, data, args.language)
            rendered.append({"path": rel_path(root, path), "status": "rendered", "render_path": rel_path(root, output_path), "findings": findings})
    output = {"status": "block" if any(item["status"] == "block" for item in rendered) else "ok", "rendered": rendered}
    json.dump(output, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0 if output["status"] != "block" else 2


def command_next(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    with pack_mutation_lock(root, create=False):
        return _command_next_locked(root)


def _command_next_locked(root: Path) -> int:
    path, data = active_pack(root)
    if not path or not data:
        output = {"status": "not_applicable", "next_item": None}
    else:
        in_flight = active_in_flight_items(data)
        item = None if in_flight else next_item(data)
        output = {
            "status": "in_flight" if in_flight else "ok" if item else "terminal_candidate",
            "pack_path": rel_path(root, path),
            "pack_id": data.get("pack_id"),
            "next_item": item,
            "in_flight_item": in_flight[0] if len(in_flight) == 1 else None,
            "terminal_blocker": data.get("terminal_blocker"),
        }
    json.dump(output, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0
