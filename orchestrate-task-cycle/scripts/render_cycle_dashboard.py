#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


DEFAULT_STEPS = [
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
CANONICAL_STEPS = set(DEFAULT_STEPS)


def load_events(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    events: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                events.append(value)
    return events


def unique(values: list[Any]) -> list[str]:
    return sorted({str(item) for item in values if item is not None and str(item) != ""})


def long_run_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for event in events:
        event_kind = str(event.get("event_kind") or "").lower()
        role = str(event.get("long_run_role") or "").lower()
        if event.get("long_run_branch") or event_kind.startswith("long_run_") or role in {"launch", "monitor", "harvest", "finalize"}:
            result.append(event)
    return result


def render(events: list[dict[str, Any]], cycle_id: str) -> str:
    latest_by_step: dict[str, dict[str, Any]] = {}
    malformed_events: list[dict[str, Any]] = []
    for event in events:
        step = str(event.get("step") or "unknown")
        if step in CANONICAL_STEPS:
            latest_by_step[step] = event
        else:
            malformed_events.append(event)
    latest = events[-1] if events else {}
    changed_files = unique([item for event in events for item in (event.get("changed_files") or [])])
    artifacts = unique([item for event in events for item in (event.get("artifacts") or [])])
    blockers = unique([item for event in events for item in (event.get("blockers") or [])])
    long_runs = long_run_events(events)
    task_packs = unique(
        [event.get("task_pack_id") for event in events]
        + [event.get("task_pack_path") for event in events]
        + [event.get("task_pack_status") for event in events]
        + [event.get("task_pack_item_id") for event in events]
        + [event.get("promoted_item_id") for event in events]
        + [event.get("completed_item_id") for event in events]
    )
    blocker_signatures = unique([event.get("blocker_signature") for event in events])
    validation = next((event.get("validation_verdict") for event in reversed(events) if event.get("validation_verdict")), "not_run")
    progress = next((event.get("progress_verdict") for event in reversed(events) if event.get("progress_verdict")), "not_run")
    lines = [
        f"# 사이클 대시보드: {cycle_id}",
        "",
        f"- 이벤트 수(event_count): {len(events)}",
        f"- 최신 단계(latest_step): {latest.get('step') or 'none'}",
        f"- 최신 상태(latest_status): {latest.get('status') or 'none'}",
        f"- 검증 판정(validation_verdict): {validation}",
        f"- 진행 판정(progress_verdict): {progress}",
        "",
        "## 단계 상태",
    ]
    for step in DEFAULT_STEPS:
        if step not in latest_by_step:
            continue
        event = latest_by_step[step]
        reason = event.get("reason") or ""
        lines.append(f"- {step}: {event.get('status') or 'unknown'}" + (f" - {reason}" if reason else ""))
    if malformed_events:
        lines.extend(["", "## 비정상 이벤트"])
        for event in malformed_events[-10:]:
            reason = event.get("reason") or ""
            step = event.get("step") or "missing_step"
            lines.append(f"- {step}: {event.get('status') or 'unknown'}" + (f" - {reason}" if reason else ""))
    if long_runs:
        lines.extend(["", "## 장기 실행 상태"])
        for event in long_runs[-10:]:
            status = event.get("execution_status") or event.get("source_status") or event.get("status") or "unknown"
            run_id = event.get("run_id") or "unknown-run"
            role = event.get("long_run_role") or event.get("event_kind") or "long_run"
            remaining = event.get("remaining_validation") or ""
            detail = f" - remaining_validation: {remaining}" if remaining else ""
            lines.append(f"- {run_id}: {status} ({role}){detail}")
    for title, values in (("변경 파일", changed_files), ("아티팩트", artifacts), ("Task Pack", task_packs), ("Blocker Signature", blocker_signatures), ("블로커", blockers)):
        lines.extend(["", f"## {title}"])
        lines.extend([f"- {item}" for item in values] or ["- 없음"])
    return "\n".join(lines).rstrip() + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render .task/cycle dashboard markdown.")
    parser.add_argument("--root", default=".")
    parser.add_argument("--cycle-id", required=True)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    ledger = root / ".task" / "cycle" / args.cycle_id / "stage.jsonl"
    markdown = render(load_events(ledger), args.cycle_id)
    if args.write:
        path = root / ".task" / "cycle" / args.cycle_id / "dashboard.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(markdown, encoding="utf-8")
    sys.stdout.write(markdown)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
