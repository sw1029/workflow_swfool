from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from .constants import ORDER, STEP_ALIASES, TERMINAL_OK


def add(
    findings: list[dict[str, Any]],
    severity: str,
    code: str,
    message: str,
    evidence: Any = None,
) -> None:
    item: dict[str, Any] = {
        "severity": severity,
        "code": code,
        "message": message,
    }
    if evidence is not None:
        item["evidence"] = evidence
    findings.append(item)


def load_json_arg(value: str | None) -> dict[str, Any]:
    if not value or value == "-":
        raw = sys.stdin.read()
        return json.loads(raw) if raw.strip() else {}
    path = Path(value)
    stripped = value.strip()
    if stripped.startswith("{") or stripped.startswith("["):
        return json.loads(stripped)
    try:
        if path.exists():
            raw = path.read_text(encoding="utf-8")
            return json.loads(raw) if raw.strip() else {}
    except OSError:
        pass
    return json.loads(stripped)


def deep_get(data: Any, *keys: str) -> Any:
    current = data
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def flatten_values(data: Any) -> list[Any]:
    values: list[Any] = []
    if isinstance(data, dict):
        for value in data.values():
            values.extend(flatten_values(value))
    elif isinstance(data, list):
        for value in data:
            values.extend(flatten_values(value))
    else:
        values.append(data)
    return values


def text_blob(*items: Any) -> str:
    values: list[str] = []
    for item in items:
        for value in flatten_values(item):
            if isinstance(value, (str, int, float, bool)):
                values.append(str(value))
    return "\n".join(values).lower()


def stage_event_candidates(stage: dict[str, Any]) -> list[dict[str, Any]]:
    """Return top-level and nested events in deterministic ledger order."""
    candidates: list[dict[str, Any]] = []
    seen: set[int] = set()

    def add_candidate(value: Any) -> None:
        if isinstance(value, dict) and id(value) not in seen:
            candidates.append(value)
            seen.add(id(value))

    add_candidate(stage)
    add_candidate(stage.get("latest_event"))
    steps = stage.get("steps")
    if isinstance(steps, dict):
        for step in ORDER:
            add_candidate(steps.get(step))
        for name in sorted(set(steps) - set(ORDER)):
            add_candidate(steps.get(name))
    events = stage.get("events")
    if isinstance(events, list):
        for event in events:
            add_candidate(event)
    return candidates


def normalized_path_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    paths: list[str] = []
    for item in value:
        if isinstance(item, dict) and item.get("path"):
            paths.append(str(item["path"]))
        elif item is not None and str(item).strip():
            paths.append(str(item))
    return paths


def extend_unique(items: list[str], values: list[str]) -> None:
    seen = set(items)
    for value in values:
        if value not in seen:
            items.append(value)
            seen.add(value)


def status_for_step(stage: dict[str, Any], step: str) -> str | None:
    names = [step, *STEP_ALIASES.get(step, [])]
    steps = stage.get("steps")
    if isinstance(steps, dict):
        value = next((steps[name] for name in names if name in steps), None)
        if isinstance(value, dict):
            raw = value.get("status") or value.get("verdict") or value.get("result")
        else:
            raw = value
        return str(raw).lower() if raw is not None else None
    events = stage.get("events")
    if isinstance(events, list):
        found = None
        for event in events:
            if isinstance(event, dict) and event.get("step") in names:
                found = (
                    event.get("status") or event.get("verdict") or event.get("result")
                )
        return str(found).lower() if found is not None else None
    return None


def completed(stage: dict[str, Any], step: str) -> bool:
    status = status_for_step(stage, step)
    return bool(status and status in TERMINAL_OK)


def step_event(stage: dict[str, Any], step: str) -> dict[str, Any]:
    names = [step, *STEP_ALIASES.get(step, [])]
    steps = stage.get("steps")
    if isinstance(steps, dict):
        for name in names:
            value = steps.get(name)
            if isinstance(value, dict):
                return value
    events = stage.get("events")
    if isinstance(events, list):
        found: dict[str, Any] = {}
        for event in events:
            if isinstance(event, dict) and event.get("step") in names:
                found = event
        return found
    return {}


def list_value(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if item is not None and str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value]
    return []


def first_value(stage: dict[str, Any], *paths: str) -> Any:
    for candidate in stage_event_candidates(stage):
        for path in paths:
            value = (
                deep_get(candidate, *path.split("."))
                if "." in path
                else candidate.get(path)
            )
            if value is not None:
                return value
    return None


def truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in {"true", "yes", "1", "required", "block", "blocked"}
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, (list, dict)):
        return bool(value)
    return False


def number_value(value: Any) -> int | None:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def dict_list(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        return [value]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    return []
