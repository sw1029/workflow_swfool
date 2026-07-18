from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..base import RuleContext
from ..common import add
from ...cycle_efficiency.producer_receipts import (
    APPLICABILITY_VALUES,
    normalize_producer_run_receipt,
)
from .cycle_efficiency_common import (
    EXECUTION_SCOPE_EVIDENCE_FIELDS,
    EXECUTION_SCOPE_FIELDS,
    bounded_id_list,
    bounded_opaque_id,
    nonnegative_int,
)
from .cycle_efficiency_starvation_scope import validate_scope_evidence


@dataclass(slots=True)
class StarvationState:
    context: RuleContext
    present: bool
    starvation_status: str
    execution_scope_status: str
    applicability: str
    exclusion_reason: Any
    starvation: Any
    run_count: Any
    run_ids: Any
    run_receipts: Any
    required_input_binding: Any
    missing_scope: Any
    run_ids_valid: bool
    run_receipts_valid: bool
    required_input_binding_valid: bool
    required_input_binding_absent: bool
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
    run_receipts = result.get("recent_cycle_run_receipts")
    applicability_value = result.get("execution_scope_applicability")
    applicability = (
        applicability_value.strip().lower()
        if isinstance(applicability_value, str)
        else "legacy_unspecified"
        if applicability_value is None
        else ""
    )
    required_binding = result.get("required_input_binding")
    required_binding_absent = required_binding is None
    required_binding_valid = bool(
        isinstance(required_binding, dict)
        and set(required_binding) == {"revision_id", "content_digest"}
        and bounded_opaque_id(required_binding.get("revision_id")) is not None
        and isinstance(required_binding.get("content_digest"), str)
        and len(required_binding["content_digest"]) == 64
        and all(
            character in "0123456789abcdef"
            for character in required_binding["content_digest"]
        )
    )
    legacy_receipts_omitted = bool(
        "recent_cycle_run_receipts" not in result
        and applicability == "legacy_unspecified"
        and required_binding_absent
    )
    run_receipts_valid = legacy_receipts_omitted or bool(
        isinstance(run_receipts, list)
        and all(
            normalize_producer_run_receipt(item) is not None for item in run_receipts
        )
        and len(
            {
                normalized["run_id"]
                for item in run_receipts
                if (normalized := normalize_producer_run_receipt(item)) is not None
            }
        )
        == len(run_receipts)
    )
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
    if applicability == "scope_unknown":
        actual_missing.add("execution_scope_applicability")
    if (applicability == "applicable" and not required_binding_valid) or (
        not required_binding_absent and not required_binding_valid
    ):
        actual_missing.add("required_input_binding")
    if applicability in {"excluded_by_task", "not_applicable"}:
        actual_missing.clear()
    return StarvationState(
        context,
        present,
        starvation_status,
        execution_status,
        applicability,
        result.get("execution_scope_exclusion_reason_id"),
        result.get("execution_starvation"),
        run_count,
        run_ids,
        run_receipts,
        required_binding,
        missing_scope,
        run_ids_valid,
        run_receipts_valid,
        required_binding_valid,
        required_binding_absent,
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
        "not_applicable",
    }:
        add(
            state.context.findings,
            "block",
            "cycle_efficiency_execution_starvation_status_invalid",
            "execution_starvation_status must be present, absent, scope_unknown, or not_applicable.",
        )
    if state.present and state.execution_scope_status not in {
        "evaluated",
        "scope_unknown",
        "excluded_by_task",
        "not_applicable",
    }:
        add(
            state.context.findings,
            "block",
            "cycle_efficiency_execution_scope_status_invalid",
            "execution_scope_status must be evaluated, scope_unknown, excluded_by_task, or not_applicable.",
        )
    if state.present and state.applicability not in APPLICABILITY_VALUES:
        add(
            state.context.findings,
            "block",
            "cycle_efficiency_execution_scope_applicability_invalid",
            "Execution-scope applicability must be applicable, excluded_by_task, not_applicable, legacy_unspecified, or scope_unknown.",
        )


def _validate_scope_evidence(state: StarvationState) -> None:
    validate_scope_evidence(state)


def _validate_decision(state: StarvationState) -> None:
    if not state.present:
        return
    if state.starvation_status == "scope_unknown":
        _validate_scope_unknown(state)
    elif state.starvation_status == "not_applicable":
        _validate_not_applicable(state)
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
        or (
            state.run_receipts_valid
            and isinstance(state.run_receipts, list)
            and bool(state.run_receipts)
        )
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


def _validate_not_applicable(state: StarvationState) -> None:
    result = state.context.result
    valid = bool(
        state.applicability == "not_applicable"
        and state.execution_scope_status == "not_applicable"
        and bounded_opaque_id(state.exclusion_reason) is not None
        and state.starvation is None
        and state.run_count_valid
        and state.run_count == 0
        and state.run_ids_valid
        and not state.run_ids
        and state.run_receipts_valid
        and isinstance(state.run_receipts, list)
        and not state.run_receipts
        and state.missing_scope_valid
        and not state.missing_scope
        and state.required_input_binding_absent
        and result.get("execution_starvation_window") is None
        and result.get("execution_candidate_priority_boost") is False
    )
    if not valid:
        add(
            state.context.findings,
            "block",
            "cycle_efficiency_execution_scope_not_applicable_invalid",
            "not_applicable is a reason-bound intrinsic bypass with no run, binding, starvation, or terminal claim.",
        )


def _receipts_match_binding(state: StarvationState) -> bool:
    if state.required_input_binding_absent:
        return bool(
            state.applicability == "legacy_unspecified"
            and (
                state.run_receipts is None
                or isinstance(state.run_receipts, list)
                and not state.run_receipts
            )
        )
    if not state.required_input_binding_valid or not isinstance(
        state.run_receipts, list
    ):
        return False
    normalized = [normalize_producer_run_receipt(item) for item in state.run_receipts]
    if any(item is None for item in normalized):
        return False
    binding = state.required_input_binding
    return bool(
        len(normalized) == state.run_count
        and {str(item["run_id"]) for item in normalized if item is not None}
        == set(state.run_ids)
        and all(
            item is not None
            and item["input_revision_id"] == binding["revision_id"]
            and item["input_digest"] == binding["content_digest"]
            for item in normalized
        )
    )


def _present_consistent(state: StarvationState) -> bool:
    excluded_by_task = state.applicability == "excluded_by_task"
    return bool(
        state.execution_scope_status
        == ("excluded_by_task" if excluded_by_task else "evaluated")
        and (
            bounded_opaque_id(state.exclusion_reason) is not None
            if excluded_by_task
            else True
        )
        and state.starvation is True
        and not state.actual_missing_scope
        and state.starvation_window_valid
        and state.run_count_valid
        and state.run_count == 0
        and state.run_ids_valid
        and not state.run_ids
        and state.run_receipts_valid
        and (
            state.run_receipts is None
            or isinstance(state.run_receipts, list)
            and not state.run_receipts
        )
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
        and state.run_receipts_valid
        and _receipts_match_binding(state)
        and state.missing_scope_valid
        and not state.missing_scope
        and state.context.result.get("execution_candidate_priority_boost") is False
    )
