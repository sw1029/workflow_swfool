#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any, Iterable


DEFAULT_STEPS = [
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
CANONICAL_STEPS = set(DEFAULT_STEPS)
CYCLE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")

PART_L_M_FIELDS = (
    "pass_on_stale_lane",
    "decision_metadata_revision",
    "stale_measurement_artifact",
    "axis_starved_by_missing_producer",
    "producer_supply_required",
    "portfolio_quota_exceeded",
    "unreachable_within_cycle",
    "basis_overclaim",
    "surface_field_defect_matrix",
    "lane_incompatible",
    "scale_incompatible",
    "contract_conflict",
    "destructive_disposition_blocked",
    "reharvest_before_rerun_required",
    "mutually_unsatisfiable_contract",
    "sample_as_universe_misuse",
)
AXIS_FIELDS = (
    "progress_axes",
    "goal_axis_map",
    "axis_delta",
    "axis_stall_streak",
    "goal_axis_stall",
)


class DashboardDataError(ValueError):
    pass


def load_events(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise DashboardDataError(f"cycle ledger does not exist: {path}")
    events: list[dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    value = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise DashboardDataError(f"malformed ledger JSON on line {line_number}: {exc}") from exc
                if not isinstance(value, dict):
                    raise DashboardDataError(f"ledger line {line_number} must contain a JSON object")
                value = dict(value)
                value.setdefault("_ledger_line", line_number)
                events.append(value)
    except (OSError, UnicodeError) as exc:
        raise DashboardDataError(f"cannot read cycle ledger: {exc}") from exc
    return events


def load_current(path: Path) -> tuple[dict[str, Any], str]:
    if not path.is_file():
        return {}, "missing"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return {"error": str(exc)}, "malformed"
    if not isinstance(value, dict):
        return {"error": "current_stage.json must contain an object"}, "malformed"
    version = value.get("format_version", 0)
    if isinstance(version, bool) or not isinstance(version, int) or version not in {0, 1}:
        return {"error": f"unsupported current_stage format_version: {version!r}"}, "malformed"
    return value, "loaded"


def values(value: Any) -> list[str]:
    if isinstance(value, list):
        result: list[str] = []
        for item in value:
            if isinstance(item, dict):
                candidate = item.get("path") or item.get("id") or item.get("issue_id")
                if candidate is not None:
                    result.append(str(candidate))
                else:
                    result.append(json.dumps(item, ensure_ascii=False, sort_keys=True))
            elif item is not None and str(item).strip():
                result.append(str(item))
        return result
    if isinstance(value, dict):
        return [json.dumps(value, ensure_ascii=False, sort_keys=True)] if value else []
    if value is not None and str(value).strip():
        return [str(value)]
    return []


def unique(items: Iterable[Any]) -> list[str]:
    return sorted({str(item) for item in items if item is not None and str(item).strip()})


def collect_fields(events: list[dict[str, Any]], fields: Iterable[str]) -> list[str]:
    collected: list[str] = []
    for event in events:
        for field in fields:
            collected.extend(values(event.get(field)))
    return unique(collected)


def evidence_paths(events: list[dict[str, Any]]) -> list[str]:
    collected = collect_fields(events, ("evidence_paths", "artifacts", "artifact_paths", "logs"))
    for event in events:
        for ref in event.get("artifact_refs") or []:
            if isinstance(ref, dict) and ref.get("path"):
                collected.append(str(ref["path"]))
        for field in ("report_path", "log_path", "dashboard_path"):
            if event.get(field):
                collected.append(str(event[field]))
    return unique(collected)


def long_run_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for event in events:
        event_kind = str(event.get("event_kind") or "").lower()
        role = str(event.get("long_run_role") or "").lower()
        if event.get("long_run_branch") or event_kind.startswith("long_run_") or role in {"launch", "monitor", "harvest", "finalize"}:
            result.append(event)
    return result


def latest_value(events: list[dict[str, Any]], *fields: str, default: Any = None) -> Any:
    for event in reversed(events):
        for field in fields:
            value = event.get(field)
            if value is not None and value != "":
                return value
    return default


def event_malformed_reasons(event: dict[str, Any], cycle_id: str) -> list[str]:
    reasons: list[str] = []
    version = event.get("format_version", 0)
    if isinstance(version, bool) or not isinstance(version, int) or version not in {0, 1}:
        reasons.append("unsupported_format_version")
    step = event.get("step")
    if not isinstance(step, str) or not step.strip():
        reasons.append("missing_step")
    elif step not in CANONICAL_STEPS:
        reasons.append("noncanonical_step")
    if not isinstance(event.get("status"), str) or not str(event.get("status")).strip():
        reasons.append("missing_status")
    event_cycle_id = event.get("cycle_id")
    if event_cycle_id is not None and str(event_cycle_id) != cycle_id:
        reasons.append("cycle_id_mismatch")
    if version == 1 and event_cycle_id is None:
        reasons.append("missing_cycle_id")
    if version == 1 and not str(event.get("event_id") or "").strip():
        reasons.append("missing_event_id")
    return reasons


def summarize(events: list[dict[str, Any]], current: dict[str, Any], current_load_status: str, cycle_id: str) -> dict[str, Any]:
    latest_by_step: dict[str, dict[str, Any]] = {}
    valid_events: list[dict[str, Any]] = []
    malformed_events: list[dict[str, Any]] = []
    seen_event_ids: set[str] = set()
    for event in events:
        reasons = event_malformed_reasons(event, cycle_id)
        event_id = str(event.get("event_id") or "").strip()
        if event_id and event_id in seen_event_ids:
            reasons.append("duplicate_event_id")
        if event_id:
            seen_event_ids.add(event_id)
        if reasons:
            malformed_events.append({**event, "_dashboard_malformed_reasons": reasons})
            continue
        valid_events.append(event)
        latest_by_step[str(event["step"])] = event

    current_count = current.get("event_count") if isinstance(current.get("event_count"), int) and not isinstance(current.get("event_count"), bool) else None
    ledger_latest_event_id = str(events[-1].get("event_id") or "").strip() if events else ""
    current_latest = current.get("latest_event") if isinstance(current.get("latest_event"), dict) else {}
    current_latest_event_id = str(current_latest.get("event_id") or "").strip()
    if current_load_status != "loaded":
        snapshot_status = current_load_status
    elif current_count != len(events):
        snapshot_status = "stale"
    elif (ledger_latest_event_id or current_latest_event_id) and ledger_latest_event_id != current_latest_event_id:
        snapshot_status = "stale"
    else:
        snapshot_status = "current"

    task_ids = collect_fields(valid_events, ("task_id", "completed_task_id", "next_task_id"))
    issue_ids = collect_fields(valid_events, ("issue_id", "issue_ids", "issue_path", "issue_paths", "issue_url", "issue_urls"))
    changed_files = collect_fields(valid_events, ("changed_files",))
    blockers = collect_fields(valid_events, ("blockers",))
    artifacts = evidence_paths(valid_events)
    validation = str(latest_value(valid_events, "validation_verdict", default="not_run"))
    progress = str(latest_value(valid_events, "progress_verdict", default="not_run"))
    task_id = str(latest_value(valid_events, "task_id", "completed_task_id", default="unknown-task"))
    progress_axes = [
        {"step": event.get("step"), field: event[field]}
        for event in valid_events
        for field in AXIS_FIELDS
        if field in event and event[field] not in (None, "", [], {})
    ]
    lineage_findings = [
        {"step": event.get("step"), field: event[field]}
        for event in valid_events
        for field in PART_L_M_FIELDS
        if field in event and event[field] not in (None, False, "", [], {})
    ]
    commit_results = [
        {
            "step": event.get("step"),
            "commit_role": event.get("commit_role"),
            "commit_status": event.get("commit_status") or event.get("status"),
            "commit_hash": event.get("commit_hash"),
            "commit_subject": event.get("commit_subject"),
        }
        for event in valid_events
        if event.get("step") in {"commit", "closeout_commit"}
    ]
    issue_results = [
        {
            "issue_packet_id": event.get("issue_packet_id"),
            "issue_status": event.get("issue_status") or event.get("status"),
            "issue_ids": event.get("issue_ids") or values(event.get("issue_id")),
        }
        for event in valid_events
        if event.get("step") == "issue"
    ]
    long_runs = long_run_events(valid_events)
    findings: list[dict[str, Any]] = []
    if snapshot_status != "current":
        findings.append({"severity": "warn", "code": "current_stage_snapshot_not_current", "status": snapshot_status})
    if malformed_events:
        findings.append({"severity": "warn", "code": "malformed_or_noncanonical_events", "count": len(malformed_events)})
    if not events:
        findings.append({"severity": "warn", "code": "empty_cycle_ledger"})
    elif not valid_events:
        findings.append({"severity": "warn", "code": "no_valid_cycle_events"})
    dashboard_status = "rendered" if not findings else "warn"
    return {
        "format_version": 1,
        "step": "dashboard",
        "cycle_id": cycle_id,
        "task_id": task_id,
        "dashboard_status": dashboard_status,
        "event_count": len(events),
        "valid_event_count": len(valid_events),
        "current_stage_event_count": current_count,
        "ledger_latest_event_id": ledger_latest_event_id or None,
        "current_stage_latest_event_id": current_latest_event_id or None,
        "snapshot_status": snapshot_status,
        "latest_event": valid_events[-1] if valid_events else {},
        "latest_by_step": latest_by_step,
        "malformed_events": malformed_events,
        "task_ids": task_ids,
        "changed_files": changed_files,
        "artifacts": artifacts,
        "issue_ids": issue_ids,
        "issue_results": issue_results,
        "commit_results": commit_results,
        "long_runs": long_runs,
        "validation_verdict": validation,
        "progress_verdict": progress,
        "progress_axes": progress_axes,
        "lineage_findings": lineage_findings,
        "blockers": blockers,
        "findings": findings,
    }


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
        "",
        "## 단계 상태",
    ]
    for step in DEFAULT_STEPS:
        event = summary["latest_by_step"].get(step)
        if not event:
            continue
        reason = event.get("reason") or ""
        lines.append(f"- {step}: {event.get('status') or 'unknown'}" + (f" - {reason}" if reason else ""))
    if summary["malformed_events"]:
        lines.extend(["", "## 비정상/비정식 이벤트"])
        for event in summary["malformed_events"][-10:]:
            reasons = ",".join(event.get("_dashboard_malformed_reasons") or [])
            lines.append(f"- line {event.get('_ledger_line', '?')}: {event.get('step') or 'missing_step'} ({reasons})")

    runs = summary["long_runs"]
    if runs:
        lines.extend(["", "## 장기 실행 상태"])
        for event in runs[-10:]:
            status = event.get("execution_status") or event.get("source_status") or event.get("status") or "unknown"
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
        ("Part L/M 미해결 증거", summary["lineage_findings"]),
        ("Dashboard Findings", summary["findings"]),
    ):
        lines.extend(["", f"## {title}"])
        lines.extend([f"- {json.dumps(item, ensure_ascii=False, sort_keys=True)}" for item in section_values] or ["- 없음"])
    return "\n".join(lines).rstrip() + "\n"


def render(events: list[dict[str, Any]], cycle_id: str, current: dict[str, Any] | None = None, current_load_status: str = "missing") -> str:
    return render_summary(summarize(events, current or {}, current_load_status, cycle_id))


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_value = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_value)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        try:
            directory_descriptor = os.open(path.parent, os.O_RDONLY)
        except OSError:
            directory_descriptor = None
        if directory_descriptor is not None:
            try:
                os.fsync(directory_descriptor)
            finally:
                os.close(directory_descriptor)
    finally:
        if temporary.exists():
            temporary.unlink()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render a fail-closed .task/cycle dashboard and result contract.")
    parser.add_argument("--root", default=".")
    parser.add_argument("--cycle-id", required=True)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    parser.add_argument("--result-output", help="Optional dashboard result-contract JSON path.")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    if not CYCLE_ID_PATTERN.fullmatch(args.cycle_id):
        error = {"format_version": 1, "step": "dashboard", "dashboard_status": "block", "error": "cycle_id is not path-safe"}
        if args.format == "json":
            json.dump(error, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
            sys.stdout.write("\n")
        else:
            sys.stderr.write("dashboard blocked: cycle_id is not path-safe\n")
        return 2
    cycle_dir = root / ".task" / "cycle" / args.cycle_id
    ledger = cycle_dir / "stage.jsonl"
    current_path = cycle_dir / "current_stage.json"
    dashboard_path = cycle_dir / "dashboard.md"
    for label, path in (("cycle directory", cycle_dir), ("ledger", ledger), ("current snapshot", current_path), ("dashboard", dashboard_path)):
        try:
            path.resolve(strict=False).relative_to(root)
        except ValueError:
            message = f"{label} escapes the workspace root, including through a symlink"
            if args.format == "json":
                json.dump({"format_version": 1, "step": "dashboard", "dashboard_status": "block", "error": message}, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
                sys.stdout.write("\n")
            else:
                sys.stderr.write(f"dashboard blocked: {message}\n")
            return 2
    try:
        events = load_events(ledger)
    except DashboardDataError as exc:
        error = {"format_version": 1, "step": "dashboard", "dashboard_status": "block", "error": str(exc)}
        if args.format == "json":
            json.dump(error, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
            sys.stdout.write("\n")
        else:
            sys.stderr.write(f"dashboard blocked: {exc}\n")
        return 2
    current, current_load_status = load_current(current_path)
    summary = summarize(events, current, current_load_status, args.cycle_id)
    markdown = render_summary(summary)
    if args.write:
        atomic_write(dashboard_path, markdown)
    summary["dashboard_path"] = dashboard_path.relative_to(root).as_posix() if args.write else "stdout:dashboard"
    summary["evidence_paths"] = unique(
        [ledger.relative_to(root).as_posix()]
        + ([current_path.relative_to(root).as_posix()] if current_path.is_file() else [])
        + ([summary["dashboard_path"]] if args.write else [])
        + summary["artifacts"]
    )
    if args.result_output:
        result_path = Path(args.result_output)
        result_path = (result_path if result_path.is_absolute() else root / result_path).resolve(strict=False)
        try:
            result_path.relative_to(root)
        except ValueError:
            sys.stderr.write("dashboard blocked: result output must stay inside workspace root\n")
            return 2
        summary["result_path"] = result_path.relative_to(root).as_posix()
        summary["evidence_paths"] = unique(summary["evidence_paths"] + [summary["result_path"]])
        atomic_write(result_path, json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    if args.format == "json":
        json.dump(summary, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(markdown)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
