from __future__ import annotations

from ..runtime_dependencies import (
    bool_value,
)

from ..evaluation_frame import _EvaluationFrame


def _evaluate_decision_disposition(frame: _EvaluationFrame) -> None:
    (
        adapter_gate, adapter_load_gate, c4_user_escalation_backstop_required, chain_gate,
        diagnostics_gate, disposition, failure_surface_gate, forced_retarget_gate, gate_inputs,
        hard_stop,
        input_contract_gate, metric_validity_gate, primary_metric_gate, reachability_gate,
    ) = frame.require(
        'adapter_gate', 'adapter_load_gate', 'c4_user_escalation_backstop_required',
        'chain_gate', 'diagnostics_gate', 'disposition', 'failure_surface_gate',
        'forced_retarget_gate', 'gate_inputs', 'hard_stop', 'input_contract_gate',
        'metric_validity_gate',
        'primary_metric_gate', 'reachability_gate',
    )
    if (
        bool_value(chain_gate.get("cumulative_goal_distance_stalled"))
        and not bool_value(adapter_gate.get("adapter_mandate_required"))
        and not bool_value(adapter_load_gate.get("adapter_wiring_defect"))
    ):
        hard_stop = True
        disposition = "goal_productive" if bool_value(forced_retarget_gate.get("constrains_disposition")) else "terminal_blocked"
        gate_inputs.append({"name": "cumulative_goal_distance_gate", **chain_gate})
    if bool_value(reachability_gate.get("acceptance_unreachable_under_frozen_config")):
        hard_stop = True
        if not bool_value(adapter_gate.get("adapter_mandate_required")) and not bool_value(
            chain_gate.get("cumulative_goal_distance_stalled")
        ):
            disposition = "relaxation_or_escalation_required"
    if bool_value(reachability_gate.get("unverifiable_acceptance_contract")):
        hard_stop = True
        if disposition in {
            "open",
            "prefer_provider_or_semantic",
            "measurement_progress_goal_productive_candidate",
            "artifact_gate_not_evaluated",
        }:
            disposition = "verifier_contract_required"
    if bool_value(metric_validity_gate.get("metric_goal_productive_excluded")):
        hard_stop = True
        if disposition in {"open", "prefer_provider_or_semantic", "measurement_progress_goal_productive_candidate"}:
            disposition = "metric_definition_correction_required"
    if bool_value(primary_metric_gate.get("primary_metric_stalled")):
        hard_stop = True
        if c4_user_escalation_backstop_required:
            disposition = "user_escalation"
        elif disposition in {"open", "prefer_provider_or_semantic", "measurement_progress_goal_productive_candidate"}:
            disposition = "primary_metric_forced_retarget_required"
    if bool_value(failure_surface_gate.get("terminal_classification_stage_contradiction")):
        hard_stop = True
        if disposition in {"open", "prefer_provider_or_semantic", "measurement_progress_goal_productive_candidate"}:
            disposition = "terminal_classification_stage_repair_required"
    if bool_value(input_contract_gate.get("same_input_contract_violation")):
        hard_stop = True
        if disposition in {"open", "prefer_provider_or_semantic", "measurement_progress_goal_productive_candidate"}:
            disposition = "input_set_contract_repair_required"
    if bool_value(diagnostics_gate.get("instrumentation_supply_required")):
        hard_stop = True
        if disposition in {"open", "prefer_provider_or_semantic", "measurement_progress_goal_productive_candidate"}:
            disposition = "instrumentation_supply_required"
    frame.update({
        "disposition": disposition,
        "hard_stop": hard_stop,
    })
