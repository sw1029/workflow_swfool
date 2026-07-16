from __future__ import annotations

from .shared import (
    ADOPTION_AXIS_TASK_KINDS,
    BLOCKER_CONTRACT_REPAIR_TASK_KINDS,
    COMMAND_PROVENANCE_TASK_KINDS,
    EXPECTATION_REBASELINE_TASK_KINDS,
    PARITY_AXIS_TASK_KINDS,
    SCENARIO_REPAIR_TASK_KINDS,
    SCENARIO_SUPPLY_TASK_KINDS,
    STOCHASTIC_CONTRACT_TASK_KINDS,
    add,
    boolish,
    first_present,
    non_empty,
)
from .state import DeriveFacts


def _check_routing_contracts_part_01(facts: DeriveFacts) -> None:
    result = facts.result
    scenario_uncovered = boolish(
        first_present(
            result,
            [
                "scenario_uncovered",
                "acceptance_scenario_gate.scenario_uncovered",
                "anti_loop_progress_gate.scenario_uncovered",
                "result.anti_loop_progress_gate.acceptance_scenario_gate.scenario_uncovered",
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
                "anti_loop_progress_gate.acceptance_inversion",
                "result.anti_loop_progress_gate.acceptance_scenario_gate.acceptance_inversion",
            ],
        )
    )
    command_provenance_missing = boolish(
        first_present(
            result,
            [
                "command_provenance_missing",
                "command_provenance_gate.command_provenance_missing",
                "anti_loop_progress_gate.command_provenance_missing",
                "result.anti_loop_progress_gate.command_provenance_gate.command_provenance_missing",
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
                "anti_loop_progress_gate.repeated_blocker_opacity",
                "result.anti_loop_progress_gate.blocker_actionability_gate.repeated_blocker_opacity",
            ],
        )
    )
    facts.acceptance_inversion = acceptance_inversion
    facts.command_provenance_missing = command_provenance_missing
    facts.repeated_blocker_opacity = repeated_blocker_opacity
    facts.scenario_uncovered = scenario_uncovered


def _check_routing_contracts_part_02(facts: DeriveFacts) -> None:
    acceptance_inversion = facts.acceptance_inversion
    command_provenance_missing = facts.command_provenance_missing
    findings = facts.findings
    mode = facts.mode
    result = facts.result
    scenario_uncovered = facts.scenario_uncovered
    selected_kind = facts.selected_kind
    terminal_selected = facts.terminal_selected
    authorization_contract_repair_candidate = boolish(
        first_present(
            result,
            [
                "authorization_contract_repair_candidate",
                "blocker_actionability_gate.authorization_contract_repair_candidate",
                "anti_loop_progress_gate.authorization_contract_repair_candidate",
                "result.anti_loop_progress_gate.blocker_actionability_gate.authorization_contract_repair_candidate",
            ],
        )
    )
    stochastic_contract_infeasible = boolish(
        first_present(
            result,
            [
                "predetermined_unreachable",
                "floor_edge_envelope",
                "stochastic_feasibility_gate.predetermined_unreachable",
                "stochastic_feasibility_gate.floor_edge_envelope",
                "anti_loop_progress_gate.predetermined_unreachable",
                "anti_loop_progress_gate.floor_edge_envelope",
                "result.anti_loop_progress_gate.stochastic_feasibility_gate.predetermined_unreachable",
                "result.anti_loop_progress_gate.stochastic_feasibility_gate.floor_edge_envelope",
            ],
        )
    )
    if scenario_uncovered and not terminal_selected and selected_kind not in SCENARIO_SUPPLY_TASK_KINDS:
        add(
            findings,
            "block" if mode == "block" else "warn",
            "derive_scenario_uncovered_unhandled",
            "`derive` must route scenario_uncovered to validation-set planning, fixture supply, live-run supply, terminal state, or user escalation.",
            {"selected_task_kind": selected_kind or None},
        )
    if acceptance_inversion and not terminal_selected and selected_kind not in SCENARIO_REPAIR_TASK_KINDS:
        add(
            findings,
            "block" if mode == "block" else "warn",
            "derive_acceptance_inversion_unhandled",
            "`derive` must route acceptance_inversion to code or acceptance/test contract repair, not another green-test confirmation task.",
            {"selected_task_kind": selected_kind or None},
        )
    if command_provenance_missing and not terminal_selected and selected_kind not in COMMAND_PROVENANCE_TASK_KINDS:
        add(
            findings,
            "block" if mode == "block" else "warn",
            "derive_command_provenance_missing_unhandled",
            "`derive` must repair or rerun missing command provenance before using that run for baseline, comparison, A/B, or reproduction evidence.",
            {"selected_task_kind": selected_kind or None},
        )
    facts.authorization_contract_repair_candidate = authorization_contract_repair_candidate
    facts.stochastic_contract_infeasible = stochastic_contract_infeasible


