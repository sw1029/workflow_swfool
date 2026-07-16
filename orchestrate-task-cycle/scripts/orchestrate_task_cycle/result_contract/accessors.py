from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


# These fields use an empty container to state an observed zero/none result.
# Treating an explicit empty list/dict as missing forces callers to invent
# sentinel values such as ``["none"]``, which then become false blockers or
# evidence.  Fields that require substantive evidence intentionally stay out
# of this set.
EMPTY_CONTAINER_IS_VALUE = {
    "blockers",
    "changed_files",
    "changed_files_scanned",
    "commands",
    "changed_surfaces",
    "direction_recommendations",
    "direct_read_scope",
    "escalation_reasons",
    "findings",
    "artifacts",
    "blocker_taxonomy_delta",
    "delta_types",
    "issue_ids",
    "no_overclaim_flags",
    "oversize_files",
    "progress_axes",
    "planned_changed_files",
    "actual_changed_files",
    "rationale",
    "required_commands",
    "reused_prerequisites",
    "qualitative_findings",
    "reviewed_artifacts",
    "responsibility_clusters",
    "responsibility_split_plan",
    "routing_signals",
    "routing_signal_evidence",
    "routing_violations",
    "semantic_refactor_plan",
    "semantic_structure_findings",
    "surface_counts",
    "tracked_artifacts",
    "used_advice",
    "used_goal_truth",
}


def load_json(path_value: str | None) -> dict[str, Any]:
    if not path_value or path_value == "-":
        raw = sys.stdin.read()
        return json.loads(raw) if raw.strip() else {}
    stripped = path_value.strip()
    if stripped.startswith("{") or stripped.startswith("["):
        return json.loads(stripped)
    path = Path(path_value)
    try:
        if path.exists():
            raw = path.read_text(encoding="utf-8")
            return json.loads(raw) if raw.strip() else {}
    except OSError:
        pass
    return json.loads(stripped)


