from __future__ import annotations

from .shared import (
    add,
    boolish,
    first_present,
    float_value,
    forced_task_kind,
    non_empty,
    selected_disposition,
)
from .state import DeriveFacts


def _check_progress_evidence_part_01(facts: DeriveFacts) -> None:
    result = facts.result
    coupled_verifier = boolish(
        first_present(
            result,
            [
                "pass_with_coupled_verifier",
                "anti_loop_progress_gate.pass_with_coupled_verifier",
                "loopback_audit.pass_with_coupled_verifier",
                "coupled_verifier_gate.pass_with_coupled_verifier",
                "anti_loop_progress_gate.coupled_verifier_gate.pass_with_coupled_verifier",
                "result.anti_loop_progress_gate.pass_with_coupled_verifier",
                "result.anti_loop_progress_gate.coupled_verifier_gate.pass_with_coupled_verifier",
            ],
        )
    )
    attested_only_movement = boolish(
        first_present(
            result,
            [
                "attested_only_movement",
                "anti_loop_progress_gate.attested_only_movement",
                "evidence_provenance_gate.attested_only_movement",
                "anti_loop_progress_gate.evidence_provenance_gate.attested_only_movement",
                "primary_metric_gate.attested_only_movement",
                "anti_loop_progress_gate.primary_metric_gate.attested_only_movement",
                "result.anti_loop_progress_gate.attested_only_movement",
                "result.anti_loop_progress_gate.evidence_provenance_gate.attested_only_movement",
            ],
        )
    )
    primary_metric_stalled = boolish(
        first_present(
            result,
            [
                "primary_metric_stalled",
                "anti_loop_progress_gate.primary_metric_stalled",
                "primary_metric_gate.primary_metric_stalled",
                "anti_loop_progress_gate.primary_metric_gate.primary_metric_stalled",
                "result.anti_loop_progress_gate.primary_metric_stalled",
                "result.anti_loop_progress_gate.primary_metric_gate.primary_metric_stalled",
            ],
        )
    )
    c4_user_escalation = boolish(
        first_present(
            result,
            [
                "c4_user_escalation_backstop_required",
                "anti_loop_progress_gate.c4_user_escalation_backstop_required",
                "primary_metric_gate.c4_user_escalation_backstop_required",
                "anti_loop_progress_gate.primary_metric_gate.c4_user_escalation_backstop_required",
                "result.anti_loop_progress_gate.c4_user_escalation_backstop_required",
                "result.anti_loop_progress_gate.primary_metric_gate.c4_user_escalation_backstop_required",
            ],
        )
    )
    facts.attested_only_movement = attested_only_movement
    facts.c4_user_escalation = c4_user_escalation
    facts.coupled_verifier = coupled_verifier
    facts.primary_metric_stalled = primary_metric_stalled


def _check_progress_evidence_part_02(facts: DeriveFacts) -> None:
    result = facts.result
    marginal_repair = boolish(
        first_present(
            result,
            [
                "marginal_repair",
                "residual_gap_policy.marginal_repair",
                "anti_loop_progress_gate.marginal_repair",
                "anti_loop_progress_gate.residual_gap_policy.marginal_repair",
                "result.anti_loop_progress_gate.marginal_repair",
            ],
        )
    )
    descope_with_residual = boolish(
        first_present(
            result,
            [
                "descope_with_residual",
                "explicit_descope_decision",
                "residual_gap_policy.descope_with_residual",
                "anti_loop_progress_gate.descope_with_residual",
                "result.anti_loop_progress_gate.descope_with_residual",
            ],
        )
    )
    next_capability_rung = first_present(
        result,
        [
            "next_capability_rung",
            "capability_ladder.next_capability_rung",
            "residual_gap_policy.next_capability_rung",
            "anti_loop_progress_gate.next_capability_rung",
            "result.anti_loop_progress_gate.next_capability_rung",
        ],
    )
    marginal_repair_override = boolish(
        first_present(
            result,
            [
                "marginal_repair_higher_value",
                "residual_gap_policy.marginal_repair_higher_value",
                "anti_loop_progress_gate.marginal_repair_higher_value",
                "result.anti_loop_progress_gate.marginal_repair_higher_value",
            ],
        )
    )
    facts.descope_with_residual = descope_with_residual
    facts.marginal_repair = marginal_repair
    facts.marginal_repair_override = marginal_repair_override
    facts.next_capability_rung = next_capability_rung


