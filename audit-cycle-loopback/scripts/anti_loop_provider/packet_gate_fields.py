from __future__ import annotations

from .runtime_dependencies import (
    Any,
    bool_value,
    numeric_vector,
    previous_micro_hardening_count,
    public_quality_delta_policy,
)

from .evaluation_frame import _require_values


def _gate_fields(state: dict[str, Any]) -> dict[str, Any]:
    (
        adapter_contract_unmet, adapter_expected_path, adapter_gate, adapter_load_gate,
        adapter_registered, advice_gate, chain_gate, corrective_gate, coverage_gate,
        coverage_reconciliation_gate, current_root_family_key, current_substance,
        current_terminal_outcome_key, domain_adapter, domain_adapter_path, facet_root_map,
        facet_root_map_missing, forced_retarget_gate, forced_selected_task,
        forced_task_options, high_water, latest_terminal_family, metric_validity_gate,
        partial_progress_gate, prev_high, quality, quality_delta_policy, raw_root_family_key,
        reachability_gate, registry_rows, repo_owned_source_roots,
        repo_owned_source_roots_error, repo_owned_source_roots_status, structure_gate,
        substance_gate, terminal_family_fallback, terminal_family_key, terminal_family_source,
        terminal_self_resolution,
    ) = _require_values(
        state,
        (
            'adapter_contract_unmet', 'adapter_expected_path', 'adapter_gate',
            'adapter_load_gate', 'adapter_registered', 'advice_gate', 'chain_gate',
            'corrective_gate', 'coverage_gate', 'coverage_reconciliation_gate',
            'current_root_family_key', 'current_substance', 'current_terminal_outcome_key',
            'domain_adapter', 'domain_adapter_path', 'facet_root_map',
            'facet_root_map_missing', 'forced_retarget_gate', 'forced_selected_task',
            'forced_task_options', 'high_water', 'latest_terminal_family',
            'metric_validity_gate', 'partial_progress_gate', 'prev_high', 'quality',
            'quality_delta_policy', 'raw_root_family_key', 'reachability_gate',
            'registry_rows', 'repo_owned_source_roots', 'repo_owned_source_roots_error',
            'repo_owned_source_roots_status', 'structure_gate', 'substance_gate',
            'terminal_family_fallback', 'terminal_family_key', 'terminal_family_source',
            'terminal_self_resolution',
        ),
    )
    return {
        "quality_vector": quality,
        "quality_delta_policy": public_quality_delta_policy(quality_delta_policy),
        "previous_high_water_mark": prev_high,
        "high_water_mark": high_water,
        "coverage_quality_delta_gate": coverage_gate,
        "coverage_quality_delta_reconciliation_gate": coverage_reconciliation_gate,
        "substance_metrics": numeric_vector(current_substance),
        "substance_delta_gate": substance_gate,
        "vacuous_corrective_gate": corrective_gate,
        "adapter_mandate_gate": adapter_gate,
        "adapter_mandate_required": bool_value(adapter_gate.get("adapter_mandate_required")),
        "adapter_missing_streak": adapter_gate.get("adapter_missing_streak"),
        "adapter_contract_unmet": adapter_contract_unmet,
        "adapter_wiring_gate": adapter_load_gate,
        "consumer_context_conformance": adapter_load_gate.get("consumer_context_conformance") or {},
        "adapter_wiring_defect": bool_value(adapter_load_gate.get("adapter_wiring_defect")),
        "adapter_loaded": domain_adapter is not None,
        "adapter_registered": adapter_registered,
        "adapter_path": domain_adapter_path or adapter_expected_path,
        "adapter_expected_path": adapter_expected_path,
        "cumulative_goal_distance_gate": chain_gate,
        "cumulative_goal_distance_scope_key": chain_gate.get("cumulative_goal_distance_scope_key"),
        "cumulative_goal_distance_stall_streak": chain_gate.get("cumulative_goal_distance_stall_streak"),
        "cumulative_goal_distance_stalled": bool_value(chain_gate.get("cumulative_goal_distance_stalled")),
        "chain_stall_forced_retarget_gate": forced_retarget_gate,
        "forced_selected_task": forced_selected_task,
        "forced_selected_task_options": forced_task_options,
        "high_water_vector": chain_gate.get("high_water_vector"),
        "high_water_last_improved_cycle": chain_gate.get("high_water_last_improved_cycle"),
        "acceptance_reachability_gate": reachability_gate,
        "acceptance_unreachable_under_frozen_config": bool_value(
            reachability_gate.get("acceptance_unreachable_under_frozen_config")
        ),
        "acceptance_verifier_not_evaluated": bool_value(
            reachability_gate.get("acceptance_verifier_not_evaluated")
        ),
        "unverifiable_acceptance_contract": bool_value(
            reachability_gate.get("unverifiable_acceptance_contract")
        ),
        "relaxation_or_escalation_required": bool_value(
            reachability_gate.get("relaxation_or_escalation_required")
        ),
        "residual_gap_policy": reachability_gate.get("residual_gap_policy"),
        "residual_gap_ratio": reachability_gate.get("residual_gap_ratio"),
        "marginal_repair": bool_value(reachability_gate.get("marginal_repair")),
        "oracle_metric_validity_gate": metric_validity_gate,
        "metric_verifier_not_evaluated": bool_value(
            metric_validity_gate.get("metric_verifier_not_evaluated")
        ),
        "repo_owned_source_roots": repo_owned_source_roots,
        "repo_owned_source_roots_status": repo_owned_source_roots_status,
        "repo_owned_source_roots_error": repo_owned_source_roots_error,
        "facet_root_map_applied": bool(facet_root_map),
        "facet_root_map_missing": facet_root_map_missing,
        "facet_root_map_size": len(facet_root_map),
        "raw_root_family_key": raw_root_family_key,
        "terminal_outcome_key": current_terminal_outcome_key,
        "terminal_outcome_family_key": terminal_family_key,
        "terminal_outcome_family_source": terminal_family_source,
        "terminal_outcome_family_fallback_applied": terminal_family_fallback,
        "terminal_outcome_family_previous_count": previous_micro_hardening_count(registry_rows, current_root_family_key),
        "terminal_outcome_family_previous_cycle_id": (latest_terminal_family or {}).get("cycle_id"),
        "terminal_self_resolution_gate": terminal_self_resolution,
        "offline_scope_unverified": bool_value(terminal_self_resolution.get("offline_scope_unverified")),
        "goal_terminal_prohibited": bool_value(terminal_self_resolution.get("goal_terminal_prohibited")),
        "advice_freshness_gate": advice_gate,
        "partial_progress_axes_gate": partial_progress_gate,
        "structure_metrics_gate": structure_gate,
        "structure_high_water_key_scope": structure_gate.get("structure_high_water_key_scope"),
        "structure_global_invariant_metrics": structure_gate.get("structure_global_invariant_metrics") or {},
    }
