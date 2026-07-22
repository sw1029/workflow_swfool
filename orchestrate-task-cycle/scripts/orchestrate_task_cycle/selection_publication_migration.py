"""Explicit legacy-history migration into bounded selection state."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from .selection_publication_intent_index import (
    write_commit_index,
    write_prepare_index,
)
from .selection_publication_state import (
    STORAGE_SCHEMA_VERSION,
    write_state,
)
from .selection_publication_store import _lock, _receipt_path, _sha256_file


def migrate_publication_state(
    root: Path,
    *,
    committed_receipts: Callable[[Path], list[dict[str, Any]]],
    deep_pending_ids: Callable[[Path], list[str]],
    load_prepare: Callable[
        [Path, str], tuple[dict[str, Any], Path, str]
    ],
) -> dict[str, Any]:
    """Audit legacy history once and materialize schema-v4 lookup state."""

    root = root.expanduser().resolve(strict=True)
    with _lock(root):
        receipts = committed_receipts(root)
        pending = deep_pending_ids(root)
        state = write_state(root, receipts, pending, load_prepare=load_prepare)
        for transaction_id in [
            *(str(row["transaction_id"]) for row in receipts),
            *pending,
        ]:
            prepare, prepare_path, prepare_sha = load_prepare(root, transaction_id)
            intent_sha256 = prepare.get("intent_sha256")
            if not isinstance(intent_sha256, str):
                continue
            write_prepare_index(
                root, intent_sha256, transaction_id, prepare_path, prepare_sha
            )
            receipt_path = _receipt_path(root, transaction_id)
            receipt_sha = _sha256_file(receipt_path)
            if receipt_sha is not None:
                write_commit_index(
                    root,
                    intent_sha256,
                    transaction_id,
                    prepare_path,
                    prepare_sha,
                    receipt_path,
                    receipt_sha,
                )
    return {
        "status": "migrated",
        "storage_schema_version": STORAGE_SCHEMA_VERSION,
        "receipt_count": len(receipts),
        "pending_count": 1 if state.get("active_transaction") else 0,
        "state_ref": ".task/selection_publication/state.json",
        "state_content_sha256": state["state_content_sha256"],
        "mutation_performed": True,
    }


__all__ = ("migrate_publication_state",)
