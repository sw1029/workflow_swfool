"""Closed selection-publication projection contract embedded in selection ticks."""

from __future__ import annotations

import re


PUBLICATION_KEYS = frozenset(
    "status pending_transaction_ids selection_journal_initialized "
    "selection_consumption_allowed selection_consumption_reason current_head "
    "mutation_performed".split()
)
UNINITIALIZED_HEAD_KEYS = frozenset(
    "status head_transaction_id head_count lineage_mode".split()
)
CURRENT_HEAD_KEYS = frozenset(
    "status head_transaction_id head_count expected_task_sha256 "
    "current_task_sha256 lineage_mode".split()
)
AMBIGUOUS_HEAD_KEYS = frozenset(
    "status head_transaction_id head_count head_transaction_ids "
    "current_task_sha256 lineage_mode lineage_errors".split()
)
SHA256 = re.compile(r"[0-9a-f]{64}")
TRANSACTION_ID = re.compile(r"selection-[0-9a-f]{64}")
LINEAGE_ERROR = re.compile(
    r"(?:invalid_explicit_predecessor|ambiguous_legacy_predecessor):"
    r"selection-[0-9a-f]{64}"
)
LINEAGE_MODES = frozenset({"explicit", "legacy", "mixed"})


def _sha_or_none(value: object) -> bool:
    return value is None or (isinstance(value, str) and bool(SHA256.fullmatch(value)))


def _validate_current_head(value: object) -> str:
    if not isinstance(value, dict) or not isinstance(value.get("status"), str):
        raise ValueError("selection publication current head is invalid")
    status = value["status"]
    if status == "not_initialized":
        valid = bool(
            set(value) == UNINITIALIZED_HEAD_KEYS
            and value["head_transaction_id"] is None
            and type(value["head_count"]) is int
            and value["head_count"] == 0
            and value["lineage_mode"] == "uninitialized"
        )
    elif status in {"current", "drifted"}:
        expected = value.get("expected_task_sha256")
        current = value.get("current_task_sha256")
        valid = bool(
            set(value) == CURRENT_HEAD_KEYS
            and isinstance(value["head_transaction_id"], str)
            and TRANSACTION_ID.fullmatch(value["head_transaction_id"])
            and type(value["head_count"]) is int
            and value["head_count"] == 1
            and isinstance(expected, str)
            and SHA256.fullmatch(expected)
            and _sha_or_none(current)
            and isinstance(value["lineage_mode"], str)
            and value["lineage_mode"] in LINEAGE_MODES
            and (status == "current") is (current == expected)
        )
    elif status == "ambiguous":
        identifiers = value.get("head_transaction_ids")
        errors = value.get("lineage_errors")
        valid = bool(
            set(value) == AMBIGUOUS_HEAD_KEYS
            and value["head_transaction_id"] is None
            and type(value["head_count"]) is int
            and isinstance(identifiers, list)
            and all(
                isinstance(item, str) and TRANSACTION_ID.fullmatch(item)
                for item in identifiers
            )
            and identifiers == sorted(set(identifiers))
            and value["head_count"] == len(identifiers)
            and _sha_or_none(value.get("current_task_sha256"))
            and isinstance(value["lineage_mode"], str)
            and value["lineage_mode"] in LINEAGE_MODES
            and isinstance(errors, list)
            and all(
                isinstance(item, str) and LINEAGE_ERROR.fullmatch(item)
                for item in errors
            )
            and len(errors) == len(set(errors))
            and not (len(identifiers) == 1 and not errors)
            and not (identifiers and errors)
        )
    else:
        valid = False
    if not valid:
        raise ValueError("selection publication current head schema is invalid")
    return status


def validate_selection_publication(
    value: object, expected_pending_ids: list[str]
) -> str:
    """Validate one status-specific, deterministic publication projection."""

    if not isinstance(value, dict) or set(value) != PUBLICATION_KEYS:
        raise ValueError("selection publication status has non-contract fields")
    status = value["status"]
    head_status = _validate_current_head(value["current_head"])
    if (
        not isinstance(status, str)
        or status not in {"clear", "recovery_required", "drift_blocked"}
        or value["pending_transaction_ids"] != expected_pending_ids
        or value["mutation_performed"] is not False
        or not isinstance(value["selection_journal_initialized"], bool)
        or not isinstance(value["selection_consumption_allowed"], bool)
        or not isinstance(value["selection_consumption_reason"], str)
    ):
        raise ValueError("selection publication status is invalid")
    expected_status = (
        "recovery_required"
        if expected_pending_ids
        else "drift_blocked"
        if head_status in {"drifted", "ambiguous"}
        else "clear"
    )
    initialized = head_status != "not_initialized"
    allowed = expected_status == "clear" and initialized
    reason = (
        "committed_unique_current_head"
        if allowed
        else "no_committed_selection"
        if not initialized
        else "publication_recovery_or_drift_repair_required"
    )
    if (
        status != expected_status
        or value["selection_journal_initialized"] is not initialized
        or value["selection_consumption_allowed"] is not allowed
        or value["selection_consumption_reason"] != reason
    ):
        raise ValueError("selection publication projection is inconsistent")
    return status


__all__ = ("validate_selection_publication",)
