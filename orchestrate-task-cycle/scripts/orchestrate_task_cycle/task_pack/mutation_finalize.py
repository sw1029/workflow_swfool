"""Post-mutation coherence, persistence, and response assembly."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .coherence import _coherence_value
from .contracts import PACK_COHERENCE_VERSION
from . import mutation_journal
from .ordering import item_order, sorted_items
from .rendering import write_render
from .storage import (
    canonical_pack_sha256,
    guard_content_addressed_consumer,
    now_iso,
    rel_path,
)
from .validation import validate_pack


def _post_mutation_findings(
    data: dict[str, Any],
    path: Path,
    plan: dict[str, Any],
    action: str,
    coherence: dict[str, Any],
) -> tuple[list[dict[str, Any]], str]:
    actual_after_ids = item_order(data)
    coherence_findings: list[dict[str, Any]] = []
    for field, code, message in (
        (
            "proposed_after_item_ids",
            "proposed_after_item_ids_mismatch",
            "Actual pack item IDs do not match the declared post-mutation state.",
        ),
        (
            "proposed_after_order",
            "proposed_after_order_mismatch",
            "Actual pack order does not match the declared post-mutation order.",
        ),
    ):
        proposed = coherence.get(field)
        if (
            isinstance(proposed, list)
            and [str(item) for item in proposed] != actual_after_ids
        ):
            coherence_findings.append(
                {
                    "severity": "block",
                    "code": code,
                    "message": message,
                    "evidence": {"declared": proposed, "actual": actual_after_ids},
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
                "message": "Current pack mutation did not change the canonical pack body.",
                "evidence": {
                    "mutation_kind": action,
                    "canonical_pack_sha256": after_pack_sha256,
                },
            }
        )
    declared_after_hash = _coherence_value(plan, "after_pack_sha256")
    if declared_after_hash:
        normalized_after_hash = str(declared_after_hash).removeprefix("sha256:").lower()
        if normalized_after_hash != after_pack_sha256:
            coherence_findings.append(
                {
                    "severity": "block",
                    "code": "declared_after_pack_sha256_mismatch",
                    "message": "Declared post-mutation pack hash does not match the canonical resulting state.",
                    "evidence": {
                        "declared": normalized_after_hash,
                        "actual": after_pack_sha256,
                    },
                }
            )
    findings = validate_pack(data, path)
    findings.extend(coherence_findings)
    return findings, after_pack_sha256


def finalize_existing_mutation(
    args: argparse.Namespace,
    root: Path,
    path: Path,
    data: dict[str, Any],
    plan: dict[str, Any],
    action: str,
    coherence: dict[str, Any],
    before_order: list[str],
) -> int:
    findings, _ = _post_mutation_findings(data, path, plan, action, coherence)
    if any(item.get("severity") == "block" for item in findings):
        output = {
            "status": "block",
            "action": action,
            "pack_path": rel_path(root, path),
            "pack_transition_verdict": {
                "status": "blocked",
                "evidence_ref": rel_path(root, path),
            },
            "findings": findings,
        }
        json.dump(output, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
        sys.stdout.write("\n")
        return 2
    if getattr(args, "dry_run", False):
        output = {
            "status": "dry_run",
            "action": action,
            "pack_path": rel_path(root, path),
            "pack_id": data.get("pack_id"),
            "before_pack_sha256": coherence.get("before_pack_sha256"),
            "proposed_after_pack_sha256": canonical_pack_sha256(data),
            "current_item_id": data.get("current_item_id"),
            "pack_transition_verdict": {
                "status": "pass",
                "evidence_ref": rel_path(root, path),
            },
            "findings": findings,
        }
        json.dump(output, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
        sys.stdout.write("\n")
        return 0
    mutation_receipt = {
        "schema_version": PACK_COHERENCE_VERSION,
        "canonical_pack_ref": rel_path(root, path),
        "before_pack_sha256": coherence.get("before_pack_sha256"),
        "after_pack_sha256": canonical_pack_sha256(data),
        "actual_before_item_ids": coherence.get("actual_before_item_ids"),
        "actual_before_order": coherence.get("actual_before_order"),
        "actual_before_current_item": coherence.get("actual_current_item"),
        "actual_after_item_ids": item_order(data),
        "actual_after_order": item_order(data),
        "actual_after_current_item": data.get("current_item_id"),
        "mutation_kind": action,
        "legacy_normalized": bool(coherence.get("legacy_normalized"))
        or action == "normalize_initial_selection_provenance",
    }
    data["updated_at"] = now_iso()
    guard_content_addressed_consumer(path, canonical_pack_sha256(data))
    durable_receipt = mutation_journal.commit_pack_mutation(
        root,
        action=action,
        plan=plan,
        target_path=path,
        after_data=data,
        before_pack_sha256=coherence.get("before_pack_sha256"),
        coherence_receipt=mutation_receipt,
    )
    mutation_receipt["durable_receipt_ref"] = durable_receipt.get("receipt_ref")
    mutation_receipt["durable_receipt_sha256"] = durable_receipt.get("receipt_sha256")
    render_output_path = None
    if args.render:
        render_output_path = write_render(root, path, data, args.language)
    output = {
        "status": "ok",
        "action": action,
        "pack_path": rel_path(root, path),
        "render_path": (
            rel_path(root, render_output_path) if render_output_path else None
        ),
        "pack_id": data.get("pack_id"),
        "pack_status": data.get("status"),
        "current_item_id": data.get("current_item_id"),
        "before_order": before_order,
        "after_order": item_order(data),
        "pack_coherence": coherence,
        "pack_mutation_receipt": mutation_receipt,
        "durable_mutation_receipt": durable_receipt,
        "pack_transition_verdict": {
            "status": "pass",
            "evidence_ref": rel_path(root, path),
        },
        "findings": findings,
    }
    if action == "normalize_initial_selection_provenance":
        first_receipt = next(
            (
                item.get("promotion", {}).get("provenance_normalization")
                for item in sorted_items(data)
                if isinstance(item.get("promotion"), dict)
                and isinstance(
                    item.get("promotion", {}).get("provenance_normalization"), dict
                )
            ),
            {},
        )
        output["normalization_authority_status"] = first_receipt.get(
            "normalization_authority_status"
        )
        output["historical_authority_verdict"] = first_receipt.get(
            "historical_authority_verdict"
        )
        output["semantic_progress"] = False
        output["progress_kind"] = "governance_only"
    json.dump(output, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0
