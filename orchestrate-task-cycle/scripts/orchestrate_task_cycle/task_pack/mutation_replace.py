"""Atomic replacement mutation workflow."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from . import replacement_engine as task_pack_replacement

from .mutation_replace_draft import _prepare_replacement_draft
from .mutation_replace_publication import (
    _prepare_replacement_publication,
    _publish_or_preview_replacement,
)
from .mutation_replace_recovery import _replay_or_recover_replacement
from .receipts import _forbidden_receipt_key_paths
from .replacement import replacement_plan_fingerprint


def apply_replace(
    args: argparse.Namespace, root: Path, plan: dict[str, Any], pending: list[str]
) -> int:
    forbidden_plan_keys = _forbidden_receipt_key_paths(plan)
    if forbidden_plan_keys:
        raise SystemExit(
            "Replacement plan snapshots must be body-safe; replace raw/sensitive fields with opaque evidence IDs and hashes: "
            + ", ".join(forbidden_plan_keys)
        )
    plan_fingerprint = replacement_plan_fingerprint(plan)
    completed = task_pack_replacement.completed_transaction_ids_for_plan(
        root, plan_fingerprint
    )
    if len(completed) > 1:
        raise SystemExit(
            "Replacement plan is bound to multiple committed transactions."
        )
    replay_result = _replay_or_recover_replacement(
        args, root, plan, plan_fingerprint, completed, pending
    )
    if replay_result is not None:
        return replay_result
    prepared = _prepare_replacement_draft(args, root, plan)
    if isinstance(prepared, int):
        return prepared
    (
        predecessor_path,
        predecessor,
        successor_path,
        successor,
        predecessor_render_path,
        successor_render_path,
        durable_creation,
        initial_selection_applied,
        carry_bindings,
    ) = prepared
    publication = _prepare_replacement_publication(
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
    )
    if isinstance(publication, int):
        return publication
    (
        predecessor_after_bytes,
        successor_after_bytes,
        targets,
        plan_snapshot_path,
        metadata,
        transaction_id,
    ) = publication
    return _publish_or_preview_replacement(
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
    )
