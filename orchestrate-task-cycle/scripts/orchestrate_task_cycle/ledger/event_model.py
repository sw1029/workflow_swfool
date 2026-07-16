from __future__ import annotations

import datetime as dt
import hashlib
import json
import uuid
from typing import Any

from .constants import (
    CANONICAL_STEPS,
    LEDGER_FORMAT_VERSION,
    MIN_FIELDS,
    STAGE_STATUS_NORMALIZATION,
    SUPPORTED_LEDGER_FORMAT_VERSIONS,
)
from .support import normalize_list, validate_cycle_id, validate_event_id


def normalize_stage_status(value: Any) -> str:
    if value is None or not str(value).strip():
        raise ValueError("stage event requires an explicit non-empty `status`")
    raw = str(value).strip().lower()
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
    return dt.datetime.now().astimezone().isoformat(timespec="microseconds")


def default_cycle_id() -> str:
    stamp = dt.datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    return f"cycle-{stamp}-{uuid.uuid4().hex}"


def make_event_id(cycle_id: str, step: str, created_at: str, event: dict[str, Any]) -> str:
    del event
    stamp = created_at.replace(":", "").replace("-", "").split("+")[0]
    return f"{cycle_id}-{step}-{stamp}-{uuid.uuid4().hex}"


def request_fingerprint(cycle_id: str, event: dict[str, Any]) -> str:
    normalized = dict(event)
    normalized["cycle_id"] = cycle_id
    normalized["step"] = str(normalized.get("step") or "").strip()
    normalized["status"] = normalize_stage_status(normalized.get("status"))
    for field in ("changed_files", "artifacts", "blockers"):
        if field in normalized:
            normalized[field] = normalize_list(normalized.get(field))
    for field in (
        "format_version",
        "created_at",
        "artifact_refs",
        "unchanged_refs",
        "request_fingerprint",
        "source_status",
    ):
        normalized.pop(field, None)
    canonical = json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def complete_event(cycle_id: str, event: dict[str, Any]) -> dict[str, Any]:
    event = dict(event)
    cycle_id = validate_cycle_id(cycle_id)
    claimed_cycle_id = event.get("cycle_id")
    if claimed_cycle_id is not None and str(claimed_cycle_id) != cycle_id:
        raise ValueError(f"stage event cycle_id `{claimed_cycle_id}` does not match ledger cycle `{cycle_id}`")
    supplied_version = event.get("format_version")
    if supplied_version is not None and (
        isinstance(supplied_version, bool)
        or not isinstance(supplied_version, int)
        or supplied_version not in (0, LEDGER_FORMAT_VERSION)
    ):
        raise ValueError(f"unsupported ledger format_version: {supplied_version}")
    created_at = str(event.get("created_at") or now_iso())
    step = str(event.get("step") or "unknown")
    raw_status = event.get("status")
    event["format_version"] = LEDGER_FORMAT_VERSION
    event["cycle_id"] = cycle_id
    event["created_at"] = created_at
    if event.get("event_id") is None:
        event["event_id"] = validate_event_id(make_event_id(cycle_id, step, created_at, event))
    else:
        event["event_id"] = validate_event_id(event.get("event_id"))
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


def validate_event_envelope(
    cycle_id: str,
    event: dict[str, Any],
    allow_noncanonical_step: bool,
) -> dict[str, Any]:
    event = dict(event)
    cycle_id = validate_cycle_id(cycle_id)
    claimed_cycle_id = event.get("cycle_id")
    if claimed_cycle_id is not None and str(claimed_cycle_id) != cycle_id:
        raise ValueError(f"stage event cycle_id `{claimed_cycle_id}` does not match ledger cycle `{cycle_id}`")
    supplied_version = event.get("format_version")
    if supplied_version is not None and (
        isinstance(supplied_version, bool)
        or not isinstance(supplied_version, int)
        or supplied_version not in (0, LEDGER_FORMAT_VERSION)
    ):
        raise ValueError(f"unsupported ledger format_version: {supplied_version}")
    raw_status = event.get("status")
    event["status"] = normalize_stage_status(raw_status)
    if event["status"] != str(raw_status).strip().lower():
        event.setdefault("source_status", str(raw_status).strip().lower())
    raw_step = event.get("step")
    step = str(raw_step).strip() if raw_step is not None else ""
    if not step:
        raise ValueError("stage event requires a non-empty `step`")
    event["step"] = step
    if step not in CANONICAL_STEPS:
        if not allow_noncanonical_step:
            raise ValueError(f"noncanonical stage step `{step}` requires --allow-noncanonical-step")
        event["noncanonical_step"] = True
    if event.get("event_id") is not None:
        event["event_id"] = validate_event_id(event.get("event_id"))
    return event


def validate_stored_event(value: Any, cycle_id: str, line_no: int) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"ledger line {line_no} must contain a JSON object")
    version = value.get("format_version", 0)
    if isinstance(version, bool) or not isinstance(version, int) or version not in SUPPORTED_LEDGER_FORMAT_VERSIONS:
        raise ValueError(f"unsupported ledger format_version {version!r} on line {line_no}")
    if str(value.get("cycle_id") or "") != cycle_id:
        raise ValueError(f"ledger line {line_no} cycle_id does not match directory cycle `{cycle_id}`")
    if not str(value.get("step") or "").strip():
        raise ValueError(f"ledger line {line_no} lacks a non-empty step")
    if not str(value.get("status") or "").strip():
        raise ValueError(f"ledger line {line_no} lacks a non-empty status")
    validate_event_id(value.get("event_id"))
    return value
