"""Action-specific in-memory task-pack transformations."""

from __future__ import annotations

import copy
from typing import Any

from .mutation_normalization import apply_normalization
from .mutation_promotion import apply_promote
from .ordering import evidence_paths_from, item_order, renumber_items, sorted_items
from .provenance import mutation_entry
from .state_machine import IN_FLIGHT_STATUSES, OPEN_ITEM_STATUSES


_INSERT_FORBIDDEN_FIELDS = {
    "order",
    "status",
    "promotion",
    "completion",
    "result",
    "created_at",
    "updated_at",
    "mutation_log",
    "provenance",
    "source_evidence",
    "unblock_receipt",
    "retirement_basis",
}


def _last_frozen_item_index(items: list[dict[str, Any]]) -> int:
    """Return the last immutable or in-flight position in canonical order."""

    return max(
        (
            index
            for index, item in enumerate(items)
            if item.get("status") not in OPEN_ITEM_STATUSES
            or item.get("status") in IN_FLIGHT_STATUSES
        ),
        default=-1,
    )


def apply_insert(
    data: dict[str, Any],
    items: list[Any],
    plan: dict[str, Any],
    before_order: list[str],
) -> None:
    raw_items = plan.get("items") or plan.get("insert_items")
    new_items = copy.deepcopy(raw_items)
    if not isinstance(new_items, list) or not new_items:
        raise SystemExit("Insert mutation requires non-empty `items`.")
    existing_ids = {
        str(item.get("item_id")) for item in items if isinstance(item, dict)
    }
    for item in new_items:
        if not isinstance(item, dict):
            raise SystemExit("Inserted items must be JSON objects.")
        item_id = str(item.get("item_id") or "").strip()
        if not item_id or item_id in existing_ids:
            raise SystemExit(f"Inserted item_id is empty or duplicated: {item_id}")
        forbidden = sorted(_INSERT_FORBIDDEN_FIELDS & set(item))
        if forbidden:
            raise SystemExit(
                "Inserted items may contain planning fields only; helper-owned lifecycle/provenance fields were supplied: "
                + ", ".join(forbidden)
            )
        item["status"] = "inserted"
        item["dependencies"] = copy.deepcopy(item.get("dependencies", []))
        item["source_evidence"] = evidence_paths_from(plan)
        item["promotion"] = {"task_id": None, "task_path": None, "promoted_at": None}
        item["result"] = {
            "validation_verdict": None,
            "progress_verdict": None,
            "progress_kind": None,
            "semantic_signature": None,
            "blocker_signature": None,
        }
        existing_ids.add(item_id)
    ordered = sorted_items(data)
    explicit_anchor_declared = "insert_before_item_id" in plan
    explicit_anchor = plan.get("insert_before_item_id")
    if explicit_anchor_declared and not (
        isinstance(explicit_anchor, str) and explicit_anchor.strip()
    ):
        raise SystemExit("Explicit insert_before_item_id must be a non-empty item ID.")
    insert_before = (
        explicit_anchor.strip()
        if isinstance(explicit_anchor, str) and explicit_anchor.strip()
        else data.get("current_item_id")
    )
    if insert_before and not any(
        str(item.get("item_id") or "") == str(insert_before) for item in ordered
    ):
        label = "Explicit insert anchor" if explicit_anchor_declared else "Current item"
        raise SystemExit(
            f"{label} does not resolve to a task-pack item: {insert_before}"
        )
    insertion_index = next(
        (
            index
            for index, item in enumerate(ordered)
            if insert_before and item.get("item_id") == insert_before
        ),
        len(ordered),
    )
    if insertion_index <= _last_frozen_item_index(ordered):
        raise SystemExit(
            "Insert may add planning work only after closed/in-flight history."
        )
    rebuilt: list[dict[str, Any]] = []
    inserted = False
    for item in ordered:
        if insert_before and item.get("item_id") == insert_before:
            rebuilt.extend(new_items)
            inserted = True
        rebuilt.append(item)
    if not inserted:
        rebuilt.extend(new_items)
    data["items"] = rebuilt
    renumber_items(data)
    data.setdefault("mutation_log", []).append(
        mutation_entry("insert", plan, before_order, item_order(data))
    )


