"""Compact status projection for validated selection-publication history."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Sequence

from .selection_publication_status import current_head_status
from .selection_publication_store import (
    TRANSACTION_ID,
    _atomic_write,
    _canonical_json,
    _prepare_path,
    _receipt_path,
    _receipts_root,
    _sha256_bytes,
    _sha256_file,
    _state_path,
    _transactions_root,
)


STATE_KEYS = {
    "schema_version",
    "kind",
    "receipts",
    "pending_transaction_ids",
    "state_content_sha256",
}
RECORD_KEYS = {
    "transaction_id",
    "receipt_ref",
    "receipt_sha256",
    "prepare_ref",
    "prepare_sha256",
    "predecessor_present",
    "predecessor_transaction_id",
    "task_alias_before_sha256",
    "task_alias_after_sha256",
}


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is unreadable") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def _target(receipt: dict[str, Any]) -> dict[str, Any]:
    rows = [
        row
        for row in receipt.get("targets", [])
        if isinstance(row, dict) and row.get("role") == "task_alias"
    ]
    if len(rows) != 1:
        raise ValueError("selection publication receipt requires one task_alias")
    return rows[0]


def _record(receipt: dict[str, Any]) -> dict[str, Any]:
    target = _target(receipt)
    return {
        "transaction_id": receipt["transaction_id"],
        "receipt_ref": receipt["receipt_ref"],
        "receipt_sha256": receipt["receipt_sha256"],
        "prepare_ref": receipt["prepare_ref"],
        "prepare_sha256": receipt["prepare_sha256"],
        "predecessor_present": "predecessor_transaction_id" in receipt,
        "predecessor_transaction_id": receipt.get("predecessor_transaction_id"),
        "task_alias_before_sha256": target.get("before_sha256"),
        "task_alias_after_sha256": target["after_sha256"],
    }


def write_state(
    root: Path,
    receipts: Sequence[dict[str, Any]],
    pending_transaction_ids: Sequence[str],
) -> dict[str, Any]:
    records = sorted((_record(receipt) for receipt in receipts), key=lambda row: row["transaction_id"])
    body = {
        "schema_version": 1,
        "kind": "selection_publication_state",
        "receipts": records,
        "pending_transaction_ids": sorted(pending_transaction_ids),
    }
    state = {**body, "state_content_sha256": _sha256_bytes(_canonical_json(body))}
    path = _state_path(root)
    _atomic_write(path, _canonical_json(state))
    return state


def _actual_ids(root: Path) -> tuple[list[str], list[str]]:
    transactions_root = _transactions_root(root)
    transaction_ids = sorted(
        child.name
        for child in transactions_root.iterdir()
        if child.is_dir()
        and not child.is_symlink()
        and TRANSACTION_ID.fullmatch(child.name)
        and (child / "prepare.json").is_file()
        and not (child / "prepare.json").is_symlink()
    ) if transactions_root.is_dir() else []
    receipts_root = _receipts_root(root)
    receipt_ids = sorted(
        path.stem
        for path in receipts_root.glob("selection-*.json")
        if path.is_file()
        and not path.is_symlink()
        and TRANSACTION_ID.fullmatch(path.stem)
    ) if receipts_root.is_dir() else []
    return transaction_ids, receipt_ids


def load_state(root: Path) -> dict[str, Any] | None:
    """Validate a compact state without decoding any historical prepare body."""

    path = _state_path(root)
    if not path.exists():
        return None
    state = _read_json(path, "selection publication compact state")
    if set(state) != STATE_KEYS:
        raise ValueError("selection publication compact state fields are invalid")
    body = {key: value for key, value in state.items() if key != "state_content_sha256"}
    if (
        state.get("schema_version") != 1
        or state.get("kind") != "selection_publication_state"
        or state.get("state_content_sha256") != _sha256_bytes(_canonical_json(body))
    ):
        raise ValueError("selection publication compact state integrity failed")
    records = state.get("receipts")
    pending = state.get("pending_transaction_ids")
    if not isinstance(records, list) or not isinstance(pending, list):
        raise ValueError("selection publication compact state lists are invalid")
    transaction_ids, receipt_ids = _actual_ids(root)
    record_ids: list[str] = []
    for record in records:
        if not isinstance(record, dict) or set(record) != RECORD_KEYS:
            raise ValueError("selection publication compact state record is invalid")
        transaction_id = record.get("transaction_id")
        if not isinstance(transaction_id, str) or not TRANSACTION_ID.fullmatch(transaction_id):
            raise ValueError("selection publication compact state transaction is invalid")
        receipt_path = _receipt_path(root, transaction_id)
        prepare_path = _prepare_path(root, transaction_id)
        if (
            record.get("receipt_ref") != receipt_path.relative_to(root).as_posix()
            or record.get("prepare_ref") != prepare_path.relative_to(root).as_posix()
            or _sha256_file(receipt_path) != record.get("receipt_sha256")
            or not prepare_path.is_file()
            or prepare_path.is_symlink()
        ):
            raise ValueError("selection publication compact state binding has drifted")
        receipt = _read_json(receipt_path, "selection publication compact receipt")
        target = _target(receipt)
        if (
            receipt.get("transaction_id") != transaction_id
            or receipt.get("status") != "committed"
            or receipt.get("prepare_ref") != record["prepare_ref"]
            or receipt.get("prepare_sha256") != record["prepare_sha256"]
            or ("predecessor_transaction_id" in receipt)
            != record["predecessor_present"]
            or receipt.get("predecessor_transaction_id")
            != record["predecessor_transaction_id"]
            or target.get("before_sha256") != record["task_alias_before_sha256"]
            or target.get("after_sha256") != record["task_alias_after_sha256"]
        ):
            raise ValueError("selection publication compact receipt projection differs")
        record_ids.append(transaction_id)
    if (
        len(record_ids) != len(set(record_ids))
        or sorted(record_ids) != receipt_ids
        or any(not isinstance(item, str) for item in pending)
        or sorted(pending) != sorted(set(transaction_ids) - set(receipt_ids))
    ):
        raise ValueError("selection publication compact state is stale")
    return state


def status_from_state(root: Path, state: dict[str, Any]) -> dict[str, Any]:
    receipts = []
    for record in state["receipts"]:
        receipt = {
            "transaction_id": record["transaction_id"],
            "targets": [
                {
                    "role": "task_alias",
                    "before_sha256": record["task_alias_before_sha256"],
                    "after_sha256": record["task_alias_after_sha256"],
                }
            ],
        }
        if record["predecessor_present"]:
            receipt["predecessor_transaction_id"] = record[
                "predecessor_transaction_id"
            ]
        receipts.append(receipt)
    pending = list(state["pending_transaction_ids"])
    head = current_head_status(receipts, _sha256_file(root / "task.md"))
    status = (
        "recovery_required"
        if pending
        else "drift_blocked"
        if head["status"] in {"drifted", "ambiguous"}
        else "clear"
    )
    initialized = head["status"] != "not_initialized"
    return {
        "status": status,
        "pending_transaction_ids": pending,
        "selection_journal_initialized": initialized,
        "selection_consumption_allowed": status == "clear" and initialized,
        "selection_consumption_reason": (
            "committed_unique_current_head"
            if status == "clear" and initialized
            else "no_committed_selection"
            if not initialized
            else "publication_recovery_or_drift_repair_required"
        ),
        "current_head": head,
        "mutation_performed": False,
    }


__all__ = ("load_state", "status_from_state", "write_state")
