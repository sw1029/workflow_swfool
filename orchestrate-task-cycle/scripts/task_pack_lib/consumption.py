"""Serialized in-flight item consumption command."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .coherence import validate_pack_coherence_contract
from .consumption_fields import (
    apply_acceptance_result_fields,
    apply_core_result_fields,
    apply_evidence_result_fields,
    apply_policy_result_fields,
    consume_promoted_item,
)
from .contracts import PACK_COHERENCE_VERSION
from .ordering import item_order
from .packet_io import load_json, load_plan, write_json
from .rendering import write_render
from .storage import canonical_pack_sha256, now_iso, pack_mutation_lock, rel_path, resolve_pack_path
from .store import active_pack, task_pack_store_findings
from .validation import validate_pack


def command_mark_consumed(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    with pack_mutation_lock(root):
        return _command_mark_consumed_locked(args, root)


def _command_mark_consumed_locked(args: argparse.Namespace, root: Path) -> int:
    store_findings = task_pack_store_findings(root)
    if store_findings:
        raise SystemExit(store_findings[0]["message"])
    path = resolve_pack_path(root, args.pack) if args.pack else active_pack(root)[0]
    if path is None:
        raise SystemExit("No active task pack found.")
    data = load_json(path)
    coherence_payload = load_plan(args.pack_coherence_json) if args.pack_coherence_json else {}
    coherence_plan = dict(coherence_payload) if "pack_coherence" in coherence_payload else {"pack_coherence": coherence_payload}
    coherence_plan.update(
        {
            "action": "mark_consumed",
            "pack_path": rel_path(root, path),
        }
    )
    coherence_result = validate_pack_coherence_contract(root, coherence_plan, require_declared=True)
    if coherence_result["status"] == "block":
        output = {
            "status": "block",
            "pack_path": rel_path(root, path),
            "pack_transition_verdict": {"status": "blocked", "evidence_ref": rel_path(root, path)},
            "findings": coherence_result["findings"],
        }
        json.dump(output, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
        sys.stdout.write("\n")
        return 2
    coherence = dict(coherence_result["pack_coherence"] or {})
    verdict_payload = load_plan(args.verdict_axes_json) if args.verdict_axes_json else {}
    target = next(
        (
            item
            for item in data.get("items", [])
            if isinstance(item, dict) and item.get("item_id") == args.item_id
        ),
        None,
    )
    if target is None:
        raise SystemExit(f"Unknown task pack item: {args.item_id}")
    result = consume_promoted_item(root, target, args)
    apply_core_result_fields(result, args, verdict_payload, coherence)
    apply_acceptance_result_fields(result, args)
    apply_evidence_result_fields(result, args)
    apply_policy_result_fields(result, args)
    remaining = [item for item in data.get("items", []) if isinstance(item, dict) and item.get("status") in {"planned", "inserted", "reordered"}]
    data["current_item_id"] = remaining[0].get("item_id") if remaining else None
    if not remaining and data.get("status") == "active":
        data["status"] = "completed"
    data.setdefault("mutation_log", []).append(
        {
            "timestamp": now_iso(),
            "action": "mark_consumed",
            "reason": args.reason or "pack item consumed by completed task",
            "item_id": args.item_id,
            "actor": "$derive-improvement-task",
        }
    )
    actual_after_ids = item_order(data)
    coherence_findings: list[dict[str, Any]] = []
    for key, actual_value in (
        ("proposed_after_item_ids", actual_after_ids),
        ("proposed_after_order", actual_after_ids),
    ):
        declared = coherence.get(key)
        if isinstance(declared, list) and [str(item) for item in declared] != actual_value:
            coherence_findings.append(
                {
                    "severity": "block",
                    "code": f"{key}_mismatch",
                    "message": "Consumed pack state does not match the declared post-mutation state.",
                    "evidence": {"declared": declared, "actual": actual_value},
                }
            )
    after_pack_sha256 = canonical_pack_sha256(data)
    if (
        coherence.get("contract_version") == PACK_COHERENCE_VERSION
        and coherence.get("before_pack_sha256") == after_pack_sha256
    ):
        coherence_findings.append(
            {
                "severity": "block",
                "code": "pack_mutation_noop",
                "message": "mark_consumed did not change the canonical pack body.",
            }
        )
    findings = validate_pack(data, path)
    findings.extend(coherence_findings)
    if any(item.get("severity") == "block" for item in findings):
        output = {
            "status": "block",
            "pack_path": rel_path(root, path),
            "pack_id": data.get("pack_id"),
            "pack_transition_verdict": {"status": "blocked", "evidence_ref": rel_path(root, path)},
            "findings": findings,
        }
        json.dump(output, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
        sys.stdout.write("\n")
        return 2
    write_json(path, data)
    if args.render:
        write_render(root, path, data, args.language)
    mutation_receipt = {
        "schema_version": PACK_COHERENCE_VERSION,
        "canonical_pack_ref": rel_path(root, path),
        "before_pack_sha256": coherence.get("before_pack_sha256"),
        "after_pack_sha256": after_pack_sha256,
        "actual_before_item_ids": coherence.get("actual_before_item_ids"),
        "actual_before_order": coherence.get("actual_before_order"),
        "actual_before_current_item": coherence.get("actual_current_item"),
        "actual_after_item_ids": actual_after_ids,
        "actual_after_order": actual_after_ids,
        "actual_after_current_item": data.get("current_item_id"),
        "mutation_kind": "mark_consumed",
        "legacy_normalized": bool(coherence.get("legacy_normalized")),
    }
    output = {
        "status": "ok",
        "pack_path": rel_path(root, path),
        "pack_id": data.get("pack_id"),
        "current_item_id": data.get("current_item_id"),
        "pack_coherence": coherence,
        "pack_mutation_receipt": mutation_receipt,
        "pack_transition_verdict": {"status": "pass", "evidence_ref": rel_path(root, path)},
    }
    json.dump(output, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


