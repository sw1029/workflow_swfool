from __future__ import annotations

from typing import Any

from .access import first_value, list_value, number_value, truthy
from .context import ValidationContext
from .evidence import (
    collect_sealed_families,
    collect_stage_semantic_signatures,
    selected_disposition,
)


PROGRESS_TRANSITIONS = {
    "pre_derive",
    "pre_schema_post_derive",
    "pre_index",
    "pre_commit",
    "pre_report",
    "pre_closeout_commit",
}


def validate_disposition_gate(state: ValidationContext) -> None:
    if not _applies(state):
        return
    terminal = terminal_blocker(state)
    progress_kind = next_progress_kind(state)
    allowed = list_value(
        first_value(
            state.stage,
            "effective_allowed_dispositions",
            "packet.effective_allowed_dispositions",
            "anti_loop_progress_gate.effective_allowed_dispositions",
            "packet.anti_loop_progress_gate.effective_allowed_dispositions",
            "loop_breaker_packet.effective_allowed_dispositions",
            "packet.loop_breaker_packet.effective_allowed_dispositions",
        )
    )
    if not allowed:
        return
    disposition = selected_disposition(state.stage, progress_kind, terminal)
    if disposition and disposition not in {item.lower() for item in allowed}:
        state.add(
            "block",
            "disposition_not_effectively_allowed",
            "Selected disposition is outside `effective_allowed_dispositions`; active progress gates must be consumed as an intersection.",
            {
                "selected_disposition": disposition,
                "effective_allowed_dispositions": allowed,
            },
        )


def validate_positive_delta_gates(state: ValidationContext) -> None:
    if not _applies(state):
        return
    terminal = terminal_blocker(state)
    has_delta, new_kinds, supplied_paths = _positive_delta(state)
    positive_required = truthy(
        first_value(
            state.stage,
            "positive_input_delta_required",
            "packet.positive_input_delta_required",
            "loop_breaker_packet.positive_input_delta_required",
            "packet.loop_breaker_packet.positive_input_delta_required",
        )
    )
    zero_viable = truthy(
        first_value(
            state.stage,
            "zero_viable_candidates",
            "packet.zero_viable_candidates",
            "loop_breaker_packet.zero_viable_candidates",
            "packet.loop_breaker_packet.zero_viable_candidates",
        )
    )
    terminal_recommended = truthy(
        first_value(
            state.stage,
            "terminal_blocker_recommended",
            "packet.terminal_blocker_recommended",
            "loop_breaker_packet.terminal_blocker_recommended",
            "packet.loop_breaker_packet.terminal_blocker_recommended",
        )
    )
    if positive_required and not has_delta and not terminal:
        state.add(
            "block",
            "positive_input_delta_missing",
            "Evidence-family task selection requires a non-empty supplied artifact path or produced_domain_delta=true with changed_vs_previous=true and semantic_progress=true, or terminal blocker state.",
            {"new_input_kinds": new_kinds},
        )
    if zero_viable and not terminal:
        state.add(
            "block",
            "zero_viable_candidates_without_terminal_state",
            "Zero viable candidate state requires `terminal_blocker` to prevent narrowing/blocker/handoff loops.",
        )
    if terminal_recommended and not terminal and not has_delta:
        state.add(
            "block",
            "terminal_blocker_recommendation_unhandled",
            "Terminal blocker recommendation requires terminal state or a supplied positive input delta override.",
            {
                "new_input_kinds": new_kinds,
                "supplied_input_artifact_paths": supplied_paths,
            },
        )


def validate_sealed_semantic_gate(state: ValidationContext) -> None:
    if not _applies(state):
        return
    terminal = terminal_blocker(state)
    has_delta, _new_kinds, _supplied_paths = _positive_delta(state)
    signatures = collect_stage_semantic_signatures(state.stage)
    sealed = collect_sealed_families(state.context)
    sealed_semantic = {
        str(item.get("semantic_signature"))
        for item in sealed
        if item.get("semantic_signature")
    }
    matches = sorted(set(signatures) & sealed_semantic)
    if matches and not terminal and not has_delta:
        state.add(
            "block",
            "sealed_semantic_family_without_input_delta",
            "A sealed semantic blocker family is in scope without a supplied input artifact or positive output delta; do not derive another task in the same family.",
            {"semantic_signature": matches, "sealed_families": sealed[:5]},
        )


