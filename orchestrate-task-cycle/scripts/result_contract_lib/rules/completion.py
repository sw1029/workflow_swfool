from __future__ import annotations

import json

from ..base import RuleContext, TargetContractRule
from ..common import add, boolish, first_present, list_values, non_empty, nonzero_scalar, value_for


class CompletionValidationRule(TargetContractRule):
    """Enforce completion, progress, evidence, and close-time integrity rules."""

    targets = frozenset({'validate'})

    def check(self, context: RuleContext) -> None:
        result = context.result
        mode = context.mode
        findings = context.findings
        validation_verdict = str(value_for(result, "validation_verdict") or "").strip().lower()
        progress_verdict = str(value_for(result, "progress_verdict") or "").strip().lower()
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
        if isinstance(parity_axis_status_value, (dict, list)):
            parity_axis_status_text = json.dumps(parity_axis_status_value, sort_keys=True, ensure_ascii=False).lower()
        else:
            parity_axis_status_text = str(parity_axis_status_value or "").lower()
        parity_unverified = boolish(
            first_present(
                result,
                [
                    "parity_unverified",
                    "comparison_parity_gate.parity_unverified",
                    "anti_loop_progress_gate.parity_unverified",
                    "result.comparison_parity_gate.parity_unverified",
                ],
            )
        )
        unknown_parity_axes = list_values(
            first_present(
                result,
                [
                    "unknown_parity_axes",
                    "parity_unknown_axes",
                    "comparison_parity_gate.unknown_parity_axes",
                    "anti_loop_progress_gate.unknown_parity_axes",
                    "result.comparison_parity_gate.unknown_parity_axes",
                ],
            )
        ) or ("unknown" in parity_axis_status_text)
        majority_vote_adoption = boolish(
            first_present(
                result,
                [
                    "majority_vote_adoption",
                    "adoption_axis_gate.majority_vote_adoption",
                    "comparison_parity_gate.majority_vote_adoption",
                    "result.adoption_axis_gate.majority_vote_adoption",
                ],
            )
        )
        provisional_adoption = boolish(
            first_present(
                result,
                [
                    "provisional_adoption",
                    "adoption_axis_gate.provisional_adoption",
                    "comparison_parity_gate.provisional_adoption",
                    "result.adoption_axis_gate.provisional_adoption",
                ],
            )
        )
        adoption_axis_classification = first_present(
            result,
            [
                "adoption_axis_classification",
                "adoption_axis_gate.adoption_axis_classification",
                "comparison_parity_gate.adoption_axis_classification",
                "result.adoption_axis_gate.adoption_axis_classification",
            ],
        )
        measured_but_disqualified = boolish(
            first_present(
                result,
                [
                    "measured_but_disqualified",
                    "adoption_axis_gate.measured_but_disqualified",
                    "comparison_parity_gate.measured_but_disqualified",
                    "anti_loop_progress_gate.measured_but_disqualified",
                    "result.adoption_axis_gate.measured_but_disqualified",
                ],
            )
        )
        failed_gating_axis = boolish(
            first_present(
                result,
                [
                    "failed_gating_axis",
                    "gating_axis_failed",
                    "adoption_axis_gate.failed_gating_axis",
                    "comparison_parity_gate.failed_gating_axis",
                    "anti_loop_progress_gate.failed_gating_axis",
                    "result.adoption_axis_gate.failed_gating_axis",
                ],
            )
        )
        required_resolution_value = first_present(
            result,
            [
                "required_evidence_resolution",
                "resolution_downgrade_gate.required_evidence_resolution",
                "anti_loop_progress_gate.required_evidence_resolution",
                "result.resolution_downgrade_gate.required_evidence_resolution",
            ],
        )
        observed_resolution_value = first_present(
            result,
            [
                "observed_evidence_resolution",
                "resolution_downgrade_gate.observed_evidence_resolution",
                "anti_loop_progress_gate.observed_evidence_resolution",
                "result.resolution_downgrade_gate.observed_evidence_resolution",
            ],
        )
        required_resolution = str(required_resolution_value or "").strip().lower()
        observed_resolution = str(observed_resolution_value or "").strip().lower()
        high_resolution_contract_required = boolish(
            first_present(
                result,
                [
                    "high_resolution_contract_required",
                    "resolution_downgrade_gate.high_resolution_contract_required",
                    "anti_loop_progress_gate.high_resolution_contract_required",
                    "result.resolution_downgrade_gate.high_resolution_contract_required",
                ],
            )
        ) or required_resolution in {"high", "full", "original", "direct", "terminal", "authoritative"}
        resolution_downgrade = boolish(
            first_present(
                result,
                [
                    "resolution_downgrade",
                    "resolution_downgrade_gate.resolution_downgrade",
                    "anti_loop_progress_gate.resolution_downgrade",
                    "result.resolution_downgrade_gate.resolution_downgrade",
                ],
            )
        ) or (
            high_resolution_contract_required
            and observed_resolution
            and observed_resolution not in {required_resolution, "high", "full", "original", "direct", "terminal", "authoritative"}
        )
        resolution_restored = boolish(
            first_present(
                result,
                [
                    "resolution_restored",
                    "observed_evidence_resolution_restored",
                    "resolution_downgrade_gate.resolution_restored",
                    "result.resolution_downgrade_gate.resolution_restored",
                ],
            )
        )
        resolution_contract_revised = boolish(
            first_present(
                result,
                [
                    "resolution_contract_revised",
                    "evidence_resolution_contract_revised",
                    "required_evidence_resolution_revised",
                    "resolution_downgrade_gate.contract_revised",
                    "result.resolution_downgrade_gate.contract_revised",
                ],
            )
        )
        pass_on_stale_lane = boolish(
            first_present(
                result,
                [
                    "pass_on_stale_lane",
                    "lane_identity_gate.pass_on_stale_lane",
                    "anti_loop_progress_gate.pass_on_stale_lane",
                    "result.lane_identity_gate.pass_on_stale_lane",
                ],
            )
        )
        lane_identity_missing = boolish(
            first_present(
                result,
                [
                    "lane_identity_missing",
                    "lane_identity_gate.lane_identity_missing",
                    "anti_loop_progress_gate.lane_identity_missing",
                    "result.lane_identity_gate.lane_identity_missing",
                ],
            )
        )
        current_lane_revalidated = non_empty(
            first_present(
                result,
                [
                    "current_lane_revalidated",
                    "current_lane_rerun_complete",
                    "lane_identity_gate.current_lane_revalidated",
                    "result.lane_identity_gate.current_lane_revalidated",
                ],
            )
        )
        decision_metadata_revision = boolish(
            first_present(
                result,
                [
                    "decision_metadata_revision",
                    "stale_measurement_artifact",
                    "decision_freshness_gate.decision_metadata_revision",
                    "decision_freshness_gate.stale_measurement_artifact",
                    "anti_loop_progress_gate.decision_metadata_revision",
                    "result.decision_freshness_gate.decision_metadata_revision",
                ],
            )
        )
        fresh_measurement_present = non_empty(
            first_present(
                result,
                [
                    "fresh_current_lane_run_id",
                    "fresh_measurement_run_id",
                    "measurement_run_id",
                    "decision_freshness_gate.fresh_current_lane_run_id",
                    "decision_freshness_gate.no_impact_proof",
                    "upstream_contract_no_impact_proof",
                    "result.decision_freshness_gate.fresh_current_lane_run_id",
                ],
            )
        )
        axis_starved_by_missing_producer = boolish(
            first_present(
                result,
                [
                    "axis_starved_by_missing_producer",
                    "gating_axis_producer_gate.axis_starved_by_missing_producer",
                    "anti_loop_progress_gate.axis_starved_by_missing_producer",
                    "result.gating_axis_producer_gate.axis_starved_by_missing_producer",
                ],
            )
        )
        producer_supply_complete = non_empty(
            first_present(
                result,
                [
                    "producer_supply_complete",
                    "producer_path_fired",
                    "gating_axis_producer_gate.producer_supply_complete",
                    "result.gating_axis_producer_gate.producer_supply_complete",
                ],
            )
        )
        portfolio_quota_exceeded = boolish(
            first_present(
                result,
                [
                    "portfolio_quota_exceeded",
                    "portfolio_quota_gate.portfolio_quota_exceeded",
                    "anti_loop_progress_gate.portfolio_quota_exceeded",
                    "result.portfolio_quota_gate.portfolio_quota_exceeded",
                ],
            )
        )
        portfolio_quota_mode = str(
            first_present(
                result,
                [
                    "portfolio_quota_mode",
                    "portfolio_quota_gate.portfolio_quota_mode",
                    "portfolio_quota_gate.mode",
                    "anti_loop_progress_gate.portfolio_quota_mode",
                    "result.portfolio_quota_gate.portfolio_quota_mode",
                ],
            )
            or ""
        ).lower()
        portfolio_quota_restrictive = portfolio_quota_mode in {"restrict", "restricted", "block", "blocking"}
        unreachable_within_cycle = boolish(
            first_present(
                result,
                [
                    "unreachable_within_cycle",
                    "cycle_reachability_gate.unreachable_within_cycle",
                    "acceptance_reachability_gate.unreachable_within_cycle",
                    "anti_loop_progress_gate.unreachable_within_cycle",
                    "result.cycle_reachability_gate.unreachable_within_cycle",
                ],
            )
        )
        harvest_validated = non_empty(
            first_present(
                result,
                [
                    "long_run_harvest_validated",
                    "harvest_validation_complete",
                    "cycle_reachability_gate.harvest_validation_complete",
                    "throughput_improved",
                    "cycle_reachability_gate.throughput_improved",
                    "result.cycle_reachability_gate.harvest_validation_complete",
                ],
            )
        )
        basis_overclaim = boolish(
            first_present(
                result,
                [
                    "basis_overclaim",
                    "metric_basis_gate.basis_overclaim",
                    "anti_loop_progress_gate.basis_overclaim",
                    "result.metric_basis_gate.basis_overclaim",
                ],
            )
        )
        basis_compatible_inputs = non_empty(
            first_present(
                result,
                [
                    "basis_compatible_inputs_present",
                    "basis_overclaim_resolved",
                    "metric_basis_gate.basis_compatible_inputs_present",
                    "metric_basis_gate.basis_overclaim_resolved",
                    "result.metric_basis_gate.basis_compatible_inputs_present",
                ],
            )
        )
        surface_field_defect_matrix = first_present(
            result,
            [
                "surface_field_defect_matrix",
                "surface_field_review_gate.surface_field_defect_matrix",
                "qualitative_review_packet.surface_field_defect_matrix",
                "result.surface_field_review_gate.surface_field_defect_matrix",
            ],
        )
        surface_field_defects = nonzero_scalar(surface_field_defect_matrix)
        field_class_map_missing = boolish(
            first_present(
                result,
                [
                    "field_class_map_missing",
                    "surface_field_review_gate.field_class_map_missing",
                    "qualitative_review_packet.field_class_map_missing",
                    "result.surface_field_review_gate.field_class_map_missing",
                ],
            )
        )
        surface_field_repaired = non_empty(
            first_present(
                result,
                [
                    "surface_field_repair_complete",
                    "field_class_repair_complete",
                    "surface_field_review_gate.surface_field_repair_complete",
                    "result.surface_field_review_gate.surface_field_repair_complete",
                ],
            )
        )
        harvest_gate_unaudited = boolish(
            first_present(
                result,
                [
                    "harvest_gate_unaudited",
                    "harvest_contract_preflight.harvest_gate_unaudited",
                    "harvest_contract_preflight_gate.harvest_gate_unaudited",
                    "anti_loop_progress_gate.harvest_gate_unaudited",
                    "result.harvest_contract_preflight_gate.harvest_gate_unaudited",
                ],
            )
        )
        harvest_risk_accepted = boolish(
            first_present(
                result,
                [
                    "harvest_risk_accepted",
                    "harvest_contract_preflight.harvest_risk_accepted",
                    "harvest_contract_preflight_gate.harvest_risk_accepted",
                    "anti_loop_progress_gate.harvest_risk_accepted",
                    "result.harvest_contract_preflight_gate.harvest_risk_accepted",
                ],
            )
        )
        harvest_preflight_incompatible = any(
            boolish(
                first_present(
                    result,
                    [
                        field,
                        f"harvest_contract_preflight.{field}",
                        f"harvest_contract_preflight_gate.{field}",
                        f"anti_loop_progress_gate.{field}",
                        f"anti_loop_progress_gate.harvest_contract_preflight.{field}",
                        f"result.harvest_contract_preflight_gate.{field}",
                    ],
                )
            )
            for field in ("lane_incompatible", "scale_incompatible", "contract_conflict")
        )
        harvest_gate_repaired = non_empty(
            first_present(
                result,
                [
                    "harvest_gate_repair_complete",
                    "harvest_gate_mitigation_complete",
                    "harvest_contract_preflight_gate.repair_complete",
                    "harvest_contract_preflight_gate.mitigation_complete",
                    "result.harvest_contract_preflight_gate.repair_complete",
                ],
            )
        )
        high_cost_artifact = boolish(
            first_present(
                result,
                [
                    "high_cost_artifact",
                    "disposal_proportionality_gate.high_cost_artifact",
                    "run_disposition_gate.high_cost_artifact",
                    "anti_loop_progress_gate.high_cost_artifact",
                    "result.disposal_proportionality_gate.high_cost_artifact",
                ],
            )
        )
        destructive_disposition_requested = boolish(
            first_present(
                result,
                [
                    "destructive_disposition_requested",
                    "destructive_disposition",
                    "disposal_proportionality_gate.destructive_disposition_requested",
                    "run_disposition_gate.destructive_disposition_requested",
                    "result.disposal_proportionality_gate.destructive_disposition_requested",
                ],
            )
        )
        destructive_disposition_blocked = boolish(
            first_present(
                result,
                [
                    "destructive_disposition_blocked",
                    "disposal_proportionality_gate.destructive_disposition_blocked",
                    "anti_loop_progress_gate.destructive_disposition_blocked",
                    "result.disposal_proportionality_gate.destructive_disposition_blocked",
                ],
            )
        )
        safety_violation = boolish(
            first_present(
                result,
                [
                    "safety_violation",
                    "safety_policy_violation",
                    "disposal_proportionality_gate.safety_violation",
                    "run_disposition_gate.safety_violation",
                ],
            )
        )
        destructive_high_cost = (destructive_disposition_blocked or (high_cost_artifact and destructive_disposition_requested)) and not safety_violation
        quarantine_preserved = non_empty(
            first_present(
                result,
                [
                    "quarantine_path",
                    "quarantine_complete",
                    "artifact_quarantined",
                    "disposal_proportionality_gate.quarantine_path",
                    "disposal_proportionality_gate.quarantine_complete",
                    "result.disposal_proportionality_gate.quarantine_path",
                ],
            )
        )
        rerun_before_reharvest = boolish(
            first_present(
                result,
                [
                    "rerun_before_reharvest",
                    "disposal_proportionality_gate.rerun_before_reharvest",
                    "anti_loop_progress_gate.rerun_before_reharvest",
                    "result.disposal_proportionality_gate.rerun_before_reharvest",
                ],
            )
        )
        reharvest_complete = non_empty(
            first_present(
                result,
                [
                    "reharvest_complete",
                    "reharvest_attempted",
                    "reharvest_terminal_blocked",
                    "disposal_proportionality_gate.reharvest_complete",
                    "disposal_proportionality_gate.reharvest_attempted",
                    "result.disposal_proportionality_gate.reharvest_complete",
                ],
            )
        )
        mutually_unsatisfiable_contract = boolish(
            first_present(
                result,
                [
                    "mutually_unsatisfiable_contract",
                    "contract_satisfiability_gate.mutually_unsatisfiable_contract",
                    "validation_predicate_contract.mutually_unsatisfiable_contract",
                    "anti_loop_progress_gate.mutually_unsatisfiable_contract",
                    "result.contract_satisfiability_gate.mutually_unsatisfiable_contract",
                ],
            )
        )
        predicate_directive_reconciled = non_empty(
            first_present(
                result,
                [
                    "predicate_directive_reconciled",
                    "contract_satisfiability_gate.reconciled",
                    "contract_satisfiability_gate.contract_repaired",
                    "same_task_contract_repair_complete",
                    "result.contract_satisfiability_gate.reconciled",
                ],
            )
        )
        closed_world_consumption = boolish(
            first_present(
                result,
                [
                    "closed_world_collection_consumption",
                    "collection_consumption_gate.closed_world_collection_consumption",
                    "result.collection_consumption_gate.closed_world_collection_consumption",
                ],
            )
        )
        collection_truncated = boolish(
            first_present(
                result,
                [
                    "collection_truncated",
                    "collection_partial",
                    "collection_sampled",
                    "collection_consumption_gate.collection_truncated",
                    "collection_consumption_gate.collection_partial",
                    "collection_consumption_gate.collection_sampled",
                    "result.collection_consumption_gate.collection_truncated",
                ],
            )
        )
        sample_as_universe_misuse = boolish(
            first_present(
                result,
                [
                    "sample_as_universe_misuse",
                    "collection_consumption_gate.sample_as_universe_misuse",
                    "closed_world_collection_consumption.sample_as_universe_misuse",
                    "anti_loop_progress_gate.sample_as_universe_misuse",
                    "result.collection_consumption_gate.sample_as_universe_misuse",
                ],
            )
        )
        full_collection_supplied = non_empty(
            first_present(
                result,
                [
                    "full_collection_supplied",
                    "full_collection_path",
                    "untruncated_collection_supplied",
                    "sample_only_contract_revision",
                    "collection_consumption_gate.full_collection_supplied",
                    "collection_consumption_gate.sample_only_contract_revision",
                    "result.collection_consumption_gate.full_collection_supplied",
                ],
            )
        )
        collection_closed_world_misuse = sample_as_universe_misuse or (closed_world_consumption and collection_truncated)
        if lane_identity_missing:
            add(
                findings,
                "warn",
                "lane_identity_missing",
                "`lane_identity_missing` is fail-quiet warning evidence; do not invent lane-key components in the result contract.",
            )
        if acceptance_diluted and validation_verdict in {"complete", "passed", "pass"}:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "validate_acceptance_diluted_complete",
                "`validate` cannot report complete when original directive acceptance was diluted; return partial and preserve residual scope.",
            )
        if measurable_target_required and validation_verdict in {"complete", "passed", "pass"} and not target_met and not explicit_descope:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "validate_measurable_target_unmet_complete",
                "`validate` cannot complete a measurable directive-derived item without meeting the original target or recording explicit descope plus residual scope.",
            )
        if (unverifiable_acceptance or required_verifier_not_evaluated) and validation_verdict in {"complete", "passed", "pass"} and not explicit_descope:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "validate_unverifiable_acceptance_complete",
                "`validate` cannot complete a measurable target when a required verifier is not_evaluated; return partial and preserve verifier or residual scope.",
            )
        if pass_with_coupled_verifier and validation_verdict in {"complete", "passed", "pass"} and not (explicit_descope or non_coupled_revalidated):
            add(
                findings,
                "block" if mode == "block" else "warn",
                "validate_coupled_verifier_complete",
                "`validate` cannot complete verifier-backed work from pass_with_coupled_verifier; require later non-coupled revalidation, independent recalculation, or explicit residual descope.",
            )
        if (pass_with_unobserved_axes or non_empty(unobserved_goal_axes)) and validation_verdict in {"complete", "passed", "pass"} and not explicit_descope:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "validate_unobserved_axes_complete",
                "`validate` cannot complete review-backed measurable work from pass_with_unobserved_axes; require adapter axis supply, residual scope, terminal blocker, or user escalation.",
                {"unobserved_goal_axes": unobserved_goal_axes or None},
            )
        if generation_dependent_count_key and generation_key_novelty_claim and progress_verdict == "advanced":
            add(
                findings,
                "block" if mode == "block" else "warn",
                "validate_advanced_from_generation_key_reset",
                "`validate` cannot accept family novelty, stall reset, hypothesis exhaustion, or seal escape based on generation-dependent task/advice/pack/cycle/run/date/hash/version keys.",
            )
        if residual_cost_below_policy and validation_verdict in {"complete", "passed", "pass"} and not (explicit_descope or marginal_repair_override):
            add(
                findings,
                "block" if mode == "block" else "warn",
                "validate_residual_cost_below_policy_complete",
                "`validate` cannot complete another same-gap residual repair when value per cycle cost is below policy without residual descope or a higher value case.",
            )
        if attested_only_movement and progress_verdict == "advanced" and not independently_verified_fields:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "validate_advanced_from_attested_only_movement",
                "`validate` cannot report progress_verdict: advanced from producer-attested movement without independently verified fields.",
            )
        if producer_attested_fields and not independently_verified_fields and validation_verdict in {"complete", "passed", "pass"} and not explicit_descope:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "validate_complete_from_producer_attested_fields",
                "`validate` cannot complete measurable progress from producer-attested fields alone; require independently verified evidence or residual scope.",
            )
        if independently_verified_fields and independent_source_status in {"missing", "overlap", "blocked"} and validation_verdict in {"complete", "passed", "pass"} and not explicit_descope:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "validate_independent_verification_source_not_disjoint",
                "`validate` cannot complete from independently_verified evidence unless verification_input_paths are disjoint from verified artifacts or the adapter marks the axis self_grounded.",
                {"independent_source_separation_status": independent_source_status},
            )
        if independently_verified_downgraded_fields and progress_verdict == "advanced" and not explicit_descope:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "validate_advanced_from_downgraded_independent_verification",
                "`validate` cannot report advanced progress from independently_verified fields that were auto-downgraded to attested.",
                {"downgraded_fields": independently_verified_downgraded_fields},
            )
        if envelope_thaw_item_required and validation_verdict in {"complete", "passed", "pass"} and not (explicit_descope or non_empty(envelope_thaw_item)):
            add(
                findings,
                "block" if mode == "block" else "warn",
                "validate_frozen_envelope_complete_without_thaw_item",
                "`validate` cannot complete acceptance that is unreachable under a frozen envelope without a reserved envelope_thaw_item or explicit descope.",
            )
        if terminal_stage_contradiction and validation_verdict in {"complete", "passed", "pass"}:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "validate_complete_with_terminal_classification_contradiction",
                "`validate` cannot complete while terminal classification contradicts the observed failure surface stage.",
            )
        if same_input_contract_violation and progress_verdict == "advanced":
            add(
                findings,
                "block" if mode == "block" else "warn",
                "validate_advanced_with_same_input_contract_violation",
                "`validate` cannot advance progress from same-family comparisons whose input sets do not match.",
            )
        if instrumentation_supply_required and progress_verdict == "advanced":
            add(
                findings,
                "block" if mode == "block" else "warn",
                "validate_advanced_with_instrumentation_supply_required",
                "`validate` cannot advance progress while repeated diagnostics_unavailable still requires instrumentation supply.",
            )
        if expectation_lineage_stale and validation_verdict in {"complete", "passed", "pass"} and not (explicit_descope or expectation_rebaselined):
            add(
                findings,
                "block" if mode == "block" else "warn",
                "validate_expectation_lineage_stale_complete",
                "`validate` cannot complete output-derived expectation work while expectation_lineage_stale is unresolved; rebaseline, descope residual scope, or return partial.",
            )
        if expectation_anchor_missing and lineage_verified_expectation_claim and validation_verdict in {"complete", "passed", "pass"}:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "validate_expectation_anchor_missing_lineage_claim",
                "`validate` cannot claim lineage-verified expectation evidence when expectation_anchor_missing is true.",
            )
        if comparison_contract and (parity_unverified or unknown_parity_axes) and validation_verdict in {"complete", "passed", "pass"} and not (explicit_descope or provisional_adoption):
            add(
                findings,
                "block" if mode == "block" else "warn",
                "validate_comparison_parity_unverified_complete",
                "`validate` cannot finalize baseline, comparison, or adoption work with parity_unverified or unknown parity axes.",
                {"unknown_parity_axes": unknown_parity_axes if isinstance(unknown_parity_axes, list) else None},
            )
        if comparison_contract and (parity_unverified or unknown_parity_axes) and progress_verdict == "advanced" and not (explicit_descope or provisional_adoption):
            add(
                findings,
                "block" if mode == "block" else "warn",
                "validate_advanced_with_parity_unverified",
                "`validate` cannot advance comparison or adoption progress until every required parity axis is controlled, measured, or explicitly provisional.",
            )
        if majority_vote_adoption and not non_empty(adoption_axis_classification) and validation_verdict in {"complete", "passed", "pass"} and not provisional_adoption:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "validate_majority_vote_adoption_without_axis_classification",
                "`validate` cannot finalize majority-vote adoption without adoption_axis_classification for gating and tradable axes.",
            )
        if (measured_but_disqualified or failed_gating_axis) and validation_verdict in {"complete", "passed", "pass"} and not explicit_descope:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "validate_complete_with_failed_adoption_axis",
                "`validate` cannot complete adoption when gating axes failed or measured evidence is disqualified; preserve measured_but_disqualified or route axis repair.",
            )
        if resolution_downgrade and high_resolution_contract_required and validation_verdict in {"complete", "passed", "pass"} and not (explicit_descope or resolution_restored or resolution_contract_revised):
            add(
                findings,
                "block" if mode == "block" else "warn",
                "validate_resolution_downgrade_complete",
                "`validate` cannot complete a high-resolution evidence contract from downgraded or surrogate evidence without restoration, contract revision, or residual descope.",
                {"required_evidence_resolution": required_resolution or None, "observed_evidence_resolution": observed_resolution or None},
            )
        if resolution_downgrade and progress_verdict == "advanced" and not (explicit_descope or resolution_restored or resolution_contract_revised):
            add(
                findings,
                "block" if mode == "block" else "warn",
                "validate_advanced_with_resolution_downgrade",
                "`validate` cannot report advanced progress from a downgraded evidence resolution unless the downgrade is explicitly provisional, restored, or contract-revised.",
            )
        if pass_on_stale_lane and validation_verdict in {"complete", "passed", "pass"} and not (explicit_descope or current_lane_revalidated):
            add(
                findings,
                "block" if mode == "block" else "warn",
                "validate_pass_on_stale_lane_complete",
                "`validate` cannot complete current-lane capability, adoption, comparison, close, or next-rung work from pass_on_stale_lane without current-lane rerun/revalidation or residual descope.",
            )
        if pass_on_stale_lane and progress_verdict == "advanced" and not (explicit_descope or current_lane_revalidated):
            add(
                findings,
                "block" if mode == "block" else "warn",
                "validate_advanced_from_stale_lane_pass",
                "`validate` cannot report advanced progress from a pass that belongs to a stale production lane.",
            )
        if decision_metadata_revision and validation_verdict in {"complete", "passed", "pass"} and not (explicit_descope or fresh_measurement_present):
            add(
                findings,
                "block" if mode == "block" else "warn",
                "validate_decision_metadata_revision_complete",
                "`validate` cannot complete measurement, adoption, or high-water work from decision_metadata_revision without a fresh current-lane run id or no-impact proof.",
            )
        if decision_metadata_revision and progress_verdict == "advanced" and not fresh_measurement_present:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "validate_advanced_from_decision_metadata_revision",
                "`validate` cannot report advanced progress from relabeling stale measurement artifacts after upstream contract changes.",
            )
        if axis_starved_by_missing_producer and validation_verdict in {"complete", "passed", "pass"} and not (explicit_descope or producer_supply_complete):
            add(
                findings,
                "block" if mode == "block" else "warn",
                "validate_axis_starved_by_missing_producer_complete",
                "`validate` cannot complete another verifier, guard, report, or metadata item for a producer-starved gating axis before producer supply fires.",
            )
        if axis_starved_by_missing_producer and progress_verdict == "advanced" and not producer_supply_complete:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "validate_advanced_with_producer_starved_axis",
                "`validate` cannot report advanced progress while the gating axis remains starved by a missing producer path.",
            )
        if portfolio_quota_exceeded and portfolio_quota_restrictive and progress_verdict == "advanced":
            add(
                findings,
                "block" if mode == "block" else "warn",
                "validate_advanced_during_portfolio_quota_restriction",
                "`validate` cannot report advanced progress for verifier-like work while restrictive portfolio_quota_exceeded is unresolved; require producer/envelope/long-run/descope/terminal/escalation evidence.",
            )
        elif portfolio_quota_exceeded and not portfolio_quota_restrictive:
            add(
                findings,
                "warn",
                "portfolio_quota_warn_only",
                "`portfolio_quota_exceeded` is warn-only unless the adapter supplies restrict mode.",
                {"portfolio_quota_mode": portfolio_quota_mode or None},
            )
        if unreachable_within_cycle and validation_verdict in {"complete", "passed", "pass"} and not (explicit_descope or harvest_validated):
            add(
                findings,
                "block" if mode == "block" else "warn",
                "validate_unreachable_within_cycle_complete",
                "`validate` cannot complete the original scale acceptance from small smoke, launch-only, or heartbeat evidence when unreachable_within_cycle=true; require harvest validation, throughput improvement, descope, terminal blocker, or escalation.",
            )
        if unreachable_within_cycle and progress_verdict == "advanced" and not harvest_validated:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "validate_advanced_with_unreachable_within_cycle",
                "`validate` cannot report advanced progress from repeating cycle-bound smoke evidence for a cycle-unreachable target.",
            )
        if basis_overclaim and validation_verdict in {"complete", "passed", "pass"} and not (explicit_descope or basis_compatible_inputs):
            add(
                findings,
                "block" if mode == "block" else "warn",
                "validate_basis_overclaim_complete",
                "`validate` cannot complete independently verified metric progress from basis_overclaim; downgrade to actual_basis_class or provide basis-compatible inputs.",
            )
        if basis_overclaim and progress_verdict == "advanced" and not basis_compatible_inputs:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "validate_advanced_from_basis_overclaim",
                "`validate` cannot report advanced progress from a metric whose claimed basis is not derivable from consumed inputs.",
            )
        if field_class_map_missing:
            add(
                findings,
                "warn",
                "field_class_map_missing",
                "`field_class_map_missing` is fail-quiet warning evidence; preserve existing review semantics and do not invent domain field classes.",
            )
        if surface_field_defects and validation_verdict in {"complete", "passed", "pass"} and not (explicit_descope or surface_field_repaired):
            add(
                findings,
                "block" if mode == "block" else "warn",
                "validate_surface_field_defects_complete",
                "`validate` cannot consume qualitative review as pass for affected producer-written field classes while surface_field_defect_matrix has nonzero defects.",
            )
        if surface_field_defects and progress_verdict == "advanced" and not surface_field_repaired:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "validate_advanced_with_surface_field_defects",
                "`validate` cannot report advanced qualitative-review progress while nonzero surface-field defects remain unresolved.",
            )
        if harvest_gate_unaudited:
            add(
                findings,
                "warn",
                "validate_harvest_gate_unaudited",
                "`harvest_gate_unaudited` is fail-quiet warning evidence; preserve it without inventing repository-specific harvest checks.",
            )
        if harvest_preflight_incompatible and validation_verdict in {"complete", "passed", "pass"} and not (explicit_descope or harvest_risk_accepted or harvest_gate_repaired):
            add(
                findings,
                "block" if mode == "block" else "warn",
                "validate_harvest_preflight_incompatible_complete",
                "`validate` cannot complete long-run launch or harvest consumption from non-degradable harvest-gate incompatibility without repair, mitigation, explicit risk acceptance, or residual descope.",
            )
        if harvest_preflight_incompatible and progress_verdict == "advanced" and not (harvest_risk_accepted or harvest_gate_repaired):
            add(
                findings,
                "block" if mode == "block" else "warn",
                "validate_advanced_with_harvest_preflight_incompatibility",
                "`validate` cannot report advanced progress while lane, scale, or predicate harvest incompatibility remains unresolved.",
            )
        if destructive_high_cost and validation_verdict in {"complete", "passed", "pass"} and not (explicit_descope or quarantine_preserved):
            add(
                findings,
                "block" if mode == "block" else "warn",
                "validate_destructive_high_cost_disposition_complete",
                "`validate` cannot complete high-cost non-safety terminal output handling when destructive disposition was requested or blocked without preserved quarantine evidence.",
            )
        if destructive_high_cost and progress_verdict == "advanced" and not quarantine_preserved:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "validate_advanced_from_destructive_high_cost_disposition",
                "`validate` cannot report advanced progress from destructive disposition of high-cost non-safety artifacts; preserve quarantine or descope the artifact.",
            )
        if rerun_before_reharvest and validation_verdict in {"complete", "passed", "pass"} and not (explicit_descope or reharvest_complete):
            add(
                findings,
                "block" if mode == "block" else "warn",
                "validate_rerun_before_reharvest_complete",
                "`validate` cannot complete a rerun path before available reharvest is attempted, terminal-blocked, or explicitly descoped.",
            )
        if rerun_before_reharvest and progress_verdict == "advanced" and not reharvest_complete:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "validate_advanced_from_rerun_before_reharvest",
                "`validate` cannot report advanced progress for a new full rerun while preserved high-cost artifacts still require reharvest first.",
            )
        if mutually_unsatisfiable_contract and validation_verdict in {"complete", "passed", "pass"} and not (explicit_descope or predicate_directive_reconciled):
            add(
                findings,
                "block" if mode == "block" else "warn",
                "validate_mutually_unsatisfiable_contract_complete",
                "`validate` cannot complete while validation predicates and producer directives remain mutually unsatisfiable; reconcile one side or preserve residual scope.",
            )
        if mutually_unsatisfiable_contract and progress_verdict == "advanced" and not predicate_directive_reconciled:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "validate_advanced_with_mutually_unsatisfiable_contract",
                "`validate` cannot report advanced progress while contradictory predicate/directive contracts coexist as consumable truth.",
            )
        if collection_closed_world_misuse and validation_verdict in {"complete", "passed", "pass"} and not (explicit_descope or full_collection_supplied):
            add(
                findings,
                "block" if mode == "block" else "warn",
                "validate_sample_as_universe_misuse_complete",
                "`validate` cannot complete closed-world collection evidence from truncated, partial, capped, or sampled collections without full collection supply or sample-only contract revision.",
            )
        if collection_closed_world_misuse and progress_verdict == "advanced" and not full_collection_supplied:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "validate_advanced_from_sample_as_universe_misuse",
                "`validate` cannot report advanced progress from absence checks over a truncated, partial, capped, or sampled collection.",
            )
        scenario_uncovered = boolish(
            first_present(
                result,
                [
                    "scenario_uncovered",
                    "acceptance_scenario_gate.scenario_uncovered",
                    "result.acceptance_scenario_gate.scenario_uncovered",
                    "anti_loop_progress_gate.scenario_uncovered",
                ],
            )
        )
        acceptance_inversion = boolish(
            first_present(
                result,
                [
                    "acceptance_inversion",
                    "acceptance_inversion_candidate",
                    "acceptance_scenario_gate.acceptance_inversion",
                    "result.acceptance_scenario_gate.acceptance_inversion",
                    "anti_loop_progress_gate.acceptance_inversion",
                ],
            )
        )
        producer_residual_blocker = boolish(
            first_present(
                result,
                [
                    "producer_residual_blocker",
                    "observed_producer_claim.residual_blocker",
                    "observed_producer_claim.remaining_blocker",
                    "acceptance_scenario_gate.producer_residual_blocker",
                    "result.acceptance_scenario_gate.producer_residual_blocker",
                ],
            )
        )
        command_provenance_missing = boolish(
            first_present(
                result,
                [
                    "command_provenance_missing",
                    "command_provenance_gate.command_provenance_missing",
                    "result.command_provenance_gate.command_provenance_missing",
                    "anti_loop_progress_gate.command_provenance_missing",
                ],
            )
        )
        command_provenance_required = boolish(
            first_present(
                result,
                [
                    "command_provenance_required",
                    "command_provenance_gate.required",
                    "baseline_claim",
                    "comparison_claim",
                    "ab_claim",
                    "reproduction_claim",
                    "result.command_provenance_gate.required",
                ],
            )
        )
        repeated_blocker_opacity = boolish(
            first_present(
                result,
                [
                    "repeated_blocker_opacity",
                    "blocker_opacity_repeated",
                    "blocker_actionability_gate.repeated_blocker_opacity",
                    "result.blocker_actionability_gate.repeated_blocker_opacity",
                    "anti_loop_progress_gate.repeated_blocker_opacity",
                ],
            )
        )
        blocker_claimed_resolved = boolish(
            first_present(
                result,
                [
                    "blocker_claimed_resolved",
                    "blocker_actionability_gate.blocker_claimed_resolved",
                    "blocker_actionability_gate.claimed_actionable",
                    "result.blocker_actionability_gate.blocker_claimed_resolved",
                ],
            )
        )
        predetermined_unreachable = boolish(
            first_present(
                result,
                [
                    "predetermined_unreachable",
                    "stochastic_feasibility_gate.predetermined_unreachable",
                    "result.stochastic_feasibility_gate.predetermined_unreachable",
                    "anti_loop_progress_gate.predetermined_unreachable",
                ],
            )
        )
        floor_edge_envelope = boolish(
            first_present(
                result,
                [
                    "floor_edge_envelope",
                    "stochastic_feasibility_gate.floor_edge_envelope",
                    "result.stochastic_feasibility_gate.floor_edge_envelope",
                    "anti_loop_progress_gate.floor_edge_envelope",
                ],
            )
        )
        instrumentation_first_fire = boolish(
            first_present(
                result,
                [
                    "instrumentation_first_fire",
                    "instrumentation_first_fire_gate.instrumentation_first_fire",
                    "result.instrumentation_first_fire_gate.instrumentation_first_fire",
                    "anti_loop_progress_gate.instrumentation_first_fire",
                ],
            )
        )
        first_fire_double_counted = boolish(
            first_present(
                result,
                [
                    "first_fire_double_counted",
                    "first_fire_double_count_blocked",
                    "instrumentation_first_fire_gate.first_fire_double_counted",
                    "result.instrumentation_first_fire_gate.first_fire_double_counted",
                ],
            )
        )
        first_fire_goal_progress = boolish(
            first_present(
                result,
                [
                    "first_fire_claimed_goal_progress",
                    "instrumentation_first_fire_gate.claimed_goal_progress",
                    "instrumentation_first_fire_gate.instrumentation_supply_consumed",
                    "result.instrumentation_first_fire_gate.claimed_goal_progress",
                ],
            )
        )
        if scenario_uncovered and validation_verdict in {"complete", "passed", "pass"}:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "validate_complete_with_scenario_uncovered",
                "`validate` cannot complete scenario-shaped acceptance without a premise-satisfying fixture or live run.",
            )
        if acceptance_inversion and validation_verdict in {"complete", "passed", "pass"}:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "validate_complete_with_acceptance_inversion",
                "`validate` cannot complete when premise-satisfying evidence asserts the opposite terminal state; keep the verdict partial and route code/contract repair.",
            )
        if producer_residual_blocker and validation_verdict in {"complete", "passed", "pass"} and not (scenario_uncovered or acceptance_inversion):
            add(
                findings,
                "block" if mode == "block" else "warn",
                "validate_complete_with_unresolved_producer_residual_blocker",
                "`validate` cannot ignore a producer-reported residual blocker that contradicts an acceptance scenario; preserve it as acceptance_inversion_candidate or resolve the scenario gate.",
            )
        if command_provenance_missing and command_provenance_required and validation_verdict in {"complete", "passed", "pass"}:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "validate_complete_with_missing_command_provenance",
                "`validate` cannot complete baseline, comparison, A/B, reproduction, or run-specific acceptance from a live run with missing full argv.",
            )
        if repeated_blocker_opacity and blocker_claimed_resolved and validation_verdict in {"complete", "passed", "pass"}:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "validate_complete_with_repeated_blocker_opacity",
                "`validate` cannot close a claimed actionable/resolved blocker when the same gate still returns only opaque reason codes.",
            )
        if (predetermined_unreachable or floor_edge_envelope) and validation_verdict in {"complete", "passed", "pass"} and not explicit_descope:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "validate_complete_with_stochastic_contract_infeasible",
                "`validate` cannot complete exact-match or floor-edge stochastic contracts until the contract is revised, descoped with residual scope, or escalated.",
            )
        if instrumentation_first_fire and (first_fire_double_counted or first_fire_goal_progress):
            add(
                findings,
                "block" if mode == "block" else "warn",
                "validate_first_fire_double_counted",
                "`validate` must count instrumentation_first_fire as one evidence credit only, not goal progress plus instrumentation-supply consumption.",
            )
        behavior_change_live_required = boolish(
            first_present(
                result,
                [
                    "behavior_change_live_required",
                    "live_behavior_evidence_required",
                    "execution_evidence_gate.behavior_change_live_required",
                    "result.execution_evidence_gate.behavior_change_live_required",
                ],
            )
        )
        behavior_change_live_present = boolish(
            first_present(
                result,
                [
                    "behavior_change_live_present",
                    "live_behavior_evidence_present",
                    "execution_evidence_gate.live_behavior_evidence_present",
                    "result.execution_evidence_gate.live_behavior_evidence_present",
                ],
            )
        )
        behavior_change_deferred = boolish(
            first_present(
                result,
                [
                    "behavior_change_live_deferred",
                    "execution_evidence_gate.live_behavior_evidence_deferred",
                    "result.execution_evidence_gate.live_behavior_evidence_deferred",
                ],
            )
        )
        if behavior_change_live_required and validation_verdict in {"complete", "passed", "pass"} and not behavior_change_live_present and not behavior_change_deferred:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "validate_behavior_change_live_evidence_missing",
                "`validate` cannot complete a runtime gate or judgment behavior-change fix without fresh live before/after evidence or an explicit defer rationale.",
            )
        refactor_effect_required = boolish(
            first_present(
                result,
                [
                    "refactor_effect_required",
                    "structure_metrics_gate.refactor_effect_required",
                    "result.structure_metrics_gate.refactor_effect_required",
                ],
            )
        )
        structure_high_water_moved = boolish(
            first_present(
                result,
                [
                    "structure_high_water_moved",
                    "structure_metrics_gate.structure_high_water_moved",
                    "structure_metrics_gate.target_structure_improved",
                    "result.structure_metrics_gate.structure_high_water_moved",
                ],
            )
        )
        if refactor_effect_required and validation_verdict in {"complete", "passed", "pass"} and not structure_high_water_moved:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "validate_refactor_without_structure_high_water",
                "`validate` cannot complete a behavior-preserving refactor from module creation and green tests alone; adapter-supplied structure high-water must move or the task remains partial.",
            )
        structure_key_scope = str(
            first_present(
                result,
                [
                    "structure_high_water_key_scope",
                    "structure_metrics_gate.structure_high_water_key_scope",
                    "result.structure_metrics_gate.structure_high_water_key_scope",
                ],
            )
            or ""
        ).lower()
        global_structure_moved = boolish(
            first_present(
                result,
                [
                    "global_structure_high_water_moved",
                    "structure_metrics_gate.global_structure_high_water_moved",
                    "result.structure_metrics_gate.global_structure_high_water_moved",
                ],
            )
        )
        if (
            refactor_effect_required
            and validation_verdict in {"complete", "passed", "pass"}
            and structure_key_scope == "global_invariant"
            and not global_structure_moved
        ):
            add(
                findings,
                "block" if mode == "block" else "warn",
                "validate_global_structure_invariant_not_moved",
                "`validate` cannot complete global structure work from selected-scope movement while adapter-owned global invariants are flat.",
            )
        convention_status = str(
            first_present(
                result,
                [
                    "convention_conformance_gate.status",
                    "convention_conformance.status",
                    "result.convention_conformance_gate.status",
                    "result.convention_conformance.status",
                ],
            )
            or ""
        ).lower()
        convention_violation = boolish(
            first_present(
                result,
                [
                    "convention_conformance_gate.contract_violation",
                    "convention_conformance.contract_violation",
                    "result.convention_conformance_gate.contract_violation",
                    "result.convention_conformance.contract_violation",
                ],
            )
        )
        if validation_verdict in {"complete", "passed", "pass"} and (
            convention_status in {"failed", "fail", "blocked", "block", "refactor_required"} or convention_violation
        ):
            add(
                findings,
                "block" if mode == "block" else "warn",
                "validate_complete_with_convention_violation",
                "`validate` cannot complete code changes with unresolved contract-backed convention violations; return partial or record explicit residual/descope handling.",
            )
        terminal_outcome_value = first_present(
            result,
            [
                "terminal_outcome_changed",
                "anti_loop_progress_gate.terminal_outcome_changed",
                "loopback_audit.terminal_outcome_changed",
                "output_delta.terminal_outcome_changed",
                "result.terminal_outcome_changed",
                "result.anti_loop_progress_gate.terminal_outcome_changed",
            ],
        )
        changed_vs_previous = first_present(
            result,
            [
                "changed_vs_previous",
                "output_delta.changed_vs_previous",
                "output_delta_gate.changed_vs_previous",
                "anti_loop_progress_gate.changed_vs_previous",
                "result.output_delta.changed_vs_previous",
                "result.anti_loop_progress_gate.changed_vs_previous",
            ],
        )
        semantic_progress = first_present(
            result,
            [
                "semantic_progress",
                "output_delta.semantic_progress",
                "output_delta_gate.semantic_progress",
                "anti_loop_progress_gate.semantic_progress",
                "result.output_delta.semantic_progress",
                "result.anti_loop_progress_gate.semantic_progress",
            ],
        )
        produced_domain_delta = first_present(
            result,
            [
                "produced_domain_delta",
                "output_delta.produced_domain_delta",
                "output_delta_gate.produced_domain_delta",
                "result.output_delta.produced_domain_delta",
            ],
        )
        observed_delta_class = str(
            first_present(
                result,
                [
                    "observed_delta_class",
                    "observed_output_class",
                    "output_delta.observed_delta_class",
                    "output_delta_gate.observed_output_class",
                    "anti_loop_progress_gate.observed_delta_class",
                    "result.anti_loop_progress_gate.observed_delta_class",
                ],
            )
            or ""
        ).lower()
        strict_observed_change = (
            boolish(terminal_outcome_value)
            if terminal_outcome_value is not None
            else (
                boolish(changed_vs_previous)
                and boolish(semantic_progress)
                and (
                    boolish(produced_domain_delta)
                    or observed_delta_class
                    in {"node_edge_delta", "semantic_delta", "changed_semantic_output", "primary_output_delta"}
                )
            )
        )
        metadata_only_value = first_present(
            result,
            [
                "metadata_only",
                "output_delta.metadata_only",
                "output_delta_gate.metadata_only",
                "anti_loop_progress_gate.metadata_only",
            ],
        )
        if progress_verdict == "advanced" and boolish(metadata_only_value):
            add(
                findings,
                "block" if mode == "block" else "warn",
                "validate_advanced_from_metadata_only_delta",
                "Metadata-only output cannot be advanced even when producer progress booleans claim semantic or domain movement.",
            )
        if progress_verdict == "advanced" and not strict_observed_change:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "validate_advanced_without_terminal_outcome_changed",
                "`validate` cannot report progress_verdict: advanced without terminal_outcome_changed=true or strict changed-and-semantic observed output delta.",
                {
                    "terminal_outcome_changed": terminal_outcome_value,
                    "changed_vs_previous": changed_vs_previous,
                    "semantic_progress": semantic_progress,
                    "produced_domain_delta": produced_domain_delta,
                    "observed_delta_class": observed_delta_class or None,
                },
            )
        if progress_verdict == "advanced":
            authoritative_progress_verdict = str(
                first_present(
                    result,
                    [
                        "authoritative_progress_verdict",
                        "validation.authoritative_progress_verdict",
                        "result.authoritative_progress_verdict",
                    ],
                )
                or ""
            ).strip().lower()
            loopback_authoritative = first_present(
                result,
                [
                    "authoritative_semantic_progress",
                    "anti_loop_progress_gate.authoritative_semantic_progress",
                    "loopback_audit.authoritative_semantic_progress",
                    "result.anti_loop_progress_gate.authoritative_semantic_progress",
                ],
            )
            hard_stop = boolish(
                first_present(
                    result,
                    [
                        "hard_stop_required",
                        "anti_loop_progress_gate.hard_stop_required",
                        "loopback_audit.hard_stop_required",
                    ],
                )
            )
            if authoritative_progress_verdict != "advanced":
                add(
                    findings,
                    "block" if mode == "block" else "warn",
                    "validate_advanced_without_authoritative_progress_verdict",
                    "Only completion validation may emit close-time advanced progress, and it must explicitly own `authoritative_progress_verdict: advanced`.",
                )
            if loopback_authoritative is not None and not boolish(loopback_authoritative):
                add(
                    findings,
                    "block" if mode == "block" else "warn",
                    "validate_progress_monotonicity_violation",
                    "Completion validation cannot upgrade loopback `authoritative_semantic_progress=false` to advanced.",
                )
            if hard_stop:
                add(
                    findings,
                    "block" if mode == "block" else "warn",
                    "validate_advanced_despite_hard_stop",
                    "Completion validation cannot report advanced while an authoritative hard stop remains active.",
                )

            required_artifact_class = str(first_present(result, ["required_artifact_class", "acceptance.required_artifact_class"]) or "").strip()
            observed_artifact_class = str(first_present(result, ["observed_artifact_class", "artifact_class", "target_metric_delta.artifact_class"]) or "").strip()
            if required_artifact_class and observed_artifact_class and required_artifact_class != observed_artifact_class:
                add(
                    findings,
                    "block" if mode == "block" else "warn",
                    "validate_required_artifact_class_mismatch",
                    "Observed artifact class does not satisfy the acceptance-required artifact class.",
                    {"required_artifact_class": required_artifact_class, "observed_artifact_class": observed_artifact_class},
                )

            required_status_paths = (
                "actual_body_truth_status",
                "report_convergence_status",
                "artifact_class_status",
                "freshness_status",
                "current_lane_status",
                "consumer_context_status",
                "verifier_completeness_status",
            )
            unevaluated_axes = [
                field
                for field in required_status_paths
                if str(first_present(result, [field, f"progress_integrity.{field}"]) or "").strip().lower()
                in {"not_evaluated", "missing", "unknown"}
            ]
            if unevaluated_axes:
                add(
                    findings,
                    "block" if mode == "block" else "warn",
                    "validate_advanced_with_required_integrity_not_evaluated",
                    "Advanced progress is invalid while a required integrity axis is not evaluated.",
                    {"axes": unevaluated_axes},
                )
