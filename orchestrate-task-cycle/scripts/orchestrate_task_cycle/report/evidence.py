from __future__ import annotations

import json
from typing import Any

from .events import all_events, event_value, long_run_status_lines
from .io import deep_get, list_value


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


def goal_truth(
    context: dict[str, Any], stage: dict[str, Any], validation: dict[str, Any]
) -> list[str]:
    containers = [
        (stage, "used_goal_truth"),
        (
            stage.get("packet") if isinstance(stage.get("packet"), dict) else {},
            "used_goal_truth",
        ),
        (validation, "used_goal_truth"),
        (
            deep_get(context, "cycle_state")
            if isinstance(deep_get(context, "cycle_state"), dict)
            else {},
            "used_goal_truth",
        ),
        (
            deep_get(context, "agent_goal")
            if isinstance(deep_get(context, "agent_goal"), dict)
            else {},
            "used_goal_truth",
        ),
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


def advice_docs(
    context: dict[str, Any], stage: dict[str, Any], validation: dict[str, Any]
) -> list[str]:
    for value in (
        stage.get("used_advice"),
        deep_get(stage, "packet", "used_advice"),
        validation.get("used_advice"),
        event_value(
            stage,
            "used_advice",
            ("report", "validate", "derive", "commit", "closeout_commit"),
        ),
    ):
        if isinstance(value, list):
            docs: list[str] = []
            for item in value:
                if isinstance(item, dict) and item.get("path"):
                    docs.append(
                        f"{item.get('path')}: {item.get('title', 'external advice')}"
                    )
                elif isinstance(item, str):
                    docs.append(item)
            if docs:
                return docs
            # An explicit empty list means that active advice was not used.
            # Active inventory belongs in context, not in the report's
            # ``used_advice`` surface.
            return []
    return []


def model_effort_routing_lines(
    context: dict[str, Any], stage: dict[str, Any]
) -> list[str]:
    lines: list[str] = []
    seen: set[str] = set()
    for event in all_events(context, stage):
        routing = (
            event.get("agent_routing")
            if isinstance(event.get("agent_routing"), dict)
            else {}
        )
        applicability = event.get("agent_routing_applicability") or routing.get(
            "applicability"
        )
        if not applicability:
            continue
        step = event.get("step") or event.get("target") or "unknown_step"
        if str(applicability) == "deterministic_only":
            line = f"{step}: deterministic_only"
        elif str(applicability) == "delegation_unavailable":
            limitation = (
                event.get("routing_limitation")
                or routing.get("routing_limitation")
                or "not_recorded"
            )
            line = f"{step}: delegation_unavailable; limitation={limitation}"
        else:
            profile_id = (
                event.get("profile_id")
                or routing.get("profile_id")
                or "unknown_profile"
            )
            routing_tier = (
                event.get("routing_tier") or routing.get("routing_tier") or "?"
            )
            model = (
                event.get("requested_model")
                or routing.get("requested_model")
                or "unknown_model"
            )
            effort = (
                event.get("requested_reasoning_effort")
                or routing.get("requested_reasoning_effort")
                or "unknown_effort"
            )
            policy_id = (
                event.get("policy_id") or routing.get("policy_id") or "unknown_policy"
            )
            reason_codes = (
                event.get("routing_reason_codes")
                or routing.get("routing_reason_codes")
                or []
            )
            signals = (
                event.get("routing_signals") or routing.get("routing_signals") or {}
            )
            violations = event.get("routing_violations")
            if violations is None:
                violations = routing.get("routing_violations")
            enforcement = (
                event.get("routing_enforcement")
                or routing.get("routing_enforcement")
                or "not_recorded"
            )
            actual_model = event.get("actual_model") or routing.get("actual_model")
            actual_effort = event.get("actual_reasoning_effort") or routing.get(
                "actual_reasoning_effort"
            )
            actual = (
                f"; actual={actual_model}/{actual_effort}"
                if actual_model or actual_effort
                else ""
            )
            limitation = event.get("routing_limitation") or routing.get(
                "routing_limitation"
            )
            limitation_text = f"; limitation={limitation}" if limitation else ""
            max_reason = event.get("max_escalation_reason") or routing.get(
                "max_escalation_reason"
            )
            max_text = f"; max_reason={max_reason}" if max_reason else ""
            prior_evidence = event.get("prior_tier5_evidence") or routing.get(
                "prior_tier5_evidence"
            )
            agent_count = event.get("agent_count") or routing.get("agent_count")
            max_evidence_text = (
                f"; prior_tier5_evidence={prior_evidence}; agent_count={agent_count}"
                if max_reason
                else ""
            )
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


def changed_files(
    context: dict[str, Any],
    stage: dict[str, Any],
    validation: dict[str, Any],
    commit: dict[str, Any],
) -> list[str]:
    for value in (
        stage.get("changed_files"),
        validation.get("changed_files"),
        commit.get("changed_files"),
        event_value(
            stage, "changed_files", ("report", "validate", "governance", "derive")
        ),
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
        or event_value(
            stage, "validation_verdict", ("report", "validate", "closeout_commit")
        )
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


def progress_verdict(
    validation: dict[str, Any], stage: dict[str, Any], progress: dict[str, Any]
) -> str:
    raw = (
        validation.get("progress_verdict")
        or deep_get(validation, "progress", "verdict")
        or stage.get("progress_verdict")
        or deep_get(stage, "validation", "progress_verdict")
        or event_value(
            stage,
            "progress_verdict",
            ("report", "validate", "derive", "closeout_commit"),
        )
    )
    if raw:
        value = str(raw).lower()
        if value in {"advanced", "safety_only", "no_progress", "regressed"}:
            return value
    if progress.get("status") in {"warn", "block"} and progress.get(
        "safety_only_count"
    ):
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
                status = (
                    item.get("status")
                    or item.get("verdict")
                    or item.get("value")
                    or "unknown"
                )
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
                command_value = (
                    command.get("command")
                    or command.get("cmd")
                    or command.get("argv")
                    or "unknown"
                )
                if isinstance(command_value, list):
                    command_value = " ".join(str(value) for value in command_value)
                status = command.get("result") or command.get("status")
                if status is None and isinstance(command.get("exit_code"), int):
                    status = (
                        "passed"
                        if command["exit_code"] == 0
                        else f"failed(exit_code={command['exit_code']})"
                    )
                rendered.append(f"{command_value}: {status or 'unknown'}")
            else:
                rendered.append(str(command))
        return rendered
    if isinstance(commands, dict):
        return [f"{key}: {value}" for key, value in commands.items()]
    return ["not_run"]


def command_result_passed(value: str) -> bool:
    lowered = value.strip().lower()
    if any(
        token in lowered
        for token in (
            "failed",
            "failure",
            "error",
            "blocked",
            "not passed",
            "not_run",
            "unknown",
            "exit_code=1",
            "exit 1",
        )
    ):
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
    return any(
        term in lowered
        for term in (
            "status: resolved",
            "status: closed",
            "status: deleted",
            "/resolved/",
            "/closed/",
            "resolved:",
            "closed:",
        )
    )


def blockers(
    context: dict[str, Any],
    stage: dict[str, Any],
    validation: dict[str, Any],
    progress: dict[str, Any],
) -> list[str]:
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
        event_explicit = event_value(
            stage, "blockers", ("report", "validate", "closeout_commit")
        )
        if event_explicit is not None:
            explicit = event_explicit
            explicit_present = True
    if explicit_present and isinstance(explicit, list):
        rendered = [
            str(item) for item in explicit if not is_resolved_blocker(str(item))
        ]
        for line in long_run_status_lines(context, stage):
            if any(
                status in line
                for status in (
                    "running",
                    "launching",
                    "completed_pending_validation",
                    "stale",
                    "not_running",
                )
            ):
                rendered.append(f"long_run_pending: {line}")
        return rendered
    if explicit_present:
        return []
    event_blockers: list[str] = []
    for event in all_events(context, stage):
        event_blockers.extend(list_value(event.get("blockers")))
    if event_blockers:
        return [
            item
            for item in sorted(set(event_blockers))
            if not is_resolved_blocker(item)
        ]
    found: list[str] = []
    for group_key in ("task_miss",):
        for item in deep_get(context, "task_state", group_key, "files") or []:
            if isinstance(item, dict):
                path = item.get("path")
                title = item.get("title") or item.get("status") or "active"
                status = str(item.get("status") or title)
                if path and status.lower() not in {
                    "resolved",
                    "deleted",
                    "closed",
                    "archived",
                    "obsolete",
                    "passed",
                    "complete",
                }:
                    found.append(f"{path}: {title}")
    for item in deep_get(context, "issue", "files") or []:
        if isinstance(item, dict):
            path = item.get("path")
            title = item.get("title") or item.get("status") or "active"
            status = str(item.get("status") or title)
            if path and status.lower() not in {
                "resolved",
                "deleted",
                "closed",
                "archived",
                "obsolete",
                "passed",
                "complete",
            }:
                found.append(f"{path}: {title}")
    for finding in progress.get("findings") or []:
        if isinstance(finding, dict) and finding.get("severity") in {"warn", "block"}:
            found.append(
                f"progress_loop:{finding.get('code')}: {finding.get('message')}"
            )
    for line in long_run_status_lines(context, stage):
        if any(
            status in line
            for status in (
                "running",
                "launching",
                "completed_pending_validation",
                "stale",
                "not_running",
            )
        ):
            found.append(f"long_run_pending: {line}")
    return found[:8]
