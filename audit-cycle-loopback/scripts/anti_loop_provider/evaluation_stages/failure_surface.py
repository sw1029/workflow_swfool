from __future__ import annotations

from ..runtime_dependencies import (
    bool_value,
    call_adapter,
    first_field_value,
    first_named_value,
    rel_path,
    same_input_contract_gate,
    terminal_stage_resolution_gate,
)

from ..evaluation_frame import _EvaluationFrame


def _evaluate_failure_surface(frame: _EvaluationFrame) -> None:
    (
        current_root_family_key, current_root_key, domain_adapter, failure_autopsies,
        family_key, gate_inputs, output_delta, paths, quality, root, runner_validation,
    ) = frame.require(
        'current_root_family_key', 'current_root_key', 'domain_adapter', 'failure_autopsies',
        'family_key', 'gate_inputs', 'output_delta', 'paths', 'quality', 'root',
        'runner_validation',
    )
    failure_contexts = [runner_validation, output_delta, quality, gate_inputs, *failure_autopsies]
    root_dominant_parameter_key = (
        first_named_value(failure_contexts, {"root_dominant_parameter_key", "dominant_parameter_key", "deficit_axis"})
        or current_root_key
    )
    execution_stage_ladder_value, execution_stage_ladder_error = call_adapter(
        domain_adapter,
        "execution_stage_ladder",
        root=root,
        artifact_paths=[rel_path(root, path) for path in paths],
        quality_vector=quality,
        output_delta=output_delta,
        runner_validation=runner_validation,
        failure_autopsies=failure_autopsies,
        family_key=family_key,
        root_key=current_root_key,
        root_family_key=current_root_family_key,
    )
    if execution_stage_ladder_value is None:
        execution_stage_ladder_value = first_field_value(failure_contexts, {"execution_stage_ladder", "stage_ladder"})
    terminal_stage_map_value, terminal_stage_map_error = call_adapter(
        domain_adapter,
        "terminal_classification_stage_map",
        root=root,
        artifact_paths=[rel_path(root, path) for path in paths],
        quality_vector=quality,
        output_delta=output_delta,
        runner_validation=runner_validation,
        failure_autopsies=failure_autopsies,
        family_key=family_key,
        root_key=current_root_key,
        root_family_key=current_root_family_key,
    )
    failure_surface_gate = terminal_stage_resolution_gate(
        ladder_value=execution_stage_ladder_value,
        classification_map_value=terminal_stage_map_value,
        contexts=failure_contexts,
        root_family_key=current_root_family_key,
        dominant_parameter=str(root_dominant_parameter_key),
    )
    if execution_stage_ladder_error:
        failure_surface_gate["execution_stage_ladder_error"] = execution_stage_ladder_error
    if terminal_stage_map_error:
        failure_surface_gate["terminal_classification_stage_map_error"] = terminal_stage_map_error
    effective_count_key = str(failure_surface_gate.get("failure_surface_count_key") or current_root_family_key)
    if bool_value(failure_surface_gate.get("constrains_disposition")):
        gate_inputs.append({"name": "failure_surface_stage_gate", **failure_surface_gate})
    input_contract_gate = same_input_contract_gate(failure_contexts)
    if bool_value(input_contract_gate.get("constrains_disposition")):
        gate_inputs.append({"name": "same_input_contract_gate", **input_contract_gate})
    frame.update({
        "effective_count_key": effective_count_key,
        "failure_contexts": failure_contexts,
        "failure_surface_gate": failure_surface_gate,
        "input_contract_gate": input_contract_gate,
        "root_dominant_parameter_key": root_dominant_parameter_key,
    })
