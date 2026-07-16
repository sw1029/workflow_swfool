from __future__ import annotations

from .shared import (
    add,
    non_empty,
)
from .state import CompletionFacts

from .evaluate_outcomes import (
    _check_evaluate_part_05,
    _check_evaluate_part_06,
    _check_evaluate_part_07,
    _check_evaluate_part_08,
)


def _check_evaluate_part_01(facts: CompletionFacts) -> None:
    acceptance_diluted = facts.acceptance_diluted
    explicit_descope = facts.explicit_descope
    findings = facts.findings
    generation_dependent_count_key = facts.generation_dependent_count_key
    generation_key_novelty_claim = facts.generation_key_novelty_claim
    lane_identity_missing = facts.lane_identity_missing
    measurable_target_required = facts.measurable_target_required
    mode = facts.mode
    non_coupled_revalidated = facts.non_coupled_revalidated
    pass_with_coupled_verifier = facts.pass_with_coupled_verifier
    pass_with_unobserved_axes = facts.pass_with_unobserved_axes
    progress_verdict = facts.progress_verdict
    required_verifier_not_evaluated = facts.required_verifier_not_evaluated
    target_met = facts.target_met
    unobserved_goal_axes = facts.unobserved_goal_axes
    unverifiable_acceptance = facts.unverifiable_acceptance
    validation_verdict = facts.validation_verdict
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


def _check_evaluate_part_02(facts: CompletionFacts) -> None:
    attested_only_movement = facts.attested_only_movement
    envelope_thaw_item = facts.envelope_thaw_item
    envelope_thaw_item_required = facts.envelope_thaw_item_required
    explicit_descope = facts.explicit_descope
    findings = facts.findings
    independent_source_status = facts.independent_source_status
    independently_verified_downgraded_fields = facts.independently_verified_downgraded_fields
    independently_verified_fields = facts.independently_verified_fields
    marginal_repair_override = facts.marginal_repair_override
    mode = facts.mode
    producer_attested_fields = facts.producer_attested_fields
    progress_verdict = facts.progress_verdict
    residual_cost_below_policy = facts.residual_cost_below_policy
    self_grounded_mislabeled_independent = facts.self_grounded_mislabeled_independent
    validation_verdict = facts.validation_verdict
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
            "`validate` cannot complete from independently_verified evidence unless verification inputs are disjoint from verified artifacts; self-grounded axes remain a separate structural provenance class.",
            {"independent_source_separation_status": independent_source_status},
        )
    if self_grounded_mislabeled_independent and (
        validation_verdict in {"complete", "passed", "pass"} or progress_verdict == "advanced"
    ) and not explicit_descope:
        add(
            findings,
            "block" if mode == "block" else "warn",
            "validate_self_grounded_counted_as_independent",
            "Self-grounded structural axes cannot satisfy source-independent semantic completion or advanced progress.",
            {"axis_ids": self_grounded_mislabeled_independent},
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


def _check_evaluate_part_03(facts: CompletionFacts) -> None:
    comparison_contract = facts.comparison_contract
    expectation_anchor_missing = facts.expectation_anchor_missing
    expectation_lineage_stale = facts.expectation_lineage_stale
    expectation_rebaselined = facts.expectation_rebaselined
    explicit_descope = facts.explicit_descope
    findings = facts.findings
    instrumentation_supply_required = facts.instrumentation_supply_required
    lineage_verified_expectation_claim = facts.lineage_verified_expectation_claim
    mode = facts.mode
    parity_unverified = facts.parity_unverified
    progress_verdict = facts.progress_verdict
    provisional_adoption = facts.provisional_adoption
    same_input_contract_violation = facts.same_input_contract_violation
    terminal_stage_contradiction = facts.terminal_stage_contradiction
    unknown_parity_axes = facts.unknown_parity_axes
    validation_verdict = facts.validation_verdict
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


def _check_evaluate_part_04(facts: CompletionFacts) -> None:
    adoption_axis_classification = facts.adoption_axis_classification
    current_lane_revalidated = facts.current_lane_revalidated
    decision_metadata_revision = facts.decision_metadata_revision
    explicit_descope = facts.explicit_descope
    failed_gating_axis = facts.failed_gating_axis
    findings = facts.findings
    fresh_measurement_present = facts.fresh_measurement_present
    high_resolution_contract_required = facts.high_resolution_contract_required
    majority_vote_adoption = facts.majority_vote_adoption
    measured_but_disqualified = facts.measured_but_disqualified
    mode = facts.mode
    observed_resolution = facts.observed_resolution
    pass_on_stale_lane = facts.pass_on_stale_lane
    progress_verdict = facts.progress_verdict
    provisional_adoption = facts.provisional_adoption
    required_resolution = facts.required_resolution
    resolution_contract_revised = facts.resolution_contract_revised
    resolution_downgrade = facts.resolution_downgrade
    resolution_restored = facts.resolution_restored
    validation_verdict = facts.validation_verdict
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


def check_evaluate(facts: CompletionFacts) -> None:
    _check_evaluate_part_01(facts)
    _check_evaluate_part_02(facts)
    _check_evaluate_part_03(facts)
    _check_evaluate_part_04(facts)
    _check_evaluate_part_05(facts)
    _check_evaluate_part_06(facts)
    _check_evaluate_part_07(facts)
    _check_evaluate_part_08(facts)

