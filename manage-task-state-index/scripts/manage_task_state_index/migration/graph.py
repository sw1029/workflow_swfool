"""Shared migration journal and receipt-anchor graph helpers."""
from __future__ import annotations

import json
from typing import Any

from .contracts import ANCHOR_KIND, MIGRATION_EVENT_FIELD, MigrationError
from .mapping import _physical_lines


def _validate_journal_base(
    journal: dict[str, Any],
    prepare: dict[str, Any],
) -> None:
    if any(journal.get(key) != value for key, value in prepare.items() if key != "state"):
        raise MigrationError("Migration journal does not match immutable prepare contract")


def _find_anchor_lines(payload: bytes) -> list[tuple[int, bytes, dict[str, Any]]]:
    anchors: list[tuple[int, bytes, dict[str, Any]]] = []
    offset = 0
    for raw_line in _physical_lines(payload):
        try:
            value = json.loads(raw_line.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            offset += len(raw_line)
            continue
        fields = (
            value.get("fields")
            if isinstance(value, dict) and isinstance(value.get("fields"), dict)
            else {}
        )
        if fields.get(MIGRATION_EVENT_FIELD) == ANCHOR_KIND:
            anchors.append((offset, raw_line, value))
        offset += len(raw_line)
    return anchors


def _matching_plan_anchor(
    payload: bytes,
    plan: dict[str, Any],
) -> tuple[int, bytes, dict[str, Any]] | None:
    for offset, raw, anchor in reversed(_find_anchor_lines(payload)):
        fields = anchor.get("fields", {})
        if fields.get("migration_id") != plan["migration_id"]:
            continue
        return offset, raw, anchor
    return None