def _check_progress_evidence_part_03(facts: DeriveFacts) -> None:
    result = facts.result
    pass_with_unobserved_axes = boolish(
        first_present(
            result,
            [
                "pass_with_unobserved_axes",
                "goal_axis_completeness_gate.pass_with_unobserved_axes",
                "qualitative_review_packet.pass_with_unobserved_axes",
                "anti_loop_progress_gate.pass_with_unobserved_axes",
                "result.goal_axis_completeness_gate.pass_with_unobserved_axes",
                "result.anti_loop_progress_gate.pass_with_unobserved_axes",
            ],
        )
    )
    unobserved_goal_axes = first_present(
        result,
        [
            "unobserved_goal_axes",
            "goal_axis_completeness_gate.unobserved_goal_axes",
            "qualitative_review_packet.unobserved_goal_axes",
            "anti_loop_progress_gate.unobserved_goal_axes",
            "result.goal_axis_completeness_gate.unobserved_goal_axes",
            "result.anti_loop_progress_gate.unobserved_goal_axes",
        ],
    )
    goal_axis_failed = boolish(
        first_present(
            result,
            [
                "goal_axis_completeness_failed",
                "goal_axis_completeness_gate.failed",
                "goal_axis_completeness_gate.evaluation_failed",
                "anti_loop_progress_gate.goal_axis_completeness_gate.failed",
                "result.goal_axis_completeness_gate.failed",
            ],
        )
    ) or str(
        first_present(
            result,
            [
                "goal_axis_completeness_gate.evaluation_status",
                "anti_loop_progress_gate.goal_axis_completeness_gate.evaluation_status",
                "result.goal_axis_completeness_gate.evaluation_status",
            ],
        )
        or ""
    ).lower() == "fail"
    facts.goal_axis_failed = goal_axis_failed
    facts.pass_with_unobserved_axes = pass_with_unobserved_axes
    facts.unobserved_goal_axes = unobserved_goal_axes


def _check_progress_evidence_part_04(facts: DeriveFacts) -> None:
    result = facts.result
    generation_dependent_count_key = boolish(
        first_present(
            result,
            [
                "generation_dependent_count_key",
                "count_key_hygiene_gate.generation_dependent_count_key",
                "anti_loop_progress_gate.generation_dependent_count_key",
                "anti_loop_progress_gate.count_key_hygiene_gate.generation_dependent_count_key",
                "result.anti_loop_progress_gate.generation_dependent_count_key",
                "result.anti_loop_progress_gate.count_key_hygiene_gate.generation_dependent_count_key",
            ],
        )
    )
    effective_count_key = first_present(
        result,
        [
            "effective_count_key",
            "count_key_hygiene_gate.effective_count_key",
            "root_dominant_parameter_key",
            "anti_loop_progress_gate.effective_count_key",
            "anti_loop_progress_gate.root_dominant_parameter_key",
            "anti_loop_progress_gate.terminal_outcome_family_key",
            "result.anti_loop_progress_gate.effective_count_key",
            "result.anti_loop_progress_gate.terminal_outcome_family_key",
        ],
    )
    generation_key_novelty_claim = boolish(
        first_present(
            result,
            [
                "family_novelty_claim",
                "new_family_claim",
                "stall_reset_claim",
                "count_key_hygiene_gate.family_novelty_claim",
                "count_key_hygiene_gate.stall_reset_claim",
                "anti_loop_progress_gate.count_key_hygiene_gate.family_novelty_claim",
                "result.anti_loop_progress_gate.count_key_hygiene_gate.stall_reset_claim",
            ],
        )
    )
    cycle_fixed_cost_present = first_present(
        result,
        [
            "cycle_fixed_cost",
            "residual_gap_cost_policy.cycle_fixed_cost",
            "cycle_efficiency_profile.cycle_fixed_cost",
            "anti_loop_progress_gate.cycle_fixed_cost",
            "result.anti_loop_progress_gate.cycle_fixed_cost",
        ],
    ) is not None
    facts.cycle_fixed_cost_present = cycle_fixed_cost_present
    facts.effective_count_key = effective_count_key
    facts.generation_dependent_count_key = generation_dependent_count_key
    facts.generation_key_novelty_claim = generation_key_novelty_claim


