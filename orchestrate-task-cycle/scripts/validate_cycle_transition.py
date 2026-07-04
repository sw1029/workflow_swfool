#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ORDER = [
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
]

TRANSITION_REQUIREMENTS = {
    "pre_validation_set_plan": ["context", "ledger_init", "authority", "acceptance", "route_plan"],
    "pre_governance": ["context", "ledger_init", "authority", "acceptance", "route_plan"],
    "pre_code_structure_audit": ["context", "ledger_init", "authority", "acceptance", "route_plan", "governance", "result_contract"],
    "pre_run": ["context", "ledger_init", "authority", "acceptance", "route_plan", "governance", "result_contract", "code_structure_audit"],
    "pre_qualitative_review": ["context", "ledger_init", "authority", "governance", "code_structure_audit", "run"],
    "pre_loopback_audit": ["context", "ledger_init", "authority", "governance", "code_structure_audit", "run", "qualitative_review"],
    "pre_validation_set_build": ["context", "ledger_init", "authority", "validation_set_plan", "governance", "code_structure_audit", "run", "qualitative_review", "loopback_audit"],
    "pre_schema_pre_derive": ["context", "ledger_init", "authority", "governance", "code_structure_audit", "run", "qualitative_review", "loopback_audit", "validation_set_build"],
    "pre_derive": ["context", "ledger_init", "authority", "governance", "code_structure_audit", "run", "qualitative_review", "loopback_audit", "validation_set_build", "schema_pre_derive", "visible_increment"],
    "pre_schema_post_derive": ["context", "ledger_init", "authority", "derive"],
    "pre_index": ["context", "ledger_init", "authority", "derive", "schema_post_derive"],
    "pre_validate": ["context", "ledger_init", "authority", "governance", "code_structure_audit", "run", "derive", "schema_post_derive", "index"],
    "pre_issue": ["context", "ledger_init", "authority", "validate"],
    "pre_commit": ["context", "ledger_init", "authority", "validate", "issue"],
    "pre_dashboard": ["context", "ledger_init", "authority", "validate", "commit"],
    "pre_report": ["context", "ledger_init", "authority", "validate", "dashboard"],
    "pre_closeout_commit": ["context", "ledger_init", "authority", "validate", "dashboard", "report"],
}

TERMINAL_OK = {"complete", "completed", "ok", "passed", "partial", "not_applicable", "skipped"}
SUCCESS_WORDS = {"success", "succeeded", "passed", "complete", "completed"}
STEP_ALIASES = {
    "context": ["establish_state"],
    "code_structure_audit": ["module_boundary_audit", "structure_audit"],
    "run": ["run_log"],
    "qualitative_review": ["output_quality_review"],
    "loopback_audit": ["anti_loop_audit", "loopback"],
    "issue": ["issue_tracking"],
    "closeout_commit": ["closeout"],
}


def load_json_arg(value: str | None) -> dict[str, Any]:
    if not value or value == "-":
        raw = sys.stdin.read()
        return json.loads(raw) if raw.strip() else {}
    path = Path(value)
    stripped = value.strip()
    if stripped.startswith("{") or stripped.startswith("["):
        return json.loads(stripped)
    try:
        if path.exists():
            raw = path.read_text(encoding="utf-8")
            return json.loads(raw) if raw.strip() else {}
    except OSError:
        pass
    return json.loads(stripped)


def deep_get(data: Any, *keys: str) -> Any:
    current = data
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def flatten_values(data: Any) -> list[Any]:
    values: list[Any] = []
    if isinstance(data, dict):
        for value in data.values():
            values.extend(flatten_values(value))
    elif isinstance(data, list):
        for value in data:
            values.extend(flatten_values(value))
    else:
        values.append(data)
    return values


def text_blob(*items: Any) -> str:
    values: list[str] = []
    for item in items:
        for value in flatten_values(item):
            if isinstance(value, (str, int, float, bool)):
                values.append(str(value))
    return "\n".join(values).lower()


def stage_event_candidates(stage: dict[str, Any]) -> list[dict[str, Any]]:
    """Return top-level and nested stage events from either a packet or current_stage."""
    candidates: list[dict[str, Any]] = []
    seen: set[int] = set()

    def add_candidate(value: Any) -> None:
        if isinstance(value, dict) and id(value) not in seen:
            candidates.append(value)
            seen.add(id(value))

    add_candidate(stage)
    add_candidate(stage.get("latest_event"))

    steps = stage.get("steps")
    if isinstance(steps, dict):
        for step in ORDER:
            add_candidate(steps.get(step))
        for name in sorted(set(steps) - set(ORDER)):
            add_candidate(steps.get(name))

    events = stage.get("events")
    if isinstance(events, list):
        for event in events:
            add_candidate(event)

    return candidates


def normalized_path_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    paths: list[str] = []
    for item in value:
        if isinstance(item, dict) and item.get("path"):
            paths.append(str(item["path"]))
        elif item is not None and str(item).strip():
            paths.append(str(item))
    return paths


def extend_unique(items: list[str], values: list[str]) -> None:
    seen = set(items)
    for value in values:
        if value not in seen:
            items.append(value)
            seen.add(value)


def status_for_step(stage: dict[str, Any], step: str) -> str | None:
    names = [step, *STEP_ALIASES.get(step, [])]
    steps = stage.get("steps")
    if isinstance(steps, dict):
        value = None
        for name in names:
            if name in steps:
                value = steps.get(name)
                break
        if isinstance(value, dict):
            raw = value.get("status") or value.get("verdict") or value.get("result")
        else:
            raw = value
        return str(raw).lower() if raw is not None else None
    events = stage.get("events")
    if isinstance(events, list):
        found = None
        for event in events:
            if isinstance(event, dict) and event.get("step") in names:
                found = event.get("status") or event.get("verdict") or event.get("result")
        return str(found).lower() if found is not None else None
    return None


