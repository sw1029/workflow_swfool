from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from .constants import (
    LEDGER_FORMAT_VERSION,
    STAGE_COMPILER_PROTOCOL_VERSION,
    STAGE_PREPARATION_SCHEMA_VERSION,
)
from .current_projection import stage_compiler_protocol_version as _protocol_version
from .event_model import default_cycle_id, now_iso
from .repository import AtomicTextWriter, read_all_cycle_events, read_events_unlocked, write_current_unlocked
from .support import (
    atomic_write_text,
    current_stage_path,
    cycle_dir,
    initialization_path,
    ledger_lock,
    ledger_path,
    rel_path,
    validate_cycle_id,
)
from .terminal import terminal_latch_state, verify_terminal_reopen_receipt


EventAppender = Callable[[Path, str, dict[str, Any], bool], dict[str, Any]]


def cli_init_protocol(
    root: Path,
    cycle_id: str | None,
    requested: int | None,
) -> int | None:
    """Default new CLI cycles to v2 without migrating initialized cycles."""

    if requested is not None:
        return requested
    if cycle_id is None:
        return STAGE_COMPILER_PROTOCOL_VERSION
    return (
        None
        if initialization_path(root, cycle_id).is_file()
        else STAGE_COMPILER_PROTOCOL_VERSION
    )


def _validate_terminal_state(
    root: Path,
    terminal_state: dict[str, Any],
) -> dict[str, Any]:
    latch = terminal_latch_state(read_all_cycle_events(root), terminal_state)
    if latch.get("terminal_latch_status") == "not_evaluated":
        missing = ", ".join(str(field) for field in latch.get("terminal_latch_missing_fields") or [])
        raise ValueError(f"terminal latch contract is not evaluated; missing or invalid fields: {missing}")
    if latch.get("terminal_latch_status") == "reopen_incomplete":
        raise ValueError("terminal reopen requires one atomic seal/registry/pack/index lifecycle transition receipt")
    if latch.get("terminal_latch_status") == "reopened":
        verified, receipt_errors = verify_terminal_reopen_receipt(
            root, terminal_state.get("lifecycle_transition_result")
        )
        if not verified:
            raise ValueError("terminal reopen receipt failed content verification: " + ", ".join(receipt_errors))
    return latch


