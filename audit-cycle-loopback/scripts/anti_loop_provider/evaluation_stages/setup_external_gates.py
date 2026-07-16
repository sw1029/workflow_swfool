from __future__ import annotations

from ..runtime_dependencies import (
    Any,
    bool_value,
    extract_disposition_gates,
    load_json_value,
    normalize_portfolio_budget_gate,
    normalize_root_family_key,
    terminal_self_resolution_gate,
)

from ..evaluation_frame import _EvaluationFrame


def _prepare_external_gates(frame: _EvaluationFrame) -> None:
    (
        adapter_load_gate, args, bind_artifact_gate, budget_evaluations, finalized_cycle_id,
        finalized_state_error, finalized_state_status, output_delta, root, runner_validation,
    ) = frame.require(
        'adapter_load_gate', 'args', 'bind_artifact_gate', 'budget_evaluations',
        'finalized_cycle_id', 'finalized_state_error', 'finalized_state_status',
        'output_delta', 'root', 'runner_validation',
    )
    gate_inputs: list[dict[str, Any]] = []
    if finalized_state_status == "invalid":
        gate_inputs.append(
            {
                "name": "finalized_state_integrity_gate",
                "gate": "FINALIZED-STATE-INTEGRITY",
                "status": "block",
                "constrains_disposition": True,
                "allowed_dispositions": ["terminal_blocked", "user_escalation"],
                "finalized_cycle_id": finalized_cycle_id,
                "error": finalized_state_error,
            }
        )
    if bool_value(adapter_load_gate.get("constrains_disposition")):
        gate_inputs.append({"name": "adapter_wiring_gate", **adapter_load_gate})
    for raw_gate in getattr(args, "gate_state_json", []) or []:
        for gate in extract_disposition_gates(load_json_value(root, raw_gate)):
            gate_id = str(gate.get("name") or gate.get("gate") or gate.get("gate_id") or "external_gate")
            if normalize_root_family_key(gate_id) in {
                "portfolio_quota",
                "portfolio_quota_gate",
            }:
                gate, portfolio_budget_evaluation = normalize_portfolio_budget_gate(gate)
                budget_evaluations["portfolio_nonsemantic_work"] = portfolio_budget_evaluation
            gate_inputs.append(bind_artifact_gate(gate_id, gate))
    identity_gate_inputs = [dict(gate) for gate in gate_inputs]
    terminal_self_resolution = terminal_self_resolution_gate(runner_validation, output_delta, *gate_inputs)
    if bool_value(terminal_self_resolution.get("goal_terminal_prohibited")):
        gate_inputs.append(
            {
                "name": "terminal_self_resolution",
                **terminal_self_resolution,
                "constrains_disposition": True,
                "allowed_dispositions": ["goal_productive"],
            }
        )
    frame.update({
        "gate_inputs": gate_inputs,
        "identity_gate_inputs": identity_gate_inputs,
        "terminal_self_resolution": terminal_self_resolution,
    })
