"""Bounded, receipt-last migration of legacy selection history."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from .selection_publication_intent_index import (
    commit_index_value,
    prepare_index_value,
    write_commit_index,
    write_prepare_index,
)
from .selection_publication_migration_contract import (
    MAX_MIGRATION_JOURNAL_BYTES,
    MAX_MIGRATION_TRANSACTIONS,
    MigrationBudget,
)
from .selection_publication_state import (
    STORAGE_SCHEMA_VERSION,
    compile_state,
    write_compiled_state,
)
from .selection_publication_store import (
    SHA256,
    _canonical_json,
    _intent_index_path,
    _lock,
    _migration_path,
    _receipt_path,
    _sha256_bytes,
    _sha256_file,
    _state_path,
    _write_once,
)
from .selection_publication_gc_fs import (
    replace_relative,
)
from .selection_publication_migration_journal import (
    archive_completed_generation,
    migration_binding,
    validate_migration_visibility,
)
from .selection_publication_producer_capability import (
    _SELECTION_PUBLICATION_PRODUCER_CAPABILITY,
)


def _migration_hook(stage: str, path: Path) -> None:
    """Test seam for crash/recovery ordering."""

    _ = stage, path


def _index_rows(
    root: Path,
    transaction_ids: list[str],
    *,
    load_prepare: Callable[[Path, str], tuple[dict[str, Any], Path, str]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for transaction_id in transaction_ids:
        prepare, prepare_path, prepare_sha = load_prepare(root, transaction_id)
        intent_sha256 = prepare.get("intent_sha256")
        if not isinstance(intent_sha256, str):
            continue
        if not SHA256.fullmatch(intent_sha256):
            raise ValueError("legacy selection publication intent digest is invalid")
        prepare_value = prepare_index_value(
            root,
            intent_sha256,
            transaction_id,
            prepare_path,
            prepare_sha,
        )
        prepare_index_path = _intent_index_path(root, intent_sha256, "prepare")
        row: dict[str, Any] = {
            "intent_sha256": intent_sha256,
            "transaction_id": transaction_id,
            "prepare_index": migration_binding(
                root,
                prepare_index_path,
                _sha256_bytes(_canonical_json(prepare_value)),
            ),
            "commit_index": None,
        }
        receipt_path = _receipt_path(root, transaction_id)
        receipt_sha = _sha256_file(receipt_path)
        if receipt_sha is not None:
            commit_value = commit_index_value(
                root,
                intent_sha256,
                transaction_id,
                prepare_path,
                prepare_sha,
                receipt_path,
                receipt_sha,
            )
            row["commit_index"] = migration_binding(
                root,
                _intent_index_path(root, intent_sha256, "commit"),
                _sha256_bytes(_canonical_json(commit_value)),
            )
        rows.append(row)
    if len({row["intent_sha256"] for row in rows}) != len(rows):
        raise ValueError(
            "legacy selection publication contains duplicate intent identities"
        )
    return sorted(rows, key=lambda row: row["intent_sha256"])


def _transaction_inventory(
    root: Path,
    transaction_ids: list[str],
    *,
    budget: MigrationBudget,
    load_prepare: Callable[[Path, str], tuple[dict[str, Any], Path, str]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for transaction_id in transaction_ids:
        _prepare, prepare_path, prepare_sha = load_prepare(root, transaction_id)
        budget.consume_path(
            prepare_path, "legacy selection publication prepare inventory"
        )
        receipt_path = _receipt_path(root, transaction_id)
        receipt_sha = _sha256_file(receipt_path)
        if receipt_sha is not None:
            budget.consume_path(
                receipt_path, "legacy selection publication receipt inventory"
            )
        rows.append(
            {
                "transaction_id": transaction_id,
                "prepare": migration_binding(root, prepare_path, prepare_sha),
                "receipt": (
                    migration_binding(root, receipt_path, receipt_sha)
                    if receipt_sha is not None
                    else None
                ),
            }
        )
    return rows


def _write_indexes(
    root: Path,
    transaction_ids: list[str],
    *,
    load_prepare: Callable[[Path, str], tuple[dict[str, Any], Path, str]],
) -> None:
    for transaction_id in transaction_ids:
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


def _completed_result(
    root: Path, state_path: Path, complete_path: Path
) -> dict[str, Any] | None:
    if not complete_path.is_file() or not state_path.is_file():
        return None
    try:
        state_payload = state_path.read_bytes()
        state = json.loads(state_payload)
        if state_payload != _canonical_json(state):
            return None
        complete = validate_migration_visibility(root, state)
    except (OSError, UnicodeDecodeError, ValueError, json.JSONDecodeError):
        return None
    if complete is None:
        return None
    current_state_binding = migration_binding(
        root,
        state_path,
        _sha256_bytes(state_payload),
    )
    if complete.get("state") != current_state_binding:
        return None
    return {
        "status": "migrated",
        "storage_schema_version": STORAGE_SCHEMA_VERSION,
        "receipt_count": complete["receipt_count"],
        "pending_count": complete["pending_count"],
        "state_ref": state_path.relative_to(root).as_posix(),
        "state_content_sha256": state["state_content_sha256"],
        "migration_completion": migration_binding(
            root, complete_path, str(_sha256_file(complete_path))
        ),
        "idempotent_replay": True,
        "mutation_performed": False,
    }


def _compile_assets(
    root: Path,
    *,
    committed_receipts: Callable[..., list[dict[str, Any]]],
    deep_pending_ids: Callable[..., list[str]],
    load_prepare: Callable[[Path, str], tuple[dict[str, Any], Path, str]],
) -> dict[str, Any]:
    budget = MigrationBudget()
    receipts = committed_receipts(root, budget=budget)
    pending = deep_pending_ids(root, budget=budget)
    transaction_ids = [
        *(str(row["transaction_id"]) for row in receipts),
        *pending,
    ]
    if len(transaction_ids) > MAX_MIGRATION_TRANSACTIONS:
        raise ValueError(
            "selection-publication migration exceeds transaction-count bound"
        )
    if len(set(transaction_ids)) != len(transaction_ids):
        raise ValueError(
            "selection-publication migration transaction inventory overlaps"
        )
    state = compile_state(root, receipts, pending, load_prepare=load_prepare)
    state_path = root / ".task/selection_publication/state.json"
    state_binding = migration_binding(
        root, state_path, _sha256_bytes(_canonical_json(state))
    )
    transactions = _transaction_inventory(
        root, transaction_ids, budget=budget, load_prepare=load_prepare
    )
    index_rows = _index_rows(root, transaction_ids, load_prepare=load_prepare)
    inventory = {
        "receipt_count": len(receipts),
        "pending_count": len(pending),
        "transactions": transactions,
        "entry_count": budget.entries,
        "bytes_read": budget.bytes_read,
    }
    prepare_body = {
        "schema_version": 1,
        "kind": "selection_publication_storage_v4_migration_prepare",
        "storage_schema_version": STORAGE_SCHEMA_VERSION,
        "inventory": inventory,
        "intent_indexes": index_rows,
        "state": state_binding,
        "limits": {
            "max_transactions": MAX_MIGRATION_TRANSACTIONS,
            "max_journal_bytes": MAX_MIGRATION_JOURNAL_BYTES,
        },
    }
    prepare = {
        **prepare_body,
        "prepare_content_sha256": _sha256_bytes(_canonical_json(prepare_body)),
    }
    prepare_payload = _canonical_json(prepare)
    if len(prepare_payload) > MAX_MIGRATION_JOURNAL_BYTES:
        raise ValueError(
            "selection-publication migration prepare exceeds journal bound"
        )
    return {
        "receipts": receipts,
        "pending": pending,
        "transaction_ids": transaction_ids,
        "state": state,
        "state_path": state_path,
        "state_binding": state_binding,
        "index_rows": index_rows,
        "prepare_payload": prepare_payload,
    }


def _publish_assets(
    root: Path,
    assets: dict[str, Any],
    *,
    complete_path: Path,
    load_prepare: Callable[[Path, str], tuple[dict[str, Any], Path, str]],
) -> str:
    prepare_payload = assets["prepare_payload"]
    prepare_path = _migration_path(root, "prepare")
    prepare_sha = _sha256_bytes(prepare_payload)
    if _sha256_file(prepare_path) != prepare_sha:
        archive_completed_generation(root, prepare_path, complete_path)
        prepare_sha, _changed = replace_relative(
            root,
            prepare_path.relative_to(root).as_posix(),
            prepare_payload,
            "selection-publication migration prepare",
            producer_capability=_SELECTION_PUBLICATION_PRODUCER_CAPABILITY,
        )
    else:
        _write_once(
            prepare_path,
            prepare_payload,
            "selection-publication migration prepare",
            producer_capability=_SELECTION_PUBLICATION_PRODUCER_CAPABILITY,
        )
    _migration_hook("after_prepare", prepare_path)
    _write_indexes(root, assets["transaction_ids"], load_prepare=load_prepare)
    _migration_hook("after_indexes", prepare_path)
    write_compiled_state(root, assets["state"])
    _migration_hook("after_state", assets["state_path"])
    complete_body = {
        "schema_version": 1,
        "kind": "selection_publication_storage_v4_migration_complete",
        "storage_schema_version": STORAGE_SCHEMA_VERSION,
        "migration_prepare": migration_binding(root, prepare_path, prepare_sha),
        "state": assets["state_binding"],
        "receipt_count": len(assets["receipts"]),
        "pending_count": len(assets["pending"]),
        "intent_index_count": len(assets["index_rows"]),
        "visibility_rule": "indexes_then_state_then_completion_receipt",
    }
    complete = {
        **complete_body,
        "completion_content_sha256": _sha256_bytes(_canonical_json(complete_body)),
    }
    complete_payload = _canonical_json(complete)
    expected_complete_sha = _sha256_bytes(complete_payload)
    if _sha256_file(complete_path) != expected_complete_sha:
        complete_sha, _changed = replace_relative(
            root,
            complete_path.relative_to(root).as_posix(),
            complete_payload,
            "selection-publication migration completion",
            producer_capability=_SELECTION_PUBLICATION_PRODUCER_CAPABILITY,
        )
    else:
        complete_sha = _write_once(
            complete_path,
            complete_payload,
            "selection-publication migration completion",
            producer_capability=_SELECTION_PUBLICATION_PRODUCER_CAPABILITY,
        )
    _migration_hook("after_completion", complete_path)
    return complete_sha


def migrate_publication_state(
    root: Path,
    *,
    committed_receipts: Callable[..., list[dict[str, Any]]],
    deep_pending_ids: Callable[..., list[str]],
    load_prepare: Callable[[Path, str], tuple[dict[str, Any], Path, str]],
) -> dict[str, Any]:
    """Audit bounded history and publish state only after all lookup indexes."""

    root = root.expanduser().resolve(strict=True)
    with _lock(
        root,
        producer_capability=_SELECTION_PUBLICATION_PRODUCER_CAPABILITY,
    ):
        complete_path = _migration_path(root, "complete")
        state_path = _state_path(root)
        completed = _completed_result(root, state_path, complete_path)
        if completed is not None:
            return completed
        assets = _compile_assets(
            root,
            committed_receipts=committed_receipts,
            deep_pending_ids=deep_pending_ids,
            load_prepare=load_prepare,
        )
        complete_sha = _publish_assets(
            root,
            assets,
            complete_path=complete_path,
            load_prepare=load_prepare,
        )
    return {
        "status": "migrated",
        "storage_schema_version": STORAGE_SCHEMA_VERSION,
        "receipt_count": len(assets["receipts"]),
        "pending_count": len(assets["pending"]),
        "state_ref": assets["state_path"].relative_to(root).as_posix(),
        "state_content_sha256": assets["state"]["state_content_sha256"],
        "migration_completion": migration_binding(root, complete_path, complete_sha),
        "idempotent_replay": False,
        "mutation_performed": True,
    }


__all__ = (
    "migrate_publication_state",
    "validate_migration_visibility",
)
