from __future__ import annotations

from .shared import (
    EXECUTION_SCOPE_RECOVERY_TASK_KINDS,
    EXECUTION_STARVATION_TASK_KINDS,
    EXECUTION_STARVATION_STATUSES,
    _bounded_id_items,
    _bounded_opaque_id,
    _declared_values,
    add,
)
from .goal_stagnation_projection import check_goal_projection
from .state import DeriveFacts


def _starvation_status_surface(facts: DeriveFacts) -> tuple[set[str], bool, bool]:
    result = facts.result
    mode = facts.mode
    findings = facts.findings
    starvation_status_paths = (
        "execution_starvation_status",
        "cycle_efficiency_profile.execution_starvation_status",
        "anti_loop_progress_gate.execution_starvation_status",
        "anti_loop_progress_gate.cycle_efficiency_profile.execution_starvation_status",
        "result.cycle_efficiency_profile.execution_starvation_status",
    )
    starvation_status_values = _declared_values(
        result,
        starvation_status_paths,
    )
    normalized_starvation_status_items = [
        text.lower()
        for value in starvation_status_values
        if (text := _bounded_opaque_id(value)) is not None
        and text.lower() in EXECUTION_STARVATION_STATUSES
    ]
    normalized_starvation_statuses = set(normalized_starvation_status_items)
    starvation_status_malformed = len(normalized_starvation_status_items) != len(
        starvation_status_values
    )
    starvation_status_conflict = len(normalized_starvation_statuses) > 1
    if starvation_status_malformed:
        add(
            findings,
            "warn",
            "derive_execution_starvation_status_malformed",
            "Malformed execution-starvation status is consumed conservatively as scope_unknown; raw input is not retained.",
        )
    if starvation_status_conflict:
        add(
            findings,
            "block" if mode == "block" else "warn",
            "derive_execution_starvation_status_conflict",
            "Duplicate execution-starvation status surfaces must converge before derive consumes them.",
        )
    return (
        normalized_starvation_statuses,
        starvation_status_malformed,
        starvation_status_conflict,
    )


def _scope_status_surface(facts: DeriveFacts) -> tuple[set[str], bool, bool]:
    result = facts.result
    mode = facts.mode
    findings = facts.findings
    scope_status_values = _declared_values(
        result,
        (
            "execution_scope_status",
            "cycle_efficiency_profile.execution_scope_status",
            "anti_loop_progress_gate.execution_scope_status",
            "anti_loop_progress_gate.cycle_efficiency_profile.execution_scope_status",
            "result.cycle_efficiency_profile.execution_scope_status",
        ),
    )
    normalized_scope_status_items = [
        text.lower()
        for value in scope_status_values
        if (text := _bounded_opaque_id(value)) is not None
        and text.lower()
        in {"evaluated", "scope_unknown", "excluded_by_task", "not_applicable"}
    ]
    normalized_scope_statuses = set(normalized_scope_status_items)
    scope_status_malformed = len(normalized_scope_status_items) != len(
        scope_status_values
    )
    scope_status_conflict = len(normalized_scope_statuses) > 1
    if scope_status_malformed:
        add(
            findings,
            "warn",
            "derive_execution_scope_status_malformed",
            "Malformed execution-scope status is consumed conservatively as scope_unknown; raw input is not retained.",
        )
    if scope_status_conflict:
        add(
            findings,
            "block" if mode == "block" else "warn",
            "derive_execution_scope_status_conflict",
            "Duplicate execution-scope status surfaces must converge before derive consumes them.",
        )
    return normalized_scope_statuses, scope_status_malformed, scope_status_conflict


def _scope_starvation_conflict(
    facts: DeriveFacts,
    starvation_statuses: set[str],
    scope_statuses: set[str],
) -> bool:
    mode = facts.mode
    findings = facts.findings
    scope_starvation_status_conflict = bool(
        (
            "scope_unknown" in scope_statuses
            and starvation_statuses & {"present", "absent"}
        )
        or ("evaluated" in scope_statuses and "scope_unknown" in starvation_statuses)
    )
    if scope_starvation_status_conflict:
        add(
            findings,
            "block" if mode == "block" else "warn",
            "derive_execution_scope_status_conflict",
            "Execution-scope and starvation status surfaces must describe the same decision state.",
        )
    return scope_starvation_status_conflict


