from __future__ import annotations

from .runtime_dependencies import (
    Any,
    bool_value,
    numeric_vector,
    previous_micro_hardening_count,
    public_quality_delta_policy,
)


def _acceptance_reachability_fields(gate: dict[str, Any]) -> dict[str, Any]:
    return {
        "acceptance_reachability_gate": gate,
        "acceptance_unreachable_under_frozen_config": bool_value(
            gate.get("acceptance_unreachable_under_frozen_config")
        ),
        "acceptance_verifier_not_evaluated": bool_value(
            gate.get("acceptance_verifier_not_evaluated")
        ),
        "unverifiable_acceptance_contract": bool_value(
            gate.get("unverifiable_acceptance_contract")
        ),
        "relaxation_or_escalation_required": bool_value(
            gate.get("relaxation_or_escalation_required")
        ),
        "residual_gap_policy": gate.get("residual_gap_policy"),
        "residual_gap_ratio": gate.get("residual_gap_ratio"),
        "marginal_repair": bool_value(gate.get("marginal_repair")),
    }


def _cycle_reachability_fields(gate: dict[str, Any]) -> dict[str, Any]:
    return {
        "cycle_reachability_gate": gate,
        "acceptance_scale": gate.get("acceptance_scale") or {},
        "throughput_evidence": gate.get("throughput_evidence") or {},
        "unreachable_within_cycle": bool_value(gate.get("unreachable_within_cycle")),
        "long_run_launch_required": bool_value(gate.get("long_run_launch_required")),
        "harvest_validation_required": bool_value(
            gate.get("harvest_validation_required")
        ),
    }


def _quality_fields(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "quality_vector": state["quality"],
        "quality_delta_policy": public_quality_delta_policy(
            state["quality_delta_policy"]
        ),
        "previous_high_water_mark": state["prev_high"],
        "high_water_mark": state["high_water"],
        "coverage_quality_delta_gate": state["coverage_gate"],
        "coverage_quality_delta_reconciliation_gate": state[
            "coverage_reconciliation_gate"
        ],
        "substance_metrics": numeric_vector(state["current_substance"]),
        "substance_delta_gate": state["substance_gate"],
        "vacuous_corrective_gate": state["corrective_gate"],
    }


def _adapter_fields(state: dict[str, Any]) -> dict[str, Any]:
    adapter_gate = state["adapter_gate"]
    load_gate = state["adapter_load_gate"]
    return {
        "adapter_mandate_gate": adapter_gate,
        "adapter_mandate_required": bool_value(
            adapter_gate.get("adapter_mandate_required")
        ),
        "adapter_missing_streak": adapter_gate.get("adapter_missing_streak"),
        "adapter_contract_unmet": state["adapter_contract_unmet"],
        "adapter_wiring_gate": load_gate,
        "consumer_context_conformance": load_gate.get("consumer_context_conformance")
        or {},
        "adapter_wiring_defect": bool_value(load_gate.get("adapter_wiring_defect")),
        "adapter_loaded": state["domain_adapter"] is not None,
        "adapter_registered": state["adapter_registered"],
        "adapter_path": state["domain_adapter_path"] or state["adapter_expected_path"],
        "adapter_expected_path": state["adapter_expected_path"],
    }


def _chain_fields(state: dict[str, Any]) -> dict[str, Any]:
    chain_gate = state["chain_gate"]
    return {
        "cumulative_goal_distance_gate": chain_gate,
        "cumulative_goal_distance_scope_key": chain_gate.get(
            "cumulative_goal_distance_scope_key"
        ),
        "cumulative_goal_distance_stall_streak": chain_gate.get(
            "cumulative_goal_distance_stall_streak"
        ),
        "cumulative_goal_distance_stalled": bool_value(
            chain_gate.get("cumulative_goal_distance_stalled")
        ),
        "chain_stall_forced_retarget_gate": state["forced_retarget_gate"],
        "forced_selected_task": state["forced_selected_task"],
        "forced_selected_task_options": state["forced_task_options"],
        "high_water_vector": chain_gate.get("high_water_vector"),
        "high_water_last_improved_cycle": chain_gate.get(
            "high_water_last_improved_cycle"
        ),
    }


def _metric_and_source_fields(state: dict[str, Any]) -> dict[str, Any]:
    metric_gate = state["metric_validity_gate"]
    facet_map = state["facet_root_map"]
    return {
        **_acceptance_reachability_fields(state["reachability_gate"]),
        **_cycle_reachability_fields(state["cycle_reachability_gate"]),
        "oracle_metric_validity_gate": metric_gate,
        "metric_verifier_not_evaluated": bool_value(
            metric_gate.get("metric_verifier_not_evaluated")
        ),
        "repo_owned_source_roots": state["repo_owned_source_roots"],
        "repo_owned_source_roots_status": state["repo_owned_source_roots_status"],
        "repo_owned_source_roots_error": state["repo_owned_source_roots_error"],
        "facet_root_map_applied": bool(facet_map),
        "facet_root_map_missing": state["facet_root_map_missing"],
        "facet_root_map_size": len(facet_map),
        "raw_root_family_key": state["raw_root_family_key"],
    }


def _terminal_and_review_fields(state: dict[str, Any]) -> dict[str, Any]:
    resolution = state["terminal_self_resolution"]
    return {
        "terminal_outcome_key": state["current_terminal_outcome_key"],
        "terminal_outcome_family_key": state["terminal_family_key"],
        "terminal_outcome_family_source": state["terminal_family_source"],
        "terminal_outcome_family_fallback_applied": state["terminal_family_fallback"],
        "terminal_outcome_family_previous_count": previous_micro_hardening_count(
            state["registry_rows"], state["current_root_family_key"]
        ),
        "terminal_outcome_family_previous_cycle_id": (
            state["latest_terminal_family"] or {}
        ).get("cycle_id"),
        "terminal_self_resolution_gate": resolution,
        "offline_scope_unverified": bool_value(
            resolution.get("offline_scope_unverified")
        ),
        "goal_terminal_prohibited": bool_value(
            resolution.get("goal_terminal_prohibited")
        ),
        "advice_freshness_gate": state["advice_gate"],
        "partial_progress_axes_gate": state["partial_progress_gate"],
        "structure_metrics_gate": state["structure_gate"],
        "structure_high_water_key_scope": state["structure_gate"].get(
            "structure_high_water_key_scope"
        ),
        "structure_global_invariant_metrics": state["structure_gate"].get(
            "structure_global_invariant_metrics"
        )
        or {},
    }


def _gate_fields(state: dict[str, Any]) -> dict[str, Any]:
    return {
        **_quality_fields(state),
        **_adapter_fields(state),
        **_chain_fields(state),
        **_metric_and_source_fields(state),
        **_terminal_and_review_fields(state),
    }
