"""Write-free transition and result gates for deterministic renderers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .artifact_store import project_stage_input
from .builder import ResultBuilder
from .contracts import canonical_sha256
from .executor_registry import executor_spec
from .native_results import normalize_native_owner_result
from .submission_output import build_submission_output


def _preflight(
    root: Path,
    preparation: dict[str, Any],
    prediction: dict[str, Any],
    *,
    mode: str,
    max_files: int,
    max_paths: int,
) -> dict[str, Any]:
    """Validate a pure renderer projection with the registered hard gates."""

    target = str(preparation["target"])
    if executor_spec(target).executor_kind != "deterministic":
        raise ValueError("deterministic preflight requires a deterministic target")
    from .deterministic_dispatch import predict_deterministic
    from .gates import validate_submission_transition
    from ..result_contract.api import validate as validate_result

    current = predict_deterministic(
        root,
        preparation,
        max_files=max_files,
        max_paths=max_paths,
    )
    if current.get("status") == "block":
        return current
    compared = ("raw_owner_result", "effect_plan")
    if canonical_sha256(
        {key: current.get(key) for key in compared}
    ) != canonical_sha256(
        {key: prediction.get(key) for key in compared}
    ):
        raise ValueError(
            "deterministic prediction changed before preflight"
        )
    raw_owner_result = current["raw_owner_result"]
    full_context = current["full_context"]
    _wrapper, binding, _payload = project_stage_input(
        root,
        str(preparation["cycle_id"]),
        target,
        "owner_result",
        raw_owner_result,
        preparation=preparation,
    )
    owner = dict(
        normalize_native_owner_result(
            target,
            raw_owner_result,
            root=root,
            cycle_id=str(preparation["cycle_id"]),
            source_ref=str(binding["ref"]),
            publish_auxiliary=False,
            include_auxiliary_binding=False,
        )
    )
    for field, expected in (preparation.get("derived_values") or {}).items():
        if field in owner and owner[field] != expected:
            raise ValueError(
                f"deterministic result conflicts with derived field: {field}"
            )
        owner.pop(field, None)
    judgment = {"owner_result": owner}
    result = ResultBuilder().build(preparation, judgment)
    transition = validate_submission_transition(
        full_context, preparation, None
    )
    if transition["status"] == "block":
        return {
            "status": "block",
            "stop_reason": "blocked_transition",
            "preparation_id": preparation["preparation_id"],
            "transition_validation": transition,
            "applied": False,
        }
    digest = canonical_sha256(result)
    validation = validate_result(target, result, mode, full_context)
    output = build_submission_output(
        preparation,
        judgment,
        result,
        digest,
        {"owner_result_binding": binding},
        validation=validation,
    )
    output["compiler_metrics"]["precondition_validation_status"] = (
        "exact_precondition"
    )
    return {
        "status": validation["status"],
        "output": output,
        "result": result,
        "result_sha256": digest,
        "owner_result_binding": binding,
    }


__all__: list[str] = []
