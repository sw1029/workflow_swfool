"""Pure rendering of immutable selection-publication commit receipts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from .selection_publication_plan import _target_path
from .selection_publication_store import (
    SHA256,
    _display_json,
    _receipt_path,
    _sha256_file,
)


RECEIPT_KEYS = {
    "schema_version",
    "kind",
    "status",
    "transaction_id",
    "selection_id",
    "source_decision_id",
    "source_decision_sha256",
    "prepare_ref",
    "prepare_sha256",
    "targets",
    "authoritative_pointer_role",
    "all_targets_verified_before_receipt",
}
V3_RECEIPT_KEYS = {"owner_pending_receipt", "external_settlement_plan_id"}
LINEAGE_KEY = {"predecessor_transaction_id"}


def receipt_for_prepare(
    root: Path,
    prepare: dict[str, Any],
    prepare_path: Path,
    prepare_sha256: str,
    *,
    pending_binding: dict[str, str] | None,
) -> dict[str, Any]:
    """Render the exact commit receipt without performing an effect."""

    projection = [
        {
            key: target.get(key)
            for key in ("role", "target_ref", "before_sha256", "after_sha256")
        }
        for target in prepare["targets"]
    ]
    receipt: dict[str, Any] = {
        "schema_version": prepare["schema_version"],
        "kind": "selection_publication_receipt",
        "status": "committed",
        "transaction_id": prepare["transaction_id"],
        "selection_id": prepare["selection_id"],
        "source_decision_id": prepare["source_decision_id"],
        "source_decision_sha256": prepare["source_decision_sha256"],
        "prepare_ref": prepare_path.relative_to(root).as_posix(),
        "prepare_sha256": prepare_sha256,
        "targets": projection,
        "authoritative_pointer_role": "task_alias",
        "all_targets_verified_before_receipt": True,
    }
    if prepare.get("schema_version") == 3:
        if pending_binding is None:
            raise ValueError(
                "selection publication v3 receipt requires pending owner binding"
            )
        receipt["owner_pending_receipt"] = pending_binding
        receipt["external_settlement_plan_id"] = Path(
            prepare["task_state_plan"]["ref"]
        ).stem
    if "predecessor_transaction_id" in prepare:
        receipt["predecessor_transaction_id"] = prepare.get(
            "predecessor_transaction_id"
        )
    return receipt


def validate_receipt(
    root: Path,
    transaction_id: str,
    *,
    require_current_targets: bool,
    verify_external_binding: bool = True,
    load_prepare: Callable[
        [Path, str], tuple[dict[str, Any], Path, str]
    ],
) -> dict[str, Any]:
    """Validate one exact writer-owned receipt and its complete prepare binding."""

    root = root.expanduser().resolve(strict=True)
    prepare, prepare_path, prepare_sha = load_prepare(root, transaction_id)
    path = _receipt_path(root, transaction_id)
    if path.is_symlink() or not path.is_file():
        raise ValueError("selection-publication receipt is unreadable")
    raw = path.read_bytes()
    try:
        receipt = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("selection-publication receipt is unreadable") from exc
    if not isinstance(receipt, dict) or raw != _display_json(receipt):
        raise ValueError("selection-publication receipt is non-canonical")
    expected_keys = set(RECEIPT_KEYS)
    if "predecessor_transaction_id" in prepare:
        expected_keys.update(LINEAGE_KEY)
    if prepare.get("schema_version") == 3:
        expected_keys.update(V3_RECEIPT_KEYS)
    if set(receipt) != expected_keys:
        raise ValueError("selection-publication receipt fields are invalid")
    expected_targets = [
        {
            key: target.get(key)
            for key in ("role", "target_ref", "before_sha256", "after_sha256")
        }
        for target in prepare["targets"]
    ]
    pending = receipt.get("owner_pending_receipt")
    external_valid = True
    if prepare.get("schema_version") == 3:
        plan = prepare.get("task_state_plan") or {}
        plan_id = Path(str(plan.get("ref") or "")).stem
        external_valid = bool(
            receipt.get("external_settlement_plan_id") == plan_id
            and isinstance(pending, dict)
            and set(pending) == {"ref", "sha256"}
            and pending.get("ref")
            == f".task/transition_pending_receipts/{plan_id}.json"
            and SHA256.fullmatch(str(pending.get("sha256") or ""))
            and (
                not verify_external_binding
                or _sha256_file(root / str(pending["ref"])) == pending["sha256"]
            )
        )
    if (
        receipt.get("schema_version") != prepare.get("schema_version")
        or receipt.get("schema_version") not in {1, 2, 3}
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
        or receipt.get("all_targets_verified_before_receipt") is not True
        or receipt.get("predecessor_transaction_id")
        != prepare.get("predecessor_transaction_id")
        or not external_valid
    ):
        raise ValueError("selection-publication receipt contract is invalid")
    if require_current_targets:
        for target in prepare["targets"]:
            current = _sha256_file(
                _target_path(root, target["role"], target["target_ref"])
            )
            if current != target["after_sha256"]:
                raise ValueError("selection-publication committed target has drifted")
    receipt_sha = _sha256_file(path)
    assert receipt_sha is not None
    return {
        **receipt,
        "receipt_ref": path.relative_to(root).as_posix(),
        "receipt_sha256": receipt_sha,
    }


__all__ = ("receipt_for_prepare", "validate_receipt")
