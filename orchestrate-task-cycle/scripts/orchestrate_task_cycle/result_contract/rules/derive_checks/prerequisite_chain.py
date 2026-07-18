from __future__ import annotations

from typing import Any

from ....prerequisite_chain_contract import (
    APPLICABILITY,
    BUDGET_STATUSES,
    DIRECT_SUCCESSOR_KINDS,
    SUCCESSOR_KINDS,
    TRISTATE,
    not_applicable_evidence_valid,
    reduction_observation_valid,
    successor_task_kind_valid,
)
from .shared import add, selected_task_kind_value
from .state import DeriveFacts


SELECTED_SUCCESSOR_KINDS = DIRECT_SUCCESSOR_KINDS | {"prerequisite"}


def _chain(result: dict[str, Any]) -> object:
    direct = result.get("bounded_prerequisite_chain")
    if direct is not None:
        return direct
    anti_loop = result.get("anti_loop")
    if isinstance(anti_loop, dict):
        return anti_loop.get("bounded_prerequisite_chain")
    return None


def _block(
    facts: DeriveFacts, code: str, message: str, evidence: object = None
) -> None:
    add(
        facts.findings,
        "block" if facts.mode == "block" else "warn",
        code,
        message,
        evidence,
    )


def _validate_shape(
    facts: DeriveFacts, raw: dict[str, Any]
) -> tuple[object, object, str, str, str]:
    required = (
        "stable_root_id",
        "item_owner_id",
        "prerequisite_relation_id",
        "strict_local_reduction",
        "semantic_high_water_moved",
        "chain_budget_status",
        "mandatory_successor_kind",
        "selected_successor_kind",
    )
    missing = [field for field in required if raw.get(field) in (None, "")]
    if missing:
        _block(
            facts,
            "derive_prerequisite_chain_fields_missing",
            "Applicable prerequisite chains require stable identity, reduction, budget, and successor fields.",
            {"fields": missing},
        )

    strict = raw.get("strict_local_reduction")
    semantic = raw.get("semantic_high_water_moved")
    if strict not in TRISTATE or semantic not in TRISTATE:
        _block(
            facts,
            "derive_prerequisite_chain_tristate_invalid",
            "Reduction and semantic-high-water values must be true, false, or not_evaluated.",
        )

    budget = str(raw.get("chain_budget_status") or "")
    mandatory = str(raw.get("mandatory_successor_kind") or "")
    selected_successor = str(raw.get("selected_successor_kind") or "")
    if budget not in BUDGET_STATUSES:
        _block(
            facts,
            "derive_prerequisite_chain_budget_invalid",
            "Prerequisite-chain budget status is invalid.",
            {"chain_budget_status": budget},
        )
    if mandatory not in SUCCESSOR_KINDS:
        _block(
            facts,
            "derive_prerequisite_chain_mandatory_successor_invalid",
            "The mandatory post-chain successor must be direct work, descope, terminal, or none.",
            {"mandatory_successor_kind": mandatory},
        )
    if selected_successor not in SELECTED_SUCCESSOR_KINDS:
        _block(
            facts,
            "derive_prerequisite_chain_selected_successor_invalid",
            "The selected successor must explicitly classify prerequisite recursion or a direct successor.",
            {"selected_successor_kind": selected_successor},
        )
    return strict, semantic, budget, mandatory, selected_successor


def _position_at_cap(facts: DeriveFacts, raw: dict[str, Any]) -> bool:
    position = raw.get("chain_position")
    cap = raw.get("chain_cap")
    if position is None and cap is None:
        return False
    valid = (
        isinstance(position, int)
        and not isinstance(position, bool)
        and position >= 1
        and isinstance(cap, int)
        and not isinstance(cap, bool)
        and cap >= 1
        and position <= cap
    )
    if not valid:
        _block(
            facts,
            "derive_prerequisite_chain_cap_invalid",
            "Supplied chain position/cap must be positive and position cannot exceed cap.",
        )
        return False
    return position >= cap


