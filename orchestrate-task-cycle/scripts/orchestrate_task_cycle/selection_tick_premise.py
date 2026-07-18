"""Premise-input policy and semantic watch rows for selection ticks."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .exact_subject_premise_v2 import (
    validate_artifact_verified_exact_subject_premise_receipt,
)
from .selection_tick_io import safe_json_object, safe_path, sha256_and_size


RAW_PREMISE_CONTRACT = "raw_exact_file_v1"
VERIFIED_PREMISE_CONTRACT = "validated_exact_subject_premise_receipt_v2"
PREMISE_CONTRACTS = frozenset({RAW_PREMISE_CONTRACT, VERIFIED_PREMISE_CONTRACT})
_VERIFIED_ROW_KEYS = {
    "watch_id",
    "exists",
    "kind",
    "evidence_class",
    "premise_id",
    "path_redacted",
    "sha256",
    "size_bytes",
    "premise_input_contract",
    "premise_receipt_schema_version",
    "premise_receipt_id",
    "premise_replay_identity_sha256",
    "premise_receipt",
}


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _packet_sha256(packet: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical(packet)).hexdigest()


def premise_input_contract(
    previous: dict[str, Any] | None,
    requested: str | None,
) -> str:
    """Resolve and lock one premise-input contract across a wait baseline."""

    if requested is not None and not isinstance(requested, str):
        raise ValueError("premise input contract must be a string or null")
    requested_value = (requested or "").strip()
    if requested_value and requested_value not in PREMISE_CONTRACTS:
        raise ValueError("premise input contract is unsupported")
    if previous is None:
        return requested_value or VERIFIED_PREMISE_CONTRACT
    previous_value = previous.get("premise_input_contract", RAW_PREMISE_CONTRACT)
    if not isinstance(previous_value, str):
        raise ValueError("previous premise input contract must be a string")
    if previous_value not in PREMISE_CONTRACTS:
        raise ValueError("previous premise input contract is unsupported")
    if requested_value and requested_value != previous_value:
        raise ValueError(
            "premise input contract cannot change while comparing a baseline"
        )
    return previous_value


def _previous_exact_row(
    previous: dict[str, Any] | None, watch_id: str
) -> dict[str, Any] | None:
    rows = previous.get("watch_entries") if previous else None
    if not isinstance(rows, list):
        return None
    return next(
        (
            row
            for row in rows
            if isinstance(row, dict)
            and row.get("watch_id") == watch_id
            and row.get("kind") == "exact_premise"
        ),
        None,
    )


def _expected_binding(root: Path, previous: dict[str, Any] | None) -> dict[str, str]:
    if previous is not None:
        packet_id = previous.get("packet_id")
        if not isinstance(packet_id, str):
            raise ValueError("selection baseline packet_id must be a string")
        return {
            "binding_kind": "selection_baseline",
            "selection_baseline_id": packet_id,
            "selection_baseline_sha256": _packet_sha256(previous),
        }
    try:
        task, _normalized = safe_path(root, "task.md", explicit=True)
        task_sha256, _size = sha256_and_size(task)
    except (OSError, ValueError) as exc:
        raise ValueError(
            "verified exact premise requires a bounded regular terminal task"
        ) from exc
    return {
        "binding_kind": "terminal_task",
        "terminal_task_sha256": task_sha256,
    }


def validate_premise_watch_row(
    *,
    root: Path,
    path: Path,
    row: dict[str, Any],
    premise_id: str,
    previous: dict[str, Any] | None,
    contract: str,
) -> dict[str, Any]:
    """Validate a receipt-mode premise and return a body-free semantic row."""

    if contract == RAW_PREMISE_CONTRACT:
        return row
    try:
        value, _normalized = safe_json_object(
            root, str(path), "exact-subject premise receipt"
        )
    except (OSError, ValueError) as exc:
        raise ValueError("exact-subject premise receipt is unreadable") from exc
    receipt = validate_artifact_verified_exact_subject_premise_receipt(value)
    legacy_receipt = receipt["legacy_receipt"]
    accepted = legacy_receipt["accepted_premise"]
    if accepted["premise_id"] != premise_id:
        raise ValueError("premise ID differs from the exact-subject receipt")
    previous_row = _previous_exact_row(previous, str(row["watch_id"]))
    exact_replay = bool(
        previous_row
        and previous_row.get("sha256") == receipt["receipt_sha256"]
        and previous_row.get("premise_replay_identity_sha256")
        == legacy_receipt["replay_identity_sha256"]
    )
    if not exact_replay and legacy_receipt["current_binding"] != _expected_binding(
        root, previous
    ):
        raise ValueError("exact-subject premise receipt is bound to another wait state")
    row.update(
        {
            "sha256": receipt["receipt_sha256"],
            "size_bytes": len(_canonical(receipt)),
            "premise_input_contract": contract,
            "premise_receipt_schema_version": 2,
            "premise_receipt_id": receipt["receipt_id"],
            "premise_replay_identity_sha256": legacy_receipt["replay_identity_sha256"],
            "premise_receipt": receipt,
        }
    )
    return row


def validate_embedded_verified_premise_row(
    value: object,
) -> dict[str, Any]:
    """Validate one path-free self-contained v2 exact-premise watch row."""

    if not isinstance(value, dict) or set(value) != _VERIFIED_ROW_KEYS:
        raise ValueError("verified exact-premise watch row has non-contract fields")
    premise_id = value.get("premise_id")
    if not isinstance(premise_id, str):
        raise ValueError("verified exact-premise row premise_id must be a string")
    expected_watch_id = (
        "watch-"
        + hashlib.sha256(f"exact_subject:{premise_id}".encode()).hexdigest()[:24]
    )
    receipt = validate_artifact_verified_exact_subject_premise_receipt(
        value.get("premise_receipt")
    )
    legacy = receipt["legacy_receipt"]
    valid = bool(
        value.get("kind") == "exact_premise"
        and value.get("evidence_class") == "exact_subject"
        and value.get("watch_id") == expected_watch_id
        and value.get("exists") is True
        and value.get("path_redacted") is True
        and value.get("premise_input_contract") == VERIFIED_PREMISE_CONTRACT
        and value.get("premise_receipt_schema_version") == 2
        and value.get("premise_receipt_id") == receipt["receipt_id"]
        and value.get("premise_replay_identity_sha256")
        == legacy["replay_identity_sha256"]
        and value.get("sha256") == receipt["receipt_sha256"]
        and value.get("size_bytes") == len(_canonical(receipt))
        and legacy["accepted_premise"]["premise_id"] == premise_id
    )
    if not valid:
        raise ValueError("verified exact-premise watch row binding is invalid")
    return value


__all__ = (
    "PREMISE_CONTRACTS",
    "RAW_PREMISE_CONTRACT",
    "VERIFIED_PREMISE_CONTRACT",
    "premise_input_contract",
    "validate_embedded_verified_premise_row",
    "validate_premise_watch_row",
)
