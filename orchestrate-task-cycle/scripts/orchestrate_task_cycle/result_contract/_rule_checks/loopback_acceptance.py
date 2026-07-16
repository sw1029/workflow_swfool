from __future__ import annotations

from ..common import non_empty
from .loopback_state import LoopbackState


def validate_acceptance_and_verification(state: LoopbackState) -> None:
    _validate_acceptance_reachability(state)
    _validate_verifier_consumption(state)
    _validate_goal_axis_completeness(state)
    _validate_count_key_hygiene(state)


def _validate_acceptance_reachability(state: LoopbackState) -> None:
    if state.flag("acceptance_unreachable_under_frozen_config") and not state.flag(
        "relaxation_or_escalation_required"
    ):
        state.emit(
            "loopback_unreachable_acceptance_without_relaxation_gate",
            "`acceptance_unreachable_under_frozen_config` requires `relaxation_or_escalation_required=true`.",
        )
    if state.flag("unverifiable_acceptance_contract") and not state.hard_stop:
        state.emit(
            "loopback_unverifiable_acceptance_without_hard_stop",
            "`unverifiable_acceptance_contract=true` means a required live verifier was not evaluated; the packet must hard-stop target consumption.",
        )


def _validate_verifier_consumption(state: LoopbackState) -> None:
    metric_excluded = state.nested_flag(
        "oracle_metric_validity_gate.metric_goal_productive_excluded"
    )
    if (
        metric_excluded
        and state.semantic_progress
        and state.measurement_progress_allowed
    ):
        state.emit(
            "loopback_tautological_metric_claimed_progress",
            "Tautological oracle/metric validity must not support semantic or measurement goal-productive progress without independent output-delta evidence.",
        )
    coupled_verifier = state.flag(
        "pass_with_coupled_verifier",
        "coupled_verifier_gate.pass_with_coupled_verifier",
    )
    if coupled_verifier and (
        not state.hard_stop or state.disposition == "goal_productive"
    ):
        state.emit(
            "loopback_coupled_verifier_consumable_as_pass",
            "`loopback_audit` must treat pass_with_coupled_verifier as not-pass and hard-stop target consumption.",
        )
    attested_only = state.flag(
        "attested_only_movement",
        "evidence_provenance_gate.attested_only_movement",
        "primary_metric_gate.attested_only_movement",
    )
    if attested_only and (
        state.primary_metric_high_water_moved
        or state.measurement_progress_allowed
        or state.disposition == "goal_productive"
    ):
        state.emit(
            "loopback_attested_only_movement_counted_as_progress",
            "`loopback_audit` must not let producer-attested movement update high-water, allow measurement progress, or route goal_productive.",
        )


def _validate_goal_axis_completeness(state: LoopbackState) -> None:
    pass_with_unobserved = state.flag(
        "pass_with_unobserved_axes",
        "goal_axis_completeness_gate.pass_with_unobserved_axes",
    )
    axes = state.value("unobserved_goal_axes") or state.nested(
        "goal_axis_completeness_gate.unobserved_goal_axes"
    )
    if (pass_with_unobserved or non_empty(axes)) and (
        not state.hard_stop or state.disposition == "goal_productive"
    ):
        state.emit(
            "loopback_unobserved_axes_consumable_as_pass",
            "`loopback_audit` must treat pass_with_unobserved_axes as not-pass for measurable goals and hard-stop target consumption.",
            {"unobserved_goal_axes": axes or None},
        )


def _validate_count_key_hygiene(state: LoopbackState) -> None:
    generation_dependent = state.flag(
        "generation_dependent_count_key",
        "count_key_hygiene_gate.generation_dependent_count_key",
    )
    effective_key = (
        state.value("effective_count_key")
        or state.nested("count_key_hygiene_gate.effective_count_key")
        or state.value("root_dominant_parameter_key")
        or state.value("terminal_outcome_family_key")
    )
    novelty_claim = (
        state.flag("family_novelty_claim")
        or state.flag("stall_reset_claim")
        or state.nested_flag("count_key_hygiene_gate.family_novelty_claim")
        or state.nested_flag("count_key_hygiene_gate.stall_reset_claim")
    )
    if generation_dependent and not effective_key:
        state.emit(
            "loopback_generation_count_key_without_effective_key",
            "Generation-dependent count-key material is trace-only; loopback must emit an effective adapter-collapsed key or terminal-outcome fallback.",
        )
    if generation_dependent and novelty_claim:
        state.emit(
            "loopback_generation_key_claimed_family_reset",
            "`loopback_audit` must not use task/advice/pack/cycle/run/date/hash/version key churn as family novelty, stall reset, hypothesis exhaustion, or seal escape.",
        )