def deep_get(data: Any, path: str) -> Any:
    current = data
    for key in path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def has_value(data: dict[str, Any], field: str) -> bool:
    candidates = [
        field,
        f"result.{field}",
        f"validation.{field}",
        f"run.{field}",
        f"quality_review.{field}",
        f"qualitative_review.{field}",
        f"commit.{field}",
        f"derive.{field}",
        f"schema.{field}",
        f"issue.{field}",
        f"report.{field}",
        f"closeout_commit.{field}",
    ]
    aliases = {
        "evidence_paths": ["evidence_paths", "artifacts", "artifact_paths", "logs", "report_path"],
        "commands": ["commands", "validation_commands", "checks"],
        "blockers": ["blockers", "remaining_blockers", "blocking_findings"],
        "commit_status": ["commit_status", "status", "commit.status"],
        "commit_role": ["commit_role", "role", "commit.role"],
        "commit_subject": ["commit_subject", "subject", "commit.subject"],
        "tracked_artifacts": ["tracked_artifacts", "closeout_artifacts", "staged_files", "changed_files", "artifacts"],
        "execution_status": ["execution_status", "status", "run.status"],
        "audit_status": ["audit_status", "status", "structure_status", "code_structure_audit.audit_status", "code_structure_audit.status"],
        "changed_files_scanned": ["changed_files_scanned", "scanned_files", "code_structure_audit.changed_files_scanned"],
        "oversize_files": ["oversize_files", "oversized_files", "code_structure_audit.oversize_files"],
        "thresholds": ["thresholds", "code_structure_audit.thresholds"],
        "responsibility_clusters": ["responsibility_clusters", "clusters", "code_structure_audit.responsibility_clusters"],
        "semantic_structure_metrics": ["semantic_structure_metrics", "code_structure_audit.semantic_structure_metrics"],
        "semantic_structure_findings": ["semantic_structure_findings", "code_structure_audit.semantic_structure_findings"],
        "convention_conformance": ["convention_conformance", "code_structure_audit.convention_conformance"],
        "moduleization_required": ["moduleization_required", "refactor_required", "code_structure_audit.moduleization_required"],
        "suggested_module_root": ["suggested_module_root", "module_root", "code_structure_audit.suggested_module_root"],
        "responsibility_split_plan": ["responsibility_split_plan", "split_plan", "module_split_plan", "code_structure_audit.responsibility_split_plan"],
        "semantic_refactor_plan": ["semantic_refactor_plan", "code_structure_audit.semantic_refactor_plan"],
        "validation_set_status": ["validation_set_status", "status", "validation_set.status"],
        "validation_set_id": ["validation_set_id", "vset_id", "validation_set.id"],
        "not_gold": ["not_gold", "validation_set.not_gold"],
        "progress_axes": ["progress_axes", "validation.progress_axes", "progress.axes"],
        "pid_or_session": ["pid", "session_id", "job_id", "pid_or_session", "run.pid", "run.session_id", "run.job_id"],
        "run_id": ["run_id", "run.run_id", "execution.run_id", "monitor_result.run_id"],
        "owner_task_id": ["owner_task_id", "task_id", "run.owner_task_id", "monitor_result.owner_task_id"],
        "launch_cycle_id": ["launch_cycle_id", "cycle_id", "run.launch_cycle_id", "monitor_result.launch_cycle_id"],
        "workdir": ["workdir", "cwd", "working_directory", "run.workdir", "run.cwd"],
        "output_dir": ["output_dir", "run.output_dir", "execution.output_dir", "monitor_result.output_dir"],
        "expected_completion_signal": ["expected_completion_signal", "run.expected_completion_signal", "monitor_result.expected_completion_signal"],
        "expected_completion_artifacts": ["expected_completion_artifacts", "expected_completion_paths", "run.expected_completion_artifacts", "monitor_result.expected_completion_artifacts"],
        "used_advice": ["used_advice", "external_advice", "advice", "packet.used_advice", "routing_packet.used_advice", "result.used_advice"],
        "reviewer_routing": ["reviewer_routing", "reviewer_route", "reviewer_reasoning", "quality_review.reviewer_routing", "qualitative_review.reviewer_routing"],
        "agent_routing_applicability": ["agent_routing_applicability", "agent_routing.applicability", "routing.agent_routing_applicability"],
        "policy_id": ["policy_id", "agent_routing.policy_id", "routing.policy_id"],
        "profile_id": ["profile_id", "agent_routing.profile_id", "routing.profile_id"],
        "routing_tier": ["routing_tier", "agent_routing.routing_tier", "routing.routing_tier"],
        "requested_model_ref": ["requested_model_ref", "agent_routing.requested_model_ref", "routing.requested_model_ref", "routing.code_worker.requested_model_ref", "worker.requested_model_ref"],
        "requested_model": ["requested_model", "agent_routing.requested_model", "routing.requested_model"],
        "model_configuration_status": ["model_configuration_status", "agent_routing.model_configuration_status", "routing.model_configuration_status", "routing.code_worker.model_configuration_status", "worker.model_configuration_status"],
        "model_binding_receipt": ["model_binding_receipt", "agent_routing.model_binding_receipt", "routing.model_binding_receipt", "routing.code_worker.model_binding_receipt", "worker.model_binding_receipt"],
        "requested_reasoning_effort": ["requested_reasoning_effort", "agent_routing.requested_reasoning_effort", "routing.requested_reasoning_effort"],
        "routing_reason_codes": ["routing_reason_codes", "agent_routing.routing_reason_codes", "routing.routing_reason_codes"],
        "routing_signals": ["routing_signals", "agent_routing.routing_signals", "routing.routing_signals"],
        "routing_signal_evidence": ["routing_signal_evidence", "agent_routing.routing_signal_evidence", "routing.routing_signal_evidence"],
        "routing_violations": ["routing_violations", "agent_routing.routing_violations", "routing.routing_violations"],
        "final_direction_ownership": ["final_direction_ownership", "agent_routing.final_direction_ownership", "routing.final_direction_ownership"],
        "routing_enforcement": ["routing_enforcement", "agent_routing.routing_enforcement", "routing.routing_enforcement"],
        "actual_model": ["actual_model", "agent_routing.actual_model", "routing.actual_model"],
        "actual_reasoning_effort": ["actual_reasoning_effort", "agent_routing.actual_reasoning_effort", "routing.actual_reasoning_effort"],
        "routing_limitation": ["routing_limitation", "agent_routing.routing_limitation", "routing.routing_limitation"],
        "max_escalation_reason": ["max_escalation_reason", "agent_routing.max_escalation_reason", "routing.max_escalation_reason"],
        "prior_tier5_unresolved": ["prior_tier5_unresolved", "agent_routing.prior_tier5_unresolved", "routing.prior_tier5_unresolved"],
        "prior_tier5_evidence": ["prior_tier5_evidence", "agent_routing.prior_tier5_evidence", "routing.prior_tier5_evidence"],
        "agent_count": ["agent_count", "agent_routing.agent_count", "routing.agent_count", "review_agent_count"],
        "model_effort_routing": ["model_effort_routing", "routing_summary", "fields.모델/effort 라우팅"],
        "reviewed_artifacts": ["reviewed_artifacts", "reviewed_artifact_paths", "quality_review.reviewed_artifacts", "qualitative_review.reviewed_artifacts", "artifacts"],
        "direct_read_scope": ["direct_read_scope", "read_scope", "quality_review.direct_read_scope", "qualitative_review.direct_read_scope"],
        "qualitative_findings": ["qualitative_findings", "quality_review.qualitative_findings", "quality_review.findings", "qualitative_review.qualitative_findings", "qualitative_review.findings", "findings"],
        "direction_recommendations": ["direction_recommendations", "recommendations", "quality_review.direction_recommendations", "qualitative_review.direction_recommendations"],
        "blocker_taxonomy_delta": ["blocker_taxonomy_delta", "quality_review.blocker_taxonomy_delta", "qualitative_review.blocker_taxonomy_delta"],
        "semantic_ready": ["semantic_ready", "quality_review.semantic_ready", "qualitative_review.semantic_ready"],
        "progress_cap": ["progress_cap", "quality_review.progress_cap", "qualitative_review.progress_cap"],
        "no_overclaim_flags": ["no_overclaim_flags", "quality_review.no_overclaim_flags", "qualitative_review.no_overclaim_flags"],
        "selected_task_source": ["selected_task_source", "derive.selected_task_source", "result.selected_task_source"],
        "loop_breaker_disposition": ["loop_breaker_disposition", "derive.loop_breaker_disposition", "result.loop_breaker_disposition"],
        "progress_kind": ["progress_kind", "selected_progress_kind", "expected_progress_kind", "derive.progress_kind", "derive.selected_progress_kind", "result.progress_kind", "result.selected_progress_kind"],
        "semantic_signature": ["semantic_signature", "selected_semantic_signature", "derive.semantic_signature", "derive.selected_semantic_signature", "result.semantic_signature", "result.selected_semantic_signature", "terminal_blocker.semantic_signature"],
        "goal_distance_gate": ["goal_distance_gate", "loop_breaker_packet.goal_distance_gate", "packet.goal_distance_gate", "result.goal_distance_gate"],
        "task_pack_status": ["task_pack_status", "derive.task_pack_status", "result.task_pack_status", "task_pack.status", "task_pack_packet.status"],
        "task_pack_path": ["task_pack_path", "derive.task_pack_path", "result.task_pack_path", "task_pack.path", "task_pack_packet.path"],
        "task_pack_item_id": ["task_pack_item_id", "promoted_item_id", "derive.task_pack_item_id", "derive.promoted_item_id", "result.task_pack_item_id", "result.promoted_item_id", "task_pack.item_id", "task_pack_packet.current_item_id"],
        "pack_disposition": ["pack_disposition", "derive.pack_disposition", "result.pack_disposition", "task_pack_packet.pack_disposition", "task_pack.disposition"],
        "pack_mutation_plan": ["pack_mutation_plan", "derive.pack_mutation_plan", "result.pack_mutation_plan", "task_pack_packet.pack_mutation_plan"],
        "pack_mutation_log": ["pack_mutation_log", "mutation_log", "task_pack.mutation_log", "task_pack_packet.mutation_log", "result.pack_mutation_log"],
        "task_pack_render_path": ["task_pack_render_path", "render_path", "task_pack.render_path", "task_pack_packet.render_path", "result.task_pack_render_path"],
        "skipped_item_ids": ["skipped_item_ids", "exclude_item_ids", "pack_mutation_plan.skipped_item_ids", "pack_mutation_plan.item_ids", "result.skipped_item_ids"],
        "derive_standalone_rationale": ["derive_standalone_rationale", "pack_bypass_rationale", "result.derive_standalone_rationale"],
        "terminal_blocker": ["terminal_blocker", "derive.terminal_blocker", "result.terminal_blocker", "task_pack.terminal_blocker"],
        "output_delta_status": ["output_delta_status", "output_delta.output_delta_status", "output_delta_gate.output_delta_status", "quality_review.output_delta_status", "qualitative_review.output_delta_status", "result.output_delta.output_delta_status"],
        "produced_domain_delta": ["produced_domain_delta", "output_delta.produced_domain_delta", "output_delta_gate.produced_domain_delta", "quality_review.produced_domain_delta", "qualitative_review.produced_domain_delta", "result.output_delta.produced_domain_delta"],
        "metadata_only": ["metadata_only", "output_delta.metadata_only", "output_delta_gate.metadata_only", "quality_review.metadata_only", "qualitative_review.metadata_only", "result.output_delta.metadata_only"],
        "effective_progress_kind": ["effective_progress_kind", "output_delta.effective_progress_kind", "output_delta_gate.effective_progress_kind", "quality_review.effective_progress_kind", "qualitative_review.effective_progress_kind", "result.output_delta.effective_progress_kind"],
        "root_cause_attempted_for_family": ["root_cause_attempted_for_family", "terminal_blocker.root_cause_attempted_for_family", "loop_breaker_packet.root_cause_attempted_for_family", "result.root_cause_attempted_for_family"],
        "authorized_alternative_path": ["authorized_alternative_path", "terminal_blocker.authorized_alternative_path", "sealing_direction_guard.authorized_alternative_path", "result.terminal_blocker.authorized_alternative_path"],
        "alternative_in_gt_allowed": ["alternative_in_gt_allowed", "terminal_blocker.alternative_in_gt_allowed", "sealing_direction_guard.alternative_in_gt_allowed", "result.terminal_blocker.alternative_in_gt_allowed"],
        "gt_allowed_alternative_attempted": ["gt_allowed_alternative_attempted", "terminal_blocker.gt_allowed_alternative_attempted", "sealing_direction_guard.gt_allowed_alternative_attempted", "result.terminal_blocker.gt_allowed_alternative_attempted"],
        "gt_allowed_alternative_evidence_paths": ["gt_allowed_alternative_evidence_paths", "terminal_blocker.gt_allowed_alternative_evidence_paths", "sealing_direction_guard.gt_allowed_alternative_evidence_paths", "result.terminal_blocker.gt_allowed_alternative_evidence_paths"],
        "autonomous_retarget_disabled": ["autonomous_retarget_disabled", "root_axis_gate.autonomous_retarget_disabled", "loop_breaker_packet.root_axis_gate.autonomous_retarget_disabled", "result.root_axis_gate.autonomous_retarget_disabled"],
    }
    for alias in aliases.get(field, [field]):
        candidates.append(alias)
    for candidate in candidates:
        value = deep_get(data, candidate) if "." in candidate else data.get(candidate)
        if value is None:
            continue
        if isinstance(value, (list, dict)) and not value:
            if field in EMPTY_CONTAINER_IS_VALUE:
                return True
            continue
        if isinstance(value, str) and not value.strip():
            continue
        return True
    return False


