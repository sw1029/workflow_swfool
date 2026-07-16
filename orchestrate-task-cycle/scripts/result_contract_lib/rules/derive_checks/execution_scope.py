from __future__ import annotations

from .shared import (
    EXECUTION_SCOPE_RECOVERY_TASK_KINDS,
    EXECUTION_STARVATION_STATUSES,
    _bounded_id_items,
    _bounded_opaque_id,
    _declared_values,
    _nonnegative_int,
    add,
    boolish,
    first_present,
)
from .state import DeriveFacts


def _goal_projection_summary(
    goal_projection_value: object,
) -> tuple[bool, str, list[object], int | None, int | None, int | None, int | None]:
    projection_valid = isinstance(goal_projection_value, dict)
    projection_status = ""
    family_ids: list[object] = []
    cycle_count = semantic_count = producer_count = no_movement_streak = None
    if isinstance(goal_projection_value, dict):
        projection_status_value = goal_projection_value.get("status")
        projection_status_text = _bounded_opaque_id(projection_status_value)
        projection_status = projection_status_text.lower() if projection_status_text else ""
        goal_axis = _bounded_opaque_id(goal_projection_value.get("goal_axis"))
        raw_family_ids = goal_projection_value.get("family_ids")
        family_ids = raw_family_ids if isinstance(raw_family_ids, list) else []
        family_ids_valid = bool(
            isinstance(raw_family_ids, list)
            and all(_bounded_opaque_id(item) is not None for item in raw_family_ids)
            and len(raw_family_ids) == len(set(raw_family_ids))
        )
        cycle_count = goal_projection_value.get("cycle_count")
        semantic_count = goal_projection_value.get("semantic_movement_cycle_count")
        producer_count = goal_projection_value.get("producer_run_cycle_count")
        no_movement_streak = goal_projection_value.get("no_semantic_movement_streak")
        counts_valid = all(
            _nonnegative_int(value)
            for value in (cycle_count, semantic_count, producer_count, no_movement_streak)
        )
        projection_valid = bool(
            projection_status in {"evaluated", "scope_unknown"}
            and family_ids_valid
            and goal_projection_value.get("family_change_resets_streak") is False
            and counts_valid
            and semantic_count <= producer_count <= cycle_count
            and no_movement_streak <= cycle_count
            and (
                projection_status == "scope_unknown" and goal_projection_value.get("goal_axis") in (None, "")
                or projection_status == "evaluated" and goal_axis is not None
            )
        )
    return (
        projection_valid,
        projection_status,
        family_ids,
        cycle_count,
        semantic_count,
        producer_count,
        no_movement_streak,
    )


def _duplicate_projection_malformed(goal_projection_values: list[object]) -> bool:
    projection_signatures: set[tuple[object, ...]] = set()
    malformed = False
    for candidate in goal_projection_values:
        if not isinstance(candidate, dict):
            malformed = True
            continue
        candidate_status = _bounded_opaque_id(candidate.get("status"))
        candidate_goal_axis = _bounded_opaque_id(candidate.get("goal_axis"))
        candidate_family_items, candidate_families_valid = _bounded_id_items(candidate.get("family_ids"))
        candidate_counts = tuple(
            candidate.get(field)
            for field in (
                "cycle_count",
                "semantic_movement_cycle_count",
                "producer_run_cycle_count",
                "no_semantic_movement_streak",
            )
        )
        if (
            candidate_status is None
            or not candidate_families_valid
            or not all(_nonnegative_int(value) for value in candidate_counts)
            or candidate.get("family_change_resets_streak") is not False
        ):
            malformed = True
            continue
        projection_signatures.add(
            (
                candidate_status.lower(),
                candidate_goal_axis,
                tuple(sorted(candidate_family_items)),
                *candidate_counts,
                False,
            )
        )
    return malformed or len(projection_signatures) != 1


