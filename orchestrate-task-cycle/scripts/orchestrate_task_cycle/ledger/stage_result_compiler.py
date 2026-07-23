"""Deterministic derivation and locked validation for compiled stage results."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from .result_hydration import (
    COMPACT_COMPILER_METRIC_FIELDS,
    hydrate_result_event,
    project_result_scalars,
)
from .stage_result_validation import (
    INPUT_BINDING_FIELDS,
    _require_bound_collection_limits,
    _validate_binding_presence,
    _validate_collection_limits,
    _validate_full_result_gates,
    _validate_preparation,
    preflight_stage_result_material,
    preflight_stage_result_publication,
)
from .support import canonical_json_bytes


DERIVATION_SCHEMA_VERSION = 1
DERIVATION_FIELDS = {
    "schema_version",
    "preparation",
    "result",
    "result_ref",
    "result_sha256",
    "compiler_metrics",
    "input_bindings",
    "collection_limits",
    "previous_events_sha256",
}
def _canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _compact_metrics(value: dict[str, Any] | None) -> dict[str, Any]:
    metrics: dict[str, Any] = {}
    for key, item in (value or {}).items():
        if key not in COMPACT_COMPILER_METRIC_FIELDS or item is None:
            continue
        if isinstance(item, bool):
            metrics[key] = item
        elif isinstance(item, int) and item >= 0:
            metrics[key] = item
        elif isinstance(item, str) and len(item.encode("utf-8")) <= 512:
            metrics[key] = item
    return metrics


def previous_events_sha256(events: list[dict[str, Any]]) -> str:
    """Bind the exact raw ledger prefix validated by the submitting producer."""

    return hashlib.sha256(canonical_json_bytes(events)).hexdigest()


def derive_stage_result_event(
    preparation: dict[str, Any],
    result: dict[str, Any],
    result_ref: str,
    result_sha256: str,
    compiler_metrics: dict[str, Any] | None = None,
    input_bindings: dict[str, Any] | None = None,
    *,
    input_bindings_sha256: str | None = None,
) -> dict[str, Any]:
    """Render the only accepted compact result envelope from semantic inputs."""

    from ..stage.contracts import preparation_binding_sha256

    preparation_binding = preparation_binding_sha256(preparation)
    event_identity = {
        "preparation_id": preparation["preparation_id"],
        "result_sha256": result_sha256,
    }
    event_id = (
        "stage-"
        + str(preparation["target"])
        + "-"
        + _canonical_sha256(event_identity)[:32]
    )
    if preparation.get("schema_version") == 1:
        legacy = dict(result)
        legacy.update(
            {
                "step": preparation["target"],
                "status": "completed",
                "event_id": event_id,
                "reason": "validated compiled stage result",
                "preparation_id": preparation["preparation_id"],
                "preparation_binding_sha256": preparation_binding,
                "result_artifact_ref": result_ref,
                "result_artifact_sha256": result_sha256,
            }
        )
        artifacts = list(result.get("artifacts") or [])
        if result_ref not in artifacts:
            artifacts.append(result_ref)
        legacy["artifacts"] = artifacts
        return legacy
    payload = canonical_json_bytes(result) + b"\n"
    raw_sha256 = hashlib.sha256(payload).hexdigest()
    scalars = project_result_scalars(result)
    event = {
        "format_version": 2,
        "step": preparation["target"],
        "status": "completed",
        "event_id": event_id,
        "reason": "validated compiled stage result",
        "preparation_id": preparation["preparation_id"],
        "preparation_binding_sha256": preparation_binding,
        "input_bindings_sha256": (
            input_bindings_sha256 or _canonical_sha256(input_bindings or {})
        ),
        "result_artifact_ref": result_ref,
        "result_artifact_sha256": result_sha256,
        "result_artifact_raw_sha256": raw_sha256,
        "result_artifact_binding": {
            "ref": result_ref,
            "sha256": raw_sha256,
            "size_bytes": len(payload),
            "body_sha256": result_sha256,
        },
        "compiler_metrics": _compact_metrics(compiler_metrics),
        "result_projection": scalars,
        "artifacts": [result_ref],
        **scalars,
    }
    commit_binding = (input_bindings or {}).get(
        "deterministic_commit_binding"
    )
    if commit_binding is not None:
        event["deterministic_commit_binding"] = dict(commit_binding)
    event["compiler_metrics"]["compact_payload_bytes"] = (
        len(canonical_json_bytes(event)) + 1
    )
    return event


def make_stage_result_derivation(
    preparation: dict[str, Any],
    result: dict[str, Any],
    result_ref: str,
    result_sha256: str,
    compiler_metrics: dict[str, Any] | None,
    input_bindings: dict[str, Any] | None,
    collection_limits: dict[str, Any],
    previous_events: list[dict[str, Any]],
) -> dict[str, Any]:
    validated = _validate_preparation(preparation)
    if not isinstance(result, dict):
        raise ValueError("compiled stage result must be an object")
    if _canonical_sha256(result) != result_sha256:
        raise ValueError("compiled stage result digest does not match its body")
    bindings = input_bindings or {}
    if not isinstance(bindings, dict) or set(bindings) - set(INPUT_BINDING_FIELDS):
        raise ValueError("compiled stage result input bindings are not registered")
    _validate_binding_presence(validated, bindings)
    limits = _validate_collection_limits(collection_limits)
    _require_bound_collection_limits(validated, limits)
    return {
        "schema_version": DERIVATION_SCHEMA_VERSION,
        "preparation": validated,
        "result": result,
        "result_ref": result_ref,
        "result_sha256": result_sha256,
        "compiler_metrics": _compact_metrics(compiler_metrics),
        "input_bindings": bindings,
        "collection_limits": limits,
        "previous_events_sha256": previous_events_sha256(previous_events),
    }


def validate_derivation_shape(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != DERIVATION_FIELDS:
        raise ValueError("compiled stage result derivation material is not closed")
    if value.get("schema_version") != DERIVATION_SCHEMA_VERSION:
        raise ValueError("compiled stage result derivation schema is unsupported")
    _validate_preparation(value.get("preparation"))
    if not isinstance(value.get("result"), dict):
        raise ValueError("compiled stage result derivation lacks a result object")
    bindings = value.get("input_bindings")
    if not isinstance(bindings, dict) or set(bindings) - set(INPUT_BINDING_FIELDS):
        raise ValueError("compiled stage result derivation input bindings are invalid")
    _validate_binding_presence(value["preparation"], bindings)
    limits = _validate_collection_limits(value.get("collection_limits"))
    _require_bound_collection_limits(value["preparation"], limits)
    return value


def validate_stage_result_derivation(
    root: Path,
    cycle_id: str,
    event: dict[str, Any],
    derivation: dict[str, Any],
    previous_events: list[dict[str, Any]],
) -> None:
    """Reopen all exact bindings and rederive the envelope under the ledger lock."""

    value = validate_derivation_shape(derivation)
    preparation = value["preparation"]
    result = value["result"]
    limits = _validate_collection_limits(value["collection_limits"])
    if preparation.get("cycle_id") != cycle_id:
        raise ValueError("compiled stage result preparation belongs to another cycle")
    if value["previous_events_sha256"] != previous_events_sha256(previous_events):
        raise ValueError("compiled stage result ledger precondition changed before append")
    _validate_full_result_gates(
        root,
        preparation,
        result,
        value["input_bindings"],
        limits,
        previous_events,
    )
    expected = derive_stage_result_event(
        preparation,
        result,
        str(value["result_ref"]),
        str(value["result_sha256"]),
        value["compiler_metrics"],
        value["input_bindings"],
    )
    semantic = {
        key: item
        for key, item in event.items()
        if key not in {"event_kind", "producer_kind"}
    }
    if canonical_json_bytes(semantic) != canonical_json_bytes(expected):
        raise ValueError("compiled stage result differs from exact compiler derivation")
    hydrate_result_event(root, cycle_id, event)


__all__ = [
    "derive_stage_result_event",
    "make_stage_result_derivation",
    "preflight_stage_result_material",
    "preflight_stage_result_publication",
    "previous_events_sha256",
    "validate_derivation_shape",
    "validate_stage_result_derivation",
]
