"""Historical-boundary proof for transition-plan replay and recovery."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .event_batch_validation import validate_event_batch
from .storage import jsonl_path
from .transition_plan_contract import regular_payload, sha256_bytes


def event_payload(events: list[dict[str, Any]]) -> bytes:
    return b"".join(
        json.dumps(event, ensure_ascii=False, sort_keys=True).encode("utf-8") + b"\n"
        for event in events
    )


def matching_events(
    existing: list[dict[str, Any]], plan: dict[str, Any]
) -> tuple[bool, bool]:
    tagged = [
        event
        for event in existing
        if event.get("transition_plan_id") == plan.get("plan_id")
    ]
    if not tagged:
        return False, False
    return tagged == plan["events"], tagged != plan["events"]


def committed_boundary_valid(
    root: Path,
    plan: dict[str, Any],
    existing: list[dict[str, Any]],
) -> bool:
    tagged_indexes = [
        index
        for index, event in enumerate(existing)
        if event.get("transition_plan_id") == plan["plan_id"]
    ]
    if len(tagged_indexes) != len(plan["events"]):
        return False
    start = tagged_indexes[0]
    if tagged_indexes != list(range(start, start + len(plan["events"]))):
        return False
    if existing[start : start + len(plan["events"])] != plan["events"]:
        return False
    ledger = regular_payload(jsonl_path(root), missing=b"")
    before_size = plan["ledger"]["before_size"]
    prefix = ledger[:before_size]
    if sha256_bytes(prefix) != plan["ledger"]["before_sha256"]:
        return False
    separator = b"\n" if prefix and not prefix.endswith(b"\n") else b""
    planned_payload = separator + event_payload(plan["events"])
    boundary = before_size + len(planned_payload)
    if ledger[before_size:boundary] != planned_payload:
        return False
    suffix_events = existing[start + len(plan["events"]) :]
    if ledger[boundary:] != event_payload(suffix_events):
        return False
    try:
        validate_event_batch(
            [*existing[:start], *plan["events"]],
            suffix_events,
            source=jsonl_path(root),
        )
    except ValueError:
        return False
    return True