def _check_progress_evidence_part_05(facts: DeriveFacts) -> None:
    attested_only_movement = facts.attested_only_movement
    coupled_verifier = facts.coupled_verifier
    effective_count_key = facts.effective_count_key
    findings = facts.findings
    generation_dependent_count_key = facts.generation_dependent_count_key
    goal_axis_failed = facts.goal_axis_failed
    mode = facts.mode
    pass_with_unobserved_axes = facts.pass_with_unobserved_axes
    progress_kind = facts.progress_kind
    result = facts.result
    selected_source = facts.selected_source
    unobserved_goal_axes = facts.unobserved_goal_axes
    marginal_value_per_cycle_cost = float_value(
        first_present(
            result,
            [
                "marginal_value_per_cycle_cost",
                "residual_gap_cost_policy.marginal_value_per_cycle_cost",
                "anti_loop_progress_gate.marginal_value_per_cycle_cost",
                "result.anti_loop_progress_gate.marginal_value_per_cycle_cost",
            ],
        )
    )
    residual_cost_below_policy = boolish(
        first_present(
            result,
            [
                "residual_gap_cost_below_policy",
                "value_per_cycle_cost_below_policy",
                "cost_disproportionate_residual",
                "residual_gap_cost_policy.below_policy",
                "residual_gap_cost_policy.cost_disproportionate",
                "anti_loop_progress_gate.residual_gap_cost_policy.below_policy",
                "result.anti_loop_progress_gate.residual_gap_cost_policy.below_policy",
            ],
        )
    )
    if progress_kind == "goal_productive" and coupled_verifier and selected_source != "terminal_blocked":
        add(
            findings,
            "block" if mode == "block" else "warn",
            "derive_goal_productive_from_coupled_verifier",
            "`derive` cannot classify work as goal_productive from pass_with_coupled_verifier; select non-coupled revalidation, independent recalculation, residual descope, terminal block, or user escalation.",
        )
    if progress_kind == "goal_productive" and attested_only_movement and selected_source != "terminal_blocked":
        add(
            findings,
            "block" if mode == "block" else "warn",
            "derive_goal_productive_from_attested_only_movement",
            "`derive` cannot classify producer-attested metric movement as goal_productive or high-water progress.",
        )
    if progress_kind == "goal_productive" and (pass_with_unobserved_axes or non_empty(unobserved_goal_axes) or goal_axis_failed) and selected_source != "terminal_blocked":
        add(
            findings,
            "block" if mode == "block" else "warn",
            "derive_goal_productive_from_unobserved_axes",
            "`derive` cannot consume a qualitative review pass as goal_productive for measurable goals with zero mapped observing axes; select axis supply, residual descope, terminal block, or user escalation.",
            {"unobserved_goal_axes": unobserved_goal_axes or None},
        )
    if generation_dependent_count_key and not effective_count_key:
        add(
            findings,
            "block" if mode == "block" else "warn",
            "derive_generation_count_key_without_effective_key",
            "Generation-dependent family/count keys are trace-only; derive must carry an effective adapter-collapsed key or terminal-outcome family fallback.",
        )
    facts.marginal_value_per_cycle_cost = marginal_value_per_cycle_cost
    facts.residual_cost_below_policy = residual_cost_below_policy


