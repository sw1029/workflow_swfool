"""Pure item ordering and selection helpers."""
from __future__ import annotations

from typing import Any

from .state_machine import READY_STATUSES, earliest_ready_item, refresh_lifecycle

def sorted_items(data: dict[str, Any]) -> list[dict[str, Any]]:
    return sorted((item for item in data.get("items", []) if isinstance(item, dict)), key=lambda item: item.get("order", 0))


def item_order(data: dict[str, Any]) -> list[str]:
    return [str(item.get("item_id")) for item in sorted_items(data) if item.get("item_id")]


def renumber_items(data: dict[str, Any]) -> None:
    for index, item in enumerate((item for item in data.get("items", []) if isinstance(item, dict)), start=1):
        item["order"] = index


def planned_items(data: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for item in sorted_items(data) if item.get("status") in {"planned", "inserted", "reordered", "blocked"}]


def active_in_flight_items(data: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for item in sorted_items(data) if item.get("status") in {"promoted", "in_progress"}]


def refresh_current_item(data: dict[str, Any]) -> None:
    refresh_lifecycle(data)


def evidence_paths_from(plan: dict[str, Any]) -> list[str]:
    value = plan.get("evidence_paths") or plan.get("evidence") or []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    return []
def next_item(data: dict[str, Any]) -> dict[str, Any] | None:
    current = data.get("current_item_id")
    ready = earliest_ready_item(data)
    if ready is None:
        return None
    if current and ready.get("item_id") != current:
        return None
    if ready.get("status") not in READY_STATUSES:
        return None
    return ready
