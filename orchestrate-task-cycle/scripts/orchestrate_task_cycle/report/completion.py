from __future__ import annotations

from typing import Any

from .events import all_events, event_value, stage_events
from .evidence import command_result_passed
from .io import deep_get


def report_input_findings(
    stage: dict[str, Any], validation: dict[str, Any]
) -> list[dict[str, Any]]:
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
    selected_source = str(
        stage.get("selected_task_source")
        or event_value(stage, "selected_task_source", ("derive", "report"))
        or ""
    )
    if (
        next_task_id in {"", "unknown-task", "none", "null"}
        and selected_source not in terminal_sources
    ):
        missing.append("next_task_id_or_terminal_disposition")
    if not commands or not all(command_result_passed(value) for value in commands):
        missing.append("validation_commands")
    if not axes or axes == ["not_recorded"]:
        missing.append("progress_axes")
    if not any(path != "stdout:assemble_cycle_report" for path in evidence_paths):
        missing.append("validation_evidence_paths")
    closure_records = report_closure_records(stage, commit)
    successful_closure_statuses = {
        "issue": {
            "closed",
            "complete",
            "completed",
            "created",
            "not_applicable",
            "open",
            "reopened",
            "resolved",
            "skipped",
            "tracked",
            "updated",
        },
        "derive": {
            "complete",
            "completed",
            "not_applicable",
            "ok",
            "pass",
            "passed",
            "skipped",
            "success",
        },
        "commit": {
            "committed",
            "complete",
            "completed",
            "created",
            "not_applicable",
            "pass",
            "passed",
            "skipped",
            "success",
        },
        "dashboard": {
            "complete",
            "completed",
            "ok",
            "pass",
            "passed",
            "rendered",
            "success",
            "warn",
        },
    }
    for step in ("issue", "derive", "commit", "dashboard"):
        candidates = [
            record for record in closure_records if record.get("step") == step
        ]
        if step == "commit" and any(
            record.get("source") == "commit_input" for record in candidates
        ):
            candidates = [
                record
                for record in candidates
                if record.get("source") == "commit_input"
            ]
        if not candidates:
            missing.append(f"{step}_closure")
            continue
        task_bound = [
            record
            for record in candidates
            if str(record.get("task_id") or "") == task_id
        ]
        if not task_bound:
            missing.append(f"{step}_closure_task_binding")
            continue
        successful = [
            record
            for record in task_bound
            if str(record.get("status") or "").lower()
            in successful_closure_statuses[step]
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


def report_closure_records(
    stage: dict[str, Any], commit: dict[str, Any]
) -> list[dict[str, Any]]:
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
    return {
        str(record.get("step"))
        for record in report_closure_records(stage, commit)
        if record.get("step")
    }


def task_line(
    context: dict[str, Any], validation: dict[str, Any], stage: dict[str, Any]
) -> str:
    task_id = (
        validation.get("completed_task_id")
        or stage.get("completed_task_id")
        or validation.get("task_id")
        or stage.get("task_id")
        or deep_get(stage, "task", "id")
    )
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
                    task_id = (
                        task_id
                        or event.get("completed_task_id")
                        or event.get("task_id")
                    )
                    summary = (
                        event.get("task_summary")
                        or event.get("reason")
                        or event.get("summary")
                    )
                    break
            if summary:
                break
    if not summary:
        for event in reversed(all_events(context, stage)):
            if event.get("step") not in {"closeout_commit", "dashboard", "commit"} and (
                event.get("completed_task_id") or event.get("task_id")
            ):
                task_id = (
                    task_id or event.get("completed_task_id") or event.get("task_id")
                )
                summary = event.get("reason") or event.get("summary")
                break
    task = context.get("task_md") if isinstance(context.get("task_md"), dict) else {}
    summary = summary or task.get("title") or task.get("path") or "task.md"
    task_id = task_id or "unknown-task"
    return f"{task_id}: {summary}"


def next_task_line(context: dict[str, Any], stage: dict[str, Any]) -> str:
    next_id = (
        stage.get("next_task_id")
        or deep_get(stage, "derive", "next_task_id")
        or event_value(
            stage, "next_task_id", ("report", "derive", "validate", "commit")
        )
    )
    summary = (
        stage.get("next_task_summary")
        or deep_get(stage, "derive", "summary")
        or event_value(stage, "selected_task_title", ("derive",))
    )
    task_pack_id = (
        stage.get("task_pack_id")
        or deep_get(stage, "derive", "task_pack_id")
        or deep_get(stage, "task_pack_packet", "pack_id")
        or event_value(stage, "task_pack_id", ("derive",))
    )
    task_pack_item_id = (
        stage.get("task_pack_item_id")
        or deep_get(stage, "derive", "task_pack_item_id")
        or deep_get(stage, "task_pack_packet", "current_item_id")
        or event_value(stage, "task_pack_item_promoted", ("derive",))
        or event_value(stage, "task_pack_item_id", ("derive",))
    )
    terminal_blocker = stage.get("terminal_blocker") or deep_get(
        stage, "derive", "terminal_blocker"
    )
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
    suffix = (
        f" (task_pack: {task_pack_id}/{task_pack_item_id})"
        if task_pack_id or task_pack_item_id
        else ""
    )
    return f"{next_id}: {summary}{suffix}"