def _terminal_observation(
    root: Path,
    terminal_state: dict[str, Any],
    latch: dict[str, Any],
    append_event: EventAppender,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    if not latch.get("suppress_full_cycle") and latch.get("terminal_latch_status") != "reopened":
        return None, None
    source_cycle_id = validate_cycle_id(str(latch.get("terminal_latch_source_cycle_id") or ""))
    observation = dict(terminal_state)
    observation.pop("cycle_id", None)
    observation.setdefault("step", "report")
    observation.setdefault("status", "complete")
    if latch.get("suppress_full_cycle"):
        result = append_event(root, source_cycle_id, observation, False)
        return {
            "cycle_suppressed": True,
            "reason": "quiescent_terminal_latched",
            **latch,
            "observation_cycle_id": source_cycle_id,
            "observation_result": result,
        }, None
    observation.setdefault("event_kind", "terminal_reopen_receipt")
    return None, append_event(root, source_cycle_id, observation, False)


def _load_existing_metadata(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"malformed cycle initialization metadata: {path}") from exc
    return loaded if isinstance(loaded, dict) else None


def init_cycle(
    root: Path,
    cycle_id: str | None,
    task_id: str | None,
    reason: str,
    terminal_state: dict[str, Any] | None = None,
    allow_missing_task_for_bootstrap: bool = False,
    stage_compiler_protocol_version: int | None = None,
    stage_preparation_schema_version: int | None = None,
    *,
    atomic_writer: AtomicTextWriter = atomic_write_text,
    append_event: EventAppender,
) -> dict[str, Any]:
    terminal_reopen_result: dict[str, Any] | None = None
    if terminal_state:
        latch = _validate_terminal_state(root, terminal_state)
        suppressed, terminal_reopen_result = _terminal_observation(root, terminal_state, latch, append_event)
        if suppressed is not None:
            return suppressed
    cycle_id = validate_cycle_id(cycle_id or default_cycle_id())
    if task_id is None and not allow_missing_task_for_bootstrap:
        raise ValueError("task_id is required unless allow_missing_task_for_bootstrap is explicitly enabled")
    if task_id is not None and allow_missing_task_for_bootstrap:
        raise ValueError("allow_missing_task_for_bootstrap is valid only when task_id is absent")
    directory = cycle_dir(root, cycle_id)
    (directory / "packets").mkdir(parents=True, exist_ok=True)
    metadata_path = initialization_path(root, cycle_id)
    metadata_exists = metadata_path.is_file()
    requested_protocol = (
        None
        if metadata_exists and stage_compiler_protocol_version is None
        else _protocol_version(
            {
                "stage_compiler_protocol_version": (
                    stage_compiler_protocol_version
                    if stage_compiler_protocol_version is not None
                    else STAGE_COMPILER_PROTOCOL_VERSION
                )
            }
        )
    )
    requested_preparation = stage_preparation_schema_version
    if not metadata_exists and requested_preparation is None:
        requested_preparation = (
            STAGE_PREPARATION_SCHEMA_VERSION if requested_protocol == 2 else 1
        )
    if requested_preparation is not None:
        if isinstance(requested_preparation, bool) or requested_preparation not in {
            1,
            2,
            STAGE_PREPARATION_SCHEMA_VERSION,
        }:
            raise ValueError("unsupported stage_preparation_schema_version")
        effective_protocol = requested_protocol or 1
        if effective_protocol == 1 and requested_preparation != 1:
            raise ValueError("protocol v1 requires preparation schema v1")
        if effective_protocol == 2 and requested_preparation not in {2, 3}:
            raise ValueError("protocol v2 requires preparation schema v2 or v3")
    expected_reason = str(reason or "cycle ledger initialized")
    with ledger_lock(root, cycle_id, exclusive=True):
        existing_metadata = _load_existing_metadata(metadata_path)
        if existing_metadata is not None:
            if (
                existing_metadata.get("task_id") != task_id
                or str(existing_metadata.get("reason") or "") != expected_reason
                or existing_metadata.get("allow_missing_task_for_bootstrap", False)
                is not allow_missing_task_for_bootstrap
                or (
                    requested_protocol is not None
                    and _protocol_version(existing_metadata) != requested_protocol
                )
                or (
                    requested_preparation is not None
                    and existing_metadata.get(
                        "stage_preparation_schema_version",
                        2
                        if existing_metadata.get("stage_compiler_protocol_version") == 2
                        else 1,
                    )
                    != requested_preparation
                )
            ):
                raise ValueError(f"cycle `{cycle_id}` is already initialized with different task or reason")
            metadata = existing_metadata
            cycle_existing = True
        else:
            metadata = {
                "format_version": LEDGER_FORMAT_VERSION,
                "cycle_id": cycle_id,
                "initialized_at": now_iso(),
                "task_id": task_id,
                "reason": expected_reason,
                "storage_bootstrap_only": True,
                "first_canonical_step": "context",
                "allow_missing_task_for_bootstrap": allow_missing_task_for_bootstrap,
            }
            if requested_protocol is not None:
                metadata["stage_compiler_protocol_version"] = requested_protocol
            if requested_preparation is not None:
                metadata["stage_preparation_schema_version"] = requested_preparation
            atomic_writer(metadata_path, json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
            cycle_existing = False
        events = read_events_unlocked(root, cycle_id)
        current = write_current_unlocked(
            root,
            cycle_id,
            events,
            protocol_version=_protocol_version(metadata),
            atomic_writer=atomic_writer,
        )
    result = {
        "cycle_id": cycle_id,
        "cycle_dir": rel_path(root, directory),
        "cycle_existing": cycle_existing,
        "initialization": metadata,
        "initialization_path": rel_path(root, metadata_path),
        "current_stage": current,
        "ledger_path": rel_path(root, ledger_path(root, cycle_id)),
        "current_stage_path": rel_path(root, current_stage_path(root, cycle_id)),
    }
    if terminal_reopen_result is not None:
        result["terminal_reopen_result"] = terminal_reopen_result
    return result
