from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..base import RuleContext
from ..common import add
from .cycle_efficiency_common import (
    EXECUTION_SCOPE_EVIDENCE_FIELDS,
    EXECUTION_SCOPE_FIELDS,
    bounded_id_list,
    bounded_opaque_id,
    nonnegative_int,
)


@dataclass(slots=True)
class StarvationState:
    context: RuleContext
    present: bool
    starvation_status: str
    execution_scope_status: str
    starvation: Any
    run_count: Any
    run_ids: Any
    missing_scope: Any
    run_ids_valid: bool
    run_count_valid: bool
    missing_scope_valid: bool
    starvation_window_valid: bool
    execution_scope_valid: bool
    actual_missing_scope: set[str]


def validate_execution_starvation(context: RuleContext) -> None:
    state = _starvation_state(context)
    _validate_statuses(state)
    _validate_scope_evidence(state)
    _validate_decision(state)


def _starvation_state(context: RuleContext) -> StarvationState:
    result = context.result
    present = any(
        field in result
        for field in (
            "execution_starvation_status",
            "execution_starvation",
            "execution_scope_status",
            "scope_evidence_required",
        )
    )
    starvation_status_value = result.get("execution_starvation_status")
    starvation_status = (
        starvation_status_value.strip().lower()
        if isinstance(starvation_status_value, str)
        else ""
    )
    execution_status_value = result.get("execution_scope_status")
    execution_status = (
        execution_status_value.strip().lower()
        if isinstance(execution_status_value, str)
        else ""
    )
    run_count = result.get("recent_cycle_run_id_count")
    run_ids = result.get("recent_cycle_run_ids")
    missing_scope = result.get("scope_evidence_required")
    run_ids_valid = bounded_id_list(run_ids)
    run_count_valid = nonnegative_int(run_count)
    missing_scope_valid = bool(
        bounded_id_list(missing_scope)
        and set(missing_scope) <= EXECUTION_SCOPE_EVIDENCE_FIELDS
    )
    execution_scope = result.get("execution_scope")
    window = result.get("execution_starvation_window")
    window_valid = bool(
        isinstance(window, int) and not isinstance(window, bool) and window > 0
    )
    execution_scope_valid = bool(
        isinstance(execution_scope, dict)
        and set(execution_scope) == EXECUTION_SCOPE_FIELDS
        and all(
            value in (None, "") or bounded_opaque_id(value) is not None
            for value in execution_scope.values()
        )
    )
    actual_missing = (
        {field for field, value in execution_scope.items() if value in (None, "")}
        if execution_scope_valid
        else set()
    )
    if not window_valid:
        actual_missing.add("execution_starvation_window")
    return StarvationState(
        context,
        present,
        starvation_status,
        execution_status,
        result.get("execution_starvation"),
        run_count,
        run_ids,
        missing_scope,
        run_ids_valid,
        run_count_valid,
        missing_scope_valid,
        window_valid,
        execution_scope_valid,
        actual_missing,
    )


def _validate_statuses(state: StarvationState) -> None:
    if state.present and state.starvation_status not in {
        "present",
        "absent",
        "scope_unknown",
    }:
        add(
            state.context.findings,
            "block",
            "cycle_efficiency_execution_starvation_status_invalid",
            "execution_starvation_status must be present, absent, or scope_unknown.",
        )
    if state.present and state.execution_scope_status not in {
        "evaluated",
        "scope_unknown",
    }:
        add(
            state.context.findings,
            "block",
            "cycle_efficiency_execution_scope_status_invalid",
            "execution_scope_status must be evaluated or scope_unknown.",
        )


