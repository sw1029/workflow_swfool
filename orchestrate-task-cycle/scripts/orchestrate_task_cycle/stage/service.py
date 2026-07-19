"""Read-mostly stage preparation, submission, and bounded advance services."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..collect_cycle_context import collect
from ..cycle_ledger import (
    append_event,
    cycle_dir,
    read_events,
    read_initialization_metadata,
)
from ..model_context import project_model_context
from ..result_contract.api import validate as validate_result
from ..transition.constants import BOOTSTRAP_ORDER, ORDER, TERMINAL_OK
from .builder import ResultBuilder
from .contracts import (
    PREPARATION_KIND,
    PREPARATION_SCHEMA_VERSION,
    canonical_bytes,
    canonical_sha256,
    leaf_count,
    preparation_identity,
    require_expected_preparation,
    stale_preparation_result,
    state_fingerprint,
    validate_preparation,
)
from .gates import boundary_reason, validate_submission_transition
from .packet_projection import MAX_MODEL_PACKET_BYTES, model_packet as _model_packet
from .publication import (
    existing_publication,
    publish_result,
    published_preparation,
    replay_mismatch,
    result_path,
)
from .specs import TARGET_COMPILE_SPECS


STOP_REASONS = frozenset(
    {
        "awaiting_owner_result",
        "awaiting_model_judgment",
        "awaiting_authority",
        "awaiting_exact_approval",
        "awaiting_external_input",
        "awaiting_goal_truth",
        "awaiting_risk_acceptance",
        "awaiting_design_selection",
        "awaiting_advice_normalization",
        "awaiting_running_execution",
        "awaiting_effect_settlement",
        "model_context_budget_exceeded",
        "model_packet_budget_exceeded",
        "stale_preparation",
        "blocked_transition",
        "rejected_result",
        "terminal_wait",
        "no_progress_replay",
        "step_budget_exhausted",
        "complete",
    }
)


def _context(
    root: Path,
    cycle_id: str,
    max_files: int,
    max_paths: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    full = collect(root, include_git=True, max_files=max_files, cycle_id=cycle_id)
    return full, project_model_context(full, max_paths=max_paths)


def _task_id(root: Path, cycle_id: str) -> str | None:
    initialization = read_initialization_metadata(root, cycle_id)
    value = initialization.get("task_id")
    return str(value) if value is not None and str(value).strip() else None


def _derived_values(
    root: Path,
    cycle_id: str,
    target: str,
    model_context: dict[str, Any],
) -> dict[str, Any]:
    spec = TARGET_COMPILE_SPECS[target]
    task_id = _task_id(root, cycle_id)
    advice = (
        model_context.get("advice")
        if isinstance(model_context.get("advice"), dict)
        else {}
    )
    candidates: dict[str, Any] = {
        "step": target,
        "cycle_id": cycle_id,
        "task_id": task_id,
        "used_goal_truth": list(
            (model_context.get("goal_truth") or {}).get("used_goal_truth") or []
        ),
        "used_advice": [
            item.get("advice_id")
            for item in advice.get("items") or []
            if isinstance(item, dict) and item.get("advice_id")
        ],
    }
    return {
        field: candidates[field]
        for field in spec.derived_fields
        if candidates.get(field) is not None
    }


def prepare_stage(
    root: str | Path,
    cycle_id: str,
    target: str,
    *,
    workflow_mode: str = "normal",
    max_files: int = 12,
    max_paths: int = 40,
) -> dict[str, Any]:
    workspace = Path(root).resolve(strict=True)
    cycle_dir(workspace, cycle_id)
    if target not in TARGET_COMPILE_SPECS:
        raise ValueError(f"unsupported stage target: {target}")
    if workflow_mode not in {"normal", "bootstrap"}:
        raise ValueError(f"unsupported workflow mode: {workflow_mode}")
    events = read_events(workspace, cycle_id)
    if not any(event.get("step") == "context" for event in events):
        raise ValueError("stage prepare requires the deterministic context event")
    expected_target = _next_target(events, workflow_mode)
    if expected_target != target:
        raise ValueError(
            f"stage target is not dependency-ready: expected {expected_target!r}, got {target!r}"
        )
    full, model = _context(workspace, cycle_id, max_files, max_paths)
    spec = TARGET_COMPILE_SPECS[target]
    packet = _model_packet(target, full, model, workflow_mode)
    preparation: dict[str, Any] = {
        "schema_version": PREPARATION_SCHEMA_VERSION,
        "artifact_kind": PREPARATION_KIND,
        "cycle_id": cycle_id,
        "target": target,
        "workflow_mode": workflow_mode,
        "state_fingerprint": state_fingerprint(model, spec.dependency_roles),
        "fingerprint_roles": list(spec.dependency_roles),
        "model_context": model,
        "model_packet": packet,
        "model_packet_sha256": canonical_sha256(packet),
        "derived_values": _derived_values(workspace, cycle_id, target, model),
        "result_contract": {
            "required_fields": list(spec.required_fields),
            "derived_fields": list(spec.derived_fields),
            "semantic_fields": list(spec.semantic_fields),
            "optional_semantic_fields": list(spec.optional_semantic_fields),
            "owner_receipt_fields": list(spec.owner_receipt_fields),
            "optional_owner_fields": list(spec.optional_owner_fields),
            "reasoned_not_applicable_fields": list(spec.reasoned_not_applicable_fields),
            "forbidden_derived_overrides": list(spec.derived_fields),
        },
        "next_action": (
            {"kind": "stop", "reason": model.get("stop_reason")}
            if model.get("projection_status") == "block"
            else {"kind": "submit_judgment", "command": "stage submit"}
        ),
    }
    preparation["preparation_id"] = (
        "stageprep-" + canonical_sha256(preparation_identity(preparation))[:32]
    )
    preparation["compiler_metrics"] = {
        "required_field_count": len(spec.required_fields),
        "derived_field_count": len(spec.derived_fields),
        "semantic_field_count": len(spec.semantic_fields),
        "owner_receipt_field_count": len(spec.owner_receipt_fields),
        "model_packet_bytes": len(canonical_bytes(packet)),
        "model_packet_limit_bytes": MAX_MODEL_PACKET_BYTES,
    }
    return preparation


def submit_stage(
    root: str | Path,
    preparation: dict[str, Any],
    judgment: dict[str, Any],
    *,
    mode: str = "block",
    apply: bool = False,
    max_files: int = 12,
    max_paths: int = 40,
) -> dict[str, Any]:
    workspace = Path(root).resolve(strict=True)
    preparation = validate_preparation(preparation)
    cycle_id = str(preparation["cycle_id"])
    replay = published_preparation(workspace, cycle_id, preparation)
    if not replay:
        _full, current_model = _context(workspace, cycle_id, max_files, max_paths)
        current_fingerprint = state_fingerprint(
            current_model, preparation["fingerprint_roles"]
        )
        if current_fingerprint != preparation["state_fingerprint"]:
            return stale_preparation_result(preparation, current_fingerprint)
        expected = prepare_stage(
            workspace,
            cycle_id,
            str(preparation["target"]),
            workflow_mode=str(preparation["workflow_mode"]),
            max_files=max_files,
            max_paths=max_paths,
        )
        preparation = require_expected_preparation(preparation, expected)
    result = ResultBuilder().build(preparation, judgment)
    result_sha256 = canonical_sha256(result)
    path = result_path(workspace, cycle_id, str(preparation["target"]), result_sha256)
    existing = existing_publication(
        workspace,
        cycle_id,
        str(preparation["target"]),
        preparation,
        result,
        result_sha256,
    )
    if existing is not None:
        return {
            "status": "ok",
            "stop_reason": None,
            "preparation_id": preparation["preparation_id"],
            "result": result,
            "result_artifact_ref": existing["result_artifact_ref"],
            "result_artifact_sha256": result_sha256,
            "applied": True,
            "event": existing["event"],
            "event_duplicate": True,
            "ledger_path": existing["ledger_path"],
            "result_contract": {
                "status": "ok",
                "target": preparation["target"],
                "mode": "replay",
                "findings": [],
                "missing_fields": [],
            },
            "compiler_metrics": {
                "semantic_leaf_count": leaf_count(judgment.get("semantic") or {}),
                "owner_result_leaf_count": leaf_count(
                    judgment.get("owner_result") or {}
                ),
                "compiled_result_leaf_count": leaf_count(result),
                "validation_finding_count": 0,
            },
        }
    if replay:
        return replay_mismatch(preparation)
    current_full, current_model = _context(workspace, cycle_id, max_files, max_paths)
    current_fingerprint = state_fingerprint(
        current_model, preparation["fingerprint_roles"]
    )
    if current_fingerprint != preparation["state_fingerprint"]:
        return stale_preparation_result(preparation, current_fingerprint)
    transition = validate_submission_transition(current_full, preparation)
    if transition["status"] == "block":
        return {
            "status": "block",
            "stop_reason": "blocked_transition",
            "preparation_id": preparation["preparation_id"],
            "transition_validation": transition,
            "applied": False,
        }
    validation = validate_result(str(preparation["target"]), result, mode, current_full)
    relative = path.relative_to(workspace).as_posix()
    output: dict[str, Any] = {
        "status": validation["status"],
        "stop_reason": ("rejected_result" if validation["status"] == "block" else None),
        "preparation_id": preparation["preparation_id"],
        "result": result,
        "result_contract": validation,
        "result_artifact_ref": relative,
        "result_artifact_sha256": result_sha256,
        "applied": False,
        "compiler_metrics": {
            "semantic_leaf_count": leaf_count(judgment.get("semantic") or {}),
            "owner_result_leaf_count": leaf_count(judgment.get("owner_result") or {}),
            "compiled_result_leaf_count": leaf_count(result),
            "validation_finding_count": len(validation.get("findings") or []),
        },
    }
    if not apply or validation["status"] == "block":
        return output
    publication = publish_result(
        workspace, cycle_id, preparation, result, result_sha256
    )
    output.update(
        {
            "applied": True,
            "event": publication["event"],
            "event_duplicate": publication["event_duplicate"],
            "ledger_path": publication["ledger_path"],
        }
    )
    return output


def _target_order(workflow_mode: str) -> list[str]:
    order = BOOTSTRAP_ORDER if workflow_mode == "bootstrap" else ORDER
    return [target for target in order if target in TARGET_COMPILE_SPECS]


def _next_target(events: list[dict[str, Any]], workflow_mode: str) -> str | None:
    latest = {str(event.get("step")): event for event in events}
    for target in _target_order(workflow_mode):
        event = latest.get(target)
        if event is None or str(event.get("status") or "").lower() not in TERMINAL_OK:
            return target
    return None


def _context_event(
    root: Path,
    cycle_id: str,
    full: dict[str, Any],
    model: dict[str, Any],
) -> dict[str, Any]:
    task_id = _task_id(root, cycle_id)
    identity = {
        "cycle_id": cycle_id,
        "task": model.get("task"),
        "goal_truth": model.get("goal_truth"),
        "advice_digest": (model.get("advice") or {}).get("advice_packet_digest"),
    }
    return {
        "step": "context",
        "status": "completed",
        "event_id": "stage-context-" + canonical_sha256(identity)[:32],
        "reason": "deterministic cycle context projection",
        "task_id": task_id,
        "task_absent": task_id is None,
        "task_md": full.get("task_md"),
        "used_goal_truth": (model.get("goal_truth") or {}).get("used_goal_truth", []),
        "used_advice": [
            item.get("advice_id")
            for item in (model.get("advice") or {}).get("items", [])
            if isinstance(item, dict) and item.get("advice_id")
        ],
        "context_fingerprint": state_fingerprint(model),
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
) -> dict[str, Any]:
    if max_steps < 1 or max_steps > 32:
        raise ValueError("max_steps must be between 1 and 32")
    workspace = Path(root).resolve(strict=True)
    read_initialization_metadata(workspace, cycle_id)
    actions: list[dict[str, Any]] = []
    fingerprints: set[str] = set()
    for _step in range(max_steps):
        events = read_events(workspace, cycle_id)
        latest = {str(event.get("step")): event for event in events}
        blocked = [
            event
            for event in latest.values()
            if str(event.get("status") or "").lower() in {"blocked", "failed"}
        ]
        if blocked:
            return {
                "status": "block",
                "stop_reason": "blocked_transition",
                "blocking_event_ids": [event.get("event_id") for event in blocked],
                "actions": actions,
            }
        full, model = _context(workspace, cycle_id, max_files, max_paths)
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
        if "context" not in latest:
            event = _context_event(workspace, cycle_id, full, model)
            actions.append({"kind": "append_system_context", "event": event})
            if not apply:
                return {
                    "status": "ready",
                    "stop_reason": None,
                    "actions": actions,
                    "applied": False,
                }
            publication = append_event(workspace, cycle_id, event)
            actions[-1]["publication"] = {
                "event_id": publication["event"].get("event_id"),
                "event_duplicate": bool(publication.get("event_duplicate")),
            }
            continue
        target = _next_target(events, workflow_mode)
        if target is None:
            return {
                "status": "complete",
                "stop_reason": "complete",
                "actions": actions,
                "applied": bool(actions and apply),
            }
        preparation = prepare_stage(
            workspace,
            cycle_id,
            target,
            workflow_mode=workflow_mode,
            max_files=max_files,
            max_paths=max_paths,
        )
        reason = boundary_reason(target)
        return {
            "status": "waiting",
            "stop_reason": reason,
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


__all__ = ["STOP_REASONS", "advance_stage", "prepare_stage", "submit_stage"]
