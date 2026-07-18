"""Central task-pack lifecycle and dependency state machine."""

from __future__ import annotations

from typing import Any, Callable

READY_STATUSES = {"planned", "inserted", "reordered"}
IN_FLIGHT_STATUSES = {"promoted", "in_progress"}
WAITING_STATUSES = {"blocked"}
COMPLETED_ITEM_STATUSES = {"consumed", "skipped"}
OPEN_ITEM_STATUSES = READY_STATUSES | IN_FLIGHT_STATUSES | WAITING_STATUSES
IMMUTABLE_ITEM_STATUSES = COMPLETED_ITEM_STATUSES | {"terminal_blocked", "superseded"}


def _sorted_items(data: dict[str, Any]) -> list[dict[str, Any]]:
    return sorted(
        (item for item in data.get("items", []) if isinstance(item, dict)),
        key=lambda item: item.get("order", 0),
    )


def item_dependencies(item: dict[str, Any]) -> list[str]:
    value = item.get("dependencies", [])
    if not isinstance(value, list):
        return []
    return [str(dependency).strip() for dependency in value if str(dependency).strip()]


def item_index(data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("item_id")): item
        for item in _sorted_items(data)
        if item.get("item_id")
    }


def dependencies_satisfied(
    item: dict[str, Any], by_id: dict[str, dict[str, Any]]
) -> bool:
    dependencies = item_dependencies(item)
    return bool(
        all(
            dependency in by_id and by_id[dependency].get("status") == "consumed"
            for dependency in dependencies
        )
    )


def earliest_ready_item(data: dict[str, Any]) -> dict[str, Any] | None:
    by_id = item_index(data)
    return next(
        (
            item
            for item in _sorted_items(data)
            if item.get("status") in READY_STATUSES
            and dependencies_satisfied(item, by_id)
        ),
        None,
    )


def waiting_items(data: dict[str, Any]) -> list[dict[str, Any]]:
    by_id = item_index(data)
    return [
        item
        for item in _sorted_items(data)
        if item.get("status") in WAITING_STATUSES
        or (
            item.get("status") in READY_STATUSES
            and not dependencies_satisfied(item, by_id)
        )
    ]


def derived_operational_status(data: dict[str, Any]) -> str:
    status = str(data.get("status") or "")
    if status in {"terminal_blocked", "superseded"}:
        return status
    if any(item.get("status") in IN_FLIGHT_STATUSES for item in _sorted_items(data)):
        return "active"
    if earliest_ready_item(data) is not None:
        return "active"
    if waiting_items(data):
        return "blocked"
    return "completed"


def refresh_lifecycle(data: dict[str, Any]) -> None:
    """Project current item and nonterminal pack status from canonical item state."""

    ready = earliest_ready_item(data)
    data["current_item_id"] = ready.get("item_id") if ready is not None else None
    if data.get("status") not in {"terminal_blocked", "superseded"}:
        data["status"] = derived_operational_status(data)


