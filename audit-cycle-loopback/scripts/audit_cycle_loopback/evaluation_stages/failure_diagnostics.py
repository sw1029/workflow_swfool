from __future__ import annotations

from ..runtime_dependencies import (
    bool_value,
    budget_evaluation,
    budget_value,
    call_adapter,
    diagnostics_unavailable_gate,
    positive_int_or_none,
    rel_path,
)

from ..evaluation_frame import _EvaluationFrame


def _evaluate_failure_diagnostics(frame: _EvaluationFrame) -> None:
    (
        args, budget_evaluations, current_root_family_key, current_root_key, domain_adapter,
        failure_autopsies, failure_contexts, failure_surface_gate, family_key, gate_inputs,
        output_delta, paths, quality, registry_rows, root, runner_validation,
    ) = frame.require(
        'args', 'budget_evaluations', 'current_root_family_key', 'current_root_key',
        'domain_adapter', 'failure_autopsies', 'failure_contexts', 'failure_surface_gate',
        'family_key', 'gate_inputs', 'output_delta', 'paths', 'quality',
        'registry_rows', 'root', 'runner_validation',
    )
    instrumentation_threshold_value, instrumentation_threshold_error = call_adapter(
        domain_adapter,
        "instrumentation_trigger_threshold",
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
    instrumentation_budget_source = (
        "adapter"
        if positive_int_or_none(instrumentation_threshold_value) is not None
        else "caller_or_repository_config"
    )
    instrumentation_budget_input = (
        instrumentation_threshold_value
        if positive_int_or_none(instrumentation_threshold_value) is not None
        else getattr(args, "instrumentation_trigger_threshold", None)
    )
    instrumentation_budget_evaluation = budget_evaluation(
        "instrumentation_unobservable_attempts",
        instrumentation_budget_input,
        source=instrumentation_budget_source,
        error=instrumentation_threshold_error,
    )
    budget_evaluations["instrumentation_unobservable_attempts"] = (
        instrumentation_budget_evaluation
    )
    instrumentation_threshold = budget_value(instrumentation_budget_evaluation)
    diagnostics_gate = diagnostics_unavailable_gate(
        registry_rows=registry_rows,
        failure_surface_count_key=failure_surface_gate.get("failure_surface_count_key"),
        contexts=failure_contexts,
        threshold=instrumentation_threshold,
    )
    if instrumentation_threshold_error:
        diagnostics_gate["adapter_error"] = instrumentation_threshold_error
    if bool_value(diagnostics_gate.get("constrains_disposition")):
        gate_inputs.append({"name": "diagnostics_unavailable_gate", **diagnostics_gate})
    frame.update({
        "diagnostics_gate": diagnostics_gate,
    })