def _scope_evidence_surface(facts: DeriveFacts) -> set[str]:
    result = facts.result
    mode = facts.mode
    findings = facts.findings
    scope_evidence_values = _declared_values(
        result,
        (
            "scope_evidence_required",
            "cycle_efficiency_profile.scope_evidence_required",
            "anti_loop_progress_gate.scope_evidence_required",
            "anti_loop_progress_gate.cycle_efficiency_profile.scope_evidence_required",
            "result.cycle_efficiency_profile.scope_evidence_required",
        ),
    )
    normalized_scope_evidence = [
        _bounded_id_items(value) for value in scope_evidence_values
    ]
    scope_evidence_malformed = any(not valid for _, valid in normalized_scope_evidence)
    scope_evidence_sets = {
        tuple(sorted(items)) for items, valid in normalized_scope_evidence if valid
    }
    scope_evidence_conflict = len(scope_evidence_sets) > 1
    scope_evidence_required = set(next(iter(scope_evidence_sets), ()))
    if scope_evidence_malformed or scope_evidence_conflict:
        add(
            findings,
            "block" if mode == "block" else "warn",
            "derive_execution_scope_evidence_conflict",
            "Scope-evidence requirements must be bounded and converge across duplicate profile surfaces.",
        )
    return scope_evidence_required


def _applicability_surface(facts: DeriveFacts) -> tuple[set[str], bool]:
    values = _declared_values(
        facts.result,
        (
            "execution_scope_applicability",
            "cycle_efficiency_profile.execution_scope_applicability",
            "anti_loop_progress_gate.execution_scope_applicability",
            "anti_loop_progress_gate.cycle_efficiency_profile.execution_scope_applicability",
            "result.cycle_efficiency_profile.execution_scope_applicability",
        ),
    )
    normalized_items = [
        text.lower()
        for value in values
        if (text := _bounded_opaque_id(value)) is not None
        and text.lower()
        in {
            "applicable",
            "excluded_by_task",
            "not_applicable",
            "legacy_unspecified",
            "scope_unknown",
        }
    ]
    statuses = set(normalized_items)
    malformed = len(normalized_items) != len(values) or len(statuses) > 1
    if malformed:
        add(
            facts.findings,
            "block" if facts.mode == "block" else "warn",
            "derive_execution_scope_applicability_conflict",
            "Execution-scope applicability must be bounded and converge across profile surfaces.",
        )
    return statuses, malformed


def _disposition_reason_valid(facts: DeriveFacts, applicability: set[str]) -> bool:
    if not applicability & {"excluded_by_task", "not_applicable"}:
        return True
    values = _declared_values(
        facts.result,
        (
            "execution_scope_exclusion_reason_id",
            "cycle_efficiency_profile.execution_scope_exclusion_reason_id",
            "anti_loop_progress_gate.execution_scope_exclusion_reason_id",
            "anti_loop_progress_gate.cycle_efficiency_profile.execution_scope_exclusion_reason_id",
            "result.cycle_efficiency_profile.execution_scope_exclusion_reason_id",
        ),
    )
    normalized = [text for value in values if (text := _bounded_opaque_id(value))]
    valid = bool(
        normalized and len(normalized) == len(values) and len(set(normalized)) == 1
    )
    if not valid:
        add(
            facts.findings,
            "block" if facts.mode == "block" else "warn",
            "derive_execution_scope_disposition_reason_invalid",
            "Task exclusion and intrinsic non-applicability require one convergent bounded reason identifier.",
        )
    return valid