def _check_goal_projection(facts: DeriveFacts, goal_projection_values: list[object]) -> None:
    result = facts.result
    mode = facts.mode
    findings = facts.findings
    (
        projection_valid,
        projection_status,
        family_ids,
        cycle_count,
        semantic_count,
        producer_count,
        no_movement_streak,
    ) = _goal_projection_summary(goal_projection_values[0])
    if _duplicate_projection_malformed(goal_projection_values):
        add(
            findings,
            "block" if mode == "block" else "warn",
            "derive_goal_axis_stagnation_projection_conflict",
            "Duplicate goal-axis stagnation projections must be valid and converge before derive consumes movement claims.",
        )
        projection_valid = False
    if not projection_valid:
        add(
            findings,
            "block" if mode == "block" else "warn",
            "derive_goal_axis_stagnation_projection_invalid",
            "Derive cannot consume malformed or family-resetting goal-axis stagnation evidence; raw input is not retained.",
        )
    projection_implies_unjustified_reset = bool(
        projection_valid
        and cycle_count
        and semantic_count == 0
        and no_movement_streak != cycle_count
    )
    explicit_reset = boolish(
        first_present(
            result,
            [
                "goal_axis_stagnation_reset",
                "goal_axis_streak_reset",
                "reset_goal_axis_stagnation",
                "goal_axis_stagnation_projection.reset_applied",
                "cycle_efficiency_profile.goal_axis_stagnation_projection.reset_applied",
            ],
        )
    )
    semantic_progress_claimed = boolish(
        first_present(
            result,
            [
                "semantic_progress",
                "output_delta.semantic_progress",
                "output_delta_gate.semantic_progress",
                "result.output_delta.semantic_progress",
            ],
        )
    )
    verified_current_movement = bool(
        projection_valid
        and projection_status == "evaluated"
        and semantic_count is not None
        and semantic_count > 0
        and producer_count is not None
        and producer_count >= semantic_count
        and no_movement_streak == 0
    )
    if projection_implies_unjustified_reset or (
        (explicit_reset or semantic_progress_claimed) and not verified_current_movement
    ):
        add(
            findings,
            "block" if mode == "block" else "warn",
            "derive_goal_axis_stagnation_unjustified_reset",
            "Family change, an explicit reset, or semantic-progress wording cannot reset goal-axis stagnation without verified current-axis producer movement.",
            {
                "family_change_observed": len(family_ids) > 1,
                "explicit_reset_claimed": explicit_reset,
                "semantic_progress_claimed": semantic_progress_claimed,
                "verified_current_movement": verified_current_movement,
            },
        )


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
    starvation_status_malformed = len(normalized_starvation_status_items) != len(starvation_status_values)
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
    return normalized_starvation_statuses, starvation_status_malformed, starvation_status_conflict


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
        and text.lower() in {"evaluated", "scope_unknown"}
    ]
    normalized_scope_statuses = set(normalized_scope_status_items)
    scope_status_malformed = len(normalized_scope_status_items) != len(scope_status_values)
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
        ("scope_unknown" in scope_statuses and starvation_statuses & {"present", "absent"})
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
    normalized_scope_evidence = [_bounded_id_items(value) for value in scope_evidence_values]
    scope_evidence_malformed = any(not valid for _, valid in normalized_scope_evidence)
    scope_evidence_sets = {tuple(sorted(items)) for items, valid in normalized_scope_evidence if valid}
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
) -> None:
    mode = facts.mode
    findings = facts.findings
    execution_scope_unknown = bool(
        starvation_status_malformed
        or starvation_status_conflict
        or scope_status_malformed
        or scope_status_conflict
        or scope_starvation_status_conflict
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
        facts.terminal_selected or facts.selected_kind not in EXECUTION_SCOPE_RECOVERY_TASK_KINDS
    ):
        add(
            findings,
            "block" if mode == "block" else "warn",
            "derive_execution_scope_unknown_unrecovered",
            "Execution scope_unknown permits only bounded scope-evidence recovery; terminal and ordinary continuation remain unavailable.",
            {
                "terminal_selected": facts.terminal_selected,
                "recovery_kind_selected": facts.selected_kind in EXECUTION_SCOPE_RECOVERY_TASK_KINDS,
            },
        )


def check_execution_scope(facts: DeriveFacts) -> None:
    starvation_statuses, starvation_malformed, starvation_conflict = _starvation_status_surface(facts)
    scope_statuses, scope_malformed, scope_conflict = _scope_status_surface(facts)
    cross_surface_conflict = _scope_starvation_conflict(facts, starvation_statuses, scope_statuses)
    scope_evidence_required = _scope_evidence_surface(facts)
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
        _check_goal_projection(facts, goal_projection_values)