def _check_selected_transition(
    facts: DeriveFacts,
    *,
    strict: object,
    semantic: object,
    budget: str,
    mandatory: str,
    selected_successor: str,
    at_cap: bool,
) -> None:
    outcome = str(facts.result.get("selection_outcome") or "selected")
    if outcome == "selected" and selected_successor == "prerequisite":
        if strict is not True:
            _block(
                facts,
                "derive_nonconvergent_prerequisite_chain_recurred",
                "Another prerequisite task cannot be selected without substantiated strict local reduction.",
            )
        if semantic is not True and budget in {"budget_unverified", "not_evaluated"}:
            _block(
                facts,
                "derive_unverified_prerequisite_budget_recurred",
                "An unverified prerequisite budget cannot authorize another non-semantic prerequisite cycle.",
            )
        if budget == "exhausted" or at_cap:
            _block(
                facts,
                "derive_exhausted_prerequisite_chain_recurred",
                "An exhausted or capped prerequisite chain must transition to its direct successor.",
            )
    if budget == "exhausted" or at_cap:
        if mandatory not in DIRECT_SUCCESSOR_KINDS:
            _block(
                facts,
                "derive_prerequisite_chain_exhausted_without_successor",
                "An exhausted prerequisite chain requires an explicit direct successor.",
            )
        elif selected_successor != mandatory:
            _block(
                facts,
                "derive_prerequisite_chain_successor_not_enforced",
                "The selected task must match the mandatory successor after chain exhaustion.",
                {"mandatory": mandatory, "selected": selected_successor},
            )
    selected_kind = selected_task_kind_value(facts.result)
    if (
        outcome == "selected"
        and selected_successor in DIRECT_SUCCESSOR_KINDS
        and not selected_kind
    ):
        _block(
            facts,
            "derive_prerequisite_chain_selected_task_kind_missing",
            "A direct chain successor requires a concrete selected task kind.",
        )
    elif (
        outcome == "selected"
        and selected_successor in DIRECT_SUCCESSOR_KINDS
        and not successor_task_kind_valid(selected_successor, selected_kind)
    ):
        _block(
            facts,
            "derive_prerequisite_chain_selected_task_kind_mismatch",
            "The concrete selected task kind does not implement the declared direct successor category.",
            {
                "selected_successor_kind": selected_successor,
                "selected_task_kind": selected_kind,
            },
        )


def check_prerequisite_chain(facts: DeriveFacts) -> None:
    """Prevent a bounded prerequisite chain from resetting or recurring vacuously."""

    raw = _chain(facts.result)
    if raw is None:
        return
    if not isinstance(raw, dict):
        _block(
            facts,
            "derive_prerequisite_chain_invalid",
            "`bounded_prerequisite_chain` must be an object when supplied.",
        )
        return
    applicability = str(raw.get("applicability") or "")
    if applicability not in APPLICABILITY:
        _block(
            facts,
            "derive_prerequisite_chain_applicability_invalid",
            "A supplied prerequisite-chain contract requires explicit applicable or not_applicable state.",
        )
        return
    if applicability == "not_applicable":
        if not not_applicable_evidence_valid(raw):
            _block(
                facts,
                "derive_prerequisite_chain_not_applicable_unsubstantiated",
                "A not-applicable chain requires a closed, content-bound reason receipt.",
            )
        return
    strict, semantic, budget, mandatory, selected_successor = _validate_shape(
        facts, raw
    )
    at_cap = _position_at_cap(facts, raw)
    if strict is True and not reduction_observation_valid(raw):
        _block(
            facts,
            "derive_prerequisite_chain_reduction_unsubstantiated",
            "strict_local_reduction=true requires a closed observation receipt bound to a decreasing source revision.",
        )
    _check_selected_transition(
        facts,
        strict=strict,
        semantic=semantic,
        budget=budget,
        mandatory=mandatory,
        selected_successor=selected_successor,
        at_cap=at_cap,
    )
