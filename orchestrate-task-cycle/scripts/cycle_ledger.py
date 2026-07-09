#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
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

MIN_FIELDS = [
    "cycle_id",
    "event_id",
    "step",
    "status",
    "reason",
    "task_id",
    "completed_task_id",
    "next_task_id",
    "changed_files",
    "artifacts",
    "artifact_refs",
    "unchanged_refs",
    "validation_verdict",
    "progress_verdict",
    "blockers",
    "code_structure_audit",
    "qualitative_review",
    "anti_loop_progress_gate",
    "validation_set",
    "task_pack_id",
    "task_pack_item_id",
    "task_pack_path",
    "task_pack_status",
    "selected_task_source",
    "promoted_item_id",
    "completed_item_id",
    "blocker_signature",
    "input_delta_gate",
    "terminal_blocker",
    "used_advice",
    "authority_policy",
    "authority_policy_source",
    "created_at",
]

STAGE_STATUS_NORMALIZATION = {
    "success": "complete",
    "succeeded": "complete",
}


def normalize_stage_status(value: Any) -> str:
    raw = str(value).strip().lower() if value is not None else "complete"
    return STAGE_STATUS_NORMALIZATION.get(raw, raw)


def truthy_delta(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() not in {"", "0", "false", "none", "null", "unchanged", "no_delta"}
    return bool(value)


def now_iso() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def default_cycle_id() -> str:
    return "cycle-" + dt.datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")


def rel_path(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def cycle_dir(root: Path, cycle_id: str) -> Path:
    return root / ".task" / "cycle" / cycle_id


def ledger_path(root: Path, cycle_id: str) -> Path:
    return cycle_dir(root, cycle_id) / "stage.jsonl"


def current_stage_path(root: Path, cycle_id: str) -> Path:
    return cycle_dir(root, cycle_id) / "current_stage.json"


def load_json_value(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    if value == "-":
        raw = sys.stdin.read()
        return json.loads(raw) if raw.strip() else {}
    path = Path(value)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return json.loads(value)


def normalize_list(*values: Any) -> list[str]:
    result: list[str] = []
    for value in values:
        if value is None:
            continue
        if isinstance(value, list):
            result.extend(str(item) for item in value if item is not None and str(item) != "")
        elif isinstance(value, tuple):
            result.extend(str(item) for item in value if item is not None and str(item) != "")
        elif str(value) != "":
            result.append(str(value))
    return result


def file_sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError:
        return None
    return digest.hexdigest()


def artifact_path(root: Path, artifact: str) -> Path:
    path = Path(artifact)
    return path if path.is_absolute() else root / path


def prior_artifact_refs(root: Path, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for event in events:
        for ref in event.get("artifact_refs") or []:
            if isinstance(ref, dict) and ref.get("path") and ref.get("sha256"):
                refs.append(ref)
        for artifact in normalize_list(event.get("artifacts")):
            if not artifact:
                continue
            refs.append({"path": artifact, "sha256": file_sha256(artifact_path(root, artifact))})
    return refs


def annotate_artifact_refs(root: Path, event: dict[str, Any], previous_events: list[dict[str, Any]]) -> None:
    previous = prior_artifact_refs(root, previous_events)
    artifact_refs: list[dict[str, Any]] = []
    unchanged_refs: list[dict[str, str]] = []
    for artifact in normalize_list(event.get("artifacts")):
        digest = file_sha256(artifact_path(root, artifact))
        if not digest:
            continue
        ref: dict[str, Any] = {"path": artifact, "sha256": digest}
        prior = next(
            (
                item
                for item in reversed(previous)
                if item.get("sha256") == digest and item.get("path") == artifact
            ),
            None,
        ) or next((item for item in reversed(previous) if item.get("sha256") == digest), None)
        if prior and prior.get("path") and prior.get("sha256"):
            ref["unchanged_ref"] = {"path": str(prior["path"]), "sha256": str(prior["sha256"])}
            unchanged_refs.append(ref["unchanged_ref"])
        artifact_refs.append(ref)
    if artifact_refs:
        event["artifact_refs"] = artifact_refs
    if unchanged_refs:
        event["unchanged_refs"] = unchanged_refs


def make_event_id(cycle_id: str, step: str, created_at: str, event: dict[str, Any]) -> str:
    basis = json.dumps({k: v for k, v in event.items() if k != "event_id"}, ensure_ascii=False, sort_keys=True)
    digest = hashlib.sha256(basis.encode("utf-8")).hexdigest()[:10]
    stamp = created_at.replace(":", "").replace("-", "").split("+")[0]
    return f"{cycle_id}-{step}-{stamp}-{digest}"


def complete_event(cycle_id: str, event: dict[str, Any]) -> dict[str, Any]:
    event = dict(event)
    created_at = str(event.get("created_at") or now_iso())
    step = str(event.get("step") or "unknown")
    raw_status = event.get("status")
    event.setdefault("cycle_id", cycle_id)
    event.setdefault("created_at", created_at)
    event.setdefault("event_id", make_event_id(cycle_id, step, created_at, event))
    event["status"] = normalize_stage_status(raw_status)
    if raw_status is not None and event["status"] != str(raw_status).strip().lower():
        event.setdefault("source_status", str(raw_status).strip().lower())
    event.setdefault("reason", "")
    event.setdefault("task_id", None)
    event.setdefault("completed_task_id", None)
    event.setdefault("next_task_id", None)
    event["changed_files"] = normalize_list(event.get("changed_files"))
    event["artifacts"] = normalize_list(event.get("artifacts"))
    event["blockers"] = normalize_list(event.get("blockers"))
    event.setdefault("validation_verdict", None)
    event.setdefault("progress_verdict", None)
    event.setdefault("authority_policy", None)
    event.setdefault("authority_policy_source", None)
    for field in MIN_FIELDS:
        event.setdefault(field, None)
    return event


def validate_event_step(event: dict[str, Any], allow_noncanonical_step: bool) -> dict[str, Any]:
    event = dict(event)
    raw_step = event.get("step")
    step = str(raw_step).strip() if raw_step is not None else ""
    if not step:
        raise ValueError("stage event requires a non-empty `step`")
    event["step"] = step
    if step not in CANONICAL_STEPS:
        if not allow_noncanonical_step:
            raise ValueError(f"noncanonical stage step `{step}` requires --allow-noncanonical-step")
        event["noncanonical_step"] = True
    return event


def terminal_latch_state(previous_events: list[dict[str, Any]], event: dict[str, Any]) -> dict[str, Any]:
    if not event.get("terminal_justified"):
        return {}
    tuple_fields = ("terminal_outcome_family_key", "input_state_fingerprint", "authority_state_fingerprint")
    current_key = tuple(str(event.get(field) or "") for field in tuple_fields)
    if not all(current_key):
        return {"terminal_latch_status": "not_evaluated", "terminal_latch_missing_fields": [field for field, value in zip(tuple_fields, current_key) if not value]}
    residuals = event.get("residual_classification") or event.get("residuals") or []
    residual_classes = {
        str(item.get("classification") or item.get("residual_class") or item)
        for item in residuals
        if isinstance(item, (dict, str))
    }
    if residual_classes & {"self_resolvable_local", "offline_recompute", "existing_authority", "unverified"}:
        return {"terminal_latch_status": "prohibited", "quiescent_terminal_latched": False, "terminal_latch_residual_classes": sorted(residual_classes)}
    previous = next(
        (
            row
            for row in reversed(previous_events)
            if tuple(str(row.get(field) or "") for field in tuple_fields) == current_key
        ),
        None,
    )
    material_delta = truthy_delta(event.get("material_delta")) or truthy_delta(event.get("input_delta"))
    if previous is not None and not material_delta:
        return {
            "terminal_latch_status": "latched",
            "quiescent_terminal_latched": True,
            "suppress_full_cycle": True,
            "terminal_latch_streak": int(previous.get("terminal_latch_streak") or 1) + 1,
            "unchanged_terminal_ref": previous.get("event_id"),
        }
    if material_delta and any(row.get("quiescent_terminal_latched") for row in previous_events):
        transition = event.get("lifecycle_transition_result") if isinstance(event.get("lifecycle_transition_result"), dict) else {}
        required = ("seal_updated", "registry_updated", "pack_updated", "index_updated")
        return {
            "terminal_latch_status": "reopened" if all(transition.get(field) for field in required) else "reopen_incomplete",
            "quiescent_terminal_latched": False,
            "lifecycle_transition_result": {**transition, "atomic": all(transition.get(field) for field in required)},
        }
    return {"terminal_latch_status": "observed", "quiescent_terminal_latched": False, "terminal_latch_streak": 1}


def read_events(root: Path, cycle_id: str) -> list[dict[str, Any]]:
    path = ledger_path(root, cycle_id)
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


def read_all_cycle_events(root: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    cycle_root = root / ".task" / "cycle"
    if not cycle_root.is_dir():
        return events
    for path in sorted(cycle_root.glob("*/stage.jsonl")):
        events.extend(read_events(root, path.parent.name))
    return events


def write_current(root: Path, cycle_id: str, events: list[dict[str, Any]]) -> dict[str, Any]:
    latest_by_step: dict[str, dict[str, Any]] = {}
    malformed_events: list[dict[str, Any]] = []
    for event in events:
        step = str(event.get("step") or "unknown")
        if step in CANONICAL_STEPS:
            latest_by_step[step] = event
        else:
            malformed_events.append(event)
    latest = events[-1] if events else {}
    status = "empty"
    if any(str(event.get("status")).lower() in {"blocked", "failed", "block"} for event in events):
        status = "blocked"
    elif latest:
        status = str(latest.get("status") or "unknown")
    current = {
        "cycle_id": cycle_id,
        "updated_at": now_iso(),
        "status": status,
        "latest_event": latest,
        "steps": {step: latest_by_step[step] for step in sorted(latest_by_step)},
        "malformed_event_count": len(malformed_events),
        "malformed_events": malformed_events[-10:],
        "event_count": len(events),
    }
    path = current_stage_path(root, cycle_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(current, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return current


def append_event(root: Path, cycle_id: str, event: dict[str, Any], allow_noncanonical_step: bool = False) -> dict[str, Any]:
    directory = cycle_dir(root, cycle_id)
    (directory / "packets").mkdir(parents=True, exist_ok=True)
    path = ledger_path(root, cycle_id)
    previous_events = read_events(root, cycle_id)
    event = validate_event_step(event, allow_noncanonical_step)
    latch = terminal_latch_state(previous_events, event)
    event.update(latch)
    if latch.get("suppress_full_cycle"):
        current = write_current(root, cycle_id, previous_events)
        return {
            "event": {
                "cycle_id": cycle_id,
                "step": event.get("step"),
                "created_at": now_iso(),
                **latch,
            },
            "event_suppressed": True,
            "current_stage": current,
            "ledger_path": rel_path(root, path),
            "current_stage_path": rel_path(root, current_stage_path(root, cycle_id)),
        }
    completed = complete_event(cycle_id, event)
    annotate_artifact_refs(root, completed, previous_events)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(completed, ensure_ascii=False, sort_keys=True) + "\n")
    current = write_current(root, cycle_id, previous_events + [completed])
    return {"event": completed, "current_stage": current, "ledger_path": rel_path(root, path), "current_stage_path": rel_path(root, current_stage_path(root, cycle_id))}


def init_cycle(
    root: Path,
    cycle_id: str | None,
    task_id: str | None,
    reason: str,
    terminal_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if terminal_state:
        latch = terminal_latch_state(read_all_cycle_events(root), terminal_state)
        if latch.get("suppress_full_cycle"):
            return {
                "cycle_suppressed": True,
                "reason": "quiescent_terminal_latched",
                **latch,
            }
    cycle_id = cycle_id or default_cycle_id()
    directory = cycle_dir(root, cycle_id)
    (directory / "packets").mkdir(parents=True, exist_ok=True)
    if not ledger_path(root, cycle_id).exists():
        ledger_path(root, cycle_id).write_text("", encoding="utf-8")
    result = append_event(
        root,
        cycle_id,
        {
            "step": "ledger_init",
            "status": "complete",
            "reason": reason or "cycle ledger initialized",
            "task_id": task_id,
            "artifacts": [rel_path(root, ledger_path(root, cycle_id)), rel_path(root, current_stage_path(root, cycle_id))],
        },
    )
    result["cycle_id"] = cycle_id
    result["cycle_dir"] = rel_path(root, directory)
    return result


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
        "cycle_id": latest.get("cycle_id") if latest else None,
        "event_count": len(events),
        "latest_status": latest.get("status") if latest else None,
        "latest_step": latest.get("step") if latest else None,
        "steps": {step: {"status": event.get("status"), "reason": event.get("reason")} for step, event in latest_by_step.items()},
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
        "validation_verdict": latest.get("validation_verdict") or next((event.get("validation_verdict") for event in reversed(events) if event.get("validation_verdict")), None),
        "progress_verdict": latest.get("progress_verdict") or next((event.get("progress_verdict") for event in reversed(events) if event.get("progress_verdict")), None),
        "task_id": latest.get("task_id") or next((event.get("task_id") for event in reversed(events) if event.get("task_id")), None),
        "completed_task_id": next((event.get("completed_task_id") for event in reversed(events) if event.get("completed_task_id")), None),
        "next_task_id": next((event.get("next_task_id") for event in reversed(events) if event.get("next_task_id")), None),
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
    for title, key in (("변경 파일", "changed_files"), ("아티팩트", "artifacts"), ("Task Pack", "task_pack"), ("블로커", "blockers")):
        lines.extend(["", f"## {title}"])
        values = summary.get(key) or []
        if values:
            lines.extend(f"- {item}" for item in values)
        else:
            lines.append("- 없음")
    return "\n".join(lines).rstrip() + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Maintain .task/cycle/<cycle-id> stage ledger artifacts.")
    parser.add_argument("--root", default=".", help="Workspace root.")
    sub = parser.add_subparsers(dest="command", required=True)

    init_p = sub.add_parser("init", help="Initialize a cycle ledger.")
    init_p.add_argument("--cycle-id")
    init_p.add_argument("--task-id")
    init_p.add_argument("--reason", default="cycle ledger initialized")
    init_p.add_argument("--terminal-state-json", help="Optional terminal state used to suppress an unchanged full-cycle restart.")

    append_p = sub.add_parser("append", help="Append a stage event.")
    append_p.add_argument("--cycle-id", required=True)
    append_p.add_argument("--event-json", help="JSON object, JSON file path, or '-' for stdin.")
    append_p.add_argument("--step")
    append_p.add_argument("--status")
    append_p.add_argument("--reason")
    append_p.add_argument("--task-id")
    append_p.add_argument("--completed-task-id")
    append_p.add_argument("--next-task-id")
    append_p.add_argument("--changed-file", action="append", default=[])
    append_p.add_argument("--artifact", action="append", default=[])
    append_p.add_argument("--blocker", action="append", default=[])
    append_p.add_argument("--validation-verdict")
    append_p.add_argument("--progress-verdict")
    append_p.add_argument("--task-pack-id")
    append_p.add_argument("--task-pack-item-id")
    append_p.add_argument("--task-pack-path")
    append_p.add_argument("--task-pack-status")
    append_p.add_argument("--selected-task-source")
    append_p.add_argument("--promoted-item-id")
    append_p.add_argument("--completed-item-id")
    append_p.add_argument("--blocker-signature")
    append_p.add_argument("--input-delta-gate")
    append_p.add_argument("--terminal-blocker")
    append_p.add_argument("--authority-policy")
    append_p.add_argument("--authority-policy-source")
    append_p.add_argument("--allow-noncanonical-step", action="store_true", help="Allow a noncanonical step and mark it as malformed/noncanonical evidence.")

    render_p = sub.add_parser("render", help="Render a ledger summary.")
    render_p.add_argument("--cycle-id", required=True)
    render_p.add_argument("--format", choices=("json", "markdown"), default="markdown")
    render_p.add_argument("--write-dashboard", action="store_true")

    current_p = sub.add_parser("current", help="Refresh and print current_stage.json.")
    current_p.add_argument("--cycle-id", required=True)

    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    if args.command == "init":
        result = init_cycle(root, args.cycle_id, args.task_id, args.reason, load_json_value(args.terminal_state_json))
    elif args.command == "append":
        event = load_json_value(args.event_json)
        for attr, key in (
            ("step", "step"),
            ("status", "status"),
            ("reason", "reason"),
            ("task_id", "task_id"),
            ("completed_task_id", "completed_task_id"),
            ("next_task_id", "next_task_id"),
            ("validation_verdict", "validation_verdict"),
            ("progress_verdict", "progress_verdict"),
            ("task_pack_id", "task_pack_id"),
            ("task_pack_item_id", "task_pack_item_id"),
            ("task_pack_path", "task_pack_path"),
            ("task_pack_status", "task_pack_status"),
            ("selected_task_source", "selected_task_source"),
            ("promoted_item_id", "promoted_item_id"),
            ("completed_item_id", "completed_item_id"),
            ("blocker_signature", "blocker_signature"),
            ("input_delta_gate", "input_delta_gate"),
            ("terminal_blocker", "terminal_blocker"),
            ("authority_policy", "authority_policy"),
            ("authority_policy_source", "authority_policy_source"),
        ):
            value = getattr(args, attr)
            if value is not None:
                event[key] = value
        if args.changed_file:
            event["changed_files"] = normalize_list(event.get("changed_files"), args.changed_file)
        if args.artifact:
            event["artifacts"] = normalize_list(event.get("artifacts"), args.artifact)
        if args.blocker:
            event["blockers"] = normalize_list(event.get("blockers"), args.blocker)
        result = append_event(root, args.cycle_id, event, allow_noncanonical_step=args.allow_noncanonical_step)
    elif args.command == "render":
        summary = summarize(read_events(root, args.cycle_id))
        if args.write_dashboard:
            dashboard = cycle_dir(root, args.cycle_id) / "dashboard.md"
            dashboard.parent.mkdir(parents=True, exist_ok=True)
            dashboard.write_text(render_markdown(summary), encoding="utf-8")
            summary["dashboard_path"] = rel_path(root, dashboard)
        if args.format == "markdown":
            sys.stdout.write(render_markdown(summary))
            return 0
        result = summary
    else:
        result = write_current(root, args.cycle_id, read_events(root, args.cycle_id))

    json.dump(result, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