def dependency_findings(
    data: dict[str, Any],
    add: Callable[[str, str, str, Any], None],
) -> None:
    ordered = _sorted_items(data)
    by_id = item_index(data)
    order_by_id = {
        str(item.get("item_id")): item.get("order")
        for item in ordered
        if item.get("item_id")
    }
    graph: dict[str, list[str]] = {}
    for item in ordered:
        item_id = str(item.get("item_id") or "")
        raw = item.get("dependencies", [])
        if raw is not None and not isinstance(raw, list):
            add(
                "block",
                "item_dependencies_invalid",
                "Task-pack item dependencies must be a list of item IDs.",
                {"item_id": item_id},
            )
            continue
        dependencies = item_dependencies(item)
        graph[item_id] = [
            dependency for dependency in dependencies if dependency in by_id
        ]
        if len(dependencies) != len(set(dependencies)):
            add(
                "block",
                "duplicate_item_dependency",
                "Task-pack item dependencies must be unique.",
                {"item_id": item_id, "dependencies": dependencies},
            )
        for dependency in dependencies:
            if dependency == item_id:
                add(
                    "block",
                    "self_item_dependency",
                    "Task-pack item cannot depend on itself.",
                    {"item_id": item_id},
                )
            elif dependency not in by_id:
                add(
                    "block",
                    "unknown_item_dependency",
                    "Task-pack item dependency must reference another item in the pack.",
                    {"item_id": item_id, "dependency_item_id": dependency},
                )
            elif (
                isinstance(order_by_id.get(item_id), int)
                and isinstance(order_by_id.get(dependency), int)
                and order_by_id[dependency] >= order_by_id[item_id]
            ):
                add(
                    "block",
                    "item_dependency_not_topological",
                    "A dependency must precede its dependent item in canonical order.",
                    {
                        "item_id": item_id,
                        "dependency_item_id": dependency,
                        "item_order": order_by_id[item_id],
                        "dependency_order": order_by_id[dependency],
                    },
                )

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(item_id: str, trail: list[str]) -> None:
        if item_id in visiting:
            cycle_start = trail.index(item_id) if item_id in trail else 0
            add(
                "block",
                "cyclic_item_dependency",
                "Task-pack item dependencies must be acyclic.",
                {"cycle": trail[cycle_start:] + [item_id]},
            )
            return
        if item_id in visited:
            return
        visiting.add(item_id)
        for dependency in graph.get(item_id, []):
            visit(dependency, trail + [item_id])
        visiting.remove(item_id)
        visited.add(item_id)

    for item_id in graph:
        visit(item_id, [])

    for item in ordered:
        if item.get("status") not in IN_FLIGHT_STATUSES | {"consumed"}:
            continue
        if not dependencies_satisfied(item, by_id):
            add(
                "block",
                "item_dependency_bypassed",
                "Promoted, in-progress, or consumed items require every dependency to be consumed.",
                {
                    "item_id": item.get("item_id"),
                    "status": item.get("status"),
                    "unsatisfied_dependencies": [
                        dependency
                        for dependency in item_dependencies(item)
                        if dependency not in by_id
                        or by_id[dependency].get("status") != "consumed"
                    ],
                },
            )


def lifecycle_findings(
    data: dict[str, Any],
    add: Callable[[str, str, str, Any], None],
) -> None:
    status = str(data.get("status") or "")
    ordered = _sorted_items(data)
    in_flight = [item for item in ordered if item.get("status") in IN_FLIGHT_STATUSES]
    if status == "completed":
        inconsistent = [
            str(item.get("item_id") or "")
            for item in ordered
            if item.get("status") not in COMPLETED_ITEM_STATUSES
        ]
        if inconsistent:
            add(
                "block",
                "completed_pack_has_noncompleted_items",
                "A completed task pack may contain only consumed or skipped items.",
                {"item_ids": inconsistent},
            )
    if status == "terminal_blocked":
        open_items = [
            item
            for item in ordered
            if item.get("status") in OPEN_ITEM_STATUSES | IN_FLIGHT_STATUSES
        ]
        if open_items:
            add(
                "block",
                "closed_pack_has_open_item",
                "A terminal-blocked or superseded pack cannot retain executable or in-flight items.",
                {
                    "pack_status": status,
                    "item_ids": [item.get("item_id") for item in open_items],
                },
            )
    if status == "superseded" and in_flight:
        add(
            "block",
            "closed_pack_has_in_flight_item",
            "A superseded pack cannot contain an in-flight item.",
            {
                "pack_status": status,
                "item_ids": [item.get("item_id") for item in in_flight],
            },
        )

    expected_status = derived_operational_status(data)
    if status not in {"terminal_blocked", "superseded"} and status != expected_status:
        add(
            "block",
            "pack_operational_status_mismatch",
            "Pack status must be derived from ready, waiting, in-flight, and completed item state.",
            {"declared": status, "expected": expected_status},
        )
    ready = earliest_ready_item(data)
    expected_current = ready.get("item_id") if ready is not None else None
    if data.get("current_item_id") != expected_current:
        add(
            "block",
            "current_item_not_earliest_ready",
            "current_item_id must equal the earliest dependency-ready open item.",
            {"declared": data.get("current_item_id"), "expected": expected_current},
        )
