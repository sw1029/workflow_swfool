from __future__ import annotations

import re
from typing import Any

_DURABLE_SENSITIVE_KEYS = {
    "anti_loop_handoff",
    "artifact_path_or_store_ref",
    "changed_files",
    "changed_verifier_source_paths",
    "duplicate_key_paths",
    "error",
    "evidence_paths",
    "legacy_attempt_identity",
    "legacy_family_key",
    "message",
    "original_title",
    "path",
    "raw_source_path",
    "reason",
    "repair_task_id",
    "root_cause_ledger_projection",
    "sealed_blocker_families_projection",
    "source_paths",
    "task_family_label",
    "task_id",
    "task_label",
    "task_name",
    "task_pack_name",
    "title",
    "verifier_source_paths",
}
_DURABLE_VOLATILE_KEYS = {
    "checked_at",
    "created_at",
    "created_or_observed_at",
    "timestamp",
    "updated_at",
}
_DURABLE_SENSITIVE_KEY_PARTS = (
    "character_count",
    "char_count",
    "direct_quote",
    "interval",
    "line_number",
    "line_start",
    "line_end",
    "locator",
    "offset",
    "original_title",
    "quoted_text",
    "raw_text",
    "source_text",
    "text_span",
)


def _durable_key_is_sensitive(key: str) -> bool:
    normalized = key.strip().lower()
    return bool(
        normalized in _DURABLE_SENSITIVE_KEYS
        or normalized in _DURABLE_VOLATILE_KEYS
        or normalized.endswith("_at")
        or normalized.endswith("_error")
        or normalized.endswith("_path")
        or normalized.endswith("_paths")
        or normalized.startswith("path_")
        or normalized == "raw"
        or normalized.startswith("raw_")
        or normalized.endswith("_raw")
        or normalized == "text"
        or normalized.startswith("text_")
        or normalized.endswith("_text")
        or normalized == "quote"
        or normalized.startswith("quote_")
        or normalized.endswith("_quote")
        or normalized == "title"
        or normalized.startswith("title_")
        or normalized.endswith("_title")
        or any(part in normalized for part in _DURABLE_SENSITIVE_KEY_PARTS)
    )


def _reference_looks_like_path(value: str) -> bool:
    text = value.strip()
    return bool(
        text.startswith(("/", "./", "../", "~"))
        or "/" in text
        or "\\" in text
        or re.search(r"(?:^|[._-])(?:md|jsonl?|ya?ml|txt|csv|parquet|py)$", text, re.IGNORECASE)
    )


def bounded_durable_projection(value: Any, *, parent_key: str = "") -> Any:
    """Remove source-locating metadata while retaining replayable scalar state."""
    if isinstance(value, dict):
        projected: dict[str, Any] = {}
        for raw_key, child in value.items():
            key = str(raw_key)
            if _durable_key_is_sensitive(key):
                continue
            if key == "findings" and isinstance(child, list):
                projected[key] = [
                    {
                        field: finding.get(field)
                        for field in ("severity", "code")
                        if finding.get(field) is not None
                    }
                    for finding in child
                    if isinstance(finding, dict)
                ]
                continue
            sanitized = bounded_durable_projection(child, parent_key=key)
            if sanitized is not None or child is None:
                projected[key] = sanitized
        return projected
    if isinstance(value, list):
        projected_items = []
        for child in value:
            sanitized = bounded_durable_projection(child, parent_key=parent_key)
            if sanitized is not None:
                projected_items.append(sanitized)
        return projected_items
    if isinstance(value, str) and _reference_looks_like_path(value):
        if (
            parent_key.endswith("_ref")
            or parent_key.endswith("_refs")
            or parent_key.endswith("_error")
            or parent_key in {"action", "error", "message", "orphans", "provenance_refs"}
        ):
            return None
    return value
