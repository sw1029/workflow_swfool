from __future__ import annotations

from ..runtime_dependencies import (
    adapter_contract_unmet_fields,
    budget_evaluation,
    call_adapter,
    hook_demand_threshold_from_value,
    merge_adapter_hook_demand,
    normalize_hook_id,
    numeric_vector,
    partial_progress_axes_gate,
    rel_path,
)

from ..evaluation_frame import _EvaluationFrame


def _evaluate_progress_adapter_demand(frame: _EvaluationFrame) -> None:
    (
        adapter_hook_value_supplied, args, budget_evaluations, current_no_goal_distance_delta,
        current_root_family_key, current_root_key, current_substance, domain_adapter,
        evidence_provenance_value, facet_root_map, facet_root_map_missing, family_key,
        hook_demand_events, metric_validity_value, output_delta, paths, quality,
        registry_rows, root, runner_validation, substance_gate, target_required_verifier_value,
    ) = frame.require(
        'adapter_hook_value_supplied', 'args', 'budget_evaluations',
        'current_no_goal_distance_delta', 'current_root_family_key', 'current_root_key',
        'current_substance', 'domain_adapter', 'evidence_provenance_value', 'facet_root_map',
        'facet_root_map_missing', 'family_key', 'hook_demand_events', 'metric_validity_value',
        'output_delta', 'paths', 'quality', 'registry_rows', 'root',
        'runner_validation', 'substance_gate', 'target_required_verifier_value',
    )
    partial_progress_value, partial_progress_error = call_adapter(
        domain_adapter,
        "partial_progress_axes",
        root=root,
        artifact_paths=[rel_path(root, path) for path in paths],
        quality_vector=quality,
        output_delta=output_delta,
        runner_validation=runner_validation,
        family_key=family_key,
        root_key=current_root_key,
        current_no_goal_distance_delta=current_no_goal_distance_delta,
    )
    partial_progress_gate = partial_progress_axes_gate(partial_progress_value, current_no_goal_distance_delta)
    partial_progress_gate["adapter_error"] = partial_progress_error
    adapter_contract_unmet = adapter_contract_unmet_fields(
        facet_root_map_missing=facet_root_map_missing,
        substance_gate=substance_gate,
        quality=quality,
    )
    hook_threshold_value, hook_threshold_error = call_adapter(
        domain_adapter,
        "hook_demand_threshold",
        root=root,
        artifact_paths=[rel_path(root, path) for path in paths],
        quality_vector=quality,
        output_delta=output_delta,
        runner_validation=runner_validation,
        family_key=family_key,
        root_key=current_root_key,
        root_family_key=current_root_family_key,
    )
    hook_demand_threshold = hook_demand_threshold_from_value(
        hook_threshold_value,
        None,
    )
    hook_demand_budget_evaluation = budget_evaluation(
        "hook_demand_attempts",
        hook_demand_threshold,
        source="adapter" if hook_demand_threshold is not None else None,
        error=hook_threshold_error,
    )
    budget_evaluations["hook_demand_attempts"] = hook_demand_budget_evaluation
    adapter_hook_demand = merge_adapter_hook_demand(registry_rows, hook_demand_events, args.cycle_id)
    supplied_adapter_hooks = set()
    if numeric_vector(quality):
        supplied_adapter_hooks.add("quality_vector")
    if facet_root_map:
        supplied_adapter_hooks.add("facet_root_map")
    if numeric_vector(current_substance):
        supplied_adapter_hooks.add("substance_metrics")
    if adapter_hook_value_supplied(target_required_verifier_value):
        supplied_adapter_hooks.add("target_required_verifier")
    if adapter_hook_value_supplied(metric_validity_value):
        supplied_adapter_hooks.add("metric_validity_self_check")
    if adapter_hook_value_supplied(evidence_provenance_value):
        supplied_adapter_hooks.add("evidence_provenance")
    if adapter_hook_value_supplied(partial_progress_value):
        supplied_adapter_hooks.add("partial_progress_axes")
    if domain_adapter is None:
        adapter_hook_demand = []
    elif supplied_adapter_hooks:
        adapter_hook_demand = [
            record
            for record in adapter_hook_demand
            if normalize_hook_id(record.get("hook_id")) not in supplied_adapter_hooks
        ]
    frame.update({
        "adapter_contract_unmet": adapter_contract_unmet,
        "adapter_hook_demand": adapter_hook_demand,
        "hook_demand_threshold": hook_demand_threshold,
        "hook_threshold_error": hook_threshold_error,
        "partial_progress_gate": partial_progress_gate,
    })
