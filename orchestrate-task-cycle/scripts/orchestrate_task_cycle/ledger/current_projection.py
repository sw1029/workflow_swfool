from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .constants import (
    CANONICAL_STEPS,
    CURRENT_STAGE_PROJECTION_VERSION,
    LEDGER_FORMAT_VERSION,
    STAGE_COMPILER_PROTOCOL_VERSION,
    SUPPORTED_STAGE_COMPILER_PROTOCOL_VERSIONS,
)
from .event_model import now_iso
from .support import canonical_sha256, current_stage_path


EVENT_REF_KIND = "cycle_ledger_event_ref"
CURRENT_STAGE_KIND = "cycle_current_stage_projection"

# These scalar fields make the stored projection useful for cheap status reads.  Any
# structured result body remains authoritative only in stage.jsonl and is recovered
# by expand_current_projection/read_current_expanded.
_EVENT_REF_SCALARS = (
    "task_id",
    "completed_task_id",
    "next_task_id",
    "validation_verdict",
    "progress_verdict",
    "preparation_id",
    "preparation_binding_sha256",
    "result_artifact_ref",
    "result_artifact_sha256",
    "result_artifact_raw_sha256",
    "terminal_latch_status",
    "terminal_justified",
)
_MAX_PROJECTED_STRING_BYTES = 4096


def stage_compiler_protocol_version(metadata: dict[str, Any] | None) -> int:
    raw = (metadata or {}).get("stage_compiler_protocol_version", 1)
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise ValueError("stage_compiler_protocol_version must be an integer")
    if raw not in SUPPORTED_STAGE_COMPILER_PROTOCOL_VERSIONS:
        raise ValueError(f"unsupported stage_compiler_protocol_version: {raw}")
    return raw


def _bounded_scalar(value: Any) -> bool:
    if value is None or isinstance(value, (bool, int, float)):
        return True
    if not isinstance(value, str):
        return False
    return len(value.encode("utf-8")) <= _MAX_PROJECTED_STRING_BYTES


def event_ref(event: dict[str, Any], sequence: int) -> dict[str, Any]:
    ref: dict[str, Any] = {
        "kind": EVENT_REF_KIND,
        "event_id": event.get("event_id"),
        "ledger_sequence": sequence,
        "event_sha256": canonical_sha256(event),
        "step": event.get("step"),
        "status": event.get("status"),
    }
    for field in _EVENT_REF_SCALARS:
        if field in event and _bounded_scalar(event[field]):
            ref[field] = event[field]
    return ref


def _current_status(
    latest_by_step: dict[str, dict[str, Any]],
    latest: dict[str, Any],
) -> str:
    if any(
        str(event.get("status")).lower() in {"blocked", "failed"}
        for event in latest_by_step.values()
    ):
        return "blocked"
    return str(latest.get("status") or "unknown") if latest else "empty"


