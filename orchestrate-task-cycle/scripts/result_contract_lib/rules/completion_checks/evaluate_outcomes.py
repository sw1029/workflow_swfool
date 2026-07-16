from __future__ import annotations

from .shared import (
    add,
)
from .state import CompletionFacts

def _check_evaluate_part_05(facts: CompletionFacts) -> None:
    axis_starved_by_missing_producer = facts.axis_starved_by_missing_producer
    decision_metadata_revision = facts.decision_metadata_revision
    explicit_descope = facts.explicit_descope
    findings = facts.findings
    fresh_measurement_present = facts.fresh_measurement_present
    harvest_validated = facts.harvest_validated
    mode = facts.mode
    portfolio_quota_exceeded = facts.portfolio_quota_exceeded
    portfolio_quota_mode = facts.portfolio_quota_mode
    portfolio_quota_restrictive = facts.portfolio_quota_restrictive
    producer_supply_complete = facts.producer_supply_complete
    progress_verdict = facts.progress_verdict
    unreachable_within_cycle = facts.unreachable_within_cycle
    validation_verdict = facts.validation_verdict
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


def _check_evaluate_part_06(facts: CompletionFacts) -> None:
    basis_compatible_inputs = facts.basis_compatible_inputs
    basis_overclaim = facts.basis_overclaim
    explicit_descope = facts.explicit_descope
    field_class_map_missing = facts.field_class_map_missing
    findings = facts.findings
    harvest_gate_repaired = facts.harvest_gate_repaired
    harvest_gate_unaudited = facts.harvest_gate_unaudited
    harvest_preflight_incompatible = facts.harvest_preflight_incompatible
    harvest_risk_accepted = facts.harvest_risk_accepted
    mode = facts.mode
    progress_verdict = facts.progress_verdict
    surface_field_defects = facts.surface_field_defects
    surface_field_repaired = facts.surface_field_repaired
    validation_verdict = facts.validation_verdict
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


def _check_evaluate_part_07(facts: CompletionFacts) -> None:
    destructive_high_cost = facts.destructive_high_cost
    explicit_descope = facts.explicit_descope
    findings = facts.findings
    harvest_gate_repaired = facts.harvest_gate_repaired
    harvest_preflight_incompatible = facts.harvest_preflight_incompatible
    harvest_risk_accepted = facts.harvest_risk_accepted
    mode = facts.mode
    mutually_unsatisfiable_contract = facts.mutually_unsatisfiable_contract
    predicate_directive_reconciled = facts.predicate_directive_reconciled
    progress_verdict = facts.progress_verdict
    quarantine_preserved = facts.quarantine_preserved
    reharvest_complete = facts.reharvest_complete
    rerun_before_reharvest = facts.rerun_before_reharvest
    validation_verdict = facts.validation_verdict
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


def _check_evaluate_part_08(facts: CompletionFacts) -> None:
    collection_closed_world_misuse = facts.collection_closed_world_misuse
    explicit_descope = facts.explicit_descope
    findings = facts.findings
    full_collection_supplied = facts.full_collection_supplied
    mode = facts.mode
    progress_verdict = facts.progress_verdict
    validation_verdict = facts.validation_verdict
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