def apply_reorder(
    data: dict[str, Any],
    items: list[Any],
    plan: dict[str, Any],
    before_order: list[str],
) -> None:
    requested = plan.get("item_order") or plan.get("order")
    if not isinstance(requested, list) or not requested:
        raise SystemExit("Reorder mutation requires full `item_order` list.")
    requested_ids = [str(item) for item in requested]
    current_ids = item_order(data)
    if set(requested_ids) != set(current_ids) or len(requested_ids) != len(current_ids):
        raise SystemExit("Reorder mutation must name every existing item exactly once.")
    if requested_ids == current_ids:
        raise SystemExit(
            "Reorder mutation is a no-op; canonical item order is unchanged."
        )
    by_id = {str(item.get("item_id")): item for item in items if isinstance(item, dict)}
    frozen_end = _last_frozen_item_index([by_id[item_id] for item_id in current_ids])
    if requested_ids[: frozen_end + 1] != current_ids[: frozen_end + 1]:
        raise SystemExit(
            "Reorder may change only the open residual suffix after closed/in-flight history."
        )
    if set(requested_ids[frozen_end + 1 :]) != set(current_ids[frozen_end + 1 :]):
        raise SystemExit(
            "Reorder open residual suffix does not preserve exact item membership."
        )
    data["items"] = [by_id[item_id] for item_id in requested_ids]
    for item in data["items"]:
        if item.get("status") == "planned":
            item["status"] = "reordered"
    renumber_items(data)
    data.setdefault("mutation_log", []).append(
        mutation_entry("reorder", plan, before_order, item_order(data))
    )


def apply_skip(
    data: dict[str, Any],
    items: list[Any],
    plan: dict[str, Any],
    before_order: list[str],
) -> None:
    item_ids = (
        plan.get("item_ids")
        or plan.get("skip_item_ids")
        or plan.get("exclude_item_ids")
    )
    if not isinstance(item_ids, list) or not item_ids:
        raise SystemExit("Skip mutation requires non-empty `item_ids`.")
    targets = {str(item_id) for item_id in item_ids}
    found: set[str] = set()
    for item in items:
        if isinstance(item, dict) and str(item.get("item_id")) in targets:
            if item.get("status") == "skipped":
                found.add(str(item.get("item_id")))
                continue
            if item.get("status") not in {
                "planned",
                "inserted",
                "reordered",
                "blocked",
            }:
                raise SystemExit(
                    f"Skip cannot rewrite closed or in-flight item {item.get('item_id')} from status {item.get('status')}."
                )
            item["status"] = "skipped"
            result = item.setdefault("result", {})
            result["skip_reason"] = plan.get("reason")
            result["evidence_paths"] = evidence_paths_from(plan)
            found.add(str(item.get("item_id")))
    missing = sorted(targets - found)
    if missing:
        raise SystemExit(f"Unknown task pack item(s): {', '.join(missing)}")
    data.setdefault("mutation_log", []).append(
        mutation_entry("skip", plan, before_order, item_order(data))
    )


def apply_supersede(
    data: dict[str, Any],
    items: list[Any],
    plan: dict[str, Any],
    before_order: list[str],
) -> None:
    in_flight = [
        item.get("item_id")
        for item in items
        if isinstance(item, dict) and item.get("status") in IN_FLIGHT_STATUSES
    ]
    if in_flight:
        raise SystemExit(
            "Supersede cannot close a pack with an in-flight item: "
            + ", ".join(str(item) for item in in_flight)
        )
    data["status"] = "superseded"
    for item in items:
        if isinstance(item, dict) and item.get("status") in {
            "planned",
            "inserted",
            "reordered",
            "blocked",
        }:
            item["status"] = "superseded"
    data.setdefault("mutation_log", []).append(
        mutation_entry("supersede", plan, before_order, item_order(data))
    )


def apply_terminal_block(
    data: dict[str, Any],
    items: list[Any],
    plan: dict[str, Any],
    before_order: list[str],
) -> None:
    terminal = plan.get("terminal_blocker")
    if not isinstance(terminal, dict):
        raise SystemExit("terminal_block mutation requires `terminal_blocker` object.")
    in_flight = [
        item.get("item_id")
        for item in items
        if isinstance(item, dict) and item.get("status") in IN_FLIGHT_STATUSES
    ]
    if in_flight:
        raise SystemExit(
            "terminal_block cannot close a pack with an in-flight item: "
            + ", ".join(str(item) for item in in_flight)
        )
    data["status"] = "terminal_blocked"
    data["terminal_blocker"] = terminal
    for item in items:
        if isinstance(item, dict) and item.get("status") in {
            "planned",
            "inserted",
            "reordered",
            "blocked",
        }:
            item["status"] = "terminal_blocked"
    data.setdefault("mutation_log", []).append(
        mutation_entry("terminal_block", plan, before_order, item_order(data))
    )


__all__ = (
    "apply_insert",
    "apply_normalization",
    "apply_promote",
    "apply_reorder",
    "apply_skip",
    "apply_supersede",
    "apply_terminal_block",
)
