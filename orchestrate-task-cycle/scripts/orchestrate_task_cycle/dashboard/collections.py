from __future__ import annotations

import json
from typing import Any, Iterable

from .constants import CANONICAL_STEPS


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
    return sorted(
        {str(item) for item in items if item is not None and str(item).strip()}
    )


def collect_fields(events: list[dict[str, Any]], fields: Iterable[str]) -> list[str]:
    collected: list[str] = []
    for event in events:
        for field in fields:
            collected.extend(values(event.get(field)))
    return unique(collected)


def evidence_paths(events: list[dict[str, Any]]) -> list[str]:
    collected = collect_fields(
        events, ("evidence_paths", "artifacts", "artifact_paths", "logs")
    )
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
        if (
            event.get("long_run_branch")
            or event_kind.startswith("long_run_")
            or role in {"launch", "monitor", "harvest", "finalize"}
        ):
            result.append(event)
    return result


def latest_value(
    events: list[dict[str, Any]], *fields: str, default: Any = None
) -> Any:
    for event in reversed(events):
        for field in fields:
            value = event.get(field)
            if value is not None and value != "":
                return value
    return default


def event_malformed_reasons(event: dict[str, Any], cycle_id: str) -> list[str]:
    reasons: list[str] = []
    version = event.get("format_version", 0)
    if (
        isinstance(version, bool)
        or not isinstance(version, int)
        or version not in {0, 1}
    ):
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
