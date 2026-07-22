"""Recovery and status projections for selection-publication journals."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .selection_publication_state import load_state, status_from_state
from .selection_publication_status import current_head_status
from .selection_publication_store import (
    _receipt_path,
    _sha256_file,
)
from .selection_publication_v2 import validate_external_settlement_assertion


def recover_publications(
    root: Path, transaction_id: str | None = None
) -> dict[str, Any]:
    from .selection_publication import pending_transaction_ids, publish_prepared

    root = root.expanduser().resolve(strict=True)
    identifiers = [transaction_id] if transaction_id else pending_transaction_ids(root)
    if transaction_id is None and len(identifiers) > 1:
        raise ValueError(
            "selection-publication has competing pending transactions; "
            "automatic recovery cannot choose an authoritative selection"
        )
    receipts = [publish_prepared(root, item) for item in identifiers]
    return {
        "status": "recovered" if receipts else "no_op",
        "recovered_count": len(receipts),
        "receipts": receipts,
        "remaining_pending_transaction_ids": pending_transaction_ids(root),
        "mutation_performed": bool(receipts),
    }


def _load_receipt(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("selection-publication receipt is unreadable") from exc
    if not isinstance(value, dict):
        raise ValueError("selection-publication receipt must be an object")
    return value


def _apply_external_settlement_gate(
    root: Path, status: dict[str, Any]
) -> dict[str, Any]:
    head = status.get("current_head")
    if not isinstance(head, dict) or head.get("status") != "current":
        return status
    transaction_id = head.get("head_transaction_id")
    if not isinstance(transaction_id, str):
        return status
    receipt_path = _receipt_path(root, transaction_id)
    try:
        receipt = _load_receipt(receipt_path)
    except ValueError:
        return status
    if receipt.get("schema_version") != 3:
        return status
    binding = {
        "ref": receipt_path.relative_to(root).as_posix(),
        "sha256": _sha256_file(receipt_path),
    }
    try:
        validate_external_settlement_assertion(root, receipt, binding)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        missing = "missing" in str(exc)
        return {
            **status,
            "status": "settlement_required" if missing else "settlement_conflict",
            "selection_consumption_allowed": False,
            "selection_consumption_reason": (
                "task_state_external_settlement_required"
                if missing
                else "task_state_external_settlement_conflict"
            ),
        }
    return status


def publication_status(root: Path, *, deep: bool = False) -> dict[str, Any]:
    from .selection_publication import _committed_receipts, pending_transaction_ids

    root = root.expanduser().resolve(strict=True)
    if not deep:
        state = load_state(root)
        if state is not None:
            return _apply_external_settlement_gate(root, status_from_state(root, state))
    pending = pending_transaction_ids(root)
    head = current_head_status(
        _committed_receipts(root), _sha256_file(root / "task.md")
    )
    status = (
        "recovery_required"
        if pending
        else "drift_blocked"
        if head["status"] in {"drifted", "ambiguous"}
        else "clear"
    )
    initialized = head["status"] != "not_initialized"
    return _apply_external_settlement_gate(
        root,
        {
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
        },
    )


__all__ = ("publication_status", "recover_publications")
