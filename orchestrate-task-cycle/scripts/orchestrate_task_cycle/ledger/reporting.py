from __future__ import annotations

from typing import Any

from .constants import CANONICAL_STEPS, DEFAULT_STEPS, LEDGER_FORMAT_VERSION
from .support import normalize_list


def summarize(events: list[dict[str, Any]]) -> dict[str, Any]:
    latest_by_step: dict[str, dict[str, Any]] = {}
    changed_files: list[str] = []
    artifacts: list[str] = []
    unchanged_refs: list[dict[str, Any]] = []
    blockers: list[str] = []
    task_pack_values: list[str] = []
    malformed_events: list[dict[str, Any]] = []
    for event in events:
        step = str(event.get("step") or "unknown")
        if step in CANONICAL_STEPS:
            latest_by_step[step] = event
        else:
            malformed_events.append(event)
        changed_files.extend(normalize_list(event.get("changed_files")))
        artifacts.extend(normalize_list(event.get("artifacts")))
        unchanged_refs.extend(ref for ref in event.get("unchanged_refs") or [] if isinstance(ref, dict))
        blockers.extend(normalize_list(event.get("blockers")))
        task_pack_values.extend(
            normalize_list(
                event.get("task_pack_id"),
                event.get("task_pack_path"),
                event.get("task_pack_status"),
                event.get("task_pack_item_id"),
                event.get("promoted_item_id"),
                event.get("completed_item_id"),
            )
        )
    latest = events[-1] if events else {}
    return {
        "format_version": LEDGER_FORMAT_VERSION,
        "cycle_id": latest.get("cycle_id") if latest else None,
        "event_count": len(events),
        "latest_status": latest.get("status") if latest else None,
        "latest_step": latest.get("step") if latest else None,
        "steps": {
            step: {"status": event.get("status"), "reason": event.get("reason")}
            for step, event in latest_by_step.items()
        },
        "changed_files": sorted(set(changed_files)),
        "artifacts": sorted(set(artifacts)),
        "unchanged_ref_count": len(unchanged_refs),
        "unchanged_refs": unchanged_refs[-20:],
        "blockers": sorted(set(blockers)),
        "task_pack": sorted(set(task_pack_values)),
        "malformed_events": [
            {
                "event_id": event.get("event_id"),
                "step": event.get("step"),
                "status": event.get("status"),
                "reason": event.get("reason"),
            }
            for event in malformed_events[-10:]
        ],
        "validation_verdict": latest.get("validation_verdict")
        or next((event.get("validation_verdict") for event in reversed(events) if event.get("validation_verdict")), None),
        "progress_verdict": latest.get("progress_verdict")
        or next((event.get("progress_verdict") for event in reversed(events) if event.get("progress_verdict")), None),
        "task_id": latest.get("task_id")
        or next((event.get("task_id") for event in reversed(events) if event.get("task_id")), None),
        "completed_task_id": next(
            (event.get("completed_task_id") for event in reversed(events) if event.get("completed_task_id")), None
        ),
        "next_task_id": next(
            (event.get("next_task_id") for event in reversed(events) if event.get("next_task_id")), None
        ),
    }


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        f"# 사이클 대시보드: {summary.get('cycle_id') or 'unknown'}",
        "",
        f"- 이벤트 수(event_count): {summary.get('event_count') or 0}",
        f"- 최신 단계(latest_step): {summary.get('latest_step') or 'none'}",
        f"- 최신 상태(latest_status): {summary.get('latest_status') or 'none'}",
        f"- unchanged_ref 수(unchanged_ref_count): {summary.get('unchanged_ref_count') or 0}",
        f"- 검증 판정(validation_verdict): {summary.get('validation_verdict') or 'not_run'}",
        f"- 진행 판정(progress_verdict): {summary.get('progress_verdict') or 'not_run'}",
        f"- task ID(task_id): {summary.get('task_id') or 'unknown'}",
        f"- 완료 task ID(completed_task_id): {summary.get('completed_task_id') or 'unknown'}",
        f"- 다음 task ID(next_task_id): {summary.get('next_task_id') or 'unknown'}",
        "",
        "## 단계 상태",
    ]
    steps = summary.get("steps") or {}
    for step in DEFAULT_STEPS:
        if step in steps:
            value = steps[step]
            lines.append(f"- {step}: {value.get('status') or 'unknown'} - {value.get('reason') or ''}".rstrip())
    for step in sorted(set(steps) - set(DEFAULT_STEPS)):
        value = steps[step]
        lines.append(f"- {step}: {value.get('status') or 'unknown'} - {value.get('reason') or ''}".rstrip())
    malformed_events = summary.get("malformed_events") or []
    if malformed_events:
        lines.extend(["", "## 비정상 이벤트"])
        for event in malformed_events:
            lines.append(
                f"- {event.get('step') or 'missing_step'}: {event.get('status') or 'unknown'}"
                + (f" - {event.get('reason')}" if event.get("reason") else "")
            )
    for title, key in (
        ("변경 파일", "changed_files"),
        ("아티팩트", "artifacts"),
        ("Task Pack", "task_pack"),
        ("블로커", "blockers"),
    ):
        lines.extend(["", f"## {title}"])
        values = summary.get(key) or []
        if values:
            lines.extend(f"- {item}" for item in values)
        else:
            lines.append("- 없음")
    return "\n".join(lines).rstrip() + "\n"
