"""Serialized task-pack mutation command facade."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import replacement_engine as task_pack_replacement

from .contracts import normalize_action
from .mutation_create import apply_create
from .mutation_existing import apply_existing
from .mutation_replace import apply_replace
from . import mutation_journal
from .packet_io import load_plan
from .render_recovery import recover_requested_render
from .storage import content_addressed_write_transaction, pack_mutation_lock

_ALLOWED_ACTIONS = {
    "insert",
    "reorder",
    "skip",
    "supersede",
    "terminal_block",
    "create",
    "replace",
    "promote",
    "normalize_initial_selection_provenance",
}


def command_apply_mutation(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    with (
        pack_mutation_lock(
            root,
            create=not bool(getattr(args, "dry_run", False)),
        ),
        content_addressed_write_transaction() as evidence_transaction,
    ):
        result = _command_apply_mutation_locked(args, root)
        if result == 0 and not getattr(args, "dry_run", False):
            evidence_transaction.commit()
        return result


def _command_apply_mutation_locked(args: argparse.Namespace, root: Path) -> int:
    plan = load_plan(args.plan)
    action = normalize_action(
        args.action or str(plan.get("action") or plan.get("pack_disposition") or "")
    )
    if action not in _ALLOWED_ACTIONS:
        raise SystemExit(
            "Mutation action must be create, replace, promote, normalize_initial_selection_provenance, insert, reorder, skip, supersede, or terminal_block."
        )

    generic_pending = mutation_journal.pending_transaction_ids(root)
    if generic_pending and getattr(args, "dry_run", False):
        raise SystemExit(
            "A prepared task-pack mutation must be recovered before dry-run inspection."
        )
    recovered_receipts = (
        mutation_journal.recover_pending_transactions(root) if generic_pending else []
    )
    if action != "replace" and not getattr(args, "dry_run", False):
        completed = mutation_journal.completed_for_plan(root, plan)
        if len(completed) > 1:
            raise SystemExit(
                "Mutation plan maps to multiple durable completion receipts."
            )
        if completed:
            receipt = completed[0]
            render_path = recover_requested_render(
                root,
                receipt,
                requested=bool(getattr(args, "render", False)),
                language=str(getattr(args, "language", "en")),
            )
            coherence_receipt = dict(receipt.get("coherence_receipt") or {})
            coherence_receipt.update(
                {
                    "durable_receipt_ref": receipt.get("receipt_ref"),
                    "durable_receipt_sha256": receipt.get("receipt_sha256"),
                }
            )
            output = {
                "status": (
                    "recovered"
                    if any(
                        recovered.get("plan_fingerprint")
                        == receipt.get("plan_fingerprint")
                        for recovered in recovered_receipts
                    )
                    else "already_committed"
                ),
                "action": action,
                "pack_path": receipt.get("target_ref"),
                "render_path": render_path,
                "pack_mutation_receipt": coherence_receipt,
                "durable_mutation_receipt": receipt,
                "pack_transition_verdict": {
                    "status": "pass",
                    "evidence_ref": receipt.get("receipt_ref"),
                },
                "recovery_performed": bool(recovered_receipts),
                "recovered_receipts": recovered_receipts,
            }
            json.dump(output, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
            sys.stdout.write("\n")
            return 0

    pending = task_pack_replacement.pending_transaction_ids(root)
    if pending and action != "replace":
        raise SystemExit(
            "A prepared task-pack replacement must be recovered before another mutation."
        )
    if action == "replace":
        return apply_replace(args, root, plan, pending)
    if action == "create":
        return apply_create(args, root, plan)
    return apply_existing(args, root, plan, action)