def completed(stage: dict[str, Any], step: str) -> bool:
    status = status_for_step(stage, step)
    return bool(status and status in TERMINAL_OK)


def add(findings: list[dict[str, Any]], severity: str, code: str, message: str, evidence: Any = None) -> None:
    item: dict[str, Any] = {"severity": severity, "code": code, "message": message}
    if evidence is not None:
        item["evidence"] = evidence
    findings.append(item)


def context_goal_truth(context: dict[str, Any]) -> list[str]:
    used = deep_get(context, "agent_goal", "used_goal_truth")
    if isinstance(used, list):
        return [str(path) for path in used]
    files = deep_get(context, "agent_goal", "goal_truth_files")
    if isinstance(files, dict):
        return [str(info.get("path")) for info in files.values() if isinstance(info, dict) and info.get("exists")]
    return []


def stage_goal_truth(stage: dict[str, Any]) -> list[str]:
    paths: list[str] = []
    for candidate in stage_event_candidates(stage):
        for key in ("used_goal_truth", "gt_files", "goal_truth"):
            extend_unique(paths, normalized_path_list(candidate.get(key)))
        for nested in ("packet", "result"):
            value = deep_get(candidate, nested, "used_goal_truth")
            extend_unique(paths, normalized_path_list(value))
    return paths


def context_active_advice(context: dict[str, Any]) -> list[str]:
    active = deep_get(context, "external_advice", "active_files")
    if isinstance(active, list):
        return [str(item.get("path")) for item in active if isinstance(item, dict) and item.get("path")]
    return []


def stage_used_advice(stage: dict[str, Any]) -> list[str]:
    paths: list[str] = []
    for candidate in stage_event_candidates(stage):
        for key in ("used_advice", "external_advice", "advice"):
            extend_unique(paths, normalized_path_list(candidate.get(key)))
        for nested in ("packet", "result"):
            value = deep_get(candidate, nested, "used_advice")
            extend_unique(paths, normalized_path_list(value))
    return paths


def stage_advice_handling_rationale(stage: dict[str, Any]) -> str | None:
    fields = (
        "advice_deferred_reason",
        "advice_rejected_reason",
        "advice_not_applicable_reason",
        "advice_handling_rationale",
        "external_advice_rationale",
        "used_advice_rationale",
        "advice_usage_deferred_reason",
    )
    for candidate in stage_event_candidates(stage):
        for field in fields:
            value = candidate.get(field) or deep_get(candidate, "packet", field) or deep_get(candidate, "result", field)
            if isinstance(value, str) and value.strip():
                return value
            if isinstance(value, list) and value:
                return ", ".join(str(item) for item in value)
    return None


def long_run_events(stage: dict[str, Any]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for candidate in stage_event_candidates(stage):
        event_kind = str(candidate.get("event_kind") or "").lower()
        role = str(candidate.get("long_run_role") or "").lower()
        if truthy(candidate.get("long_run_branch")) or event_kind.startswith("long_run_") or role in {"launch", "monitor", "harvest", "finalize"}:
            events.append(candidate)
    return events


def active_long_run_events(stage: dict[str, Any]) -> list[dict[str, Any]]:
    active_statuses = {"launching", "running", "completed_pending_validation", "stale", "not_running"}
    result: list[dict[str, Any]] = []
    for event in long_run_events(stage):
        status = str(event.get("execution_status") or event.get("source_status") or event.get("status") or "").lower()
        if status in active_statuses:
            result.append(event)
    return result


def stage_authority_policy(stage: dict[str, Any]) -> Any:
    for candidate in stage_event_candidates(stage):
        for key in ("authority_policy", "authority", "effective_authority_policy"):
            value = candidate.get(key)
            if value:
                return value
        value = deep_get(candidate, "packet", "authority_policy") or deep_get(candidate, "routing", "authority_policy")
        if value:
            return value
    return None


def list_value(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if item is not None and str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value]
    return []


def first_value(stage: dict[str, Any], *paths: str) -> Any:
    for candidate in stage_event_candidates(stage):
        for path in paths:
            value = deep_get(candidate, *path.split(".")) if "." in path else candidate.get(path)
            if value is not None:
                return value
    return None


def truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in {"true", "yes", "1", "required", "block", "blocked"}
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, (list, dict)):
        return bool(value)
    return False


def selected_disposition(stage: dict[str, Any], next_progress_kind: str, terminal_blocker: Any) -> str:
    if terminal_blocker:
        return "terminal_blocked"
    for key in (
        "selected_disposition",
        "disposition",
        "progress_target",
        "selected_task_kind",
        "derive.selected_task_kind",
        "result.selected_task_kind",
        "packet.selected_task_kind",
    ):
        value = str(first_value(stage, key) or "").strip().lower()
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
    if next_progress_kind == "goal_productive":
        return "goal_productive"
    return next_progress_kind


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


