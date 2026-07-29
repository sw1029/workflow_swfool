"""Publish one producer-owned terminal run observation into an enforced ledger."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from run_task_code_and_log.terminal_projection import (
    reopen_run_terminal_projection,
    validate_run_terminal_projection,
)

from ..cycle_ledger import read_events
from ..ledger.compiled_events import append_compiled_run_terminal
from ..ledger.semantic_seeds import make_run_terminal_seed
from ..ledger.support import read_initialization_metadata


_SUCCESS_STATES = frozenset(
    {"complete", "completed", "passed", "success", "succeeded"}
)
_FAILURE_STATES = frozenset(
    {"blocked", "failed", "failed_closed", "failure", "not_running", "stale"}
)


def _bound_refs(value: Any) -> set[tuple[str, str]]:
    rows: set[tuple[str, str]] = set()
    if isinstance(value, dict):
        if set(value) >= {"ref", "sha256"}:
            rows.add((str(value["ref"]), str(value["sha256"])))
        for item in value.values():
            rows.update(_bound_refs(item))
    elif isinstance(value, list):
        for item in value:
            rows.update(_bound_refs(item))
    return rows


def _run_evidence(
    events: list[dict[str, Any]], projection: dict[str, Any]
) -> None:
    run_id = projection["run_id"]
    sources = [
        event
        for event in events
        if event.get("run_id") == run_id
        and event.get("observation_kind") != "run_terminal"
    ]
    if not sources:
        raise ValueError("terminal projection lacks an active run observation")
    latest = sources[-1]
    if (
        projection["monitor"]["monitor_command_id"]
        != latest.get("event_id")
    ):
        raise ValueError(
            "terminal projection does not bind the latest run observation"
        )
    observed = str(
        latest.get("execution_status") or latest.get("status") or ""
    ).lower()
    expected = (
        _SUCCESS_STATES
        if projection["status"] == "succeeded"
        else _FAILURE_STATES
    )
    if observed not in expected:
        raise ValueError(
            "run observation does not support the terminal disposition"
        )
    refs: set[str] = set()
    bindings: set[tuple[str, str]] = set()
    for event in sources:
        refs.update(
            str(item)
            for item in (event.get("artifacts") or [])
            if isinstance(item, str)
        )
        monitor = event.get("monitor_result")
        if isinstance(monitor, dict):
            refs.update(
                str(item["path"])
                for item in (monitor.get("completion_artifacts") or [])
                if isinstance(item, dict)
                and item.get("exists") is True
                and isinstance(item.get("path"), str)
            )
        bindings.update(_bound_refs(event))
    claimed = [
        projection["harvest"]["evidence_binding"],
        *(
            row["binding"]
            for row in projection["safe_surviving_artifacts"]
        ),
        *(
            row["binding"] for row in projection["discarded_artifacts"]
        ),
    ]
    if projection.get("failure") is not None:
        claimed.append(projection["failure"]["evidence_binding"])
    for binding in (item for item in claimed if item is not None):
        identity = (binding["ref"], binding["sha256"])
        if binding["ref"] not in refs and identity not in bindings:
            raise ValueError(
                "terminal evidence was not declared by the active run"
            )


def publish_run_terminal_observation(
    root: str | Path,
    cycle_id: str,
    *,
    projection: Any,
    projection_binding: Any,
) -> dict[str, Any]:
    workspace = Path(root).resolve(strict=True)
    validated = validate_run_terminal_projection(projection)
    if validated["status"] == "running":
        raise ValueError("running projection is not terminal")
    reopened = reopen_run_terminal_projection(
        workspace,
        validated,
        projection_binding,
        expected_cycle_id=cycle_id,
    )
    binding = reopened["binding"]
    task_id = read_initialization_metadata(workspace, cycle_id).get("task_id")
    previous = [
        event
        for event in read_events(workspace, cycle_id)
        if event.get("step") == "run"
    ]
    if not previous or previous[-1].get("run_id") != validated["run_id"]:
        raise ValueError("terminal projection does not match the active run")
    _run_evidence(previous, validated)
    semantic = {
        "task_id": task_id,
        "run_id": validated["run_id"],
        "execution_status": validated["status"],
        "run_terminal_projection": validated,
        "run_terminal_projection_binding": binding,
        "reason": f"verified run terminal projection: {validated['status']}",
    }
    return append_compiled_run_terminal(
        workspace, cycle_id, make_run_terminal_seed(semantic)
    )


__all__ = ("publish_run_terminal_observation",)