def _check_progress_evidence_part_06(facts: DeriveFacts) -> None:
    c4_user_escalation = facts.c4_user_escalation
    cycle_fixed_cost_present = facts.cycle_fixed_cost_present
    descope_with_residual = facts.descope_with_residual
    findings = facts.findings
    generation_dependent_count_key = facts.generation_dependent_count_key
    generation_key_novelty_claim = facts.generation_key_novelty_claim
    marginal_repair = facts.marginal_repair
    marginal_repair_override = facts.marginal_repair_override
    marginal_value_per_cycle_cost = facts.marginal_value_per_cycle_cost
    mode = facts.mode
    next_capability_rung = facts.next_capability_rung
    primary_metric_stalled = facts.primary_metric_stalled
    progress_kind = facts.progress_kind
    residual_cost_below_policy = facts.residual_cost_below_policy
    result = facts.result
    selected_source = facts.selected_source
    terminal_selected = facts.terminal_selected
    if generation_dependent_count_key and generation_key_novelty_claim and not terminal_selected:
        add(
            findings,
            "block" if mode == "block" else "warn",
            "derive_family_novelty_from_generation_key",
            "`derive` must not treat task/advice/pack/cycle/run/date/hash/version churn as a new family or stall reset.",
        )
    if c4_user_escalation and selected_source != "terminal_blocked" and selected_disposition(result, selected_source, progress_kind) != "user_escalation" and not forced_task_kind(result):
        add(
            findings,
            "block" if mode == "block" else "warn",
            "derive_c4_user_escalation_not_selected",
            "`derive` must select user escalation when the primary-metric C4 backstop is required and no actionable forced task is present.",
        )
    if primary_metric_stalled and progress_kind == "goal_productive" and not forced_task_kind(result) and not terminal_selected:
        add(
            findings,
            "block" if mode == "block" else "warn",
            "derive_primary_metric_stall_without_forced_task",
            "`derive` cannot choose ordinary goal_productive work during primary-metric stall without selecting an emitted forced-retarget task.",
        )
    if marginal_repair and progress_kind == "goal_productive" and not (descope_with_residual and next_capability_rung) and not marginal_repair_override and selected_source != "terminal_blocked":
        add(
            findings,
            "block" if mode == "block" else "warn",
            "derive_marginal_repair_without_descope_or_value_case",
            "`derive` must rank below-threshold residual-gap repair behind explicit descope-with-residual plus the next capability rung unless higher marginal value is recorded.",
        )
    if marginal_repair and cycle_fixed_cost_present and marginal_value_per_cycle_cost is None:
        add(
            findings,
            "block" if mode == "block" else "warn",
            "derive_residual_cycle_cost_missing_ratio",
            "Residual repair with cycle-cost evidence must carry `marginal_value_per_cycle_cost`, or explicitly fall back to denominator 1 when cost evidence is absent.",
        )
    if progress_kind == "goal_productive" and residual_cost_below_policy and not (descope_with_residual and next_capability_rung) and not marginal_repair_override and selected_source != "terminal_blocked":
        add(
            findings,
            "block" if mode == "block" else "warn",
            "derive_residual_cost_below_policy_goal_productive",
            "`derive` cannot select another same-gap goal_productive repair when value per cycle cost is below policy without explicit residual descope, next rung, or a higher value case.",
        )
    forced_kind = forced_task_kind(result)
    facts.forced_kind = forced_kind


def check_progress_evidence(facts: DeriveFacts) -> None:
    _check_progress_evidence_part_01(facts)
    _check_progress_evidence_part_02(facts)
    _check_progress_evidence_part_03(facts)
    _check_progress_evidence_part_04(facts)
    _check_progress_evidence_part_05(facts)
    _check_progress_evidence_part_06(facts)

