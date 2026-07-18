from __future__ import annotations

from typing import Any

from ...scenario_receipts import ScenarioReceiptAssessment, assess_scenario_receipts
from .shared import (
    add,
    boolish,
    first_present,
)
from .state import CompletionFacts


def _declared_bool(result: dict[str, Any], paths: list[str]) -> tuple[bool, bool]:
    value = first_present(result, paths)
    return value is not None, boolish(value)


def _record_receipt_findings(
    facts: CompletionFacts,
    assessment: ScenarioReceiptAssessment,
) -> None:
    positive_close = facts.validation_verdict in {"complete", "passed", "pass", "success"}
    severity = "block" if positive_close and facts.mode == "block" else "warn"
    for issue in assessment.contract_issues:
        add(
            facts.findings,
            severity,
            "validate_scenario_contract_malformed",
            "Scenario-shaped acceptance must retain an opaque scenario ID, premise predicate, and expected terminal state.",
            issue.evidence(),
        )
    for issue in assessment.receipt_issues:
        add(
            facts.findings,
            severity,
            "validate_scenario_receipt_malformed",
            "Scenario coverage requires a structured actual-invocation receipt; a caller coverage boolean is not sufficient.",
            issue.evidence(),
        )
    if assessment.uncovered_scenario_ids:
        add(
            facts.findings,
            severity,
            "validate_scenario_receipt_uncovered",
            "At least one declared acceptance scenario has no valid premise-satisfying invocation with the expected terminal state.",
            {"scenario_ids": list(assessment.uncovered_scenario_ids)},
        )


def _check_scenarios_part_01(facts: CompletionFacts) -> None:
    result = facts.result
    uncovered_paths = [
        "scenario_uncovered",
        "acceptance_scenario_gate.scenario_uncovered",
        "result.acceptance_scenario_gate.scenario_uncovered",
        "anti_loop_progress_gate.scenario_uncovered",
    ]
    inversion_paths = [
        "acceptance_inversion",
        "acceptance_inversion_candidate",
        "acceptance_scenario_gate.acceptance_inversion",
        "result.acceptance_scenario_gate.acceptance_inversion",
        "anti_loop_progress_gate.acceptance_inversion",
    ]
    uncovered_declared, claimed_uncovered = _declared_bool(result, uncovered_paths)
    inversion_declared, claimed_inversion = _declared_bool(result, inversion_paths)
    receipt_assessment = assess_scenario_receipts(result)
    if receipt_assessment.applicable:
        _record_receipt_findings(facts, receipt_assessment)
        recomputed_uncovered = bool(
            receipt_assessment.uncovered_scenario_ids
            or receipt_assessment.contract_issues
        )
        recomputed_inversion = bool(receipt_assessment.inversion_scenario_ids)
        mismatch_fields: list[str] = []
        if uncovered_declared and claimed_uncovered != recomputed_uncovered:
            mismatch_fields.append("scenario_uncovered")
        if inversion_declared and claimed_inversion != recomputed_inversion:
            mismatch_fields.append("acceptance_inversion")
        if mismatch_fields:
            positive_close = facts.validation_verdict in {
                "complete",
                "passed",
                "pass",
                "success",
            }
            add(
                facts.findings,
                "block" if positive_close and facts.mode == "block" else "warn",
                "validate_scenario_coverage_claim_mismatch",
                "Caller scenario booleans conflict with the recomputed structured premise receipts.",
                {"mismatched_fields": mismatch_fields},
            )
        scenario_uncovered = recomputed_uncovered or claimed_uncovered
        acceptance_inversion = recomputed_inversion or claimed_inversion
    else:
        scenario_uncovered = claimed_uncovered
        acceptance_inversion = claimed_inversion
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
    facts.acceptance_inversion = acceptance_inversion
    facts.command_provenance_missing = command_provenance_missing
    facts.producer_residual_blocker = producer_residual_blocker
    facts.scenario_uncovered = scenario_uncovered


def _check_scenarios_part_02(facts: CompletionFacts) -> None:
    result = facts.result
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
    facts.blocker_claimed_resolved = blocker_claimed_resolved
    facts.command_provenance_required = command_provenance_required
    facts.predetermined_unreachable = predetermined_unreachable
    facts.repeated_blocker_opacity = repeated_blocker_opacity


def _check_scenarios_part_03(facts: CompletionFacts) -> None:
    findings = facts.findings
    mode = facts.mode
    result = facts.result
    scenario_uncovered = facts.scenario_uncovered
    validation_verdict = facts.validation_verdict
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
    facts.first_fire_double_counted = first_fire_double_counted
    facts.first_fire_goal_progress = first_fire_goal_progress
    facts.floor_edge_envelope = floor_edge_envelope
    facts.instrumentation_first_fire = instrumentation_first_fire


def _check_scenarios_part_04(facts: CompletionFacts) -> None:
    acceptance_inversion = facts.acceptance_inversion
    blocker_claimed_resolved = facts.blocker_claimed_resolved
    command_provenance_missing = facts.command_provenance_missing
    command_provenance_required = facts.command_provenance_required
    explicit_descope = facts.explicit_descope
    findings = facts.findings
    first_fire_double_counted = facts.first_fire_double_counted
    first_fire_goal_progress = facts.first_fire_goal_progress
    floor_edge_envelope = facts.floor_edge_envelope
    instrumentation_first_fire = facts.instrumentation_first_fire
    mode = facts.mode
    predetermined_unreachable = facts.predetermined_unreachable
    producer_residual_blocker = facts.producer_residual_blocker
    repeated_blocker_opacity = facts.repeated_blocker_opacity
    scenario_uncovered = facts.scenario_uncovered
    validation_verdict = facts.validation_verdict
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


def check_scenarios(facts: CompletionFacts) -> None:
    _check_scenarios_part_01(facts)
    _check_scenarios_part_02(facts)
    _check_scenarios_part_03(facts)
    _check_scenarios_part_04(facts)
