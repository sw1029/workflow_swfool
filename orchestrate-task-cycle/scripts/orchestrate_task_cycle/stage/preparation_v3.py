"""Preparation-v2/v3 compiler with deterministic machine-input specialization."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .artifact_store import compiler_artifact_binding, merge_compiler_io_metrics
from .contracts import (
    PREPARATION_KIND,
    PREPARATION_SCHEMA_VERSION_V2,
    PREPARATION_SCHEMA_VERSION_V3,
    canonical_sha256,
    preparation_identity,
)
from .executor_registry import allowed_post_effect_selectors, executor_spec
from .specs import TARGET_COMPILE_SPECS
from .v2_context import (
    collect_selected_context,
    render_machine_input,
    render_work_order,
    selected_state_fingerprint,
)


def _stable_binding(value: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value[key]
        for key in ("artifact_type", "ref", "sha256", "size_bytes")
    }


def _preparation_bindings(
    root: Path,
    cycle_id: str,
    target: str,
    workflow_mode: str,
    model: dict[str, Any],
    fingerprint: str,
    spec: Any,
    context_metrics: dict[str, Any],
    precondition_fingerprints: dict[str, str],
    *,
    schema_version: int,
    persist: bool,
    origin_id: str | None = None,
    origin_preparation: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], tuple[dict[str, Any], ...]]:
    registered = executor_spec(target)
    if (
        schema_version == PREPARATION_SCHEMA_VERSION_V3
        and registered.executor_kind == "deterministic"
    ):
        machine_input = render_machine_input(
            cycle_id,
            target,
            workflow_mode,
            model,
            fingerprint,
            context_metrics,
            precondition_fingerprints,
        )
        raw_binding = compiler_artifact_binding(
            root,
            cycle_id,
            "machine_input",
            machine_input,
            persist=persist,
            origin_id=origin_id,
            origin_preparation=origin_preparation,
        )
        return (
            {"machine_input_binding": _stable_binding(raw_binding)},
            (raw_binding["compiler_io_receipt"],),
        )
    context = {
        "schema_version": 1,
        "artifact_kind": "orchestrate_stage_context",
        "cycle_id": cycle_id,
        "target": target,
        "dependency_selectors": list(spec.dependency_selectors),
        "state_fingerprint": fingerprint,
        "model_context": model,
        "collection_limits": context_metrics["collection_limits"],
    }
    if schema_version == PREPARATION_SCHEMA_VERSION_V3:
        context.update(
            {
                "context_metrics": context_metrics,
                "precondition_fingerprints": precondition_fingerprints,
            }
        )
    raw_context_binding = compiler_artifact_binding(
        root,
        cycle_id,
        "context",
        context,
        persist=persist,
        origin_id=origin_id,
        origin_preparation=origin_preparation,
    )
    context_binding = _stable_binding(raw_context_binding)
    work_order = render_work_order(
        cycle_id,
        target,
        workflow_mode,
        spec,
        model,
        fingerprint,
        context_binding,
        (
            precondition_fingerprints
            if schema_version == PREPARATION_SCHEMA_VERSION_V3
            else None
        ),
    )
    raw_work_order_binding = compiler_artifact_binding(
        root,
        cycle_id,
        "work_order",
        work_order,
        persist=persist,
        origin_id=origin_id,
        origin_preparation=origin_preparation,
    )
    return (
        {
            "context_binding": context_binding,
            "work_order_binding": _stable_binding(raw_work_order_binding),
        },
        (
            raw_context_binding["compiler_io_receipt"],
            raw_work_order_binding["compiler_io_receipt"],
        ),
    )


def _derived_values(
    target: str, cycle_id: str, task_id: str | None, model: dict[str, Any]
) -> dict[str, Any]:
    spec = TARGET_COMPILE_SPECS[target]
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
    return {
        field: candidates[field]
        for field in spec.derived_fields
        if candidates.get(field) is not None
    }


def _result_contract(spec: Any) -> dict[str, Any]:
    return {
        "required_fields": list(spec.required_fields),
        "derived_fields": list(spec.derived_fields),
        "semantic_fields": list(spec.semantic_fields),
        "optional_semantic_fields": list(spec.optional_semantic_fields),
        "owner_receipt_fields": list(spec.owner_receipt_fields),
        "optional_owner_fields": list(spec.optional_owner_fields),
        "reasoned_not_applicable_fields": list(spec.reasoned_not_applicable_fields),
        "forbidden_derived_overrides": list(spec.derived_fields),
    }


def render_preparation(
    cycle_id: str,
    target: str,
    workflow_mode: str,
    task_id: str | None,
    model: dict[str, Any],
    context_metrics: dict[str, Any],
    bindings: dict[str, Any],
    precondition_fingerprints: dict[str, str],
    *,
    schema_version: int,
    compiler_io_receipts: tuple[dict[str, Any], ...] = (),
) -> dict[str, Any]:
    """Render one closed preparation from already-bound compiler inputs."""

    spec = TARGET_COMPILE_SPECS[target]
    registered = executor_spec(target)
    blocked = model.get("projection_status") == "block"
    deterministic = registered.executor_kind == "deterministic"
    preparation: dict[str, Any] = {
        "schema_version": schema_version,
        "artifact_kind": PREPARATION_KIND,
        "cycle_id": cycle_id,
        "target": target,
        "workflow_mode": workflow_mode,
        "executor_kind": spec.executor_kind,
        "model_call_required": bool(spec.semantic_fields),
        "executor_spec": registered.projection(),
        "state_fingerprint": selected_state_fingerprint(
            model, spec.dependency_selectors
        ),
        "fingerprint_roles": list(spec.dependency_selectors),
        **bindings,
        "derived_values": _derived_values(target, cycle_id, task_id, model),
        "result_contract": _result_contract(spec),
        "next_action": (
            {"kind": "stop", "reason": model.get("stop_reason")}
            if blocked
            else {
                "kind": "execute_deterministic"
                if deterministic
                else "submit_exact_inputs",
                "command": "stage execute" if deterministic else "stage submit",
                "owner_result_required": bool(spec.owner_receipt_fields),
                "semantic_required": bool(spec.semantic_fields),
            }
        ),
    }
    if schema_version == PREPARATION_SCHEMA_VERSION_V3:
        preparation.update(
            {
                "precondition_fingerprints": precondition_fingerprints,
                "allowed_post_effect_selectors": list(
                    allowed_post_effect_selectors(target)
                ),
            }
        )
    compiler_metrics = {
            **context_metrics,
            "executor_kind": spec.executor_kind,
            "model_call_required": bool(spec.semantic_fields),
            "semantic_field_count": len(spec.semantic_fields),
            "owner_field_count": len(spec.owner_receipt_fields),
            "context_bytes": (bindings.get("context_binding") or {}).get(
                "size_bytes", 0
            ),
            "work_order_bytes": (bindings.get("work_order_binding") or {}).get(
                "size_bytes", 0
            ),
            "machine_input_bytes": (
                bindings.get("machine_input_binding") or {}
            ).get("size_bytes", 0),
            "model_visible_bytes": (
                0
                if deterministic
                else (bindings.get("work_order_binding") or {}).get(
                    "size_bytes", 0
                )
            ),
            "model_authored_mechanical_bytes": 0,
            "model_authored_mechanical_bytes_origin": "field_origin_registry",
            "inline_payload_bytes": 0,
        }
    preparation["compiler_metrics"] = (
        merge_compiler_io_metrics(compiler_metrics, *compiler_io_receipts)
        if schema_version == PREPARATION_SCHEMA_VERSION_V3
        else compiler_metrics
    )
    preparation["preparation_id"] = (
        "stageprep-" + canonical_sha256(preparation_identity(preparation))[:32]
    )
    return preparation


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
    schema_version: int = PREPARATION_SCHEMA_VERSION_V2,
) -> dict[str, Any]:
    spec = TARGET_COMPILE_SPECS[target]
    registered = executor_spec(target)
    if registered.executor_kind != spec.executor_kind:
        raise RuntimeError("executor registry conflicts with field-origin registry")
    _full, model, observed_metrics = collect_selected_context(
        root, cycle_id, spec, max_files=max_files, max_paths=max_paths
    )
    context_metrics = dict(observed_metrics)
    precondition_fingerprints = context_metrics.pop("precondition_fingerprints")
    fingerprint = selected_state_fingerprint(model, spec.dependency_selectors)
    origin_bound_publication = schema_version in {
        PREPARATION_SCHEMA_VERSION_V2,
        PREPARATION_SCHEMA_VERSION_V3,
    }
    bindings, compiler_io_receipts = _preparation_bindings(
        root,
        cycle_id,
        target,
        workflow_mode,
        model,
        fingerprint,
        spec,
        context_metrics,
        precondition_fingerprints,
        schema_version=schema_version,
        persist=persist_compiler_artifacts and not origin_bound_publication,
    )
    preparation = render_preparation(
        cycle_id,
        target,
        workflow_mode,
        task_id,
        model,
        context_metrics,
        bindings,
        precondition_fingerprints,
        schema_version=schema_version,
        compiler_io_receipts=(
            compiler_io_receipts
            if schema_version == PREPARATION_SCHEMA_VERSION_V3
            else ()
        ),
    )
    if origin_bound_publication and persist_compiler_artifacts:
        persisted_bindings, persisted_receipts = _preparation_bindings(
            root,
            cycle_id,
            target,
            workflow_mode,
            model,
            fingerprint,
            spec,
            context_metrics,
            precondition_fingerprints,
            schema_version=schema_version,
            persist=True,
            origin_id=str(preparation["preparation_id"]),
            origin_preparation=preparation,
        )
        if persisted_bindings != bindings:
            raise RuntimeError("compiler artifact bindings changed during publication")
        preparation["compiler_metrics"] = merge_compiler_io_metrics(
            preparation["compiler_metrics"], *persisted_receipts
        )
        expected_id = "stageprep-" + canonical_sha256(
            preparation_identity(preparation)
        )[:32]
        if preparation["preparation_id"] != expected_id:
            raise RuntimeError("dynamic compiler I/O changed preparation identity")
    return preparation


__all__ = ["prepare_v2", "render_preparation"]
