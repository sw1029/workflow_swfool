from __future__ import annotations

import re

from ..base import RuleContext, TargetContractRule
from ..common import add


ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
STATUSES = {"ok", "warn", "blocked"}
RECOMMENDATIONS = {
    "continue",
    "batch_micro_contracts",
    "supply_evidence_path",
    "bounded_preflight",
    "supply_evidence_path_or_bounded_preflight",
    "resume_primary_output",
    "root_cause_repair_or_stop_with_blocker",
    "narrow_scope",
    "register_consolidation_candidate",
    "stop_with_blocker",
    "consume_or_reorder_task_pack_or_terminal_block",
    "route_validation_set_plan_or_build",
}
BASIS_LIST_FIELDS = {"unique_new_artifact_ids", "unique_unchanged_artifact_ids", "fresh_stage_event_ids"}
OPAQUE_ID_MAX_LENGTH = 128
PROFILE_SCOPE_FIELDS = {
    "goal_axis",
    "root_family_key",
    "producer_lineage",
    "artifact_class",
    "decision_lane",
    "input_cohort",
}
EXECUTION_SCOPE_FIELDS = {"goal_axis", "producer_lineage", "artifact_class", "decision_lane"}
EXECUTION_SCOPE_EVIDENCE_FIELDS = EXECUTION_SCOPE_FIELDS | {"execution_starvation_window"}


def _bounded_opaque_id(value: object, *, path_safe: bool = False) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text or len(text) > OPAQUE_ID_MAX_LENGTH:
        return None
    if any(ord(character) < 32 or ord(character) == 127 for character in text):
        return None
    if path_safe and not ID_PATTERN.fullmatch(text):
        return None
    return text


def _bounded_id_list(value: object, *, allow_empty: bool = True) -> bool:
    return bool(
        isinstance(value, list)
        and (allow_empty or value)
        and all(_bounded_opaque_id(item) is not None for item in value)
        and len(value) == len(set(value))
    )


def _nonnegative_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


