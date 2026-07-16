from __future__ import annotations

from .shared import (
    boolish,
    first_present,
    non_empty,
    nonzero_scalar,
)
from .state import CompletionFacts


def _check_operation_facts_part_01(facts: CompletionFacts) -> None:
    result = facts.result
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
    facts.basis_compatible_inputs = basis_compatible_inputs
    facts.basis_overclaim = basis_overclaim
    facts.field_class_map_missing = field_class_map_missing
    facts.surface_field_defects = surface_field_defects
    facts.surface_field_repaired = surface_field_repaired


def _check_operation_facts_part_02(facts: CompletionFacts) -> None:
    result = facts.result
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
    facts.harvest_gate_repaired = harvest_gate_repaired
    facts.harvest_gate_unaudited = harvest_gate_unaudited
    facts.harvest_preflight_incompatible = harvest_preflight_incompatible
    facts.harvest_risk_accepted = harvest_risk_accepted


def _check_operation_facts_part_03(facts: CompletionFacts) -> None:
    result = facts.result
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
    facts.destructive_high_cost = destructive_high_cost


def _check_operation_facts_part_04(facts: CompletionFacts) -> None:
    result = facts.result
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
    facts.mutually_unsatisfiable_contract = mutually_unsatisfiable_contract
    facts.quarantine_preserved = quarantine_preserved
    facts.reharvest_complete = reharvest_complete
    facts.rerun_before_reharvest = rerun_before_reharvest


def _check_operation_facts_part_05(facts: CompletionFacts) -> None:
    result = facts.result
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
    facts.closed_world_consumption = closed_world_consumption
    facts.collection_truncated = collection_truncated
    facts.predicate_directive_reconciled = predicate_directive_reconciled
    facts.sample_as_universe_misuse = sample_as_universe_misuse


def _check_operation_facts_part_06(facts: CompletionFacts) -> None:
    closed_world_consumption = facts.closed_world_consumption
    collection_truncated = facts.collection_truncated
    result = facts.result
    sample_as_universe_misuse = facts.sample_as_universe_misuse
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
    facts.collection_closed_world_misuse = collection_closed_world_misuse
    facts.full_collection_supplied = full_collection_supplied


def check_operation_facts(facts: CompletionFacts) -> None:
    _check_operation_facts_part_01(facts)
    _check_operation_facts_part_02(facts)
    _check_operation_facts_part_03(facts)
    _check_operation_facts_part_04(facts)
    _check_operation_facts_part_05(facts)
    _check_operation_facts_part_06(facts)

