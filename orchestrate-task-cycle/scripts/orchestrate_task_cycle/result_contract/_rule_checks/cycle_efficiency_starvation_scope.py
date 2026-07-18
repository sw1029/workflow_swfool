"""Scope-evidence checks for the execution-starvation result contract."""

from __future__ import annotations

from typing import Any

from ..common import add
from .cycle_efficiency_common import bounded_opaque_id


def validate_scope_evidence(state: Any) -> None:
    """Validate identity, run, binding, missing-field, and status alignment."""

    _validate_identity_and_bindings(state)
    _validate_run_cardinality(state)
    _validate_missing_scope(state)
    _validate_status_alignment(state)


def _validate_identity_and_bindings(state: Any) -> None:
    findings = state.context.findings
    if (
        state.present
        and state.applicability == "excluded_by_task"
        and bounded_opaque_id(state.exclusion_reason) is None
    ):
        add(
            findings,
            "block",
            "cycle_efficiency_execution_scope_exclusion_invalid",
            "excluded_by_task requires a bounded reason and preserves present starvation instead of bypassing producer routing.",
        )
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
    if state.present and not state.run_receipts_valid:
        add(
            findings,
            "block",
            "cycle_efficiency_recent_run_receipts_invalid",
            "Bound execution requires unique content-bound producer-run receipts with valid canonical digests.",
        )
    if (
        state.present
        and state.applicability == "applicable"
        and not state.required_input_binding_valid
    ):
        add(
            findings,
            "block",
            "cycle_efficiency_required_input_binding_missing",
            "Applicable execution scope requires an exact input revision and full content digest.",
        )
    if (
        state.present
        and not state.required_input_binding_absent
        and not state.required_input_binding_valid
    ):
        add(
            findings,
            "block",
            "cycle_efficiency_required_input_binding_invalid",
            "A declared required-input binding must contain one bounded revision ID and full lowercase SHA-256 digest.",
        )


def _validate_run_cardinality(state: Any) -> None:
    findings = state.context.findings
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


def _validate_missing_scope(state: Any) -> None:
    findings = state.context.findings
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


def _validate_status_alignment(state: Any) -> None:
    if not state.present:
        return
    conflict = bool(
        (
            state.execution_scope_status == "scope_unknown"
            and state.starvation_status != "scope_unknown"
        )
        or (
            state.execution_scope_status == "evaluated"
            and state.starvation_status == "scope_unknown"
        )
        or (
            state.starvation_status == "absent"
            and state.execution_scope_status != "evaluated"
        )
        or (
            state.starvation_status == "present"
            and state.execution_scope_status not in {"evaluated", "excluded_by_task"}
        )
        or (
            state.starvation_status == "not_applicable"
            and state.execution_scope_status != "not_applicable"
        )
        or (
            state.applicability == "excluded_by_task"
            and (
                state.execution_scope_status != "excluded_by_task"
                or state.starvation_status != "present"
            )
        )
        or (
            state.execution_scope_status == "excluded_by_task"
            and state.applicability != "excluded_by_task"
        )
        or (
            state.applicability == "not_applicable"
            and (
                state.execution_scope_status != "not_applicable"
                or state.starvation_status != "not_applicable"
            )
        )
        or (
            state.execution_scope_status == "not_applicable"
            and state.applicability != "not_applicable"
        )
    )
    if conflict:
        add(
            state.context.findings,
            "block",
            "cycle_efficiency_scope_starvation_status_conflict",
            "Execution scope and starvation statuses must describe the same decision state.",
        )


__all__ = ("validate_scope_evidence",)