class CycleEfficiencyProfileRule(TargetContractRule):
    """Reject fabricated or structurally empty efficiency-profile envelopes."""

    targets = frozenset({"cycle_efficiency_profile"})

    def check(self, context: RuleContext) -> None:
        result = context.result
        severity = "block"
        task_id = _bounded_opaque_id(result.get("task_id"), path_safe=True)
        if task_id is None:
            add(context.findings, severity, "cycle_efficiency_task_id_invalid", "Cycle-efficiency task_id must be one bounded path-safe token.")
        status_value = result.get("status")
        status = status_value.strip().lower() if isinstance(status_value, str) else ""
        if status not in STATUSES:
            add(context.findings, severity, "cycle_efficiency_status_invalid", "Cycle-efficiency status is outside the closed vocabulary.", {"allowed": sorted(STATUSES)})
        cost = result.get("cycle_fixed_cost")
        if isinstance(cost, bool) or not isinstance(cost, (int, float)) or cost < 0:
            add(context.findings, severity, "cycle_efficiency_cost_invalid", "cycle_fixed_cost must be a nonnegative number.")
        basis = result.get("cycle_cost_basis")
        if (
            not isinstance(basis, dict)
            or any(
                not isinstance(basis.get(field), list)
                or any(not isinstance(item, str) or not item.strip() for item in basis.get(field) or [])
                for field in BASIS_LIST_FIELDS
            )
            or not isinstance(basis.get("denominator"), str)
            or not basis.get("denominator", "").strip()
        ):
            add(
                context.findings,
                severity,
                "cycle_efficiency_cost_basis_invalid",
                "cycle_cost_basis must include the three identity lists and a non-empty denominator description.",
                {"required_list_fields": sorted(BASIS_LIST_FIELDS)},
            )
        elif isinstance(cost, (int, float)) and not isinstance(cost, bool):
            expected_floor = max(
                1,
                len(set(str(item) for item in basis.get("unique_new_artifact_ids") or []))
                + len(set(str(item) for item in basis.get("fresh_stage_event_ids") or [])),
            )
            if cost < expected_floor:
                add(
                    context.findings,
                    severity,
                    "cycle_efficiency_cost_below_observed_basis",
                    "cycle_fixed_cost must not be smaller than the observable artifact and stage-event basis.",
                    {"cycle_fixed_cost": cost, "observed_basis_floor": expected_floor},
                )
        scope_unverified = result.get("profile_scope_unverified")
        if not isinstance(scope_unverified, bool):
            add(
                context.findings,
                severity,
                "cycle_efficiency_scope_status_missing",
                "Cycle-efficiency profiles require an explicit boolean profile_scope_unverified field.",
            )
        if scope_unverified is True and result.get("family_scoped_hard_gate") is True:
            add(
                context.findings,
                severity,
                "cycle_efficiency_unverified_family_hard_gate",
                "An unverified family scope cannot emit a current-family hard gate.",
            )
        profile_scope = result.get("profile_scope")
        if isinstance(profile_scope, dict):
            malformed_profile_scope = [
                field
                for field, value in profile_scope.items()
                if field not in PROFILE_SCOPE_FIELDS
                or value not in (None, "") and _bounded_opaque_id(value) is None
            ]
            if malformed_profile_scope or (
                scope_unverified is False
                and (
                    set(profile_scope) != PROFILE_SCOPE_FIELDS
                    or any(_bounded_opaque_id(value) is None for value in profile_scope.values())
                )
            ):
                add(
                    context.findings,
                    severity,
                    "cycle_efficiency_profile_scope_identity_invalid",
                    "Profile scope identifiers must be bounded opaque strings; raw values are not retained.",
                    {"invalid_field_count": len(malformed_profile_scope)},
                )
        elif profile_scope is not None:
            add(
                context.findings,
                severity,
                "cycle_efficiency_profile_scope_identity_invalid",
                "Profile scope must be a bounded identifier mapping.",
            )
        starvation_contract_present = any(
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
        execution_scope_status_value = result.get("execution_scope_status")
        execution_scope_status = (
            execution_scope_status_value.strip().lower()
            if isinstance(execution_scope_status_value, str)
            else ""
        )
        if starvation_contract_present and starvation_status not in {"present", "absent", "scope_unknown"}:
            add(
                context.findings,
                severity,
                "cycle_efficiency_execution_starvation_status_invalid",
                "execution_starvation_status must be present, absent, or scope_unknown.",
            )
        if starvation_contract_present and execution_scope_status not in {"evaluated", "scope_unknown"}:
            add(
                context.findings,
                severity,
                "cycle_efficiency_execution_scope_status_invalid",
                "execution_scope_status must be evaluated or scope_unknown.",
            )
        starvation = result.get("execution_starvation")
        run_count = result.get("recent_cycle_run_id_count")
        run_ids = result.get("recent_cycle_run_ids")
        missing_scope = result.get("scope_evidence_required")
        run_ids_valid = _bounded_id_list(run_ids)
        run_count_valid = _nonnegative_int(run_count)
        missing_scope_valid = bool(
            _bounded_id_list(missing_scope)
            and set(missing_scope) <= EXECUTION_SCOPE_EVIDENCE_FIELDS
        )
        execution_scope = result.get("execution_scope")
        starvation_window = result.get("execution_starvation_window")
        starvation_window_valid = bool(
            isinstance(starvation_window, int)
            and not isinstance(starvation_window, bool)
            and starvation_window > 0
        )
        execution_scope_mapping_valid = bool(
            isinstance(execution_scope, dict)
            and set(execution_scope) == EXECUTION_SCOPE_FIELDS
            and all(
                value in (None, "") or _bounded_opaque_id(value) is not None
                for value in execution_scope.values()
            )
        )
        actual_missing_scope = (
            {
                field
                for field, value in execution_scope.items()
                if value in (None, "")
            }
            if execution_scope_mapping_valid
            else set()
        )
        if not starvation_window_valid:
            actual_missing_scope.add("execution_starvation_window")
        if starvation_contract_present and not execution_scope_mapping_valid:
            add(
                context.findings,
                severity,
                "cycle_efficiency_execution_scope_identity_invalid",
                "Execution scope requires bounded opaque identifiers for its declared fields.",
            )
        if starvation_contract_present and not run_ids_valid:
            add(
                context.findings,
                severity,
                "cycle_efficiency_recent_run_ids_invalid",
                "Recent run identifiers must be unique bounded opaque strings; raw values are not retained.",
            )
        if starvation_contract_present and not run_count_valid:
            add(
                context.findings,
                severity,
                "cycle_efficiency_recent_run_count_invalid",
                "recent_cycle_run_id_count must be a nonnegative integer.",
            )
        if starvation_contract_present and run_ids_valid and run_count_valid and run_count != len(run_ids):
            add(
                context.findings,
                severity,
                "cycle_efficiency_recent_run_count_mismatch",
                "Recent run count must equal the bounded run-id list cardinality.",
                {"declared_count": run_count, "observed_count": len(run_ids)},
            )
        if starvation_contract_present and not missing_scope_valid:
            add(
                context.findings,
                severity,
                "cycle_efficiency_scope_evidence_ids_invalid",
                "scope_evidence_required must contain only unique bounded field identifiers.",
            )
        if starvation_contract_present and execution_scope_mapping_valid and missing_scope_valid and (
            set(missing_scope) != actual_missing_scope
            or (execution_scope_status == "evaluated" and actual_missing_scope)
            or (execution_scope_status == "scope_unknown" and not actual_missing_scope)
        ):
            add(
                context.findings,
                severity,
                "cycle_efficiency_scope_evidence_mismatch",
                "Execution-scope status and required evidence must match the exact missing scope fields.",
                {
                    "declared_missing_count": len(missing_scope),
                    "observed_missing_count": len(actual_missing_scope),
                },
            )
        if starvation_contract_present and (
            (execution_scope_status == "scope_unknown" and starvation_status != "scope_unknown")
            or (execution_scope_status == "evaluated" and starvation_status == "scope_unknown")
            or (starvation_status in {"present", "absent"} and execution_scope_status != "evaluated")
        ):
            add(
                context.findings,
                severity,
                "cycle_efficiency_scope_starvation_status_conflict",
                "Execution scope and starvation statuses must describe the same decision state.",
            )
        if starvation_contract_present and starvation_status == "scope_unknown":
            if (
                starvation is not None
                or not missing_scope_valid
                or not missing_scope
                or (run_count_valid and run_count != 0)
                or (run_ids_valid and bool(run_ids))
                or result.get("execution_candidate_priority_boost") is True
            ):
                add(
                    context.findings,
                    severity,
                    "cycle_efficiency_scope_unknown_contract_invalid",
                    "scope_unknown requires a null starvation decision and explicit missing scope fields.",
                )
            recommendations = result.get("recommendations")
            recommendation_values = {
                item.strip()
                for item in (recommendations if isinstance(recommendations, list) else [result.get("recommendation")])
                if isinstance(item, str) and item.strip()
            }
            if "supply_evidence_path" not in recommendation_values:
                add(
                    context.findings,
                    severity,
                    "cycle_efficiency_scope_unknown_auto_continue",
                    "scope_unknown requires scope recovery in the recommendation set before automatic continuation or terminal routing.",
                )
        elif starvation_contract_present and starvation_status == "present" and not (
            execution_scope_status == "evaluated"
            and starvation is True
            and not actual_missing_scope
            and starvation_window_valid
            and run_count_valid
            and run_count == 0
            and run_ids_valid
            and not run_ids
            and missing_scope_valid
            and not missing_scope
            and result.get("execution_candidate_priority_boost") is True
        ):
            add(
                context.findings,
                severity,
                "cycle_efficiency_starvation_present_inconsistent",
                "present starvation requires zero fresh run ids and an execution-candidate priority boost.",
            )
        elif starvation_contract_present and starvation_status == "absent" and not (
            execution_scope_status == "evaluated"
            and starvation is False
            and not actual_missing_scope
            and starvation_window_valid
            and run_count_valid
            and run_count > 0
            and run_ids_valid
            and len(run_ids) == run_count
            and missing_scope_valid
            and not missing_scope
            and result.get("execution_candidate_priority_boost") is False
        ):
            add(
                context.findings,
                severity,
                "cycle_efficiency_starvation_absent_inconsistent",
                "absent starvation requires at least one fresh scoped run id.",
            )
        goal_projection = result.get("goal_axis_stagnation_projection")
        if goal_projection is not None and not isinstance(goal_projection, dict):
            add(
                context.findings,
                severity,
                "cycle_efficiency_goal_axis_projection_invalid",
                "Goal-axis stagnation must remain a separate projection whose streak is not reset by family changes.",
            )
        elif isinstance(goal_projection, dict):
            projection_status_value = goal_projection.get("status")
            projection_status = (
                projection_status_value.strip().lower()
                if isinstance(projection_status_value, str)
                else ""
            )
            goal_axis = goal_projection.get("goal_axis")
            family_ids = goal_projection.get("family_ids")
            cycle_count = goal_projection.get("cycle_count")
            semantic_count = goal_projection.get("semantic_movement_cycle_count")
            producer_count = goal_projection.get("producer_run_cycle_count")
            safety_count = goal_projection.get("safety_or_governance_cycle_count")
            no_movement_streak = goal_projection.get("no_semantic_movement_streak")
            counts_valid = all(
                _nonnegative_int(value)
                for value in (
                    cycle_count,
                    semantic_count,
                    producer_count,
                    safety_count,
                    no_movement_streak,
                )
            )
            identity_valid = bool(
                projection_status in {"evaluated", "scope_unknown"}
                and _bounded_id_list(family_ids)
                and (
                    projection_status == "scope_unknown" and goal_axis in (None, "")
                    or projection_status == "evaluated" and _bounded_opaque_id(goal_axis) is not None
                )
            )
            if not identity_valid or goal_projection.get("family_change_resets_streak") is not False:
                add(
                    context.findings,
                    severity,
                    "cycle_efficiency_goal_axis_projection_invalid",
                    "Goal-axis projection requires bounded identities and cannot reset on family change.",
                )
            if not counts_valid or (
                counts_valid
                and not (
                    semantic_count <= producer_count <= cycle_count
                    and safety_count <= cycle_count
                    and no_movement_streak <= cycle_count
                )
            ):
                add(
                    context.findings,
                    severity,
                    "cycle_efficiency_semantic_movement_without_producer_run",
                    "Goal-axis semantic movement cannot outnumber fresh producer-run cycles.",
                )
            if (
                counts_valid
                and cycle_count > 0
                and semantic_count == 0
                and no_movement_streak != cycle_count
            ):
                add(
                    context.findings,
                    severity,
                    "cycle_efficiency_goal_axis_unjustified_reset",
                    "A goal-axis streak without verified semantic movement cannot be reset by family change or declaration.",
                )
        global_aggregate = result.get("global_aggregate")
        if not isinstance(global_aggregate, dict) or global_aggregate.get("dashboard_only") is not True:
            add(
                context.findings,
                severity,
                "cycle_efficiency_global_dashboard_contract_missing",
                "Global efficiency debt must be explicitly marked dashboard_only.",
            )
        elif global_aggregate.get("hard_gate") is True:
            add(
                context.findings,
                severity,
                "cycle_efficiency_global_dashboard_hard_gate",
                "Global dashboard debt cannot be a current-family hard gate.",
            )
        for budget_name in ("command_surface_budget", "artifact_sprawl_budget"):
            budget = result.get(budget_name)
            if not isinstance(budget, dict):
                continue
            if budget.get("decision_scope") == "global_dashboard" and (
                budget.get("hard_gate") is True or budget.get("constrains_current_family") is True
            ):
                add(
                    context.findings,
                    severity,
                    "cycle_efficiency_global_budget_hard_gate",
                    "A global dashboard budget cannot constrain the current family.",
                    {"budget": budget_name},
                )
        recommendation_value = result.get("recommendation")
        recommendation = recommendation_value.strip() if isinstance(recommendation_value, str) else ""
        if recommendation not in RECOMMENDATIONS:
            add(context.findings, severity, "cycle_efficiency_recommendation_invalid", "Cycle-efficiency recommendation is outside the closed vocabulary.", {"allowed": sorted(RECOMMENDATIONS)})
        blockers = result.get("blockers")
        if not isinstance(blockers, list):
            add(context.findings, severity, "cycle_efficiency_blockers_missing", "Cycle-efficiency profile requires an explicit blockers list.")
        evidence_paths = result.get("evidence_paths")
        if not isinstance(evidence_paths, list) or not evidence_paths or any(not isinstance(item, str) or not item.strip() for item in evidence_paths):
            add(context.findings, severity, "cycle_efficiency_evidence_paths_invalid", "Cycle-efficiency profile requires explicit non-empty evidence_paths.")
