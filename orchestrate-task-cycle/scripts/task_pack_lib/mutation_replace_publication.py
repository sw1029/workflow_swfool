"""Atomic publication and preview stages for replacement mutations."""

from __future__ import annotations

import copy
import json
import sys

import task_pack_replacement

from .ordering import item_order, refresh_current_item
from .packet_io import write_content_addressed_file
from .provenance import mutation_entry
from .rendering import render_markdown
from .replacement import replacement_plan_snapshot_path, replacement_postcondition
from .storage import (
    canonical_pack_sha256,
    guard_content_addressed_consumer,
    json_bytes,
    rel_path,
    sha256_bytes,
    sha256_file,
    sha256_optional_file,
)
from .validation import validate_pack


def _prepare_replacement_publication(
    args,
    root,
    plan,
    plan_fingerprint,
    predecessor_path,
    predecessor,
    successor_path,
    successor,
    predecessor_render_path,
    successor_render_path,
    durable_creation,
    initial_selection_applied,
    carry_bindings,
):
    predecessor_after = copy.deepcopy(predecessor)
    predecessor_after["status"] = "superseded"
    for item in predecessor_after.get("items", []):
        if isinstance(item, dict) and item.get("status") in {
            "planned",
            "inserted",
            "reordered",
            "blocked",
        }:
            item["status"] = "superseded"
    supersede_entry = mutation_entry(
        "supersede", plan, item_order(predecessor_after), item_order(predecessor_after)
    )
    supersede_entry["replacement_plan_fingerprint"] = plan_fingerprint
    supersede_entry["successor_pack_ref"] = rel_path(root, successor_path)
    predecessor_after.setdefault("mutation_log", []).append(supersede_entry)
    refresh_current_item(predecessor_after)
    transaction_time = str(successor["updated_at"])
    supersede_entry["timestamp"] = transaction_time
    predecessor_after["updated_at"] = transaction_time
    predecessor_blocks = [
        finding
        for finding in validate_pack(predecessor_after, predecessor_path)
        if finding.get("severity") == "block"
    ]
    if predecessor_blocks:
        output = {
            "status": "block",
            "action": "replace",
            "pack_path": rel_path(root, predecessor_path),
            "pack_transition_verdict": {
                "status": "blocked",
                "evidence_ref": rel_path(root, predecessor_path),
            },
            "findings": predecessor_blocks,
        }
        json.dump(output, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
        sys.stdout.write("\n")
        return 2
    predecessor_after_bytes = json_bytes(predecessor_after)
    successor_after_bytes = json_bytes(successor)
    targets = [
        {
            "role": "predecessor_pack",
            "target_ref": rel_path(root, predecessor_path),
            "before_sha256": sha256_file(predecessor_path),
            "after_bytes": predecessor_after_bytes,
        },
        {
            "role": "successor_pack",
            "target_ref": rel_path(root, successor_path),
            "before_sha256": None,
            "after_bytes": successor_after_bytes,
        },
    ]
    if args.render:
        targets.extend(
            [
                {
                    "role": "predecessor_render",
                    "target_ref": rel_path(root, predecessor_render_path),
                    "before_sha256": sha256_optional_file(predecessor_render_path),
                    "after_bytes": render_markdown(
                        root, predecessor_path, predecessor_after, args.language
                    ).encode("utf-8"),
                },
                {
                    "role": "successor_render",
                    "target_ref": rel_path(root, successor_render_path),
                    "before_sha256": None,
                    "after_bytes": render_markdown(
                        root, successor_path, successor, args.language
                    ).encode("utf-8"),
                },
            ]
        )
    plan_snapshot_path = replacement_plan_snapshot_path(root, plan_fingerprint)
    metadata = {
        "plan_fingerprint": plan_fingerprint,
        "plan_snapshot_ref": rel_path(root, plan_snapshot_path),
        "plan_snapshot_sha256": plan_fingerprint,
        "predecessor_pack_ref": rel_path(root, predecessor_path),
        "predecessor_before_canonical_sha256": canonical_pack_sha256(predecessor),
        "predecessor_after_canonical_sha256": canonical_pack_sha256(predecessor_after),
        "successor_pack_ref": rel_path(root, successor_path),
        "successor_after_canonical_sha256": canonical_pack_sha256(successor),
        "creation_snapshot": durable_creation,
        "initial_selection_applied": initial_selection_applied,
        "carry_forward_bindings": carry_bindings,
    }
    transaction_id = task_pack_replacement.transaction_id_for_targets(metadata, targets)
    return (
        predecessor_after_bytes,
        successor_after_bytes,
        targets,
        plan_snapshot_path,
        metadata,
        transaction_id,
    )


def _publish_or_preview_replacement(
    args,
    root,
    plan,
    plan_fingerprint,
    predecessor_path,
    predecessor,
    successor_path,
    successor,
    predecessor_render_path,
    successor_render_path,
    durable_creation,
    initial_selection_applied,
    carry_bindings,
    predecessor_after_bytes,
    successor_after_bytes,
    targets,
    plan_snapshot_path,
    metadata,
    transaction_id,
):
    if getattr(args, "dry_run", False):
        output = {
            "status": "dry_run",
            "action": "replace",
            "transaction_id": transaction_id,
            "predecessor_pack_ref": rel_path(root, predecessor_path),
            "predecessor_before_sha256": sha256_file(predecessor_path),
            "predecessor_after_sha256": sha256_bytes(predecessor_after_bytes),
            "successor_pack_ref": rel_path(root, successor_path),
            "successor_after_sha256": sha256_bytes(successor_after_bytes),
            "successor_after_canonical_sha256": canonical_pack_sha256(successor),
            "plan_snapshot_ref": rel_path(root, plan_snapshot_path),
            "plan_snapshot_sha256": plan_fingerprint,
            "creation_snapshot": durable_creation,
            "initial_selection_applied": initial_selection_applied,
            "carry_forward_bindings": carry_bindings,
            "pack_transition_verdict": {
                "status": "pass",
                "evidence_ref": rel_path(root, successor_path),
            },
            "findings": [],
        }
        json.dump(output, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
        sys.stdout.write("\n")
        return 0
    write_content_addressed_file(
        plan_snapshot_path, json_bytes(plan), "Replacement plan snapshot"
    )
    prepare_info = task_pack_replacement.prepare_transaction(
        root, targets=targets, metadata=metadata
    )
    if prepare_info.get("transaction_id") != transaction_id:
        raise SystemExit(
            "Replacement prepare transaction identity changed during publication."
        )
    prepare_path = root / str(prepare_info["prepare_ref"])
    guard_content_addressed_consumer(
        prepare_path, canonical_pack_sha256(prepare_info["prepare"])
    )
    receipt = task_pack_replacement.publish_transaction(
        root,
        transaction_id,
        postcondition=lambda prepare: replacement_postcondition(root, prepare),
    )
    output = {
        "status": "ok",
        "action": "replace",
        "transaction_id": transaction_id,
        "predecessor_pack_ref": rel_path(root, predecessor_path),
        "successor_pack_ref": rel_path(root, successor_path),
        "render_path": rel_path(root, successor_render_path) if args.render else None,
        "creation_snapshot": durable_creation,
        "initial_selection_applied": initial_selection_applied,
        "carry_forward_bindings": carry_bindings,
        "pack_mutation_receipt": receipt,
        "pack_transition_verdict": {
            "status": "pass",
            "evidence_ref": receipt.get("receipt_ref"),
        },
        "findings": [],
    }
    json.dump(output, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0
