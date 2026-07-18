"""Forward-recoverable publication of one canonical task selection.

The helper owns no task-selection policy.  It only publishes caller-prepared
workflow projections with exact before/after digests, writes the authoritative
``task.md`` pointer last, and withholds a committed receipt until every target
matches its prepared after-state.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .selection_publication_prepare import (
    committed_replay,
    new_predecessor_transaction_id,
    pending_replay,
    prepare_response,
    validate_publish_predecessor,
)
from .selection_publication_plan import (
    MAX_TARGET_BYTES as MAX_TARGET_BYTES,
    MAX_TOTAL_BYTES as MAX_TOTAL_BYTES,
    OPAQUE_ID as OPAQUE_ID,
    OWNER_COMMITTED_PROJECTION_ROLES as OWNER_COMMITTED_PROJECTION_ROLES,
    ROLE_PRIORITY as ROLE_PRIORITY,
    SCHEMA_VERSION,
    SHA256 as SHA256,
    _decode_payload,
    _normalize_plan,
    _role_path_allowed as _role_path_allowed,
    _target_path,
)
from .selection_publication_status import current_head_status
from .selection_publication_store import (
    TRANSACTION_ID,
    _atomic_write,
    _canonical_json,
    _display_json,
    _lock,
    _prepare_path,
    _receipts_root,
    _receipt_path,
    _sha256_bytes,
    _sha256_file,
    _transactions_root,
    _write_once,
)


def _load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is unreadable") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def _load_prepare(root: Path, transaction_id: str) -> tuple[dict[str, Any], Path, str]:
    path = _prepare_path(root, transaction_id)
    prepare = _load_json(path, "selection-publication prepare journal")
    if prepare.get("transaction_id") != transaction_id:
        raise ValueError("selection-publication prepare transaction id is inconsistent")
    plan_material = {
        key: value
        for key, value in prepare.items()
        if key not in {"transaction_id", "predecessor_transaction_id"}
    }
    plan_material["kind"] = "selection_publication_plan"
    normalized = _normalize_plan(root, plan_material)
    if "predecessor_transaction_id" in prepare:
        predecessor = prepare.get("predecessor_transaction_id")
        if predecessor is not None and not TRANSACTION_ID.fullmatch(str(predecessor)):
            raise ValueError("selection-publication predecessor transaction is invalid")
        if predecessor == transaction_id:
            raise ValueError("selection-publication transaction cannot precede itself")
        normalized["predecessor_transaction_id"] = predecessor
    normalized["transaction_id"] = transaction_id
    if prepare != normalized:
        raise ValueError("selection-publication prepare journal is non-canonical")
    transaction_material = {
        key: value for key, value in normalized.items() if key != "transaction_id"
    }
    expected_id = "selection-" + _sha256_bytes(_canonical_json(transaction_material))
    if expected_id != transaction_id:
        raise ValueError("selection-publication prepare journal binding is invalid")
    digest = _sha256_file(path)
    assert digest is not None
    return prepare, path, digest


def prepare_publication(root: Path, plan: dict[str, Any]) -> dict[str, Any]:
    root = root.expanduser().resolve(strict=True)
    normalized = _normalize_plan(root, plan)
    with _lock(root):
        replay = pending_replay(
            root,
            normalized,
            pending_transaction_ids(root),
            load_prepare=_load_prepare,
        )
        if replay is not None:
            return replay
        receipts = _committed_receipts(root)
        replay = committed_replay(
            root, normalized, receipts, load_prepare=_load_prepare
        )
        if replay is not None:
            return replay
        predecessor = new_predecessor_transaction_id(
            normalized, receipts, _sha256_file(root / "task.md")
        )
        transaction_material = {
            **normalized,
            "predecessor_transaction_id": predecessor,
        }
        transaction_id = "selection-" + _sha256_bytes(
            _canonical_json(transaction_material)
        )
        prepare = {**transaction_material, "transaction_id": transaction_id}
        path = _prepare_path(root, transaction_id)
        digest = _write_once(
            path, _display_json(prepare), "selection-publication prepare journal"
        )
        _load_prepare(root, transaction_id)
    return prepare_response(
        root,
        transaction_id,
        path,
        digest,
        status="prepared",
        mutation_performed=True,
        recovery_required=True,
    )


def validate_receipt(
    root: Path, transaction_id: str, *, require_current_targets: bool = False
) -> dict[str, Any]:
    root = root.expanduser().resolve(strict=True)
    prepare, prepare_path, prepare_sha = _load_prepare(root, transaction_id)
    path = _receipt_path(root, transaction_id)
    receipt = _load_json(path, "selection-publication receipt")
    expected_targets = [
        {
            key: target.get(key)
            for key in ("role", "target_ref", "before_sha256", "after_sha256")
        }
        for target in prepare["targets"]
    ]
    lineage_matches = ("predecessor_transaction_id" in prepare) == (
        "predecessor_transaction_id" in receipt
    ) and receipt.get("predecessor_transaction_id") == prepare.get(
        "predecessor_transaction_id"
    )
    if (
        receipt.get("schema_version") != SCHEMA_VERSION
        or receipt.get("kind") != "selection_publication_receipt"
        or receipt.get("status") != "committed"
        or receipt.get("transaction_id") != transaction_id
        or receipt.get("selection_id") != prepare.get("selection_id")
        or receipt.get("source_decision_id") != prepare.get("source_decision_id")
        or receipt.get("source_decision_sha256")
        != prepare.get("source_decision_sha256")
        or receipt.get("prepare_ref") != prepare_path.relative_to(root).as_posix()
        or receipt.get("prepare_sha256") != prepare_sha
        or receipt.get("targets") != expected_targets
        or receipt.get("authoritative_pointer_role") != "task_alias"
        or not lineage_matches
    ):
        raise ValueError("selection-publication receipt contract is invalid")
    if require_current_targets:
        for target in prepare["targets"]:
            if (
                _sha256_file(_target_path(root, target["role"], target["target_ref"]))
                != target["after_sha256"]
            ):
                raise ValueError("selection-publication committed target has drifted")
    receipt_sha = _sha256_file(path)
    assert receipt_sha is not None
    return {
        **receipt,
        "receipt_ref": path.relative_to(root).as_posix(),
        "receipt_sha256": receipt_sha,
    }


def _historical_receipt_response(root: Path, transaction_id: str) -> dict[str, Any]:
    verified = validate_receipt(root, transaction_id, require_current_targets=False)
    return {
        **verified,
        "mutation_performed": False,
        "authoritative_selection_published": False,
        "current_selection_authority_claimed": False,
        "publication_authority_status": "historical_receipt_only",
        "recovery_required": False,
    }


def publish_prepared(root: Path, transaction_id: str) -> dict[str, Any]:
    root = root.expanduser().resolve(strict=True)
    with _lock(root):
        receipt_path = _receipt_path(root, transaction_id)
        if receipt_path.is_file():
            return _historical_receipt_response(root, transaction_id)
        _reject_competing_pending(root, transaction_id)
        prepare, prepare_path, prepare_sha = _load_prepare(root, transaction_id)
        validate_publish_predecessor(
            prepare,
            _committed_receipts(root),
            _sha256_file(root / "task.md"),
        )
        targets = list(prepare["targets"])
        for target in targets:
            current = _sha256_file(
                _target_path(root, target["role"], target["target_ref"])
            )
            if current not in {target.get("before_sha256"), target["after_sha256"]}:
                raise ValueError(
                    f"selection-publication target drifted outside prepared states: {target['target_ref']}"
                )
        for target in targets:  # canonical pointer is sorted last by ROLE_PRIORITY.
            path = _target_path(root, target["role"], target["target_ref"])
            if _sha256_file(path) == target["after_sha256"]:
                continue
            _atomic_write(path, _decode_payload(target))
            if _sha256_file(path) != target["after_sha256"]:
                raise ValueError(
                    "selection-publication target failed post-write verification"
                )
        projection = [
            {
                key: target.get(key)
                for key in ("role", "target_ref", "before_sha256", "after_sha256")
            }
            for target in targets
        ]
        receipt = {
            "schema_version": SCHEMA_VERSION,
            "kind": "selection_publication_receipt",
            "status": "committed",
            "transaction_id": transaction_id,
            "selection_id": prepare["selection_id"],
            "source_decision_id": prepare["source_decision_id"],
            "source_decision_sha256": prepare["source_decision_sha256"],
            "prepare_ref": prepare_path.relative_to(root).as_posix(),
            "prepare_sha256": prepare_sha,
            "targets": projection,
            "authoritative_pointer_role": "task_alias",
            "all_targets_verified_before_receipt": True,
        }
        if "predecessor_transaction_id" in prepare:
            receipt["predecessor_transaction_id"] = prepare.get(
                "predecessor_transaction_id"
            )
        receipt_sha = _write_once(
            receipt_path, _display_json(receipt), "selection-publication receipt"
        )
        verified = validate_receipt(root, transaction_id, require_current_targets=True)
        return {
            **verified,
            "receipt_sha256": receipt_sha,
            "mutation_performed": True,
            "authoritative_selection_published": True,
            "current_selection_authority_claimed": True,
            "publication_authority_status": "published_current",
            "recovery_required": False,
        }


def pending_transaction_ids(root: Path) -> list[str]:
    root = root.expanduser().resolve(strict=True)
    directory = _transactions_root(root)
    if not directory.is_dir():
        return []
    pending: list[str] = []
    for child in sorted(directory.iterdir()):
        if not child.is_dir() or not TRANSACTION_ID.fullmatch(child.name):
            continue
        if not (child / "prepare.json").is_file():
            continue
        try:
            validate_receipt(root, child.name)
        except (OSError, ValueError):
            pending.append(child.name)
    return pending


def _reject_competing_pending(root: Path, transaction_id: str) -> None:
    competing = [
        item for item in pending_transaction_ids(root) if item != transaction_id
    ]
    if competing:
        raise ValueError(
            "selection-publication has a different pending transaction; "
            "recover it before preparing or publishing new selection work"
        )


def _committed_receipts(root: Path) -> list[dict[str, Any]]:
    directory = _receipts_root(root)
    if not directory.is_dir():
        return []
    receipts: list[dict[str, Any]] = []
    for path in sorted(directory.glob("selection-*.json")):
        transaction_id = path.stem
        if TRANSACTION_ID.fullmatch(transaction_id):
            receipts.append(validate_receipt(root, transaction_id))
    return receipts


def recover_publications(
    root: Path, transaction_id: str | None = None
) -> dict[str, Any]:
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


def publication_status(root: Path) -> dict[str, Any]:
    root = root.expanduser().resolve(strict=True)
    pending = pending_transaction_ids(root)
    head = current_head_status(
        _committed_receipts(root), _sha256_file(root / "task.md")
    )
    if pending:
        status = "recovery_required"
    elif head["status"] in {"drifted", "ambiguous"}:
        status = "drift_blocked"
    else:
        status = "clear"
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
