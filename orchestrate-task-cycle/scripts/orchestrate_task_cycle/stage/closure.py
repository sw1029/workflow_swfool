"""Fail-closed recognition of producer-owned terminal execution failures."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from run_task_code_and_log.terminal_projection import (
    CONTRACT_ID as RUN_TERMINAL_CONTRACT_ID,
    reopen_run_terminal_projection,
    validate_run_terminal_projection,
)

from ..ledger.constants import COMPILED_STAGE_OBSERVATION_EVENT_KIND


_FAILURE_STATUSES = frozenset({"blocked", "failed", "failed_closed"})


def validate_failed_closed_projection(value: Any) -> dict[str, Any]:
    """Validate the failed-closed subset of run_terminal_projection@v1."""

    projection = validate_run_terminal_projection(value)
    if projection["status"] != "failed_closed":
        raise ValueError("run terminal projection is not failed_closed")
    return projection


def is_run_failure_event(event: Any) -> bool:
    """Return whether a canonical run event reports an execution failure."""

    if not isinstance(event, dict) or event.get("step") != "run":
        return False
    ledger_status = str(event.get("status") or "").strip().lower()
    execution_status = str(event.get("execution_status") or "").strip().lower()
    return (
        ledger_status in {"blocked", "failed"}
        or execution_status in _FAILURE_STATUSES
    )


def is_run_terminal_event(event: Any) -> bool:
    """Return whether an event claims the producer-owned terminal protocol."""

    return (
        isinstance(event, dict)
        and event.get("step") == "run"
        and event.get("observation_kind") == "run_terminal"
    )


def reopen_run_terminal_event(
    root: str | Path,
    cycle_id: str,
    event: Any,
) -> dict[str, Any]:
    """Reopen and validate one compiler-owned terminal run event."""

    if (
        not isinstance(event, dict)
        or event.get("step") != "run"
        or event.get("producer_kind") != "stage_observer"
        or event.get("event_kind") != COMPILED_STAGE_OBSERVATION_EVENT_KIND
        or event.get("observation_kind") != "run_terminal"
        or event.get("cycle_id") != cycle_id
    ):
        raise ValueError("run terminal event is not producer-owned")
    reopened = reopen_run_terminal_projection(
        root,
        event.get("run_terminal_projection"),
        event.get("run_terminal_projection_binding"),
        expected_cycle_id=cycle_id,
    )
    projection = reopened["projection"]
    if projection["terminal"] is not True or projection["status"] == "running":
        raise ValueError("run terminal event contains a live projection")
    expected_status = (
        "failed" if projection["status"] == "failed_closed" else "complete"
    )
    if (
        event.get("run_id") != projection["run_id"]
        or event.get("execution_status") != projection["status"]
        or str(event.get("status") or "").lower() != expected_status
    ):
        raise ValueError("run terminal event differs from its projection")
    expected_event_id = (
        f"{cycle_id}-run-terminal-{projection['projection_id']}"
    )
    if event.get("event_id") != expected_event_id:
        raise ValueError("run terminal event identity is not deterministic")
    return projection


def is_verified_run_terminal_event(
    event: Any,
    *,
    root: str | Path | None = None,
    cycle_id: str | None = None,
) -> bool:
    """Recognize a terminal claim only while its producer CAS still reopens."""

    if (
        not is_run_terminal_event(event)
        or root is None
        or cycle_id is None
    ):
        return False
    try:
        reopen_run_terminal_event(root, cycle_id, event)
    except (OSError, TypeError, ValueError):
        return False
    return True


def is_failed_closed_run_event(
    event: Any,
    *,
    root: str | Path | None = None,
    cycle_id: str | None = None,
) -> bool:
    """Recognize only a producer-CAS-backed, non-retrying terminal run failure."""

    if not is_run_failure_event(event):
        return False
    ledger_status = str(event.get("status") or "").strip().lower()
    execution_status = str(event.get("execution_status") or "").strip().lower()
    if (
        ledger_status in {"blocked", "failed"}
        and execution_status
        and execution_status not in _FAILURE_STATUSES
    ):
        return False
    if root is None or cycle_id is None:
        return False
    try:
        projection = reopen_run_terminal_event(root, cycle_id, event)
        validate_failed_closed_projection(projection)
    except (OSError, TypeError, ValueError):
        return False
    return projection["status"] == "failed_closed"


__all__ = [
    "RUN_TERMINAL_CONTRACT_ID",
    "is_failed_closed_run_event",
    "is_run_failure_event",
    "is_run_terminal_event",
    "is_verified_run_terminal_event",
    "reopen_run_terminal_event",
    "validate_failed_closed_projection",
]
