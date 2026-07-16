from __future__ import annotations

from ..runtime_dependencies import (
    advice_freshness_gate,
    bool_value,
    budget_value,
    call_adapter,
    measurement_progress_details,
    rel_path,
    structure_metrics_gate,
)

from ..evaluation_frame import _EvaluationFrame


def _evaluate_progress_measurement(frame: _EvaluationFrame) -> None:
    (
        bind_artifact_gate, budget_evaluations, coverage_gate, coverage_reconciliation_blocks,
        current_check_ids, current_frontiers, current_root_family_key, current_root_key,
        domain_adapter, family_key, gate_inputs, metric_validity_gate, output_delta,
        paths, quality, record_adapter_hook_demand, registry_rows, root, runner_validation,
        substance_gate,
    ) = frame.require(
        'bind_artifact_gate', 'budget_evaluations', 'coverage_gate',
        'coverage_reconciliation_blocks', 'current_check_ids', 'current_frontiers',
        'current_root_family_key', 'current_root_key', 'domain_adapter', 'family_key',
        'gate_inputs', 'metric_validity_gate', 'output_delta', 'paths', 'quality',
        'record_adapter_hook_demand', 'registry_rows', 'root', 'runner_validation',
        'substance_gate',
    )
    adapter_fingerprint_value, adapter_fingerprint_error = call_adapter(
        domain_adapter,
        "output_fingerprint",
        root=root,
        artifact_paths=[rel_path(root, path) for path in paths],
        quality_vector=quality,
    )
    if adapter_fingerprint_value and not quality.get("current_output_fingerprint"):
        quality["current_output_fingerprint"] = str(adapter_fingerprint_value)
    advice_gate = advice_freshness_gate(root, quality.get("current_output_fingerprint"), [gate_inputs, runner_validation, output_delta])
    structure_value, structure_error = call_adapter(
        domain_adapter,
        "structure_metrics",
        root=root,
        artifact_paths=[rel_path(root, path) for path in paths],
        quality_vector=quality,
        output_delta=output_delta,
        runner_validation=runner_validation,
        family_key=family_key,
        root_key=current_root_key,
    )
    if structure_error:
        structure_value = {"structure_metrics_error": structure_error}
    structure_gate = structure_metrics_gate(structure_value)
    structure_gate = bind_artifact_gate(
        "structure_metrics_gate",
        structure_gate,
        pass_fields=("structure_high_water_moved", "global_structure_high_water_moved"),
        computed_from_decision_artifact=True,
    )
    measurement_details = measurement_progress_details(
        registry_rows,
        family_key,
        current_root_key,
        current_root_family_key,
        current_check_ids,
        current_frontiers,
    )
    measurement_progress = bool_value(measurement_details["measurement_progress"])
    measurement_streak_value = int(measurement_details["measurement_streak"])
    measurement_streak_cap = budget_value(
        budget_evaluations["measurement_nonsemantic_attempts"]
    )
    if measurement_progress:
        record_adapter_hook_demand(
            "metric_validity_self_check",
            "oracle_metric_validity_gate",
            decision_relevant_skip=True,
        )
    measurement_progress_allowed = (
        measurement_progress
        and measurement_streak_cap is not None
        and measurement_streak_value <= measurement_streak_cap
        and bool_value(coverage_gate.get("quality_delta_pass"))
        and bool_value(substance_gate.get("substance_delta_pass"))
        and not coverage_reconciliation_blocks
    )
    if bool_value(metric_validity_gate.get("metric_goal_productive_excluded")):
        measurement_progress_allowed = False
    frame.update({
        "adapter_fingerprint_error": adapter_fingerprint_error,
        "advice_gate": advice_gate,
        "measurement_details": measurement_details,
        "measurement_progress": measurement_progress,
        "measurement_progress_allowed": measurement_progress_allowed,
        "measurement_streak_cap": measurement_streak_cap,
        "measurement_streak_value": measurement_streak_value,
        "structure_error": structure_error,
        "structure_gate": structure_gate,
    })
