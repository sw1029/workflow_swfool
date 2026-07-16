"""Serialized task-pack mutation command facade."""
from __future__ import annotations

import argparse
from pathlib import Path

from . import replacement_engine as task_pack_replacement

from .contracts import normalize_action
from .mutation_create import apply_create
from .mutation_existing import apply_existing
from .mutation_replace import apply_replace
from .packet_io import load_plan
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
    with pack_mutation_lock(
        root,
        create=not bool(getattr(args, "dry_run", False)),
    ), content_addressed_write_transaction() as evidence_transaction:
        result = _command_apply_mutation_locked(args, root)
        if result == 0 and not getattr(args, "dry_run", False):
            evidence_transaction.commit()
        return result


def _command_apply_mutation_locked(args: argparse.Namespace, root: Path) -> int:
    plan = load_plan(args.plan)
    action = normalize_action(args.action or str(plan.get("action") or plan.get("pack_disposition") or ""))
    if action not in _ALLOWED_ACTIONS:
        raise SystemExit(
            "Mutation action must be create, replace, promote, normalize_initial_selection_provenance, insert, reorder, skip, supersede, or terminal_block."
        )

    pending = task_pack_replacement.pending_transaction_ids(root)
    if pending and action != "replace":
        raise SystemExit("A prepared task-pack replacement must be recovered before another mutation.")
    if action == "replace":
        return apply_replace(args, root, plan, pending)
    if action == "create":
        return apply_create(args, root, plan)
    return apply_existing(args, root, plan, action)
