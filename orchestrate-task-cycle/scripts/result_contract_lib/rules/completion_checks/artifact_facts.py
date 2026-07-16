from __future__ import annotations

from .shared import (
    boolish,
    first_present,
    json,
    list_values,
    non_empty,
)
from .state import CompletionFacts


def _check_artifact_facts_part_01(facts: CompletionFacts) -> None:
    parity_axis_status_value = facts.parity_axis_status_value
    result = facts.result
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
    facts.majority_vote_adoption = majority_vote_adoption
    facts.parity_unverified = parity_unverified
    facts.provisional_adoption = provisional_adoption
    facts.unknown_parity_axes = unknown_parity_axes


def _check_artifact_facts_part_02(facts: CompletionFacts) -> None:
    result = facts.result
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
    facts.adoption_axis_classification = adoption_axis_classification
    facts.failed_gating_axis = failed_gating_axis
    facts.measured_but_disqualified = measured_but_disqualified
    facts.observed_resolution = observed_resolution
    facts.required_resolution = required_resolution


def _check_artifact_facts_part_03(facts: CompletionFacts) -> None:
    observed_resolution = facts.observed_resolution
    required_resolution = facts.required_resolution
    result = facts.result
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
    facts.high_resolution_contract_required = high_resolution_contract_required
    facts.resolution_contract_revised = resolution_contract_revised
    facts.resolution_downgrade = resolution_downgrade
    facts.resolution_restored = resolution_restored


def _check_artifact_facts_part_04(facts: CompletionFacts) -> None:
    result = facts.result
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
    facts.current_lane_revalidated = current_lane_revalidated
    facts.decision_metadata_revision = decision_metadata_revision
    facts.lane_identity_missing = lane_identity_missing
    facts.pass_on_stale_lane = pass_on_stale_lane


def _check_artifact_facts_part_05(facts: CompletionFacts) -> None:
    result = facts.result
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
    facts.axis_starved_by_missing_producer = axis_starved_by_missing_producer
    facts.fresh_measurement_present = fresh_measurement_present
    facts.portfolio_quota_exceeded = portfolio_quota_exceeded
    facts.producer_supply_complete = producer_supply_complete


def _check_artifact_facts_part_06(facts: CompletionFacts) -> None:
    result = facts.result
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
    facts.harvest_validated = harvest_validated
    facts.portfolio_quota_mode = portfolio_quota_mode
    facts.portfolio_quota_restrictive = portfolio_quota_restrictive
    facts.unreachable_within_cycle = unreachable_within_cycle


def check_artifact_facts(facts: CompletionFacts) -> None:
    _check_artifact_facts_part_01(facts)
    _check_artifact_facts_part_02(facts)
    _check_artifact_facts_part_03(facts)
    _check_artifact_facts_part_04(facts)
    _check_artifact_facts_part_05(facts)
    _check_artifact_facts_part_06(facts)

