#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


FIELD_ORDER = [
    "기준 GT",
    "비-GT 방향성 문서",
    "주 진행 skill",
    "모델/effort 라우팅",
    "수행한 task",
    "변경한 파일",
    "실행한 검증",
    "validation verdict",
    "progress verdict",
    "progress axes",
    "남은 blocker",
    "다음 task/방향성",
    "완료 여부",
]

STAGE_ORDER = [
    "context",
    "authority",
    "repo_skill_adapter_scan",
    "acceptance",
    "route_plan",
    "validation_scope_plan",
    "validation_set_plan",
    "governance",
    "result_contract",
    "repo_skill_adapter_validate",
    "ledger_append",
    "code_structure_audit",
    "run",
    "qualitative_review",
    "loopback_audit",
    "validation_set_build",
    "visible_increment",
    "repo_skill_gap_analysis",
    "cycle_efficiency_profile",
    "validation_scope_finalize",
    "index_pre_validate",
    "validate",
    "issue",
    "schema_pre_derive",
    "derive",
    "schema_post_derive",
    "index",
    "commit",
    "dashboard",
    "report",
    "closeout_commit",
]


def load_json(path_value: str | None) -> dict[str, Any]:
    if not path_value:
        return {}
    if path_value == "-":
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


def deep_get(data: Any, *keys: str) -> Any:
    current: Any = data
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def list_value(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if item is not None and str(item) != ""]
    return []


def cycle_events(context: dict[str, Any]) -> list[dict[str, Any]]:
    events = deep_get(context, "cycle_state", "latest_events")
    if isinstance(events, list):
        return [event for event in events if isinstance(event, dict)]
    return []


