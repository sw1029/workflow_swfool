#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


TARGETS = {
    "governance",
    "validation_set_plan",
    "code_structure_audit",
    "run",
    "qualitative_review",
    "loopback_audit",
    "validation_set_build",
    "schema_pre_derive",
    "derive",
    "schema_post_derive",
    "index",
    "validate",
    "issue",
    "commit",
    "report",
    "closeout_commit",
}

CANONICAL_LEDGER_STEPS = {
    "context",
    "ledger_init",
    "authority",
    "acceptance",
    "route_plan",
    "validation_set_plan",
    "governance",
    "result_contract",
    "ledger_append",
    "code_structure_audit",
    "run",
    "qualitative_review",
    "loopback_audit",
    "validation_set_build",
    "schema_pre_derive",
    "visible_increment",
    "derive",
    "schema_post_derive",
    "index",
    "validate",
    "issue",
    "commit",
    "dashboard",
    "report",
    "closeout_commit",
}

COMMON_FIELDS = {
    "governance": ["task_id", "changed_files", "evidence_paths"],
    "validation_set_plan": ["task_id", "validation_set_need", "task_family", "oracle_strategy", "split_strategy", "evidence_paths"],
    "code_structure_audit": [
        "task_id",
        "audit_status",
        "thresholds",
        "semantic_structure_metrics",
        "semantic_structure_findings",
        "convention_conformance",
        "moduleization_required",
        "semantic_refactor_plan",
        "evidence_paths",
    ],
    "run": ["task_id", "execution_status", "evidence_paths"],
    "qualitative_review": [
        "task_id",
        "review_agent_count",
        "reviewer_routing",
        "review_status",
        "quality_verdict",
        "reviewed_artifacts",
        "direct_read_scope",
        "qualitative_findings",
        "direction_recommendations",
        "output_delta_status",
        "changed_vs_previous",
        "semantic_progress",
        "produced_domain_delta",
        "metadata_only",
        "effective_progress_kind",
        "progress_cap",
        "blocker_taxonomy_delta",
        "no_overclaim_flags",
        "evidence_paths",
    ],
    "loopback_audit": [
        "task_id",
        "cycle_id",
        "family_key",
        "changed_vs_previous",
        "semantic_progress",
        "same_family_micro_hardening_count",
        "recommended_disposition",
        "hard_stop_required",
        "evidence_class",
        "evidence_paths",
    ],
    "validation_set_build": [
        "task_id",
        "validation_set_id",
        "validation_set_status",
        "quality_tier",
        "not_gold",
        "item_count",
        "oracle_manifest_path",
        "split_manifest_path",
        "leakage_report_path",
        "validation_set_root_path",
        "evidence_paths",
    ],
    "schema_pre_derive": ["task_id", "schema_status", "evidence_paths"],
    "derive": ["completed_task_id", "selected_task_source", "loop_breaker_disposition", "progress_kind", "semantic_signature", "evidence_paths"],
    "schema_post_derive": ["next_task_id", "schema_status", "evidence_paths"],
    "index": ["task_id", "index_status", "evidence_paths"],
    "validate": ["task_id", "validation_verdict", "progress_verdict", "blockers", "evidence_paths"],
    "issue": ["task_id", "issue_status", "blockers", "evidence_paths"],
    "commit": ["commit_role", "commit_status", "evidence_paths"],
    "report": [
        "used_goal_truth",
        "used_advice",
        "task_id",
        "changed_files",
        "commands",
        "validation_verdict",
        "progress_verdict",
        "blockers",
        "progress_axes",
        "next_task_id",
        "completion_status",
    ],
    "closeout_commit": ["commit_role", "commit_status", "tracked_artifacts", "evidence_paths"],
}

RUNNING_FIELDS = ["pid_or_session", "log_path", "startup_or_heartbeat_evidence", "monitor_command", "stop_command", "remaining_validation"]
LONG_RUN_REQUIRED_FIELDS = [
    "run_id",
    "owner_task_id",
    "launch_cycle_id",
    "command_argv",
    "workdir",
    "output_dir",
    "log_path",
    "startup_or_heartbeat_evidence",
    "monitor_command",
    "stop_command",
    "remaining_validation",
    "expected_completion_signal",
    "expected_completion_artifacts",
]
LONG_RUN_ROLES = {"launch", "monitor", "harvest", "finalize"}
LONG_RUN_STATUSES = {"launching", "running", "completed_pending_validation", "stale", "not_running", "failed", "success"}
ADVICE_REQUIRED_TARGETS = {"governance", "validation_set_plan", "qualitative_review", "validation_set_build", "derive", "validate"}
PACK_DISPOSITIONS = {
    "create_pack",
    "promote_next_item",
    "insert_items",
    "insert_item",
    "reorder_items",
    "skip_items",
    "exclude_items",
    "supersede_pack",
    "derive_standalone",
    "terminal_blocked",
}
PACK_MUTATION_DISPOSITIONS = {"create_pack", "insert_items", "insert_item", "reorder_items", "skip_items", "exclude_items", "supersede_pack", "terminal_blocked"}


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


REPORT_CONTEXT_KEYS = {
    "report",
    "quality_report",
    "validation_report",
    "result_report",
    "report_payload",
    "report_artifact",
    "artifact_report",
    "summary_report",
}

REPORT_DUPLICATE_KEY_EXCLUSIONS = {
    "id",
    "path",
    "status",
    "step",
    "target",
    "mode",
    "severity",
    "code",
    "message",
    "reason",
    "created_at",
    "updated_at",
    "timestamp",
    "evidence_path",
    "evidence_paths",
}


def report_integrity_required(data: dict[str, Any]) -> bool:
    return boolish(
        first_present(
            data,
            [
                "report_key_integrity_required",
                "report_key_integrity_gate.required",
                "report_key_integrity_gate.scan_duplicate_terminal_keys",
                "result.report_key_integrity_gate.required",
            ],
        )
    )


def is_report_context_key(key: str) -> bool:
    normalized = key.strip().lower()
    return normalized in REPORT_CONTEXT_KEYS or normalized.endswith("_report")


def collect_report_roots(value: Any, path: str = "$", key: str = "") -> list[tuple[str, Any]]:
    roots: list[tuple[str, Any]] = []
    if isinstance(value, dict):
        if key and is_report_context_key(key):
            roots.append((path, value))
            return roots
        for child_key, child in value.items():
            child_path = f"{path}.{child_key}"
            roots.extend(collect_report_roots(child, child_path, str(child_key)))
    elif isinstance(value, list):
        for idx, child in enumerate(value):
            roots.extend(collect_report_roots(child, f"{path}[{idx}]", key))
    return roots


def collect_terminal_key_values(value: Any, path: str = "$") -> dict[str, list[tuple[str, str, Any]]]:
    values: dict[str, list[tuple[str, str, Any]]] = {}
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if isinstance(child, (dict, list)):
                child_values = collect_terminal_key_values(child, child_path)
                for child_key, child_entries in child_values.items():
                    values.setdefault(child_key, []).extend(child_entries)
                continue
            key_text = str(key)
            if key_text.lower() in REPORT_DUPLICATE_KEY_EXCLUSIONS:
                continue
            try:
                encoded = json.dumps(child, sort_keys=True, ensure_ascii=False)
            except TypeError:
                encoded = repr(child)
            values.setdefault(key_text, []).append((child_path, encoded, child))
    elif isinstance(value, list):
        for idx, child in enumerate(value):
            child_values = collect_terminal_key_values(child, f"{path}[{idx}]")
            for child_key, child_entries in child_values.items():
                values.setdefault(child_key, []).extend(child_entries)
    return values


def report_key_divergences(data: dict[str, Any]) -> list[dict[str, Any]]:
    roots = collect_report_roots(data)
    if report_integrity_required(data) and not roots:
        roots = [("$", data)]
    divergences: list[dict[str, Any]] = []
    for root_path, root in roots:
        terminal_values = collect_terminal_key_values(root, root_path)
        for key, entries in terminal_values.items():
            unique_values = {encoded for _, encoded, _ in entries}
            if len(entries) < 2 or len(unique_values) <= 1:
                continue
            divergences.append(
                {
                    "root_path": root_path,
                    "terminal_key": key,
                    "paths": [path for path, _, _ in entries],
                    "values": [value for _, _, value in entries],
                }
            )
    return divergences


def report_key_duplicate_matches(data: dict[str, Any]) -> list[dict[str, Any]]:
    roots = collect_report_roots(data)
    if report_integrity_required(data) and not roots:
        roots = [("$", data)]
    duplicates: list[dict[str, Any]] = []
    for root_path, root in roots:
        terminal_values = collect_terminal_key_values(root, root_path)
        for key, entries in terminal_values.items():
            unique_values = {encoded for _, encoded, _ in entries}
            if len(entries) < 2 or len(unique_values) != 1:
                continue
            duplicates.append(
                {
                    "root_path": root_path,
                    "terminal_key": key,
                    "paths": [path for path, _, _ in entries],
                    "value": entries[0][2],
                    "duplicate_count": len(entries),
                }
            )
    return duplicates


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
    "fresh_current_lane_measurement",
    "fresh_measurement",
    "measurement_rerun",
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


def active_advice_present(data: dict[str, Any]) -> bool:
    candidates = [
        "active_advice_count",
        "external_advice_active",
        "context_counts.external_advice_active",
        "external_advice.active_count",
        "context.external_advice.active_count",
        "packet.context_counts.external_advice_active",
    ]
    if has_value(data, "used_advice"):
        return True
    for candidate in candidates:
        value = deep_get(data, candidate) if "." in candidate else data.get(candidate)
        if positive_count(value):
            return True
    for candidate in ("active_advice", "external_advice.active_files", "context.external_advice.active_files"):
        value = deep_get(data, candidate) if "." in candidate else data.get(candidate)
        if isinstance(value, list) and value:
            return True
    return False


def active_task_pack_present(data: dict[str, Any]) -> bool:
    candidates = [
        "task_pack_active",
        "context_counts.task_pack_active",
        "packet.context_counts.task_pack_active",
        "task_pack_packet",
        "packet.task_pack_packet",
    ]
    for candidate in candidates:
        value = deep_get(data, candidate) if "." in candidate else data.get(candidate)
        if positive_count(value) or (isinstance(value, dict) and value):
            return True
    return False


def task_pack_path_present(data: dict[str, Any]) -> bool:
    fields = ["changed_files", "artifacts", "artifact_paths", "evidence_paths", "report_paths", "tracked_artifacts"]
    for field in fields:
        value = deep_get(data, field) if "." in field else data.get(field)
        values = value if isinstance(value, list) else [value]
        for item in values:
            if isinstance(item, str) and ".task/task_pack/" in item:
                return True
    return False


def task_pack_in_scope(data: dict[str, Any]) -> bool:
    selected_source = str(value_for(data, "selected_task_source") or "").lower()
    return selected_source == "task_pack" or active_task_pack_present(data) or task_pack_path_present(data) or has_value(data, "task_pack_status")


def advice_handling_rationale_present(data: dict[str, Any]) -> bool:
    fields = [
        "advice_deferred_reason",
        "advice_rejected_reason",
        "advice_not_applicable_reason",
        "advice_handling_rationale",
        "external_advice_rationale",
        "used_advice_rationale",
        "advice_usage_deferred_reason",
    ]
    for field in fields:
        if has_value(data, field):
            return True
    return False


def add(findings: list[dict[str, Any]], severity: str, code: str, message: str, evidence: Any = None) -> None:
    item: dict[str, Any] = {"severity": severity, "code": code, "message": message}
    if evidence is not None:
        item["evidence"] = evidence
    findings.append(item)