def validate_goal_distance_gate(state: ValidationContext) -> None:
    if not _applies(state):
        return
    cycles = number_value(
        first_value(
            state.stage,
            "cycles_since_goal_productive_output",
            "packet.cycles_since_goal_productive_output",
            "goal_distance_gate.cycles_since_goal_productive_output",
            "packet.goal_distance_gate.cycles_since_goal_productive_output",
            "loop_breaker_packet.cycles_since_goal_productive_output",
            "packet.loop_breaker_packet.cycles_since_goal_productive_output",
        )
    )
    threshold = number_value(
        first_value(
            state.stage,
            "goal_productive_threshold",
            "packet.goal_productive_threshold",
            "goal_distance_gate.threshold",
            "packet.goal_distance_gate.threshold",
        )
    )
    evaluation = (
        str(
            first_value(
                state.stage,
                "goal_distance_gate.evaluation_status",
                "packet.goal_distance_gate.evaluation_status",
                "goal_distance_gate.budget_evaluation_status",
                "packet.goal_distance_gate.budget_evaluation_status",
            )
            or ""
        )
        .strip()
        .lower()
    )
    productive = truthy(
        first_value(
            state.stage,
            "goal_productive_this_cycle",
            "packet.goal_productive_this_cycle",
            "goal_distance_gate.goal_productive_this_cycle",
            "packet.goal_distance_gate.goal_productive_this_cycle",
        )
    )
    progress_kind = next_progress_kind(state)
    if not _goal_distance_exceeded(
        cycles, threshold, evaluation, productive, terminal_blocker(state)
    ):
        return
    evidence = {
        "cycles_since_goal_productive_output": cycles,
        "threshold": threshold,
    }
    if progress_kind and progress_kind != "goal_productive":
        evidence["progress_kind"] = progress_kind
        state.add(
            "block",
            "goal_distance_gate_unmet",
            "Goal-distance gate requires a goal-productive next task or terminal blocker after too many governance-only cycles.",
            evidence,
        )
    elif not progress_kind:
        state.add(
            "warn",
            "goal_distance_gate_requires_derive_disposition",
            "Derive must select a goal-productive candidate or record terminal blocker state.",
            evidence,
        )


def _goal_distance_exceeded(
    cycles: int | None,
    threshold: int | None,
    evaluation: str,
    productive: bool,
    terminal: Any,
) -> bool:
    return bool(
        threshold is not None
        and evaluation == "evaluated"
        and cycles is not None
        and cycles > threshold
        and not productive
        and not terminal
    )


def _positive_delta(state: ValidationContext) -> tuple[bool, list[str], list[str]]:
    new_kinds = list_value(
        first_value(
            state.stage,
            "new_input_kinds",
            "packet.new_input_kinds",
            "loop_breaker_packet.new_input_kinds",
            "packet.loop_breaker_packet.new_input_kinds",
            "positive_input_delta_gate.new_input_kinds",
            "packet.positive_input_delta_gate.new_input_kinds",
        )
    )
    supplied_paths = list_value(
        first_value(
            state.stage,
            "supplied_input_artifact_paths",
            "packet.supplied_input_artifact_paths",
            "positive_input_delta_gate.supplied_input_artifact_paths",
            "packet.positive_input_delta_gate.supplied_input_artifact_paths",
            "loop_breaker_packet.positive_input_delta_gate.supplied_input_artifact_paths",
            "packet.loop_breaker_packet.positive_input_delta_gate.supplied_input_artifact_paths",
        )
    )
    produced = _gate_truth(
        state,
        "produced_domain_delta",
        "output_delta_gate.produced_domain_delta",
        "positive_input_delta_gate.produced_domain_delta",
    )
    changed = _gate_truth(
        state,
        "changed_vs_previous",
        "output_delta_gate.changed_vs_previous",
        "anti_loop_progress_gate.changed_vs_previous",
    )
    semantic = _gate_truth(
        state,
        "semantic_progress",
        "output_delta_gate.semantic_progress",
        "anti_loop_progress_gate.semantic_progress",
    )
    declared = truthy(
        first_value(
            state.stage,
            "has_supplied_input_delta",
            "packet.has_supplied_input_delta",
            "positive_input_delta_gate.has_supplied_input_delta",
            "packet.positive_input_delta_gate.has_supplied_input_delta",
            "loop_breaker_packet.positive_input_delta_gate.has_supplied_input_delta",
            "packet.loop_breaker_packet.positive_input_delta_gate.has_supplied_input_delta",
        )
    )
    return (
        declared or bool(supplied_paths) or (produced and changed and semantic),
        new_kinds,
        supplied_paths,
    )


def _gate_truth(state: ValidationContext, field: str, *nested: str) -> bool:
    paths = [field, f"packet.{field}"]
    for path in nested:
        paths.extend((path, f"packet.{path}"))
    return truthy(first_value(state.stage, *paths))


def terminal_blocker(state: ValidationContext) -> Any:
    return first_value(
        state.stage,
        "terminal_blocker",
        "packet.terminal_blocker",
        "result.terminal_blocker",
        "derive.terminal_blocker",
    )


def next_progress_kind(state: ValidationContext) -> str:
    return str(
        first_value(
            state.stage,
            "selected_progress_kind",
            "candidate_progress_kind",
            "next_task_progress_kind",
            "progress_kind",
            "derive.progress_kind",
            "result.progress_kind",
        )
        or ""
    ).lower()


def _applies(state: ValidationContext) -> bool:
    return state.transition in PROGRESS_TRANSITIONS