def value_for(data: dict[str, Any], field: str) -> Any:
    for candidate in (
        field,
        f"result.{field}",
        f"run.{field}",
        f"quality_review.{field}",
        f"qualitative_review.{field}",
        f"validation.{field}",
        f"commit.{field}",
        f"closeout_commit.{field}",
    ):
        value = deep_get(data, candidate) if "." in candidate else data.get(candidate)
        if value is not None:
            return value
    return None


def positive_count(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value > 0
    if isinstance(value, str):
        stripped = value.strip()
        return stripped.isdigit() and int(stripped) > 0
    return False


def boolish(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "1", "required", "block", "blocked"}
    if isinstance(value, (list, dict)):
        return bool(value)
    return False


def non_empty(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def nonzero_scalar(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return False
        try:
            return float(stripped) != 0
        except ValueError:
            return stripped.lower() in {"true", "fail", "failed", "block", "blocked"}
    if isinstance(value, dict):
        return any(nonzero_scalar(item) for item in value.values())
    if isinstance(value, list):
        return any(nonzero_scalar(item) for item in value)
    return False


def number_value(value: Any) -> int | None:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def float_value(value: Any) -> float | None:
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def first_present(data: dict[str, Any], aliases: list[str]) -> Any:
    for alias in aliases:
        value = deep_get(data, alias) if "." in alias else data.get(alias)
        if value is None:
            continue
        if isinstance(value, (list, dict)) and not value:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        return value
    return None


def list_values(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if item is not None and str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def recursive_key_present(value: Any, keys: set[str]) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            if key in keys and non_empty(item):
                return True
            if recursive_key_present(item, keys):
                return True
    if isinstance(value, list):
        return any(recursive_key_present(item, keys) for item in value)
    return False


def command_summary_omitted(value: Any, command_context: bool = False) -> bool:
    command_keys = {"command", "cmd", "command_line", "command_summary", "commands"}
    if isinstance(value, dict):
        for key, item in value.items():
            next_context = command_context or key in command_keys or "command" in key
            if command_summary_omitted(item, next_context):
                return True
    if isinstance(value, list):
        return any(command_summary_omitted(item, command_context) for item in value)
    if isinstance(value, str):
        return command_context and "..." in value
    return False
