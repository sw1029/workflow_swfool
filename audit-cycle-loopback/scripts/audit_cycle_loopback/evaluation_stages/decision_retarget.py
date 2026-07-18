from __future__ import annotations

from ..runtime_dependencies import (
    bool_value,
    bind_adapter_invocation_result,
    call_adapter,
    chain_stall_forced_retarget_gate,
    first_actionable_capability_ladder_option,
    normalize_task_kinds,
    rel_path,
)

from ..evaluation_frame import _EvaluationFrame


def _evaluate_decision_retarget(frame: _EvaluationFrame) -> None:
    (
        adapter_load_gate, chain_gate, current_root_family_key, current_root_key,
        domain_adapter, family_key, gate_inputs, high_water, mutation_kind, output_delta,
        paths, primary_metric_gate, quality, root, runner_validation,
    ) = frame.require(
        'adapter_load_gate', 'chain_gate', 'current_root_family_key', 'current_root_key',
        'domain_adapter', 'family_key', 'gate_inputs', 'high_water', 'mutation_kind',
        'output_delta', 'paths', 'primary_metric_gate', 'quality', 'root',
        'runner_validation',
    )
    capability_ladder_value, capability_ladder_error = call_adapter(
        domain_adapter,
        "capability_ladder",
        root=root,
        artifact_paths=[rel_path(root, path) for path in paths],
        quality_vector=quality,
        output_delta=output_delta,
        runner_validation=runner_validation,
        family_key=family_key,
        root_key=current_root_key,
        root_family_key=current_root_family_key,
        high_water=high_water,
    )
    capability_ladder_option = first_actionable_capability_ladder_option(capability_ladder_value)
    capability_status = (
        str(
            capability_ladder_value.get("evaluation_status")
            or capability_ladder_value.get("status")
            or ""
        ).strip().lower()
        if isinstance(capability_ladder_value, dict)
        else ""
    )
    capability_contract_valid = isinstance(capability_ladder_value, (dict, list))
    capability_accepted = bool(
        capability_contract_valid
        and not capability_ladder_error
        and capability_status
        not in {"fail", "failed", "fail_quiet", "not_evaluated", "unavailable"}
    )
    bind_adapter_invocation_result(
        "capability_ladder",
        return_contract_valid=capability_contract_valid,
        semantic_accepted=capability_accepted,
        value_consumed_by_decision=capability_accepted,
    )
    forced_retarget_gate = chain_stall_forced_retarget_gate(
        chain_gate,
        blocker_mutation=mutation_kind,
        adapter_gate=adapter_load_gate,
        capability_ladder_option=capability_ladder_option,
    )
    if capability_ladder_error:
        forced_retarget_gate["capability_ladder_error"] = capability_ladder_error
    if bool_value(forced_retarget_gate.get("constrains_disposition")):
        chain_gate["allowed_dispositions"] = ["goal_productive", "terminal_blocked", "user_escalation"]
        chain_gate["allowed_task_kinds"] = forced_retarget_gate.get("allowed_task_kinds") or []
        gate_inputs.append({"name": "chain_stall_forced_retarget_gate", **forced_retarget_gate})
    c4_user_escalation_backstop_required = False
    if bool_value(primary_metric_gate.get("primary_metric_stalled")):
        forced_task_kinds = normalize_task_kinds(forced_retarget_gate.get("allowed_task_kinds") or [])
        if forced_task_kinds:
            primary_metric_gate["allowed_task_kinds"] = sorted(forced_task_kinds)
        else:
            c4_user_escalation_backstop_required = True
            primary_metric_gate["c4_user_escalation_backstop_required"] = True
            primary_metric_gate["allowed_dispositions"] = ["user_escalation"]
        gate_inputs.append({"name": "primary_metric_gate", **primary_metric_gate})
    frame.update({
        "c4_user_escalation_backstop_required": c4_user_escalation_backstop_required,
        "forced_retarget_gate": forced_retarget_gate,
    })