def _check_routing_contracts_part_03(facts: DeriveFacts) -> None:
    authorization_contract_repair_candidate = facts.authorization_contract_repair_candidate
    findings = facts.findings
    mode = facts.mode
    repeated_blocker_opacity = facts.repeated_blocker_opacity
    result = facts.result
    selected_kind = facts.selected_kind
    stochastic_contract_infeasible = facts.stochastic_contract_infeasible
    terminal_selected = facts.terminal_selected
    if (repeated_blocker_opacity or authorization_contract_repair_candidate) and not terminal_selected and selected_kind not in BLOCKER_CONTRACT_REPAIR_TASK_KINDS:
        add(
            findings,
            "block" if mode == "block" else "warn",
            "derive_repeated_blocker_opacity_unhandled",
            "`derive` must route repeated same-gate blocker_opacity or hidden multi-input authorization contracts to blocker/gate contract repair or terminal/user escalation.",
            {"selected_task_kind": selected_kind or None},
        )
    if stochastic_contract_infeasible and not terminal_selected and selected_kind not in STOCHASTIC_CONTRACT_TASK_KINDS:
        add(
            findings,
            "block" if mode == "block" else "warn",
            "derive_stochastic_contract_infeasible_unhandled",
            "`derive` must route predetermined_unreachable or floor_edge_envelope to contract revision, envelope expansion, residual descope, terminal state, or user escalation rather than retry.",
            {"selected_task_kind": selected_kind or None},
        )
    expectation_lineage_stale = boolish(
        first_present(
            result,
            [
                "expectation_lineage_stale",
                "expectation_lineage_gate.expectation_lineage_stale",
                "anti_loop_progress_gate.expectation_lineage_stale",
                "result.anti_loop_progress_gate.expectation_lineage_gate.expectation_lineage_stale",
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
                "result.anti_loop_progress_gate.expectation_lineage_gate.expectation_anchor_missing",
            ],
        )
    )
    parity_unverified = boolish(
        first_present(
            result,
            [
                "parity_unverified",
                "comparison_parity_gate.parity_unverified",
                "anti_loop_progress_gate.parity_unverified",
                "result.anti_loop_progress_gate.comparison_parity_gate.parity_unverified",
            ],
        )
    )
    facts.expectation_anchor_missing = expectation_anchor_missing
    facts.expectation_lineage_stale = expectation_lineage_stale
    facts.parity_unverified = parity_unverified


def _check_routing_contracts_part_04(facts: DeriveFacts) -> None:
    result = facts.result
    unknown_parity_axes = boolish(
        first_present(
            result,
            [
                "unknown_parity_axes",
                "comparison_parity_gate.unknown_parity_axes",
                "anti_loop_progress_gate.unknown_parity_axes",
                "result.anti_loop_progress_gate.comparison_parity_gate.unknown_parity_axes",
            ],
        )
    )
    majority_vote_adoption = boolish(
        first_present(
            result,
            [
                "majority_vote_adoption",
                "adoption_axis_gate.majority_vote_adoption",
                "anti_loop_progress_gate.majority_vote_adoption",
                "result.anti_loop_progress_gate.adoption_axis_gate.majority_vote_adoption",
            ],
        )
    )
    adoption_axis_classification = first_present(
        result,
        [
            "adoption_axis_classification",
            "adoption_axis_gate.adoption_axis_classification",
            "anti_loop_progress_gate.adoption_axis_classification",
            "result.anti_loop_progress_gate.adoption_axis_gate.adoption_axis_classification",
        ],
    )
    measured_but_disqualified = boolish(
        first_present(
            result,
            [
                "measured_but_disqualified",
                "adoption_axis_gate.measured_but_disqualified",
                "anti_loop_progress_gate.measured_but_disqualified",
                "result.anti_loop_progress_gate.adoption_axis_gate.measured_but_disqualified",
            ],
        )
    )
    failed_gating_axis = boolish(
        first_present(
            result,
            [
                "failed_gating_axis",
                "adoption_axis_gate.failed_gating_axis",
                "anti_loop_progress_gate.failed_gating_axis",
                "result.anti_loop_progress_gate.adoption_axis_gate.failed_gating_axis",
            ],
        )
    )
    facts.adoption_axis_classification = adoption_axis_classification
    facts.failed_gating_axis = failed_gating_axis
    facts.majority_vote_adoption = majority_vote_adoption
    facts.measured_but_disqualified = measured_but_disqualified
    facts.unknown_parity_axes = unknown_parity_axes


