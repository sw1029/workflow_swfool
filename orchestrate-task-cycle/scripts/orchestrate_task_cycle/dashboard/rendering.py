from __future__ import annotations

import json
from typing import Any

from .constants import DEFAULT_STEPS


def render_summary(summary: dict[str, Any]) -> str:
    latest = summary["latest_event"]
    lines = [
        f"# 사이클 대시보드: {summary['cycle_id']}",
        "",
        f"- 이벤트 수(event_count): {summary['event_count']}",
        f"- current_stage 이벤트 수: {summary['current_stage_event_count'] if summary['current_stage_event_count'] is not None else 'unknown'}",
        f"- snapshot 상태: {summary['snapshot_status']}",
        f"- 최신 단계(latest_step): {latest.get('step') or 'none'}",
        f"- 최신 상태(latest_status): {latest.get('status') or 'none'}",
        f"- 검증 판정(validation_verdict): {summary['validation_verdict']}",
        f"- 진행 판정(progress_verdict): {summary['progress_verdict']}",
        f"- unchanged_ref 수: {summary['unchanged_ref_count']}",
        "",
        "## 단계 상태",
    ]
    for step in DEFAULT_STEPS:
        event = summary["latest_by_step"].get(step)
        if not event:
            continue
        reason = event.get("reason") or ""
        lines.append(
            f"- {step}: {event.get('status') or 'unknown'}"
            + (f" - {reason}" if reason else "")
        )
    if summary["malformed_events"]:
        lines.extend(["", "## 비정상/비정식 이벤트"])
        for event in summary["malformed_events"][-10:]:
            reasons = ",".join(event.get("_dashboard_malformed_reasons") or [])
            lines.append(
                f"- line {event.get('_ledger_line', '?')}: "
                f"{event.get('step') or 'missing_step'} ({reasons})"
            )

    runs = summary["long_runs"]
    if runs:
        lines.extend(["", "## 장기 실행 상태"])
        for event in runs[-10:]:
            status = (
                event.get("execution_status")
                or event.get("source_status")
                or event.get("status")
                or "unknown"
            )
            run_id = event.get("run_id") or "unknown-run"
            role = event.get("long_run_role") or event.get("event_kind") or "long_run"
            remaining = event.get("remaining_validation") or ""
            detail = f" - remaining_validation: {remaining}" if remaining else ""
            lines.append(f"- {run_id}: {status} ({role}){detail}")

    sections = (
        ("Task IDs", summary["task_ids"]),
        ("변경 파일", summary["changed_files"]),
        ("증거 경로", summary["artifacts"]),
        ("Issue IDs", summary["issue_ids"]),
        ("블로커", summary["blockers"]),
    )
    for title, section_values in sections:
        lines.extend(["", f"## {title}"])
        lines.extend([f"- {item}" for item in section_values] or ["- 없음"])
    for title, section_values in (
        ("Issue 결과", summary["issue_results"]),
        ("Commit 결과", summary["commit_results"]),
        ("Progress Axes", summary["progress_axes"]),
        ("분리 판정 축", summary["verdict_axes"]),
        ("Unchanged References", summary["unchanged_refs"]),
        ("Part L/M 미해결 증거", summary["lineage_findings"]),
        ("Dashboard Findings", summary["findings"]),
    ):
        lines.extend(["", f"## {title}"])
        lines.extend(
            [
                f"- {json.dumps(item, ensure_ascii=False, sort_keys=True)}"
                for item in section_values
            ]
            or ["- 없음"]
        )
    return "\n".join(lines).rstrip() + "\n"
