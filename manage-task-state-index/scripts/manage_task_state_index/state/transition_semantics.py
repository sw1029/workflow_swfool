"""Reconstruct and validate immutable transition-plan derived semantics."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .event_batch_validation import validate_event_batch
from .events import merge_state, validate_event, versioned_event
from ..migration.api import load_sealed_events_if_present
from .render import _generated_at_from_markdown, _render_markdown_payload
from .transition_plan_contract import (
    canonical_bytes,
    regular_payload,
    sha256_bytes,
    workspace_path,
)
from .transition_recovery import event_payload


def _prefix_events(
    root: Path, payload: bytes, plan: dict[str, Any]
) -> list[dict[str, Any]]:
    sealed = load_sealed_events_if_present(root)
    if sealed is not None:
        count = plan["ledger"]["before_event_count"]
        events = sealed[0][:count]
    else:
        events = _parse_prefix_events(root, payload)
    if (
        len(events) != plan["ledger"]["before_event_count"]
        or sha256_bytes(canonical_bytes(events))
        != plan["ledger"]["before_events_sha256"]
    ):
        raise ValueError("Task-state transition normalized prestate mismatch")
    return events


def _parse_prefix_events(root: Path, payload: bytes) -> list[dict[str, Any]]:
    source = workspace_path(root, ".task/index.jsonl")
    events: list[dict[str, Any]] = []
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("Task-state transition historical prefix is not UTF-8") from exc
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            raw = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(
                "Task-state transition historical prefix is malformed"
            ) from exc
        events.append(validate_event(raw, line_number, source))
    return events


def _validate_links(
    existing: list[dict[str, Any]], planned: list[dict[str, Any]]
) -> None:
    known_ids = set(merge_state([*existing, *planned]))
    for event in planned:
        if event.get("id") not in known_ids:
            raise ValueError("Task-state transition event has an unknown source ID")
        for link in event.get("links") or []:
            if link.get("id") not in known_ids:
                raise ValueError("Task-state transition event has an unknown link target")


def _materialize_request_events(
    existing: list[dict[str, Any]], plan: dict[str, Any]
) -> list[dict[str, Any]]:
    materialized: list[dict[str, Any]] = []
    projected = list(existing)
    for raw in plan["request"]["events"]:
        event = dict(raw)
        complete_upsert = event.get("event") == "upsert" and all(
            isinstance(event.get(field), str) and event.get(field)
            for field in ("type", "status", "path")
        )
        if event.get("event") == "upsert" and not complete_upsert:
            prior = merge_state(projected).get(str(event.get("id")))
            if not isinstance(prior, dict):
                raise ValueError(
                    "Sparse transition request references an unknown ID"
                )
            for field in (
                "type", "status", "path", "title", "parent_id",
                "content_sha256", "note",
            ):
                if field not in event and prior.get(field) is not None:
                    event[field] = prior[field]
        event.setdefault("updated_at", plan["created_at"])
        if event["updated_at"] != plan["created_at"]:
            raise ValueError("Transition request event timestamp binding mismatch")
        event["transition_plan_id"] = plan["plan_id"]
        normalized = versioned_event(event)
        materialized.append(normalized)
        projected.append(normalized)
    return materialized


def _validate_markdown_when_at_prestate(
    root: Path,
    plan: dict[str, Any],
    ledger: bytes,
    existing: list[dict[str, Any]],
) -> None:
    if sha256_bytes(ledger) != plan["ledger"]["before_sha256"]:
        return
    markdown = regular_payload(
        workspace_path(root, ".task/index.md"), missing=b""
    )
    markdown_digest = sha256_bytes(markdown) if markdown else None
    if markdown_digest != plan["markdown"]["before_sha256"]:
        return
    state = merge_state([*existing, *plan["events"]])
    prior_generated = _generated_at_from_markdown(markdown)
    if prior_generated:
        candidate = _render_markdown_payload(state, prior_generated)
        expected = (
            candidate
            if candidate == markdown
            else _render_markdown_payload(state, plan["created_at"])
        )
    else:
        expected = _render_markdown_payload(state, plan["created_at"])
    if sha256_bytes(expected) != plan["markdown"]["after_sha256"]:
        raise ValueError("Task-state transition Markdown derivation mismatch")


def validate_transition_plan_semantics(root: Path, plan: dict[str, Any]) -> None:
    """Prove plan events and derived ledger bindings from the historical prefix."""

    root = root.resolve()
    ledger = regular_payload(
        workspace_path(root, ".task/index.jsonl"), missing=b""
    )
    before_size = plan["ledger"]["before_size"]
    if len(ledger) < before_size:
        raise ValueError("Task-state transition historical prefix is truncated")
    prefix = ledger[:before_size]
    if sha256_bytes(prefix) != plan["ledger"]["before_sha256"]:
        raise ValueError(
            "Task-state transition committed boundary historical prefix digest mismatch"
        )
    existing = _prefix_events(root, prefix, plan)
    request_events = _materialize_request_events(existing, plan)
    if request_events != plan["events"]:
        raise ValueError("Task-state transition request/event derivation mismatch")
    planned = validate_event_batch(
        existing, plan["events"], source=workspace_path(root, ".task/index.jsonl")
    )
    if planned != plan["events"]:
        raise ValueError("Task-state transition event normalization mismatch")
    _validate_links(existing, planned)
    separator = b"\n" if prefix and not prefix.endswith(b"\n") else b""
    derived = prefix + separator + event_payload(planned)
    if (
        len(prefix) != before_size
        or sha256_bytes(derived) != plan["ledger"]["after_sha256"]
    ):
        raise ValueError("Task-state transition ledger derivation mismatch")
    _validate_markdown_when_at_prestate(root, plan, ledger, existing)


__all__ = ["validate_transition_plan_semantics"]
