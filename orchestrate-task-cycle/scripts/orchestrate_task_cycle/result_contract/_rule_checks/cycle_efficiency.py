from __future__ import annotations

from typing import Any

from ..base import RuleContext
from ..common import add
from .cycle_efficiency_common import (
    BASIS_LIST_FIELDS,
    PROFILE_SCOPE_FIELDS,
    RECOMMENDATIONS,
    STATUSES,
    bounded_id_list,
    bounded_opaque_id,
    nonnegative_int,
)
from .cycle_efficiency_starvation import validate_execution_starvation


def run_cycle_efficiency_profile_check(context: RuleContext) -> None:
    _validate_identity_and_cost(context)
    _validate_profile_scope(context)
    validate_execution_starvation(context)
    _validate_goal_axis_projection(context)
    _validate_dashboard_and_routing(context)


def _validate_identity_and_cost(context: RuleContext) -> None:
    result = context.result
    if bounded_opaque_id(result.get("task_id"), path_safe=True) is None:
        add(
            context.findings,
            "block",
            "cycle_efficiency_task_id_invalid",
            "Cycle-efficiency task_id must be one bounded path-safe token.",
        )
    status_value = result.get("status")
    status = status_value.strip().lower() if isinstance(status_value, str) else ""
    if status not in STATUSES:
        add(
            context.findings,
            "block",
            "cycle_efficiency_status_invalid",
            "Cycle-efficiency status is outside the closed vocabulary.",
            {"allowed": sorted(STATUSES)},
        )
    cost = result.get("cycle_fixed_cost")
    if isinstance(cost, bool) or not isinstance(cost, (int, float)) or cost < 0:
        add(
            context.findings,
            "block",
            "cycle_efficiency_cost_invalid",
            "cycle_fixed_cost must be a nonnegative number.",
        )
    _validate_cost_basis(context, cost)


def _validate_cost_basis(context: RuleContext, cost: Any) -> None:
    basis = context.result.get("cycle_cost_basis")
    if (
        not isinstance(basis, dict)
        or any(
            not isinstance(basis.get(field), list)
            or any(
                not isinstance(item, str) or not item.strip()
                for item in basis.get(field) or []
            )
            for field in BASIS_LIST_FIELDS
        )
        or not isinstance(basis.get("denominator"), str)
        or not basis.get("denominator", "").strip()
    ):
        add(
            context.findings,
            "block",
            "cycle_efficiency_cost_basis_invalid",
            "cycle_cost_basis must include the three identity lists and a non-empty denominator description.",
            {"required_list_fields": sorted(BASIS_LIST_FIELDS)},
        )
        return
    if isinstance(cost, (int, float)) and not isinstance(cost, bool):
        expected_floor = max(
            1,
            len(set(str(item) for item in basis.get("unique_new_artifact_ids") or []))
            + len(set(str(item) for item in basis.get("fresh_stage_event_ids") or [])),
        )
        if cost < expected_floor:
            add(
                context.findings,
                "block",
                "cycle_efficiency_cost_below_observed_basis",
                "cycle_fixed_cost must not be smaller than the observable artifact and stage-event basis.",
                {"cycle_fixed_cost": cost, "observed_basis_floor": expected_floor},
            )


def _validate_profile_scope(context: RuleContext) -> None:
    result = context.result
    scope_unverified = result.get("profile_scope_unverified")
    if not isinstance(scope_unverified, bool):
        add(
            context.findings,
            "block",
            "cycle_efficiency_scope_status_missing",
            "Cycle-efficiency profiles require an explicit boolean profile_scope_unverified field.",
        )
    if scope_unverified is True and result.get("family_scoped_hard_gate") is True:
        add(
            context.findings,
            "block",
            "cycle_efficiency_unverified_family_hard_gate",
            "An unverified family scope cannot emit a current-family hard gate.",
        )
    profile_scope = result.get("profile_scope")
    if isinstance(profile_scope, dict):
        malformed = [
            field
            for field, value in profile_scope.items()
            if field not in PROFILE_SCOPE_FIELDS
            or value not in (None, "")
            and bounded_opaque_id(value) is None
        ]
        if malformed or (
            scope_unverified is False
            and (
                set(profile_scope) != PROFILE_SCOPE_FIELDS
                or any(
                    bounded_opaque_id(value) is None for value in profile_scope.values()
                )
            )
        ):
            add(
                context.findings,
                "block",
                "cycle_efficiency_profile_scope_identity_invalid",
                "Profile scope identifiers must be bounded opaque strings; raw values are not retained.",
                {"invalid_field_count": len(malformed)},
            )
    elif profile_scope is not None:
        add(
            context.findings,
            "block",
            "cycle_efficiency_profile_scope_identity_invalid",
            "Profile scope must be a bounded identifier mapping.",
        )