def dict_list(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        return [value]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    return []


def signature_values(value: Any, key: str) -> list[str]:
    values: list[str] = []
    if isinstance(value, str) and value.strip():
        return [value.strip().lower()]
    for item in dict_list(value):
        raw = item.get(key) or item.get("signature") or item.get("family")
        if isinstance(raw, str) and raw.strip():
            values.append(raw.strip().lower())
    return values


def collect_stage_semantic_signatures(stage: dict[str, Any]) -> list[str]:
    values: list[str] = []
    seen: set[str] = set()
    paths = (
        "semantic_signature",
        "packet.semantic_signature",
        "result.semantic_signature",
        "derive.semantic_signature",
        "loop_breaker_packet.semantic_signature",
        "packet.loop_breaker_packet.semantic_signature",
        "terminal_blocker.semantic_signature",
        "packet.terminal_blocker.semantic_signature",
    )
    list_paths = (
        "repeated_semantic_signatures",
        "packet.repeated_semantic_signatures",
        "loop_breaker_packet.repeated_semantic_signatures",
        "packet.loop_breaker_packet.repeated_semantic_signatures",
        "semantic_signature_gate.sealed_matches",
        "packet.semantic_signature_gate.sealed_matches",
    )
    for candidate in stage_event_candidates(stage):
        for path in paths:
            raw = deep_get(candidate, *path.split(".")) if "." in path else candidate.get(path)
            for value in signature_values(raw, "semantic_signature"):
                if value not in seen:
                    values.append(value)
                    seen.add(value)
        for path in list_paths:
            raw = deep_get(candidate, *path.split(".")) if "." in path else candidate.get(path)
            items = raw if isinstance(raw, list) else [raw]
            for item in items:
                for value in signature_values(item, "semantic_signature"):
                    if value not in seen:
                        values.append(value)
                        seen.add(value)
    return values


def collect_sealed_families(context: dict[str, Any]) -> list[dict[str, Any]]:
    workspace = context.get("workspace") or "."
    root = Path(str(workspace))
    sealed: list[dict[str, Any]] = []

    def add_record(record: Any, source_path: Path) -> None:
        if not isinstance(record, dict):
            return
        records: list[Any]
        if isinstance(record.get("families"), list):
            records = record["families"]
        elif isinstance(record.get("sealed_families"), list):
            records = record["sealed_families"]
        else:
            records = [record]
        for item in records:
            if not isinstance(item, dict):
                continue
            semantic = item.get("semantic_signature") or item.get("family") or item.get("signature")
            blocker = item.get("blocker_signature")
            if semantic or blocker:
                sealed.append(
                    {
                        "semantic_signature": str(semantic).lower() if semantic else None,
                        "blocker_signature": str(blocker).lower() if blocker else None,
                        "path": str(source_path),
                        "reason": item.get("reason") or item.get("required_handoff"),
                    }
                )

    for path in (root / ".task").glob("sealed_blocker_families.json*"):
        try:
            if path.suffix == ".jsonl":
                for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                    if line.strip():
                        add_record(json.loads(line), path)
            else:
                add_record(json.loads(path.read_text(encoding="utf-8", errors="replace")), path)
        except (OSError, json.JSONDecodeError):
            continue

    pack_root = root / ".task" / "task_pack"
    if pack_root.is_dir():
        for path in pack_root.glob("*.json"):
            try:
                pack = json.loads(path.read_text(encoding="utf-8", errors="replace"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(pack, dict) and isinstance(pack.get("terminal_blocker"), dict):
                add_record(pack["terminal_blocker"], path)
    return sealed


def step_event(stage: dict[str, Any], step: str) -> dict[str, Any]:
    names = [step, *STEP_ALIASES.get(step, [])]
    steps = stage.get("steps")
    if isinstance(steps, dict):
        for name in names:
            value = steps.get(name)
            if isinstance(value, dict):
                return value
    events = stage.get("events")
    if isinstance(events, list):
        found: dict[str, Any] = {}
        for event in events:
            if isinstance(event, dict) and event.get("step") in names:
                found = event
        return found
    return {}


def validate(context: dict[str, Any], stage: dict[str, Any], transition: str) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []

    required = TRANSITION_REQUIREMENTS.get(transition, [])
    for step in required:
        if not completed(stage, step):
            add(findings, "block", "ordering_required_step_missing", f"{transition} requires completed step `{step}`.", {"step_status": status_for_step(stage, step)})

    completed_steps = [step for step in ORDER if completed(stage, step)]
    if completed_steps:
        latest_idx = max(ORDER.index(step) for step in completed_steps)
        for earlier in ORDER[:latest_idx]:
            if earlier in {"schema_pre_derive", "schema_post_derive"}:
                continue
            if not completed(stage, earlier) and earlier in required:
                add(findings, "block", "ordering_gap", f"Later step completed before required `{earlier}` was complete.", {"completed_steps": completed_steps})

    if transition in {"pre_loopback_audit", "pre_validation_set_build", "pre_schema_pre_derive", "pre_derive", "pre_schema_post_derive", "pre_validate", "pre_report", "pre_closeout_commit"}:
        review_event = step_event(stage, "qualitative_review")
        review_status = status_for_step(stage, "qualitative_review")
        if review_status in {"skipped", "not_applicable", "blocked", "failed"} and not (
            review_event.get("reason")
            or review_event.get("review_skipped_reason")
            or review_event.get("qualitative_review_pending_reason")
            or review_event.get("blockers")
        ):
            add(
                findings,
                "block",
                "qualitative_review_status_reason_missing",
                "Skipped/not-applicable/blocked qualitative output review requires a concrete reason.",
            )

    if transition in {"pre_governance", "pre_run", "pre_loopback_audit", "pre_validation_set_build", "pre_schema_pre_derive", "pre_derive", "pre_validate", "pre_report", "pre_closeout_commit"}:
        plan_event = step_event(stage, "validation_set_plan")
        plan_status = status_for_step(stage, "validation_set_plan")
        if plan_status in {"skipped", "not_applicable", "blocked", "failed"} and not (
            plan_event.get("reason")
            or plan_event.get("validation_set_skipped_reason")
            or plan_event.get("validation_set_blocked_reason")
            or plan_event.get("blockers")
        ):
            add(findings, "block", "validation_set_plan_status_reason_missing", "Skipped/not-applicable/blocked validation_set_plan requires a concrete reason.")

    if transition in {"pre_run", "pre_qualitative_review", "pre_loopback_audit", "pre_validation_set_build", "pre_schema_pre_derive", "pre_derive", "pre_validate", "pre_report", "pre_closeout_commit"}:
        structure_event = step_event(stage, "code_structure_audit")
        structure_status = status_for_step(stage, "code_structure_audit")
        if structure_status in {"skipped", "not_applicable", "blocked", "failed"} and not (
            structure_event.get("reason")
            or structure_event.get("code_structure_audit_skipped_reason")
            or structure_event.get("structure_audit_skipped_reason")
            or structure_event.get("blockers")
        ):
            add(findings, "block", "code_structure_audit_status_reason_missing", "Skipped/not-applicable/blocked code_structure_audit requires a concrete reason.")

    if transition in {"pre_validation_set_build", "pre_schema_pre_derive", "pre_derive", "pre_validate", "pre_report", "pre_closeout_commit"}:
        loopback_event = step_event(stage, "loopback_audit")
        loopback_status = status_for_step(stage, "loopback_audit")
        if loopback_status in {"skipped", "not_applicable", "blocked", "failed"} and not (
            loopback_event.get("reason")
            or loopback_event.get("loopback_audit_skipped_reason")
            or loopback_event.get("blockers")
        ):
            add(findings, "block", "loopback_audit_status_reason_missing", "Skipped/not-applicable/blocked loopback_audit requires a concrete reason.")

    if transition in {"pre_schema_pre_derive", "pre_derive", "pre_validate", "pre_report", "pre_closeout_commit"}:
        build_event = step_event(stage, "validation_set_build")
        build_status = status_for_step(stage, "validation_set_build")
        if build_status in {"skipped", "not_applicable", "blocked", "failed"} and not (
            build_event.get("reason")
            or build_event.get("validation_set_skipped_reason")
            or build_event.get("validation_set_blocked_reason")
            or build_event.get("blockers")
        ):
            add(findings, "block", "validation_set_build_status_reason_missing", "Skipped/not-applicable/blocked validation_set_build requires a concrete reason.")

    if transition in {"pre_derive", "pre_schema_post_derive", "pre_validate", "pre_report", "pre_closeout_commit"}:
        schema_event = step_event(stage, "schema_pre_derive")
        schema_status = status_for_step(stage, "schema_pre_derive")
        if schema_status in {"skipped", "not_applicable"} and not (schema_event.get("reason") or schema_event.get("schema_skipped_reason")):
            add(findings, "block", "schema_pre_derive_skipped_without_reason", "Skipped pre-derive schema refresh requires a reason.")

    if transition in {"pre_validate", "pre_issue", "pre_commit", "pre_dashboard", "pre_report", "pre_closeout_commit"}:
        derive_status = status_for_step(stage, "derive")
        derive_event = step_event(stage, "derive")
        if derive_status in {"pending", "deferred", "blocked", "failed"} and not (
            derive_event.get("reason") or derive_event.get("derive_pending_reason") or derive_event.get("blockers")
        ):
            add(findings, "block", "derive_pending_reason_missing", "Deferred/blocked derivation requires a pending or blocker reason.")
        if transition in {"pre_validate", "pre_report", "pre_closeout_commit"} and derive_status is None:
            add(findings, "warn", "derive_status_missing", "Derive status is missing; validation/report should explain whether next-task derivation completed, was deferred, or was skipped.")

    if transition in {"pre_derive", "pre_schema_post_derive", "pre_validate", "pre_report", "pre_closeout_commit"}:
        terminal_blocker = first_value(stage, "terminal_blocker", "packet.terminal_blocker", "result.terminal_blocker", "derive.terminal_blocker")
        new_input_kinds = list_value(
            first_value(
                stage,
                "new_input_kinds",
                "packet.new_input_kinds",
                "loop_breaker_packet.new_input_kinds",
                "packet.loop_breaker_packet.new_input_kinds",
                "positive_input_delta_gate.new_input_kinds",
                "packet.positive_input_delta_gate.new_input_kinds",
            )
        )
        supplied_input_paths = list_value(
            first_value(
                stage,
                "supplied_input_artifact_paths",
                "packet.supplied_input_artifact_paths",
                "positive_input_delta_gate.supplied_input_artifact_paths",
                "packet.positive_input_delta_gate.supplied_input_artifact_paths",
                "loop_breaker_packet.positive_input_delta_gate.supplied_input_artifact_paths",
                "packet.loop_breaker_packet.positive_input_delta_gate.supplied_input_artifact_paths",
            )
        )
        produced_domain_delta = truthy(
            first_value(
                stage,
                "produced_domain_delta",
                "packet.produced_domain_delta",
                "output_delta_gate.produced_domain_delta",
                "packet.output_delta_gate.produced_domain_delta",
                "positive_input_delta_gate.produced_domain_delta",
                "packet.positive_input_delta_gate.produced_domain_delta",
            )
        )
        changed_vs_previous = truthy(
            first_value(
                stage,
                "changed_vs_previous",
                "packet.changed_vs_previous",
                "output_delta_gate.changed_vs_previous",
                "packet.output_delta_gate.changed_vs_previous",
                "anti_loop_progress_gate.changed_vs_previous",
                "packet.anti_loop_progress_gate.changed_vs_previous",
            )
        )
        semantic_progress = truthy(
            first_value(
                stage,
                "semantic_progress",
                "packet.semantic_progress",
                "output_delta_gate.semantic_progress",
                "packet.output_delta_gate.semantic_progress",
                "anti_loop_progress_gate.semantic_progress",
                "packet.anti_loop_progress_gate.semantic_progress",
            )
        )
        strict_positive_output_delta = produced_domain_delta and changed_vs_previous and semantic_progress
        has_supplied_input_delta = truthy(
            first_value(
                stage,
                "has_supplied_input_delta",
                "packet.has_supplied_input_delta",
                "positive_input_delta_gate.has_supplied_input_delta",
                "packet.positive_input_delta_gate.has_supplied_input_delta",
                "loop_breaker_packet.positive_input_delta_gate.has_supplied_input_delta",
                "packet.loop_breaker_packet.positive_input_delta_gate.has_supplied_input_delta",
            )
        ) or bool(supplied_input_paths) or strict_positive_output_delta
        positive_delta_required = truthy(
            first_value(
                stage,
                "positive_input_delta_required",
                "packet.positive_input_delta_required",
                "loop_breaker_packet.positive_input_delta_required",
                "packet.loop_breaker_packet.positive_input_delta_required",
            )
        )
        zero_viable = truthy(
            first_value(
                stage,
                "zero_viable_candidates",
                "packet.zero_viable_candidates",
                "loop_breaker_packet.zero_viable_candidates",
                "packet.loop_breaker_packet.zero_viable_candidates",
            )
        )
        terminal_recommended = truthy(
            first_value(
                stage,
                "terminal_blocker_recommended",
                "packet.terminal_blocker_recommended",
                "loop_breaker_packet.terminal_blocker_recommended",
                "packet.loop_breaker_packet.terminal_blocker_recommended",
            )
        )
        semantic_signatures = collect_stage_semantic_signatures(stage)
        sealed_families = collect_sealed_families(context)
        sealed_semantic = {str(item.get("semantic_signature")) for item in sealed_families if item.get("semantic_signature")}
        sealed_matches = sorted(set(semantic_signatures) & sealed_semantic)
        cycles_since_goal_productive = number_value(
            first_value(
                stage,
                "cycles_since_goal_productive_output",
                "packet.cycles_since_goal_productive_output",
                "goal_distance_gate.cycles_since_goal_productive_output",
                "packet.goal_distance_gate.cycles_since_goal_productive_output",
                "loop_breaker_packet.cycles_since_goal_productive_output",
                "packet.loop_breaker_packet.cycles_since_goal_productive_output",
            )
        )
        goal_threshold = number_value(
            first_value(
                stage,
                "goal_productive_threshold",
                "packet.goal_productive_threshold",
                "goal_distance_gate.threshold",
                "packet.goal_distance_gate.threshold",
            )
        ) or 5
        goal_productive_this_cycle = truthy(
            first_value(
                stage,
                "goal_productive_this_cycle",
                "packet.goal_productive_this_cycle",
                "goal_distance_gate.goal_productive_this_cycle",
                "packet.goal_distance_gate.goal_productive_this_cycle",
            )
        )
        next_progress_kind = str(
            first_value(
                stage,
                "selected_progress_kind",
                "candidate_progress_kind",
                "next_task_progress_kind",
                "progress_kind",
                "derive.progress_kind",
                "result.progress_kind",
            )
            or ""
        ).lower()
        effective_allowed = list_value(
            first_value(
                stage,
                "effective_allowed_dispositions",
                "packet.effective_allowed_dispositions",
                "anti_loop_progress_gate.effective_allowed_dispositions",
                "packet.anti_loop_progress_gate.effective_allowed_dispositions",
                "loop_breaker_packet.effective_allowed_dispositions",
                "packet.loop_breaker_packet.effective_allowed_dispositions",
            )
        )
        if effective_allowed:
            disposition = selected_disposition(stage, next_progress_kind, terminal_blocker)
            if disposition and disposition not in {item.lower() for item in effective_allowed}:
                add(
                    findings,
                    "block",
                    "disposition_not_effectively_allowed",
                    "Selected disposition is outside `effective_allowed_dispositions`; active progress gates must be consumed as an intersection.",
                    {"selected_disposition": disposition, "effective_allowed_dispositions": effective_allowed},
                )
        if positive_delta_required and not has_supplied_input_delta and not terminal_blocker:
            add(
                findings,
                "block",
                "positive_input_delta_missing",
                "Evidence-family task selection requires a non-empty supplied artifact path or produced_domain_delta=true with changed_vs_previous=true and semantic_progress=true, or terminal blocker state.",
                {"new_input_kinds": new_input_kinds},
            )
        if zero_viable and not terminal_blocker:
            add(findings, "block", "zero_viable_candidates_without_terminal_state", "Zero viable candidate state requires `terminal_blocker` to prevent narrowing/blocker/handoff loops.")
        if terminal_recommended and not terminal_blocker and not has_supplied_input_delta:
            add(
                findings,
                "block",
                "terminal_blocker_recommendation_unhandled",
                "Terminal blocker recommendation requires terminal state or a supplied positive input delta override.",
                {"new_input_kinds": new_input_kinds, "supplied_input_artifact_paths": supplied_input_paths},
            )
        if sealed_matches and not terminal_blocker and not has_supplied_input_delta:
            add(
                findings,
                "block",
                "sealed_semantic_family_without_input_delta",
                "A sealed semantic blocker family is in scope without a supplied input artifact or positive output delta; do not derive another task in the same family.",
                {"semantic_signature": sealed_matches, "sealed_families": sealed_families[:5]},
            )
        if (
            cycles_since_goal_productive is not None
            and cycles_since_goal_productive > goal_threshold
            and not goal_productive_this_cycle
            and not terminal_blocker
            and next_progress_kind
            and next_progress_kind != "goal_productive"
        ):
            add(
                findings,
                "block",
                "goal_distance_gate_unmet",
                "Goal-distance gate requires a goal-productive next task or terminal blocker after too many governance-only cycles.",
                {"cycles_since_goal_productive_output": cycles_since_goal_productive, "threshold": goal_threshold, "progress_kind": next_progress_kind},
            )
        elif (
            cycles_since_goal_productive is not None
            and cycles_since_goal_productive > goal_threshold
            and not goal_productive_this_cycle
            and not terminal_blocker
            and not next_progress_kind
        ):
            add(
                findings,
                "warn",
                "goal_distance_gate_requires_derive_disposition",
                "Derive must select a goal-productive candidate or record terminal blocker state.",
                {"cycles_since_goal_productive_output": cycles_since_goal_productive, "threshold": goal_threshold},
            )
        provider_reattempt_required = truthy(
            first_value(
                stage,
                "provider_reattempt_required",
                "packet.provider_reattempt_required",
                "provider_reattempt_gate.provider_reattempt_required",
                "packet.provider_reattempt_gate.provider_reattempt_required",
                "loop_breaker_packet.provider_reattempt_gate.provider_reattempt_required",
                "packet.loop_breaker_packet.provider_reattempt_gate.provider_reattempt_required",
            )
        )
        provider_mitigation_required = truthy(
            first_value(
                stage,
                "provider_mitigation_required",
                "packet.provider_mitigation_required",
                "provider_reattempt_gate.provider_mitigation_required",
                "packet.provider_reattempt_gate.provider_mitigation_required",
                "loop_breaker_packet.provider_reattempt_gate.provider_mitigation_required",
                "packet.loop_breaker_packet.provider_reattempt_gate.provider_mitigation_required",
            )
        )
        provider_terminal_seal_allowed = first_value(
            stage,
            "provider_terminal_seal_allowed",
            "packet.provider_terminal_seal_allowed",
            "provider_reattempt_gate.provider_terminal_seal_allowed",
            "packet.provider_reattempt_gate.provider_terminal_seal_allowed",
            "loop_breaker_packet.provider_reattempt_gate.provider_terminal_seal_allowed",
            "packet.loop_breaker_packet.provider_reattempt_gate.provider_terminal_seal_allowed",
        )
        if provider_reattempt_required and terminal_blocker:
            add(
                findings,
                "block",
                "provider_terminal_seal_before_bounded_retry",
                "Transient provider failure with retry authority must not be terminal-blocked before required mitigation retry/probe evidence.",
            )
        if provider_mitigation_required and provider_terminal_seal_allowed is False and terminal_blocker:
            add(
                findings,
                "block",
                "provider_terminal_seal_before_mitigation_exhausted",
                "Transient provider failure must not be terminal-blocked while required mitigations remain unexhausted.",
            )
        autonomous_retarget_disabled = truthy(
            first_value(
                stage,
                "autonomous_retarget_disabled",
                "hard_stop_required",
                "packet.autonomous_retarget_disabled",
                "packet.hard_stop_required",
                "root_axis_gate.autonomous_retarget_disabled",
                "root_axis_gate.hard_stop_required",
                "packet.root_axis_gate.autonomous_retarget_disabled",
                "packet.root_axis_gate.hard_stop_required",
                "loop_breaker_packet.root_axis_gate.autonomous_retarget_disabled",
                "packet.loop_breaker_packet.root_axis_gate.autonomous_retarget_disabled",
            )
        )
        if autonomous_retarget_disabled and not terminal_blocker and next_progress_kind and next_progress_kind != "goal_productive":
            add(
                findings,
                "block",
                "autonomous_retarget_disabled_unhandled",
                "A root-axis hard stop allows only goal-productive derivation or terminal/user-escalation state.",
                {"progress_kind": next_progress_kind},
            )
        elif autonomous_retarget_disabled and not terminal_blocker and not next_progress_kind:
            add(
                findings,
                "warn",
                "autonomous_retarget_disabled_requires_disposition",
                "Derive must handle the root-axis hard stop by selecting goal-productive work or recording terminal/user-escalation state.",
            )
        gt_constraint_conflict_blocked = truthy(
            first_value(
                stage,
                "gt_constraint_conflict_packet.requires_conflict_resolution_task",
                "gt_constraint_conflict_packet.status",
                "packet.gt_constraint_conflict_packet.requires_conflict_resolution_task",
                "packet.gt_constraint_conflict_packet.status",
                "loop_breaker_packet.gt_constraint_conflict_packet.requires_conflict_resolution_task",
                "packet.loop_breaker_packet.gt_constraint_conflict_packet.requires_conflict_resolution_task",
            )
        )
        resolves_gt_constraint_conflict = truthy(
            first_value(
                stage,
                "resolves_gt_constraint_conflict",
                "conflict_resolution_task_selected",
                "packet.resolves_gt_constraint_conflict",
                "packet.conflict_resolution_task_selected",
                "derive.resolves_gt_constraint_conflict",
                "result.resolves_gt_constraint_conflict",
            )
        )
        selected_task_kind = str(
            first_value(
                stage,
                "selected_task_kind",
                "packet.selected_task_kind",
                "derive.selected_task_kind",
                "result.selected_task_kind",
            )
            or ""
        ).lower()
        if selected_task_kind in {"gt_constraint_conflict_resolution", "conflict_resolution", "authority_conflict_resolution"}:
            resolves_gt_constraint_conflict = True
        if gt_constraint_conflict_blocked and not terminal_blocker and next_progress_kind and not resolves_gt_constraint_conflict:
            add(
                findings,
                "block",
                "gt_constraint_conflict_unhandled",
                "A GT/task constraint conflict requires explicit conflict-resolution, contradiction-removing work, or terminal/user-escalation state.",
                {"selected_task_kind": selected_task_kind or None},
            )
        elif gt_constraint_conflict_blocked and not terminal_blocker and not next_progress_kind and not resolves_gt_constraint_conflict:
            add(
                findings,
                "warn",
                "gt_constraint_conflict_requires_disposition",
                "Derive must handle the GT/task constraint conflict before writing another task.",
            )
        authorized_alternative_exists = truthy(
            first_value(
                stage,
                "authorized_alternative_path_exists",
                "terminal_blocker.authorized_alternative_path_exists",
                "packet.authorized_alternative_path_exists",
                "packet.terminal_blocker.authorized_alternative_path_exists",
                "sealing_direction_guard.authorized_alternative_path_exists",
                "packet.sealing_direction_guard.authorized_alternative_path_exists",
            )
        )
        authorized_alternative_path = first_value(
            stage,
            "authorized_alternative_path",
            "terminal_blocker.authorized_alternative_path",
            "packet.authorized_alternative_path",
            "packet.terminal_blocker.authorized_alternative_path",
            "sealing_direction_guard.authorized_alternative_path",
            "packet.sealing_direction_guard.authorized_alternative_path",
        )
        alternative_in_gt_allowed = truthy(
            first_value(
                stage,
                "alternative_in_gt_allowed",
                "terminal_blocker.alternative_in_gt_allowed",
                "packet.alternative_in_gt_allowed",
                "packet.terminal_blocker.alternative_in_gt_allowed",
                "sealing_direction_guard.alternative_in_gt_allowed",
                "packet.sealing_direction_guard.alternative_in_gt_allowed",
            )
        )
        gt_allowed_alternative_attempted = truthy(
            first_value(
                stage,
                "gt_allowed_alternative_attempted",
                "terminal_blocker.gt_allowed_alternative_attempted",
                "packet.gt_allowed_alternative_attempted",
                "packet.terminal_blocker.gt_allowed_alternative_attempted",
                "sealing_direction_guard.gt_allowed_alternative_attempted",
                "packet.sealing_direction_guard.gt_allowed_alternative_attempted",
            )
        )
        gt_allowed_alternative_evidence_paths = list_value(
            first_value(
                stage,
                "gt_allowed_alternative_evidence_paths",
                "terminal_blocker.gt_allowed_alternative_evidence_paths",
                "packet.gt_allowed_alternative_evidence_paths",
                "packet.terminal_blocker.gt_allowed_alternative_evidence_paths",
                "sealing_direction_guard.gt_allowed_alternative_evidence_paths",
                "packet.sealing_direction_guard.gt_allowed_alternative_evidence_paths",
            )
        )
        if terminal_blocker and authorized_alternative_exists and not authorized_alternative_path:
            add(findings, "block", "seal_authorized_alternative_path_missing", "Terminal/seal state with an authorized alternative must name `authorized_alternative_path`.")
        if terminal_blocker and authorized_alternative_exists and not alternative_in_gt_allowed:
            add(
                findings,
                "block",
                "seal_alternative_not_gt_allowed",
                "The authorized alternative must be derived from `.agent_goal` allowed/required actions before terminal/seal state is accepted.",
                {"authorized_alternative_path": authorized_alternative_path},
            )
        if terminal_blocker and authorized_alternative_exists and alternative_in_gt_allowed and not gt_allowed_alternative_attempted:
            add(
                findings,
                "block",
                "seal_gt_allowed_alternative_unattempted",
                "A GT-allowed productive alternative must be attempted before terminal/seal state is accepted.",
                {"authorized_alternative_path": authorized_alternative_path},
            )
        if (
            terminal_blocker
            and authorized_alternative_exists
            and alternative_in_gt_allowed
            and gt_allowed_alternative_attempted
            and not gt_allowed_alternative_evidence_paths
        ):
            add(
                findings,
                "block",
                "seal_gt_allowed_alternative_evidence_missing",
                "A GT-allowed alternative attempt must cite evidence paths before terminal/seal state is accepted.",
                {"authorized_alternative_path": authorized_alternative_path},
            )
        command_budget_required = truthy(
            first_value(
                stage,
                "command_surface_budget.consolidation_candidate_required",
                "packet.command_surface_budget.consolidation_candidate_required",
                "loop_breaker_packet.command_surface_budget.consolidation_candidate_required",
                "packet.loop_breaker_packet.command_surface_budget.consolidation_candidate_required",
            )
        )
        consolidation_registered = truthy(
            first_value(
                stage,
                "consolidation_candidate_registered",
                "packet.consolidation_candidate_registered",
                "command_surface_budget.consolidation_candidate_registered",
                "packet.command_surface_budget.consolidation_candidate_registered",
            )
        )
        if command_budget_required and not consolidation_registered and not terminal_blocker and next_progress_kind != "goal_productive":
            add(
                findings,
                "block",
                "command_surface_budget_unhandled",
                "Command-surface budget requires a consolidation candidate/task unless derive selects goal-productive work or terminal state.",
            )

    gt_files = context_goal_truth(context)
    authority = stage_authority_policy(stage)
    if gt_files and not authority:
        add(findings, "warn", "authority_policy_missing", "Goal-truth files exist but the stage packet has no authority policy. Use `.agent_goal/agent_authority.md` or `default_current_agent_permissions`.")
    if authority and "default_current_agent_permissions" in str(authority):
        agent_authority = deep_get(context, "agent_goal", "goal_truth_files", "agent_authority.md", "exists")
        if not agent_authority:
            add(findings, "warn", "authority_default_fallback", "Using `default_current_agent_permissions` because `.agent_goal/agent_authority.md` is absent.", {"authority_policy": authority})

    stage_gt = stage_goal_truth(stage)
    if gt_files and not stage_gt:
        add(findings, "warn", "goal_truth_usage_missing", "The stage packet does not list `.agent_goal` GT files used.")
    elif gt_files:
        missing = sorted(set(gt_files) - set(stage_gt))
        if missing:
            add(findings, "warn", "goal_truth_usage_incomplete", "The stage packet omits some available `.agent_goal` GT files.", {"missing": missing})

    active_advice = context_active_advice(context)
    used_advice = stage_used_advice(stage)
    if active_advice and not used_advice:
        rationale = stage_advice_handling_rationale(stage)
        if rationale:
            add(
                findings,
                "warn",
                "external_advice_deferred_with_rationale",
                "Active `.agent_advice/active` documents exist and the stage records an explicit advice handling rationale instead of `used_advice`.",
                {"rationale": rationale},
            )
        else:
            add(
                findings,
                "block",
                "external_advice_usage_missing",
                "Active `.agent_advice/active` documents exist but the stage packet does not list `used_advice` or an explicit advice defer/reject/not-applicable rationale.",
            )
    if used_advice:
        advice_in_gt = [path for path in used_advice if path in stage_gt]
        if advice_in_gt or any(".agent_advice/" in path for path in stage_gt):
            add(findings, "warn", "external_advice_misclassified_as_gt", "External advice must be reported separately from `.agent_goal` GT.", {"used_advice": used_advice, "used_goal_truth": stage_gt})

    blob = text_blob(stage)
    if "gpt-5.3-codex-spark" in blob or "spark worker" in blob or "spark workers" in blob:
        add(findings, "warn", "stale_worker_model", "Stale Spark worker routing detected. Canonical code-writing workers use `model: gpt-5.5`.")
    worker_model = first_value(stage, "routing.code_worker_model", "worker.model", "code_worker_model")
    if worker_model and str(worker_model) != "gpt-5.5":
        add(findings, "warn", "noncanonical_worker_model", "Code-writing worker model is not the canonical `gpt-5.5`.", {"worker_model": worker_model})

    execution_status = str(first_value(stage, "execution_status", "run_log.status") or "").lower()
    validation_verdict = str(first_value(stage, "validation_verdict", "validation.verdict") or "").lower()
    startup_sufficient = bool(first_value(stage, "startup_evidence_satisfies_success", "run_log.startup_evidence_satisfies_success"))
    if execution_status == "running" and not startup_sufficient:
        if validation_verdict in {"complete", "passed", "success"} or any(word in blob for word in ("running success", "execution success")):
            add(findings, "block", "running_misclassified_success", "`running` execution was classified as success without explicit startup/heartbeat success criteria.")
        elif transition in {"pre_commit", "pre_report", "pre_closeout_commit"}:
            add(findings, "warn", "running_execution_incomplete", "`running` execution is in-progress evidence and normally supports only partial validation.")

    pending_long_runs = active_long_run_events(stage)
    if pending_long_runs:
        pending_summary = [
            {
                "run_id": event.get("run_id"),
                "task_id": event.get("task_id") or event.get("owner_task_id"),
                "execution_status": event.get("execution_status") or event.get("source_status") or event.get("status"),
                "event_kind": event.get("event_kind"),
                "remaining_validation": event.get("remaining_validation"),
            }
            for event in pending_long_runs[-3:]
        ]
        final_output_dependent = {
            "pre_qualitative_review",
            "pre_loopback_audit",
            "pre_validation_set_build",
            "pre_schema_pre_derive",
            "pre_derive",
        }
        if transition in final_output_dependent:
            add(
                findings,
                "block",
                "long_run_pending_final_output_phase",
                "Pending long-running execution cannot advance to final-output-dependent review, loopback, validation-set build, schema refresh, or derive; record a partial handoff and resume through monitor/harvest.",
                {"pending_long_runs": pending_summary},
            )
        if transition in {"pre_issue", "pre_commit", "pre_report", "pre_closeout_commit"}:
            if validation_verdict in {"complete", "passed", "success"} or str(first_value(stage, "progress_verdict") or "").lower() == "advanced":
                add(
                    findings,
                    "block",
                    "long_run_pending_claimed_complete",
                    "Pending long-running execution can support only partial/not_complete reporting until harvest validation consumes terminal artifacts.",
                    {"pending_long_runs": pending_summary, "validation_verdict": validation_verdict or None},
                )

    if transition == "pre_commit":
        if not validation_verdict:
            add(findings, "block", "pre_commit_missing_validation", "`$repo-change-commit` cannot run before `$validate-task-completion` returns a verdict.")
        issue_status = status_for_step(stage, "issue")
        if issue_status is None:
            add(findings, "warn", "issue_tracking_not_recorded", "Issue tracking status is not recorded before commit.")
        elif issue_status in {"skipped", "not_applicable"}:
            issue_event = step_event(stage, "issue")
            if not (issue_event.get("reason") or issue_event.get("issue_skipped_reason")):
                add(findings, "block", "issue_skipped_reason_missing", "Skipped issue tracking requires a reason before commit.")
        commit_intent = str(first_value(stage, "commit_intent", "commit.intent") or "").lower()
        if validation_verdict == "partial" and "partial" not in commit_intent and "checkpoint" not in commit_intent:
            add(findings, "block", "partial_commit_intent_missing", "Partial validation requires explicit partial/checkpoint commit intent.")
        if validation_verdict in {"failed", "block", "blocked"} and "force" not in commit_intent:
            add(findings, "block", "failed_commit_blocked", "Failed or blocked validation cannot be committed without explicit user authorization.")

    if transition in {"pre_report", "pre_closeout_commit"}:
        commit_status = status_for_step(stage, "commit") or str(first_value(stage, "commit_status", "commit.status") or "").lower()
        commit_event = step_event(stage, "commit")
        skipped_reason = first_value(stage, "commit_skipped_reason", "commit.commit_skipped_reason") or commit_event.get("reason") or commit_event.get("commit_skipped_reason")
        if commit_status in {"skipped", "not_applicable", "blocked", "failed"} and not skipped_reason:
            add(findings, "block", "commit_skipped_reason_missing", "Skipped/blocked/failed commit finalization requires a concrete reason in the report packet.")
        if not commit_status:
            add(findings, "warn", "commit_status_missing", "Commit finalization status is missing before final report.")
    if transition == "pre_closeout_commit":
        closeout_artifacts = first_value(
            stage,
            "tracked_artifacts",
            "closeout_artifacts",
            "closeout_commit.tracked_artifacts",
            "report.tracked_artifacts",
        )
        if not closeout_artifacts:
            add(
                findings,
                "warn",
                "closeout_artifacts_missing",
                "Closeout commit should name report/dashboard/current_stage/commit-result/advice artifacts or record why they are local-only.",
            )

    status = "ok"
    if any(item["severity"] == "block" for item in findings):
        status = "block"
    elif findings:
        status = "warn"

    return {"status": status, "transition": transition, "findings": findings}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate an orchestrate-task-cycle phase transition.")
    parser.add_argument("--context", default="-", help="Cycle context JSON path, or '-' for stdin.")
    parser.add_argument("--stage", help="Optional stage/status JSON path.")
    parser.add_argument("--transition", default="pre_report", choices=sorted(TRANSITION_REQUIREMENTS), help="Transition to validate.")
    args = parser.parse_args(argv)

    context = load_json_arg(args.context)
    stage = load_json_arg(args.stage) if args.stage else {}
    result = validate(context, stage, args.transition)
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0 if result["status"] != "block" else 2


if __name__ == "__main__":
    raise SystemExit(main())
