from __future__ import annotations

from ..common import non_empty
from .loopback_state import LoopbackState


def validate_envelope_and_observability(state: LoopbackState) -> None:
    _validate_envelope_thaw(state)
    _validate_scenario_and_provenance(state)
    _validate_blocker_and_stochastic_routing(state)
    _validate_first_fire(state)


def _validate_envelope_thaw(state: LoopbackState) -> None:
    required = state.flag(
        "envelope_thaw_item_required",
        "acceptance_reachability_gate.envelope_thaw_item_required",
    )
    item = state.value("envelope_thaw_item") or state.nested(
        "acceptance_reachability_gate.envelope_thaw_item"
    )
    if required and (
        state.disposition == "goal_productive"
        or not state.hard_stop
        or not non_empty(item)
    ):
        state.emit(
            "loopback_envelope_thaw_item_not_reserved",
            "`loopback_audit` must reserve an envelope_thaw_item and hard-stop when acceptance is unreachable under a frozen envelope.",
        )


def _validate_scenario_and_provenance(state: LoopbackState) -> None:
    scenario_uncovered = state.flag(
        "scenario_uncovered", "acceptance_scenario_gate.scenario_uncovered"
    )
    acceptance_inversion = state.flag(
        "acceptance_inversion", "acceptance_scenario_gate.acceptance_inversion"
    )
    if (scenario_uncovered or acceptance_inversion) and (
        state.disposition == "goal_productive" or not state.hard_stop
    ):
        state.emit(
            "loopback_acceptance_scenario_not_fail_closed",
            "`loopback_audit` must fail closed on uncovered or inverted acceptance scenarios until scenario supply or code/contract repair is selected.",
        )
    provenance_missing = state.flag(
        "command_provenance_missing",
        "command_provenance_gate.command_provenance_missing",
    )
    if provenance_missing and (
        state.disposition == "goal_productive" or state.measurement_progress_allowed
    ):
        state.emit(
            "loopback_command_provenance_missing_counted",
            "`loopback_audit` must not count a missing-argv live run as baseline, comparison, A/B, reproduction, or measurement-progress evidence.",
        )


def _validate_blocker_and_stochastic_routing(state: LoopbackState) -> None:
    blocker_opacity = state.flag(
        "repeated_blocker_opacity",
        "blocker_actionability_gate.repeated_blocker_opacity",
    )
    if blocker_opacity and state.disposition == "goal_productive":
        state.emit(
            "loopback_repeated_blocker_opacity_goal_productive",
            "`loopback_audit` must route repeated same-gate blocker_opacity to blocker-contract repair instead of ordinary goal_productive work.",
        )
    predetermined_unreachable = state.flag(
        "predetermined_unreachable",
        "stochastic_feasibility_gate.predetermined_unreachable",
    )
    floor_edge = state.flag(
        "floor_edge_envelope", "stochastic_feasibility_gate.floor_edge_envelope"
    )
    if (predetermined_unreachable or floor_edge) and (
        state.disposition == "goal_productive" or not state.hard_stop
    ):
        state.emit(
            "loopback_stochastic_contract_infeasible_not_fail_closed",
            "`loopback_audit` must treat exact-match and floor-edge stochastic findings as contract-revision blockers, not retryable goal_productive progress.",
        )


def _validate_first_fire(state: LoopbackState) -> None:
    first_fire = state.flag(
        "instrumentation_first_fire",
        "instrumentation_first_fire_gate.instrumentation_first_fire",
    )
    consumed_item = state.value("first_fire_consumed_item_id") or state.nested(
        "instrumentation_first_fire_gate.first_fire_consumed_item_id"
    )
    if first_fire and not non_empty(consumed_item):
        state.emit(
            "loopback_first_fire_without_consumed_item",
            "`loopback_audit` must attach instrumentation_first_fire to exactly one consumed workflow item.",
        )
    double_counted = state.flag(
        "first_fire_double_counted",
        "instrumentation_first_fire_gate.first_fire_double_counted",
    )
    if first_fire and double_counted:
        state.emit(
            "loopback_first_fire_double_counted",
            "`loopback_audit` must not double-count instrumentation_first_fire as both first-fire evidence and goal progress or instrumentation-supply consumption.",
        )
