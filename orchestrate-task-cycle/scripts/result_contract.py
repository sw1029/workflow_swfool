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
        "moduleization_required",
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
ADVICE_REQUIRED_TARGETS = {"governance", "validation_set_plan", "qualitative_review", "validation_set_build", "derive", "validate"}


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
        "moduleization_required": ["moduleization_required", "refactor_required", "code_structure_audit.moduleization_required"],
        "suggested_module_root": ["suggested_module_root", "module_root", "code_structure_audit.suggested_module_root"],
        "responsibility_split_plan": ["responsibility_split_plan", "split_plan", "module_split_plan", "code_structure_audit.responsibility_split_plan"],
        "validation_set_status": ["validation_set_status", "status", "validation_set.status"],
        "validation_set_id": ["validation_set_id", "vset_id", "validation_set.id"],
        "not_gold": ["not_gold", "validation_set.not_gold"],
        "progress_axes": ["progress_axes", "validation.progress_axes", "progress.axes"],
        "pid_or_session": ["pid", "session_id", "job_id", "pid_or_session", "run.pid", "run.session_id"],
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
        if active_task_pack_present(result) and selected_source != "task_pack" and not has_value(result, "task_pack_status"):
            add(findings, "block" if mode == "block" else "warn", "task_pack_status_missing", "Active task pack in scope requires `task_pack_status` in derive result.")
        if selected_source and selected_source not in {"task_pack", "candidate_task", "standalone", "terminal_blocked"}:
            add(findings, "warn", "selected_task_source_invalid", "`selected_task_source` should be task_pack, candidate_task, standalone, or terminal_blocked.", {"selected_task_source": selected_source})
        if selected_source == "task_pack":
            require_context_field("task_pack_status", "task_pack_status_missing", "`selected_task_source: task_pack` requires `task_pack_status`.")
            require_context_field("task_pack_path", "task_pack_path_missing", "`selected_task_source: task_pack` requires `task_pack_path`.")
            require_context_field("task_pack_item_id", "task_pack_item_id_missing", "`selected_task_source: task_pack` requires `task_pack_item_id` or `promoted_item_id`.")
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
        forward_mutation_progress = str(value_for(result, "blocker_mutation_kind") or "").lower() == "forward_mutation"
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
        if forward_mutation_progress and not substance_delta_pass and not hard_stop:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "loopback_forward_mutation_without_substance_delta",
                "`loopback_audit` must not leave ladder forward mutation open without G-SUBSTANCE pass or a hard stop.",
            )
        if vacuous_corrective_noop and semantic_progress:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "loopback_vacuous_corrective_claimed_semantic_progress",
                "`loopback_audit` reported semantic_progress while G-VACUOUS found attempted corrective lanes with zero resolved items.",
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