def build_current_projection(
    cycle_id: str,
    events: list[dict[str, Any]],
    *,
    protocol_version: int,
    updated_at: str | None = None,
) -> dict[str, Any]:
    if protocol_version not in SUPPORTED_STAGE_COMPILER_PROTOCOL_VERSIONS:
        raise ValueError(
            f"unsupported stage_compiler_protocol_version: {protocol_version}"
        )
    latest_by_step: dict[str, dict[str, Any]] = {}
    malformed_events: list[dict[str, Any]] = []
    event_positions: dict[str, int] = {}
    for sequence, event in enumerate(events, start=1):
        event_id = str(event.get("event_id") or "")
        if protocol_version == STAGE_COMPILER_PROTOCOL_VERSION:
            if not event_id or event_id in event_positions:
                raise ValueError(
                    "protocol-v2 current-stage projection requires unique event IDs"
                )
            if event.get("ledger_sequence") != sequence:
                raise ValueError(
                    "protocol-v2 current-stage projection requires contiguous ledger_sequence values"
                )
        event_positions[event_id] = sequence
        step = str(event.get("step") or "unknown")
        if step in CANONICAL_STEPS:
            latest_by_step[step] = event
        else:
            malformed_events.append(event)
    latest = events[-1] if events else {}
    current: dict[str, Any] = {
        "format_version": LEDGER_FORMAT_VERSION,
        "cycle_id": cycle_id,
        "updated_at": updated_at or now_iso(),
        "status": _current_status(latest_by_step, latest),
        "latest_event": latest,
        "steps": {step: latest_by_step[step] for step in sorted(latest_by_step)},
        "malformed_event_count": len(malformed_events),
        "malformed_events": malformed_events[-10:],
        "event_count": len(events),
    }
    if protocol_version == 1:
        return current

    def reference(event: dict[str, Any]) -> dict[str, Any]:
        sequence = event_positions.get(str(event.get("event_id") or ""))
        if sequence is None:
            raise ValueError("current-stage event is missing from the ledger sequence")
        return event_ref(event, sequence)

    current.update(
        {
            "kind": CURRENT_STAGE_KIND,
            "projection_version": CURRENT_STAGE_PROJECTION_VERSION,
            "stage_compiler_protocol_version": STAGE_COMPILER_PROTOCOL_VERSION,
            "latest_event": reference(latest) if latest else {},
            "steps": {
                step: reference(latest_by_step[step])
                for step in sorted(latest_by_step)
            },
            "malformed_events": [reference(event) for event in malformed_events[-10:]],
        }
    )
    return current


def _projection_version(current: dict[str, Any]) -> int:
    raw = current.get("projection_version", 1)
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise ValueError("current_stage projection_version must be an integer")
    if raw not in {1, CURRENT_STAGE_PROJECTION_VERSION}:
        raise ValueError(f"unsupported current_stage projection_version: {raw}")
    return raw


def expand_current_projection(
    current: dict[str, Any],
    events: list[dict[str, Any]],
    *,
    cycle_id: str,
) -> dict[str, Any]:
    if _projection_version(current) == 1:
        return current
    if current.get("kind") != CURRENT_STAGE_KIND:
        raise ValueError("protocol-v2 current_stage has an invalid kind")
    if current.get("stage_compiler_protocol_version") != STAGE_COMPILER_PROTOCOL_VERSION:
        raise ValueError("protocol-v2 current_stage has an invalid compiler protocol")
    if str(current.get("cycle_id") or "") != cycle_id:
        raise ValueError("current_stage cycle_id does not match its cycle directory")

    expected = build_current_projection(
        cycle_id,
        events,
        protocol_version=STAGE_COMPILER_PROTOCOL_VERSION,
        updated_at=str(current.get("updated_at") or ""),
    )
    if current != expected:
        raise ValueError("protocol-v2 current_stage does not match the authoritative ledger")

    expanded = dict(current)
    expanded["latest_event"] = events[-1] if events else {}
    latest_by_step = {
        str(event.get("step") or "unknown"): event
        for event in events
        if str(event.get("step") or "unknown") in CANONICAL_STEPS
    }
    expanded["steps"] = {
        step: latest_by_step[step] for step in sorted(latest_by_step)
    }
    malformed = [
        event
        for event in events
        if str(event.get("step") or "unknown") not in CANONICAL_STEPS
    ]
    expanded["malformed_events"] = malformed[-10:]
    return expanded


def load_current_file(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"malformed current_stage JSON: {path}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"current_stage must contain a JSON object: {path}")
    return value


def load_cycle_current_file(root: Path, cycle_id: str) -> dict[str, Any]:
    return load_current_file(current_stage_path(root, cycle_id))


__all__ = [
    "CURRENT_STAGE_KIND",
    "EVENT_REF_KIND",
    "build_current_projection",
    "event_ref",
    "expand_current_projection",
    "load_current_file",
    "load_cycle_current_file",
    "stage_compiler_protocol_version",
]
