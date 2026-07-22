"""Bounded head/pending projection for selection publication storage v4."""

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
    _sha256_bytes,
    _sha256_file,
    _state_path,
)


STORAGE_SCHEMA_VERSION = 4
STATE_SCHEMA_VERSION = 2
STATE_KEYS = {
    "schema_version",
    "storage_schema_version",
    "kind",
    "head",
    "active_transaction",
    "state_content_sha256",
}
RECORD_KEYS = {
    "transaction_id",
    "prepare",
    "receipt",
    "predecessor_transaction_id",
    "task_alias_before_sha256",
    "task_alias_after_sha256",
    "intent_sha256",
}
BINDING_KEYS = {"ref", "sha256"}


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is unreadable") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def _target(value: dict[str, Any]) -> dict[str, Any]:
    rows = [
        row
        for row in value.get("targets", [])
        if isinstance(row, dict) and row.get("role") == "task_alias"
    ]
    if len(rows) != 1:
        raise ValueError("selection publication evidence requires one task_alias")
    return rows[0]


def _binding(root: Path, path: Path, digest: str | None = None) -> dict[str, str]:
    actual = digest if digest is not None else _sha256_file(path)
    if actual is None:
        raise ValueError("selection publication state evidence is missing")
    return {"ref": path.relative_to(root).as_posix(), "sha256": actual}


def _record(
    root: Path,
    prepare: dict[str, Any],
    *,
    prepare_sha256: str | None = None,
    receipt_sha256: str | None = None,
) -> dict[str, Any]:
    transaction_id = str(prepare.get("transaction_id") or "")
    if not TRANSACTION_ID.fullmatch(transaction_id):
        raise ValueError("selection publication state transaction is invalid")
    target = _target(prepare)
    prepare_path = _prepare_path(root, transaction_id)
    receipt_path = _receipt_path(root, transaction_id)
    return {
        "transaction_id": transaction_id,
        "prepare": _binding(root, prepare_path, prepare_sha256),
        "receipt": (
            _binding(root, receipt_path, receipt_sha256)
            if receipt_sha256 is not None or receipt_path.is_file()
            else None
        ),
        "predecessor_transaction_id": prepare.get("predecessor_transaction_id"),
        "task_alias_before_sha256": target.get("before_sha256"),
        "task_alias_after_sha256": target.get("after_sha256"),
        "intent_sha256": prepare.get("intent_sha256"),
    }


def _write(root: Path, *, head: Any, active: Any) -> dict[str, Any]:
    body = {
        "schema_version": STATE_SCHEMA_VERSION,
        "storage_schema_version": STORAGE_SCHEMA_VERSION,
        "kind": "selection_publication_state",
        "head": head,
        "active_transaction": active,
    }
    state = {**body, "state_content_sha256": _sha256_bytes(_canonical_json(body))}
    _atomic_write(_state_path(root), _canonical_json(state))
    return state


def write_empty_state(root: Path) -> dict[str, Any]:
    return _write(root, head=None, active=None)


def _validate_binding(root: Path, value: Any, expected: Path, label: str) -> None:
    if not isinstance(value, dict) or set(value) != BINDING_KEYS:
        raise ValueError(f"{label} binding is invalid")
    if (
        value.get("ref") != expected.relative_to(root).as_posix()
        or _sha256_file(expected) != value.get("sha256")
    ):
        raise ValueError(f"{label} binding has drifted")


def _validate_record(root: Path, value: Any, *, committed: bool) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != RECORD_KEYS:
        raise ValueError("selection publication compact state record is invalid")
    transaction_id = value.get("transaction_id")
    if not isinstance(transaction_id, str) or not TRANSACTION_ID.fullmatch(transaction_id):
        raise ValueError("selection publication compact state transaction is invalid")
    _validate_binding(
        root,
        value.get("prepare"),
        _prepare_path(root, transaction_id),
        "selection publication prepare",
    )
    if committed:
        _validate_binding(
            root,
            value.get("receipt"),
            _receipt_path(root, transaction_id),
            "selection publication receipt",
        )
    # Reopen the complete owner contracts through their closed validators. This
    # remains O(1): one exact prepare and, for a head, one exact receipt.
    from .selection_publication import _load_prepare
    from .selection_publication_receipt import validate_receipt

    prepare, _prepare_file, prepare_sha = _load_prepare(root, transaction_id)
    if committed:
        verified = validate_receipt(
            root,
            transaction_id,
            require_current_targets=False,
            verify_external_binding=False,
            load_prepare=lambda _root, _transaction_id: (
                prepare,
                _prepare_file,
                prepare_sha,
            ),
        )
        expected = _record(
            root,
            prepare,
            prepare_sha256=prepare_sha,
            receipt_sha256=str(verified["receipt_sha256"]),
        )
    else:
        expected = _record(root, prepare, prepare_sha256=prepare_sha)
        # A receipt may already exist after a crash; the still-active record is
        # the legal recovery checkpoint and intentionally keeps receipt null.
        expected["receipt"] = None
    if value != expected:
        label = "head" if committed else "active"
        raise ValueError(f"selection publication bounded {label} projection differs")
    return value