def stage_events(stage: dict[str, Any]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    seen: set[int] = set()

    def add(value: Any) -> None:
        if isinstance(value, dict) and id(value) not in seen:
            events.append(value)
            seen.add(id(value))

    steps = stage.get("steps")
    if isinstance(steps, dict):
        for step in STAGE_ORDER:
            add(steps.get(step))
        for name in sorted(set(steps) - set(STAGE_ORDER)):
            add(steps.get(name))

    listed = stage.get("events")
    if isinstance(listed, list):
        for event in listed:
            add(event)

    add(stage.get("latest_event"))
    return events


def all_events(context: dict[str, Any], stage: dict[str, Any]) -> list[dict[str, Any]]:
    events = cycle_events(context) + stage_events(stage)
    deduped: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    for event in events:
        key = str(event.get("event_id") or id(event))
        if key not in seen_keys:
            deduped.append(event)
            seen_keys.add(key)
    return deduped


def report_evidence_paths(
    context: dict[str, Any],
    stage: dict[str, Any],
    *results: dict[str, Any],
) -> list[str]:
    paths = ["stdout:assemble_cycle_report"]
    sources = list(results) + all_events(context, stage)
    for source in sources:
        values = source.get("evidence_paths") if isinstance(source, dict) else None
        if not isinstance(values, list):
            continue
        for value in values:
            path = str(value).strip()
            if path and path not in paths:
                paths.append(path)
    return paths


def long_run_events(context: dict[str, Any], stage: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for event in all_events(context, stage):
        event_kind = str(event.get("event_kind") or "").lower()
        role = str(event.get("long_run_role") or "").lower()
        if event.get("long_run_branch") or event_kind.startswith("long_run_") or role in {"launch", "monitor", "harvest", "finalize"}:
            result.append(event)
    return result


def long_run_status_lines(context: dict[str, Any], stage: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    for event in long_run_events(context, stage)[-10:]:
        status = event.get("execution_status") or event.get("source_status") or event.get("status") or "unknown"
        run_id = event.get("run_id") or "unknown-run"
        role = event.get("long_run_role") or event.get("event_kind") or "long_run"
        remaining = event.get("remaining_validation") or "not_recorded"
        lines.append(f"{run_id}: {status} ({role}); remaining_validation={remaining}")
    return lines


def event_value(stage: dict[str, Any], field: str, preferred_steps: tuple[str, ...] = ()) -> Any:
    by_step: dict[str, dict[str, Any]] = {}
    for event in stage_events(stage):
        step = event.get("step")
        if isinstance(step, str):
            by_step[step] = event
    for step in preferred_steps:
        value = by_step.get(step, {}).get(field)
        if value is not None:
            return value
    latest = deep_get(stage, "latest_event", field)
    if latest is not None:
        return latest
    for event in reversed(stage_events(stage)):
        value = event.get(field)
        if value is not None:
            return value
    return None


def goal_truth(context: dict[str, Any], stage: dict[str, Any], validation: dict[str, Any]) -> list[str]:
    containers = [
        (stage, "used_goal_truth"),
        (stage.get("packet") if isinstance(stage.get("packet"), dict) else {}, "used_goal_truth"),
        (validation, "used_goal_truth"),
        (deep_get(context, "cycle_state") if isinstance(deep_get(context, "cycle_state"), dict) else {}, "used_goal_truth"),
        (deep_get(context, "agent_goal") if isinstance(deep_get(context, "agent_goal"), dict) else {}, "used_goal_truth"),
    ]
    for container, key in containers:
        if key in container and isinstance(container.get(key), list):
            return list_value(container.get(key))
    event_used: list[str] = []
    for event in all_events(context, stage):
        event_used.extend(list_value(event.get("used_goal_truth")))
        packet = event.get("packet")
        if isinstance(packet, dict):
            event_used.extend(list_value(packet.get("used_goal_truth")))
    if event_used:
        return sorted(set(event_used))
    return []


def advice_docs(context: dict[str, Any], stage: dict[str, Any], validation: dict[str, Any]) -> list[str]:
    for value in (
        stage.get("used_advice"),
        deep_get(stage, "packet", "used_advice"),
        validation.get("used_advice"),
        event_value(stage, "used_advice", ("report", "validate", "derive", "commit", "closeout_commit")),
    ):
        if isinstance(value, list):
            docs: list[str] = []
            for item in value:
                if isinstance(item, dict) and item.get("path"):
                    docs.append(f"{item.get('path')}: {item.get('title', 'external advice')}")
                elif isinstance(item, str):
                    docs.append(item)
            if docs:
                return docs
            # An explicit empty list means that active advice was not used.
            # Active inventory belongs in context, not in the report's
            # ``used_advice`` surface.
            return []
    return []


def model_effort_routing_lines(context: dict[str, Any], stage: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    seen: set[str] = set()
    for event in all_events(context, stage):
        routing = event.get("agent_routing") if isinstance(event.get("agent_routing"), dict) else {}
        applicability = event.get("agent_routing_applicability") or routing.get("applicability")
        if not applicability:
            continue
        step = event.get("step") or event.get("target") or "unknown_step"
        if str(applicability) == "deterministic_only":
            line = f"{step}: deterministic_only"
        elif str(applicability) == "delegation_unavailable":
            limitation = event.get("routing_limitation") or routing.get("routing_limitation") or "not_recorded"
            line = f"{step}: delegation_unavailable; limitation={limitation}"
        else:
            profile_id = event.get("profile_id") or routing.get("profile_id") or "unknown_profile"
            routing_tier = event.get("routing_tier") or routing.get("routing_tier") or "?"
            model = event.get("requested_model") or routing.get("requested_model") or "unknown_model"
            effort = event.get("requested_reasoning_effort") or routing.get("requested_reasoning_effort") or "unknown_effort"
            policy_id = event.get("policy_id") or routing.get("policy_id") or "unknown_policy"
            reason_codes = event.get("routing_reason_codes") or routing.get("routing_reason_codes") or []
            signals = event.get("routing_signals") or routing.get("routing_signals") or {}
            violations = event.get("routing_violations")
            if violations is None:
                violations = routing.get("routing_violations")
            enforcement = event.get("routing_enforcement") or routing.get("routing_enforcement") or "not_recorded"
            actual_model = event.get("actual_model") or routing.get("actual_model")
            actual_effort = event.get("actual_reasoning_effort") or routing.get("actual_reasoning_effort")
            actual = f"; actual={actual_model}/{actual_effort}" if actual_model or actual_effort else ""
            limitation = event.get("routing_limitation") or routing.get("routing_limitation")
            limitation_text = f"; limitation={limitation}" if limitation else ""
            max_reason = event.get("max_escalation_reason") or routing.get("max_escalation_reason")
            max_text = f"; max_reason={max_reason}" if max_reason else ""
            prior_evidence = event.get("prior_tier5_evidence") or routing.get("prior_tier5_evidence")
            agent_count = event.get("agent_count") or routing.get("agent_count")
            max_evidence_text = f"; prior_tier5_evidence={prior_evidence}; agent_count={agent_count}" if max_reason else ""
            line = (
                f"{step}: T{routing_tier} {profile_id} {model}/{effort}; policy={policy_id}; "
                f"reasons={json.dumps(reason_codes, ensure_ascii=False, separators=(',', ':'))}; "
                f"signals={json.dumps(signals, ensure_ascii=False, separators=(',', ':'))}; "
                f"violations={json.dumps(violations, ensure_ascii=False, separators=(',', ':'))}; "
                f"enforcement={enforcement}{actual}{limitation_text}{max_text}{max_evidence_text}"
            )
        if line not in seen:
            lines.append(line)
            seen.add(line)
    return lines


def changed_files(context: dict[str, Any], stage: dict[str, Any], validation: dict[str, Any], commit: dict[str, Any]) -> list[str]:
    for value in (
        stage.get("changed_files"),
        validation.get("changed_files"),
        commit.get("changed_files"),
        event_value(stage, "changed_files", ("report", "validate", "governance", "derive")),
    ):
        listed = list_value(value)
        if listed:
            return listed
    event_files: list[str] = []
    for event in all_events(context, stage):
        event_files.extend(list_value(event.get("changed_files")))
    if event_files:
        return sorted(set(event_files))
    entries: list[str] = []
    for line in deep_get(context, "git", "status_short_branch") or []:
        if isinstance(line, str) and not line.startswith("##"):
            entries.append(line)
    if not entries:
        for line in deep_get(context, "git", "diff_name_status") or []:
            if isinstance(line, str):
                entries.append(line)
    return entries


def validation_verdict(validation: dict[str, Any], stage: dict[str, Any]) -> str:
    raw = (
        validation.get("validation_verdict")
        or validation.get("verdict")
        or deep_get(validation, "validation", "verdict")
        or stage.get("validation_verdict")
        or deep_get(stage, "validation", "verdict")
        or event_value(stage, "validation_verdict", ("report", "validate", "closeout_commit"))
    )
    if not raw:
        return "not_run"
    value = str(raw).lower()
    if value == "complete":
        return "passed"
    if value in {"passed", "failed", "partial"}:
        return value
    if value in {"success", "ok"}:
        return "passed"
    return "failed" if value in {"block", "blocked"} else value


def progress_verdict(validation: dict[str, Any], stage: dict[str, Any], progress: dict[str, Any]) -> str:
    raw = (
        validation.get("progress_verdict")
        or deep_get(validation, "progress", "verdict")
        or stage.get("progress_verdict")
        or deep_get(stage, "validation", "progress_verdict")
        or event_value(stage, "progress_verdict", ("report", "validate", "derive", "closeout_commit"))
    )
    if raw:
        value = str(raw).lower()
        if value in {"advanced", "safety_only", "no_progress", "regressed"}:
            return value
    if progress.get("status") in {"warn", "block"} and progress.get("safety_only_count"):
        return "safety_only"
    return "not_run"


def progress_axes(validation: dict[str, Any], stage: dict[str, Any]) -> list[str]:
    raw = (
        validation.get("progress_axes")
        or deep_get(validation, "progress", "axes")
        or stage.get("progress_axes")
        or deep_get(stage, "validation", "progress_axes")
        or event_value(stage, "progress_axes", ("report", "validate"))
    )
    if isinstance(raw, dict) and raw:
        return [f"{key}: {value}" for key, value in sorted(raw.items())]
    if isinstance(raw, list) and raw:
        rendered: list[str] = []
        for item in raw:
            if isinstance(item, dict):
                axis = item.get("axis") or item.get("name") or item.get("id") or "axis"
                status = item.get("status") or item.get("verdict") or item.get("value") or "unknown"
                rendered.append(f"{axis}: {status}")
            else:
                rendered.append(str(item))
        return rendered
    return ["not_recorded"]


def command_results(validation: dict[str, Any], stage: dict[str, Any]) -> list[str]:
    commands = (
        validation.get("commands")
        or validation.get("validation_commands")
        or stage.get("commands")
        or stage.get("validation_commands")
        or deep_get(stage, "validation", "commands")
        or deep_get(stage, "validation", "validation_commands")
        or event_value(stage, "commands", ("report", "run", "validate"))
        or event_value(stage, "validation_commands", ("report", "run", "validate"))
    )
    if isinstance(commands, list):
        rendered = []
        for command in commands:
            if isinstance(command, dict):
                command_value = command.get("command") or command.get("cmd") or command.get("argv") or "unknown"
                if isinstance(command_value, list):
                    command_value = " ".join(str(value) for value in command_value)
                status = command.get("result") or command.get("status")
                if status is None and isinstance(command.get("exit_code"), int):
                    status = "passed" if command["exit_code"] == 0 else f"failed(exit_code={command['exit_code']})"
                rendered.append(f"{command_value}: {status or 'unknown'}")
            else:
                rendered.append(str(command))
        return rendered
    if isinstance(commands, dict):
        return [f"{key}: {value}" for key, value in commands.items()]
    return ["not_run"]


def command_result_passed(value: str) -> bool:
    lowered = value.strip().lower()
    if any(token in lowered for token in ("failed", "failure", "error", "blocked", "not passed", "not_run", "unknown", "exit_code=1", "exit 1")):
        return False
    return any(
        token in lowered
        for token in (
            ": pass",
            ": passed",
            ": ok",
            ": success",
            ": complete",
            ": completed",
            " exit_code=0",
            " exit 0",
            " passed",
        )
    )


def is_resolved_blocker(text: str) -> bool:
    lowered = text.lower()
    return any(term in lowered for term in ("status: resolved", "status: closed", "status: deleted", "/resolved/", "/closed/", "resolved:", "closed:"))


def blockers(context: dict[str, Any], stage: dict[str, Any], validation: dict[str, Any], progress: dict[str, Any]) -> list[str]:
    explicit: Any = None
    explicit_present = False
    for container, key in (
        (validation, "blockers"),
        (validation, "blocking_findings"),
        (stage, "blockers"),
    ):
        if key in container:
            explicit = container.get(key)
            explicit_present = True
            break
    if not explicit_present:
        event_explicit = event_value(stage, "blockers", ("report", "validate", "closeout_commit"))
        if event_explicit is not None:
            explicit = event_explicit
            explicit_present = True
    if explicit_present and isinstance(explicit, list):
        rendered = [str(item) for item in explicit if not is_resolved_blocker(str(item))]
        for line in long_run_status_lines(context, stage):
            if any(status in line for status in ("running", "launching", "completed_pending_validation", "stale", "not_running")):
                rendered.append(f"long_run_pending: {line}")
        return rendered
    if explicit_present:
        return []
    event_blockers: list[str] = []
    for event in all_events(context, stage):
        event_blockers.extend(list_value(event.get("blockers")))
    if event_blockers:
        return [item for item in sorted(set(event_blockers)) if not is_resolved_blocker(item)]
    found: list[str] = []
    for group_key in ("task_miss",):
        for item in deep_get(context, "task_state", group_key, "files") or []:
            if isinstance(item, dict):
                path = item.get("path")
                title = item.get("title") or item.get("status") or "active"
                status = str(item.get("status") or title)
                if path and status.lower() not in {"resolved", "deleted", "closed", "archived", "obsolete", "passed", "complete"}:
                    found.append(f"{path}: {title}")
    for item in deep_get(context, "issue", "files") or []:
        if isinstance(item, dict):
            path = item.get("path")
            title = item.get("title") or item.get("status") or "active"
            status = str(item.get("status") or title)
            if path and status.lower() not in {"resolved", "deleted", "closed", "archived", "obsolete", "passed", "complete"}:
                found.append(f"{path}: {title}")
    for finding in progress.get("findings") or []:
        if isinstance(finding, dict) and finding.get("severity") in {"warn", "block"}:
            found.append(f"progress_loop:{finding.get('code')}: {finding.get('message')}")
    for line in long_run_status_lines(context, stage):
        if any(status in line for status in ("running", "launching", "completed_pending_validation", "stale", "not_running")):
            found.append(f"long_run_pending: {line}")
    return found[:8]


def report_input_findings(stage: dict[str, Any], validation: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for source_name, container, field in (
        ("validation", validation, "blockers"),
        ("validation", validation, "blocking_findings"),
        ("stage", stage, "blockers"),
    ):
        if field in container and not isinstance(container.get(field), list):
            findings.append(
                {
                    "severity": "block",
                    "code": "invalid_report_blockers_input",
                    "message": f"{source_name}.{field} must be an explicit JSON list.",
                }
            )
    for event in stage_events(stage):
        if "blockers" in event and not isinstance(event.get("blockers"), list):
            findings.append(
                {
                    "severity": "block",
                    "code": "invalid_report_blockers_input",
                    "message": f"ledger event {event.get('event_id') or event.get('step') or 'unknown'} has non-list blockers.",
                }
            )
    return findings


def completion_evidence_findings(
    *,
    stage: dict[str, Any],
    validation: dict[str, Any],
    commit: dict[str, Any],
    task_id: str,
    next_task_id: str,
    commands: list[str],
    axes: list[str],
    evidence_paths: list[str],
) -> list[dict[str, Any]]:
    missing: list[str] = []
    if task_id in {"", "unknown-task", "none", "null"}:
        missing.append("task_id")
    terminal_sources = {"terminal_blocked", "user_escalation", "final_goal_complete"}
    selected_source = str(stage.get("selected_task_source") or event_value(stage, "selected_task_source", ("derive", "report")) or "")
    if next_task_id in {"", "unknown-task", "none", "null"} and selected_source not in terminal_sources:
        missing.append("next_task_id_or_terminal_disposition")
    if not commands or not all(command_result_passed(value) for value in commands):
        missing.append("validation_commands")
    if not axes or axes == ["not_recorded"]:
        missing.append("progress_axes")
    if not any(path != "stdout:assemble_cycle_report" for path in evidence_paths):
        missing.append("validation_evidence_paths")
    closure_records = report_closure_records(stage, commit)
    successful_closure_statuses = {
        "issue": {"closed", "complete", "completed", "created", "not_applicable", "open", "reopened", "resolved", "skipped", "tracked", "updated"},
        "derive": {"complete", "completed", "not_applicable", "ok", "pass", "passed", "skipped", "success"},
        "commit": {"committed", "complete", "completed", "created", "not_applicable", "pass", "passed", "skipped", "success"},
        "dashboard": {"complete", "completed", "ok", "pass", "passed", "rendered", "success", "warn"},
    }
    for step in ("issue", "derive", "commit", "dashboard"):
        candidates = [record for record in closure_records if record.get("step") == step]
        if step == "commit" and any(record.get("source") == "commit_input" for record in candidates):
            candidates = [record for record in candidates if record.get("source") == "commit_input"]
        if not candidates:
            missing.append(f"{step}_closure")
            continue
        task_bound = [record for record in candidates if str(record.get("task_id") or "") == task_id]
        if not task_bound:
            missing.append(f"{step}_closure_task_binding")
            continue
        successful = [
            record
            for record in task_bound
            if str(record.get("status") or "").lower() in successful_closure_statuses[step]
        ]
        if not successful:
            missing.append(f"{step}_closure_status")
            continue
        if step == "commit" and any(
            str(record.get("status") or "").lower() in {"skipped", "not_applicable"}
            and not str(record.get("reason") or "").strip()
            for record in successful
        ):
            missing.append("commit_closure_reason")
    if not isinstance(validation.get("blockers"), list):
        missing.append("validation_blockers_contract")
    if not missing:
        return []
    return [
        {
            "severity": "block",
            "code": "report_completion_evidence_incomplete",
            "message": "complete_verified lacks substantive current-task validation and close-phase evidence.",
            "missing": missing,
        }
    ]


def report_closure_records(stage: dict[str, Any], commit: dict[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for event in stage_events(stage):
        step = str(event.get("step") or "")
        if step not in {"issue", "derive", "commit", "dashboard"}:
            continue
        records.append(
            {
                "step": step,
                "task_id": event.get("completed_task_id") or event.get("task_id"),
                "status": event.get("commit_status")
                or event.get("issue_status")
                or event.get("dashboard_status")
                or event.get("status"),
                "reason": event.get("commit_skipped_reason") or event.get("reason"),
                "source": "ledger_event",
            }
        )
    if commit:
        records.append(
            {
                "step": "commit",
                "task_id": commit.get("completed_task_id") or commit.get("task_id"),
                "status": commit.get("commit_status") or commit.get("status"),
                "reason": commit.get("commit_skipped_reason") or commit.get("reason"),
                "source": "commit_input",
            }
        )
    return records


def report_closure_steps(stage: dict[str, Any], commit: dict[str, Any]) -> set[str]:
    return {str(record.get("step")) for record in report_closure_records(stage, commit) if record.get("step")}


def task_line(context: dict[str, Any], validation: dict[str, Any], stage: dict[str, Any]) -> str:
    task_id = validation.get("completed_task_id") or stage.get("completed_task_id") or validation.get("task_id") or stage.get("task_id") or deep_get(stage, "task", "id")
    summary = (
        validation.get("task_summary")
        or stage.get("completed_task_summary")
        or stage.get("task_summary")
        or validation.get("reason")
        or validation.get("completion_status")
    )
    if not summary:
        events = all_events(context, stage)
        preferred_steps = ("validate", "run", "governance", "derive", "report")
        for step in preferred_steps:
            for event in events:
                if event.get("step") != step:
                    continue
                if event.get("completed_task_id") or event.get("task_id"):
                    task_id = task_id or event.get("completed_task_id") or event.get("task_id")
                    summary = event.get("task_summary") or event.get("reason") or event.get("summary")
                    break
            if summary:
                break
    if not summary:
        for event in reversed(all_events(context, stage)):
            if event.get("step") not in {"closeout_commit", "dashboard", "commit"} and (event.get("completed_task_id") or event.get("task_id")):
                task_id = task_id or event.get("completed_task_id") or event.get("task_id")
                summary = event.get("reason") or event.get("summary")
                break
    task = context.get("task_md") if isinstance(context.get("task_md"), dict) else {}
    summary = summary or task.get("title") or task.get("path") or "task.md"
    task_id = task_id or "unknown-task"
    return f"{task_id}: {summary}"


def next_task_line(context: dict[str, Any], stage: dict[str, Any]) -> str:
    next_id = stage.get("next_task_id") or deep_get(stage, "derive", "next_task_id") or event_value(stage, "next_task_id", ("report", "derive", "validate", "commit"))
    summary = stage.get("next_task_summary") or deep_get(stage, "derive", "summary") or event_value(stage, "selected_task_title", ("derive",))
    task_pack_id = stage.get("task_pack_id") or deep_get(stage, "derive", "task_pack_id") or deep_get(stage, "task_pack_packet", "pack_id") or event_value(stage, "task_pack_id", ("derive",))
    task_pack_item_id = (
        stage.get("task_pack_item_id")
        or deep_get(stage, "derive", "task_pack_item_id")
        or deep_get(stage, "task_pack_packet", "current_item_id")
        or event_value(stage, "task_pack_item_promoted", ("derive",))
        or event_value(stage, "task_pack_item_id", ("derive",))
    )
    terminal_blocker = stage.get("terminal_blocker") or deep_get(stage, "derive", "terminal_blocker")
    for event in reversed(all_events(context, stage)):
        if event.get("next_task_id") and not next_id:
            next_id = event.get("next_task_id")
            summary = summary or event.get("reason") or event.get("summary")
        task_pack_id = task_pack_id or event.get("task_pack_id")
        task_pack_item_id = task_pack_item_id or event.get("task_pack_item_id")
        terminal_blocker = terminal_blocker or event.get("terminal_blocker")
    if terminal_blocker and not next_id:
        return f"terminal_blocked: {terminal_blocker}"
    task = context.get("task_md") if isinstance(context.get("task_md"), dict) else {}
    next_id = next_id or "unknown-task"
    summary = summary or task.get("title") or "task.md"
    suffix = f" (task_pack: {task_pack_id}/{task_pack_item_id})" if task_pack_id or task_pack_item_id else ""
    return f"{next_id}: {summary}{suffix}"


def assemble(
    context: dict[str, Any],
    stage: dict[str, Any],
    validation: dict[str, Any],
    progress: dict[str, Any],
    commit: dict[str, Any],
    closeout_commit: dict[str, Any],
) -> dict[str, Any]:
    validation_value = validation_verdict(validation, stage)
    report_validation_value = "passed" if validation_value == "complete" else validation_value
    progress_value = progress_verdict(validation, stage, progress)
    blocker_list = blockers(context, stage, validation, progress)
    report_findings = report_input_findings(stage, validation)
    completion_candidate = (
        validation_value in {"complete", "passed", "pass", "success"}
        and progress_value == "advanced"
        and not blocker_list
        and not report_findings
    )
    used_goal_truth = goal_truth(context, stage, validation)
    used_advice = advice_docs(context, stage, validation)
    routing_lines = model_effort_routing_lines(context, stage)
    routing_summary = routing_lines or ["not_recorded"]
    changed = changed_files(context, stage, validation, commit)
    commands = command_results(validation, stage)
    axes = progress_axes(validation, stage)
    evidence_paths = report_evidence_paths(context, stage, validation, progress, commit, closeout_commit)
    task_id = (
        validation.get("completed_task_id")
        or stage.get("completed_task_id")
        or validation.get("task_id")
        or stage.get("task_id")
        or "unknown-task"
    )
    next_task_id = (
        stage.get("next_task_id")
        or deep_get(stage, "derive", "next_task_id")
        or event_value(stage, "next_task_id", ("report", "derive", "validate", "commit"))
        or "unknown-task"
    )
    selected_task_source = str(stage.get("selected_task_source") or event_value(stage, "selected_task_source", ("derive", "report")) or "")
    closure_records = report_closure_records(stage, commit)
    closure_steps = sorted(report_closure_steps(stage, commit))
    if completion_candidate:
        report_findings.extend(
            completion_evidence_findings(
                stage=stage,
                validation=validation,
                commit=commit,
                task_id=task_id,
                next_task_id=next_task_id,
                commands=commands,
                axes=axes,
                evidence_paths=evidence_paths,
            )
        )
    complete = completion_candidate and not report_findings
    completion_status = "complete_verified" if complete else "not_complete"
    fields = {
        "기준 GT": used_goal_truth or ["없음"],
        "비-GT 방향성 문서": used_advice or ["없음"],
        "주 진행 skill": ["$orchestrate-task-cycle"],
        "모델/effort 라우팅": routing_summary,
        "수행한 task": [task_line(context, validation, stage)],
        "변경한 파일": changed or ["없음"],
        "실행한 검증": commands,
        "validation verdict": [report_validation_value],
        "progress verdict": [progress_value],
        "progress axes": axes,
        "남은 blocker": blocker_list or ["없음"],
        "다음 task/방향성": [next_task_line(context, stage)],
        "완료 여부": [completion_status],
    }
    extra: dict[str, Any] = {}
    if validation.get("report_path"):
        extra["validation_report_path"] = validation["report_path"]
    long_run_lines = long_run_status_lines(context, stage)
    if long_run_lines:
        extra["long_running_execution"] = long_run_lines
    if commit:
        extra["implementation_commit"] = commit
    if closeout_commit:
        extra["closeout_commit"] = closeout_commit
    # Preserve the human-facing ``fields`` object while also returning the
    # canonical report result-contract envelope.  Callers can now validate
    # the assembler output directly without a hidden translation step.
    return {
        "format_version": 1,
        "step": "report",
        "used_goal_truth": used_goal_truth,
        "used_advice": used_advice,
        "model_effort_routing": routing_summary,
        "task_id": task_id,
        "changed_files": changed,
        "commands": commands,
        "validation_verdict": report_validation_value,
        "progress_verdict": progress_value,
        "blockers": blocker_list,
        "progress_axes": axes,
        "next_task_id": next_task_id,
        "selected_task_source": selected_task_source,
        "closure_steps": closure_steps,
        "closure_records": closure_records,
        "completion_status": completion_status,
        "report_findings": report_findings,
        "evidence_paths": evidence_paths,
        "fields": fields,
        "extra": extra,
        "field_order": FIELD_ORDER,
    }


def render_markdown(report: dict[str, Any]) -> str:
    fields = report["fields"]
    lines: list[str] = []
    for field in FIELD_ORDER:
        lines.append(f"{field}:")
        for item in fields.get(field, ["not_run"]):
            lines.append(f"- {item}")
        lines.append("")
    extra = report.get("extra") or {}
    if extra:
        lines.append("추가 참고:")
        for key, value in extra.items():
            lines.append(f"- {key}: {value}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Assemble a Korean orchestrate-task-cycle report draft.")
    parser.add_argument("--context", required=True, help="Cycle context JSON path, or '-' for stdin.")
    parser.add_argument("--stage", help="Optional stage/status JSON path.")
    parser.add_argument("--validation", help="Optional validation result JSON path.")
    parser.add_argument("--progress", help="Optional progress-loop JSON path.")
    parser.add_argument("--commit", help="Optional commit result JSON path.")
    parser.add_argument("--closeout-commit", help="Optional closeout commit result JSON path.")
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    args = parser.parse_args(argv)

    context = load_json(args.context)
    report = assemble(
        context,
        load_json(args.stage),
        load_json(args.validation),
        load_json(args.progress),
        load_json(args.commit),
        load_json(args.closeout_commit),
    )
    if args.format == "json":
        json.dump(report, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(render_markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
