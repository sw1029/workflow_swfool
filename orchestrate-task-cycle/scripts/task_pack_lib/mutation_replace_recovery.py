"""Replay and forward-recovery stages for replacement mutations."""

from __future__ import annotations

import json
import sys

import task_pack_replacement

from .replacement import replacement_postcondition, validate_replacement_receipt
from .storage import rel_path


def _replay_or_recover_replacement(
    args, root, plan, plan_fingerprint, completed, pending
):
    if completed:
        transaction_id = completed[0]
        receipt = task_pack_replacement.validate_completed_transaction(
            root, transaction_id
        )
        validation = validate_replacement_receipt(root, plan, receipt)
        if validation.get("status") != "ok":
            raise SystemExit("Completed replacement replay failed receipt validation.")
        output = {
            "status": "no_op",
            "action": "replace",
            "transaction_id": transaction_id,
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
    if pending:
        pending_for_plan = task_pack_replacement.pending_transaction_ids_for_plan(
            root, plan_fingerprint
        )
        if len(pending_for_plan) != 1 or pending != pending_for_plan:
            raise SystemExit(
                "A different prepared task-pack replacement must be recovered first."
            )
        transaction_id = pending_for_plan[0]
        if getattr(args, "dry_run", False):
            output = {
                "status": "block",
                "action": "replace",
                "transaction_id": transaction_id,
                "recovery_required": True,
                "pack_transition_verdict": {
                    "status": "blocked",
                    "evidence_ref": rel_path(
                        root, task_pack_replacement.prepare_path(root, transaction_id)
                    ),
                },
                "findings": [
                    {
                        "severity": "block",
                        "code": "replacement_transaction_pending",
                        "message": "Dry-run never recovers a prepared replacement; run recover-replacement explicitly.",
                    }
                ],
            }
            json.dump(output, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
            sys.stdout.write("\n")
            return 2
        receipt = task_pack_replacement.publish_transaction(
            root,
            transaction_id,
            postcondition=lambda prepare: replacement_postcondition(root, prepare),
        )
        validation = validate_replacement_receipt(root, plan, receipt)
        if validation.get("status") != "ok":
            raise SystemExit(
                "Recovered replacement journal failed exact receipt validation."
            )
        output = {
            "status": "recovered",
            "action": "replace",
            "transaction_id": transaction_id,
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
    return None
