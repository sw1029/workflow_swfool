from __future__ import annotations

from ..runtime_dependencies import (
    bool_value,
    budget_value,
    classify_task_correction,
    detection_only_streak,
    numeric_vector,
)

from ..evaluation_frame import _EvaluationFrame


def _evaluate_progress_correction(frame: _EvaluationFrame) -> None:
    (
        args, artifact_decision_evaluated, blocker_root_family, budget_evaluations,
        changed_vs_previous, coverage_gate, current_check_ids, current_frontiers,
        current_substance, facet_root_map_missing, gate_inputs, hard_stop, insufficient_reason,
        output_delta, provider_request_count, quality, record_adapter_hook_demand,
        registry_rows, runner_validation, semantic_progress, substance_gate,
    ) = frame.require(
        'args', 'artifact_decision_evaluated', 'blocker_root_family', 'budget_evaluations',
        'changed_vs_previous', 'coverage_gate', 'current_check_ids', 'current_frontiers',
        'current_substance', 'facet_root_map_missing', 'gate_inputs', 'hard_stop',
        'insufficient_reason',
        'output_delta', 'provider_request_count', 'quality', 'record_adapter_hook_demand',
        'registry_rows', 'runner_validation', 'semantic_progress', 'substance_gate',
    )
    task_correction_class = classify_task_correction(
        current_check_ids=current_check_ids,
        current_frontiers=current_frontiers,
        provider_request_count=provider_request_count,
        changed_vs_previous=changed_vs_previous,
        semantic_progress=semantic_progress,
        values=[runner_validation, output_delta, quality, gate_inputs, args.semantic_signature, args.artifact_family],
    )
    detection_only = artifact_decision_evaluated and task_correction_class == "detection" and not semantic_progress
    detection_streak = detection_only_streak(registry_rows, blocker_root_family, detection_only)
    detection_streak_cap = budget_value(
        budget_evaluations["detection_nonsemantic_attempts"]
    )
    requires_correction_or_terminal = (
        detection_streak_cap is not None
        and detection_streak >= detection_streak_cap
        and not semantic_progress
    )
    if requires_correction_or_terminal:
        hard_stop = True
    current_no_goal_distance_delta = artifact_decision_evaluated and not (
        bool_value(coverage_gate.get("quality_delta_pass"))
        or bool_value(substance_gate.get("substance_delta_pass"))
    )
    if current_no_goal_distance_delta:
        if insufficient_reason == "domain_adapter_quality_vector_missing":
            record_adapter_hook_demand("quality_vector", "adapter_mandate_gate", decision_relevant_skip=True)
        if facet_root_map_missing:
            record_adapter_hook_demand("facet_root_map", "adapter_mandate_gate", decision_relevant_skip=True)
        if not numeric_vector(current_substance):
            record_adapter_hook_demand("substance_metrics", "adapter_mandate_gate", decision_relevant_skip=True)
    frame.update({
        "current_no_goal_distance_delta": current_no_goal_distance_delta,
        "detection_only": detection_only,
        "detection_streak": detection_streak,
        "detection_streak_cap": detection_streak_cap,
        "hard_stop": hard_stop,
        "requires_correction_or_terminal": requires_correction_or_terminal,
        "task_correction_class": task_correction_class,
    })
