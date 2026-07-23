"""Current task-alias classification for selected-successor preparation."""

from __future__ import annotations

from typing import Any

from .contracts import (
    NON_ACTIVE_STATUSES,
    TASK_SCAN_PRESERVED_NONEXECUTABLE_STATUSES,
)


SUPPORTED_PREDECESSOR_STATUSES = {
    "active",
    *TASK_SCAN_PRESERVED_NONEXECUTABLE_STATUSES,
}


def _completed_mutable_alias(
    item_id: str,
    item: dict[str, Any],
    current_alias_sha256: str,
) -> bool:
    fields = item.get("fields") if isinstance(item.get("fields"), dict) else {}
    return bool(
        item.get("status") in TASK_SCAN_PRESERVED_NONEXECUTABLE_STATUSES
        and item.get("content_sha256") == current_alias_sha256
        and fields.get("record_class") == "mutable_alias"
        and fields.get("canonical_id") == item_id
    )


def _predecessor_candidates(
    state: dict[str, dict[str, Any]],
    current_alias_sha256: str,
) -> list[tuple[str, dict[str, Any]]]:
    return [
        (item_id, item)
        for item_id, item in state.items()
        if item.get("type") == "task"
        and item.get("path") == "task.md"
        and (
            item.get("status") not in NON_ACTIVE_STATUSES
            or _completed_mutable_alias(item_id, item, current_alias_sha256)
        )
    ]


def current_task_predecessor(
    state: dict[str, dict[str, Any]],
    current_alias_sha256: str,
) -> tuple[str, dict[str, Any]] | None:
    """Return one supported current alias or reject its lifecycle state."""

    active_ids = {
        item_id
        for item_id, item in state.items()
        if item.get("type") == "task" and item.get("status") == "active"
    }
    rows = _predecessor_candidates(state, current_alias_sha256)
    if len(rows) > 1:
        raise ValueError("Current task alias identity is not unique")
    if not rows:
        if active_ids:
            raise ValueError(
                "Global active task set exists without one current task alias"
            )
        return None
    item_id, item = rows[0]
    status = item.get("status")
    if status not in SUPPORTED_PREDECESSOR_STATUSES:
        raise ValueError(
            f"Selected-successor current task predecessor status is unsupported: {status!r}"
        )
    if item.get("content_sha256") != current_alias_sha256:
        raise ValueError(
            "Selected-successor current task predecessor differs from task.md"
        )
    expected_active = {item_id} if status == "active" else set()
    if active_ids != expected_active:
        raise ValueError(
            "Global active task set differs from the current task predecessor"
        )
    return item_id, item


__all__ = (
    "SUPPORTED_PREDECESSOR_STATUSES",
    "current_task_predecessor",
)
