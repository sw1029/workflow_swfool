from __future__ import annotations

from .shared import (
    boolish,
    first_present,
    list_values,
)
from .state import CompletionFacts


def _check_acceptance_facts_part_01(facts: CompletionFacts) -> None:
    result = facts.result
    acceptance_diluted = boolish(
        first_present(
            result,
            [
                "acceptance_diluted",
                "acceptance_provenance_gate.acceptance_diluted",
                "scope_fidelity_gate.acceptance_diluted",
                "result.acceptance_provenance_gate.acceptance_diluted",
            ],
        )
    )
    target_met = boolish(
        first_present(
            result,
            [
                "acceptance_target_met",
                "acceptance_provenance_gate.target_met",
                "scope_fidelity_gate.target_met",
                "result.acceptance_provenance_gate.target_met",
            ],
        )
    )
    explicit_descope = boolish(
        first_present(
            result,
            [
                "explicit_descope_decision",
                "acceptance_provenance_gate.explicit_descope_decision",
                "scope_fidelity_gate.explicit_descope_decision",
                "result.acceptance_provenance_gate.explicit_descope_decision",
            ],
        )
    )
    measurable_target_required = boolish(
        first_present(
            result,
            [
                "measurable_target_required",
                "acceptance_provenance_gate.measurable_target_required",
                "scope_fidelity_gate.measurable_target_required",
                "task_pack_item.scope_fidelity.measurable_target_required",
                "result.acceptance_provenance_gate.measurable_target_required",
            ],
        )
    )
    facts.acceptance_diluted = acceptance_diluted
    facts.explicit_descope = explicit_descope
    facts.measurable_target_required = measurable_target_required
    facts.target_met = target_met


def _check_acceptance_facts_part_02(facts: CompletionFacts) -> None:
    result = facts.result
    unverifiable_acceptance = boolish(
        first_present(
            result,
            [
                "unverifiable_acceptance_contract",
                "acceptance_verifier_gate.unverifiable_acceptance_contract",
                "acceptance_verifier_contract.unverifiable_acceptance_contract",
                "result.acceptance_verifier_gate.unverifiable_acceptance_contract",
            ],
        )
    )
    required_verifier_not_evaluated = boolish(
        first_present(
            result,
            [
                "acceptance_verifier_not_evaluated",
                "acceptance_verifier_gate.acceptance_verifier_not_evaluated",
                "acceptance_verifier_contract.acceptance_verifier_not_evaluated",
                "result.acceptance_verifier_gate.acceptance_verifier_not_evaluated",
            ],
        )
    )
    pass_with_coupled_verifier = boolish(
        first_present(
            result,
            [
                "pass_with_coupled_verifier",
                "coupled_verifier_gate.pass_with_coupled_verifier",
                "acceptance_verifier_gate.pass_with_coupled_verifier",
                "anti_loop_progress_gate.pass_with_coupled_verifier",
                "result.coupled_verifier_gate.pass_with_coupled_verifier",
                "result.anti_loop_progress_gate.pass_with_coupled_verifier",
            ],
        )
    )
    non_coupled_revalidated = boolish(
        first_present(
            result,
            [
                "non_coupled_revalidation_passed",
                "coupled_verifier_gate.non_coupled_revalidation_passed",
                "acceptance_verifier_gate.non_coupled_revalidation_passed",
                "independent_evidence_recalculation_passed",
                "evidence_provenance_gate.independent_evidence_recalculation_passed",
            ],
        )
    )
    facts.non_coupled_revalidated = non_coupled_revalidated
    facts.pass_with_coupled_verifier = pass_with_coupled_verifier
    facts.required_verifier_not_evaluated = required_verifier_not_evaluated
    facts.unverifiable_acceptance = unverifiable_acceptance


