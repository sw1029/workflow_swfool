from __future__ import annotations

from ..common import boolish, number_value
from .loopback_state import LoopbackState


def validate_progress_and_mutation(state: LoopbackState) -> None:
    _validate_insufficient_evidence(state)
    _validate_nonsemantic_streak(state)
    _validate_forward_mutation(state)
    _validate_vacuous_and_adapter(state)
    _validate_cumulative_chain(state)


def _validate_insufficient_evidence(state: LoopbackState) -> None:
    evidence_class = state.text("evidence_class")
    forward_mutation = state.text("blocker_mutation_kind") == "forward_mutation"
    if (
        evidence_class == "insufficient_evidence"
        and not (state.measurement_progress_allowed or forward_mutation)
        and (state.disposition != "conservative_hold" or not state.hard_stop)
    ):
        state.emit(
            "loopback_insufficient_not_fail_closed",
            "`loopback_audit` insufficient evidence must use conservative_hold with hard_stop_required=true.",
        )


def _validate_nonsemantic_streak(state: LoopbackState) -> None:
    count_value = state.value("same_family_micro_hardening_count")
    try:
        streak_count = int(str(count_value))
    except (TypeError, ValueError):
        streak_count = None
    budget_status = str(
        state.nested("same_family_budget_evaluation.budget_evaluation_status") or ""
    ).lower()
    budget_value = state.value("same_family_nonsemantic_budget")
    try:
        budget = int(str(budget_value))
    except (TypeError, ValueError):
        budget = None
    forward_mutation = state.text("blocker_mutation_kind") == "forward_mutation"
    if (
        streak_count is not None
        and budget_status == "evaluated"
        and budget is not None
        and budget > 0
        and streak_count >= budget
        and not state.semantic_progress
        and not state.hard_stop
        and not (state.measurement_progress_allowed or forward_mutation)
    ):
        state.emit(
            "loopback_streak_without_hard_stop",
            "`loopback_audit` reached its explicitly evaluated same-family nonsemantic budget without semantic progress and must hard-stop.",
            {
                "same_family_micro_hardening_count": streak_count,
                "same_family_nonsemantic_budget": budget,
            },
        )


def _validate_forward_mutation(state: LoopbackState) -> None:
    if state.text("blocker_mutation_kind") != "forward_mutation":
        return
    terminal_outcome_value = state.value("terminal_outcome_changed")
    terminal_outcome_changed = (
        state.flag("terminal_outcome_changed")
        if terminal_outcome_value is not None
        else state.flag("changed_vs_previous") and state.semantic_progress
    )
    if (
        state.flag("forward_mutation_vacuous") or not terminal_outcome_changed
    ) and not state.hard_stop:
        state.emit(
            "loopback_forward_mutation_without_terminal_outcome_delta",
            "`loopback_audit` must not leave ladder forward mutation open without observed terminal outcome change or a hard stop.",
        )
    substance_delta_pass = state.nested_flag(
        "substance_delta_gate.substance_delta_pass"
    )
    if (
        not substance_delta_pass
        and not terminal_outcome_changed
        and not state.hard_stop
    ):
        state.emit(
            "loopback_forward_mutation_without_substance_delta",
            "`loopback_audit` must not leave ladder forward mutation open without G-SUBSTANCE pass, strict terminal outcome delta, or a hard stop.",
        )


def _validate_vacuous_and_adapter(state: LoopbackState) -> None:
    vacuous_noop = state.nested_flag("vacuous_corrective_gate.surface_corrective_noop")
    if vacuous_noop and state.semantic_progress:
        state.emit(
            "loopback_vacuous_corrective_claimed_semantic_progress",
            "`loopback_audit` reported semantic_progress while G-VACUOUS found attempted corrective lanes with zero resolved items.",
        )
    adapter_required = state.flag("adapter_mandate_required")
    if adapter_required and not state.hard_stop:
        state.emit(
            "loopback_adapter_mandate_without_hard_stop",
            "`loopback_audit` adapter_mandate_required=true must hard-stop ordinary domain repair and force adapter registration/strengthening or escalation.",
        )
    if state.flag("adapter_wiring_defect") and (
        adapter_required
        or state.disposition != "self_inflicted_gate_defect"
        or not state.hard_stop
    ):
        state.emit(
            "loopback_adapter_wiring_defect_misrouted",
            "`loopback_audit` must route a registered-but-unloaded adapter as self_inflicted_gate_defect, not adapter absence.",
        )


def _validate_cumulative_chain(state: LoopbackState) -> None:
    stalled = state.flag("cumulative_goal_distance_stalled")
    adapter_required = state.flag("adapter_mandate_required")
    if stalled and not adapter_required and not state.hard_stop:
        state.emit(
            "loopback_cumulative_chain_without_hard_stop",
            "`loopback_audit` cumulative goal-distance stall must hard-stop unless G-ADAPTER is the active preceding mandate.",
        )
    streak = state.number("cumulative_goal_distance_stall_streak")
    cap = (
        number_value(
            state.nested(
                "cumulative_goal_distance_gate.cumulative_goal_distance_stall_cap"
            )
        )
        or number_value(state.value("cumulative_goal_distance_stall_cap"))
        or 0
    )
    blocker_mutation = state.text("blocker_mutation_kind")
    if (
        stalled
        and not adapter_required
        and cap > 0
        and streak >= cap * 2
        and blocker_mutation in {"facet_rename", "lateral", "repeat"}
    ):
        gate = state.nested("chain_stall_forced_retarget_gate")
        options = state.nested("forced_selected_task_options")
        gate_present = isinstance(gate, dict) and boolish(
            gate.get("chain_stall_force_retarget")
        )
        if not gate_present or not isinstance(options, list):
            state.emit(
                "loopback_chain_stall_forced_retarget_missing",
                "`loopback_audit` must enumerate forced retarget alternatives when cumulative goal-distance stall reaches cap*2.",
                {
                    "cumulative_goal_distance_stall_streak": streak,
                    "cumulative_goal_distance_stall_cap": cap,
                },
            )
    if state.flag("untried_veto_overridden_by_chain_stall") and not stalled:
        state.emit(
            "loopback_untried_override_without_chain_stall",
            "`untried_veto_overridden_by_chain_stall` requires cumulative goal-distance stall evidence.",
        )
