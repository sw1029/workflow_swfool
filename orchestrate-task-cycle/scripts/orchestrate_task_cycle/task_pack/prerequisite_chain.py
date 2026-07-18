"""Validation for optional bounded prerequisite-chain projections."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ..prerequisite_chain_contract import (
    APPLICABILITY,
    BUDGET_STATUSES,
    SUCCESSOR_KINDS,
    TRISTATE,
    not_applicable_evidence_valid,
    reduction_observation_valid,
)

FindingAdder = Callable[..., None]


def validate_item_prerequisite_chain(
    item: dict[str, Any], item_id: str, result: dict[str, Any], add: FindingAdder
) -> dict[str, Any] | None:
    raw = item.get("bounded_prerequisite_chain")
    if raw is None:
        raw = result.get("bounded_prerequisite_chain")
    if raw is None:
        return None
    if not isinstance(raw, dict):
        add(
            "block",
            "prerequisite_chain_invalid",
            "`bounded_prerequisite_chain` must be an object when supplied.",
            {"item_id": item_id},
        )
        return None
    applicability = str(raw.get("applicability") or "")
    if applicability not in APPLICABILITY:
        add(
            "block",
            "prerequisite_chain_applicability_invalid",
            "A bounded prerequisite chain requires explicit applicable or not_applicable state.",
            {"item_id": item_id},
        )
        return raw
    if applicability == "not_applicable":
        if not not_applicable_evidence_valid(raw):
            add(
                "block",
                "prerequisite_chain_not_applicable_unsubstantiated",
                "A not-applicable chain requires a closed, content-bound reason receipt.",
                {"item_id": item_id},
            )
        return raw
    required = (
        "stable_root_id",
        "item_owner_id",
        "prerequisite_relation_id",
        "strict_local_reduction",
        "semantic_high_water_moved",
        "chain_budget_status",
        "mandatory_successor_kind",
    )
    missing = [field for field in required if raw.get(field) in (None, "")]
    if missing:
        add(
            "block",
            "prerequisite_chain_fields_missing",
            "Applicable prerequisite chains require root, owner, reduction, budget, and successor fields.",
            {"item_id": item_id, "fields": missing},
        )
    strict = raw.get("strict_local_reduction")
    semantic = raw.get("semantic_high_water_moved")
    if strict not in TRISTATE or semantic not in TRISTATE:
        add(
            "block",
            "prerequisite_chain_tristate_invalid",
            "Reduction and semantic-high-water fields must be true, false, or not_evaluated.",
            {"item_id": item_id},
        )
    budget = str(raw.get("chain_budget_status") or "")
    successor = str(raw.get("mandatory_successor_kind") or "")
    if budget not in BUDGET_STATUSES or successor not in SUCCESSOR_KINDS:
        add(
            "block",
            "prerequisite_chain_budget_or_successor_invalid",
            "Chain budget and mandatory successor values are invalid.",
            {"item_id": item_id},
        )
    position = raw.get("chain_position")
    cap = raw.get("chain_cap")
    if position is not None or cap is not None:
        if (
            not isinstance(position, int)
            or isinstance(position, bool)
            or position < 1
            or not isinstance(cap, int)
            or isinstance(cap, bool)
            or cap < 1
            or position > cap
        ):
            add(
                "block",
                "prerequisite_chain_cap_invalid",
                "Supplied chain position/cap must be positive and position cannot exceed cap.",
                {"item_id": item_id},
            )
    if strict is True and not reduction_observation_valid(raw):
        add(
            "block",
            "prerequisite_chain_reduction_unsubstantiated",
            "strict_local_reduction=true requires a closed observation receipt bound to a decreasing source revision.",
            {"item_id": item_id},
        )
    if budget == "exhausted" and successor == "none":
        add(
            "block",
            "prerequisite_chain_exhausted_without_successor",
            "An exhausted applicable chain requires a producer, implementation, refresh, descope, or terminal successor.",
            {"item_id": item_id},
        )
    if (
        isinstance(position, int)
        and not isinstance(position, bool)
        and isinstance(cap, int)
        and not isinstance(cap, bool)
        and position == cap
        and successor == "none"
    ):
        add(
            "block",
            "prerequisite_chain_cap_without_successor",
            "A chain at its declared cap requires a direct successor even when budget status was not refreshed.",
            {"item_id": item_id},
        )
    if item.get("status") == "consumed" and strict is not True and semantic is not True:
        disposition = str(raw.get("item_close_disposition") or "")
        if disposition not in {"partial", "blocked", "descope", "terminal"}:
            add(
                "block",
                "nonreducing_prerequisite_consumed",
                "A non-reducing prerequisite item cannot be consumed as progress without partial, blocked, descope, or terminal disposition.",
                {"item_id": item_id},
            )
    return raw


def validate_pack_chain_coherence(
    rows: list[tuple[str, dict[str, Any]]], add: FindingAdder
) -> None:
    applicable = [
        (item_id, row)
        for item_id, row in rows
        if row.get("applicability") == "applicable"
    ]
    roots = {str(row.get("stable_root_id") or "") for _item_id, row in applicable}
    if len(roots) > 1:
        add(
            "block",
            "prerequisite_chain_root_drift",
            "One bounded prerequisite pack cannot reset its stable root between items.",
            {"item_ids": [item_id for item_id, _row in applicable]},
        )
    positions = [
        row.get("chain_position")
        for _item_id, row in applicable
        if row.get("chain_position") is not None
    ]
    if positions and positions != sorted(positions):
        add(
            "block",
            "prerequisite_chain_position_not_monotonic",
            "Chain positions must remain monotonic in pack order.",
            {"item_ids": [item_id for item_id, _row in applicable]},
        )
    relation_positions: dict[str, int] = {}
    for item_id, row in applicable:
        relation = str(row.get("prerequisite_relation_id") or "")
        position = row.get("chain_position")
        if not relation or not isinstance(position, int) or isinstance(position, bool):
            continue
        previous = relation_positions.get(relation)
        if previous is not None and position <= previous:
            add(
                "block",
                "prerequisite_chain_position_reset",
                "One prerequisite relation cannot reuse or reset its chain position.",
                {"item_id": item_id, "prerequisite_relation_id": relation},
            )
        relation_positions[relation] = position
