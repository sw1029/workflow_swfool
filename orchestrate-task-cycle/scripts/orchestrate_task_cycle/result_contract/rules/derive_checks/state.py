from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ...base import RuleContext


@dataclass
class DeriveFacts:
    """Cross-stage facts for the ordered derive contract checks."""

    context: RuleContext
    explicit_report_key_divergence: bool = False
    auto_report_key_divergences: list[Any] = field(default_factory=list)
    allowed_task_kinds: Any = None
    progress_kind: str = ""
    selected_kind: str = ""
    selected_source: str = ""
    terminal_selected: bool = False
    failed_gating_axis: Any = None
    measured_but_disqualified: bool = False
    repeated_resolution_downgrade: bool = False
    resolution_downgrade: bool = False
    harvest_gate_unaudited: bool = False
    harvest_preflight_required: bool = False
    forced_kind: str = ""
    allowed_force_impl_class: bool = False
    changed_vs_previous: bool = False
    force_implementation_cycle: bool = False
    produced_domain_delta: bool = False
    semantic_progress: bool = False
    alternative_in_gt_allowed: bool = False
    alternative_in_gt_allowed_value: Any = None
    authorized_alternative_exists: bool = False
    authorized_alternative_path: Any = None
    cycles_since_goal_productive: Any = None
    goal_distance_required: bool = False
    goal_threshold: Any = None
    gt_allowed_alternative_attempted: bool = False
    has_supplied_input_delta: bool = False
    loop_detector_status: str = ""
    new_input_kinds: Any = None
    provider_mitigation_required: bool = False
    provider_reattempt_disposition: Any = None
    provider_reattempt_required: bool = False
    provider_terminal_seal_allowed: bool = False
    seal_requested: bool = False
    sealed_match: bool = False
    strict_positive_output_delta: bool = False
    terminal_or_seal: bool = False

    acceptance_inversion: Any = None
    adoption_axis_classification: Any = None
    advice_metrics_stale: Any = None
    attested_only_movement: Any = None
    authorization_contract_repair_candidate: Any = None
    axis_starved_by_missing_producer: Any = None
    basis_overclaim: Any = None
    blocker_mutation_kind: Any = None
    c4_user_escalation: Any = None
    command_budget_constrains_current: Any = None
    command_budget_required: Any = None
    command_provenance_missing: Any = None
    command_surface_class: Any = None
    consolidation_registered: Any = None
    coupled_verifier: Any = None
    cycle_fixed_cost_present: Any = None
    decision_metadata_revision: Any = None
    decision_lineage_declared: Any = None
    decision_lineage_status: Any = None
    descope_with_residual: Any = None
    destructive_disposition_blocked: Any = None
    destructive_disposition_requested: Any = None
    diagnostics_observable_without_new_instrumentation: Any = None
    diagnostics_unavailable_streak: Any = None
    effective_count_key: Any = None
    effective_progress_kind: Any = None
    envelope_thaw_item: Any = None
    envelope_thaw_item_required: Any = None
    expectation_anchor_missing: Any = None
    expectation_lineage_stale: Any = None
    forward_mutation_progress: Any = None
    forward_mutation_vacuous: Any = None
    generation_dependent_count_key: Any = None
    generation_key_novelty_claim: Any = None
    goal_axis_failed: Any = None
    gt_allowed_evidence_paths: Any = None
    high_cost_artifact: Any = None
    independent_source_status: Any = None
    independent_invariant_status: Any = None
    independently_verified_downgraded_fields: Any = None
    instrumentation_supply_required: Any = None
    majority_vote_adoption: Any = None
    marginal_repair: Any = None
    marginal_repair_override: Any = None
    marginal_value_per_cycle_cost: Any = None
    measurement_progress: Any = None
    measurement_progress_allowed: Any = None
    measurement_streak: Any = None
    measurement_streak_cap: Any = None
    metadata_only: Any = None
    next_capability_rung: Any = None
    output_delta_applies: Any = None
    output_delta_status: Any = None
    parity_unverified: Any = None
    pass_on_stale_lane: Any = None
    pass_with_unobserved_axes: Any = None
    portfolio_quota_exceeded: Any = None
    portfolio_quota_mode: Any = None
    portfolio_quota_restrictive: Any = None
    primary_metric_stalled: Any = None
    repeated_blocker_opacity: Any = None
    residual_cost_below_policy: Any = None
    safety_violation: Any = None
    same_input_contract_violation: Any = None
    scenario_uncovered: Any = None
    stochastic_contract_infeasible: Any = None
    substance_delta_pass: Any = None
    surface_field_defects: Any = None
    terminal_classification_invalid_for_counting: Any = None
    terminal_outcome_changed: Any = None
    terminal_stage_contradiction: Any = None
    unknown_parity_axes: Any = None
    unobserved_goal_axes: Any = None
    unreachable_within_cycle: Any = None
    vacuous_corrective_noop: Any = None

    @property
    def result(self) -> dict[str, Any]:
        return self.context.result

    @property
    def mode(self) -> str:
        return self.context.mode

    @property
    def findings(self) -> list[dict[str, Any]]:
        return self.context.findings

    @property
    def require_context_field(self) -> Any:
        return self.context.require_context_field
