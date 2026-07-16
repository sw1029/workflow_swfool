from __future__ import annotations

from ..runtime_dependencies import (
    adapter_mandate_gate,
    bool_value,
    cumulative_goal_distance_gate,
)

from ..evaluation_frame import _EvaluationFrame


def _evaluate_progress_chain(frame: _EvaluationFrame) -> None:
    (
        adapter_contract_unmet, adapter_hook_demand, adapter_load_gate, args,
        current_no_goal_distance_delta, current_root_family_key, disposition,
        facet_root_map_missing, gate_inputs, hard_stop, high_water, hook_demand_threshold,
        hook_threshold_error, registry_rows,
    ) = frame.require(
        'adapter_contract_unmet', 'adapter_hook_demand', 'adapter_load_gate', 'args',
        'current_no_goal_distance_delta', 'current_root_family_key', 'disposition',
        'facet_root_map_missing', 'gate_inputs', 'hard_stop', 'high_water',
        'hook_demand_threshold', 'hook_threshold_error', 'registry_rows',
    )
    adapter_gate = adapter_mandate_gate(
        registry_rows,
        artifact_family=args.artifact_family,
        contract_unmet=adapter_contract_unmet,
        current_no_delta=current_no_goal_distance_delta,
        cap=getattr(args, "adapter_mandate_streak_cap", None),
        adapter_hook_demand=adapter_hook_demand,
        hook_demand_threshold=hook_demand_threshold,
    )
    if hook_threshold_error:
        adapter_gate["hook_demand_threshold_error"] = hook_threshold_error
    if bool_value(adapter_load_gate.get("adapter_wiring_defect")):
        adapter_gate["adapter_mandate_required"] = False
        adapter_gate["status"] = "ok"
        adapter_gate["adapter_wiring_defect_supersedes_adapter_mandate"] = True
    if bool_value(adapter_load_gate.get("adapter_wiring_defect")):
        hard_stop = True
        disposition = "self_inflicted_gate_defect"
    elif bool_value(adapter_gate.get("adapter_mandate_required")):
        hard_stop = True
        disposition = "adapter_mandate_required"
        gate_inputs.append({"name": "adapter_mandate_gate", **adapter_gate})
    chain_gate = cumulative_goal_distance_gate(
        registry_rows,
        artifact_family=args.artifact_family,
        root_family_key=current_root_family_key,
        facet_root_map_missing=facet_root_map_missing,
        current_no_delta=current_no_goal_distance_delta,
        high_water=high_water,
        current_cycle_id=args.cycle_id,
        cap=getattr(args, "cumulative_chain_streak_cap", None),
    )
    frame.update({
        "adapter_gate": adapter_gate,
        "chain_gate": chain_gate,
        "disposition": disposition,
        "hard_stop": hard_stop,
    })
