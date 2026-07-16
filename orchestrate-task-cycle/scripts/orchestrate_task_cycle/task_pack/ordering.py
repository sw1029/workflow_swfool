"""Pure item ordering and selection helpers."""
from __future__ import annotations

from typing import Any

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
    remaining = [item for item in planned_items(data) if item.get("status") in {"planned", "inserted", "reordered"}]
    data["current_item_id"] = remaining[0].get("item_id") if remaining else None
    in_flight = any(
        isinstance(item, dict) and item.get("status") in {"promoted", "in_progress"}
        for item in data.get("items", [])
    )
    if not remaining and not in_flight and data.get("status") == "active":
        data["status"] = "completed"


def evidence_paths_from(plan: dict[str, Any]) -> list[str]:
    value = plan.get("evidence_paths") or plan.get("evidence") or []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    return []
def next_item(data: dict[str, Any]) -> dict[str, Any] | None:
    current = data.get("current_item_id")
    items = sorted_items(data)
    if current:
        for item in items:
            if item.get("item_id") == current and item.get("status") in {"planned", "inserted", "reordered", "blocked"}:
                return item
    for item in items:
        if item.get("status") in {"planned", "inserted", "reordered"}:
            return item
    return None

