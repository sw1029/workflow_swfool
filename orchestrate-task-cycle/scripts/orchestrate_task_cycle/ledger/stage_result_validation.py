"""No-write reconstruction and mutable-state gates for stage results."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from .support import canonical_json_bytes


INPUT_BINDING_FIELDS = {
    "owner_result_binding": {"ref", "sha256", "size_bytes"},
    "semantic_binding": {"ref", "sha256", "size_bytes"},
    "routing_binding": {"ref", "sha256", "size_bytes"},
    "usage_binding": {"ref", "sha256", "size_bytes", "schema_version"},
    "deterministic_commit_binding": {"ref", "sha256", "size_bytes"},
}


def _canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _validate_preparation(value: Any) -> dict[str, Any]:
    from ..stage.contracts import validate_preparation

    return validate_preparation(value)


def _validate_collection_limits(value: Any) -> dict[str, int]:
    if not isinstance(value, dict) or set(value) != {"max_files", "max_paths"}:
        raise ValueError("compiled stage result collection limits are not closed")
    if any(
        isinstance(value[key], bool)
        or not isinstance(value[key], int)
        or value[key] < 1
        for key in ("max_files", "max_paths")
    ):
        raise ValueError("compiled stage result collection limits must be positive")
    return {"max_files": value["max_files"], "max_paths": value["max_paths"]}


def _require_bound_collection_limits(
    preparation: dict[str, Any],
    limits: dict[str, int],
) -> None:
    metrics = preparation.get("compiler_metrics")
    bound = metrics.get("collection_limits") if isinstance(metrics, dict) else None
    if bound != limits:
        raise ValueError(
            "compiled stage result collection limits differ from preparation"
        )


def _validate_binding_presence(
    preparation: dict[str, Any], bindings: dict[str, Any]
) -> None:
    from ..stage.executor_registry import executor_spec
    from ..stage.specs import TARGET_COMPILE_SPECS

    target = str(preparation["target"])
    specification = TARGET_COMPILE_SPECS[target]
    executor = executor_spec(target)
    required = {
        key
        for key, needed in (
            ("owner_result_binding", bool(specification.owner_receipt_fields)),
            ("semantic_binding", bool(specification.semantic_fields)),
            ("routing_binding", executor.routing_required),
        )
        if needed
    }
    if executor.executor_kind == "deterministic":
        if preparation.get("schema_version") != 3:
            raise ValueError(
                "deterministic stage result requires a schema-v3 preparation"
            )
        required.add("deterministic_commit_binding")
    actual = set(bindings)
    if not required <= actual:
        raise ValueError(
            "compiled stage result omits required exact input bindings: "
            + ",".join(sorted(required - actual))
        )
    allowed = required | (
        {"usage_binding"} if executor.executor_kind != "deterministic" else set()
    )
    if actual - allowed:
        raise ValueError(
            "compiled stage result supplies inapplicable input bindings: "
            + ",".join(sorted(actual - allowed))
        )


def _validate_transition(
    preparation: dict[str, Any], previous_events: list[dict[str, Any]]
) -> None:
    from ..transition.constants import BOOTSTRAP_ORDER, ORDER, TERMINAL_OK

    order = (
        BOOTSTRAP_ORDER
        if preparation.get("workflow_mode") == "bootstrap"
        else ORDER
    )
    target = str(preparation["target"])
    if target not in order:
        raise ValueError("compiled stage result target is outside the workflow order")
    latest = {str(event.get("step") or ""): event for event in previous_events}
    missing = [
        step
        for step in order[: order.index(target)]
        if str((latest.get(step) or {}).get("status") or "").lower()
        not in TERMINAL_OK
    ]
    if missing:
        raise ValueError(
            "compiled stage result transition lacks completed predecessors: "
            + ",".join(missing)
        )


def _reopen_and_rebuild_result(
    root: Path,
    preparation: dict[str, Any],
    bindings: dict[str, Any],
    *,
    max_files: int,
    max_paths: int,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any] | None]:
    from ..stage.builder import ResultBuilder
    from ..stage.v2_service import _exact_judgment, _usage

    _validate_binding_presence(preparation, bindings)
    for key, binding in bindings.items():
        expected_fields = INPUT_BINDING_FIELDS[key]
        if not isinstance(binding, dict) or set(binding) != expected_fields:
            raise ValueError(f"compiled stage result {key} fields are not closed")
    owner = bindings.get("owner_result_binding") or {}
    semantic = bindings.get("semantic_binding") or {}
    routing_binding = bindings.get("routing_binding") or {}
    judgment, reopened, routing = _exact_judgment(
        root,
        preparation,
        owner_result_ref=owner.get("ref"),
        owner_result_sha256=owner.get("sha256"),
        semantic_ref=semantic.get("ref"),
        semantic_sha256=semantic.get("sha256"),
        routing_ref=routing_binding.get("ref"),
        routing_sha256=routing_binding.get("sha256"),
        predict_native_artifacts=True,
    )
    usage_binding = bindings.get("usage_binding") or {}
    _usage_value, reopened_usage = _usage(
        root,
        preparation,
        usage_binding.get("ref"),
        usage_binding.get("sha256"),
    )
    if reopened_usage is not None:
        reopened["usage_binding"] = reopened_usage
    result = ResultBuilder().build(preparation, judgment)
    commit_binding = bindings.get("deterministic_commit_binding")
    if commit_binding is not None:
        from ..stage.deterministic_receipt import (
            validate_deterministic_commit_receipt,
        )

        reopened["deterministic_commit_binding"] = (
            validate_deterministic_commit_receipt(
                root,
                preparation,
                _canonical_sha256(result),
                reopened["owner_result_binding"],
                commit_binding,
                max_files=max_files,
                max_paths=max_paths,
                verify_current=True,
            )
        )
    if canonical_json_bytes(reopened) != canonical_json_bytes(bindings):
        raise ValueError("compiled stage result inputs do not reopen exactly")
    return result, judgment, routing


def preflight_stage_result_material(
    root: Path,
    preparation: dict[str, Any],
    result: dict[str, Any],
    input_bindings: dict[str, Any] | None,
    collection_limits: dict[str, Any],
) -> None:
    """Reject non-reconstructable material before result CAS mutation."""

    validated = _validate_preparation(preparation)
    bindings = input_bindings or {}
    if not isinstance(bindings, dict) or set(bindings) - set(INPUT_BINDING_FIELDS):
        raise ValueError("compiled stage result input bindings are not registered")
    limits = _validate_collection_limits(collection_limits)
    _require_bound_collection_limits(validated, limits)
    rebuilt, _judgment, _routing = _reopen_and_rebuild_result(
        root,
        validated,
        bindings,
        max_files=limits["max_files"],
        max_paths=limits["max_paths"],
    )
    if canonical_json_bytes(rebuilt) != canonical_json_bytes(result):
        raise ValueError(
            "compiled stage result does not match exact input reconstruction"
        )


def _validate_full_result_gates(
    root: Path,
    preparation: dict[str, Any],
    result: dict[str, Any],
    bindings: dict[str, Any],
    limits: dict[str, int],
    previous_events: list[dict[str, Any]],
) -> None:
    """Run every mutable-state result gate without publishing any bytes."""

    _validate_transition(preparation, previous_events)
    rebuilt, judgment, routing = _reopen_and_rebuild_result(
        root,
        preparation,
        bindings,
        max_files=limits["max_files"],
        max_paths=limits["max_paths"],
    )
    if canonical_json_bytes(rebuilt) != canonical_json_bytes(result):
        raise ValueError(
            "compiled stage result does not match exact input reconstruction"
        )
    from ..result_contract.api import validate as validate_result
    from ..stage.freshness import (
        evaluate_preparation_freshness,
        validate_owner_post_effect_claims,
    )
    from ..stage.gates import validate_submission_transition

    freshness = evaluate_preparation_freshness(
        root,
        preparation,
        max_files=limits["max_files"],
        max_paths=limits["max_paths"],
        allow_post_effect=True,
    )
    if freshness.get("status") == "block":
        raise ValueError("compiled stage result preparation is stale")
    claim_block = validate_owner_post_effect_claims(
        preparation,
        freshness,
        judgment.get("owner_result"),
    )
    if claim_block is not None:
        raise ValueError(
            "compiled stage result owner post-effect claims do not match workspace"
        )
    full = freshness["full_context"]
    work_order = freshness["work_order"]
    transition = validate_submission_transition(
        full,
        preparation,
        routing if routing is not None else work_order,
    )
    if transition.get("status") == "block":
        raise ValueError("compiled stage result transition validation blocked")
    validation = validate_result(
        str(preparation["target"]), result, "block", full
    )
    if validation.get("status") == "block":
        raise ValueError("compiled stage result contract validation blocked")


def preflight_stage_result_publication(
    root: Path,
    cycle_id: str,
    preparation: dict[str, Any],
    result: dict[str, Any],
    input_bindings: dict[str, Any] | None,
    collection_limits: dict[str, Any],
    previous_events: list[dict[str, Any]],
) -> None:
    """Run the complete locked publication gate before result CAS mutation."""

    validated = _validate_preparation(preparation)
    if validated.get("cycle_id") != cycle_id:
        raise ValueError("compiled stage result preparation belongs to another cycle")
    bindings = input_bindings or {}
    if not isinstance(bindings, dict) or set(bindings) - set(INPUT_BINDING_FIELDS):
        raise ValueError("compiled stage result input bindings are not registered")
    limits = _validate_collection_limits(collection_limits)
    _require_bound_collection_limits(validated, limits)
    _validate_full_result_gates(
        root,
        validated,
        result,
        bindings,
        limits,
        previous_events,
    )


__all__ = [
    "preflight_stage_result_material",
    "preflight_stage_result_publication",
]
