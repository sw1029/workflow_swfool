"""Pure committed-head projection for selection-publication receipts."""

from __future__ import annotations

import re
from typing import Any, Sequence


SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _task_alias_transition(receipt: dict[str, Any]) -> tuple[str | None, str]:
    target = next(
        (
            row
            for row in receipt.get("targets", [])
            if isinstance(row, dict) and row.get("role") == "task_alias"
        ),
        None,
    )
    if not isinstance(target, dict) or not SHA256.fullmatch(
        str(target.get("after_sha256") or "")
    ):
        raise ValueError("selection-publication receipt lacks a task_alias transition")
    before = target.get("before_sha256")
    if before is not None and not SHA256.fullmatch(str(before)):
        raise ValueError("selection-publication task_alias before digest is invalid")
    return (str(before) if before is not None else None), str(target["after_sha256"])


def _receipt_records(
    receipts: Sequence[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for receipt in receipts:
        transaction_id = str(receipt.get("transaction_id") or "")
        if not transaction_id or transaction_id in records:
            raise ValueError(
                "selection-publication receipts require unique transaction ids"
            )
        before, after = _task_alias_transition(receipt)
        records[transaction_id] = {
            "before": before,
            "after": after,
            "explicit": "predecessor_transaction_id" in receipt,
            "predecessor": receipt.get("predecessor_transaction_id"),
        }
    return records


def _lineage_heads(
    records: dict[str, dict[str, Any]],
) -> tuple[list[str], list[str], str]:
    predecessor_ids: set[str] = set()
    errors: list[str] = []
    modes = {"explicit" if row["explicit"] else "legacy" for row in records.values()}
    mode = next(iter(modes)) if len(modes) == 1 else "mixed"
    for successor_id, successor in records.items():
        if successor["explicit"]:
            predecessor = successor["predecessor"]
            if predecessor is None:
                continue
            if (
                not isinstance(predecessor, str)
                or predecessor == successor_id
                or predecessor not in records
            ):
                errors.append(f"invalid_explicit_predecessor:{successor_id}")
                continue
            predecessor_ids.add(predecessor)
            continue
        candidates = [
            candidate_id
            for candidate_id, candidate in records.items()
            if candidate_id != successor_id
            and candidate["after"] == successor["before"]
        ]
        if len(candidates) > 1:
            errors.append(f"ambiguous_legacy_predecessor:{successor_id}")
        elif candidates:
            predecessor_ids.add(candidates[0])
    heads = sorted(set(records) - predecessor_ids) if not errors else []
    return heads, errors, mode


def current_head_status(
    receipts: Sequence[dict[str, Any]], current_task_sha256: str | None
) -> dict[str, Any]:
    if not receipts:
        return {
            "status": "not_initialized",
            "head_transaction_id": None,
            "head_count": 0,
            "lineage_mode": "uninitialized",
        }
    records = _receipt_records(receipts)
    heads, errors, mode = _lineage_heads(records)
    if len(heads) != 1 or errors:
        return {
            "status": "ambiguous",
            "head_transaction_id": None,
            "head_count": len(heads),
            "head_transaction_ids": heads,
            "current_task_sha256": current_task_sha256,
            "lineage_mode": mode,
            "lineage_errors": errors,
        }
    head = heads[0]
    expected = records[head]["after"]
    return {
        "status": "current" if current_task_sha256 == expected else "drifted",
        "head_transaction_id": head,
        "head_count": 1,
        "expected_task_sha256": expected,
        "current_task_sha256": current_task_sha256,
        "lineage_mode": mode,
    }


__all__ = ("current_head_status",)
