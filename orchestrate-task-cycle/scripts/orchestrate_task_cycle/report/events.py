from __future__ import annotations

from typing import Any

from .constants import STAGE_ORDER
from .io import deep_get


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


def long_run_events(
    context: dict[str, Any], stage: dict[str, Any]
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for event in all_events(context, stage):
        event_kind = str(event.get("event_kind") or "").lower()
        role = str(event.get("long_run_role") or "").lower()
        if (
            event.get("long_run_branch")
            or event_kind.startswith("long_run_")
            or role in {"launch", "monitor", "harvest", "finalize"}
        ):
            result.append(event)
    return result


def long_run_status_lines(context: dict[str, Any], stage: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    for event in long_run_events(context, stage)[-10:]:
        status = (
            event.get("execution_status")
            or event.get("source_status")
            or event.get("status")
            or "unknown"
        )
        run_id = event.get("run_id") or "unknown-run"
        role = event.get("long_run_role") or event.get("event_kind") or "long_run"
        remaining = event.get("remaining_validation") or "not_recorded"
        lines.append(f"{run_id}: {status} ({role}); remaining_validation={remaining}")
    return lines


def event_value(
    stage: dict[str, Any], field: str, preferred_steps: tuple[str, ...] = ()
) -> Any:
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
