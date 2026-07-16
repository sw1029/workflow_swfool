from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .access import (
    deep_get,
    dict_list,
    extend_unique,
    first_value,
    normalized_path_list,
    stage_event_candidates,
    truthy,
)


def context_goal_truth(context: dict[str, Any]) -> list[str]:
    used = deep_get(context, "agent_goal", "used_goal_truth")
    if isinstance(used, list):
        return [str(path) for path in used]
    files = deep_get(context, "agent_goal", "goal_truth_files")
    if isinstance(files, dict):
        return [
            str(info.get("path"))
            for info in files.values()
            if isinstance(info, dict) and info.get("exists")
        ]
    return []


def stage_goal_truth(stage: dict[str, Any]) -> list[str]:
    paths: list[str] = []
    for candidate in stage_event_candidates(stage):
        for key in ("used_goal_truth", "gt_files", "goal_truth"):
            extend_unique(paths, normalized_path_list(candidate.get(key)))
        for nested in ("packet", "result"):
            extend_unique(
                paths,
                normalized_path_list(deep_get(candidate, nested, "used_goal_truth")),
            )
    return paths


def context_active_advice(context: dict[str, Any]) -> list[str]:
    active = deep_get(context, "external_advice", "active_files")
    if isinstance(active, list):
        return [
            str(item.get("path"))
            for item in active
            if isinstance(item, dict) and item.get("path")
        ]
    return []


def stage_used_advice(stage: dict[str, Any]) -> list[str]:
    paths: list[str] = []
    for candidate in stage_event_candidates(stage):
        for key in ("used_advice", "external_advice", "advice"):
            extend_unique(paths, normalized_path_list(candidate.get(key)))
        for nested in ("packet", "result"):
            extend_unique(
                paths,
                normalized_path_list(deep_get(candidate, nested, "used_advice")),
            )
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
            value = (
                candidate.get(field)
                or deep_get(candidate, "packet", field)
                or deep_get(candidate, "result", field)
            )
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
        if (
            truthy(candidate.get("long_run_branch"))
            or event_kind.startswith("long_run_")
            or role in {"launch", "monitor", "harvest", "finalize"}
        ):
            events.append(candidate)
    return events


def active_long_run_events(stage: dict[str, Any]) -> list[dict[str, Any]]:
    active_statuses = {
        "launching",
        "running",
        "completed_pending_validation",
        "stale",
        "not_running",
    }
    return [
        event
        for event in long_run_events(stage)
        if str(
            event.get("execution_status")
            or event.get("source_status")
            or event.get("status")
            or ""
        ).lower()
        in active_statuses
    ]


def stage_authority_policy(stage: dict[str, Any]) -> Any:
    for candidate in stage_event_candidates(stage):
        for key in ("authority_policy", "authority", "effective_authority_policy"):
            value = candidate.get(key)
            if value:
                return value
        value = deep_get(candidate, "packet", "authority_policy") or deep_get(
            candidate, "routing", "authority_policy"
        )
        if value:
            return value
    return None


def selected_disposition(
    stage: dict[str, Any],
    next_progress_kind: str,
    terminal_blocker: Any,
) -> str:
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
        if value in {
            "goal_productive",
            "consolidation",
            "terminal_blocked",
            "user_escalation",
        }:
            return value
        if "consolidation" in value:
            return "consolidation"
        if "goal_productive" in value:
            return "goal_productive"
        if "terminal" in value:
            return "terminal_blocked"
        if "user_escalation" in value or "user-escalation" in value:
            return "user_escalation"
    return (
        "goal_productive"
        if next_progress_kind == "goal_productive"
        else next_progress_kind
    )


def signature_values(value: Any, key: str) -> list[str]:
    if isinstance(value, str) and value.strip():
        return [value.strip().lower()]
    values: list[str] = []
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
            raw = (
                deep_get(candidate, *path.split("."))
                if "." in path
                else candidate.get(path)
            )
            _extend_signatures(values, seen, raw)
        for path in list_paths:
            raw = (
                deep_get(candidate, *path.split("."))
                if "." in path
                else candidate.get(path)
            )
            for item in raw if isinstance(raw, list) else [raw]:
                _extend_signatures(values, seen, item)
    return values


def _extend_signatures(values: list[str], seen: set[str], raw: Any) -> None:
    for value in signature_values(raw, "semantic_signature"):
        if value not in seen:
            values.append(value)
            seen.add(value)


def collect_sealed_families(context: dict[str, Any]) -> list[dict[str, Any]]:
    root = Path(str(context.get("workspace") or "."))
    sealed: list[dict[str, Any]] = []
    for path in (root / ".task").glob("sealed_blocker_families.json*"):
        for record in _read_sealed_records(path):
            _append_sealed_records(sealed, record, path)
    pack_root = root / ".task" / "task_pack"
    if pack_root.is_dir():
        for path in pack_root.glob("*.json"):
            try:
                pack = json.loads(path.read_text(encoding="utf-8", errors="replace"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(pack, dict) and isinstance(
                pack.get("terminal_blocker"), dict
            ):
                _append_sealed_records(sealed, pack["terminal_blocker"], path)
    return sealed


def _read_sealed_records(path: Path) -> list[Any]:
    records: list[Any] = []
    try:
        if path.suffix == ".jsonl":
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                if line.strip():
                    records.append(json.loads(line))
            return records
        return [json.loads(path.read_text(encoding="utf-8", errors="replace"))]
    except (OSError, json.JSONDecodeError):
        return records


def _append_sealed_records(
    sealed: list[dict[str, Any]],
    record: Any,
    source_path: Path,
) -> None:
    if not isinstance(record, dict):
        return
    if isinstance(record.get("families"), list):
        records = record["families"]
    elif isinstance(record.get("sealed_families"), list):
        records = record["sealed_families"]
    else:
        records = [record]
    for item in records:
        if not isinstance(item, dict):
            continue
        semantic = (
            item.get("semantic_signature")
            or item.get("family")
            or item.get("signature")
        )
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