def _validate_goal_axis_projection(context: RuleContext) -> None:
    projection = context.result.get("goal_axis_stagnation_projection")
    if projection is not None and not isinstance(projection, dict):
        add(
            context.findings,
            "block",
            "cycle_efficiency_goal_axis_projection_invalid",
            "Goal-axis stagnation must remain a separate projection whose streak is not reset by family changes.",
        )
    elif isinstance(projection, dict):
        _validate_goal_axis_mapping(context, projection)


def _validate_goal_axis_mapping(
    context: RuleContext, projection: dict[str, Any]
) -> None:
    status_value = projection.get("status")
    status = status_value.strip().lower() if isinstance(status_value, str) else ""
    goal_axis = projection.get("goal_axis")
    family_ids = projection.get("family_ids")
    cycle_count = projection.get("cycle_count")
    semantic_count = projection.get("semantic_movement_cycle_count")
    producer_count = projection.get("producer_run_cycle_count")
    safety_count = projection.get("safety_or_governance_cycle_count")
    no_movement_streak = projection.get("no_semantic_movement_streak")
    counts_valid = all(
        nonnegative_int(value)
        for value in (
            cycle_count,
            semantic_count,
            producer_count,
            safety_count,
            no_movement_streak,
        )
    )
    identity_valid = bool(
        status in {"evaluated", "scope_unknown"}
        and bounded_id_list(family_ids)
        and (
            status == "scope_unknown"
            and goal_axis in (None, "")
            or status == "evaluated"
            and bounded_opaque_id(goal_axis) is not None
        )
    )
    if not identity_valid or projection.get("family_change_resets_streak") is not False:
        add(
            context.findings,
            "block",
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
            "block",
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
            "block",
            "cycle_efficiency_goal_axis_unjustified_reset",
            "A goal-axis streak without verified semantic movement cannot be reset by family change or declaration.",
        )


def _validate_dashboard_and_routing(context: RuleContext) -> None:
    result = context.result
    aggregate = result.get("global_aggregate")
    if not isinstance(aggregate, dict) or aggregate.get("dashboard_only") is not True:
        add(
            context.findings,
            "block",
            "cycle_efficiency_global_dashboard_contract_missing",
            "Global efficiency debt must be explicitly marked dashboard_only.",
        )
    elif aggregate.get("hard_gate") is True:
        add(
            context.findings,
            "block",
            "cycle_efficiency_global_dashboard_hard_gate",
            "Global dashboard debt cannot be a current-family hard gate.",
        )
    _validate_global_budgets(context)
    recommendation_value = result.get("recommendation")
    recommendation = (
        recommendation_value.strip() if isinstance(recommendation_value, str) else ""
    )
    if recommendation not in RECOMMENDATIONS:
        add(
            context.findings,
            "block",
            "cycle_efficiency_recommendation_invalid",
            "Cycle-efficiency recommendation is outside the closed vocabulary.",
            {"allowed": sorted(RECOMMENDATIONS)},
        )
    if not isinstance(result.get("blockers"), list):
        add(
            context.findings,
            "block",
            "cycle_efficiency_blockers_missing",
            "Cycle-efficiency profile requires an explicit blockers list.",
        )
    evidence_paths = result.get("evidence_paths")
    if (
        not isinstance(evidence_paths, list)
        or not evidence_paths
        or any(not isinstance(item, str) or not item.strip() for item in evidence_paths)
    ):
        add(
            context.findings,
            "block",
            "cycle_efficiency_evidence_paths_invalid",
            "Cycle-efficiency profile requires explicit non-empty evidence_paths.",
        )


def _validate_global_budgets(context: RuleContext) -> None:
    for budget_name in ("command_surface_budget", "artifact_sprawl_budget"):
        budget = context.result.get(budget_name)
        if not isinstance(budget, dict):
            continue
        if budget.get("decision_scope") == "global_dashboard" and (
            budget.get("hard_gate") is True
            or budget.get("constrains_current_family") is True
        ):
            add(
                context.findings,
                "block",
                "cycle_efficiency_global_budget_hard_gate",
                "A global dashboard budget cannot constrain the current family.",
                {"budget": budget_name},
            )
