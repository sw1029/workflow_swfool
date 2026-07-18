from __future__ import annotations

import json
from typing import Any

from .accessors import deep_get, has_value, list_values


def normalize_task_kind(value: Any) -> str:
    return "".join(
        ch if ch.isalnum() or ch == "_" else "_"
        for ch in str(value or "").strip().lower().replace("-", "_")
    ).strip("_")


def selected_task_kind_value(result: dict[str, Any]) -> str:
    for alias in (
        "selected_task_kind",
        "task_kind",
        "selected_task.kind",
        "selected_task.task_kind",
        "derive.selected_task_kind",
        "derive.task_kind",
        "result.selected_task_kind",
        "result.task_kind",
    ):
        value = deep_get(result, alias) if "." in alias else result.get(alias)
        kind = normalize_task_kind(value)
        if kind:
            return kind
    return ""


def allowed_task_kinds_from_basis(value: Any) -> set[str]:
    allowed: set[str] = set()
    if isinstance(value, str) and value.strip():
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return allowed
    if not isinstance(value, dict):
        return allowed
    for gate in value.values():
        if not isinstance(gate, dict):
            continue
        for key in ("allowed_task_kinds", "goal_productive_task_kinds", "required_task_kinds"):
            for item in list_values(gate.get(key)):
                kind = normalize_task_kind(item)
                if kind:
                    allowed.add(kind)
    return allowed


INSTRUMENTATION_TASK_KINDS = {
    "instrumentation_supply",
    "diagnostic_instrumentation",
    "diagnostics_supply",
    "post_failure_diagnostics",
    "adapter_instrumentation",
    "measurement_instrumentation",
}

CLASSIFICATION_REPAIR_TASK_KINDS = {
    "terminal_classification_stage_repair",
    "classification_stage_repair",
    "failure_surface_stage_repair",
    "input_contract_repair",
    "same_input_contract_repair",
}

