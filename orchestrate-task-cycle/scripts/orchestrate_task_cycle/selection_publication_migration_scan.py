"""Bounded legacy receipt/transaction inventory for explicit migration."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .selection_publication_migration_contract import (
    MAX_MIGRATION_TRANSACTIONS,
    MigrationBudget,
)
from .selection_publication_store import TRANSACTION_ID


def deep_pending_transaction_ids(
    root: Path, *, budget: MigrationBudget | None = None
) -> list[str]:
    """Enumerate pending history only for explicit bounded audit/migration."""

    from . import selection_publication as publication

    root = root.expanduser().resolve(strict=True)
    directory = publication._transactions_root(root)
    if not directory.is_dir():
        return []
    migration_budget = budget if budget is not None else MigrationBudget()
    candidates: list[str] = []
    with os.scandir(directory) as entries:
        for entry in entries:
            observed = entry.stat(follow_symlinks=False)
            migration_budget.consume_stat(
                observed, "legacy selection publication transaction entry"
            )
            if (
                entry.is_dir(follow_symlinks=False)
                and TRANSACTION_ID.fullmatch(entry.name)
            ):
                candidates.append(entry.name)
                if len(candidates) > MAX_MIGRATION_TRANSACTIONS:
                    raise ValueError(
                        "selection-publication migration exceeds "
                        "transaction-count bound"
                    )
    pending: list[str] = []
    for transaction_id in sorted(candidates):
        prepare_path = directory / transaction_id / "prepare.json"
        if not prepare_path.is_file() or prepare_path.is_symlink():
            continue
        migration_budget.consume_path(
            prepare_path, "legacy selection publication prepare"
        )
        try:
            publication.validate_receipt(root, transaction_id)
        except (OSError, ValueError):
            pending.append(transaction_id)
    return pending


def committed_receipts(
    root: Path, *, budget: MigrationBudget | None = None
) -> list[dict[str, Any]]:
    """Enumerate committed receipt history with hard entry and byte bounds."""

    from . import selection_publication as publication

    directory = publication._receipts_root(root)
    if not directory.is_dir():
        return []
    migration_budget = budget if budget is not None else MigrationBudget()
    candidates: list[str] = []
    with os.scandir(directory) as entries:
        for entry in entries:
            observed = entry.stat(follow_symlinks=False)
            migration_budget.consume_stat(
                observed, "legacy selection publication receipt entry"
            )
            if (
                entry.is_file(follow_symlinks=False)
                and entry.name.startswith("selection-")
                and entry.name.endswith(".json")
            ):
                transaction_id = entry.name[:-5]
                if TRANSACTION_ID.fullmatch(transaction_id):
                    candidates.append(transaction_id)
                    if len(candidates) > MAX_MIGRATION_TRANSACTIONS:
                        raise ValueError(
                            "selection-publication migration exceeds "
                            "transaction-count bound"
                        )
    return [
        publication.validate_receipt(root, transaction_id)
        for transaction_id in sorted(candidates)
    ]


__all__ = ("committed_receipts", "deep_pending_transaction_ids")
