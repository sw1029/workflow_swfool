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


SCOPED_PROGRESS_DECLARATION_KEYS = frozenset(
    {
        "progress_scope_contract",
        "work_intent",
        "progress_observations",
        "closeout_projection",
        "retained_change_evidence",
        "retained_change_classification",
    }
)
SCOPED_PROGRESS_TRANSPORT_KEYS = (
    "progress_scope_contract",
    "work_intent",
    "progress_observations",
    "closeout_projection",
    "retained_change_evidence",
    "actual_changed_files",
    "goal_axis_completeness_gate",
    "goal_axis_observations",
    "unobserved_goal_axes",
    "goal_axis_conflicted",
    "task_acceptance_verdict",
    "goal_readiness_verdict",
)


def _scoped_progress_candidate(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    nested = value.get("scoped_progress")
    source = nested if isinstance(nested, dict) else value
    if not SCOPED_PROGRESS_DECLARATION_KEYS & set(source):
        return None
    projected = {
        key: source[key]
        for key in SCOPED_PROGRESS_TRANSPORT_KEYS
        if key in source
    }
    for key in (
        "goal_axis_completeness_gate",
        "goal_axis_observations",
        "unobserved_goal_axes",
        "goal_axis_conflicted",
        "task_acceptance_verdict",
        "goal_readiness_verdict",
    ):
        if key in value:
            projected[key] = value[key]
    return projected or {"progress_scope_contract": {}}


def _select_scoped_progress_input(
    values: list[Any],
) -> tuple[dict[str, Any] | None, bool]:
    candidates = [
        candidate
        for value in values
        if (candidate := _scoped_progress_candidate(value)) is not None
    ]
    if not candidates:
        return None, False
    first = candidates[0]
    if all(candidate == first for candidate in candidates[1:]):
        return first, False
    # Preserve declaration while refusing a positive projection from conflicts.
    return {"progress_scope_contract": {}}, True


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
    loaded_gate_values: list[Any] = []
    for raw_gate in getattr(args, "gate_state_json", []) or []:
        loaded_value = load_json_value(root, raw_gate)
        loaded_gate_values.append(loaded_value)
        for gate in extract_disposition_gates(loaded_value):
            gate_id = str(gate.get("name") or gate.get("gate") or gate.get("gate_id") or "external_gate")
            if normalize_root_family_key(gate_id) in {
                "portfolio_quota",
                "portfolio_quota_gate",
            }:
                gate, portfolio_budget_evaluation = normalize_portfolio_budget_gate(gate)
                budget_evaluations["portfolio_nonsemantic_work"] = portfolio_budget_evaluation
            gate_inputs.append(bind_artifact_gate(gate_id, gate))
    scoped_progress_input, scoped_progress_input_conflicted = (
        _select_scoped_progress_input(loaded_gate_values)
    )
    identity_gate_inputs = [dict(gate) for gate in gate_inputs]
    terminal_self_resolution = terminal_self_resolution_gate(runner_validation, output_delta, *gate_inputs)
    if bool_value(terminal_self_resolution.get("goal_terminal_prohibited")):
        gate_inputs.append(
            {
                "name": "terminal_self_resolution",
                **terminal_self_resolution,
                "constrains_disposition": True,
                "allowed_dispositions": terminal_self_resolution.get(
                    "allowed_resolution_dispositions"
                )
                or ["classification_repair"],
            }
        )
    frame.update({
        "gate_inputs": gate_inputs,
        "identity_gate_inputs": identity_gate_inputs,
        "scoped_progress_input": scoped_progress_input,
        "scoped_progress_input_conflicted": scoped_progress_input_conflicted,
        "terminal_self_resolution": terminal_self_resolution,
    })
