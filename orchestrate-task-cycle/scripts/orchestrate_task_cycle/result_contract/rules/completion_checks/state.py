from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ...base import RuleContext


@dataclass
class CompletionFacts:
    """Facts gathered before ordered completion verdict checks."""

    context: RuleContext
    validation_verdict: str = ""
    progress_verdict: str = ""
    acceptance_diluted: Any = None
    attested_only_movement: Any = None
    comparison_contract: Any = None
    envelope_thaw_item: Any = None
    envelope_thaw_item_required: Any = None
    expectation_anchor_missing: Any = None
    expectation_lineage_stale: Any = None
    expectation_rebaselined: Any = None
    explicit_descope: Any = None
    generation_dependent_count_key: Any = None
    generation_key_novelty_claim: Any = None
    independent_source_status: Any = None
    independently_verified_downgraded_fields: Any = None
    independently_verified_fields: Any = None
    instrumentation_supply_required: Any = None
    lineage_verified_expectation_claim: Any = None
    marginal_repair_override: Any = None
    measurable_target_required: Any = None
    non_coupled_revalidated: Any = None
    parity_axis_status_value: Any = None
    pass_with_coupled_verifier: Any = None
    pass_with_unobserved_axes: Any = None
    producer_attested_fields: Any = None
    required_verifier_not_evaluated: Any = None
    residual_cost_below_policy: Any = None
    same_input_contract_violation: Any = None
    self_grounded_mislabeled_independent: Any = None
    target_met: Any = None
    terminal_stage_contradiction: Any = None
    unobserved_goal_axes: Any = None
    unverifiable_acceptance: Any = None
    adoption_axis_classification: Any = None
    axis_starved_by_missing_producer: Any = None
    current_lane_revalidated: Any = None
    decision_metadata_revision: Any = None
    failed_gating_axis: Any = None
    fresh_measurement_present: Any = None
    harvest_validated: Any = None
    high_resolution_contract_required: Any = None
    lane_identity_missing: Any = None
    majority_vote_adoption: Any = None
    measured_but_disqualified: Any = None
    observed_resolution: Any = None
    parity_unverified: Any = None
    pass_on_stale_lane: Any = None
    portfolio_quota_exceeded: Any = None
    portfolio_quota_mode: Any = None
    portfolio_quota_restrictive: Any = None
    producer_supply_complete: Any = None
    provisional_adoption: Any = None
    required_resolution: Any = None
    resolution_contract_revised: Any = None
    resolution_downgrade: Any = None
    resolution_restored: Any = None
    unknown_parity_axes: Any = None
    unreachable_within_cycle: Any = None
    basis_compatible_inputs: Any = None
    basis_overclaim: Any = None
    collection_closed_world_misuse: Any = None
    destructive_high_cost: Any = None
    field_class_map_missing: Any = None
    full_collection_supplied: Any = None
    harvest_gate_repaired: Any = None
    harvest_gate_unaudited: Any = None
    harvest_preflight_incompatible: Any = None
    harvest_risk_accepted: Any = None
    mutually_unsatisfiable_contract: Any = None
    predicate_directive_reconciled: Any = None
    quarantine_preserved: Any = None
    reharvest_complete: Any = None
    rerun_before_reharvest: Any = None
    surface_field_defects: Any = None
    surface_field_repaired: Any = None

    acceptance_inversion: Any = None
    blocker_claimed_resolved: Any = None
    changed_vs_previous: Any = None
    closed_world_consumption: Any = None
    collection_truncated: Any = None
    command_provenance_missing: Any = None
    command_provenance_required: Any = None
    first_fire_double_counted: Any = None
    first_fire_goal_progress: Any = None
    floor_edge_envelope: Any = None
    instrumentation_first_fire: Any = None
    observed_delta_class: Any = None
    predetermined_unreachable: Any = None
    produced_domain_delta: Any = None
    producer_residual_blocker: Any = None
    refactor_effect_required: Any = None
    repeated_blocker_opacity: Any = None
    sample_as_universe_misuse: Any = None
    scenario_uncovered: Any = None
    semantic_progress: Any = None
    strict_observed_change: Any = None
    terminal_outcome_value: Any = None

    @property
    def result(self) -> dict[str, Any]:
        return self.context.result

    @property
    def mode(self) -> str:
        return self.context.mode

    @property
    def findings(self) -> list[dict[str, Any]]:
        return self.context.findings
