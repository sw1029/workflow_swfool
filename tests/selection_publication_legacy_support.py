"""Private fixture builder for immutable v1 selection recovery tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from orchestrate_task_cycle import selection_publication as publication
from orchestrate_task_cycle.selection_publication_prepare import (
    committed_replay,
    new_predecessor_transaction_id,
    pending_replay,
    prepare_response,
)
from orchestrate_task_cycle.selection_publication_state import (
    STORAGE_SCHEMA_VERSION,
    head_receipts,
    record_prepared,
)


def prepare_legacy_publication(
    root: Path, plan: dict[str, Any]
) -> dict[str, Any]:
    root = root.expanduser().resolve(strict=True)
    normalized = publication._normalize_plan(root, plan)
    with publication._lock(root):
        state = publication._load_or_initialize_state(root)
        pending = publication._state_pending_ids(state)
        replay = pending_replay(
            root, normalized, pending, load_prepare=publication._load_prepare
        )
        if replay is not None:
            return {**replay, "storage_schema_version": STORAGE_SCHEMA_VERSION}
        receipts = head_receipts(state)
        replay = committed_replay(
            root, normalized, receipts, load_prepare=publication._load_prepare
        )
        if replay is not None:
            return {**replay, "storage_schema_version": STORAGE_SCHEMA_VERSION}
        predecessor = new_predecessor_transaction_id(
            normalized, receipts, publication._sha256_file(root / "task.md")
        )
        material = {**normalized, "predecessor_transaction_id": predecessor}
        transaction_id = "selection-" + publication._sha256_bytes(
            publication._canonical_json(material)
        )
        prepare = {**material, "transaction_id": transaction_id}
        path = publication._prepare_path(root, transaction_id)
        digest = publication._write_once(
            path,
            publication._display_json(prepare),
            "selection-publication prepare journal",
        )
        publication._load_prepare(root, transaction_id)
        record_prepared(root, state, prepare, digest)
    return {
        **prepare_response(
            root,
            transaction_id,
            path,
            digest,
            status="prepared",
            mutation_performed=True,
            recovery_required=True,
        ),
        "storage_schema_version": STORAGE_SCHEMA_VERSION,
    }


__all__ = ("prepare_legacy_publication",)
