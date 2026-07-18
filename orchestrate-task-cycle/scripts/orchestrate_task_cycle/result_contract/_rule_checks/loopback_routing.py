from __future__ import annotations

from .loopback_state import LoopbackState


def validate_routing_and_provenance(state: LoopbackState) -> None:
    _validate_cost_and_stall_routing(state)
    _validate_contract_fail_closed(state)
    _validate_independent_sources(state)


def _validate_cost_and_stall_routing(state: LoopbackState) -> None:
    residual_cost_below_policy = (
        state.flag("residual_gap_cost_below_policy")
        or state.flag("value_per_cycle_cost_below_policy")
        or state.nested_flag("residual_gap_cost_policy.below_policy")
    )
    if residual_cost_below_policy and state.disposition == "goal_productive":
        state.emit(
            "loopback_residual_cost_below_policy_goal_productive",
            "`loopback_audit` must not route below-policy residual value per cycle cost as ordinary goal_productive repair.",
        )
    primary_metric_stalled = state.flag(
        "primary_metric_stalled", "primary_metric_gate.primary_metric_stalled"
    )
    if primary_metric_stalled and not state.hard_stop:
        state.emit(
            "loopback_primary_metric_stall_without_hard_stop",
            "`loopback_audit` primary_metric_stalled=true must hard-stop ordinary progress and route forced retargeting or user escalation.",
        )
    c4_escalation = state.flag(
        "c4_user_escalation_backstop_required",
        "primary_metric_gate.c4_user_escalation_backstop_required",
    )
    if c4_escalation and state.disposition != "user_escalation":
        state.emit(
            "loopback_c4_user_escalation_misrouted",
            "`loopback_audit` C4 user-escalation backstop must route to user_escalation when no forced option is actionable.",
        )


def _validate_contract_fail_closed(state: LoopbackState) -> None:
    terminal_contradiction = state.flag(
        "terminal_classification_stage_contradiction",
        "failure_surface_stage_gate.terminal_classification_stage_contradiction",
    )
    invalid_counting = state.flag(
        "terminal_classification_invalid_for_counting",
        "failure_surface_stage_gate.terminal_classification_invalid_for_counting",
    )
    if (terminal_contradiction or invalid_counting) and (
        state.disposition == "goal_productive" or not state.hard_stop
    ):
        state.emit(
            "loopback_terminal_classification_stage_not_fail_closed",
            "`loopback_audit` contradictory terminal classification must be invalid for counting/close and hard-stop target consumption.",
        )
    same_input_violation = state.flag(
        "same_input_contract_violation",
        "same_input_contract_gate.same_input_contract_violation",
    )
    if same_input_violation and (
        state.disposition == "goal_productive" or not state.hard_stop
    ):
        state.emit(
            "loopback_same_input_contract_not_fail_closed",
            "`loopback_audit` same-condition input-set mismatch must hard-stop counting until the comparison contract is repaired.",
        )
    instrumentation_required = state.flag(
        "instrumentation_supply_required",
        "diagnostics_unavailable_gate.instrumentation_supply_required",
    )
    if instrumentation_required and (
        state.disposition == "goal_productive" or not state.hard_stop
    ):
        state.emit(
            "loopback_instrumentation_supply_not_fail_closed",
            "`loopback_audit` repeated diagnostics_unavailable must force instrumentation supply or an explicit observability rationale, not ordinary goal_productive routing.",
        )


def _validate_independent_sources(state: LoopbackState) -> None:
    source_status = state.text(
        "independent_source_separation_status",
        "verification_source_separation_gate.independent_source_separation_status",
        "evidence_provenance_gate.independent_source_separation_status",
    )
    progress_claimed = (
        state.primary_metric_high_water_moved
        or state.measurement_progress_allowed
        or state.disposition == "goal_productive"
    )
    if source_status in {"missing", "overlap", "blocked"} and progress_claimed:
        state.emit(
            "loopback_independent_verification_source_not_disjoint_counted",
            "`loopback_audit` must downgrade independently_verified evidence to attested when verification inputs are missing or overlap verified artifacts.",
            {"independent_source_separation_status": source_status},
        )
    invariant_status = state.text(
        "independent_invariant_separation_status",
        "verification_source_separation_gate.independent_invariant_separation_status",
        "evidence_provenance_gate.independent_invariant_separation_status",
    )
    if invariant_status in {"coupled", "unknown", "blocked"} and progress_claimed:
        state.emit(
            "loopback_independent_verification_invariant_not_separated",
            "`loopback_audit` must downgrade independent evidence when decisive invariant ownership is coupled or unknown.",
            {"independent_invariant_separation_status": invariant_status},
        )
    downgraded = state.items(
        "independently_verified_downgraded_fields",
        "verification_source_separation_gate.independently_verified_downgraded_fields",
        "evidence_provenance_gate.independently_verified_downgraded_fields",
    )
    if downgraded and progress_claimed:
        state.emit(
            "loopback_downgraded_independent_verification_counted",
            "`loopback_audit` must not count auto-downgraded independently_verified fields as primary progress.",
            {"downgraded_fields": downgraded},
        )
    self_grounded = set(
        state.items(
            "self_grounded_axes",
            "verification_source_separation_gate.self_grounded_axes",
            "evidence_provenance_gate.self_grounded_axes",
        )
    )
    independently_verified = set(
        state.items(
            "independently_verified_fields",
            "evidence_provenance_gate.independently_verified_fields",
        )
    )
    mislabeled = sorted(self_grounded & independently_verified)
    if mislabeled and (progress_claimed or state.semantic_progress):
        state.emit(
            "loopback_self_grounded_counted_as_independent",
            "Self-grounded structural axes cannot remain in the independently-verified bucket or move semantic high-water.",
            {"axis_ids": mislabeled},
        )