ENVELOPE_THAW_TASK_KINDS = {"envelope_thaw_item", "constraint_relaxation", "verifier_contract_supply"}
SCENARIO_SUPPLY_TASK_KINDS = {
    "validation_set_plan",
    "validation_set_build",
    "scenario_fixture_supply",
    "fixture_supply",
    "live_run_supply",
    "acceptance_scenario_supply",
    "test_scenario_supply",
}
SCENARIO_REPAIR_TASK_KINDS = {
    "acceptance_inversion_repair",
    "code_contract_repair",
    "implementation_contract_repair",
    "acceptance_contract_repair",
    "test_contract_repair",
}
COMMAND_PROVENANCE_TASK_KINDS = {
    "command_provenance_repair",
    "rerun_with_full_argv",
    "run_reproduction_repair",
    "execution_log_repair",
}
BLOCKER_CONTRACT_REPAIR_TASK_KINDS = {
    "blocker_contract_repair",
    "gate_contract_repair",
    "gate_blocker_repair",
    "authorization_contract_repair",
}
STOCHASTIC_CONTRACT_TASK_KINDS = {
    "stochastic_contract_revision",
    "acceptance_contract_revision",
    "envelope_expansion",
    "residual_descope",
    "user_escalation",
    "terminal_blocked",
}
EXPECTATION_REBASELINE_TASK_KINDS = {
    "expectation_rebaseline",
    "expectation_anchor_supply",
    "expectation_lineage_repair",
    "baseline_rebind",
    "residual_descope",
    "user_escalation",
    "terminal_blocked",
}
PARITY_AXIS_TASK_KINDS = {
    "parity_axis_resolution",
    "comparison_parity_repair",
    "provisional_comparison",
    "residual_descope",
    "user_escalation",
    "terminal_blocked",
}
ADOPTION_AXIS_TASK_KINDS = {
    "adoption_axis_classification",
    "gating_axis_repair",
    "adoption_contract_revision",
    "measured_but_disqualified_preservation",
    "candidate_rejection",
    "residual_descope",
    "user_escalation",
    "terminal_blocked",
}
RESOLUTION_REPAIR_TASK_KINDS = {
    "resolution_restoration",
    "evidence_resolution_repair",
    "contract_resolution_revision",
    "acceptance_contract_revision",
    "residual_descope",
    "user_escalation",
    "terminal_blocked",
}
REPORT_KEY_REPAIR_TASK_KINDS = {
    "report_key_repair",
    "report_schema_repair",
    "report_sync_repair",
    "schema_single_source_repair",
    "user_escalation",
    "terminal_blocked",
}
CURRENT_LANE_TASK_KINDS = {
    "current_lane_rerun",
    "current_lane_revalidation",
    "fresh_current_lane_run",
    "lane_revalidation",
    "revalidation",
    "residual_descope",
    "descope_with_residual",
    "user_escalation",
    "terminal_blocked",
    "terminal_blocker",
}
DECISION_FRESHNESS_TASK_KINDS = {
    "consumer_refresh",
    "deliverable_refresh",
    "fresh_current_lane_measurement",
    "fresh_measurement",
    "fresh_producer_execution",
    "measurement_rerun",
    "producer_execution",
    "producer_refresh",
    "rerun_with_current_contract",
    "no_impact_proof",
    "upstream_contract_no_impact_proof",
    "decision_metadata_revision",
    "residual_descope",
    "descope_with_residual",
    "user_escalation",
    "terminal_blocked",
    "terminal_blocker",
}
PRODUCER_SUPPLY_TASK_KINDS = {
    "producer_supply",
    "producer_path_supply",
    "production_code_path_supply",
    "gating_axis_producer_supply",
    "producer_repair",
    "field_producer_repair",
    "gating_axis_repair",
    "residual_descope",
    "descope_with_residual",
    "user_escalation",
    "terminal_blocked",
    "terminal_blocker",
}
EXECUTION_PRODUCING_TASK_KINDS = {
    "fresh_producer_execution",
    "producer_execution",
    "producer_run",
    "implementation_execution",
    "instrumentation_exercise",
    "live_run",
    "live_run_supply",
    "fresh_current_lane_run",
    "current_lane_rerun",
    "long_run_launch",
}
PRODUCER_RECONCILIATION_TASK_KINDS = {
    "producer_input_reconciliation",
    "producer_revision_reconciliation",
    "producer_receipt_reconciliation",
    "producer_authority_reconciliation",
    "producer_safety_reconciliation",
}
_TERMINAL_TASK_KINDS = {
    "user_escalation",
    "terminal_blocked",
    "terminal_blocker",
}
EXECUTION_STARVATION_TASK_KINDS = (
    PRODUCER_SUPPLY_TASK_KINDS
    | EXECUTION_PRODUCING_TASK_KINDS
    | PRODUCER_RECONCILIATION_TASK_KINDS
) - _TERMINAL_TASK_KINDS
PORTFOLIO_QUOTA_TASK_KINDS = {
    "producer_supply",
    "producer_repair",
    "envelope_expansion",
    "envelope_thaw_item",
    "long_run_launch",
    "long_run_monitor",
    "long_run_harvest",
    "long_run_finalize",
    "throughput_improvement",
    "residual_descope",
    "descope_with_residual",
    "user_escalation",
    "terminal_blocked",
    "terminal_blocker",
}
CYCLE_REACHABILITY_TASK_KINDS = {
    "long_run_launch",
    "long_run_monitor",
    "long_run_harvest",
    "long_run_finalize",
    "throughput_improvement",
    "residual_descope",
    "descope_with_residual",
    "user_escalation",
    "terminal_blocked",
    "terminal_blocker",
}
METRIC_BASIS_TASK_KINDS = {
    "basis_compatible_measurement",
    "metric_basis_repair",
    "basis_contract_repair",
    "basis_downgrade_contract",
    "contract_basis_revision",
    "residual_descope",
    "descope_with_residual",
    "user_escalation",
    "terminal_blocked",
    "terminal_blocker",
}
SURFACE_FIELD_TASK_KINDS = {
    "surface_field_repair",
    "field_class_repair",
    "producer_field_repair",
    "producer_repair",
    "qualitative_review_repair",
    "residual_descope",
    "descope_with_residual",
    "user_escalation",
    "terminal_blocked",
    "terminal_blocker",
}
HARVEST_GATE_TASK_KINDS = {
    "harvest_gate_repair",
    "harvest_gate_mitigation",
    "harvest_contract_repair",
    "launch_manifest_repair",
    "harvest_anchor_repair",
    "harvest_scale_repair",
    "harvest_contract_mitigation",
    "residual_descope",
    "descope_with_residual",
    "user_escalation",
    "terminal_blocked",
    "terminal_blocker",
}
REHARVEST_TASK_KINDS = {
    "quarantine_artifact",
    "artifact_quarantine",
    "terminal_artifact_quarantine",
    "reharvest",
    "reharvest_preserved_artifact",
    "reharvest_path_supply",
    "verifier_repair_then_reharvest",
    "governance_metadata_repair",
    "verifier_defect_repair",
    "gate_repair_then_reharvest",
    "residual_descope",
    "descope_with_residual",
    "user_escalation",
    "terminal_blocked",
    "terminal_blocker",
}
CONTRACT_SATISFIABILITY_TASK_KINDS = {
    "predicate_directive_reconciliation",
    "predicate_directive_repair",
    "predicate_revision",
    "producer_directive_revision",
    "validation_predicate_repair",
    "producer_contract_repair",
    "contract_satisfiability_repair",
    "same_task_contract_repair",
    "residual_descope",
    "descope_with_residual",
    "user_escalation",
    "terminal_blocked",
    "terminal_blocker",
}
COLLECTION_CONSUMPTION_TASK_KINDS = {
    "full_collection_supply",
    "untruncated_collection_supply",
    "collection_contract_revision",
    "sample_only_contract_revision",
    "sample_consistency_contract",
    "closed_world_collection_repair",
    "collection_consumer_repair",
    "residual_descope",
    "descope_with_residual",
    "user_escalation",
    "terminal_blocked",
    "terminal_blocker",
}