def _check_scope_decision(
    facts: DeriveFacts,
    starvation_statuses: set[str],
    starvation_status_malformed: bool,
    starvation_status_conflict: bool,
    scope_statuses: set[str],
    scope_status_malformed: bool,
    scope_status_conflict: bool,
    scope_starvation_status_conflict: bool,
    scope_evidence_required: set[str],
    applicability_statuses: set[str],
    applicability_malformed: bool,
    disposition_reason_valid: bool,
) -> None:
    mode = facts.mode
    findings = facts.findings
    execution_scope_unknown = bool(
        starvation_status_malformed
        or starvation_status_conflict
        or scope_status_malformed
        or scope_status_conflict
        or scope_starvation_status_conflict
        or applicability_malformed
        or not disposition_reason_valid
        or "scope_unknown" in applicability_statuses
        or "scope_unknown" in starvation_statuses
        or "scope_unknown" in scope_statuses
        or scope_evidence_required
    )
    execution_starvation_status = (
        "scope_unknown"
        if execution_scope_unknown
        else next(iter(starvation_statuses), "")
    )
    if "evaluated" in scope_statuses and scope_evidence_required:
        add(
            findings,
            "block" if mode == "block" else "warn",
            "derive_execution_scope_evidence_conflict",
            "Evaluated execution scope cannot retain unresolved scope-evidence requirements.",
        )
    if execution_starvation_status == "scope_unknown" and not scope_evidence_required:
        add(
            findings,
            "block" if mode == "block" else "warn",
            "derive_execution_scope_evidence_missing",
            "scope_unknown requires bounded scope-evidence fields before a recovery task can be selected.",
        )
    if execution_starvation_status == "scope_unknown" and (
        facts.terminal_selected
        or facts.selected_kind not in EXECUTION_SCOPE_RECOVERY_TASK_KINDS
    ):
        add(
            findings,
            "block" if mode == "block" else "warn",
            "derive_execution_scope_unknown_unrecovered",
            "Execution scope_unknown permits only bounded scope-evidence recovery; terminal and ordinary continuation remain unavailable.",
            {
                "terminal_selected": facts.terminal_selected,
                "recovery_kind_selected": facts.selected_kind
                in EXECUTION_SCOPE_RECOVERY_TASK_KINDS,
            },
        )
    excluded = "excluded_by_task" in applicability_statuses
    intrinsically_not_applicable = "not_applicable" in applicability_statuses
    if (
        (
            excluded
            and (
                execution_starvation_status != "present"
                or "excluded_by_task" not in scope_statuses
            )
        )
        or (
            execution_starvation_status == "not_applicable"
            and (
                not intrinsically_not_applicable
                or "not_applicable" not in scope_statuses
            )
        )
        or (
            intrinsically_not_applicable
            and (
                execution_starvation_status != "not_applicable"
                or "not_applicable" not in scope_statuses
            )
        )
    ):
        add(
            findings,
            "block" if mode == "block" else "warn",
            "derive_execution_scope_exclusion_conflict",
            "excluded_by_task is an active producer-scope conflict and must preserve present starvation; only intrinsic not_applicable may bypass producer routing.",
        )
    outcome = str(facts.result.get("selection_outcome") or "").strip().lower()
    genuine_terminal = outcome in {"terminal_blocked", "user_escalation"}
    if execution_starvation_status == "present" and not genuine_terminal:
        if (
            outcome != "selected"
            or facts.selected_kind not in EXECUTION_STARVATION_TASK_KINDS
        ):
            add(
                findings,
                "block" if mode == "block" else "warn",
                "derive_execution_starvation_unhandled",
                "Present execution starvation permits execution-producing work, producer reconciliation, explicit residual descope, or a separately valid terminal/escalation outcome; another guard, report, or metadata successor is not ordinary progress.",
                {
                    "selection_outcome": outcome or None,
                    "selected_task_kind": facts.selected_kind or None,
                },
            )


def check_execution_scope(facts: DeriveFacts) -> None:
    starvation_statuses, starvation_malformed, starvation_conflict = (
        _starvation_status_surface(facts)
    )
    scope_statuses, scope_malformed, scope_conflict = _scope_status_surface(facts)
    cross_surface_conflict = _scope_starvation_conflict(
        facts, starvation_statuses, scope_statuses
    )
    scope_evidence_required = _scope_evidence_surface(facts)
    applicability_statuses, applicability_malformed = _applicability_surface(facts)
    disposition_reason_valid = _disposition_reason_valid(facts, applicability_statuses)
    _check_scope_decision(
        facts,
        starvation_statuses,
        starvation_malformed,
        starvation_conflict,
        scope_statuses,
        scope_malformed,
        scope_conflict,
        cross_surface_conflict,
        scope_evidence_required,
        applicability_statuses,
        applicability_malformed,
        disposition_reason_valid,
    )
    goal_projection_values = _declared_values(
        facts.result,
        (
            "goal_axis_stagnation_projection",
            "cycle_efficiency_profile.goal_axis_stagnation_projection",
            "anti_loop_progress_gate.goal_axis_stagnation_projection",
            "anti_loop_progress_gate.cycle_efficiency_profile.goal_axis_stagnation_projection",
            "result.cycle_efficiency_profile.goal_axis_stagnation_projection",
        ),
    )
    if goal_projection_values:
        check_goal_projection(facts, goal_projection_values)
