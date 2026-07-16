from __future__ import annotations

from .shared import (
    add,
    boolish,
    first_present,
)
from .state import CompletionFacts


def _check_change_evidence_part_01(facts: CompletionFacts) -> None:
    findings = facts.findings
    mode = facts.mode
    result = facts.result
    validation_verdict = facts.validation_verdict
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
    facts.refactor_effect_required = refactor_effect_required


def _check_change_evidence_part_02(facts: CompletionFacts) -> None:
    findings = facts.findings
    mode = facts.mode
    refactor_effect_required = facts.refactor_effect_required
    result = facts.result
    validation_verdict = facts.validation_verdict
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


def _check_change_evidence_part_03(facts: CompletionFacts) -> None:
    findings = facts.findings
    mode = facts.mode
    result = facts.result
    validation_verdict = facts.validation_verdict
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
    facts.changed_vs_previous = changed_vs_previous
    facts.terminal_outcome_value = terminal_outcome_value


def _check_change_evidence_part_04(facts: CompletionFacts) -> None:
    changed_vs_previous = facts.changed_vs_previous
    result = facts.result
    terminal_outcome_value = facts.terminal_outcome_value
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
                in {"material_delta", "semantic_delta", "changed_semantic_output", "primary_output_delta"}
            )
        )
    )
    facts.observed_delta_class = observed_delta_class
    facts.produced_domain_delta = produced_domain_delta
    facts.semantic_progress = semantic_progress
    facts.strict_observed_change = strict_observed_change


def _check_change_evidence_part_05(facts: CompletionFacts) -> None:
    changed_vs_previous = facts.changed_vs_previous
    findings = facts.findings
    mode = facts.mode
    observed_delta_class = facts.observed_delta_class
    produced_domain_delta = facts.produced_domain_delta
    progress_verdict = facts.progress_verdict
    result = facts.result
    semantic_progress = facts.semantic_progress
    strict_observed_change = facts.strict_observed_change
    terminal_outcome_value = facts.terminal_outcome_value
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


def check_change_evidence(facts: CompletionFacts) -> None:
    _check_change_evidence_part_01(facts)
    _check_change_evidence_part_02(facts)
    _check_change_evidence_part_03(facts)
    _check_change_evidence_part_04(facts)
    _check_change_evidence_part_05(facts)

