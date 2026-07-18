"""Shared prospective validation for canonical task-state event batches."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from ..migration.api import validate_current_suffix_event
from .contracts import TASK_SCAN_PRESERVED_NONEXECUTABLE_STATUSES
from .events import merge_state, validate_event, versioned_event


def validate_completed_task_alias_batch(
    existing_state: dict[str, dict[str, Any]],
    events: list[dict[str, Any]],
) -> None:
    event_ids = {
        str(event.get("id"))
        for event in events
        if isinstance(event.get("id"), str)
    }
    prospective_state = merge_state([*existing_state.values(), *events])
    for item_id, existing in existing_state.items():
        existing_fields = (
            existing.get("fields") if isinstance(existing.get("fields"), dict) else {}
        )
        completed_alias = bool(
            existing.get("type") == "task"
            and existing.get("path") == "task.md"
            and existing.get("status") in TASK_SCAN_PRESERVED_NONEXECUTABLE_STATUSES
            and existing_fields.get("record_class") == "mutable_alias"
            and existing_fields.get("canonical_id") == item_id
        )
        if not completed_alias or item_id not in event_ids:
            continue
        current = prospective_state[item_id]
        if current.get("content_sha256") != existing.get("content_sha256"):
            raise ValueError(
                "A completed current task alias cannot change body under the same identity"
            )
        current_fields = (
            current.get("fields") if isinstance(current.get("fields"), dict) else {}
        )
        if (
            current.get("status") in TASK_SCAN_PRESERVED_NONEXECUTABLE_STATUSES
            and current_fields.get("record_class") == "mutable_alias"
            and current_fields.get("canonical_id") == item_id
        ):
            continue
        successor_ids = {
            str(link.get("id"))
            for link in current.get("links") or []
            if isinstance(link, dict)
            and link.get("rel") == "superseded_by"
            and link.get("id")
        }
        valid_successor = False
        for successor_id in successor_ids.intersection(event_ids):
            if successor_id == item_id:
                continue
            successor = prospective_state.get(successor_id) or {}
            successor_fields = (
                successor.get("fields")
                if isinstance(successor.get("fields"), dict)
                else {}
            )
            supersedes = {
                str(link.get("id"))
                for link in successor.get("links") or []
                if isinstance(link, dict)
                and link.get("rel") == "supersedes"
                and link.get("id")
            }
            if (
                current.get("status") == "superseded"
                and current_fields.get("record_class") == "immutable_snapshot"
                and successor.get("type") == "task"
                and successor.get("path") == "task.md"
                and successor_fields.get("record_class") == "mutable_alias"
                and successor_fields.get("canonical_id") == successor_id
                and item_id in supersedes
            ):
                valid_successor = True
                break
        if not valid_successor:
            raise ValueError(
                "A completed task identity can change lifecycle only in one batch "
                "with a distinct linked successor"
            )


def validate_event_batch(
    existing: list[dict[str, Any]],
    events: list[dict[str, Any]],
    *,
    source: Path,
) -> list[dict[str, Any]]:
    """Run the exact deterministic suffix invariants used by canonical append."""

    existing_state = merge_state(existing)
    known_ids = set(existing_state)
    versioned = [versioned_event(event) for event in events]
    for offset, event in enumerate(versioned, start=1):
        validate_event(event, offset, source)
        validate_current_suffix_event(event, known_ids)
    validate_completed_task_alias_batch(existing_state, versioned)
    return versioned
