from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from .artifact_evidence import annotate_artifact_refs
from .constants import CURRENT_STAGE_PROJECTION_VERSION
from .current_projection import (
    build_current_projection,
    expand_current_projection,
    load_cycle_current_file,
    stage_compiler_protocol_version,
)
from .event_model import (
    complete_event,
    request_fingerprint,
    validate_event_envelope,
    validate_stored_event,
)
from .support import (
    atomic_write_text,
    current_stage_path,
    cycle_dir,
    durable_append_json,
    initialization_path,
    ledger_lock,
    ledger_path,
    read_initialization_metadata,
    rel_path,
    validate_cycle_id,
)
from .terminal import (
    compact_terminal_observation,
    terminal_latch_state,
    verify_terminal_reopen_receipt,
)


AtomicTextWriter = Callable[[Path, str], None]
JsonAppender = Callable[[Path, dict[str, Any]], None]


def read_events_unlocked(root: Path, cycle_id: str) -> list[dict[str, Any]]:
    path = ledger_path(root, cycle_id)
    if not path.is_file():
        return []
    events: list[dict[str, Any]] = []
    seen_event_ids: set[str] = set()
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line_no, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"malformed ledger JSON on line {line_no}: {exc}") from exc
            event = validate_stored_event(value, cycle_id, line_no)
            event_id = str(event["event_id"])
            if event_id in seen_event_ids:
                raise ValueError(f"duplicate ledger event_id `{event_id}` on line {line_no}")
            seen_event_ids.add(event_id)
            events.append(event)
    return events


def read_events(root: Path, cycle_id: str) -> list[dict[str, Any]]:
    cycle_id = validate_cycle_id(cycle_id)
    path = ledger_path(root, cycle_id)
    if not path.is_file():
        return []
    with ledger_lock(root, cycle_id, exclusive=False):
        return read_events_unlocked(root, cycle_id)


