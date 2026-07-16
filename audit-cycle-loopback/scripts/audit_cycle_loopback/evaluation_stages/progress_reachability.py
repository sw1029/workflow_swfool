from __future__ import annotations

from ..runtime_dependencies import (
    acceptance_reachability_gate,
    acceptance_target_from_value,
    bool_value,
    call_adapter,
    load_json_value,
    merge_acceptance_verifier_contract,
    oracle_metric_validity_gate,
    rel_path,
)

from ..evaluation_frame import _EvaluationFrame


def _evaluate_progress_reachability(frame: _EvaluationFrame) -> None:
    (
        args, bind_artifact_gate, current_root_key, domain_adapter, family_key, gate_inputs,
        output_delta, paths, quality, record_adapter_hook_demand, root,
        runner_validation,
    ) = frame.require(
        'args', 'bind_artifact_gate', 'current_root_key', 'domain_adapter', 'family_key',
        'gate_inputs', 'output_delta', 'paths', 'quality',
        'record_adapter_hook_demand', 'root', 'runner_validation',
    )
    acceptance_value = load_json_value(root, getattr(args, "acceptance_reachability_json", None))
    acceptance_error: str | None = None
    if acceptance_value is None:
        acceptance_value, acceptance_error = call_adapter(
            domain_adapter,
            "acceptance_reachability",
            root=root,
            artifact_paths=[rel_path(root, path) for path in paths],
            quality_vector=quality,
            output_delta=output_delta,
            runner_validation=runner_validation,
            family_key=family_key,
            root_key=current_root_key,
        )
    target_required_verifier_error: str | None = None
    target_required_verifier_value, target_required_verifier_error = call_adapter(
        domain_adapter,
        "target_required_verifier",
        root=root,
        target=acceptance_target_from_value(acceptance_value),
        acceptance=acceptance_value,
        acceptance_reachability=acceptance_value,
        artifact_paths=[rel_path(root, path) for path in paths],
        quality_vector=quality,
        output_delta=output_delta,
        runner_validation=runner_validation,
        family_key=family_key,
        root_key=current_root_key,
    )
    if target_required_verifier_value is not None:
        acceptance_value = merge_acceptance_verifier_contract(acceptance_value, target_required_verifier_value)
    if acceptance_target_from_value(acceptance_value) is not None:
        record_adapter_hook_demand(
            "target_required_verifier",
            "acceptance_reachability_gate",
            decision_relevant_skip=True,
        )
    reachability_gate = acceptance_reachability_gate(acceptance_value)
    if bool_value(reachability_gate.get("constrains_disposition")):
        gate_inputs.append({"name": "acceptance_reachability_gate", **reachability_gate})
    metric_validity_value = load_json_value(root, getattr(args, "metric_validity_json", None))
    metric_validity_error: str | None = None
    if metric_validity_value is None:
        metric_validity_value, metric_validity_error = call_adapter(
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
    metric_validity_gate = oracle_metric_validity_gate(metric_validity_value)
    metric_validity_gate = bind_artifact_gate(
        "oracle_metric_validity_gate",
        metric_validity_gate,
        pass_fields=("metric_goal_productive_excluded",),
        computed_from_decision_artifact=True,
    )
    if bool_value(metric_validity_gate.get("constrains_disposition")):
        gate_inputs.append({"name": "oracle_metric_validity_gate", **metric_validity_gate})
    frame.update({
        "acceptance_error": acceptance_error,
        "metric_validity_error": metric_validity_error,
        "metric_validity_gate": metric_validity_gate,
        "metric_validity_value": metric_validity_value,
        "reachability_gate": reachability_gate,
        "target_required_verifier_error": target_required_verifier_error,
        "target_required_verifier_value": target_required_verifier_value,
    })
