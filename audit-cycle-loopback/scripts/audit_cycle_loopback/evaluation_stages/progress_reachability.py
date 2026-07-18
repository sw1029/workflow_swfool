from __future__ import annotations

from ..runtime_dependencies import (
    acceptance_reachability_gate,
    acceptance_target_from_value,
    bind_adapter_invocation_result,
    bool_value,
    call_adapter,
    cycle_reachability_gate,
    load_json_value,
    merge_acceptance_verifier_contract,
    oracle_metric_validity_gate,
    rel_path,
)

from ..evaluation_frame import _EvaluationFrame


def _cycle_reachability_from_adapter(
    *,
    acceptance_value: object,
    current_root_key: str,
    domain_adapter: object,
    family_key: str,
    output_delta: object,
    paths: list[object],
    quality: object,
    root: object,
    runner_validation: object,
) -> tuple[dict[str, object], object, str | None, object, str | None]:
    hook_context = {
        "root": root,
        "target": acceptance_target_from_value(acceptance_value),
        "acceptance": acceptance_value,
        "artifact_paths": [rel_path(root, path) for path in paths],
        "quality_vector": quality,
        "output_delta": output_delta,
        "runner_validation": runner_validation,
        "family_key": family_key,
        "root_key": current_root_key,
    }
    scale, scale_error = call_adapter(
        domain_adapter, "acceptance_scale", **hook_context
    )
    throughput, throughput_error = call_adapter(
        domain_adapter,
        "throughput_evidence",
        **hook_context,
    )
    scale_contract_valid = isinstance(scale, dict)
    throughput_contract_valid = isinstance(throughput, dict)
    scale_from_hook = scale_contract_valid and bool(scale)
    throughput_from_hook = throughput_contract_valid and bool(throughput)
    if isinstance(acceptance_value, dict):
        if not isinstance(scale, dict) or not scale:
            scale = acceptance_value.get("acceptance_scale")
        if not isinstance(throughput, dict) or not throughput:
            throughput = acceptance_value.get("throughput_evidence")
        cycle_cap = acceptance_value.get("cycle_execution_cap") or acceptance_value.get(
            "cycle_cap"
        )
        nested_gate = acceptance_value.get("cycle_reachability_gate")
        if cycle_cap is None and isinstance(nested_gate, dict):
            cycle_cap = nested_gate.get("cycle_execution_cap")
        if isinstance(throughput, dict) and not any(
            throughput.get(key) is not None
            for key in (
                "cycle_execution_cap",
                "cycle_cap",
                "max_cycles",
                "execution_cycle_cap",
            )
        ):
            throughput = {**throughput, "cycle_execution_cap": cycle_cap}
    gate = cycle_reachability_gate(scale, throughput)
    reachability_accepted = gate.get("applicability") == "applicable"
    bind_adapter_invocation_result(
        "acceptance_scale",
        return_contract_valid=scale_contract_valid,
        semantic_accepted=bool(
            scale_from_hook and not scale_error and reachability_accepted
        ),
        value_consumed_by_decision=bool(
            scale_from_hook and not scale_error and reachability_accepted
        ),
    )
    bind_adapter_invocation_result(
        "throughput_evidence",
        return_contract_valid=throughput_contract_valid,
        semantic_accepted=bool(
            throughput_from_hook and not throughput_error and reachability_accepted
        ),
        value_consumed_by_decision=bool(
            throughput_from_hook and not throughput_error and reachability_accepted
        ),
    )
    return gate, scale, scale_error, throughput, throughput_error


def _acceptance_reachability_from_adapter(
    *,
    args: object,
    current_root_key: str,
    domain_adapter: object,
    family_key: str,
    output_delta: object,
    paths: list[object],
    quality: object,
    record_adapter_hook_demand: object,
    root: object,
    runner_validation: object,
) -> tuple[object, str | None, object, str | None, dict[str, object]]:
    acceptance_value = load_json_value(
        root, getattr(args, "acceptance_reachability_json", None)
    )
    acceptance_error: str | None = None
    context = {
        "root": root,
        "artifact_paths": [rel_path(root, path) for path in paths],
        "quality_vector": quality,
        "output_delta": output_delta,
        "runner_validation": runner_validation,
        "family_key": family_key,
        "root_key": current_root_key,
    }
    if acceptance_value is None:
        acceptance_value, acceptance_error = call_adapter(
            domain_adapter, "acceptance_reachability", **context
        )
    verifier_value, verifier_error = call_adapter(
        domain_adapter,
        "target_required_verifier",
        target=acceptance_target_from_value(acceptance_value),
        acceptance=acceptance_value,
        acceptance_reachability=acceptance_value,
        **context,
    )
    if verifier_value is not None:
        acceptance_value = merge_acceptance_verifier_contract(
            acceptance_value, verifier_value
        )
    if acceptance_target_from_value(acceptance_value) is not None:
        record_adapter_hook_demand(
            "target_required_verifier",
            "acceptance_reachability_gate",
            decision_relevant_skip=True,
        )
    return (
        acceptance_value,
        acceptance_error,
        verifier_value,
        verifier_error,
        acceptance_reachability_gate(acceptance_value),
    )


