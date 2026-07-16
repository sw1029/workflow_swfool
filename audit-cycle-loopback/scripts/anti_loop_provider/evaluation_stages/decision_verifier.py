from __future__ import annotations

from ..runtime_dependencies import (
    bool_value,
    call_adapter,
    coupled_verifier_gate,
    normalize_verifier_source_paths,
    rel_path,
)

from ..evaluation_frame import _EvaluationFrame


def _evaluate_decision_verifier(frame: _EvaluationFrame) -> None:
    (
        adapter_gate, adapter_load_gate, advice_gate, chain_gate, changed_files,
        corrective_gate, coverage_gate, coverage_reconciliation_gate, current_root_key,
        dispatch_gate, disposition, domain_adapter, family_key, forced_retarget_gate,
        gate_inputs, hard_stop, metric_validity_gate, output_delta, paths, primary_metric_gate,
        quality, reachability_gate, root, runner_validation, structure_gate, substance_gate,
        validator_gate,
    ) = frame.require(
        'adapter_gate', 'adapter_load_gate', 'advice_gate', 'chain_gate', 'changed_files',
        'corrective_gate', 'coverage_gate', 'coverage_reconciliation_gate', 'current_root_key',
        'dispatch_gate', 'disposition', 'domain_adapter', 'family_key', 'forced_retarget_gate',
        'gate_inputs', 'hard_stop', 'metric_validity_gate', 'output_delta', 'paths',
        'primary_metric_gate', 'quality', 'reachability_gate', 'root', 'runner_validation',
        'structure_gate', 'substance_gate', 'validator_gate',
    )
    verifier_source_value, verifier_source_error = call_adapter(
        domain_adapter,
        "verifier_source_paths",
        root=root,
        artifact_paths=[rel_path(root, path) for path in paths],
        changed_files=changed_files,
        gate_results=gate_inputs,
        quality_vector=quality,
        output_delta=output_delta,
        runner_validation=runner_validation,
        family_key=family_key,
        root_key=current_root_key,
    )
    verifier_source_map, verifier_source_hook_provided = normalize_verifier_source_paths(verifier_source_value)
    verifier_coupling_gate = coupled_verifier_gate(
        changed_files=changed_files,
        verifier_source_map=verifier_source_map,
        hook_provided=verifier_source_hook_provided,
        gates=[
            adapter_load_gate,
            validator_gate,
            coverage_gate,
            coverage_reconciliation_gate,
            dispatch_gate,
            substance_gate,
            corrective_gate,
            reachability_gate,
            metric_validity_gate,
            advice_gate,
            structure_gate,
            adapter_gate,
            chain_gate,
            forced_retarget_gate,
            primary_metric_gate,
            *gate_inputs,
        ],
    )
    if verifier_source_error:
        verifier_coupling_gate["adapter_error"] = verifier_source_error
    if bool_value(verifier_coupling_gate.get("pass_with_coupled_verifier")):
        hard_stop = True
        if disposition in {"open", "prefer_provider_or_semantic", "measurement_progress_goal_productive_candidate"}:
            disposition = "coupled_verifier_revalidation_required"
        gate_inputs.append({"name": "coupled_verifier_gate", **verifier_coupling_gate})
    frame.update({
        "disposition": disposition,
        "hard_stop": hard_stop,
        "verifier_coupling_gate": verifier_coupling_gate,
        "verifier_source_error": verifier_source_error,
    })
