"""Read-mostly stage preparation, submission, and bounded advance services."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..collect_cycle_context import collect
from ..cycle_ledger import (
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
    PREPARATION_SCHEMA_VERSION_V2,
    PREPARATION_SCHEMA_VERSION_V3,
    canonical_bytes,
    canonical_sha256,
    leaf_count,
    preparation_identity,
    require_expected_preparation,
    stale_preparation_result,
    state_fingerprint,
    validate_preparation,
)
from .gates import validate_submission_transition
from .packet_projection import MAX_MODEL_PACKET_BYTES, model_packet as _model_packet
from .publication import (
    existing_publication,
    publish_result,
    published_preparation,
    replay_mismatch,
    result_path,
)
from .protocol import cycle_preparation_version
from .specs import LEGACY_TARGET_COMPILE_SPECS, TARGET_COMPILE_SPECS
from .system_steps import compile_derived_values
from .v2_service import prepare_v2, require_v1_judgment, submit_v2


STOP_REASONS = frozenset(
    {
        "awaiting_owner_result",
        "awaiting_model_judgment",
        "awaiting_deterministic_result",
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


def prepare_stage(
    root: str | Path,
    cycle_id: str,
    target: str,
    *,
    workflow_mode: str = "normal",
    max_files: int = 12,
    max_paths: int = 40,
    preparation_schema_version: int | None = None,
    persist_compiler_artifacts: bool = False,
) -> dict[str, Any]:
    workspace = Path(root).resolve(strict=True)
    cycle_dir(workspace, cycle_id)
    if target not in TARGET_COMPILE_SPECS:
        raise ValueError(f"unsupported stage target: {target}")
    if workflow_mode not in {"normal", "bootstrap"}:
        raise ValueError(f"unsupported workflow mode: {workflow_mode}")
    preparation_schema_version = cycle_preparation_version(
        workspace, cycle_id, preparation_schema_version
    )
    events = read_events(workspace, cycle_id)
    if not any(event.get("step") == "context" for event in events):
        raise ValueError("stage prepare requires the deterministic context event")
    expected_target = _next_target(
        events, workflow_mode, preparation_schema_version
    )
    if expected_target != target:
        raise ValueError(
            f"stage target is not dependency-ready: expected {expected_target!r}, got {target!r}"
        )
    if preparation_schema_version in {
        PREPARATION_SCHEMA_VERSION_V2,
        PREPARATION_SCHEMA_VERSION_V3,
    }:
        return prepare_v2(
            workspace,
            cycle_id,
            target,
            workflow_mode,
            _task_id(workspace, cycle_id),
            max_files=max_files,
            max_paths=max_paths,
            persist_compiler_artifacts=persist_compiler_artifacts,
            schema_version=preparation_schema_version,
        )
    full, model = _context(workspace, cycle_id, max_files, max_paths)
    spec = LEGACY_TARGET_COMPILE_SPECS[target]
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
        "derived_values": compile_derived_values(
            spec, cycle_id, target, _task_id(workspace, cycle_id), model
        ),
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
    judgment: dict[str, Any] | None = None,
    *,
    mode: str = "block",
    apply: bool = False,
    max_files: int = 12,
    max_paths: int = 40,
    owner_result_ref: str | None = None,
    owner_result_sha256: str | None = None,
    semantic_ref: str | None = None, semantic_sha256: str | None = None,
    routing_ref: str | None = None, routing_sha256: str | None = None,
    usage_ref: str | None = None, usage_sha256: str | None = None,
) -> dict[str, Any]:
    workspace = Path(root).resolve(strict=True)
    preparation = validate_preparation(preparation)
    cycle_id = str(preparation["cycle_id"])
    cycle_preparation_version(workspace, cycle_id, preparation["schema_version"])
    if preparation["schema_version"] in {
        PREPARATION_SCHEMA_VERSION_V2,
        PREPARATION_SCHEMA_VERSION_V3,
    }:
        if judgment is not None:
            raise ValueError("v2 stage submission forbids inline judgment JSON")
        return submit_v2(
            workspace,
            preparation,
            task_id=_task_id(workspace, cycle_id),
            owner_result_ref=owner_result_ref,
            owner_result_sha256=owner_result_sha256,
            semantic_ref=semantic_ref,
            semantic_sha256=semantic_sha256,
            routing_ref=routing_ref,
            routing_sha256=routing_sha256,
            usage_ref=usage_ref, usage_sha256=usage_sha256,
            mode=mode,
            apply=apply,
            max_files=max_files,
            max_paths=max_paths,
        )
    exact_bindings = (
        owner_result_ref,
        owner_result_sha256,
        semantic_ref,
        semantic_sha256,
        routing_ref,
        routing_sha256,
        usage_ref,
        usage_sha256,
    )
    judgment = require_v1_judgment(judgment, *exact_bindings)
    return _submit_v1(
        workspace,
        preparation,
        judgment,
        mode=mode,
        apply=apply,
        max_files=max_files,
        max_paths=max_paths,
    )


def _submit_v1(
    workspace: Path,
    preparation: dict[str, Any],
    judgment: dict[str, Any],
    *,
    mode: str,
    apply: bool,
    max_files: int,
    max_paths: int,
) -> dict[str, Any]:
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
        repair_projection=apply,
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
    publication = publish_result(workspace, cycle_id, preparation, result, result_sha256)
    output.update(
        {
            "applied": True,
            "event": publication["event"],
            "event_duplicate": publication["event_duplicate"],
            "ledger_path": publication["ledger_path"],
        }
    )
    return output


def _target_order(workflow_mode: str, schema_version: int = 1) -> list[str]:
    order = BOOTSTRAP_ORDER if workflow_mode == "bootstrap" else ORDER
    if schema_version in {PREPARATION_SCHEMA_VERSION_V2, PREPARATION_SCHEMA_VERSION_V3}:
        return list(order)
    return [target for target in order if target in TARGET_COMPILE_SPECS]


def _next_target(
    events: list[dict[str, Any]], workflow_mode: str, schema_version: int = 1
) -> str | None:
    latest = {str(event.get("step")): event for event in events}
    for target in _target_order(workflow_mode, schema_version):
        event = latest.get(target)
        if event is None or str(event.get("status") or "").lower() not in TERMINAL_OK:
            return target
    return None


def execute_deterministic_stage(*args: Any, **kwargs: Any) -> dict[str, Any]:
    from .advance import execute_deterministic_stage as execute

    return execute(*args, **kwargs)


def advance_stage(*args: Any, **kwargs: Any) -> dict[str, Any]:
    from .advance import advance_stage as advance

    return advance(*args, **kwargs)


__all__ = [
    "STOP_REASONS",
    "advance_stage",
    "execute_deterministic_stage",
    "prepare_stage",
    "submit_stage",
]
