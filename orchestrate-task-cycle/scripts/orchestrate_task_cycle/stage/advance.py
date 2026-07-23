"""Bounded stage advancement and deterministic execution dispatch."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..cycle_ledger import append_event, read_events, read_initialization_metadata
from ..ledger.compiled_events import append_compiled_system_stage
from ..ledger.workflow_contract import (
    require_cycle_mutation_contract,
    workflow_contract_state,
)
from .contracts import (
    PREPARATION_SCHEMA_VERSION_V2,
    PREPARATION_SCHEMA_VERSION_V3,
    canonical_sha256,
    state_fingerprint,
)
from .gates import boundary_reason
from .protocol import cycle_preparation_version
from .specs import TARGET_COMPILE_SPECS
from .system_steps import render_context_event, render_system_event
from .v2_context import collect_selected_context
from .v2_specs import SYSTEM_STEPS


def execute_deterministic_stage(
    root: str | Path,
    cycle_id: str,
    target: str,
    *,
    workflow_mode: str = "normal",
    apply: bool = False,
    max_files: int = 12,
    max_paths: int = 40,
    preparation_schema_version: int | None = None,
) -> dict[str, Any]:
    from .deterministic_execution import apply_prepared_deterministic
    from .service import prepare_stage

    workspace = Path(root).resolve(strict=True)
    if apply:
        require_cycle_mutation_contract(
            read_initialization_metadata(workspace, cycle_id),
            "execute deterministic stage",
        )
    preparation = prepare_stage(
        workspace,
        cycle_id,
        target,
        workflow_mode=workflow_mode,
        max_files=max_files,
        max_paths=max_paths,
        preparation_schema_version=preparation_schema_version,
        persist_compiler_artifacts=False,
    )
    if preparation.get("schema_version") != PREPARATION_SCHEMA_VERSION_V3:
        raise ValueError("deterministic dispatcher requires preparation schema v3")
    if preparation.get("executor_kind") != "deterministic":
        raise ValueError("stage target is not a deterministic executor")
    if not apply:
        return {
            "status": "ready",
            "stop_reason": None,
            "action": {
                "kind": "execute_deterministic",
                "target": target,
                "preparation_id": preparation["preparation_id"],
            },
            "preparation": preparation,
            "model_call_count": 0,
            "model_visible_bytes": 0,
            "applied": False,
        }
    output, committed = apply_prepared_deterministic(
        workspace,
        preparation,
        operation="execute deterministic stage",
        max_files=max_files,
        max_paths=max_paths,
    )
    if committed is None:
        output["deterministic_execution"] = {
            "model_call_count": 0,
            "model_visible_bytes": 0,
            "files_written_count": 0,
        }
        return output
    output["deterministic_execution"] = committed
    return output


def _context(
    workspace: Path,
    cycle_id: str,
    schema_version: int,
    max_files: int,
    max_paths: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if schema_version in {PREPARATION_SCHEMA_VERSION_V2, PREPARATION_SCHEMA_VERSION_V3}:
        full, model, _metrics = collect_selected_context(
            workspace,
            cycle_id,
            TARGET_COMPILE_SPECS["authority"],
            max_files=max_files,
            max_paths=max_paths,
        )
        return full, model
    from .service import _context as legacy_context

    return legacy_context(workspace, cycle_id, max_files, max_paths)


def _blocked(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    latest = {str(event.get("step")): event for event in events}
    return [
        event
        for event in latest.values()
        if str(event.get("status") or "").lower() in {"blocked", "failed"}
    ]


def _deterministic_disposition(
    schema_version: int,
    target: str,
    actions: list[dict[str, Any]],
    apply: bool,
) -> bool | dict[str, Any]:
    deterministic = (
        TARGET_COMPILE_SPECS[target].executor_kind == "deterministic"
    )
    if schema_version == PREPARATION_SCHEMA_VERSION_V2 and deterministic:
        return {
            "status": "block",
            "stop_reason": "preparation_v3_required",
            "actions": actions,
            "applied": bool(actions and apply),
        }
    return schema_version == PREPARATION_SCHEMA_VERSION_V3 and deterministic


def _append_system(
    workspace: Path,
    cycle_id: str,
    event: dict[str, Any],
    kind: str,
    actions: list[dict[str, Any]],
    apply: bool,
) -> dict[str, Any] | None:
    actions.append({"kind": kind, "event": event})
    if not apply:
        return {
            "status": "ready",
            "stop_reason": None,
            "actions": actions,
            "applied": False,
        }
    metadata = read_initialization_metadata(workspace, cycle_id)
    contract_state = workflow_contract_state(metadata)
    if contract_state in {"historical_v1_read_only", "historical_v2_read_only"}:
        raise ValueError(
            "historical unmarked protocol-v2 cycles are read-only; "
            "initialize a new compiler-first cycle"
        )
    publication = (
        append_compiled_system_stage(
            workspace,
            cycle_id,
            str(event["step"]),
        )
        if contract_state == "enforced"
        else append_event(workspace, cycle_id, event)
    )
    if contract_state == "enforced":
        actions[-1]["event"] = publication["event"]
    actions[-1]["publication"] = {
        "event_id": publication["event"].get("event_id"),
        "event_duplicate": bool(publication.get("event_duplicate")),
    }
    if publication.get("workflow_contract_warning") is not None:
        actions[-1]["publication"]["workflow_contract_warning"] = publication[
            "workflow_contract_warning"
        ]
    return None


def _execute_prepared(
    workspace: Path,
    preparation: dict[str, Any],
    actions: list[dict[str, Any]],
    *,
    apply: bool,
    max_files: int,
    max_paths: int,
) -> dict[str, Any] | None:
    from .deterministic_execution import apply_prepared_deterministic

    target = str(preparation["target"])
    actions.append(
        {
            "kind": "execute_deterministic",
            "target": target,
            "preparation_id": preparation["preparation_id"],
        }
    )
    if not apply:
        return {
            "status": "ready",
            "stop_reason": None,
            "actions": actions,
            "preparation": preparation,
            "applied": False,
        }
    execution, committed = apply_prepared_deterministic(
        workspace,
        preparation,
        operation="advance deterministic stage",
        max_files=max_files,
        max_paths=max_paths,
    )
    if committed is None:
        actions[-1]["execution"] = {
            "status": "block",
            "stop_reason": execution.get("stop_reason"),
            "model_call_count": 0,
            "files_written_count": 0,
        }
        return {
            "status": "block",
            "stop_reason": execution.get("stop_reason"),
            "actions": actions,
            "execution": execution,
            "applied": False,
        }
    actions[-1]["execution"] = {
        "status": execution.get("status"),
        "event_id": (execution.get("event") or {}).get("event_id"),
        "result_artifact_ref": execution.get("result_artifact_ref"),
        "model_call_count": 0,
        "effect_committed": committed.get("effect_committed"),
    }
    if execution.get("status") != "block" and execution.get("applied"):
        return None
    return {
        "status": "block",
        "stop_reason": execution.get("stop_reason") or "rejected_result",
        "actions": actions,
        "execution": execution,
        "applied": bool(actions),
    }


def advance_stage(
    root: str | Path,
    cycle_id: str,
    *,
    workflow_mode: str = "normal",
    max_steps: int = 8,
    apply: bool = False,
    max_files: int = 12,
    max_paths: int = 40,
    preparation_schema_version: int | None = None,
) -> dict[str, Any]:
    from .service import _next_target, _task_id, prepare_stage

    if max_steps < 1 or max_steps > 32:
        raise ValueError("max_steps must be between 1 and 32")
    workspace = Path(root).resolve(strict=True)
    metadata = read_initialization_metadata(workspace, cycle_id)
    if workflow_contract_state(metadata) in {
        "historical_v1_read_only",
        "historical_v2_read_only",
        "invalid",
    }:
        raise ValueError(
            "historical unsealed or invalid cycles cannot advance; "
            "initialize a new compiler-first cycle"
        )
    schema_version = cycle_preparation_version(
        workspace, cycle_id, preparation_schema_version
    )
    actions: list[dict[str, Any]] = []
    fingerprints: set[str] = set()
    for _step in range(max_steps):
        events = read_events(workspace, cycle_id)
        blocked = _blocked(events)
        if blocked:
            return {
                "status": "block",
                "stop_reason": "blocked_transition",
                "blocking_event_ids": [event.get("event_id") for event in blocked],
                "actions": actions,
            }
        full, model = _context(workspace, cycle_id, schema_version, max_files, max_paths)
        fingerprint = canonical_sha256(
            {
                "state": state_fingerprint(model),
                "events": [event.get("event_id") for event in events],
            }
        )
        if fingerprint in fingerprints:
            return {
                "status": "block",
                "stop_reason": "no_progress_replay",
                "actions": actions,
            }
        fingerprints.add(fingerprint)
        if model.get("projection_status") == "block":
            return {
                "status": "block",
                "stop_reason": model.get("stop_reason"),
                "actions": actions,
            }
        latest = {str(event.get("step")): event for event in events}
        if "context" not in latest:
            event = render_context_event(
                cycle_id, _task_id(workspace, cycle_id), full, model
            )
            ready = _append_system(
                workspace,
                cycle_id,
                event,
                "append_system_context",
                actions,
                apply,
            )
            if ready:
                return ready
            continue
        target = _next_target(events, workflow_mode, schema_version)
        if target is None:
            return {
                "status": "complete",
                "stop_reason": "complete",
                "actions": actions,
                "applied": bool(actions and apply),
            }
        if schema_version in {2, 3} and target in SYSTEM_STEPS:
            event = render_system_event(
                cycle_id, target, _task_id(workspace, cycle_id), events
            )
            ready = _append_system(
                workspace,
                cycle_id,
                event,
                "append_system_stage",
                actions,
                apply,
            )
            if ready:
                return ready
            continue
        deterministic = _deterministic_disposition(
            schema_version, target, actions, apply
        )
        if isinstance(deterministic, dict):
            return deterministic
        preparation = prepare_stage(
            workspace,
            cycle_id,
            target,
            workflow_mode=workflow_mode,
            max_files=max_files,
            max_paths=max_paths,
            preparation_schema_version=schema_version,
            persist_compiler_artifacts=False,
        )
        if deterministic:
            stopped = _execute_prepared(
                workspace,
                preparation,
                actions,
                apply=apply,
                max_files=max_files,
                max_paths=max_paths,
            )
            if stopped:
                return stopped
            continue
        return {
            "status": "waiting",
            "stop_reason": boundary_reason(target, schema_version),
            "actions": actions,
            "preparation": preparation,
            "applied": bool(actions and apply),
        }
    return {
        "status": "waiting",
        "stop_reason": "step_budget_exhausted",
        "actions": actions,
        "applied": bool(actions and apply),
    }


__all__ = ["advance_stage", "execute_deterministic_stage"]