def _validate_scope_evidence(state: StarvationState) -> None:
    findings = state.context.findings
    if state.present and not state.execution_scope_valid:
        add(
            findings,
            "block",
            "cycle_efficiency_execution_scope_identity_invalid",
            "Execution scope requires bounded opaque identifiers for its declared fields.",
        )
    if state.present and not state.run_ids_valid:
        add(
            findings,
            "block",
            "cycle_efficiency_recent_run_ids_invalid",
            "Recent run identifiers must be unique bounded opaque strings; raw values are not retained.",
        )
    if state.present and not state.run_count_valid:
        add(
            findings,
            "block",
            "cycle_efficiency_recent_run_count_invalid",
            "recent_cycle_run_id_count must be a nonnegative integer.",
        )
    if (
        state.present
        and state.run_ids_valid
        and state.run_count_valid
        and state.run_count != len(state.run_ids)
    ):
        add(
            findings,
            "block",
            "cycle_efficiency_recent_run_count_mismatch",
            "Recent run count must equal the bounded run-id list cardinality.",
            {
                "declared_count": state.run_count,
                "observed_count": len(state.run_ids),
            },
        )
    if state.present and not state.missing_scope_valid:
        add(
            findings,
            "block",
            "cycle_efficiency_scope_evidence_ids_invalid",
            "scope_evidence_required must contain only unique bounded field identifiers.",
        )
    if (
        state.present
        and state.execution_scope_valid
        and state.missing_scope_valid
        and (
            set(state.missing_scope) != state.actual_missing_scope
            or (
                state.execution_scope_status == "evaluated"
                and state.actual_missing_scope
            )
            or (
                state.execution_scope_status == "scope_unknown"
                and not state.actual_missing_scope
            )
        )
    ):
        add(
            findings,
            "block",
            "cycle_efficiency_scope_evidence_mismatch",
            "Execution-scope status and required evidence must match the exact missing scope fields.",
            {
                "declared_missing_count": len(state.missing_scope),
                "observed_missing_count": len(state.actual_missing_scope),
            },
        )
    if state.present and (
        (
            state.execution_scope_status == "scope_unknown"
            and state.starvation_status != "scope_unknown"
        )
        or (
            state.execution_scope_status == "evaluated"
            and state.starvation_status == "scope_unknown"
        )
        or (
            state.starvation_status in {"present", "absent"}
            and state.execution_scope_status != "evaluated"
        )
    ):
        add(
            findings,
            "block",
            "cycle_efficiency_scope_starvation_status_conflict",
            "Execution scope and starvation statuses must describe the same decision state.",
        )


def _validate_decision(state: StarvationState) -> None:
    if not state.present:
        return
    if state.starvation_status == "scope_unknown":
        _validate_scope_unknown(state)
    elif state.starvation_status == "present" and not _present_consistent(state):
        add(
            state.context.findings,
            "block",
            "cycle_efficiency_starvation_present_inconsistent",
            "present starvation requires zero fresh run ids and an execution-candidate priority boost.",
        )
    elif state.starvation_status == "absent" and not _absent_consistent(state):
        add(
            state.context.findings,
            "block",
            "cycle_efficiency_starvation_absent_inconsistent",
            "absent starvation requires at least one fresh scoped run id.",
        )


def _validate_scope_unknown(state: StarvationState) -> None:
    result = state.context.result
    if (
        state.starvation is not None
        or not state.missing_scope_valid
        or not state.missing_scope
        or (state.run_count_valid and state.run_count != 0)
        or (state.run_ids_valid and bool(state.run_ids))
        or result.get("execution_candidate_priority_boost") is True
    ):
        add(
            state.context.findings,
            "block",
            "cycle_efficiency_scope_unknown_contract_invalid",
            "scope_unknown requires a null starvation decision and explicit missing scope fields.",
        )
    recommendations = result.get("recommendations")
    values = {
        item.strip()
        for item in (
            recommendations
            if isinstance(recommendations, list)
            else [result.get("recommendation")]
        )
        if isinstance(item, str) and item.strip()
    }
    if "supply_evidence_path" not in values:
        add(
            state.context.findings,
            "block",
            "cycle_efficiency_scope_unknown_auto_continue",
            "scope_unknown requires scope recovery in the recommendation set before automatic continuation or terminal routing.",
        )


def _present_consistent(state: StarvationState) -> bool:
    return bool(
        state.execution_scope_status == "evaluated"
        and state.starvation is True
        and not state.actual_missing_scope
        and state.starvation_window_valid
        and state.run_count_valid
        and state.run_count == 0
        and state.run_ids_valid
        and not state.run_ids
        and state.missing_scope_valid
        and not state.missing_scope
        and state.context.result.get("execution_candidate_priority_boost") is True
    )


def _absent_consistent(state: StarvationState) -> bool:
    return bool(
        state.execution_scope_status == "evaluated"
        and state.starvation is False
        and not state.actual_missing_scope
        and state.starvation_window_valid
        and state.run_count_valid
        and state.run_count > 0
        and state.run_ids_valid
        and len(state.run_ids) == state.run_count
        and state.missing_scope_valid
        and not state.missing_scope
        and state.context.result.get("execution_candidate_priority_boost") is False
    )