def _metric_validity_from_adapter(
    *,
    args: object,
    bind_artifact_gate: object,
    current_root_key: str,
    domain_adapter: object,
    family_key: str,
    output_delta: object,
    paths: list[object],
    quality: object,
    root: object,
    runner_validation: object,
) -> tuple[object, str | None, dict[str, object]]:
    value = load_json_value(root, getattr(args, "metric_validity_json", None))
    error: str | None = None
    if value is None:
        value, error = call_adapter(
            domain_adapter,
            "metric_validity_self_check",
            root=root,
            artifact_paths=[rel_path(root, path) for path in paths],
            quality_vector=quality,
            output_delta=output_delta,
            runner_validation=runner_validation,
            family_key=family_key,
            root_key=current_root_key,
        )
    gate = bind_artifact_gate(
        "oracle_metric_validity_gate",
        oracle_metric_validity_gate(value),
        pass_fields=("metric_goal_productive_excluded",),
        computed_from_decision_artifact=True,
    )
    return value, error, gate


def _evaluate_progress_reachability(frame: _EvaluationFrame) -> None:
    state = frame.snapshot()
    args = state["args"]
    bind_artifact_gate = state["bind_artifact_gate"]
    current_root_key = state["current_root_key"]
    domain_adapter = state["domain_adapter"]
    family_key = state["family_key"]
    gate_inputs = state["gate_inputs"]
    output_delta = state["output_delta"]
    paths = state["paths"]
    quality = state["quality"]
    record_adapter_hook_demand = state["record_adapter_hook_demand"]
    root = state["root"]
    runner_validation = state["runner_validation"]
    (
        acceptance_value,
        acceptance_error,
        target_required_verifier_value,
        target_required_verifier_error,
        reachability_gate,
    ) = _acceptance_reachability_from_adapter(
        args=args,
        current_root_key=current_root_key,
        domain_adapter=domain_adapter,
        family_key=family_key,
        output_delta=output_delta,
        paths=paths,
        quality=quality,
        record_adapter_hook_demand=record_adapter_hook_demand,
        root=root,
        runner_validation=runner_validation,
    )
    if bool_value(reachability_gate.get("constrains_disposition")):
        gate_inputs.append(
            {"name": "acceptance_reachability_gate", **reachability_gate}
        )
    (
        cycle_reachability,
        acceptance_scale_value,
        acceptance_scale_error,
        throughput_evidence_value,
        throughput_evidence_error,
    ) = _cycle_reachability_from_adapter(
        acceptance_value=acceptance_value,
        current_root_key=current_root_key,
        domain_adapter=domain_adapter,
        family_key=family_key,
        output_delta=output_delta,
        paths=paths,
        quality=quality,
        root=root,
        runner_validation=runner_validation,
    )
    if bool_value(cycle_reachability.get("constrains_disposition")):
        gate_inputs.append({"name": "cycle_reachability_gate", **cycle_reachability})
    (
        metric_validity_value,
        metric_validity_error,
        metric_validity_gate,
    ) = _metric_validity_from_adapter(
        args=args,
        bind_artifact_gate=bind_artifact_gate,
        current_root_key=current_root_key,
        domain_adapter=domain_adapter,
        family_key=family_key,
        output_delta=output_delta,
        paths=paths,
        quality=quality,
        root=root,
        runner_validation=runner_validation,
    )
    if bool_value(metric_validity_gate.get("constrains_disposition")):
        gate_inputs.append(
            {"name": "oracle_metric_validity_gate", **metric_validity_gate}
        )
    frame.update(
        {
            "acceptance_error": acceptance_error,
            "acceptance_scale_error": acceptance_scale_error,
            "acceptance_scale_value": acceptance_scale_value,
            "cycle_reachability_gate": cycle_reachability,
            "metric_validity_error": metric_validity_error,
            "metric_validity_gate": metric_validity_gate,
            "metric_validity_value": metric_validity_value,
            "reachability_gate": reachability_gate,
            "target_required_verifier_error": target_required_verifier_error,
            "target_required_verifier_value": target_required_verifier_value,
            "throughput_evidence_error": throughput_evidence_error,
            "throughput_evidence_value": throughput_evidence_value,
        }
    )