def validate(target: str, result: dict[str, Any], mode: str) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    missing = [field for field in COMMON_FIELDS[target] if not has_value(result, field)]
    severity = "block" if mode == "block" or target == "report" else "warn"
    for field in missing:
        add(findings, severity, "missing_required_field", f"`{target}` result is missing `{field}`.", {"field": field})

    def require_context_field(field: str, code: str, message: str) -> None:
        if has_value(result, field):
            return
        if field not in missing:
            missing.append(field)
        add(findings, "block" if mode == "block" or target == "report" else "warn", code, message, {"field": field})

    raw_step = result.get("step")
    step = str(raw_step).strip() if raw_step is not None else ""
    if not step:
        if "step" not in missing:
            missing.append("step")
        add(
            findings,
            "block" if mode == "block" else "warn",
            "ledger_step_missing",
            f"`{target}` result lacks top-level canonical `step`; direct ledger append must pass `--step {target}` or use an event envelope.",
            {"expected_step": target},
        )
    elif step not in CANONICAL_LEDGER_STEPS:
        add(
            findings,
            "block" if mode == "block" else "warn",
            "ledger_step_noncanonical",
            f"`{target}` result has noncanonical ledger `step`.",
            {"step": step, "expected_step": target},
        )
    elif step != target:
        add(
            findings,
            "block" if mode == "block" else "warn",
            "ledger_step_mismatch",
            f"`{target}` result has `step: {step}`; expected `step: {target}` for direct ledger append.",
            {"step": step, "expected_step": target},
        )

    if target in ADVICE_REQUIRED_TARGETS and active_advice_present(result) and not has_value(result, "used_advice"):
        if not advice_handling_rationale_present(result):
            add(
                findings,
                "block",
                "active_advice_unhandled",
                f"`{target}` result has active external advice in scope but lacks `used_advice` or an explicit advice defer/reject/not-applicable rationale.",
                {"required": ["used_advice", "advice_deferred_reason|advice_rejected_reason|advice_not_applicable_reason|advice_handling_rationale"]},
            )

    explicit_report_key_divergence = boolish(
        first_present(
            result,
            [
                "report_key_divergence",
                "report_key_integrity_gate.report_key_divergence",
                "validation.report_key_integrity_gate.report_key_divergence",
                "result.report_key_integrity_gate.report_key_divergence",
            ],
        )
    )
    auto_report_key_divergences = report_key_divergences(result)
    auto_report_key_duplicate_matches = report_key_duplicate_matches(result)
    if explicit_report_key_divergence or auto_report_key_divergences:
        report_key_severity = "block" if mode == "block" or target in {"validate", "report"} else "warn"
        add(
            findings,
            report_key_severity,
            "report_key_divergence",
            "`report_key_divergence` means one report contains duplicate terminal keys with divergent values; pass/close/adoption/baseline/comparison consumption is invalid until the report is repaired.",
            {"auto_detected": auto_report_key_divergences[:20], "explicit_report_key_divergence": explicit_report_key_divergence},
        )
    if auto_report_key_duplicate_matches:
        add(
            findings,
            "warn",
            "report_key_duplicate_schema_debt",
            "Matching duplicate terminal report keys are schema debt; consumption may continue, but the report should be normalized to one authoritative copy.",
            {"auto_detected": auto_report_key_duplicate_matches[:20]},
        )

    if target == "code_structure_audit":
        audit_status = str(value_for(result, "audit_status") or value_for(result, "status") or "").lower()
        if audit_status and audit_status not in {"pass", "warn", "refactor_required", "blocked", "not_applicable"}:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "code_structure_audit_status_invalid",
                "`code_structure_audit` audit_status should be pass, warn, refactor_required, blocked, or not_applicable.",
                {"audit_status": audit_status},
            )
        moduleization_required = boolish(value_for(result, "moduleization_required"))
        split_plan = list_values(value_for(result, "responsibility_split_plan"))
        existing_debt_exemptions = list_values(
            first_present(
                result,
                [
                    "existing_debt_exemptions",
                    "existing_debt_exemption",
                    "code_structure_audit.existing_debt_exemptions",
                ],
            )
        )
        if moduleization_required and not split_plan and not existing_debt_exemptions:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "moduleization_required_without_split_plan",
                "`code_structure_audit` with moduleization_required=true requires a responsibility_split_plan or existing-debt exemption.",
            )
        raw_source_persisted = boolish(
            first_present(
                result,
                [
                    "raw_source_persisted",
                    "source_body_persisted",
                    "code_structure_audit.raw_source_persisted",
                    "code_structure_audit.source_body_persisted",
                ],
            )
        )
        forbidden_raw_source_persisted = first_present(
            result,
            [
                "forbidden_raw_source_persisted",
                "code_structure_audit.forbidden_raw_source_persisted",
            ],
        )
        if raw_source_persisted or forbidden_raw_source_persisted is False:
            add(
                findings,
                "block",
                "raw_source_persisted",
                "`code_structure_audit` must not persist raw source bodies; emit scalar metrics and symbol names only.",
            )

    execution_status = str(value_for(result, "execution_status") or value_for(result, "status") or "").lower()
    if target == "run" and execution_status == "running":
        missing_running = [field for field in RUNNING_FIELDS if not has_value(result, field)]
        for field in missing_running:
            add(findings, "block", "running_detail_missing", f"`running` execution requires `{field}`.", {"field": field})
    if target == "run":
        long_run_branch = boolish(first_present(result, ["long_run_branch", "run.long_run_branch", "monitor_result.long_run_branch"]))
        long_run_role = str(first_present(result, ["long_run_role", "run.long_run_role", "monitor_result.long_run_role"]) or "").lower()
        event_kind = str(first_present(result, ["event_kind", "run.event_kind", "monitor_result.event_kind"]) or "").lower()
        if long_run_branch:
            missing_long_run = [field for field in LONG_RUN_REQUIRED_FIELDS if not has_value(result, field)]
            for field in missing_long_run:
                add(findings, "block", "long_run_detail_missing", f"`long_run_branch=true` requires `{field}`.", {"field": field})
            if long_run_role not in LONG_RUN_ROLES:
                add(
                    findings,
                    "block",
                    "long_run_role_invalid",
                    "`long_run_branch=true` requires long_run_role launch|monitor|harvest|finalize.",
                    {"long_run_role": long_run_role or None},
                )
            if execution_status and execution_status not in LONG_RUN_STATUSES:
                add(
                    findings,
                    "block",
                    "long_run_execution_status_invalid",
                    "`long_run_branch=true` execution_status must be launching, running, completed_pending_validation, stale, not_running, failed, or success.",
                    {"execution_status": execution_status},
                )
            if event_kind and event_kind not in {"long_run_launch", "long_run_monitor", "long_run_harvest", "long_run_finalize"}:
                add(
                    findings,
                    "warn",
                    "long_run_event_kind_noncanonical",
                    "Long-running run events should use event_kind long_run_launch|long_run_monitor|long_run_harvest|long_run_finalize while keeping step=run.",
                    {"event_kind": event_kind},
                )
            if execution_status in {"running", "launching", "completed_pending_validation", "stale", "not_running"}:
                validation_verdict = str(value_for(result, "validation_verdict") or "").lower()
                progress_verdict = str(value_for(result, "progress_verdict") or "").lower()
                if validation_verdict in {"complete", "passed", "success"} or progress_verdict == "advanced":
                    add(
                        findings,
                        "block",
                        "long_run_incomplete_claimed_complete",
                        "Long-running launch/monitor/completed-pending-validation evidence cannot consume completion or advanced progress before harvest validation.",
                        {"execution_status": execution_status, "validation_verdict": validation_verdict or None, "progress_verdict": progress_verdict or None},
                    )
        live_execution = boolish(
            first_present(
                result,
                [
                    "live_execution",
                    "live_execution_required",
                    "live_run",
                    "run.live_execution",
                    "run.live_execution_required",
                ],
            )
        )
        if not live_execution:
            live_execution = execution_status not in {"", "not_applicable", "skipped", "blocked_no_execution", "no_execution"}
        command_argv = first_present(
            result,
            [
                "command_argv",
                "run.command_argv",
                "execution.command_argv",
                "command_provenance_gate.command_argv",
                "result.command_argv",
            ],
        )
        command_provenance_missing = boolish(
            first_present(
                result,
                [
                    "command_provenance_missing",
                    "command_provenance_gate.command_provenance_missing",
                    "run.command_provenance_missing",
                    "result.command_provenance_gate.command_provenance_missing",
                ],
            )
        )
        if live_execution and not non_empty(command_argv) and not command_provenance_missing:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "run_command_argv_or_missing_flag_required",
                "`run` must preserve full body-free command_argv for live execution, or explicitly set command_provenance_missing=true.",
            )
        if live_execution and command_summary_omitted(result) and not command_provenance_missing:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "run_command_summary_ellipsis_without_missing_provenance",
                "`run` command evidence contains an ellipsis or summarized command; set command_provenance_missing=true unless full argv is also preserved.",
            )
        blocker_reason_present = recursive_key_present(
            first_present(result, ["blockers", "blocking_findings", "run.blockers", "result.blockers"]) or result,
            {"reason_code", "blocker_reason_code", "blocker_reason"},
        )
        actionable_present = recursive_key_present(
            result,
            {"blocker_actionability", "violated_relation", "observed_values", "expected_relation", "minimum_input_delta"},
        )
        blocker_opacity = boolish(
            first_present(
                result,
                [
                    "blocker_opacity",
                    "blocker_actionability_gate.blocker_opacity",
                    "run.blocker_opacity",
                    "result.blocker_actionability_gate.blocker_opacity",
                ],
            )
        )
        if blocker_reason_present and not actionable_present and not blocker_opacity:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "run_blocker_reason_without_actionability_or_opacity",
                "`run` blocker reason codes must include violated relation, observed scalar values, expected relation, or minimum input delta; otherwise preserve blocker_opacity=true.",
            )
    if target in {"validation_set_plan", "validation_set_build"}:
        acceptance_scenarios = first_present(
            result,
            [
                "acceptance_scenarios",
                "acceptance_scenario_contract.acceptance_scenarios",
                "validation_set.acceptance_scenarios",
                "result.acceptance_scenarios",
            ],
        )
        scenario_required = boolish(
            first_present(
                result,
                [
                    "acceptance_scenario_required",
                    "acceptance_scenario_gate.required",
                    "scenario_coverage_required",
                    "result.acceptance_scenario_gate.required",
                ],
            )
        )
        scenario_coverage = first_present(
            result,
            [
                "scenario_coverage",
                "acceptance_scenario_gate.scenario_coverage",
                "validation_set.scenario_coverage",
                "result.acceptance_scenario_gate.scenario_coverage",
            ],
        )
        scenario_gate = first_present(
            result,
            [
                "acceptance_scenario_gate",
                "scenario_coverage_gate",
                "result.acceptance_scenario_gate",
            ],
        )
        scenario_uncovered = boolish(
            first_present(
                result,
                [
                    "scenario_uncovered",
                    "acceptance_scenario_gate.scenario_uncovered",
                    "result.acceptance_scenario_gate.scenario_uncovered",
                ],
            )
        )
        missing_premise_reason = first_present(
            result,
            [
                "missing_premise_satisfying_input_reason",
                "scenario_uncovered_reason",
                "acceptance_scenario_gate.missing_premise_satisfying_input_reason",
                "result.acceptance_scenario_gate.scenario_uncovered_reason",
            ],
        )
        if (non_empty(acceptance_scenarios) or scenario_required) and not (non_empty(scenario_coverage) or scenario_uncovered or non_empty(scenario_gate)):
            add(
                findings,
                "block" if mode == "block" else "warn",
                f"{target}_scenario_coverage_missing",
                f"`{target}` received scenario-shaped acceptance but did not record scenario coverage or scenario_uncovered.",
            )
        if scenario_uncovered and not non_empty(missing_premise_reason):
            add(
                findings,
                "block" if mode == "block" else "warn",
                f"{target}_scenario_uncovered_without_reason",
                f"`{target}` scenario_uncovered=true requires the missing premise-satisfying input condition.",
            )
    if target == "qualitative_review":
        review_agent_count = value_for(result, "review_agent_count")
        try:
            reviewer_count_value = int(str(review_agent_count))
        except (TypeError, ValueError):
            reviewer_count_value = None
        review_status = str(value_for(result, "review_status") or value_for(result, "status") or "").lower()
        quality_verdict = str(value_for(result, "quality_verdict") or "").lower()
        delegation_unavailable_reason = first_present(
            result,
            [
                "reviewer_delegation_unavailable_reason",
                "delegation_unavailable_reason",
                "review_delegation_unavailable_reason",
                "quality_review.reviewer_delegation_unavailable_reason",
                "qualitative_review.reviewer_delegation_unavailable_reason",
            ],
        )
        delegation_unavailable = delegation_unavailable_reason is not None
        if reviewer_count_value != 1 and not (review_status in {"blocked", "not_applicable"} and delegation_unavailable):
            add(
                findings,
                "block" if mode == "block" else "warn",
                "qualitative_review_agent_count_invalid",
                "`qualitative_review` must report exactly one reviewer agent.",
                {"review_agent_count": review_agent_count},
            )
        if review_status and review_status not in {"complete", "partial", "blocked", "not_applicable"}:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "qualitative_review_status_invalid",
                "`qualitative_review` review_status should be complete, partial, blocked, or not_applicable.",
                {"review_status": review_status},
            )
        if quality_verdict and quality_verdict not in {"acceptable", "candidate_only", "quality_blocked", "unreviewable", "not_applicable"}:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "qualitative_review_quality_verdict_invalid",
                "`qualitative_review` quality_verdict should use the owner skill vocabulary.",
                {"quality_verdict": quality_verdict},
            )
        pass_with_unobserved_axes = boolish(
            first_present(
                result,
                [
                    "pass_with_unobserved_axes",
                    "goal_axis_completeness_gate.pass_with_unobserved_axes",
                    "quality_review.pass_with_unobserved_axes",
                    "qualitative_review.pass_with_unobserved_axes",
                    "result.goal_axis_completeness_gate.pass_with_unobserved_axes",
                ],
            )
        )
        unobserved_goal_axes = first_present(
            result,
            [
                "unobserved_goal_axes",
                "goal_axis_completeness_gate.unobserved_goal_axes",
                "quality_review.unobserved_goal_axes",
                "qualitative_review.unobserved_goal_axes",
                "result.goal_axis_completeness_gate.unobserved_goal_axes",
            ],
        )
        if (pass_with_unobserved_axes or non_empty(unobserved_goal_axes)) and quality_verdict == "acceptable":
            add(
                findings,
                "block" if mode == "block" else "warn",
                "qualitative_review_unobserved_axes_acceptable",
                "`qualitative_review` cannot report an acceptable pass for measurable goals with zero mapped observing axes; use pass_with_unobserved_axes and preserve axis-supply or residual work.",
                {"unobserved_goal_axes": unobserved_goal_axes or None},
            )
        reviewer_identity = str(
            first_present(
                result,
                [
                    "reviewer_agent",
                    "reviewer_id",
                    "reviewer_identity",
                    "reviewer",
                    "quality_review.reviewer_agent",
                    "quality_review.reviewer_id",
                    "quality_review.reviewer_identity",
                    "qualitative_review.reviewer_agent",
                    "qualitative_review.reviewer_id",
                    "qualitative_review.reviewer_identity",
                ],
            )
            or ""
        ).lower()
        main_reviewer_markers = ("main_orchestrator", "main_coordinator", "main coordinator", "orchestrator", "coordinator")
        if reviewer_identity and any(marker in reviewer_identity for marker in main_reviewer_markers):
            add(
                findings,
                "block",
                "qualitative_review_main_coordinator_substitution",
                "`qualitative_review` may not satisfy the reviewer-agent contract by naming the main coordinator as the reviewer.",
                {"reviewer_identity": reviewer_identity},
            )
        if delegation_unavailable and review_status == "complete":
            add(
                findings,
                "block" if mode == "block" else "warn",
                "qualitative_review_delegation_unavailable_marked_complete",
                "Reviewer delegation unavailability must be reported as blocked, partial, or not_applicable, not complete.",
                {"reviewer_delegation_unavailable_reason": delegation_unavailable_reason},
            )
        if review_status in {"blocked", "not_applicable"} and not (
            delegation_unavailable
            or has_value(result, "review_skipped_reason")
            or has_value(result, "qualitative_review_pending_reason")
            or has_value(result, "blockers")
        ):
            add(
                findings,
                "block" if mode == "block" else "warn",
                "qualitative_review_blocked_reason_missing",
                "Blocked/not_applicable qualitative review requires a concrete blocker, skipped reason, or delegation unavailable reason.",
            )
    if target in {"commit", "closeout_commit"}:
        commit_hash = has_value(result, "commit_hash")
        commit_subject = has_value(result, "commit_subject")
        skipped_reason = has_value(result, "commit_skipped_reason")
        status = str(value_for(result, "commit_status") or value_for(result, "status") or "").lower()
        role = str(value_for(result, "commit_role") or value_for(result, "role") or "").lower()
        expected_role = "closeout" if target == "closeout_commit" else "implementation"
        if role and role != expected_role:
            add(findings, "warn", "commit_role_mismatch", f"`{target}` expected `commit_role: {expected_role}`.", {"commit_role": role})
        if status in {"created", "committed", "success", "passed"} and not commit_hash:
            add(findings, "block" if mode == "block" else "warn", "commit_hash_missing", "Created commit result is missing `commit_hash`.")
        if status in {"created", "committed", "success", "passed"} and not commit_subject:
            add(findings, "block" if mode == "block" else "warn", "commit_subject_missing", "Created commit result is missing `commit_subject`.")
        if status in {"skipped", "not_applicable", "blocked", "failed"} and not skipped_reason:
            add(findings, "block" if mode == "block" else "warn", "commit_skipped_reason_missing", "Skipped/blocked commit result is missing `commit_skipped_reason`.")
    if target == "derive":
        status = str(value_for(result, "status") or "").lower()
        if status in {"deferred", "pending", "blocked", "failed"} and not has_value(result, "derive_pending_reason") and not has_value(result, "blockers"):
            add(findings, "block" if mode == "block" else "warn", "derive_pending_reason_missing", "Deferred or blocked derivation requires a pending/blocker reason.")
        selected_source = str(value_for(result, "selected_task_source") or "").lower()
        pack_disposition = str(
            first_present(
                result,
                [
                    "pack_disposition",
                    "derive.pack_disposition",
                    "result.pack_disposition",
                    "task_pack_packet.pack_disposition",
                    "task_pack.disposition",
                ],
            )
            or ""
        ).lower()
        pack_scope = task_pack_in_scope(result) or bool(pack_disposition)
        if active_task_pack_present(result) and selected_source != "task_pack" and not has_value(result, "task_pack_status"):
            add(findings, "block" if mode == "block" else "warn", "task_pack_status_missing", "Active task pack in scope requires `task_pack_status` in derive result.")
        if pack_scope and not pack_disposition:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "pack_disposition_missing",
                "`derive` with task-pack scope requires exactly one `pack_disposition`.",
                {"allowed": sorted(PACK_DISPOSITIONS)},
            )
        if pack_disposition and pack_disposition not in PACK_DISPOSITIONS:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "pack_disposition_invalid",
                "`pack_disposition` is not an allowed task-pack transaction.",
                {"pack_disposition": pack_disposition, "allowed": sorted(PACK_DISPOSITIONS)},
            )
        if selected_source and selected_source not in {"task_pack", "candidate_task", "standalone", "terminal_blocked"}:
            add(findings, "warn", "selected_task_source_invalid", "`selected_task_source` should be task_pack, candidate_task, standalone, or terminal_blocked.", {"selected_task_source": selected_source})
        if selected_source == "task_pack":
            require_context_field("task_pack_status", "task_pack_status_missing", "`selected_task_source: task_pack` requires `task_pack_status`.")
            require_context_field("task_pack_path", "task_pack_path_missing", "`selected_task_source: task_pack` requires `task_pack_path`.")
            require_context_field("task_pack_item_id", "task_pack_item_id_missing", "`selected_task_source: task_pack` requires `task_pack_item_id` or `promoted_item_id`.")
            require_context_field("pack_disposition", "pack_disposition_missing", "`selected_task_source: task_pack` requires `pack_disposition`.")
        if pack_disposition in PACK_MUTATION_DISPOSITIONS:
            require_context_field("pack_mutation_plan", "pack_mutation_plan_missing", "Pack mutation dispositions require `pack_mutation_plan`.")
            require_context_field("task_pack_path", "task_pack_path_missing", "Pack mutation dispositions require `task_pack_path`.")
            require_context_field("task_pack_render_path", "task_pack_render_path_missing", "Pack mutation dispositions require a refreshed Markdown render path.")
            if not has_value(result, "pack_mutation_log") and not has_value(result, "pack_mutation_plan"):
                add(
                    findings,
                    "block" if mode == "block" else "warn",
                    "pack_mutation_evidence_missing",
                    "Pack mutation dispositions should carry mutation-log evidence or a durable mutation plan.",
                )
        if pack_disposition in {"skip_items", "exclude_items"}:
            require_context_field("skipped_item_ids", "skipped_item_ids_missing", "Skipping/excluding pack items requires `skipped_item_ids` or `exclude_item_ids`.")
        if pack_disposition == "derive_standalone":
            require_context_field("derive_standalone_rationale", "derive_standalone_rationale_missing", "`derive_standalone` with an active pack requires a rationale.")
        if pack_disposition == "terminal_blocked" and selected_source not in {"", "terminal_blocked"}:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "pack_terminal_selected_source_mismatch",
                "`pack_disposition: terminal_blocked` should use `selected_task_source: terminal_blocked`.",
                {"selected_task_source": selected_source},
            )
        if selected_source == "terminal_blocked" and not has_value(result, "terminal_blocker"):
            add(findings, "block", "terminal_blocker_missing", "`selected_task_source: terminal_blocked` requires `terminal_blocker`.")
        if selected_source == "terminal_blocked" and not has_value(result, "semantic_signature"):
            add(findings, "block" if mode == "block" else "warn", "terminal_semantic_signature_missing", "`selected_task_source: terminal_blocked` should include `semantic_signature` so the family can be sealed.")
        if selected_source != "terminal_blocked" and not has_value(result, "next_task_id"):
            add(findings, "block" if mode == "block" else "warn", "next_task_id_missing", "Non-terminal derive result requires `next_task_id`.")
        progress_kind = str(
            first_present(
                result,
                [
                    "progress_kind",
                    "selected_progress_kind",
                    "expected_progress_kind",
                    "derive.progress_kind",
                    "derive.selected_progress_kind",
                    "result.progress_kind",
                    "result.selected_progress_kind",
                ],
            )
            or ""
        ).lower()
        if progress_kind and progress_kind not in {"goal_productive", "governance_only"}:
            add(findings, "warn", "progress_kind_invalid", "`derive` progress_kind should be `goal_productive` or `governance_only`.", {"progress_kind": progress_kind})
        if progress_kind == "governance_only" and selected_source != "terminal_blocked":
            add(
                findings,
                "warn",
                "derive_governance_only_selected",
                "`derive` selected a governance-only task; ensure this is not another sidecar/narrowing loop.",
            )
        effective_allowed = list_values(
            first_present(
                result,
                [
                    "effective_allowed_dispositions",
                    "anti_loop_progress_gate.effective_allowed_dispositions",
                    "loop_breaker_packet.effective_allowed_dispositions",
                    "result.anti_loop_progress_gate.effective_allowed_dispositions",
                    "result.loop_breaker_packet.effective_allowed_dispositions",
                ],
            )
        )
        if effective_allowed:
            disposition = selected_disposition(result, selected_source, progress_kind)
            if disposition and disposition not in {item.lower() for item in effective_allowed}:
                add(
                    findings,
                    "block" if mode == "block" else "warn",
                    "disposition_not_effectively_allowed",
                    "Derive selected a disposition outside `effective_allowed_dispositions`; active gates must be consumed as an intersection, not a union.",
                    {"selected_disposition": disposition, "effective_allowed_dispositions": effective_allowed},
                )
        disposition_basis = first_present(
            result,
            [
                "disposition_intersection_basis",
                "anti_loop_progress_gate.disposition_intersection_basis",
                "loop_breaker_packet.disposition_intersection_basis",
                "result.anti_loop_progress_gate.disposition_intersection_basis",
                "result.loop_breaker_packet.disposition_intersection_basis",
            ],
        )
        allowed_task_kinds = allowed_task_kinds_from_basis(disposition_basis)
        selected_kind = selected_task_kind_value(result)
        terminal_selected = selected_source == "terminal_blocked" or has_value(result, "terminal_blocker")
        scenario_uncovered = boolish(
            first_present(
                result,
                [
                    "scenario_uncovered",
                    "acceptance_scenario_gate.scenario_uncovered",
                    "anti_loop_progress_gate.scenario_uncovered",
                    "result.anti_loop_progress_gate.acceptance_scenario_gate.scenario_uncovered",
                ],
            )
        )
        acceptance_inversion = boolish(
            first_present(
                result,
                [
                    "acceptance_inversion",
                    "acceptance_inversion_candidate",
                    "acceptance_scenario_gate.acceptance_inversion",
                    "anti_loop_progress_gate.acceptance_inversion",
                    "result.anti_loop_progress_gate.acceptance_scenario_gate.acceptance_inversion",
                ],
            )
        )
        command_provenance_missing = boolish(
            first_present(
                result,
                [
                    "command_provenance_missing",
                    "command_provenance_gate.command_provenance_missing",
                    "anti_loop_progress_gate.command_provenance_missing",
                    "result.anti_loop_progress_gate.command_provenance_gate.command_provenance_missing",
                ],
            )
        )
        repeated_blocker_opacity = boolish(
            first_present(
                result,
                [
                    "repeated_blocker_opacity",
                    "blocker_opacity_repeated",
                    "blocker_actionability_gate.repeated_blocker_opacity",
                    "anti_loop_progress_gate.repeated_blocker_opacity",
                    "result.anti_loop_progress_gate.blocker_actionability_gate.repeated_blocker_opacity",
                ],
            )
        )
        authorization_contract_repair_candidate = boolish(
            first_present(
                result,
                [
                    "authorization_contract_repair_candidate",
                    "blocker_actionability_gate.authorization_contract_repair_candidate",
                    "anti_loop_progress_gate.authorization_contract_repair_candidate",
                    "result.anti_loop_progress_gate.blocker_actionability_gate.authorization_contract_repair_candidate",
                ],
            )
        )
        stochastic_contract_infeasible = boolish(
            first_present(
                result,
                [
                    "predetermined_unreachable",
                    "floor_edge_envelope",
                    "stochastic_feasibility_gate.predetermined_unreachable",
                    "stochastic_feasibility_gate.floor_edge_envelope",
                    "anti_loop_progress_gate.predetermined_unreachable",
                    "anti_loop_progress_gate.floor_edge_envelope",
                    "result.anti_loop_progress_gate.stochastic_feasibility_gate.predetermined_unreachable",
                    "result.anti_loop_progress_gate.stochastic_feasibility_gate.floor_edge_envelope",
                ],
            )
        )
        if scenario_uncovered and not terminal_selected and selected_kind not in SCENARIO_SUPPLY_TASK_KINDS:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "derive_scenario_uncovered_unhandled",
                "`derive` must route scenario_uncovered to validation-set planning, fixture supply, live-run supply, terminal state, or user escalation.",
                {"selected_task_kind": selected_kind or None},
            )
        if acceptance_inversion and not terminal_selected and selected_kind not in SCENARIO_REPAIR_TASK_KINDS:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "derive_acceptance_inversion_unhandled",
                "`derive` must route acceptance_inversion to code or acceptance/test contract repair, not another green-test confirmation task.",
                {"selected_task_kind": selected_kind or None},
            )
        if command_provenance_missing and not terminal_selected and selected_kind not in COMMAND_PROVENANCE_TASK_KINDS:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "derive_command_provenance_missing_unhandled",
                "`derive` must repair or rerun missing command provenance before using that run for baseline, comparison, A/B, or reproduction evidence.",
                {"selected_task_kind": selected_kind or None},
            )
        if (repeated_blocker_opacity or authorization_contract_repair_candidate) and not terminal_selected and selected_kind not in BLOCKER_CONTRACT_REPAIR_TASK_KINDS:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "derive_repeated_blocker_opacity_unhandled",
                "`derive` must route repeated same-gate blocker_opacity or hidden multi-input authorization contracts to blocker/gate contract repair or terminal/user escalation.",
                {"selected_task_kind": selected_kind or None},
            )
        if stochastic_contract_infeasible and not terminal_selected and selected_kind not in STOCHASTIC_CONTRACT_TASK_KINDS:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "derive_stochastic_contract_infeasible_unhandled",
                "`derive` must route predetermined_unreachable or floor_edge_envelope to contract revision, envelope expansion, residual descope, terminal state, or user escalation rather than retry.",
                {"selected_task_kind": selected_kind or None},
            )
        expectation_lineage_stale = boolish(
            first_present(
                result,
                [
                    "expectation_lineage_stale",
                    "expectation_lineage_gate.expectation_lineage_stale",
                    "anti_loop_progress_gate.expectation_lineage_stale",
                    "result.anti_loop_progress_gate.expectation_lineage_gate.expectation_lineage_stale",
                ],
            )
        )
        expectation_anchor_missing = boolish(
            first_present(
                result,
                [
                    "expectation_anchor_missing",
                    "expectation_lineage_gate.expectation_anchor_missing",
                    "anti_loop_progress_gate.expectation_anchor_missing",
                    "result.anti_loop_progress_gate.expectation_lineage_gate.expectation_anchor_missing",
                ],
            )
        )
        parity_unverified = boolish(
            first_present(
                result,
                [
                    "parity_unverified",
                    "comparison_parity_gate.parity_unverified",
                    "anti_loop_progress_gate.parity_unverified",
                    "result.anti_loop_progress_gate.comparison_parity_gate.parity_unverified",
                ],
            )
        )
        unknown_parity_axes = boolish(
            first_present(
                result,
                [
                    "unknown_parity_axes",
                    "comparison_parity_gate.unknown_parity_axes",
                    "anti_loop_progress_gate.unknown_parity_axes",
                    "result.anti_loop_progress_gate.comparison_parity_gate.unknown_parity_axes",
                ],
            )
        )
        majority_vote_adoption = boolish(
            first_present(
                result,
                [
                    "majority_vote_adoption",
                    "adoption_axis_gate.majority_vote_adoption",
                    "anti_loop_progress_gate.majority_vote_adoption",
                    "result.anti_loop_progress_gate.adoption_axis_gate.majority_vote_adoption",
                ],
            )
        )
        adoption_axis_classification = first_present(
            result,
            [
                "adoption_axis_classification",
                "adoption_axis_gate.adoption_axis_classification",
                "anti_loop_progress_gate.adoption_axis_classification",
                "result.anti_loop_progress_gate.adoption_axis_gate.adoption_axis_classification",
            ],
        )
        measured_but_disqualified = boolish(
            first_present(
                result,
                [
                    "measured_but_disqualified",
                    "adoption_axis_gate.measured_but_disqualified",
                    "anti_loop_progress_gate.measured_but_disqualified",
                    "result.anti_loop_progress_gate.adoption_axis_gate.measured_but_disqualified",
                ],
            )
        )
        failed_gating_axis = boolish(
            first_present(
                result,
                [
                    "failed_gating_axis",
                    "adoption_axis_gate.failed_gating_axis",
                    "anti_loop_progress_gate.failed_gating_axis",
                    "result.anti_loop_progress_gate.adoption_axis_gate.failed_gating_axis",
                ],
            )
        )
        resolution_downgrade = boolish(
            first_present(
                result,
                [
                    "resolution_downgrade",
                    "resolution_downgrade_gate.resolution_downgrade",
                    "anti_loop_progress_gate.resolution_downgrade",
                    "result.anti_loop_progress_gate.resolution_downgrade_gate.resolution_downgrade",
                ],
            )
        )
        repeated_resolution_downgrade = boolish(
            first_present(
                result,
                [
                    "repeated_resolution_downgrade",
                    "resolution_downgrade_gate.repeated_resolution_downgrade",
                    "anti_loop_progress_gate.repeated_resolution_downgrade",
                    "result.anti_loop_progress_gate.resolution_downgrade_gate.repeated_resolution_downgrade",
                ],
            )
        )
        if expectation_lineage_stale and not terminal_selected and selected_kind not in EXPECTATION_REBASELINE_TASK_KINDS:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "derive_expectation_lineage_stale_unhandled",
                "`derive` must route stale output-derived expectations to rebaseline, explicit residual descope, terminal state, or user escalation before dependent live execution.",
                {"selected_task_kind": selected_kind or None},
            )
        if expectation_anchor_missing and not expectation_lineage_stale and progress_kind == "goal_productive" and selected_kind not in EXPECTATION_REBASELINE_TASK_KINDS:
            add(
                findings,
                "warn",
                "derive_expectation_anchor_missing_unhandled",
                "`derive` selected goal_productive work with an output-derived expectation missing an anchor; ensure the task does not claim lineage-verified expectation evidence.",
                {"selected_task_kind": selected_kind or None},
            )
        if (parity_unverified or unknown_parity_axes) and not terminal_selected and selected_kind not in PARITY_AXIS_TASK_KINDS:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "derive_parity_unverified_unhandled",
                "`derive` must route parity-unverified comparison/adoption to axis resolution, provisional comparison, residual descope, terminal state, or user escalation.",
                {"selected_task_kind": selected_kind or None},
            )
        if majority_vote_adoption and not non_empty(adoption_axis_classification) and not terminal_selected and selected_kind not in ADOPTION_AXIS_TASK_KINDS:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "derive_majority_vote_adoption_unhandled",
                "`derive` must not finalize majority-vote adoption without gating/tradable axis classification.",
                {"selected_task_kind": selected_kind or None},
            )
        if (measured_but_disqualified or failed_gating_axis) and not terminal_selected and selected_kind not in ADOPTION_AXIS_TASK_KINDS:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "derive_gating_axis_failure_unhandled",
                "`derive` must not promote a candidate with failed gating axes; preserve measured_but_disqualified evidence or route gating-axis repair/contract revision.",
                {"selected_task_kind": selected_kind or None},
            )
        if repeated_resolution_downgrade and not terminal_selected and selected_kind not in RESOLUTION_REPAIR_TASK_KINDS:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "derive_resolution_downgrade_unhandled",
                "`derive` must route repeated same-contract resolution_downgrade to resolution restoration, contract revision, residual descope, terminal state, or user escalation.",
                {"selected_task_kind": selected_kind or None},
            )
        if resolution_downgrade and not repeated_resolution_downgrade and progress_kind == "goal_productive":
            add(
                findings,
                "warn",
                "derive_resolution_downgrade_goal_productive",
                "`derive` selected goal_productive work while evidence resolution is downgraded; keep the decision provisional or preserve residual high-resolution scope.",
                {"selected_task_kind": selected_kind or None},
            )
        if (explicit_report_key_divergence or auto_report_key_divergences) and not terminal_selected and selected_kind not in REPORT_KEY_REPAIR_TASK_KINDS:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "derive_report_key_divergence_unhandled",
                "`derive` must route report_key_divergence to report/schema/sync repair, terminal state, or user escalation before consuming that report.",
                {"selected_task_kind": selected_kind or None},
            )
        pass_on_stale_lane = boolish(
            first_present(
                result,
                [
                    "pass_on_stale_lane",
                    "lane_identity_gate.pass_on_stale_lane",
                    "anti_loop_progress_gate.pass_on_stale_lane",
                    "anti_loop_progress_gate.lane_identity_gate.pass_on_stale_lane",
                    "result.anti_loop_progress_gate.pass_on_stale_lane",
                    "result.lane_identity_gate.pass_on_stale_lane",
                ],
            )
        )
        decision_metadata_revision = boolish(
            first_present(
                result,
                [
                    "decision_metadata_revision",
                    "stale_measurement_artifact",
                    "decision_freshness_gate.decision_metadata_revision",
                    "decision_freshness_gate.stale_measurement_artifact",
                    "anti_loop_progress_gate.decision_metadata_revision",
                    "anti_loop_progress_gate.stale_measurement_artifact",
                    "result.decision_freshness_gate.decision_metadata_revision",
                ],
            )
        )
        axis_starved_by_missing_producer = boolish(
            first_present(
                result,
                [
                    "axis_starved_by_missing_producer",
                    "gating_axis_producer_gate.axis_starved_by_missing_producer",
                    "anti_loop_progress_gate.axis_starved_by_missing_producer",
                    "anti_loop_progress_gate.gating_axis_producer_gate.axis_starved_by_missing_producer",
                    "result.gating_axis_producer_gate.axis_starved_by_missing_producer",
                ],
            )
        )
        portfolio_quota_exceeded = boolish(
            first_present(
                result,
                [
                    "portfolio_quota_exceeded",
                    "portfolio_quota_gate.portfolio_quota_exceeded",
                    "anti_loop_progress_gate.portfolio_quota_exceeded",
                    "anti_loop_progress_gate.portfolio_quota_gate.portfolio_quota_exceeded",
                    "result.portfolio_quota_gate.portfolio_quota_exceeded",
                ],
            )
        )
        portfolio_quota_mode = str(
            first_present(
                result,
                [
                    "portfolio_quota_mode",
                    "portfolio_quota_gate.portfolio_quota_mode",
                    "portfolio_quota_gate.mode",
                    "anti_loop_progress_gate.portfolio_quota_mode",
                    "anti_loop_progress_gate.portfolio_quota_gate.mode",
                    "result.portfolio_quota_gate.portfolio_quota_mode",
                ],
            )
            or ""
        ).lower()
        portfolio_quota_restrictive = portfolio_quota_mode in {"restrict", "restricted", "block", "blocking"}
        unreachable_within_cycle = boolish(
            first_present(
                result,
                [
                    "unreachable_within_cycle",
                    "cycle_reachability_gate.unreachable_within_cycle",
                    "acceptance_reachability_gate.unreachable_within_cycle",
                    "anti_loop_progress_gate.unreachable_within_cycle",
                    "anti_loop_progress_gate.cycle_reachability_gate.unreachable_within_cycle",
                    "result.cycle_reachability_gate.unreachable_within_cycle",
                ],
            )
        )
        basis_overclaim = boolish(
            first_present(
                result,
                [
                    "basis_overclaim",
                    "metric_basis_gate.basis_overclaim",
                    "anti_loop_progress_gate.basis_overclaim",
                    "anti_loop_progress_gate.metric_basis_gate.basis_overclaim",
                    "result.metric_basis_gate.basis_overclaim",
                ],
            )
        )
        surface_field_defect_matrix = first_present(
            result,
            [
                "surface_field_defect_matrix",
                "surface_field_review_gate.surface_field_defect_matrix",
                "qualitative_review_packet.surface_field_defect_matrix",
                "anti_loop_progress_gate.surface_field_defect_matrix",
                "result.surface_field_review_gate.surface_field_defect_matrix",
            ],
        )
        surface_field_defects = nonzero_scalar(surface_field_defect_matrix)
        if pass_on_stale_lane and not terminal_selected and selected_kind not in CURRENT_LANE_TASK_KINDS:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "derive_pass_on_stale_lane_unhandled",
                "`derive` must route pass_on_stale_lane to current-lane rerun/revalidation, residual descope, terminal state, or user escalation before consuming the pass.",
                {"selected_task_kind": selected_kind or None},
            )
        if decision_metadata_revision and not terminal_selected and selected_kind not in DECISION_FRESHNESS_TASK_KINDS:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "derive_decision_metadata_revision_unhandled",
                "`derive` must route stale decision updates to fresh current-lane measurement, no-impact proof, residual descope, terminal state, or user escalation.",
                {"selected_task_kind": selected_kind or None},
            )
        if axis_starved_by_missing_producer and not terminal_selected and selected_kind not in PRODUCER_SUPPLY_TASK_KINDS:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "derive_axis_starved_by_missing_producer_unhandled",
                "`derive` must route a producer-starved gating axis to producer-supply work before another verifier, guard, report, or metadata task can count as progress.",
                {"selected_task_kind": selected_kind or None},
            )
        if portfolio_quota_exceeded and portfolio_quota_restrictive and not terminal_selected and selected_kind not in PORTFOLIO_QUOTA_TASK_KINDS:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "derive_portfolio_quota_restriction_unhandled",
                "`derive` must honor restrictive portfolio_quota_exceeded by selecting producer, envelope, long-run, descope, terminal, or escalation work.",
                {"selected_task_kind": selected_kind or None},
            )
        elif portfolio_quota_exceeded and not portfolio_quota_restrictive:
            add(
                findings,
                "warn",
                "derive_portfolio_quota_warn_only",
                "`portfolio_quota_exceeded` is warn-only unless the adapter supplies restrict mode; preserve it without restricting selection.",
                {"portfolio_quota_mode": portfolio_quota_mode or None},
            )
        if unreachable_within_cycle and not terminal_selected and selected_kind not in CYCLE_REACHABILITY_TASK_KINDS:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "derive_unreachable_within_cycle_unhandled",
                "`derive` must route unreachable_within_cycle to long-run launch/monitor/harvest, throughput improvement, descope, terminal state, or user escalation.",
                {"selected_task_kind": selected_kind or None},
            )
        if basis_overclaim and not terminal_selected and selected_kind not in METRIC_BASIS_TASK_KINDS:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "derive_basis_overclaim_unhandled",
                "`derive` must route basis_overclaim to basis-compatible measurement, metric-basis repair, downgrade-aware contract work, residual descope, terminal state, or user escalation.",
                {"selected_task_kind": selected_kind or None},
            )
        if surface_field_defects and not terminal_selected and selected_kind not in SURFACE_FIELD_TASK_KINDS:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "derive_surface_field_defects_unhandled",
                "`derive` must route nonzero surface_field_defect_matrix to producer/field repair, residual descope, terminal state, or user escalation before consuming the review pass.",
                {"selected_task_kind": selected_kind or None},
            )
        terminal_stage_contradiction = boolish(
            first_present(
                result,
                [
                    "terminal_classification_stage_contradiction",
                    "failure_surface_stage_gate.terminal_classification_stage_contradiction",
                    "anti_loop_progress_gate.terminal_classification_stage_contradiction",
                    "anti_loop_progress_gate.failure_surface_stage_gate.terminal_classification_stage_contradiction",
                    "loopback_audit.terminal_classification_stage_contradiction",
                    "result.anti_loop_progress_gate.terminal_classification_stage_contradiction",
                ],
            )
        )
        terminal_classification_invalid_for_counting = boolish(
            first_present(
                result,
                [
                    "terminal_classification_invalid_for_counting",
                    "failure_surface_stage_gate.terminal_classification_invalid_for_counting",
                    "anti_loop_progress_gate.terminal_classification_invalid_for_counting",
                    "result.anti_loop_progress_gate.terminal_classification_invalid_for_counting",
                ],
            )
        )
        same_input_contract_violation = boolish(
            first_present(
                result,
                [
                    "same_input_contract_violation",
                    "same_input_contract_gate.same_input_contract_violation",
                    "anti_loop_progress_gate.same_input_contract_violation",
                    "anti_loop_progress_gate.same_input_contract_gate.same_input_contract_violation",
                    "result.anti_loop_progress_gate.same_input_contract_violation",
                ],
            )
        )
        instrumentation_supply_required = boolish(
            first_present(
                result,
                [
                    "instrumentation_supply_required",
                    "diagnostics_unavailable_gate.instrumentation_supply_required",
                    "anti_loop_progress_gate.instrumentation_supply_required",
                    "anti_loop_progress_gate.diagnostics_unavailable_gate.instrumentation_supply_required",
                    "result.anti_loop_progress_gate.instrumentation_supply_required",
                ],
            )
        )
        diagnostics_unavailable_streak = number_value(
            first_present(
                result,
                [
                    "diagnostics_unavailable_streak",
                    "diagnostics_unavailable_gate.diagnostics_unavailable_streak",
                    "anti_loop_progress_gate.diagnostics_unavailable_streak",
                    "result.anti_loop_progress_gate.diagnostics_unavailable_streak",
                ],
            )
        )
        diagnostics_observable_without_new_instrumentation = boolish(
            first_present(
                result,
                [
                    "diagnostics_observable_without_new_instrumentation",
                    "success_failure_observable_without_instrumentation",
                    "existing_diagnostics_sufficient",
                    "hypothesis_repair_observability_rationale",
                    "derive.diagnostics_observable_without_new_instrumentation",
                    "result.existing_diagnostics_sufficient",
                ],
            )
        )
        independent_source_status = str(
            first_present(
                result,
                [
                    "independent_source_separation_status",
                    "verification_source_separation_gate.independent_source_separation_status",
                    "evidence_provenance_gate.independent_source_separation_status",
                    "anti_loop_progress_gate.independent_source_separation_status",
                    "anti_loop_progress_gate.verification_source_separation_gate.independent_source_separation_status",
                    "result.anti_loop_progress_gate.independent_source_separation_status",
                ],
            )
            or ""
        ).lower()
        independently_verified_downgraded_fields = list_values(
            first_present(
                result,
                [
                    "independently_verified_downgraded_fields",
                    "verification_source_separation_gate.independently_verified_downgraded_fields",
                    "evidence_provenance_gate.independently_verified_downgraded_fields",
                    "anti_loop_progress_gate.independently_verified_downgraded_fields",
                    "result.anti_loop_progress_gate.independently_verified_downgraded_fields",
                ],
            )
        )
        envelope_thaw_item_required = boolish(
            first_present(
                result,
                [
                    "envelope_thaw_item_required",
                    "acceptance_reachability_gate.envelope_thaw_item_required",
                    "anti_loop_progress_gate.envelope_thaw_item_required",
                    "anti_loop_progress_gate.acceptance_reachability_gate.envelope_thaw_item_required",
                    "result.anti_loop_progress_gate.envelope_thaw_item_required",
                ],
            )
        )
        envelope_thaw_item = first_present(
            result,
            [
                "envelope_thaw_item",
                "acceptance_reachability_gate.envelope_thaw_item",
                "anti_loop_progress_gate.envelope_thaw_item",
                "anti_loop_progress_gate.acceptance_reachability_gate.envelope_thaw_item",
                "selected_task.envelope_thaw_item",
                "result.anti_loop_progress_gate.envelope_thaw_item",
            ],
        )
        if progress_kind == "goal_productive" and allowed_task_kinds and selected_source != "terminal_blocked":
            if not selected_kind:
                add(
                    findings,
                    "block" if mode == "block" else "warn",
                    "selected_task_kind_missing_for_constrained_goal_productive",
                    "`derive` must provide `selected_task_kind` when active gates restrict goal_productive to specific task kinds.",
                    {"allowed_task_kinds": sorted(allowed_task_kinds)},
                )
            elif selected_kind not in allowed_task_kinds:
                add(
                    findings,
                    "block" if mode == "block" else "warn",
                    "goal_productive_task_kind_not_allowed",
                    "`derive` selected goal_productive by label but the task kind is outside the gate-constrained allowed set.",
                    {"selected_task_kind": selected_kind, "allowed_task_kinds": sorted(allowed_task_kinds)},
                )
        classification_repair_selected = selected_kind in CLASSIFICATION_REPAIR_TASK_KINDS or selected_disposition(result, selected_source, progress_kind) in {
            "classification_stage_repair",
            "input_contract_repair",
        }
        if (terminal_stage_contradiction or terminal_classification_invalid_for_counting) and not terminal_selected and not classification_repair_selected:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "derive_terminal_classification_stage_repair_missing",
                "`derive` cannot count or close a contradictory terminal classification; select a classification-stage repair/input-contract repair, terminal block, or user escalation.",
            )
        if same_input_contract_violation and not terminal_selected and not classification_repair_selected:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "derive_same_input_contract_repair_missing",
                "`derive` cannot compare same-family failures across mismatched input sets; select same-input contract repair before counting progress.",
            )
        if instrumentation_supply_required and not terminal_selected and selected_kind not in INSTRUMENTATION_TASK_KINDS and not diagnostics_observable_without_new_instrumentation:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "derive_missing_instrumentation_supply",
                "`derive` must enumerate/select instrumentation supply after repeated diagnostics_unavailable, or record why success/failure is already observable without new instrumentation.",
                {"diagnostics_unavailable_streak": diagnostics_unavailable_streak},
            )
        if progress_kind == "goal_productive" and independent_source_status in {"missing", "overlap", "blocked"} and not terminal_selected:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "derive_goal_productive_from_non_disjoint_independent_verification",
                "`derive` cannot treat independently_verified evidence as goal_productive when verification inputs overlap verified artifacts or are missing; consume it as attested or repair the source separation.",
                {"independent_source_separation_status": independent_source_status},
            )
        if progress_kind == "goal_productive" and independently_verified_downgraded_fields and not terminal_selected:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "derive_goal_productive_from_downgraded_independent_verification",
                "`derive` cannot use auto-downgraded independently_verified fields as progress without new disjoint verification input.",
                {"downgraded_fields": independently_verified_downgraded_fields},
            )
        if envelope_thaw_item_required and not terminal_selected and selected_kind not in ENVELOPE_THAW_TASK_KINDS and not non_empty(envelope_thaw_item):
            add(
                findings,
                "block" if mode == "block" else "warn",
                "derive_envelope_thaw_item_missing",
                "`derive` must reserve an envelope_thaw_item when acceptance is unreachable under a frozen envelope, before ordinary repair continues.",
            )
        coupled_verifier = boolish(
            first_present(
                result,
                [
                    "pass_with_coupled_verifier",
                    "anti_loop_progress_gate.pass_with_coupled_verifier",
                    "loopback_audit.pass_with_coupled_verifier",
                    "coupled_verifier_gate.pass_with_coupled_verifier",
                    "anti_loop_progress_gate.coupled_verifier_gate.pass_with_coupled_verifier",
                    "result.anti_loop_progress_gate.pass_with_coupled_verifier",
                    "result.anti_loop_progress_gate.coupled_verifier_gate.pass_with_coupled_verifier",
                ],
            )
        )
        attested_only_movement = boolish(
            first_present(
                result,
                [
                    "attested_only_movement",
                    "anti_loop_progress_gate.attested_only_movement",
                    "evidence_provenance_gate.attested_only_movement",
                    "anti_loop_progress_gate.evidence_provenance_gate.attested_only_movement",
                    "primary_metric_gate.attested_only_movement",
                    "anti_loop_progress_gate.primary_metric_gate.attested_only_movement",
                    "result.anti_loop_progress_gate.attested_only_movement",
                    "result.anti_loop_progress_gate.evidence_provenance_gate.attested_only_movement",
                ],
            )
        )
        primary_metric_stalled = boolish(
            first_present(
                result,
                [
                    "primary_metric_stalled",
                    "anti_loop_progress_gate.primary_metric_stalled",
                    "primary_metric_gate.primary_metric_stalled",
                    "anti_loop_progress_gate.primary_metric_gate.primary_metric_stalled",
                    "result.anti_loop_progress_gate.primary_metric_stalled",
                    "result.anti_loop_progress_gate.primary_metric_gate.primary_metric_stalled",
                ],
            )
        )
        c4_user_escalation = boolish(
            first_present(
                result,
                [
                    "c4_user_escalation_backstop_required",
                    "anti_loop_progress_gate.c4_user_escalation_backstop_required",
                    "primary_metric_gate.c4_user_escalation_backstop_required",
                    "anti_loop_progress_gate.primary_metric_gate.c4_user_escalation_backstop_required",
                    "result.anti_loop_progress_gate.c4_user_escalation_backstop_required",
                    "result.anti_loop_progress_gate.primary_metric_gate.c4_user_escalation_backstop_required",
                ],
            )
        )
        marginal_repair = boolish(
            first_present(
                result,
                [
                    "marginal_repair",
                    "residual_gap_policy.marginal_repair",
                    "anti_loop_progress_gate.marginal_repair",
                    "anti_loop_progress_gate.residual_gap_policy.marginal_repair",
                    "result.anti_loop_progress_gate.marginal_repair",
                ],
            )
        )
        descope_with_residual = boolish(
            first_present(
                result,
                [
                    "descope_with_residual",
                    "explicit_descope_decision",
                    "residual_gap_policy.descope_with_residual",
                    "anti_loop_progress_gate.descope_with_residual",
                    "result.anti_loop_progress_gate.descope_with_residual",
                ],
            )
        )
        next_capability_rung = first_present(
            result,
            [
                "next_capability_rung",
                "capability_ladder.next_capability_rung",
                "residual_gap_policy.next_capability_rung",
                "anti_loop_progress_gate.next_capability_rung",
                "result.anti_loop_progress_gate.next_capability_rung",
            ],
        )
        marginal_repair_override = boolish(
            first_present(
                result,
                [
                    "marginal_repair_higher_value",
                    "residual_gap_policy.marginal_repair_higher_value",
                    "anti_loop_progress_gate.marginal_repair_higher_value",
                    "result.anti_loop_progress_gate.marginal_repair_higher_value",
                ],
            )
        )
        pass_with_unobserved_axes = boolish(
            first_present(
                result,
                [
                    "pass_with_unobserved_axes",
                    "goal_axis_completeness_gate.pass_with_unobserved_axes",
                    "qualitative_review_packet.pass_with_unobserved_axes",
                    "anti_loop_progress_gate.pass_with_unobserved_axes",
                    "result.goal_axis_completeness_gate.pass_with_unobserved_axes",
                    "result.anti_loop_progress_gate.pass_with_unobserved_axes",
                ],
            )
        )
        unobserved_goal_axes = first_present(
            result,
            [
                "unobserved_goal_axes",
                "goal_axis_completeness_gate.unobserved_goal_axes",
                "qualitative_review_packet.unobserved_goal_axes",
                "anti_loop_progress_gate.unobserved_goal_axes",
                "result.goal_axis_completeness_gate.unobserved_goal_axes",
                "result.anti_loop_progress_gate.unobserved_goal_axes",
            ],
        )
        goal_axis_failed = boolish(
            first_present(
                result,
                [
                    "goal_axis_completeness_failed",
                    "goal_axis_completeness_gate.failed",
                    "goal_axis_completeness_gate.evaluation_failed",
                    "anti_loop_progress_gate.goal_axis_completeness_gate.failed",
                    "result.goal_axis_completeness_gate.failed",
                ],
            )
        ) or str(
            first_present(
                result,
                [
                    "goal_axis_completeness_gate.evaluation_status",
                    "anti_loop_progress_gate.goal_axis_completeness_gate.evaluation_status",
                    "result.goal_axis_completeness_gate.evaluation_status",
                ],
            )
            or ""
        ).lower() == "fail"
        generation_dependent_count_key = boolish(
            first_present(
                result,
                [
                    "generation_dependent_count_key",
                    "count_key_hygiene_gate.generation_dependent_count_key",
                    "anti_loop_progress_gate.generation_dependent_count_key",
                    "anti_loop_progress_gate.count_key_hygiene_gate.generation_dependent_count_key",
                    "result.anti_loop_progress_gate.generation_dependent_count_key",
                    "result.anti_loop_progress_gate.count_key_hygiene_gate.generation_dependent_count_key",
                ],
            )
        )
        effective_count_key = first_present(
            result,
            [
                "effective_count_key",
                "count_key_hygiene_gate.effective_count_key",
                "root_dominant_parameter_key",
                "anti_loop_progress_gate.effective_count_key",
                "anti_loop_progress_gate.root_dominant_parameter_key",
                "anti_loop_progress_gate.terminal_outcome_family_key",
                "result.anti_loop_progress_gate.effective_count_key",
                "result.anti_loop_progress_gate.terminal_outcome_family_key",
            ],
        )
        generation_key_novelty_claim = boolish(
            first_present(
                result,
                [
                    "family_novelty_claim",
                    "new_family_claim",
                    "stall_reset_claim",
                    "count_key_hygiene_gate.family_novelty_claim",
                    "count_key_hygiene_gate.stall_reset_claim",
                    "anti_loop_progress_gate.count_key_hygiene_gate.family_novelty_claim",
                    "result.anti_loop_progress_gate.count_key_hygiene_gate.stall_reset_claim",
                ],
            )
        )
        cycle_fixed_cost_present = first_present(
            result,
            [
                "cycle_fixed_cost",
                "residual_gap_cost_policy.cycle_fixed_cost",
                "cycle_efficiency_profile.cycle_fixed_cost",
                "anti_loop_progress_gate.cycle_fixed_cost",
                "result.anti_loop_progress_gate.cycle_fixed_cost",
            ],
        ) is not None
        marginal_value_per_cycle_cost = float_value(
            first_present(
                result,
                [
                    "marginal_value_per_cycle_cost",
                    "residual_gap_cost_policy.marginal_value_per_cycle_cost",
                    "anti_loop_progress_gate.marginal_value_per_cycle_cost",
                    "result.anti_loop_progress_gate.marginal_value_per_cycle_cost",
                ],
            )
        )
        residual_cost_below_policy = boolish(
            first_present(
                result,
                [
                    "residual_gap_cost_below_policy",
                    "value_per_cycle_cost_below_policy",
                    "cost_disproportionate_residual",
                    "residual_gap_cost_policy.below_policy",
                    "residual_gap_cost_policy.cost_disproportionate",
                    "anti_loop_progress_gate.residual_gap_cost_policy.below_policy",
                    "result.anti_loop_progress_gate.residual_gap_cost_policy.below_policy",
                ],
            )
        )
        if progress_kind == "goal_productive" and coupled_verifier and selected_source != "terminal_blocked":
            add(
                findings,
                "block" if mode == "block" else "warn",
                "derive_goal_productive_from_coupled_verifier",
                "`derive` cannot classify work as goal_productive from pass_with_coupled_verifier; select non-coupled revalidation, independent recalculation, residual descope, terminal block, or user escalation.",
            )
        if progress_kind == "goal_productive" and attested_only_movement and selected_source != "terminal_blocked":
            add(
                findings,
                "block" if mode == "block" else "warn",
                "derive_goal_productive_from_attested_only_movement",
                "`derive` cannot classify producer-attested metric movement as goal_productive or high-water progress.",
            )
        if progress_kind == "goal_productive" and (pass_with_unobserved_axes or non_empty(unobserved_goal_axes) or goal_axis_failed) and selected_source != "terminal_blocked":
            add(
                findings,
                "block" if mode == "block" else "warn",
                "derive_goal_productive_from_unobserved_axes",
                "`derive` cannot consume a qualitative review pass as goal_productive for measurable goals with zero mapped observing axes; select axis supply, residual descope, terminal block, or user escalation.",
                {"unobserved_goal_axes": unobserved_goal_axes or None},
            )
        if generation_dependent_count_key and not effective_count_key:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "derive_generation_count_key_without_effective_key",
                "Generation-dependent family/count keys are trace-only; derive must carry an effective adapter-collapsed key or terminal-outcome family fallback.",
            )
        if generation_dependent_count_key and generation_key_novelty_claim and not terminal_selected:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "derive_family_novelty_from_generation_key",
                "`derive` must not treat task/advice/pack/cycle/run/date/hash/version churn as a new family or stall reset.",
            )
        if c4_user_escalation and selected_source != "terminal_blocked" and selected_disposition(result, selected_source, progress_kind) != "user_escalation" and not forced_task_kind(result):
            add(
                findings,
                "block" if mode == "block" else "warn",
                "derive_c4_user_escalation_not_selected",
                "`derive` must select user escalation when the primary-metric C4 backstop is required and no actionable forced task is present.",
            )
        if primary_metric_stalled and progress_kind == "goal_productive" and not forced_task_kind(result) and not terminal_selected:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "derive_primary_metric_stall_without_forced_task",
                "`derive` cannot choose ordinary goal_productive work during primary-metric stall without selecting an emitted forced-retarget task.",
            )
        if marginal_repair and progress_kind == "goal_productive" and not (descope_with_residual and next_capability_rung) and not marginal_repair_override and selected_source != "terminal_blocked":
            add(
                findings,
                "block" if mode == "block" else "warn",
                "derive_marginal_repair_without_descope_or_value_case",
                "`derive` must rank below-threshold residual-gap repair behind explicit descope-with-residual plus the next capability rung unless higher marginal value is recorded.",
            )
        if marginal_repair and cycle_fixed_cost_present and marginal_value_per_cycle_cost is None:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "derive_residual_cycle_cost_missing_ratio",
                "Residual repair with cycle-cost evidence must carry `marginal_value_per_cycle_cost`, or explicitly fall back to denominator 1 when cost evidence is absent.",
            )
        if progress_kind == "goal_productive" and residual_cost_below_policy and not (descope_with_residual and next_capability_rung) and not marginal_repair_override and selected_source != "terminal_blocked":
            add(
                findings,
                "block" if mode == "block" else "warn",
                "derive_residual_cost_below_policy_goal_productive",
                "`derive` cannot select another same-gap goal_productive repair when value per cycle cost is below policy without explicit residual descope, next rung, or a higher value case.",
            )
        forced_kind = forced_task_kind(result)
        if forced_kind and selected_source != "terminal_blocked" and selected_kind and selected_kind != forced_kind:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "forced_selected_task_kind_mismatch",
                "`derive` must select the forced task kind emitted by the anti-loop chain-stall gate before choosing another goal-productive task.",
                {"selected_task_kind": selected_kind, "forced_selected_task_kind": forced_kind},
            )
        output_delta_status = str(
            first_present(
                result,
                [
                    "output_delta_status",
                    "output_delta.output_delta_status",
                    "output_delta_gate.output_delta_status",
                    "result.output_delta.output_delta_status",
                ],
            )
            or ""
        ).lower()
        produced_domain_delta = first_present(
            result,
            [
                "produced_domain_delta",
                "output_delta.produced_domain_delta",
                "output_delta_gate.produced_domain_delta",
                "result.output_delta.produced_domain_delta",
            ],
        )
        metadata_only = first_present(
            result,
            [
                "metadata_only",
                "output_delta.metadata_only",
                "output_delta_gate.metadata_only",
                "result.output_delta.metadata_only",
            ],
        )
        effective_progress_kind = str(
            first_present(
                result,
                [
                    "effective_progress_kind",
                    "output_delta.effective_progress_kind",
                    "output_delta_gate.effective_progress_kind",
                    "result.output_delta.effective_progress_kind",
                ],
            )
            or ""
        ).lower()
        changed_vs_previous = first_present(
            result,
            [
                "changed_vs_previous",
                "output_delta.changed_vs_previous",
                "output_delta_gate.changed_vs_previous",
                "result.output_delta.changed_vs_previous",
            ],
        )
        semantic_progress = first_present(
            result,
            [
                "semantic_progress",
                "output_delta.semantic_progress",
                "output_delta_gate.semantic_progress",
                "result.output_delta.semantic_progress",
            ],
        )
        measurement_progress_allowed = boolish(
            first_present(
                result,
                [
                    "measurement_progress_allowed",
                    "anti_loop_progress_gate.measurement_progress_allowed",
                    "result.anti_loop_progress_gate.measurement_progress_allowed",
                ],
            )
        )
        measurement_progress = boolish(
            first_present(
                result,
                [
                    "measurement_progress",
                    "anti_loop_progress_gate.measurement_progress",
                    "result.anti_loop_progress_gate.measurement_progress",
                ],
            )
        )
        substance_delta_pass = boolish(
            first_present(
                result,
                [
                    "substance_delta_pass",
                    "substance_delta_gate.substance_delta_pass",
                    "anti_loop_progress_gate.substance_delta_gate.substance_delta_pass",
                    "result.anti_loop_progress_gate.substance_delta_gate.substance_delta_pass",
                ],
            )
        )
        vacuous_corrective_noop = boolish(
            first_present(
                result,
                [
                    "surface_corrective_noop",
                    "vacuous_corrective_gate.surface_corrective_noop",
                    "anti_loop_progress_gate.vacuous_corrective_gate.surface_corrective_noop",
                    "result.anti_loop_progress_gate.vacuous_corrective_gate.surface_corrective_noop",
                ],
            )
        )
        advice_metrics_stale = boolish(
            first_present(
                result,
                [
                    "advice_metrics_stale",
                    "advice_freshness_gate.advice_metrics_stale",
                    "anti_loop_progress_gate.advice_freshness_gate.advice_metrics_stale",
                    "result.anti_loop_progress_gate.advice_freshness_gate.advice_metrics_stale",
                ],
            )
        )
        measurement_streak = number_value(
            first_present(
                result,
                [
                    "measurement_streak",
                    "anti_loop_progress_gate.measurement_streak",
                    "result.anti_loop_progress_gate.measurement_streak",
                ],
            )
        )
        measurement_streak_cap = number_value(
            first_present(
                result,
                [
                    "measurement_streak_cap",
                    "anti_loop_progress_gate.measurement_streak_cap",
                    "result.anti_loop_progress_gate.measurement_streak_cap",
                ],
            )
        )
        blocker_mutation_kind = str(
            first_present(
                result,
                [
                    "blocker_mutation_kind",
                    "anti_loop_progress_gate.blocker_mutation_kind",
                    "result.anti_loop_progress_gate.blocker_mutation_kind",
                ],
            )
            or ""
        ).lower()
        forward_mutation_progress = blocker_mutation_kind == "forward_mutation"
        terminal_outcome_value = first_present(
            result,
            [
                "terminal_outcome_changed",
                "anti_loop_progress_gate.terminal_outcome_changed",
                "result.anti_loop_progress_gate.terminal_outcome_changed",
            ],
        )
        terminal_outcome_changed = (
            boolish(terminal_outcome_value)
            if terminal_outcome_value is not None
            else boolish(changed_vs_previous) and boolish(semantic_progress)
        )
        forward_mutation_vacuous = boolish(
            first_present(
                result,
                [
                    "forward_mutation_vacuous",
                    "anti_loop_progress_gate.forward_mutation_vacuous",
                    "result.anti_loop_progress_gate.forward_mutation_vacuous",
                ],
            )
        )
        force_implementation_cycle = boolish(
            first_present(
                result,
                [
                    "force_implementation_cycle",
                    "anti_loop_progress_gate.force_implementation_cycle",
                    "result.anti_loop_progress_gate.force_implementation_cycle",
                ],
            )
        )
        command_surface_class = str(
            first_present(
                result,
                [
                    "command_surface_class",
                    "selected_task.command_surface_class",
                    "command_surface_budget.command_surface_class",
                    "result.command_surface_class",
                ],
            )
            or ""
        ).strip().lower()
        allowed_force_impl_class = command_surface_class in {"b", "class_b", "c", "class_c"}
        output_delta_applies = output_delta_status == "complete" or produced_domain_delta is not None or metadata_only is not None
        if progress_kind == "goal_productive" and output_delta_applies and (
            boolish(metadata_only)
            or (produced_domain_delta is not None and not boolish(produced_domain_delta))
            or (produced_domain_delta is not None and boolish(produced_domain_delta) and not (boolish(changed_vs_previous) and boolish(semantic_progress)))
        ) and not (measurement_progress_allowed or forward_mutation_progress):
            add(
                findings,
                "block" if mode == "block" else "warn",
                "goal_productive_without_output_delta",
                "`derive` cannot classify work as goal_productive without produced_domain_delta=true backed by changed_vs_previous=true and semantic_progress=true.",
                {
                    "progress_kind": progress_kind,
                    "effective_progress_kind": effective_progress_kind or None,
                    "output_delta_status": output_delta_status or None,
                    "produced_domain_delta": produced_domain_delta,
                    "changed_vs_previous": changed_vs_previous,
                    "semantic_progress": semantic_progress,
                    "metadata_only": metadata_only,
                },
            )
        if progress_kind == "goal_productive" and (measurement_progress or blocker_mutation_kind == "forward_mutation") and not (substance_delta_pass or boolish(changed_vs_previous) and boolish(semantic_progress)):
            add(
                findings,
                "block" if mode == "block" else "warn",
                "goal_productive_without_substance_delta",
                "`derive` cannot promote measurement or ladder-rung movement from tool/oracle existence alone; require G-SUBSTANCE pass or strict changed-and-semantic primary-output evidence.",
                {
                    "measurement_progress": measurement_progress,
                    "blocker_mutation_kind": blocker_mutation_kind or None,
                    "substance_delta_pass": substance_delta_pass,
                    "changed_vs_previous": changed_vs_previous,
                    "semantic_progress": semantic_progress,
                },
            )
        if progress_kind == "goal_productive" and forward_mutation_progress and (forward_mutation_vacuous or not terminal_outcome_changed):
            add(
                findings,
                "block" if mode == "block" else "warn",
                "goal_productive_forward_mutation_without_terminal_outcome_delta",
                "`derive` cannot promote capability-ladder forward mutation when the observed terminal outcome did not change.",
                {
                    "blocker_mutation_kind": blocker_mutation_kind,
                    "terminal_outcome_changed": terminal_outcome_changed,
                    "forward_mutation_vacuous": forward_mutation_vacuous,
                },
            )
        if progress_kind == "goal_productive" and vacuous_corrective_noop and not (boolish(changed_vs_previous) and boolish(semantic_progress)):
            add(
                findings,
                "block" if mode == "block" else "warn",
                "goal_productive_from_vacuous_corrective",
                "`derive` cannot count corrective/backfill rows as goal_productive when attempted lanes resolved zero items.",
            )
        if advice_metrics_stale and has_value(result, "used_advice") and not advice_handling_rationale_present(result):
            add(
                findings,
                "warn",
                "stale_advice_used_without_rationale",
                "`derive` used advice whose headline fingerprint/metric claims are stale without a defer/reject/refresh rationale.",
            )
        if measurement_streak is not None and measurement_streak_cap is not None and measurement_streak > measurement_streak_cap and selected_source != "terminal_blocked" and not has_value(result, "terminal_blocker"):
            add(
                findings,
                "block" if mode == "block" else "warn",
                "measurement_streak_cap_exceeded",
                "Measurement progress exemption is capped; derive must not continue non-terminal measurement/governance work after the cap.",
                {"measurement_streak": measurement_streak, "measurement_streak_cap": measurement_streak_cap},
            )
        if force_implementation_cycle and not has_value(result, "terminal_blocker") and progress_kind != "goal_productive":
            add(
                findings,
                "block" if mode == "block" else "warn",
                "force_implementation_cycle_unhandled",
                "Forward-mutation budget is exhausted; derive must select implementation work or terminal/user escalation.",
                {"progress_kind": progress_kind or None},
            )
        if force_implementation_cycle and command_surface_class and not allowed_force_impl_class and not has_value(result, "terminal_blocker"):
            add(
                findings,
                "block" if mode == "block" else "warn",
                "force_implementation_command_surface_class_blocked",
                "Forced implementation under command-surface pressure may use only Class B in-place expansion or Class C surface reduction.",
                {"command_surface_class": command_surface_class},
            )

        cycles_since_goal_productive = number_value(
            first_present(
                result,
                [
                    "cycles_since_goal_productive_output",
                    "goal_distance_gate.cycles_since_goal_productive_output",
                    "loop_breaker_packet.cycles_since_goal_productive_output",
                    "packet.goal_distance_gate.cycles_since_goal_productive_output",
                    "result.goal_distance_gate.cycles_since_goal_productive_output",
                ],
            )
        )
        goal_threshold = number_value(
            first_present(result, ["goal_productive_threshold", "goal_distance_gate.threshold", "result.goal_distance_gate.threshold"])
        ) or 5
        goal_distance_required = boolish(
            first_present(
                result,
                [
                    "requires_goal_productive_next",
                    "goal_distance_gate.requires_goal_productive_next",
                    "loop_breaker_packet.requires_goal_productive_next",
                    "result.goal_distance_gate.requires_goal_productive_next",
                ],
            )
        ) or (cycles_since_goal_productive is not None and cycles_since_goal_productive > goal_threshold)
        governance_only_streak = number_value(
            first_present(
                result,
                [
                    "governance_only_streak",
                    "previous_governance_only_count",
                    "loop_breaker_packet.governance_only_streak",
                    "goal_distance_gate.governance_only_streak",
                    "result.goal_distance_gate.governance_only_streak",
                ],
            )
        )
        new_input_kinds = list_values(
            first_present(
                result,
                [
                    "new_input_kinds",
                    "introduced_input_kinds",
                    "positive_input_delta_gate.new_input_kinds",
                    "loop_breaker_packet.new_input_kinds",
                    "result.positive_input_delta_gate.new_input_kinds",
                ],
            )
        )
        supplied_input_paths = list_values(
            first_present(
                result,
                [
                    "supplied_input_artifact_paths",
                    "positive_input_delta_gate.supplied_input_artifact_paths",
                    "loop_breaker_packet.supplied_input_artifact_paths",
                    "loop_breaker_packet.positive_input_delta_gate.supplied_input_artifact_paths",
                    "result.positive_input_delta_gate.supplied_input_artifact_paths",
                ],
            )
        )
        strict_positive_output_delta = boolish(produced_domain_delta) and boolish(changed_vs_previous) and boolish(semantic_progress)
        has_supplied_input_delta = boolish(
            first_present(
                result,
                [
                    "has_supplied_input_delta",
                    "positive_input_delta_gate.has_supplied_input_delta",
                    "loop_breaker_packet.has_supplied_input_delta",
                    "loop_breaker_packet.positive_input_delta_gate.has_supplied_input_delta",
                    "result.positive_input_delta_gate.has_supplied_input_delta",
                ],
            )
        ) or bool(supplied_input_paths) or strict_positive_output_delta
        provider_reattempt_required = boolish(
            first_present(
                result,
                [
                    "provider_reattempt_required",
                    "provider_reattempt_gate.provider_reattempt_required",
                    "loop_breaker_packet.provider_reattempt_gate.provider_reattempt_required",
                    "failure_autopsy_packet.provider_reattempt_required",
                    "result.provider_reattempt_gate.provider_reattempt_required",
                ],
            )
        )
        provider_mitigation_required = boolish(
            first_present(
                result,
                [
                    "provider_mitigation_required",
                    "provider_reattempt_gate.provider_mitigation_required",
                    "loop_breaker_packet.provider_reattempt_gate.provider_mitigation_required",
                    "failure_autopsy_packet.provider_mitigation_required",
                    "result.provider_reattempt_gate.provider_mitigation_required",
                ],
            )
        )
        provider_terminal_seal_allowed = first_present(
            result,
            [
                "provider_terminal_seal_allowed",
                "provider_reattempt_gate.provider_terminal_seal_allowed",
                "loop_breaker_packet.provider_reattempt_gate.provider_terminal_seal_allowed",
                "result.provider_reattempt_gate.provider_terminal_seal_allowed",
            ],
        )
        provider_reattempt_disposition = str(
            first_present(
                result,
                [
                    "provider_reattempt_disposition",
                    "derive.provider_reattempt_disposition",
                    "result.provider_reattempt_disposition",
                    "selected_task.provider_reattempt_disposition",
                ],
            )
            or ""
        ).lower()
        loop_detector_status = str(
            first_present(
                result,
                [
                    "detect_progress_loop_status",
                    "loop_detector_status",
                    "loop_breaker_packet.status",
                    "result.loop_breaker_packet.status",
                ],
            )
            or ""
        ).lower()
        sealed_match = boolish(
            first_present(
                result,
                [
                    "sealed_semantic_family_match",
                    "semantic_signature_gate.sealed_match",
                    "semantic_signature_gate.sealed_matches",
                    "loop_breaker_packet.sealed_semantic_family_match",
                    "result.semantic_signature_gate.sealed_matches",
                ],
            )
        )
        terminal_selected = selected_source == "terminal_blocked" or has_value(result, "terminal_blocker")
        seal_requested_value = first_present(
            result,
            [
                "sealing_blocker_family",
                "seal_family_path",
                "terminal_blocker.seal_family_path",
                "terminal_blocker.sealing_blocker_family",
                "result.terminal_blocker.seal_family_path",
            ],
        )
        seal_requested = boolish(seal_requested_value) or (
            seal_requested_value is not None and str(seal_requested_value).strip().lower() not in {"false", "no", "0", "none"}
        )
        terminal_or_seal = terminal_selected or seal_requested
        root_cause_attempted = boolish(
            first_present(
                result,
                [
                    "root_cause_attempted_for_family",
                    "terminal_blocker.root_cause_attempted_for_family",
                    "loop_breaker_packet.root_cause_attempted_for_family",
                    "result.root_cause_attempted_for_family",
                ],
            )
        )
        root_cause_required = not boolish(
            first_present(
                result,
                [
                    "root_cause_not_required_for_family",
                    "terminal_blocker.root_cause_not_required_for_family",
                    "result.root_cause_not_required_for_family",
                ],
            )
        )
        if terminal_or_seal and root_cause_required and not root_cause_attempted:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "sealed_family_without_root_cause_attempt",
                "Sealing a blocker family requires at least one prior root-cause/autopsy repair attempt or an explicit not-required rationale.",
            )
        untried_root_cause_exists = boolish(
            first_present(
                result,
                [
                    "untried_actionable_root_cause_exists",
                    "anti_loop_progress_gate.untried_actionable_root_cause_exists",
                    "anti_loop_progress_gate.terminal_blocked_invalid_due_to_untried_root_cause",
                    "loop_breaker_packet.untried_actionable_root_cause_exists",
                    "terminal_blocker.untried_actionable_root_cause_exists",
                    "result.anti_loop_progress_gate.untried_actionable_root_cause_exists",
                    "result.terminal_blocker.untried_actionable_root_cause_exists",
                ],
            )
        )
        hypothesis_exhausted = boolish(
            first_present(
                result,
                [
                    "hypothesis_exhausted",
                    "anti_loop_progress_gate.hypothesis_exhausted",
                    "loop_breaker_packet.hypothesis_exhausted",
                    "terminal_blocker.hypothesis_exhausted",
                    "result.anti_loop_progress_gate.hypothesis_exhausted",
                    "result.terminal_blocker.hypothesis_exhausted",
                ],
            )
        )
        untried_veto_overridden_by_chain_stall = boolish(
            first_present(
                result,
                [
                    "untried_veto_overridden_by_chain_stall",
                    "cumulative_untried_chain_without_quality_delta",
                    "anti_loop_progress_gate.untried_veto_overridden_by_chain_stall",
                    "anti_loop_progress_gate.cumulative_untried_chain_without_quality_delta",
                    "loop_breaker_packet.untried_veto_overridden_by_chain_stall",
                    "terminal_blocker.untried_veto_overridden_by_chain_stall",
                    "result.anti_loop_progress_gate.untried_veto_overridden_by_chain_stall",
                    "result.terminal_blocker.untried_veto_overridden_by_chain_stall",
                ],
            )
        )
        if (
            terminal_or_seal
            and untried_root_cause_exists
            and not hypothesis_exhausted
            and not untried_veto_overridden_by_chain_stall
        ):
            add(
                findings,
                "block" if mode == "block" else "warn",
                "terminal_blocked_with_untried_actionable_root_cause",
                "terminal_blocked is invalid while a local, bounded, provider-free, in-scope, authority-allowed root-cause hypothesis remains untried.",
            )
        authorized_alternative_exists = boolish(
            first_present(
                result,
                [
                    "authorized_alternative_path_exists",
                    "sealing_direction_guard.authorized_alternative_path_exists",
                    "terminal_blocker.authorized_alternative_path_exists",
                    "result.sealing_direction_guard.authorized_alternative_path_exists",
                ],
            )
        )
        authorized_alternative_path = first_present(
            result,
            [
                "authorized_alternative_path",
                "sealing_direction_guard.authorized_alternative_path",
                "terminal_blocker.authorized_alternative_path",
                "result.sealing_direction_guard.authorized_alternative_path",
                "result.terminal_blocker.authorized_alternative_path",
            ],
        )
        alternative_in_gt_allowed_value = first_present(
            result,
            [
                "alternative_in_gt_allowed",
                "sealing_direction_guard.alternative_in_gt_allowed",
                "terminal_blocker.alternative_in_gt_allowed",
                "result.sealing_direction_guard.alternative_in_gt_allowed",
                "result.terminal_blocker.alternative_in_gt_allowed",
            ],
        )
        alternative_in_gt_allowed = boolish(alternative_in_gt_allowed_value)
        gt_allowed_alternative_attempted = boolish(
            first_present(
                result,
                [
                    "gt_allowed_alternative_attempted",
                    "sealing_direction_guard.gt_allowed_alternative_attempted",
                    "terminal_blocker.gt_allowed_alternative_attempted",
                    "result.sealing_direction_guard.gt_allowed_alternative_attempted",
                    "result.terminal_blocker.gt_allowed_alternative_attempted",
                ],
            )
        )
        gt_allowed_evidence_paths = list_values(
            first_present(
                result,
                [
                    "gt_allowed_alternative_evidence_paths",
                    "sealing_direction_guard.gt_allowed_alternative_evidence_paths",
                    "terminal_blocker.gt_allowed_alternative_evidence_paths",
                    "result.sealing_direction_guard.gt_allowed_alternative_evidence_paths",
                    "result.terminal_blocker.gt_allowed_alternative_evidence_paths",
                ],
            )
        )
        alternative_attempted = boolish(
            first_present(
                result,
                [
                    "authorized_alternative_path_attempted",
                    "sealing_direction_guard.authorized_alternative_path_attempted",
                    "terminal_blocker.authorized_alternative_path_attempted",
                    "result.sealing_direction_guard.authorized_alternative_path_attempted",
                ],
            )
        )
        if terminal_or_seal and authorized_alternative_exists and not alternative_attempted:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "seal_denied_authorized_alternative_unattempted",
                "A blocker family cannot be sealed while an authority-permitted productive alternative path remains unattempted.",
            )
        if terminal_or_seal and authorized_alternative_exists and not authorized_alternative_path:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "seal_authorized_alternative_path_missing",
                "Sealing with an authorized alternative requires naming the concrete `authorized_alternative_path`.",
            )
        if terminal_or_seal and authorized_alternative_exists and not alternative_in_gt_allowed:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "seal_alternative_not_gt_allowed",
                "The `authorized_alternative_path` must be derived from `.agent_goal` authority/convention allowed actions before it can justify sealing.",
                {
                    "authorized_alternative_path": authorized_alternative_path,
                    "alternative_in_gt_allowed": alternative_in_gt_allowed_value,
                },
            )
        if terminal_or_seal and authorized_alternative_exists and alternative_in_gt_allowed and not gt_allowed_alternative_attempted:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "seal_gt_allowed_alternative_unattempted",
                "A GT-allowed productive alternative must be actually attempted before sealing.",
                {"authorized_alternative_path": authorized_alternative_path},
            )
        if (
            terminal_or_seal
            and authorized_alternative_exists
            and alternative_in_gt_allowed
            and gt_allowed_alternative_attempted
            and not gt_allowed_evidence_paths
        ):
            add(
                findings,
                "block" if mode == "block" else "warn",
                "seal_gt_allowed_alternative_evidence_missing",
                "A GT-allowed alternative attempt must cite non-empty evidence paths before sealing.",
                {"authorized_alternative_path": authorized_alternative_path},
            )
        next_capability_actionable = boolish(
            first_present(
                result,
                [
                    "next_capability_actionable",
                    "capability_ladder_next.actionable",
                    "terminal_blocked_exit_guard.actionable",
                    "terminal_blocker.terminal_blocked_exit_guard.actionable",
                    "result.terminal_blocked_exit_guard.actionable",
                    "result.terminal_blocker.terminal_blocked_exit_guard.actionable",
                ],
            )
        )
        if terminal_selected and next_capability_actionable:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "terminal_blocked_exit_guard_refused",
                "Terminal blocker is invalid while the next capability rung is actionable with current authority/local/bounded inputs.",
            )
        if provider_reattempt_required and (terminal_selected or seal_requested):
            add(
                findings,
                "block" if mode == "block" else "warn",
                "provider_terminal_seal_before_bounded_retry",
                "A transient provider failure with retry authority cannot be terminal-sealed before required mitigation retry/probe evidence.",
            )
        if provider_mitigation_required and provider_terminal_seal_allowed is False and (terminal_selected or seal_requested):
            add(
                findings,
                "block" if mode == "block" else "warn",
                "provider_terminal_seal_before_mitigation_exhausted",
                "A transient provider failure cannot justify terminal sealing while required mitigations remain unexhausted.",
            )
        if provider_reattempt_required and not terminal_selected and provider_reattempt_disposition not in {"selected_bounded_retry", "selected_bounded_provider_retry", "selected_probe_retry"}:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "provider_reattempt_disposition_missing",
                "`derive` must record that it selected a bounded provider retry/probe task or explain why the provider reattempt gate no longer applies.",
                {"provider_reattempt_disposition": provider_reattempt_disposition or None},
            )
        if goal_distance_required and not terminal_selected and progress_kind != "goal_productive":
            add(
                findings,
                "block" if mode == "block" else "warn",
                "goal_distance_gate_unmet",
                "Goal-distance gate requires a goal-productive selected task or terminal blocker state.",
                {"cycles_since_goal_productive_output": cycles_since_goal_productive, "threshold": goal_threshold, "progress_kind": progress_kind or None},
            )
        if loop_detector_status == "block" and not terminal_selected and progress_kind != "goal_productive":
            add(
                findings,
                "block" if mode == "block" else "warn",
                "loop_detector_block_unhandled",
                "`detect_progress_loop status=block` allows only a goal-productive selected task or terminal blocker state.",
                {"progress_kind": progress_kind or None},
            )
        if terminal_selected and (goal_distance_required or loop_detector_status == "block"):
            dual_track_attempted = boolish(
                first_present(
                    result,
                    [
                        "dual_track_attempt_evidence",
                        "terminal_blocker.dual_track_attempt_evidence",
                        "terminal_blocker.dual_track_attempted",
                        "result.terminal_blocker.dual_track_attempt_evidence",
                    ],
                )
            )
            provider_track_attempted = boolish(first_present(result, ["provider_track_attempted", "terminal_blocker.provider_track_attempted"]))
            quality_track_attempted = boolish(
                first_present(
                    result,
                    [
                        "provider_neutral_or_quality_track_attempted",
                        "quality_or_provider_neutral_track_attempted",
                        "terminal_blocker.provider_neutral_or_quality_track_attempted",
                        "terminal_blocker.quality_or_provider_neutral_track_attempted",
                    ],
                )
            )
            if not (dual_track_attempted or (provider_track_attempted and quality_track_attempted)):
                add(
                    findings,
                    "block" if mode == "block" else "warn",
                    "terminal_blocker_missing_dual_track_attempt_evidence",
                    "Terminal blocker after a hard progress-loop gate must cite provider-track and provider-neutral/quality-track attempt evidence.",
                )
        if governance_only_streak is not None and governance_only_streak >= 2 and not terminal_selected and progress_kind != "goal_productive":
            add(
                findings,
                "block" if mode == "block" else "warn",
                "governance_only_streak_unmet",
                "After two governance-only cycles, derive must select goal-productive work or terminal blocker state.",
                {"governance_only_streak": governance_only_streak, "progress_kind": progress_kind or None},
            )
        autonomous_retarget_disabled = boolish(
            first_present(
                result,
                [
                    "autonomous_retarget_disabled",
                    "hard_stop_required",
                    "root_axis_gate.autonomous_retarget_disabled",
                    "root_axis_gate.hard_stop_required",
                    "loop_breaker_packet.autonomous_retarget_disabled",
                    "loop_breaker_packet.hard_stop_required",
                    "loop_breaker_packet.root_axis_gate.autonomous_retarget_disabled",
                    "result.root_axis_gate.autonomous_retarget_disabled",
                ],
            )
        )
        if autonomous_retarget_disabled and not terminal_selected and progress_kind != "goal_productive":
            add(
                findings,
                "block" if mode == "block" else "warn",
                "autonomous_retarget_disabled_unhandled",
                "A root-axis hard stop allows only goal-productive derivation or terminal/user-escalation state.",
                {"progress_kind": progress_kind or None},
            )
        gt_conflict_blocked = boolish(
            first_present(
                result,
                [
                    "gt_constraint_conflict_packet.requires_conflict_resolution_task",
                    "gt_constraint_conflict_packet.status",
                    "loop_breaker_packet.gt_constraint_conflict_packet.requires_conflict_resolution_task",
                    "result.gt_constraint_conflict_packet.requires_conflict_resolution_task",
                    "result.gt_constraint_conflict_packet.status",
                ],
            )
        )
        resolves_gt_conflict = boolish(
            first_present(
                result,
                [
                    "resolves_gt_constraint_conflict",
                    "conflict_resolution_task_selected",
                    "selected_task.resolves_gt_constraint_conflict",
                    "derive.resolves_gt_constraint_conflict",
                    "result.resolves_gt_constraint_conflict",
                ],
            )
        )
        selected_task_kind = str(
            first_present(
                result,
                [
                    "selected_task_kind",
                    "selected_task.task_kind",
                    "derive.selected_task_kind",
                    "result.selected_task_kind",
                ],
            )
            or ""
        ).lower()
        if selected_task_kind in {"gt_constraint_conflict_resolution", "conflict_resolution", "authority_conflict_resolution"}:
            resolves_gt_conflict = True
        if gt_conflict_blocked and not terminal_selected and not resolves_gt_conflict:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "gt_constraint_conflict_unhandled",
                "A GT/task constraint conflict requires explicit conflict-resolution, contradiction-removing work, or terminal/user-escalation state.",
                {"progress_kind": progress_kind or None, "selected_task_kind": selected_task_kind or None},
            )
        if new_input_kinds and not has_supplied_input_delta:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "named_only_input_delta",
                "`new_input_kinds` alone is not a positive input delta; provide non-empty artifact paths or produced_domain_delta=true.",
                {"new_input_kinds": new_input_kinds},
            )
        if sealed_match and not terminal_selected and not has_supplied_input_delta:
            add(
                findings,
                "block",
                "sealed_semantic_family_without_input_delta",
                "A sealed semantic blocker family cannot produce another non-terminal derive result without a supplied input artifact or positive output delta.",
            )
        command_budget_required = boolish(
            first_present(
                result,
                [
                    "command_surface_budget.consolidation_candidate_required",
                    "loop_breaker_packet.command_surface_budget.consolidation_candidate_required",
                    "result.command_surface_budget.consolidation_candidate_required",
                ],
            )
        )
        consolidation_registered = boolish(
            first_present(
                result,
                [
                    "consolidation_candidate_registered",
                    "command_surface_budget.consolidation_candidate_registered",
                    "result.consolidation_candidate_registered",
                ],
            )
        )
        if (
            command_budget_required
            and not consolidation_registered
            and not terminal_selected
            and not strict_positive_output_delta
            and not (force_implementation_cycle and allowed_force_impl_class)
        ):
            add(
                findings,
                "block" if mode == "block" else "warn",
                "command_surface_budget_unhandled",
                "Command-surface budget requires consolidation, terminal state, or strict changed-and-semantic output-delta evidence.",
            )
    if target == "loopback_audit":
        evidence_class = str(value_for(result, "evidence_class") or "").lower()
        disposition = str(value_for(result, "recommended_disposition") or "").lower()
        semantic_progress = boolish(value_for(result, "semantic_progress"))
        hard_stop = boolish(value_for(result, "hard_stop_required"))
        measurement_progress_allowed = boolish(value_for(result, "measurement_progress_allowed"))
        substance_delta_pass = boolish(deep_get(result, "substance_delta_gate.substance_delta_pass"))
        vacuous_corrective_noop = boolish(deep_get(result, "vacuous_corrective_gate.surface_corrective_noop"))
        adapter_mandate_required = boolish(value_for(result, "adapter_mandate_required"))
        adapter_wiring_defect = boolish(value_for(result, "adapter_wiring_defect"))
        cumulative_chain_stalled = boolish(value_for(result, "cumulative_goal_distance_stalled"))
        chain_stall_streak = number_value(value_for(result, "cumulative_goal_distance_stall_streak")) or 0
        chain_stall_cap = number_value(deep_get(result, "cumulative_goal_distance_gate.cumulative_goal_distance_stall_cap")) or number_value(value_for(result, "cumulative_goal_distance_stall_cap")) or 0
        untried_veto_overridden = boolish(value_for(result, "untried_veto_overridden_by_chain_stall"))
        forced_retarget_gate = deep_get(result, "chain_stall_forced_retarget_gate")
        forced_retarget_options = deep_get(result, "forced_selected_task_options")
        acceptance_unreachable = boolish(value_for(result, "acceptance_unreachable_under_frozen_config"))
        unverifiable_acceptance = boolish(value_for(result, "unverifiable_acceptance_contract"))
        metric_goal_productive_excluded = boolish(deep_get(result, "oracle_metric_validity_gate.metric_goal_productive_excluded"))
        pass_with_coupled_verifier = boolish(value_for(result, "pass_with_coupled_verifier")) or boolish(deep_get(result, "coupled_verifier_gate.pass_with_coupled_verifier"))
        attested_only_movement = boolish(value_for(result, "attested_only_movement")) or boolish(deep_get(result, "evidence_provenance_gate.attested_only_movement")) or boolish(deep_get(result, "primary_metric_gate.attested_only_movement"))
        pass_with_unobserved_axes = boolish(value_for(result, "pass_with_unobserved_axes")) or boolish(deep_get(result, "goal_axis_completeness_gate.pass_with_unobserved_axes"))
        unobserved_goal_axes = value_for(result, "unobserved_goal_axes") or deep_get(result, "goal_axis_completeness_gate.unobserved_goal_axes")
        generation_dependent_count_key = boolish(value_for(result, "generation_dependent_count_key")) or boolish(deep_get(result, "count_key_hygiene_gate.generation_dependent_count_key"))
        effective_count_key = (
            value_for(result, "effective_count_key")
            or deep_get(result, "count_key_hygiene_gate.effective_count_key")
            or value_for(result, "root_dominant_parameter_key")
            or value_for(result, "terminal_outcome_family_key")
        )
        generation_key_novelty_claim = boolish(value_for(result, "family_novelty_claim")) or boolish(value_for(result, "stall_reset_claim")) or boolish(deep_get(result, "count_key_hygiene_gate.family_novelty_claim")) or boolish(deep_get(result, "count_key_hygiene_gate.stall_reset_claim"))
        residual_cost_below_policy = boolish(value_for(result, "residual_gap_cost_below_policy")) or boolish(value_for(result, "value_per_cycle_cost_below_policy")) or boolish(deep_get(result, "residual_gap_cost_policy.below_policy"))
        primary_metric_high_water_moved = boolish(value_for(result, "primary_metric_high_water_moved")) or boolish(deep_get(result, "primary_metric_gate.primary_metric_high_water_moved"))
        primary_metric_stalled = boolish(value_for(result, "primary_metric_stalled")) or boolish(deep_get(result, "primary_metric_gate.primary_metric_stalled"))
        c4_user_escalation = boolish(value_for(result, "c4_user_escalation_backstop_required")) or boolish(deep_get(result, "primary_metric_gate.c4_user_escalation_backstop_required"))
        terminal_stage_contradiction = boolish(value_for(result, "terminal_classification_stage_contradiction")) or boolish(deep_get(result, "failure_surface_stage_gate.terminal_classification_stage_contradiction"))
        terminal_classification_invalid_for_counting = boolish(value_for(result, "terminal_classification_invalid_for_counting")) or boolish(deep_get(result, "failure_surface_stage_gate.terminal_classification_invalid_for_counting"))
        same_input_contract_violation = boolish(value_for(result, "same_input_contract_violation")) or boolish(deep_get(result, "same_input_contract_gate.same_input_contract_violation"))
        instrumentation_supply_required = boolish(value_for(result, "instrumentation_supply_required")) or boolish(deep_get(result, "diagnostics_unavailable_gate.instrumentation_supply_required"))
        independent_source_status = str(
            value_for(result, "independent_source_separation_status")
            or deep_get(result, "verification_source_separation_gate.independent_source_separation_status")
            or deep_get(result, "evidence_provenance_gate.independent_source_separation_status")
            or ""
        ).lower()
        independently_verified_downgraded_fields = list_values(
            value_for(result, "independently_verified_downgraded_fields")
            or deep_get(result, "verification_source_separation_gate.independently_verified_downgraded_fields")
            or deep_get(result, "evidence_provenance_gate.independently_verified_downgraded_fields")
        )
        envelope_thaw_item_required = boolish(value_for(result, "envelope_thaw_item_required")) or boolish(deep_get(result, "acceptance_reachability_gate.envelope_thaw_item_required"))
        envelope_thaw_item = value_for(result, "envelope_thaw_item") or deep_get(result, "acceptance_reachability_gate.envelope_thaw_item")
        scenario_uncovered = boolish(value_for(result, "scenario_uncovered")) or boolish(deep_get(result, "acceptance_scenario_gate.scenario_uncovered"))
        acceptance_inversion = boolish(value_for(result, "acceptance_inversion")) or boolish(deep_get(result, "acceptance_scenario_gate.acceptance_inversion"))
        command_provenance_missing = boolish(value_for(result, "command_provenance_missing")) or boolish(deep_get(result, "command_provenance_gate.command_provenance_missing"))
        repeated_blocker_opacity = boolish(value_for(result, "repeated_blocker_opacity")) or boolish(deep_get(result, "blocker_actionability_gate.repeated_blocker_opacity"))
        predetermined_unreachable = boolish(value_for(result, "predetermined_unreachable")) or boolish(deep_get(result, "stochastic_feasibility_gate.predetermined_unreachable"))
        floor_edge_envelope = boolish(value_for(result, "floor_edge_envelope")) or boolish(deep_get(result, "stochastic_feasibility_gate.floor_edge_envelope"))
        instrumentation_first_fire = boolish(value_for(result, "instrumentation_first_fire")) or boolish(deep_get(result, "instrumentation_first_fire_gate.instrumentation_first_fire"))
        first_fire_consumed_item_id = value_for(result, "first_fire_consumed_item_id") or deep_get(result, "instrumentation_first_fire_gate.first_fire_consumed_item_id")
        first_fire_double_counted = boolish(value_for(result, "first_fire_double_counted")) or boolish(deep_get(result, "instrumentation_first_fire_gate.first_fire_double_counted"))
        blocker_mutation = str(value_for(result, "blocker_mutation_kind") or "").lower()
        forward_mutation_progress = blocker_mutation == "forward_mutation"
        terminal_outcome_value = value_for(result, "terminal_outcome_changed")
        terminal_outcome_changed = (
            boolish(terminal_outcome_value)
            if terminal_outcome_value is not None
            else boolish(value_for(result, "changed_vs_previous")) and boolish(value_for(result, "semantic_progress"))
        )
        forward_mutation_vacuous = boolish(value_for(result, "forward_mutation_vacuous"))
        count_value = value_for(result, "same_family_micro_hardening_count")
        try:
            streak_count = int(str(count_value))
        except (TypeError, ValueError):
            streak_count = None
        if evidence_class == "insufficient_evidence" and not (measurement_progress_allowed or forward_mutation_progress) and (disposition != "conservative_hold" or not hard_stop):
            add(
                findings,
                "block" if mode == "block" else "warn",
                "loopback_insufficient_not_fail_closed",
                "`loopback_audit` insufficient evidence must use conservative_hold with hard_stop_required=true.",
            )
        if streak_count is not None and streak_count >= 3 and not semantic_progress and not hard_stop and not (measurement_progress_allowed or forward_mutation_progress):
            add(
                findings,
                "block" if mode == "block" else "warn",
                "loopback_streak_without_hard_stop",
                "`loopback_audit` same-family micro-hardening count >=3 without semantic progress must hard-stop.",
                {"same_family_micro_hardening_count": streak_count},
            )
        if forward_mutation_progress and (forward_mutation_vacuous or not terminal_outcome_changed) and not hard_stop:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "loopback_forward_mutation_without_terminal_outcome_delta",
                "`loopback_audit` must not leave ladder forward mutation open without observed terminal outcome change or a hard stop.",
            )
        if forward_mutation_progress and not substance_delta_pass and not terminal_outcome_changed and not hard_stop:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "loopback_forward_mutation_without_substance_delta",
                "`loopback_audit` must not leave ladder forward mutation open without G-SUBSTANCE pass, strict terminal outcome delta, or a hard stop.",
            )
        if vacuous_corrective_noop and semantic_progress:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "loopback_vacuous_corrective_claimed_semantic_progress",
                "`loopback_audit` reported semantic_progress while G-VACUOUS found attempted corrective lanes with zero resolved items.",
            )
        if adapter_mandate_required and not hard_stop:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "loopback_adapter_mandate_without_hard_stop",
                "`loopback_audit` adapter_mandate_required=true must hard-stop ordinary domain repair and force adapter registration/strengthening or escalation.",
            )
        if adapter_wiring_defect and (adapter_mandate_required or disposition != "self_inflicted_gate_defect" or not hard_stop):
            add(
                findings,
                "block" if mode == "block" else "warn",
                "loopback_adapter_wiring_defect_misrouted",
                "`loopback_audit` must route a registered-but-unloaded adapter as self_inflicted_gate_defect, not adapter absence.",
            )
        if cumulative_chain_stalled and not adapter_mandate_required and not hard_stop:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "loopback_cumulative_chain_without_hard_stop",
                "`loopback_audit` cumulative goal-distance stall must hard-stop unless G-ADAPTER is the active preceding mandate.",
            )
        if (
            cumulative_chain_stalled
            and not adapter_mandate_required
            and chain_stall_cap > 0
            and chain_stall_streak >= chain_stall_cap * 2
            and blocker_mutation in {"facet_rename", "lateral", "repeat"}
        ):
            gate_present = isinstance(forced_retarget_gate, dict) and boolish(forced_retarget_gate.get("chain_stall_force_retarget"))
            options_present = isinstance(forced_retarget_options, list)
            if not gate_present or not options_present:
                add(
                    findings,
                    "block" if mode == "block" else "warn",
                    "loopback_chain_stall_forced_retarget_missing",
                    "`loopback_audit` must enumerate forced retarget alternatives when cumulative goal-distance stall reaches cap*2.",
                    {"cumulative_goal_distance_stall_streak": chain_stall_streak, "cumulative_goal_distance_stall_cap": chain_stall_cap},
                )
        if untried_veto_overridden and not cumulative_chain_stalled:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "loopback_untried_override_without_chain_stall",
                "`untried_veto_overridden_by_chain_stall` requires cumulative goal-distance stall evidence.",
            )
        if acceptance_unreachable and not boolish(value_for(result, "relaxation_or_escalation_required")):
            add(
                findings,
                "block" if mode == "block" else "warn",
                "loopback_unreachable_acceptance_without_relaxation_gate",
                "`acceptance_unreachable_under_frozen_config` requires `relaxation_or_escalation_required=true`.",
            )
        if unverifiable_acceptance and not hard_stop:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "loopback_unverifiable_acceptance_without_hard_stop",
                "`unverifiable_acceptance_contract=true` means a required live verifier was not evaluated; the packet must hard-stop target consumption.",
            )
        if metric_goal_productive_excluded and semantic_progress and measurement_progress_allowed:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "loopback_tautological_metric_claimed_progress",
                "Tautological oracle/metric validity must not support semantic or measurement goal-productive progress without independent output-delta evidence.",
            )
        if pass_with_coupled_verifier and (not hard_stop or disposition == "goal_productive"):
            add(
                findings,
                "block" if mode == "block" else "warn",
                "loopback_coupled_verifier_consumable_as_pass",
                "`loopback_audit` must treat pass_with_coupled_verifier as not-pass and hard-stop target consumption.",
            )
        if attested_only_movement and (primary_metric_high_water_moved or measurement_progress_allowed or disposition == "goal_productive"):
            add(
                findings,
                "block" if mode == "block" else "warn",
                "loopback_attested_only_movement_counted_as_progress",
                "`loopback_audit` must not let producer-attested movement update high-water, allow measurement progress, or route goal_productive.",
            )
        if (pass_with_unobserved_axes or non_empty(unobserved_goal_axes)) and (not hard_stop or disposition == "goal_productive"):
            add(
                findings,
                "block" if mode == "block" else "warn",
                "loopback_unobserved_axes_consumable_as_pass",
                "`loopback_audit` must treat pass_with_unobserved_axes as not-pass for measurable goals and hard-stop target consumption.",
                {"unobserved_goal_axes": unobserved_goal_axes or None},
            )
        if generation_dependent_count_key and not effective_count_key:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "loopback_generation_count_key_without_effective_key",
                "Generation-dependent count-key material is trace-only; loopback must emit an effective adapter-collapsed key or terminal-outcome fallback.",
            )
        if generation_dependent_count_key and generation_key_novelty_claim:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "loopback_generation_key_claimed_family_reset",
                "`loopback_audit` must not use task/advice/pack/cycle/run/date/hash/version key churn as family novelty, stall reset, hypothesis exhaustion, or seal escape.",
            )
        if residual_cost_below_policy and disposition == "goal_productive":
            add(
                findings,
                "block" if mode == "block" else "warn",
                "loopback_residual_cost_below_policy_goal_productive",
                "`loopback_audit` must not route below-policy residual value per cycle cost as ordinary goal_productive repair.",
            )
        if primary_metric_stalled and not hard_stop:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "loopback_primary_metric_stall_without_hard_stop",
                "`loopback_audit` primary_metric_stalled=true must hard-stop ordinary progress and route forced retargeting or user escalation.",
            )
        if c4_user_escalation and disposition != "user_escalation":
            add(
                findings,
                "block" if mode == "block" else "warn",
                "loopback_c4_user_escalation_misrouted",
                "`loopback_audit` C4 user-escalation backstop must route to user_escalation when no forced option is actionable.",
            )
        if (terminal_stage_contradiction or terminal_classification_invalid_for_counting) and (disposition == "goal_productive" or not hard_stop):
            add(
                findings,
                "block" if mode == "block" else "warn",
                "loopback_terminal_classification_stage_not_fail_closed",
                "`loopback_audit` contradictory terminal classification must be invalid for counting/close and hard-stop target consumption.",
            )
        if same_input_contract_violation and (disposition == "goal_productive" or not hard_stop):
            add(
                findings,
                "block" if mode == "block" else "warn",
                "loopback_same_input_contract_not_fail_closed",
                "`loopback_audit` same-condition input-set mismatch must hard-stop counting until the comparison contract is repaired.",
            )
        if instrumentation_supply_required and (disposition == "goal_productive" or not hard_stop):
            add(
                findings,
                "block" if mode == "block" else "warn",
                "loopback_instrumentation_supply_not_fail_closed",
                "`loopback_audit` repeated diagnostics_unavailable must force instrumentation supply or an explicit observability rationale, not ordinary goal_productive routing.",
            )
        if independent_source_status in {"missing", "overlap", "blocked"} and (primary_metric_high_water_moved or measurement_progress_allowed or disposition == "goal_productive"):
            add(
                findings,
                "block" if mode == "block" else "warn",
                "loopback_independent_verification_source_not_disjoint_counted",
                "`loopback_audit` must downgrade independently_verified evidence to attested when verification inputs are missing or overlap verified artifacts.",
                {"independent_source_separation_status": independent_source_status},
            )
        if independently_verified_downgraded_fields and (primary_metric_high_water_moved or measurement_progress_allowed or disposition == "goal_productive"):
            add(
                findings,
                "block" if mode == "block" else "warn",
                "loopback_downgraded_independent_verification_counted",
                "`loopback_audit` must not count auto-downgraded independently_verified fields as primary progress.",
                {"downgraded_fields": independently_verified_downgraded_fields},
            )
        if envelope_thaw_item_required and (disposition == "goal_productive" or not hard_stop or not non_empty(envelope_thaw_item)):
            add(
                findings,
                "block" if mode == "block" else "warn",
                "loopback_envelope_thaw_item_not_reserved",
                "`loopback_audit` must reserve an envelope_thaw_item and hard-stop when acceptance is unreachable under a frozen envelope.",
            )
        if (scenario_uncovered or acceptance_inversion) and (disposition == "goal_productive" or not hard_stop):
            add(
                findings,
                "block" if mode == "block" else "warn",
                "loopback_acceptance_scenario_not_fail_closed",
                "`loopback_audit` must fail closed on uncovered or inverted acceptance scenarios until scenario supply or code/contract repair is selected.",
            )
        if command_provenance_missing and (disposition == "goal_productive" or measurement_progress_allowed):
            add(
                findings,
                "block" if mode == "block" else "warn",
                "loopback_command_provenance_missing_counted",
                "`loopback_audit` must not count a missing-argv live run as baseline, comparison, A/B, reproduction, or measurement-progress evidence.",
            )
        if repeated_blocker_opacity and disposition == "goal_productive":
            add(
                findings,
                "block" if mode == "block" else "warn",
                "loopback_repeated_blocker_opacity_goal_productive",
                "`loopback_audit` must route repeated same-gate blocker_opacity to blocker-contract repair instead of ordinary goal_productive work.",
            )
        if (predetermined_unreachable or floor_edge_envelope) and (disposition == "goal_productive" or not hard_stop):
            add(
                findings,
                "block" if mode == "block" else "warn",
                "loopback_stochastic_contract_infeasible_not_fail_closed",
                "`loopback_audit` must treat exact-match and floor-edge stochastic findings as contract-revision blockers, not retryable goal_productive progress.",
            )
        if instrumentation_first_fire and not non_empty(first_fire_consumed_item_id):
            add(
                findings,
                "block" if mode == "block" else "warn",
                "loopback_first_fire_without_consumed_item",
                "`loopback_audit` must attach instrumentation_first_fire to exactly one consumed workflow item.",
            )
        if instrumentation_first_fire and first_fire_double_counted:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "loopback_first_fire_double_counted",
                "`loopback_audit` must not double-count instrumentation_first_fire as both first-fire evidence and goal progress or instrumentation-supply consumption.",
            )
    if target == "validate":
        validation_verdict = str(value_for(result, "validation_verdict") or "").strip().lower()
        progress_verdict = str(value_for(result, "progress_verdict") or "").strip().lower()
        acceptance_diluted = boolish(
            first_present(
                result,
                [
                    "acceptance_diluted",
                    "acceptance_provenance_gate.acceptance_diluted",
                    "scope_fidelity_gate.acceptance_diluted",
                    "result.acceptance_provenance_gate.acceptance_diluted",
                ],
            )
        )
        target_met = boolish(
            first_present(
                result,
                [
                    "acceptance_target_met",
                    "acceptance_provenance_gate.target_met",
                    "scope_fidelity_gate.target_met",
                    "result.acceptance_provenance_gate.target_met",
                ],
            )
        )
        explicit_descope = boolish(
            first_present(
                result,
                [
                    "explicit_descope_decision",
                    "acceptance_provenance_gate.explicit_descope_decision",
                    "scope_fidelity_gate.explicit_descope_decision",
                    "result.acceptance_provenance_gate.explicit_descope_decision",
                ],
            )
        )
        measurable_target_required = boolish(
            first_present(
                result,
                [
                    "measurable_target_required",
                    "acceptance_provenance_gate.measurable_target_required",
                    "scope_fidelity_gate.measurable_target_required",
                    "task_pack_item.scope_fidelity.measurable_target_required",
                    "result.acceptance_provenance_gate.measurable_target_required",
                ],
            )
        )
        unverifiable_acceptance = boolish(
            first_present(
                result,
                [
                    "unverifiable_acceptance_contract",
                    "acceptance_verifier_gate.unverifiable_acceptance_contract",
                    "acceptance_verifier_contract.unverifiable_acceptance_contract",
                    "result.acceptance_verifier_gate.unverifiable_acceptance_contract",
                ],
            )
        )
        required_verifier_not_evaluated = boolish(
            first_present(
                result,
                [
                    "acceptance_verifier_not_evaluated",
                    "acceptance_verifier_gate.acceptance_verifier_not_evaluated",
                    "acceptance_verifier_contract.acceptance_verifier_not_evaluated",
                    "result.acceptance_verifier_gate.acceptance_verifier_not_evaluated",
                ],
            )
        )
        pass_with_coupled_verifier = boolish(
            first_present(
                result,
                [
                    "pass_with_coupled_verifier",
                    "coupled_verifier_gate.pass_with_coupled_verifier",
                    "acceptance_verifier_gate.pass_with_coupled_verifier",
                    "anti_loop_progress_gate.pass_with_coupled_verifier",
                    "result.coupled_verifier_gate.pass_with_coupled_verifier",
                    "result.anti_loop_progress_gate.pass_with_coupled_verifier",
                ],
            )
        )
        non_coupled_revalidated = boolish(
            first_present(
                result,
                [
                    "non_coupled_revalidation_passed",
                    "coupled_verifier_gate.non_coupled_revalidation_passed",
                    "acceptance_verifier_gate.non_coupled_revalidation_passed",
                    "independent_evidence_recalculation_passed",
                    "evidence_provenance_gate.independent_evidence_recalculation_passed",
                ],
            )
        )
        attested_only_movement = boolish(
            first_present(
                result,
                [
                    "attested_only_movement",
                    "evidence_provenance_gate.attested_only_movement",
                    "anti_loop_progress_gate.attested_only_movement",
                    "primary_metric_gate.attested_only_movement",
                    "result.evidence_provenance_gate.attested_only_movement",
                    "result.anti_loop_progress_gate.attested_only_movement",
                ],
            )
        )
        pass_with_unobserved_axes = boolish(
            first_present(
                result,
                [
                    "pass_with_unobserved_axes",
                    "goal_axis_completeness_gate.pass_with_unobserved_axes",
                    "anti_loop_progress_gate.pass_with_unobserved_axes",
                    "result.goal_axis_completeness_gate.pass_with_unobserved_axes",
                    "result.anti_loop_progress_gate.pass_with_unobserved_axes",
                ],
            )
        )
        unobserved_goal_axes = first_present(
            result,
            [
                "unobserved_goal_axes",
                "goal_axis_completeness_gate.unobserved_goal_axes",
                "anti_loop_progress_gate.unobserved_goal_axes",
                "result.goal_axis_completeness_gate.unobserved_goal_axes",
                "result.anti_loop_progress_gate.unobserved_goal_axes",
            ],
        )
        generation_dependent_count_key = boolish(
            first_present(
                result,
                [
                    "generation_dependent_count_key",
                    "count_key_hygiene_gate.generation_dependent_count_key",
                    "anti_loop_progress_gate.generation_dependent_count_key",
                    "anti_loop_progress_gate.count_key_hygiene_gate.generation_dependent_count_key",
                    "result.anti_loop_progress_gate.generation_dependent_count_key",
                ],
            )
        )
        generation_key_novelty_claim = boolish(
            first_present(
                result,
                [
                    "family_novelty_claim",
                    "new_family_claim",
                    "stall_reset_claim",
                    "count_key_hygiene_gate.family_novelty_claim",
                    "count_key_hygiene_gate.stall_reset_claim",
                    "anti_loop_progress_gate.count_key_hygiene_gate.family_novelty_claim",
                    "result.anti_loop_progress_gate.count_key_hygiene_gate.stall_reset_claim",
                ],
            )
        )
        residual_cost_below_policy = boolish(
            first_present(
                result,
                [
                    "residual_gap_cost_below_policy",
                    "value_per_cycle_cost_below_policy",
                    "cost_disproportionate_residual",
                    "residual_gap_cost_policy.below_policy",
                    "anti_loop_progress_gate.residual_gap_cost_policy.below_policy",
                    "result.anti_loop_progress_gate.residual_gap_cost_policy.below_policy",
                ],
            )
        )
        marginal_repair_override = boolish(
            first_present(
                result,
                [
                    "marginal_repair_higher_value",
                    "residual_gap_policy.marginal_repair_higher_value",
                    "residual_gap_cost_policy.marginal_repair_higher_value",
                    "anti_loop_progress_gate.marginal_repair_higher_value",
                    "result.anti_loop_progress_gate.marginal_repair_higher_value",
                ],
            )
        )
        producer_attested_fields = first_present(
            result,
            [
                "producer_attested_fields",
                "evidence_provenance_gate.producer_attested_fields",
                "anti_loop_progress_gate.producer_attested_fields",
                "result.evidence_provenance_gate.producer_attested_fields",
            ],
        )
        independently_verified_fields = first_present(
            result,
            [
                "independently_verified_fields",
                "evidence_provenance_gate.independently_verified_fields",
                "anti_loop_progress_gate.independently_verified_fields",
                "result.evidence_provenance_gate.independently_verified_fields",
            ],
        )
        independent_source_status = str(
            first_present(
                result,
                [
                    "independent_source_separation_status",
                    "verification_source_separation_gate.independent_source_separation_status",
                    "evidence_provenance_gate.independent_source_separation_status",
                    "anti_loop_progress_gate.independent_source_separation_status",
                    "result.verification_source_separation_gate.independent_source_separation_status",
                    "result.anti_loop_progress_gate.independent_source_separation_status",
                ],
            )
            or ""
        ).lower()
        independently_verified_downgraded_fields = list_values(
            first_present(
                result,
                [
                    "independently_verified_downgraded_fields",
                    "verification_source_separation_gate.independently_verified_downgraded_fields",
                    "evidence_provenance_gate.independently_verified_downgraded_fields",
                    "anti_loop_progress_gate.independently_verified_downgraded_fields",
                    "result.verification_source_separation_gate.independently_verified_downgraded_fields",
                    "result.anti_loop_progress_gate.independently_verified_downgraded_fields",
                ],
            )
        )
        envelope_thaw_item_required = boolish(
            first_present(
                result,
                [
                    "envelope_thaw_item_required",
                    "acceptance_reachability_gate.envelope_thaw_item_required",
                    "anti_loop_progress_gate.envelope_thaw_item_required",
                    "result.acceptance_reachability_gate.envelope_thaw_item_required",
                    "result.anti_loop_progress_gate.envelope_thaw_item_required",
                ],
            )
        )
        envelope_thaw_item = first_present(
            result,
            [
                "envelope_thaw_item",
                "acceptance_reachability_gate.envelope_thaw_item",
                "anti_loop_progress_gate.envelope_thaw_item",
                "result.acceptance_reachability_gate.envelope_thaw_item",
                "result.anti_loop_progress_gate.envelope_thaw_item",
            ],
        )
        terminal_stage_contradiction = boolish(
            first_present(
                result,
                [
                    "terminal_classification_stage_contradiction",
                    "failure_surface_stage_gate.terminal_classification_stage_contradiction",
                    "anti_loop_progress_gate.terminal_classification_stage_contradiction",
                    "result.anti_loop_progress_gate.terminal_classification_stage_contradiction",
                ],
            )
        )
        same_input_contract_violation = boolish(
            first_present(
                result,
                [
                    "same_input_contract_violation",
                    "same_input_contract_gate.same_input_contract_violation",
                    "anti_loop_progress_gate.same_input_contract_violation",
                    "result.anti_loop_progress_gate.same_input_contract_violation",
                ],
            )
        )
        instrumentation_supply_required = boolish(
            first_present(
                result,
                [
                    "instrumentation_supply_required",
                    "diagnostics_unavailable_gate.instrumentation_supply_required",
                    "anti_loop_progress_gate.instrumentation_supply_required",
                    "result.anti_loop_progress_gate.instrumentation_supply_required",
                ],
            )
        )
        expectation_lineage_stale = boolish(
            first_present(
                result,
                [
                    "expectation_lineage_stale",
                    "expectation_lineage_gate.expectation_lineage_stale",
                    "anti_loop_progress_gate.expectation_lineage_stale",
                    "result.expectation_lineage_gate.expectation_lineage_stale",
                ],
            )
        )
        expectation_anchor_missing = boolish(
            first_present(
                result,
                [
                    "expectation_anchor_missing",
                    "expectation_lineage_gate.expectation_anchor_missing",
                    "anti_loop_progress_gate.expectation_anchor_missing",
                    "result.expectation_lineage_gate.expectation_anchor_missing",
                ],
            )
        )
        expectation_rebaselined = boolish(
            first_present(
                result,
                [
                    "expectation_rebaselined",
                    "expectation_lineage_gate.expectation_rebaselined",
                    "designated_baseline_recomputed",
                    "result.expectation_lineage_gate.expectation_rebaselined",
                ],
            )
        )
        lineage_verified_expectation_claim = boolish(
            first_present(
                result,
                [
                    "lineage_verified_expectation_claim",
                    "expectation_lineage_verified_claim",
                    "baseline_lineage_claim",
                    "comparison_lineage_claim",
                    "expectation_lineage_gate.lineage_verified_expectation_claim",
                ],
            )
        )
        comparison_contract = boolish(
            first_present(
                result,
                [
                    "comparison_contract",
                    "comparison_claim",
                    "baseline_claim",
                    "adoption_claim",
                    "comparison_parity_gate.comparison_contract",
                    "result.comparison_parity_gate.comparison_contract",
                ],
            )
        )
        parity_axis_status_value = first_present(
            result,
            [
                "parity_axis_status",
                "parity_axes_status",
                "comparison_parity_gate.parity_axis_status",
                "comparison_parity_gate.parity_axes",
                "anti_loop_progress_gate.comparison_parity_gate.parity_axis_status",
                "result.comparison_parity_gate.parity_axis_status",
            ],
        )
        if isinstance(parity_axis_status_value, (dict, list)):
            parity_axis_status_text = json.dumps(parity_axis_status_value, sort_keys=True, ensure_ascii=False).lower()
        else:
            parity_axis_status_text = str(parity_axis_status_value or "").lower()
        parity_unverified = boolish(
            first_present(
                result,
                [
                    "parity_unverified",
                    "comparison_parity_gate.parity_unverified",
                    "anti_loop_progress_gate.parity_unverified",
                    "result.comparison_parity_gate.parity_unverified",
                ],
            )
        )
        unknown_parity_axes = list_values(
            first_present(
                result,
                [
                    "unknown_parity_axes",
                    "parity_unknown_axes",
                    "comparison_parity_gate.unknown_parity_axes",
                    "anti_loop_progress_gate.unknown_parity_axes",
                    "result.comparison_parity_gate.unknown_parity_axes",
                ],
            )
        ) or ("unknown" in parity_axis_status_text)
        majority_vote_adoption = boolish(
            first_present(
                result,
                [
                    "majority_vote_adoption",
                    "adoption_axis_gate.majority_vote_adoption",
                    "comparison_parity_gate.majority_vote_adoption",
                    "result.adoption_axis_gate.majority_vote_adoption",
                ],
            )
        )
        provisional_adoption = boolish(
            first_present(
                result,
                [
                    "provisional_adoption",
                    "adoption_axis_gate.provisional_adoption",
                    "comparison_parity_gate.provisional_adoption",
                    "result.adoption_axis_gate.provisional_adoption",
                ],
            )
        )
        adoption_axis_classification = first_present(
            result,
            [
                "adoption_axis_classification",
                "adoption_axis_gate.adoption_axis_classification",
                "comparison_parity_gate.adoption_axis_classification",
                "result.adoption_axis_gate.adoption_axis_classification",
            ],
        )
        measured_but_disqualified = boolish(
            first_present(
                result,
                [
                    "measured_but_disqualified",
                    "adoption_axis_gate.measured_but_disqualified",
                    "comparison_parity_gate.measured_but_disqualified",
                    "anti_loop_progress_gate.measured_but_disqualified",
                    "result.adoption_axis_gate.measured_but_disqualified",
                ],
            )
        )
        failed_gating_axis = boolish(
            first_present(
                result,
                [
                    "failed_gating_axis",
                    "gating_axis_failed",
                    "adoption_axis_gate.failed_gating_axis",
                    "comparison_parity_gate.failed_gating_axis",
                    "anti_loop_progress_gate.failed_gating_axis",
                    "result.adoption_axis_gate.failed_gating_axis",
                ],
            )
        )
        required_resolution_value = first_present(
            result,
            [
                "required_evidence_resolution",
                "resolution_downgrade_gate.required_evidence_resolution",
                "anti_loop_progress_gate.required_evidence_resolution",
                "result.resolution_downgrade_gate.required_evidence_resolution",
            ],
        )
        observed_resolution_value = first_present(
            result,
            [
                "observed_evidence_resolution",
                "resolution_downgrade_gate.observed_evidence_resolution",
                "anti_loop_progress_gate.observed_evidence_resolution",
                "result.resolution_downgrade_gate.observed_evidence_resolution",
            ],
        )
        required_resolution = str(required_resolution_value or "").strip().lower()
        observed_resolution = str(observed_resolution_value or "").strip().lower()
        high_resolution_contract_required = boolish(
            first_present(
                result,
                [
                    "high_resolution_contract_required",
                    "resolution_downgrade_gate.high_resolution_contract_required",
                    "anti_loop_progress_gate.high_resolution_contract_required",
                    "result.resolution_downgrade_gate.high_resolution_contract_required",
                ],
            )
        ) or required_resolution in {"high", "full", "original", "direct", "terminal", "authoritative"}
        resolution_downgrade = boolish(
            first_present(
                result,
                [
                    "resolution_downgrade",
                    "resolution_downgrade_gate.resolution_downgrade",
                    "anti_loop_progress_gate.resolution_downgrade",
                    "result.resolution_downgrade_gate.resolution_downgrade",
                ],
            )
        ) or (
            high_resolution_contract_required
            and observed_resolution
            and observed_resolution not in {required_resolution, "high", "full", "original", "direct", "terminal", "authoritative"}
        )
        resolution_restored = boolish(
            first_present(
                result,
                [
                    "resolution_restored",
                    "observed_evidence_resolution_restored",
                    "resolution_downgrade_gate.resolution_restored",
                    "result.resolution_downgrade_gate.resolution_restored",
                ],
            )
        )
        resolution_contract_revised = boolish(
            first_present(
                result,
                [
                    "resolution_contract_revised",
                    "evidence_resolution_contract_revised",
                    "required_evidence_resolution_revised",
                    "resolution_downgrade_gate.contract_revised",
                    "result.resolution_downgrade_gate.contract_revised",
                ],
            )
        )
        pass_on_stale_lane = boolish(
            first_present(
                result,
                [
                    "pass_on_stale_lane",
                    "lane_identity_gate.pass_on_stale_lane",
                    "anti_loop_progress_gate.pass_on_stale_lane",
                    "result.lane_identity_gate.pass_on_stale_lane",
                ],
            )
        )
        lane_identity_missing = boolish(
            first_present(
                result,
                [
                    "lane_identity_missing",
                    "lane_identity_gate.lane_identity_missing",
                    "anti_loop_progress_gate.lane_identity_missing",
                    "result.lane_identity_gate.lane_identity_missing",
                ],
            )
        )
        current_lane_revalidated = non_empty(
            first_present(
                result,
                [
                    "current_lane_revalidated",
                    "current_lane_rerun_complete",
                    "lane_identity_gate.current_lane_revalidated",
                    "result.lane_identity_gate.current_lane_revalidated",
                ],
            )
        )
        decision_metadata_revision = boolish(
            first_present(
                result,
                [
                    "decision_metadata_revision",
                    "stale_measurement_artifact",
                    "decision_freshness_gate.decision_metadata_revision",
                    "decision_freshness_gate.stale_measurement_artifact",
                    "anti_loop_progress_gate.decision_metadata_revision",
                    "result.decision_freshness_gate.decision_metadata_revision",
                ],
            )
        )
        fresh_measurement_present = non_empty(
            first_present(
                result,
                [
                    "fresh_current_lane_run_id",
                    "fresh_measurement_run_id",
                    "measurement_run_id",
                    "decision_freshness_gate.fresh_current_lane_run_id",
                    "decision_freshness_gate.no_impact_proof",
                    "upstream_contract_no_impact_proof",
                    "result.decision_freshness_gate.fresh_current_lane_run_id",
                ],
            )
        )
        axis_starved_by_missing_producer = boolish(
            first_present(
                result,
                [
                    "axis_starved_by_missing_producer",
                    "gating_axis_producer_gate.axis_starved_by_missing_producer",
                    "anti_loop_progress_gate.axis_starved_by_missing_producer",
                    "result.gating_axis_producer_gate.axis_starved_by_missing_producer",
                ],
            )
        )
        producer_supply_complete = non_empty(
            first_present(
                result,
                [
                    "producer_supply_complete",
                    "producer_path_fired",
                    "gating_axis_producer_gate.producer_supply_complete",
                    "result.gating_axis_producer_gate.producer_supply_complete",
                ],
            )
        )
        portfolio_quota_exceeded = boolish(
            first_present(
                result,
                [
                    "portfolio_quota_exceeded",
                    "portfolio_quota_gate.portfolio_quota_exceeded",
                    "anti_loop_progress_gate.portfolio_quota_exceeded",
                    "result.portfolio_quota_gate.portfolio_quota_exceeded",
                ],
            )
        )
        portfolio_quota_mode = str(
            first_present(
                result,
                [
                    "portfolio_quota_mode",
                    "portfolio_quota_gate.portfolio_quota_mode",
                    "portfolio_quota_gate.mode",
                    "anti_loop_progress_gate.portfolio_quota_mode",
                    "result.portfolio_quota_gate.portfolio_quota_mode",
                ],
            )
            or ""
        ).lower()
        portfolio_quota_restrictive = portfolio_quota_mode in {"restrict", "restricted", "block", "blocking"}
        unreachable_within_cycle = boolish(
            first_present(
                result,
                [
                    "unreachable_within_cycle",
                    "cycle_reachability_gate.unreachable_within_cycle",
                    "acceptance_reachability_gate.unreachable_within_cycle",
                    "anti_loop_progress_gate.unreachable_within_cycle",
                    "result.cycle_reachability_gate.unreachable_within_cycle",
                ],
            )
        )
        harvest_validated = non_empty(
            first_present(
                result,
                [
                    "long_run_harvest_validated",
                    "harvest_validation_complete",
                    "cycle_reachability_gate.harvest_validation_complete",
                    "throughput_improved",
                    "cycle_reachability_gate.throughput_improved",
                    "result.cycle_reachability_gate.harvest_validation_complete",
                ],
            )
        )
        basis_overclaim = boolish(
            first_present(
                result,
                [
                    "basis_overclaim",
                    "metric_basis_gate.basis_overclaim",
                    "anti_loop_progress_gate.basis_overclaim",
                    "result.metric_basis_gate.basis_overclaim",
                ],
            )
        )
        basis_compatible_inputs = non_empty(
            first_present(
                result,
                [
                    "basis_compatible_inputs_present",
                    "basis_overclaim_resolved",
                    "metric_basis_gate.basis_compatible_inputs_present",
                    "metric_basis_gate.basis_overclaim_resolved",
                    "result.metric_basis_gate.basis_compatible_inputs_present",
                ],
            )
        )
        surface_field_defect_matrix = first_present(
            result,
            [
                "surface_field_defect_matrix",
                "surface_field_review_gate.surface_field_defect_matrix",
                "qualitative_review_packet.surface_field_defect_matrix",
                "result.surface_field_review_gate.surface_field_defect_matrix",
            ],
        )
        surface_field_defects = nonzero_scalar(surface_field_defect_matrix)
        field_class_map_missing = boolish(
            first_present(
                result,
                [
                    "field_class_map_missing",
                    "surface_field_review_gate.field_class_map_missing",
                    "qualitative_review_packet.field_class_map_missing",
                    "result.surface_field_review_gate.field_class_map_missing",
                ],
            )
        )
        surface_field_repaired = non_empty(
            first_present(
                result,
                [
                    "surface_field_repair_complete",
                    "field_class_repair_complete",
                    "surface_field_review_gate.surface_field_repair_complete",
                    "result.surface_field_review_gate.surface_field_repair_complete",
                ],
            )
        )
        if lane_identity_missing:
            add(
                findings,
                "warn",
                "lane_identity_missing",
                "`lane_identity_missing` is fail-quiet warning evidence; do not invent lane-key components in the result contract.",
            )
        if acceptance_diluted and validation_verdict in {"complete", "passed", "pass"}:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "validate_acceptance_diluted_complete",
                "`validate` cannot report complete when original directive acceptance was diluted; return partial and preserve residual scope.",
            )
        if measurable_target_required and validation_verdict in {"complete", "passed", "pass"} and not target_met and not explicit_descope:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "validate_measurable_target_unmet_complete",
                "`validate` cannot complete a measurable directive-derived item without meeting the original target or recording explicit descope plus residual scope.",
            )
        if (unverifiable_acceptance or required_verifier_not_evaluated) and validation_verdict in {"complete", "passed", "pass"} and not explicit_descope:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "validate_unverifiable_acceptance_complete",
                "`validate` cannot complete a measurable target when a required verifier is not_evaluated; return partial and preserve verifier or residual scope.",
            )
        if pass_with_coupled_verifier and validation_verdict in {"complete", "passed", "pass"} and not (explicit_descope or non_coupled_revalidated):
            add(
                findings,
                "block" if mode == "block" else "warn",
                "validate_coupled_verifier_complete",
                "`validate` cannot complete verifier-backed work from pass_with_coupled_verifier; require later non-coupled revalidation, independent recalculation, or explicit residual descope.",
            )
        if (pass_with_unobserved_axes or non_empty(unobserved_goal_axes)) and validation_verdict in {"complete", "passed", "pass"} and not explicit_descope:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "validate_unobserved_axes_complete",
                "`validate` cannot complete review-backed measurable work from pass_with_unobserved_axes; require adapter axis supply, residual scope, terminal blocker, or user escalation.",
                {"unobserved_goal_axes": unobserved_goal_axes or None},
            )
        if generation_dependent_count_key and generation_key_novelty_claim and progress_verdict == "advanced":
            add(
                findings,
                "block" if mode == "block" else "warn",
                "validate_advanced_from_generation_key_reset",
                "`validate` cannot accept family novelty, stall reset, hypothesis exhaustion, or seal escape based on generation-dependent task/advice/pack/cycle/run/date/hash/version keys.",
            )
        if residual_cost_below_policy and validation_verdict in {"complete", "passed", "pass"} and not (explicit_descope or marginal_repair_override):
            add(
                findings,
                "block" if mode == "block" else "warn",
                "validate_residual_cost_below_policy_complete",
                "`validate` cannot complete another same-gap residual repair when value per cycle cost is below policy without residual descope or a higher value case.",
            )
        if attested_only_movement and progress_verdict == "advanced" and not independently_verified_fields:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "validate_advanced_from_attested_only_movement",
                "`validate` cannot report progress_verdict: advanced from producer-attested movement without independently verified fields.",
            )
        if producer_attested_fields and not independently_verified_fields and validation_verdict in {"complete", "passed", "pass"} and not explicit_descope:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "validate_complete_from_producer_attested_fields",
                "`validate` cannot complete measurable progress from producer-attested fields alone; require independently verified evidence or residual scope.",
            )
        if independently_verified_fields and independent_source_status in {"missing", "overlap", "blocked"} and validation_verdict in {"complete", "passed", "pass"} and not explicit_descope:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "validate_independent_verification_source_not_disjoint",
                "`validate` cannot complete from independently_verified evidence unless verification_input_paths are disjoint from verified artifacts or the adapter marks the axis self_grounded.",
                {"independent_source_separation_status": independent_source_status},
            )
        if independently_verified_downgraded_fields and progress_verdict == "advanced" and not explicit_descope:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "validate_advanced_from_downgraded_independent_verification",
                "`validate` cannot report advanced progress from independently_verified fields that were auto-downgraded to attested.",
                {"downgraded_fields": independently_verified_downgraded_fields},
            )
        if envelope_thaw_item_required and validation_verdict in {"complete", "passed", "pass"} and not (explicit_descope or non_empty(envelope_thaw_item)):
            add(
                findings,
                "block" if mode == "block" else "warn",
                "validate_frozen_envelope_complete_without_thaw_item",
                "`validate` cannot complete acceptance that is unreachable under a frozen envelope without a reserved envelope_thaw_item or explicit descope.",
            )
        if terminal_stage_contradiction and validation_verdict in {"complete", "passed", "pass"}:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "validate_complete_with_terminal_classification_contradiction",
                "`validate` cannot complete while terminal classification contradicts the observed failure surface stage.",
            )
        if same_input_contract_violation and progress_verdict == "advanced":
            add(
                findings,
                "block" if mode == "block" else "warn",
                "validate_advanced_with_same_input_contract_violation",
                "`validate` cannot advance progress from same-family comparisons whose input sets do not match.",
            )
        if instrumentation_supply_required and progress_verdict == "advanced":
            add(
                findings,
                "block" if mode == "block" else "warn",
                "validate_advanced_with_instrumentation_supply_required",
                "`validate` cannot advance progress while repeated diagnostics_unavailable still requires instrumentation supply.",
            )
        if expectation_lineage_stale and validation_verdict in {"complete", "passed", "pass"} and not (explicit_descope or expectation_rebaselined):
            add(
                findings,
                "block" if mode == "block" else "warn",
                "validate_expectation_lineage_stale_complete",
                "`validate` cannot complete output-derived expectation work while expectation_lineage_stale is unresolved; rebaseline, descope residual scope, or return partial.",
            )
        if expectation_anchor_missing and lineage_verified_expectation_claim and validation_verdict in {"complete", "passed", "pass"}:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "validate_expectation_anchor_missing_lineage_claim",
                "`validate` cannot claim lineage-verified expectation evidence when expectation_anchor_missing is true.",
            )
        if comparison_contract and (parity_unverified or unknown_parity_axes) and validation_verdict in {"complete", "passed", "pass"} and not (explicit_descope or provisional_adoption):
            add(
                findings,
                "block" if mode == "block" else "warn",
                "validate_comparison_parity_unverified_complete",
                "`validate` cannot finalize baseline, comparison, or adoption work with parity_unverified or unknown parity axes.",
                {"unknown_parity_axes": unknown_parity_axes if isinstance(unknown_parity_axes, list) else None},
            )
        if comparison_contract and (parity_unverified or unknown_parity_axes) and progress_verdict == "advanced" and not (explicit_descope or provisional_adoption):
            add(
                findings,
                "block" if mode == "block" else "warn",
                "validate_advanced_with_parity_unverified",
                "`validate` cannot advance comparison or adoption progress until every required parity axis is controlled, measured, or explicitly provisional.",
            )
        if majority_vote_adoption and not non_empty(adoption_axis_classification) and validation_verdict in {"complete", "passed", "pass"} and not provisional_adoption:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "validate_majority_vote_adoption_without_axis_classification",
                "`validate` cannot finalize majority-vote adoption without adoption_axis_classification for gating and tradable axes.",
            )
        if (measured_but_disqualified or failed_gating_axis) and validation_verdict in {"complete", "passed", "pass"} and not explicit_descope:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "validate_complete_with_failed_adoption_axis",
                "`validate` cannot complete adoption when gating axes failed or measured evidence is disqualified; preserve measured_but_disqualified or route axis repair.",
            )
        if resolution_downgrade and high_resolution_contract_required and validation_verdict in {"complete", "passed", "pass"} and not (explicit_descope or resolution_restored or resolution_contract_revised):
            add(
                findings,
                "block" if mode == "block" else "warn",
                "validate_resolution_downgrade_complete",
                "`validate` cannot complete a high-resolution evidence contract from downgraded or surrogate evidence without restoration, contract revision, or residual descope.",
                {"required_evidence_resolution": required_resolution or None, "observed_evidence_resolution": observed_resolution or None},
            )
        if resolution_downgrade and progress_verdict == "advanced" and not (explicit_descope or resolution_restored or resolution_contract_revised):
            add(
                findings,
                "block" if mode == "block" else "warn",
                "validate_advanced_with_resolution_downgrade",
                "`validate` cannot report advanced progress from a downgraded evidence resolution unless the downgrade is explicitly provisional, restored, or contract-revised.",
            )
        if pass_on_stale_lane and validation_verdict in {"complete", "passed", "pass"} and not (explicit_descope or current_lane_revalidated):
            add(
                findings,
                "block" if mode == "block" else "warn",
                "validate_pass_on_stale_lane_complete",
                "`validate` cannot complete current-lane capability, adoption, comparison, close, or next-rung work from pass_on_stale_lane without current-lane rerun/revalidation or residual descope.",
            )
        if pass_on_stale_lane and progress_verdict == "advanced" and not (explicit_descope or current_lane_revalidated):
            add(
                findings,
                "block" if mode == "block" else "warn",
                "validate_advanced_from_stale_lane_pass",
                "`validate` cannot report advanced progress from a pass that belongs to a stale production lane.",
            )
        if decision_metadata_revision and validation_verdict in {"complete", "passed", "pass"} and not (explicit_descope or fresh_measurement_present):
            add(
                findings,
                "block" if mode == "block" else "warn",
                "validate_decision_metadata_revision_complete",
                "`validate` cannot complete measurement, adoption, or high-water work from decision_metadata_revision without a fresh current-lane run id or no-impact proof.",
            )
        if decision_metadata_revision and progress_verdict == "advanced" and not fresh_measurement_present:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "validate_advanced_from_decision_metadata_revision",
                "`validate` cannot report advanced progress from relabeling stale measurement artifacts after upstream contract changes.",
            )
        if axis_starved_by_missing_producer and validation_verdict in {"complete", "passed", "pass"} and not (explicit_descope or producer_supply_complete):
            add(
                findings,
                "block" if mode == "block" else "warn",
                "validate_axis_starved_by_missing_producer_complete",
                "`validate` cannot complete another verifier, guard, report, or metadata item for a producer-starved gating axis before producer supply fires.",
            )
        if axis_starved_by_missing_producer and progress_verdict == "advanced" and not producer_supply_complete:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "validate_advanced_with_producer_starved_axis",
                "`validate` cannot report advanced progress while the gating axis remains starved by a missing producer path.",
            )
        if portfolio_quota_exceeded and portfolio_quota_restrictive and progress_verdict == "advanced":
            add(
                findings,
                "block" if mode == "block" else "warn",
                "validate_advanced_during_portfolio_quota_restriction",
                "`validate` cannot report advanced progress for verifier-like work while restrictive portfolio_quota_exceeded is unresolved; require producer/envelope/long-run/descope/terminal/escalation evidence.",
            )
        elif portfolio_quota_exceeded and not portfolio_quota_restrictive:
            add(
                findings,
                "warn",
                "portfolio_quota_warn_only",
                "`portfolio_quota_exceeded` is warn-only unless the adapter supplies restrict mode.",
                {"portfolio_quota_mode": portfolio_quota_mode or None},
            )
        if unreachable_within_cycle and validation_verdict in {"complete", "passed", "pass"} and not (explicit_descope or harvest_validated):
            add(
                findings,
                "block" if mode == "block" else "warn",
                "validate_unreachable_within_cycle_complete",
                "`validate` cannot complete the original scale acceptance from small smoke, launch-only, or heartbeat evidence when unreachable_within_cycle=true; require harvest validation, throughput improvement, descope, terminal blocker, or escalation.",
            )
        if unreachable_within_cycle and progress_verdict == "advanced" and not harvest_validated:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "validate_advanced_with_unreachable_within_cycle",
                "`validate` cannot report advanced progress from repeating cycle-bound smoke evidence for a cycle-unreachable target.",
            )
        if basis_overclaim and validation_verdict in {"complete", "passed", "pass"} and not (explicit_descope or basis_compatible_inputs):
            add(
                findings,
                "block" if mode == "block" else "warn",
                "validate_basis_overclaim_complete",
                "`validate` cannot complete independently verified metric progress from basis_overclaim; downgrade to actual_basis_class or provide basis-compatible inputs.",
            )
        if basis_overclaim and progress_verdict == "advanced" and not basis_compatible_inputs:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "validate_advanced_from_basis_overclaim",
                "`validate` cannot report advanced progress from a metric whose claimed basis is not derivable from consumed inputs.",
            )
        if field_class_map_missing:
            add(
                findings,
                "warn",
                "field_class_map_missing",
                "`field_class_map_missing` is fail-quiet warning evidence; preserve existing review semantics and do not invent domain field classes.",
            )
        if surface_field_defects and validation_verdict in {"complete", "passed", "pass"} and not (explicit_descope or surface_field_repaired):
            add(
                findings,
                "block" if mode == "block" else "warn",
                "validate_surface_field_defects_complete",
                "`validate` cannot consume qualitative review as pass for affected producer-written field classes while surface_field_defect_matrix has nonzero defects.",
            )
        if surface_field_defects and progress_verdict == "advanced" and not surface_field_repaired:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "validate_advanced_with_surface_field_defects",
                "`validate` cannot report advanced qualitative-review progress while nonzero surface-field defects remain unresolved.",
            )
        scenario_uncovered = boolish(
            first_present(
                result,
                [
                    "scenario_uncovered",
                    "acceptance_scenario_gate.scenario_uncovered",
                    "result.acceptance_scenario_gate.scenario_uncovered",
                    "anti_loop_progress_gate.scenario_uncovered",
                ],
            )
        )
        acceptance_inversion = boolish(
            first_present(
                result,
                [
                    "acceptance_inversion",
                    "acceptance_inversion_candidate",
                    "acceptance_scenario_gate.acceptance_inversion",
                    "result.acceptance_scenario_gate.acceptance_inversion",
                    "anti_loop_progress_gate.acceptance_inversion",
                ],
            )
        )
        producer_residual_blocker = boolish(
            first_present(
                result,
                [
                    "producer_residual_blocker",
                    "observed_producer_claim.residual_blocker",
                    "observed_producer_claim.remaining_blocker",
                    "acceptance_scenario_gate.producer_residual_blocker",
                    "result.acceptance_scenario_gate.producer_residual_blocker",
                ],
            )
        )
        command_provenance_missing = boolish(
            first_present(
                result,
                [
                    "command_provenance_missing",
                    "command_provenance_gate.command_provenance_missing",
                    "result.command_provenance_gate.command_provenance_missing",
                    "anti_loop_progress_gate.command_provenance_missing",
                ],
            )
        )
        command_provenance_required = boolish(
            first_present(
                result,
                [
                    "command_provenance_required",
                    "command_provenance_gate.required",
                    "baseline_claim",
                    "comparison_claim",
                    "ab_claim",
                    "reproduction_claim",
                    "result.command_provenance_gate.required",
                ],
            )
        )
        repeated_blocker_opacity = boolish(
            first_present(
                result,
                [
                    "repeated_blocker_opacity",
                    "blocker_opacity_repeated",
                    "blocker_actionability_gate.repeated_blocker_opacity",
                    "result.blocker_actionability_gate.repeated_blocker_opacity",
                    "anti_loop_progress_gate.repeated_blocker_opacity",
                ],
            )
        )
        blocker_claimed_resolved = boolish(
            first_present(
                result,
                [
                    "blocker_claimed_resolved",
                    "blocker_actionability_gate.blocker_claimed_resolved",
                    "blocker_actionability_gate.claimed_actionable",
                    "result.blocker_actionability_gate.blocker_claimed_resolved",
                ],
            )
        )
        predetermined_unreachable = boolish(
            first_present(
                result,
                [
                    "predetermined_unreachable",
                    "stochastic_feasibility_gate.predetermined_unreachable",
                    "result.stochastic_feasibility_gate.predetermined_unreachable",
                    "anti_loop_progress_gate.predetermined_unreachable",
                ],
            )
        )
        floor_edge_envelope = boolish(
            first_present(
                result,
                [
                    "floor_edge_envelope",
                    "stochastic_feasibility_gate.floor_edge_envelope",
                    "result.stochastic_feasibility_gate.floor_edge_envelope",
                    "anti_loop_progress_gate.floor_edge_envelope",
                ],
            )
        )
        instrumentation_first_fire = boolish(
            first_present(
                result,
                [
                    "instrumentation_first_fire",
                    "instrumentation_first_fire_gate.instrumentation_first_fire",
                    "result.instrumentation_first_fire_gate.instrumentation_first_fire",
                    "anti_loop_progress_gate.instrumentation_first_fire",
                ],
            )
        )
        first_fire_double_counted = boolish(
            first_present(
                result,
                [
                    "first_fire_double_counted",
                    "first_fire_double_count_blocked",
                    "instrumentation_first_fire_gate.first_fire_double_counted",
                    "result.instrumentation_first_fire_gate.first_fire_double_counted",
                ],
            )
        )
        first_fire_goal_progress = boolish(
            first_present(
                result,
                [
                    "first_fire_claimed_goal_progress",
                    "instrumentation_first_fire_gate.claimed_goal_progress",
                    "instrumentation_first_fire_gate.instrumentation_supply_consumed",
                    "result.instrumentation_first_fire_gate.claimed_goal_progress",
                ],
            )
        )
        if scenario_uncovered and validation_verdict in {"complete", "passed", "pass"}:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "validate_complete_with_scenario_uncovered",
                "`validate` cannot complete scenario-shaped acceptance without a premise-satisfying fixture or live run.",
            )
        if acceptance_inversion and validation_verdict in {"complete", "passed", "pass"}:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "validate_complete_with_acceptance_inversion",
                "`validate` cannot complete when premise-satisfying evidence asserts the opposite terminal state; keep the verdict partial and route code/contract repair.",
            )
        if producer_residual_blocker and validation_verdict in {"complete", "passed", "pass"} and not (scenario_uncovered or acceptance_inversion):
            add(
                findings,
                "block" if mode == "block" else "warn",
                "validate_complete_with_unresolved_producer_residual_blocker",
                "`validate` cannot ignore a producer-reported residual blocker that contradicts an acceptance scenario; preserve it as acceptance_inversion_candidate or resolve the scenario gate.",
            )
        if command_provenance_missing and command_provenance_required and validation_verdict in {"complete", "passed", "pass"}:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "validate_complete_with_missing_command_provenance",
                "`validate` cannot complete baseline, comparison, A/B, reproduction, or run-specific acceptance from a live run with missing full argv.",
            )
        if repeated_blocker_opacity and blocker_claimed_resolved and validation_verdict in {"complete", "passed", "pass"}:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "validate_complete_with_repeated_blocker_opacity",
                "`validate` cannot close a claimed actionable/resolved blocker when the same gate still returns only opaque reason codes.",
            )
        if (predetermined_unreachable or floor_edge_envelope) and validation_verdict in {"complete", "passed", "pass"} and not explicit_descope:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "validate_complete_with_stochastic_contract_infeasible",
                "`validate` cannot complete exact-match or floor-edge stochastic contracts until the contract is revised, descoped with residual scope, or escalated.",
            )
        if instrumentation_first_fire and (first_fire_double_counted or first_fire_goal_progress):
            add(
                findings,
                "block" if mode == "block" else "warn",
                "validate_first_fire_double_counted",
                "`validate` must count instrumentation_first_fire as one evidence credit only, not goal progress plus instrumentation-supply consumption.",
            )
        behavior_change_live_required = boolish(
            first_present(
                result,
                [
                    "behavior_change_live_required",
                    "live_behavior_evidence_required",
                    "execution_evidence_gate.behavior_change_live_required",
                    "result.execution_evidence_gate.behavior_change_live_required",
                ],
            )
        )
        behavior_change_live_present = boolish(
            first_present(
                result,
                [
                    "behavior_change_live_present",
                    "live_behavior_evidence_present",
                    "execution_evidence_gate.live_behavior_evidence_present",
                    "result.execution_evidence_gate.live_behavior_evidence_present",
                ],
            )
        )
        behavior_change_deferred = boolish(
            first_present(
                result,
                [
                    "behavior_change_live_deferred",
                    "execution_evidence_gate.live_behavior_evidence_deferred",
                    "result.execution_evidence_gate.live_behavior_evidence_deferred",
                ],
            )
        )
        if behavior_change_live_required and validation_verdict in {"complete", "passed", "pass"} and not behavior_change_live_present and not behavior_change_deferred:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "validate_behavior_change_live_evidence_missing",
                "`validate` cannot complete a runtime gate or judgment behavior-change fix without fresh live before/after evidence or an explicit defer rationale.",
            )
        refactor_effect_required = boolish(
            first_present(
                result,
                [
                    "refactor_effect_required",
                    "structure_metrics_gate.refactor_effect_required",
                    "result.structure_metrics_gate.refactor_effect_required",
                ],
            )
        )
        structure_high_water_moved = boolish(
            first_present(
                result,
                [
                    "structure_high_water_moved",
                    "structure_metrics_gate.structure_high_water_moved",
                    "structure_metrics_gate.target_structure_improved",
                    "result.structure_metrics_gate.structure_high_water_moved",
                ],
            )
        )
        if refactor_effect_required and validation_verdict in {"complete", "passed", "pass"} and not structure_high_water_moved:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "validate_refactor_without_structure_high_water",
                "`validate` cannot complete a behavior-preserving refactor from module creation and green tests alone; adapter-supplied structure high-water must move or the task remains partial.",
            )
        structure_key_scope = str(
            first_present(
                result,
                [
                    "structure_high_water_key_scope",
                    "structure_metrics_gate.structure_high_water_key_scope",
                    "result.structure_metrics_gate.structure_high_water_key_scope",
                ],
            )
            or ""
        ).lower()
        global_structure_moved = boolish(
            first_present(
                result,
                [
                    "global_structure_high_water_moved",
                    "structure_metrics_gate.global_structure_high_water_moved",
                    "result.structure_metrics_gate.global_structure_high_water_moved",
                ],
            )
        )
        if (
            refactor_effect_required
            and validation_verdict in {"complete", "passed", "pass"}
            and structure_key_scope == "global_invariant"
            and not global_structure_moved
        ):
            add(
                findings,
                "block" if mode == "block" else "warn",
                "validate_global_structure_invariant_not_moved",
                "`validate` cannot complete global structure work from selected-scope movement while adapter-owned global invariants are flat.",
            )
        convention_status = str(
            first_present(
                result,
                [
                    "convention_conformance_gate.status",
                    "convention_conformance.status",
                    "result.convention_conformance_gate.status",
                    "result.convention_conformance.status",
                ],
            )
            or ""
        ).lower()
        convention_violation = boolish(
            first_present(
                result,
                [
                    "convention_conformance_gate.contract_violation",
                    "convention_conformance.contract_violation",
                    "result.convention_conformance_gate.contract_violation",
                    "result.convention_conformance.contract_violation",
                ],
            )
        )
        if validation_verdict in {"complete", "passed", "pass"} and (
            convention_status in {"failed", "fail", "blocked", "block", "refactor_required"} or convention_violation
        ):
            add(
                findings,
                "block" if mode == "block" else "warn",
                "validate_complete_with_convention_violation",
                "`validate` cannot complete code changes with unresolved contract-backed convention violations; return partial or record explicit residual/descope handling.",
            )
        terminal_outcome_value = first_present(
            result,
            [
                "terminal_outcome_changed",
                "anti_loop_progress_gate.terminal_outcome_changed",
                "loopback_audit.terminal_outcome_changed",
                "output_delta.terminal_outcome_changed",
                "result.terminal_outcome_changed",
                "result.anti_loop_progress_gate.terminal_outcome_changed",
            ],
        )
        changed_vs_previous = first_present(
            result,
            [
                "changed_vs_previous",
                "output_delta.changed_vs_previous",
                "output_delta_gate.changed_vs_previous",
                "anti_loop_progress_gate.changed_vs_previous",
                "result.output_delta.changed_vs_previous",
                "result.anti_loop_progress_gate.changed_vs_previous",
            ],
        )
        semantic_progress = first_present(
            result,
            [
                "semantic_progress",
                "output_delta.semantic_progress",
                "output_delta_gate.semantic_progress",
                "anti_loop_progress_gate.semantic_progress",
                "result.output_delta.semantic_progress",
                "result.anti_loop_progress_gate.semantic_progress",
            ],
        )
        produced_domain_delta = first_present(
            result,
            [
                "produced_domain_delta",
                "output_delta.produced_domain_delta",
                "output_delta_gate.produced_domain_delta",
                "result.output_delta.produced_domain_delta",
            ],
        )
        observed_delta_class = str(
            first_present(
                result,
                [
                    "observed_delta_class",
                    "observed_output_class",
                    "output_delta.observed_delta_class",
                    "output_delta_gate.observed_output_class",
                    "anti_loop_progress_gate.observed_delta_class",
                    "result.anti_loop_progress_gate.observed_delta_class",
                ],
            )
            or ""
        ).lower()
        strict_observed_change = (
            boolish(terminal_outcome_value)
            if terminal_outcome_value is not None
            else (
                boolish(changed_vs_previous)
                and boolish(semantic_progress)
                and (
                    boolish(produced_domain_delta)
                    or observed_delta_class
                    in {"node_edge_delta", "semantic_delta", "changed_semantic_output", "primary_output_delta"}
                )
            )
        )
        if progress_verdict == "advanced" and not strict_observed_change:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "validate_advanced_without_terminal_outcome_changed",
                "`validate` cannot report progress_verdict: advanced without terminal_outcome_changed=true or strict changed-and-semantic observed output delta.",
                {
                    "terminal_outcome_changed": terminal_outcome_value,
                    "changed_vs_previous": changed_vs_previous,
                    "semantic_progress": semantic_progress,
                    "produced_domain_delta": produced_domain_delta,
                    "observed_delta_class": observed_delta_class or None,
                },
            )
    if target == "report" and task_pack_in_scope(result):
        require_context_field("task_pack_status", "report_task_pack_status_missing", "`report` result references task-pack evidence but lacks `task_pack_status`.")
        require_context_field("task_pack_path", "report_task_pack_path_missing", "`report` result references task-pack evidence but lacks `task_pack_path`.")
        require_context_field("task_pack_item_id", "report_task_pack_item_id_missing", "`report` result references task-pack evidence but lacks `task_pack_item_id` or `promoted_item_id`.")
    if target == "validation_set_build":
        quality_tier = str(value_for(result, "quality_tier") or "").lower()
        if quality_tier == "gold":
            human_reviewed = positive_count(value_for(result, "human_reviewed_count"))
            deterministic_authoritative = bool(value_for(result, "fully_deterministic_authoritative_oracle"))
            if not human_reviewed and not deterministic_authoritative:
                add(
                    findings,
                    "block",
                    "gold_without_authoritative_evidence",
                    "`validation_set_build` cannot report `quality_tier: gold` without human-reviewed or fully deterministic authoritative evidence.",
                )
        guard_fields = {
            "raw_body_persisted": "raw_body_persistence_forbidden",
            "durable_raw_body_persisted": "raw_body_persistence_forbidden",
            "source_class_promotion_violation": "source_class_promotion_forbidden",
            "sealed_holdout_labels_exposed": "sealed_holdout_label_exposure_forbidden",
        }
        for field, code in guard_fields.items():
            value = value_for(result, field)
            if value is True or str(value).lower() in {"true", "yes", "1"}:
                add(findings, "block", code, f"`validation_set_build` reported forbidden guard violation `{field}`.")

    status = "ok"
    if any(item["severity"] == "block" for item in findings):
        status = "block"
    elif findings:
        status = "warn"
    return {"status": status, "target": target, "mode": mode, "findings": findings, "missing_fields": missing}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate a subskill result contract for orchestrate-task-cycle.")
    parser.add_argument("--target", required=True, choices=sorted(TARGETS))
    parser.add_argument("--result", default="-", help="Result JSON path, JSON string, or '-' for stdin.")
    parser.add_argument("--mode", choices=("warn", "block"), default="warn")
    args = parser.parse_args(argv)

    output = validate(args.target, load_json(args.result), args.mode)
    json.dump(output, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0 if output["status"] != "block" else 2


if __name__ == "__main__":
    raise SystemExit(main())