def forced_task_kind(result: dict[str, Any]) -> str:
    for alias in (
        "forced_selected_task.selected_task_kind",
        "forced_selected_task.task_kind",
        "anti_loop_progress_gate.forced_selected_task.selected_task_kind",
        "anti_loop_progress_gate.forced_selected_task.task_kind",
        "result.anti_loop_progress_gate.forced_selected_task.selected_task_kind",
        "result.anti_loop_progress_gate.forced_selected_task.task_kind",
    ):
        kind = normalize_task_kind(deep_get(result, alias))
        if kind:
            return kind
    return ""


def selected_disposition(result: dict[str, Any], selected_source: str, progress_kind: str) -> str:
    if selected_source == "terminal_blocked" or has_value(result, "terminal_blocker"):
        return "terminal_blocked"
    for alias in (
        "selected_disposition",
        "disposition",
        "progress_target",
        "selected_task_kind",
        "loop_breaker_disposition.status",
        "derive.selected_disposition",
        "result.selected_disposition",
    ):
        value = str(deep_get(result, alias) if "." in alias else result.get(alias) or "").strip().lower()
        if value in {"goal_productive", "consolidation", "terminal_blocked", "user_escalation"}:
            return value
        if "consolidation" in value:
            return "consolidation"
        if "goal_productive" in value:
            return "goal_productive"
        if "terminal" in value:
            return "terminal_blocked"
        if "user_escalation" in value or "user-escalation" in value:
            return "user_escalation"
    if progress_kind == "goal_productive":
        return "goal_productive"
    return progress_kind
