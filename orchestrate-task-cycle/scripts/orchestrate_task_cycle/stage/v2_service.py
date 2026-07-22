"""Compact v2 stage preparation and exact-input submission services."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..result_contract.api import validate as validate_result
from .artifact_store import (
    compiler_artifact_binding,
    load_compiler_artifact,
    load_stage_input,
    load_usage_observation,
)
from .builder import ResultBuilder
from .contracts import (
    PREPARATION_KIND,
    PREPARATION_SCHEMA_VERSION_V2,
    canonical_bytes,
    canonical_sha256,
    leaf_count,
    preparation_identity,
    require_expected_preparation,
    stale_preparation_result,
)
from .gates import validate_submission_transition
from .publication import (
    existing_publication,
    publish_result,
    published_preparation,
    replay_mismatch,
)
from .specs import TARGET_COMPILE_SPECS
from .v2_context import (
    collect_selected_context,
    render_work_order,
    selected_state_fingerprint,
)


OUTPUT_SCALARS = (
    "status",
    "validation_verdict",
    "progress_verdict",
    "review_status",
    "quality_verdict",
    "selection_outcome",
    "index_status",
    "commit_status",
    "completion_status",
)


def _stable_binding(value: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value[key]
        for key in ("artifact_type", "ref", "sha256", "size_bytes")
    }


def prepare_v2(
    root: Path,
    cycle_id: str,
    target: str,
    workflow_mode: str,
    task_id: str | None,
    *,
    max_files: int,
    max_paths: int,
    persist_compiler_artifacts: bool = False,
) -> dict[str, Any]:
    spec = TARGET_COMPILE_SPECS[target]
    _full, model, context_metrics = collect_selected_context(
        root, cycle_id, spec, max_files=max_files, max_paths=max_paths
    )
    fingerprint = selected_state_fingerprint(model, spec.dependency_selectors)
    advice = model.get("advice") if isinstance(model.get("advice"), dict) else {}
    candidates: dict[str, Any] = {
        "step": target,
        "cycle_id": cycle_id,
        "task_id": task_id,
        "used_goal_truth": list(
            (model.get("goal_truth") or {}).get("used_goal_truth") or []
        ),
        "used_advice": [
            item.get("advice_id")
            for item in advice.get("items") or []
            if isinstance(item, dict) and item.get("advice_id")
        ],
    }
    derived_values = {
        field: candidates[field]
        for field in spec.derived_fields
        if candidates.get(field) is not None
    }
    context = {
        "schema_version": 1,
        "artifact_kind": "orchestrate_stage_context",
        "cycle_id": cycle_id,
        "target": target,
        "dependency_selectors": list(spec.dependency_selectors),
        "state_fingerprint": fingerprint,
        "model_context": model,
    }
    context_binding = _stable_binding(
        compiler_artifact_binding(
            root,
            cycle_id,
            "context",
            context,
            persist=persist_compiler_artifacts,
        )
    )
    work_order = render_work_order(
        cycle_id,
        target,
        workflow_mode,
        spec,
        model,
        fingerprint,
        context_binding,
    )
    work_order_binding = _stable_binding(
        compiler_artifact_binding(
            root,
            cycle_id,
            "work_order",
            work_order,
            persist=persist_compiler_artifacts,
        )
    )
    blocked = model.get("projection_status") == "block"
    preparation: dict[str, Any] = {
        "schema_version": PREPARATION_SCHEMA_VERSION_V2,
        "artifact_kind": PREPARATION_KIND,
        "cycle_id": cycle_id,
        "target": target,
        "workflow_mode": workflow_mode,
        "executor_kind": spec.executor_kind,
        "model_call_required": bool(spec.semantic_fields),
        "state_fingerprint": fingerprint,
        "fingerprint_roles": list(spec.dependency_selectors),
        "context_binding": context_binding,
        "work_order_binding": work_order_binding,
        "derived_values": derived_values,
        "result_contract": {
            "required_fields": list(spec.required_fields),
            "derived_fields": list(spec.derived_fields),
            "semantic_fields": list(spec.semantic_fields),
            "optional_semantic_fields": list(spec.optional_semantic_fields),
            "owner_receipt_fields": list(spec.owner_receipt_fields),
            "optional_owner_fields": list(spec.optional_owner_fields),
            "reasoned_not_applicable_fields": list(
                spec.reasoned_not_applicable_fields
            ),
            "forbidden_derived_overrides": list(spec.derived_fields),
        },
        "next_action": (
            {"kind": "stop", "reason": model.get("stop_reason")}
            if blocked
            else {
                "kind": "submit_exact_inputs",
                "command": "stage submit",
                "owner_result_required": bool(spec.owner_receipt_fields),
                "semantic_required": bool(spec.semantic_fields),
            }
        ),
    }
    preparation["preparation_id"] = (
        "stageprep-" + canonical_sha256(preparation_identity(preparation))[:32]
    )
    preparation["compiler_metrics"] = {
        **context_metrics,
        "executor_kind": spec.executor_kind,
        "model_call_required": bool(spec.semantic_fields),
        "semantic_field_count": len(spec.semantic_fields),
        "owner_field_count": len(spec.owner_receipt_fields),
        "context_bytes": context_binding["size_bytes"],
        "work_order_bytes": work_order_binding["size_bytes"],
        "model_authored_mechanical_bytes": 0,
        "inline_payload_bytes": 0,
    }
    return preparation


def _load_bound_material(
    root: Path, preparation: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    cycle_id = str(preparation["cycle_id"])
    context = load_compiler_artifact(
        root, cycle_id, preparation["context_binding"], "context"
    )
    work_order = load_compiler_artifact(
        root, cycle_id, preparation["work_order_binding"], "work_order"
    )
    for value, label in ((context, "context"), (work_order, "work_order")):
        if value.get("cycle_id") != cycle_id or value.get("target") != preparation["target"]:
            raise ValueError(f"{label} binding scope does not match preparation")
        if value.get("state_fingerprint") != preparation["state_fingerprint"]:
            raise ValueError(f"{label} state fingerprint does not match preparation")
    if work_order.get("context_binding") != preparation["context_binding"]:
        raise ValueError("work_order context binding does not match preparation")
    return context, work_order


def current_v2_context(
    root: Path,
    preparation: dict[str, Any],
    *,
    max_files: int,
    max_paths: int,
) -> tuple[dict[str, Any], dict[str, Any], str]:
    spec = TARGET_COMPILE_SPECS[str(preparation["target"])]
    full, model, _metrics = collect_selected_context(
        root,
        str(preparation["cycle_id"]),
        spec,
        max_files=max_files,
        max_paths=max_paths,
    )
    return full, model, selected_state_fingerprint(model, spec.dependency_selectors)


def _pair(ref: str | None, digest: str | None, label: str) -> tuple[str, str] | None:
    if bool(ref) != bool(digest):
        raise ValueError(f"--{label}-ref and --{label}-sha256 must be supplied together")
    return (str(ref), str(digest)) if ref and digest else None


def require_v1_judgment(
    judgment: dict[str, Any] | None, *exact_bindings: str | None
) -> dict[str, Any]:
    if any(value is not None for value in exact_bindings):
        raise ValueError("exact stage input bindings require a v2 preparation")
    if judgment is None:
        raise ValueError("v1 stage submission requires inline judgment JSON")
    return judgment


def _exact_judgment(
    root: Path,
    preparation: dict[str, Any],
    *,
    owner_result_ref: str | None,
    owner_result_sha256: str | None,
    semantic_ref: str | None,
    semantic_sha256: str | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    target, cycle_id = str(preparation["target"]), str(preparation["cycle_id"])
    spec = TARGET_COMPILE_SPECS[target]
    owner_pair = _pair(owner_result_ref, owner_result_sha256, "owner-result")
    semantic_pair = _pair(semantic_ref, semantic_sha256, "semantic")
    if bool(spec.owner_receipt_fields) != bool(owner_pair):
        raise ValueError("v2 stage requires one exact owner result binding")
    if bool(spec.semantic_fields) != bool(semantic_pair):
        raise ValueError("v2 semantic binding presence does not match field origin contract")
    judgment: dict[str, Any] = {}
    bindings: dict[str, Any] = {}
    if owner_pair:
        loaded, binding = load_stage_input(
            root,
            *owner_pair,
            cycle_id=cycle_id,
            target=target,
            input_kind="owner_result",
        )
        owner = loaded["owner_result"]
        for field, expected in (preparation.get("derived_values") or {}).items():
            if field in owner and owner[field] != expected:
                raise ValueError(f"owner result conflicts with derived field: {field}")
            owner.pop(field, None)
        judgment.update(loaded)
        bindings["owner_result_binding"] = binding
    if semantic_pair:
        loaded, binding = load_stage_input(
            root,
            *semantic_pair,
            cycle_id=cycle_id,
            target=target,
            input_kind="semantic",
        )
        judgment.update(loaded)
        bindings["semantic_binding"] = binding
    return judgment, bindings


def _usage(
    root: Path,
    preparation: dict[str, Any],
    ref: str | None,
    digest: str | None,
) -> tuple[dict[str, int], dict[str, Any] | None]:
    pair = _pair(ref, digest, "usage")
    if pair is None:
        return {}, None
    return load_usage_observation(
        root,
        *pair,
        cycle_id=str(preparation["cycle_id"]),
        target=str(preparation["target"]),
    )


def submit_v2(
    root: Path,
    preparation: dict[str, Any],
    *,
    task_id: str | None,
    owner_result_ref: str | None,
    owner_result_sha256: str | None,
    semantic_ref: str | None,
    semantic_sha256: str | None,
    usage_ref: str | None,
    usage_sha256: str | None,
    mode: str,
    apply: bool,
    max_files: int,
    max_paths: int,
) -> dict[str, Any]:
    cycle_id, target = str(preparation["cycle_id"]), str(preparation["target"])
    _context_artifact, work_order = _load_bound_material(root, preparation)
    replay = published_preparation(root, cycle_id, preparation)
    full, _model, current_fingerprint = current_v2_context(
        root, preparation, max_files=max_files, max_paths=max_paths
    )
    if current_fingerprint != preparation["state_fingerprint"]:
        return stale_preparation_result(preparation, current_fingerprint)
    if not replay:
        preparation = require_expected_preparation(
            preparation,
            prepare_v2(
                root,
                cycle_id,
                target,
                str(preparation["workflow_mode"]),
                task_id,
                max_files=max_files,
                max_paths=max_paths,
            ),
        )
    judgment, input_bindings = _exact_judgment(
        root,
        preparation,
        owner_result_ref=owner_result_ref,
        owner_result_sha256=owner_result_sha256,
        semantic_ref=semantic_ref,
        semantic_sha256=semantic_sha256,
    )
    usage, usage_binding = _usage(
        root, preparation, usage_ref, usage_sha256
    )
    if usage_binding is not None:
        input_bindings["usage_binding"] = usage_binding
    result = ResultBuilder().build(preparation, judgment)
    digest = canonical_sha256(result)
    existing = existing_publication(root, cycle_id, target, preparation, result, digest)
    if existing is not None:
        return _output(
            preparation,
            judgment,
            result,
            digest,
            input_bindings,
            usage=usage,
            existing=existing,
        )
    if replay:
        return replay_mismatch(preparation)
    transition = validate_submission_transition(full, preparation, work_order)
    if transition["status"] == "block":
        return {
            "status": "block",
            "stop_reason": "blocked_transition",
            "preparation_id": preparation["preparation_id"],
            "transition_validation": transition,
            "applied": False,
        }
    validation = validate_result(target, result, mode, full)
    output = _output(
        preparation,
        judgment,
        result,
        digest,
        input_bindings,
        usage=usage,
        validation=validation,
    )
    if not apply or validation["status"] == "block":
        return output
    publication = publish_result(root, cycle_id, preparation, result, digest)
    output.update(
        {
            "applied": True,
            "event": publication["event"],
            "event_duplicate": publication["event_duplicate"],
            "ledger_path": publication["ledger_path"],
        }
    )
    return output


def _output(
    preparation: dict[str, Any],
    judgment: dict[str, Any],
    result: dict[str, Any],
    digest: str,
    input_bindings: dict[str, Any],
    *,
    usage: dict[str, int] | None = None,
    validation: dict[str, Any] | None = None,
    existing: dict[str, Any] | None = None,
) -> dict[str, Any]:
    validation = validation or {
        "status": "ok",
        "target": preparation["target"],
        "mode": "replay",
        "findings": [],
        "missing_fields": [],
    }
    projection = {
        key: result.get(key)
        for key in OUTPUT_SCALARS
        if result.get(key) is None
        or isinstance(result.get(key), (bool, int, float))
        or (
            isinstance(result.get(key), str)
            and len(result.get(key).encode("utf-8")) <= 256
        )
    }
    root_fields = {
        "status": validation["status"],
        "stop_reason": "rejected_result" if validation["status"] == "block" else None,
        "preparation_id": preparation["preparation_id"],
        "result_projection": projection,
        "result_contract": validation,
        "result_artifact_sha256": digest,
        "applied": existing is not None,
        "input_bindings": input_bindings,
        "compiler_metrics": {
            "semantic_leaf_count": leaf_count(judgment.get("semantic") or {}),
            "owner_result_leaf_count": leaf_count(judgment.get("owner_result") or {}),
            "compiled_result_leaf_count": leaf_count(result),
            "model_authored_mechanical_bytes": 0,
            "inline_payload_bytes": 0,
            **(usage or {}),
        },
    }
    if existing:
        root_fields.update(
            {
                "result_artifact_ref": existing["result_artifact_ref"],
                "event": existing["event"],
                "event_duplicate": True,
                "ledger_path": existing["ledger_path"],
            }
        )
    else:
        root_fields["result_artifact_ref"] = (
            f".task/cycle/{preparation['cycle_id']}/packets/"
            f"result-{preparation['target']}-{digest}.json"
        )
    return root_fields


__all__ = ["prepare_v2", "require_v1_judgment", "submit_v2"]