def _check_routing_contracts_part_05(facts: DeriveFacts) -> None:
    adoption_axis_classification = facts.adoption_axis_classification
    expectation_anchor_missing = facts.expectation_anchor_missing
    expectation_lineage_stale = facts.expectation_lineage_stale
    findings = facts.findings
    majority_vote_adoption = facts.majority_vote_adoption
    mode = facts.mode
    parity_unverified = facts.parity_unverified
    progress_kind = facts.progress_kind
    result = facts.result
    selected_kind = facts.selected_kind
    terminal_selected = facts.terminal_selected
    unknown_parity_axes = facts.unknown_parity_axes
    resolution_downgrade = boolish(
        first_present(
            result,
            [
                "resolution_downgrade",
                "resolution_downgrade_gate.resolution_downgrade",
                "anti_loop_progress_gate.resolution_downgrade",
                "result.anti_loop_progress_gate.resolution_downgrade_gate.resolution_downgrade",
            ],
        )
    )
    repeated_resolution_downgrade = boolish(
        first_present(
            result,
            [
                "repeated_resolution_downgrade",
                "resolution_downgrade_gate.repeated_resolution_downgrade",
                "anti_loop_progress_gate.repeated_resolution_downgrade",
                "result.anti_loop_progress_gate.resolution_downgrade_gate.repeated_resolution_downgrade",
            ],
        )
    )
    if expectation_lineage_stale and not terminal_selected and selected_kind not in EXPECTATION_REBASELINE_TASK_KINDS:
        add(
            findings,
            "block" if mode == "block" else "warn",
            "derive_expectation_lineage_stale_unhandled",
            "`derive` must route stale output-derived expectations to rebaseline, explicit residual descope, terminal state, or user escalation before dependent live execution.",
            {"selected_task_kind": selected_kind or None},
        )
    if expectation_anchor_missing and not expectation_lineage_stale and progress_kind == "goal_productive" and selected_kind not in EXPECTATION_REBASELINE_TASK_KINDS:
        add(
            findings,
            "warn",
            "derive_expectation_anchor_missing_unhandled",
            "`derive` selected goal_productive work with an output-derived expectation missing an anchor; ensure the task does not claim lineage-verified expectation evidence.",
            {"selected_task_kind": selected_kind or None},
        )
    if (parity_unverified or unknown_parity_axes) and not terminal_selected and selected_kind not in PARITY_AXIS_TASK_KINDS:
        add(
            findings,
            "block" if mode == "block" else "warn",
            "derive_parity_unverified_unhandled",
            "`derive` must route parity-unverified comparison/adoption to axis resolution, provisional comparison, residual descope, terminal state, or user escalation.",
            {"selected_task_kind": selected_kind or None},
        )
    if majority_vote_adoption and not non_empty(adoption_axis_classification) and not terminal_selected and selected_kind not in ADOPTION_AXIS_TASK_KINDS:
        add(
            findings,
            "block" if mode == "block" else "warn",
            "derive_majority_vote_adoption_unhandled",
            "`derive` must not finalize majority-vote adoption without gating/tradable axis classification.",
            {"selected_task_kind": selected_kind or None},
        )
    facts.repeated_resolution_downgrade = repeated_resolution_downgrade
    facts.resolution_downgrade = resolution_downgrade


def check_routing_contracts(facts: DeriveFacts) -> None:
    _check_routing_contracts_part_01(facts)
    _check_routing_contracts_part_02(facts)
    _check_routing_contracts_part_03(facts)
    _check_routing_contracts_part_04(facts)
    _check_routing_contracts_part_05(facts)