def _check_acceptance_facts_part_03(facts: CompletionFacts) -> None:
    result = facts.result
    attested_only_movement = boolish(
        first_present(
            result,
            [
                "attested_only_movement",
                "evidence_provenance_gate.attested_only_movement",
                "anti_loop_progress_gate.attested_only_movement",
                "primary_metric_gate.attested_only_movement",
                "result.evidence_provenance_gate.attested_only_movement",
                "result.anti_loop_progress_gate.attested_only_movement",
            ],
        )
    )
    pass_with_unobserved_axes = boolish(
        first_present(
            result,
            [
                "pass_with_unobserved_axes",
                "goal_axis_completeness_gate.pass_with_unobserved_axes",
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
            "anti_loop_progress_gate.unobserved_goal_axes",
            "result.goal_axis_completeness_gate.unobserved_goal_axes",
            "result.anti_loop_progress_gate.unobserved_goal_axes",
        ],
    )
    generation_dependent_count_key = boolish(
        first_present(
            result,
            [
                "generation_dependent_count_key",
                "count_key_hygiene_gate.generation_dependent_count_key",
                "anti_loop_progress_gate.generation_dependent_count_key",
                "anti_loop_progress_gate.count_key_hygiene_gate.generation_dependent_count_key",
                "result.anti_loop_progress_gate.generation_dependent_count_key",
            ],
        )
    )
    facts.attested_only_movement = attested_only_movement
    facts.generation_dependent_count_key = generation_dependent_count_key
    facts.pass_with_unobserved_axes = pass_with_unobserved_axes
    facts.unobserved_goal_axes = unobserved_goal_axes


def _check_acceptance_facts_part_04(facts: CompletionFacts) -> None:
    result = facts.result
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
    residual_cost_below_policy = boolish(
        first_present(
            result,
            [
                "residual_gap_cost_below_policy",
                "value_per_cycle_cost_below_policy",
                "cost_disproportionate_residual",
                "residual_gap_cost_policy.below_policy",
                "anti_loop_progress_gate.residual_gap_cost_policy.below_policy",
                "result.anti_loop_progress_gate.residual_gap_cost_policy.below_policy",
            ],
        )
    )
    marginal_repair_override = boolish(
        first_present(
            result,
            [
                "marginal_repair_higher_value",
                "residual_gap_policy.marginal_repair_higher_value",
                "residual_gap_cost_policy.marginal_repair_higher_value",
                "anti_loop_progress_gate.marginal_repair_higher_value",
                "result.anti_loop_progress_gate.marginal_repair_higher_value",
            ],
        )
    )
    producer_attested_fields = first_present(
        result,
        [
            "producer_attested_fields",
            "evidence_provenance_gate.producer_attested_fields",
            "anti_loop_progress_gate.producer_attested_fields",
            "result.evidence_provenance_gate.producer_attested_fields",
        ],
    )
    facts.generation_key_novelty_claim = generation_key_novelty_claim
    facts.marginal_repair_override = marginal_repair_override
    facts.producer_attested_fields = producer_attested_fields
    facts.residual_cost_below_policy = residual_cost_below_policy


def _check_acceptance_facts_part_05(facts: CompletionFacts) -> None:
    result = facts.result
    independently_verified_fields = first_present(
        result,
        [
            "independently_verified_fields",
            "evidence_provenance_gate.independently_verified_fields",
            "anti_loop_progress_gate.independently_verified_fields",
            "result.evidence_provenance_gate.independently_verified_fields",
        ],
    )
    independent_source_status = str(
        first_present(
            result,
            [
                "independent_source_separation_status",
                "verification_source_separation_gate.independent_source_separation_status",
                "evidence_provenance_gate.independent_source_separation_status",
                "anti_loop_progress_gate.independent_source_separation_status",
                "result.verification_source_separation_gate.independent_source_separation_status",
                "result.anti_loop_progress_gate.independent_source_separation_status",
            ],
        )
        or ""
    ).lower()
    independent_invariant_status = str(
        first_present(
            result,
            [
                "independent_invariant_separation_status",
                "verification_source_separation_gate.independent_invariant_separation_status",
                "evidence_provenance_gate.independent_invariant_separation_status",
                "anti_loop_progress_gate.independent_invariant_separation_status",
                "result.verification_source_separation_gate.independent_invariant_separation_status",
                "result.anti_loop_progress_gate.independent_invariant_separation_status",
            ],
        )
        or ""
    ).lower()
    independently_verified_downgraded_fields = list_values(
        first_present(
            result,
            [
                "independently_verified_downgraded_fields",
                "verification_source_separation_gate.independently_verified_downgraded_fields",
                "evidence_provenance_gate.independently_verified_downgraded_fields",
                "anti_loop_progress_gate.independently_verified_downgraded_fields",
                "result.verification_source_separation_gate.independently_verified_downgraded_fields",
                "result.anti_loop_progress_gate.independently_verified_downgraded_fields",
            ],
        )
    )
    self_grounded_axes = set(
        list_values(
            first_present(
                result,
                [
                    "self_grounded_axes",
                    "verification_source_separation_gate.self_grounded_axes",
                    "evidence_provenance_gate.self_grounded_axes",
                    "anti_loop_progress_gate.self_grounded_axes",
                ],
            )
        )
    )
    independently_verified_field_set = set(list_values(independently_verified_fields))
    self_grounded_mislabeled_independent = sorted(self_grounded_axes & independently_verified_field_set)
    facts.independent_source_status = independent_source_status
    facts.independent_invariant_status = independent_invariant_status
    facts.independently_verified_downgraded_fields = independently_verified_downgraded_fields
    facts.independently_verified_fields = independently_verified_fields
    facts.self_grounded_mislabeled_independent = self_grounded_mislabeled_independent


def _check_acceptance_facts_part_06(facts: CompletionFacts) -> None:
    result = facts.result
    envelope_thaw_item_required = boolish(
        first_present(
            result,
            [
                "envelope_thaw_item_required",
                "acceptance_reachability_gate.envelope_thaw_item_required",
                "anti_loop_progress_gate.envelope_thaw_item_required",
                "result.acceptance_reachability_gate.envelope_thaw_item_required",
                "result.anti_loop_progress_gate.envelope_thaw_item_required",
            ],
        )
    )
    envelope_thaw_item = first_present(
        result,
        [
            "envelope_thaw_item",
            "acceptance_reachability_gate.envelope_thaw_item",
            "anti_loop_progress_gate.envelope_thaw_item",
            "result.acceptance_reachability_gate.envelope_thaw_item",
            "result.anti_loop_progress_gate.envelope_thaw_item",
        ],
    )
    terminal_stage_contradiction = boolish(
        first_present(
            result,
            [
                "terminal_classification_stage_contradiction",
                "failure_surface_stage_gate.terminal_classification_stage_contradiction",
                "anti_loop_progress_gate.terminal_classification_stage_contradiction",
                "result.anti_loop_progress_gate.terminal_classification_stage_contradiction",
            ],
        )
    )
    same_input_contract_violation = boolish(
        first_present(
            result,
            [
                "same_input_contract_violation",
                "same_input_contract_gate.same_input_contract_violation",
                "anti_loop_progress_gate.same_input_contract_violation",
                "result.anti_loop_progress_gate.same_input_contract_violation",
            ],
        )
    )
    instrumentation_supply_required = boolish(
        first_present(
            result,
            [
                "instrumentation_supply_required",
                "diagnostics_unavailable_gate.instrumentation_supply_required",
                "anti_loop_progress_gate.instrumentation_supply_required",
                "result.anti_loop_progress_gate.instrumentation_supply_required",
            ],
        )
    )
    facts.envelope_thaw_item = envelope_thaw_item
    facts.envelope_thaw_item_required = envelope_thaw_item_required
    facts.instrumentation_supply_required = instrumentation_supply_required
    facts.same_input_contract_violation = same_input_contract_violation
    facts.terminal_stage_contradiction = terminal_stage_contradiction


def _check_acceptance_facts_part_07(facts: CompletionFacts) -> None:
    result = facts.result
    expectation_lineage_stale = boolish(
        first_present(
            result,
            [
                "expectation_lineage_stale",
                "expectation_lineage_gate.expectation_lineage_stale",
                "anti_loop_progress_gate.expectation_lineage_stale",
                "result.expectation_lineage_gate.expectation_lineage_stale",
            ],
        )
    )
    expectation_anchor_missing = boolish(
        first_present(
            result,
            [
                "expectation_anchor_missing",
                "expectation_lineage_gate.expectation_anchor_missing",
                "anti_loop_progress_gate.expectation_anchor_missing",
                "result.expectation_lineage_gate.expectation_anchor_missing",
            ],
        )
    )
    expectation_rebaselined = boolish(
        first_present(
            result,
            [
                "expectation_rebaselined",
                "expectation_lineage_gate.expectation_rebaselined",
                "designated_baseline_recomputed",
                "result.expectation_lineage_gate.expectation_rebaselined",
            ],
        )
    )
    lineage_verified_expectation_claim = boolish(
        first_present(
            result,
            [
                "lineage_verified_expectation_claim",
                "expectation_lineage_verified_claim",
                "baseline_lineage_claim",
                "comparison_lineage_claim",
                "expectation_lineage_gate.lineage_verified_expectation_claim",
            ],
        )
    )
    facts.expectation_anchor_missing = expectation_anchor_missing
    facts.expectation_lineage_stale = expectation_lineage_stale
    facts.expectation_rebaselined = expectation_rebaselined
    facts.lineage_verified_expectation_claim = lineage_verified_expectation_claim


def _check_acceptance_facts_part_08(facts: CompletionFacts) -> None:
    result = facts.result
    comparison_contract = boolish(
        first_present(
            result,
            [
                "comparison_contract",
                "comparison_claim",
                "baseline_claim",
                "adoption_claim",
                "comparison_parity_gate.comparison_contract",
                "result.comparison_parity_gate.comparison_contract",
            ],
        )
    )
    parity_axis_status_value = first_present(
        result,
        [
            "parity_axis_status",
            "parity_axes_status",
            "comparison_parity_gate.parity_axis_status",
            "comparison_parity_gate.parity_axes",
            "anti_loop_progress_gate.comparison_parity_gate.parity_axis_status",
            "result.comparison_parity_gate.parity_axis_status",
        ],
    )
    facts.comparison_contract = comparison_contract
    facts.parity_axis_status_value = parity_axis_status_value


def check_acceptance_facts(facts: CompletionFacts) -> None:
    _check_acceptance_facts_part_01(facts)
    _check_acceptance_facts_part_02(facts)
    _check_acceptance_facts_part_03(facts)
    _check_acceptance_facts_part_04(facts)
    _check_acceptance_facts_part_05(facts)
    _check_acceptance_facts_part_06(facts)
    _check_acceptance_facts_part_07(facts)
    _check_acceptance_facts_part_08(facts)