def load_state(root: Path) -> dict[str, Any] | None:
    """Open a constant number of files; never enumerate journal history."""

    path = _state_path(root)
    if not path.exists():
        return None
    state = _read_json(path, "selection publication compact state")
    if path.is_symlink() or path.read_bytes() != _canonical_json(state):
        raise ValueError("selection publication compact state is non-canonical")
    if state.get("schema_version") == 1:
        raise ValueError("selection publication state migration required")
    if set(state) != STATE_KEYS:
        raise ValueError("selection publication compact state fields are invalid")
    body = {key: value for key, value in state.items() if key != "state_content_sha256"}
    if (
        state.get("schema_version") != STATE_SCHEMA_VERSION
        or state.get("storage_schema_version") != STORAGE_SCHEMA_VERSION
        or state.get("kind") != "selection_publication_state"
        or state.get("state_content_sha256") != _sha256_bytes(_canonical_json(body))
    ):
        raise ValueError("selection publication compact state integrity failed")
    head = state.get("head")
    active = state.get("active_transaction")
    if head is not None:
        _validate_record(root, head, committed=True)
    if active is not None:
        _validate_record(root, active, committed=False)
    if head is not None and active is not None:
        if active.get("transaction_id") == head.get("transaction_id"):
            raise ValueError("selection publication head and active transaction collide")
        if active.get("predecessor_transaction_id") != head.get("transaction_id"):
            raise ValueError("selection publication active predecessor differs from head")
    return state


def record_prepared(
    root: Path,
    state: dict[str, Any],
    prepare: dict[str, Any],
    prepare_sha256: str,
) -> dict[str, Any]:
    active = _record(root, prepare, prepare_sha256=prepare_sha256)
    existing = state.get("active_transaction")
    if existing is not None and existing != active:
        raise ValueError("selection publication already has another active transaction")
    return _write(root, head=state.get("head"), active=active)


def record_committed(
    root: Path,
    state: dict[str, Any],
    prepare: dict[str, Any],
    prepare_sha256: str,
    receipt_sha256: str,
) -> dict[str, Any]:
    head = _record(
        root,
        prepare,
        prepare_sha256=prepare_sha256,
        receipt_sha256=receipt_sha256,
    )
    active = state.get("active_transaction")
    if active is not None and active.get("transaction_id") != head["transaction_id"]:
        raise ValueError("selection publication commit differs from active transaction")
    existing_head = state.get("head")
    if active is None and existing_head != head:
        raise ValueError(
            "selection publication commit is neither the active transaction nor the current head"
        )
    return _write(root, head=head, active=None)


def write_state(
    root: Path,
    receipts: Sequence[dict[str, Any]],
    pending_transaction_ids: Sequence[str],
    *,
    load_prepare: Any,
) -> dict[str, Any]:
    """Deep-history migration entry point; normal operations use record_* above."""

    if len(pending_transaction_ids) > 1:
        raise ValueError(
            "legacy selection publication has multiple pending transactions; recover one explicitly before migration"
        )
    head_record = None
    if receipts:
        head = current_head_status(receipts, _sha256_file(root / "task.md"))
        transaction_id = head.get("head_transaction_id")
        if not isinstance(transaction_id, str):
            raise ValueError(
                "legacy selection publication history has no unique head; repair it before migration"
            )
        prepare, _path, digest = load_prepare(root, transaction_id)
        receipt = next(row for row in receipts if row["transaction_id"] == transaction_id)
        head_record = _record(
            root,
            prepare,
            prepare_sha256=digest,
            receipt_sha256=receipt["receipt_sha256"],
        )
    active_record = None
    if pending_transaction_ids:
        prepare, _path, digest = load_prepare(root, pending_transaction_ids[0])
        active_record = _record(root, prepare, prepare_sha256=digest)
        expected = head_record["transaction_id"] if head_record is not None else None
        if prepare.get("predecessor_transaction_id") != expected:
            raise ValueError("legacy pending selection does not extend the unique head")
    return _write(root, head=head_record, active=active_record)


def head_receipts(state: dict[str, Any]) -> list[dict[str, Any]]:
    head = state.get("head")
    if not isinstance(head, dict):
        return []
    receipt = {
        "transaction_id": head["transaction_id"],
        "targets": [
            {
                "role": "task_alias",
                "before_sha256": head["task_alias_before_sha256"],
                "after_sha256": head["task_alias_after_sha256"],
            }
        ],
    }
    return [receipt]


def status_from_state(root: Path, state: dict[str, Any]) -> dict[str, Any]:
    head = state.get("head")
    if head is None:
        head_status = {
            "status": "not_initialized",
            "head_transaction_id": None,
            "head_count": 0,
            "lineage_mode": "uninitialized",
        }
    else:
        current = _sha256_file(root / "task.md")
        expected = head["task_alias_after_sha256"]
        head_status = {
            "status": "current" if current == expected else "drifted",
            "head_transaction_id": head["transaction_id"],
            "head_count": 1,
            "expected_task_sha256": expected,
            "current_task_sha256": current,
            "lineage_mode": "explicit",
        }
    active = state.get("active_transaction")
    status = (
        "recovery_required"
        if active is not None
        else "drift_blocked"
        if head_status["status"] == "drifted"
        else "clear"
    )
    initialized = head is not None
    return {
        "status": status,
        "pending_transaction_ids": (
            [active["transaction_id"]] if isinstance(active, dict) else []
        ),
        "selection_journal_initialized": initialized,
        "selection_consumption_allowed": status == "clear" and initialized,
        "selection_consumption_reason": (
            "committed_unique_current_head"
            if status == "clear" and initialized
            else "no_committed_selection"
            if not initialized
            else "publication_recovery_or_drift_repair_required"
        ),
        "current_head": head_status,
        "mutation_performed": False,
    }


__all__ = (
    "STORAGE_SCHEMA_VERSION",
    "head_receipts",
    "load_state",
    "record_committed",
    "record_prepared",
    "status_from_state",
    "write_empty_state",
    "write_state",
)
