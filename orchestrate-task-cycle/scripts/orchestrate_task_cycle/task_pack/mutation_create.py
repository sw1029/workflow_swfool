"""New-pack creation mutation workflow."""
from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path
from typing import Any


from .contracts import PACK_COHERENCE_VERSION, PACK_ID_PATTERN
from . import mutation_journal
from .creation import apply_initial_selection_to_new_pack
from .ordering import (
    item_order,
    refresh_current_item,
)
from .provenance import (
    mutation_entry,
)
from .receipts import (
    persist_creation_snapshot,
    render_creation_snapshot,
)
from .rendering import write_render
from .storage import (
    canonical_pack_sha256,
    guard_content_addressed_consumer,
    now_iso,
    rel_path,
    resolve_pack_path,
)
from .store import active_pack_candidates, task_pack_store_findings
from .validation import publication_findings


def apply_create(args: argparse.Namespace, root: Path, plan: dict[str, Any]) -> int:
    store_findings = task_pack_store_findings(root)
    if store_findings:
        raise SystemExit(store_findings[0]["message"])
    if active_pack_candidates(root):
        raise SystemExit("Create mutation requires no active task pack; use replace_pack for an active predecessor.")
    pack_data = copy.deepcopy(plan.get("pack") if isinstance(plan.get("pack"), dict) else plan)
    initial_selection = plan.get("initial_selection")
    pack_id = str(pack_data.get("pack_id") or "").strip()
    if not PACK_ID_PATTERN.fullmatch(pack_id):
        raise SystemExit("Create mutation requires a path-safe `pack_id` token of at most 128 characters.")
    path = resolve_pack_path(root, f".task/task_pack/{pack_id}.json", must_exist=False)
    if path.exists():
        raise SystemExit(f"Task pack already exists: {rel_path(root, path)}")
    pack_data.setdefault("schema_version", 1)
    pack_data.setdefault("status", "active")
    pack_data.setdefault("language", args.language)
    pack_data.setdefault("created_at", now_iso())
    pack_data.setdefault("updated_at", now_iso())
    pack_data.setdefault("mutation_log", [])
    pack_data.setdefault("terminal_blocker", None)
    refresh_current_item(pack_data)
    create_entry = mutation_entry("create", plan, [], item_order(pack_data))
    if isinstance(initial_selection, dict):
        create_entry["timestamp"] = str(pack_data.get("created_at") or create_entry["timestamp"])
    pack_data.setdefault("mutation_log", []).append(create_entry)
    findings = publication_findings(pack_data, path, check_size=True)
    if findings:
        output = {
            "status": "block",
            "pack_path": rel_path(root, path),
            "pack_transition_verdict": {"status": "blocked", "evidence_ref": rel_path(root, path)},
            "findings": findings,
        }
        json.dump(output, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
        sys.stdout.write("\n")
        return 2
    durable_creation = (
        render_creation_snapshot(root, path, pack_data)
        if getattr(args, "dry_run", False)
        else persist_creation_snapshot(root, path, pack_data)
    )
    initial_selection_applied, findings = apply_initial_selection_to_new_pack(
        root,
        path,
        pack_data,
        initial_selection if isinstance(initial_selection, dict) else None,
        durable_creation,
        check_size=True,
        dry_run=bool(getattr(args, "dry_run", False)),
    )
    if findings:
        raise SystemExit(
            "Create initial-selection transaction failed final validation: "
            + "; ".join(str(item.get("code")) for item in findings)
        )
    if getattr(args, "dry_run", False):
        output = {
            "status": "dry_run",
            "action": "create",
            "pack_path": rel_path(root, path),
            "pack_id": pack_data.get("pack_id"),
            "proposed_after_pack_sha256": canonical_pack_sha256(pack_data),
            "current_item_id": pack_data.get("current_item_id"),
            "creation_snapshot": durable_creation,
            "initial_selection_applied": initial_selection_applied,
            "pack_transition_verdict": {"status": "pass", "evidence_ref": rel_path(root, path)},
            "findings": findings,
        }
        json.dump(output, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
        sys.stdout.write("\n")
        return 0
    pack_data["updated_at"] = now_iso()
    create_hash = canonical_pack_sha256(pack_data)
    create_receipt = {
        "schema_version": PACK_COHERENCE_VERSION,
        "canonical_pack_ref": rel_path(root, path),
        "before_pack_sha256": None,
        "after_pack_sha256": create_hash,
        "actual_before_item_ids": [],
        "actual_before_order": [],
        "actual_before_current_item": None,
        "actual_after_item_ids": item_order(pack_data),
        "actual_after_order": item_order(pack_data),
        "actual_after_current_item": pack_data.get("current_item_id"),
        "mutation_kind": "create",
        "legacy_normalized": False,
    }
    guard_content_addressed_consumer(path, create_hash)
    durable_receipt = mutation_journal.commit_pack_mutation(
        root,
        action="create",
        plan=plan,
        target_path=path,
        after_data=pack_data,
        before_pack_sha256=None,
        coherence_receipt=create_receipt,
    )
    create_receipt["durable_receipt_ref"] = durable_receipt.get("receipt_ref")
    create_receipt["durable_receipt_sha256"] = durable_receipt.get("receipt_sha256")
    render_output_path = None
    if args.render:
        render_output_path = write_render(root, path, pack_data, args.language)
    output = {
        "status": "ok",
        "action": "create",
        "pack_path": rel_path(root, path),
        "render_path": rel_path(root, render_output_path) if render_output_path else None,
        "pack_id": pack_data.get("pack_id"),
        "pack_coherence": {
            "schema_version": PACK_COHERENCE_VERSION,
            "canonical_pack_ref": rel_path(root, path),
            "before_pack_sha256": None,
            "after_pack_sha256": create_hash,
            "actual_after_item_ids": item_order(pack_data),
            "actual_after_order": item_order(pack_data),
            "actual_after_current_item": pack_data.get("current_item_id"),
            "mutation_kind": "create",
        },
        "pack_mutation_receipt": create_receipt,
        "creation_snapshot": durable_creation,
        "initial_selection_applied": initial_selection_applied,
        "pack_transition_verdict": {"status": "pass", "evidence_ref": rel_path(root, path)},
        "durable_mutation_receipt": durable_receipt,
    }
    json.dump(output, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0