def read_all_cycle_events(root: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    cycle_root = root / ".task" / "cycle"
    if not cycle_root.is_dir():
        return events
    for path in sorted(cycle_root.glob("*/stage.jsonl")):
        events.extend(read_events(root, path.parent.name))
    return sorted(
        events,
        key=lambda event: (
            str(event.get("created_at") or ""),
            str(event.get("cycle_id") or ""),
            int(event.get("ledger_sequence") or 0),
        ),
    )


def write_current_unlocked(
    root: Path,
    cycle_id: str,
    events: list[dict[str, Any]],
    *,
    protocol_version: int = 1,
    atomic_writer: AtomicTextWriter = atomic_write_text,
) -> dict[str, Any]:
    current = build_current_projection(
        cycle_id,
        events,
        protocol_version=protocol_version,
    )
    path = current_stage_path(root, cycle_id)
    atomic_writer(path, json.dumps(current, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    return current


def write_current(
    root: Path,
    cycle_id: str,
    events: list[dict[str, Any]] | None = None,
    *,
    atomic_writer: AtomicTextWriter = atomic_write_text,
) -> dict[str, Any]:
    cycle_id = validate_cycle_id(cycle_id)
    with ledger_lock(root, cycle_id, exclusive=True):
        stored_events = read_events_unlocked(root, cycle_id)
        effective_events = stored_events if ledger_path(root, cycle_id).is_file() else list(events or [])
        metadata = (
            read_initialization_metadata(root, cycle_id)
            if initialization_path(root, cycle_id).is_file()
            else None
        )
        return write_current_unlocked(
            root,
            cycle_id,
            effective_events,
            protocol_version=stage_compiler_protocol_version(metadata),
            atomic_writer=atomic_writer,
        )


def read_current_expanded(root: Path, cycle_id: str) -> dict[str, Any]:
    """Read current_stage.json and hydrate protocol-v2 event refs from stage.jsonl.

    Legacy snapshots are returned unchanged.  A v2 snapshot is accepted only when
    it exactly projects the ledger while the shared ledger lock is held.
    """

    cycle_id = validate_cycle_id(cycle_id)
    with ledger_lock(root, cycle_id, exclusive=False):
        current = load_cycle_current_file(root, cycle_id)
        if not current:
            return {}
        events = read_events_unlocked(root, cycle_id)
        metadata = (
            read_initialization_metadata(root, cycle_id)
            if initialization_path(root, cycle_id).is_file()
            else None
        )
        protocol_version = stage_compiler_protocol_version(metadata)
        projection_version = current.get("projection_version", 1)
        expected_projection_version = (
            CURRENT_STAGE_PROJECTION_VERSION if protocol_version == 2 else 1
        )
        if projection_version != expected_projection_version:
            raise ValueError(
                "current_stage projection does not match the initialized compiler protocol"
            )
        return expand_current_projection(current, events, cycle_id=cycle_id)


def duplicate_event(
    previous_events: list[dict[str, Any]],
    event: dict[str, Any],
    fingerprint: str,
) -> dict[str, Any] | None:
    event_id = event.get("event_id")
    if event_id is None:
        return None
    existing = next((row for row in previous_events if row.get("event_id") == event_id), None)
    if existing is None:
        return None
    existing_fingerprint = existing.get("request_fingerprint")
    if existing_fingerprint == fingerprint:
        return existing
    if existing_fingerprint is None:
        comparable = dict(event)
        for key in ("format_version", "created_at", "artifact_refs", "unchanged_refs"):
            comparable.pop(key, None)
        if all(existing.get(key) == value for key, value in comparable.items()):
            return existing
    raise ValueError(f"event_id `{event_id}` already exists with different content")


def _validate_first_context(
    initialization: dict[str, Any],
    previous_events: list[dict[str, Any]],
    event: dict[str, Any],
) -> None:
    step = str(event.get("step") or "").strip()
    if previous_events:
        if str(previous_events[0].get("step") or "") != "context":
            raise ValueError("cycle ledger is invalid: first canonical stage event is not `context`")
        return
    if step != "context":
        raise ValueError("the first canonical stage event must be `context`")
    initialized_task_id = initialization.get("task_id")
    context_task_id = event.get("task_id")
    allow_missing_task = initialization.get("allow_missing_task_for_bootstrap") is True
    if initialized_task_id is not None:
        if str(context_task_id or "").strip() != str(initialized_task_id):
            raise ValueError("context task_id must match initialization task_id")
    elif not allow_missing_task:
        raise ValueError("missing initialization task_id is allowed only for an explicit bootstrap transaction")
    elif context_task_id is not None and str(context_task_id).strip():
        raise ValueError("task-absent bootstrap context must not invent a task_id")
    elif not (
        event.get("task_absent") is True
        or event.get("task_md_exists") is False
        or (isinstance(event.get("task_md"), dict) and event["task_md"].get("exists") is False)
    ):
        raise ValueError("bootstrap context must explicitly record task.md absence")


def _verified_terminal_latch(
    root: Path,
    previous_events: list[dict[str, Any]],
    event: dict[str, Any],
) -> dict[str, Any]:
    latch = terminal_latch_state(previous_events, event)
    if latch.get("terminal_latch_status") == "reopen_incomplete":
        raise ValueError("terminal reopen requires one atomic seal/registry/pack/index lifecycle transition receipt")
    if latch.get("terminal_latch_status") == "reopened":
        verified, receipt_errors = verify_terminal_reopen_receipt(root, event.get("lifecycle_transition_result"))
        if not verified:
            raise ValueError("terminal reopen receipt failed content verification: " + ", ".join(receipt_errors))
    return latch


def append_event(
    root: Path,
    cycle_id: str,
    event: dict[str, Any],
    allow_noncanonical_step: bool = False,
    *,
    atomic_writer: AtomicTextWriter = atomic_write_text,
    json_appender: JsonAppender = durable_append_json,
) -> dict[str, Any]:
    cycle_id = validate_cycle_id(cycle_id)
    event = validate_event_envelope(cycle_id, event, allow_noncanonical_step)
    fingerprint = request_fingerprint(cycle_id, event)
    path = ledger_path(root, cycle_id)
    with ledger_lock(root, cycle_id, exclusive=True):
        initialization = read_initialization_metadata(root, cycle_id)
        previous_events = read_events_unlocked(root, cycle_id)
        _validate_first_context(initialization, previous_events, event)
        (cycle_dir(root, cycle_id) / "packets").mkdir(parents=True, exist_ok=True)
        duplicate = duplicate_event(previous_events, event, fingerprint)
        if duplicate is not None:
            current = write_current_unlocked(
                root,
                cycle_id,
                previous_events,
                protocol_version=stage_compiler_protocol_version(initialization),
                atomic_writer=atomic_writer,
            )
            return {
                "event": duplicate,
                "event_duplicate": True,
                "current_stage": current,
                "ledger_path": rel_path(root, path),
                "current_stage_path": rel_path(root, current_stage_path(root, cycle_id)),
            }

        latch = _verified_terminal_latch(root, previous_events, event)
        full_event_suppressed = bool(latch.get("suppress_full_cycle"))
        event_to_write = compact_terminal_observation(event, latch) if full_event_suppressed else {**event, **latch}
        event_to_write["request_fingerprint"] = fingerprint
        event_to_write["ledger_sequence"] = len(previous_events) + 1
        completed = complete_event(cycle_id, event_to_write)
        annotate_artifact_refs(root, completed, previous_events)
        json_appender(path, completed)
        current = write_current_unlocked(
            root,
            cycle_id,
            previous_events + [completed],
            protocol_version=stage_compiler_protocol_version(initialization),
            atomic_writer=atomic_writer,
        )
        return {
            "event": completed,
            "event_suppressed": full_event_suppressed,
            "observation_appended": full_event_suppressed,
            "current_stage": current,
            "ledger_path": rel_path(root, path),
            "current_stage_path": rel_path(root, current_stage_path(root, cycle_id)),
        }
