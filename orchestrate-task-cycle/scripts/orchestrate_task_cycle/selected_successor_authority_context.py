"""Closed semantic inputs for selected-successor authority preparation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .selection_decision_store import (
    closed_object,
    normalize_binding,
    read_bound_bytes,
    read_bound_json,
)
from .selection_publication_store import (
    _canonical_json,
    _sha256_bytes,
    _successor_authority_evaluation_context_path,
    _successor_authority_request_context_path,
)
from .selected_successor_execution_support import ACTIONS


REQUEST_CONTEXT_KEYS = {
    "schema_version",
    "artifact_kind",
    "bundle",
    "actor_rank",
    "context",
    "context_content_sha256",
}
CONTEXT_KEYS = {
    "external_input_status",
    "goal_truth_status",
    "risk_acceptance_status",
    "design_selection_status",
    "external_input_evidence",
    "risk_acceptance_evidence",
    "design_selection_evidence",
}
EXTERNAL_INPUT = {
    "not_required",
    "available",
    "missing_supplyable",
    "missing_unsupplyable",
    "unverified",
}
GOAL_TRUTH = {"aligned", "blocked", "unverified"}
DECISION_STATUS = {"not_required", "resolved", "unresolved", "unverified"}
MAX_CONTEXT_BYTES = 64 * 1024
MAX_SEMANTIC_INPUT_BYTES = 1024 * 1024


def _sealed_content(value: dict[str, Any]) -> str:
    body = {key: item for key, item in value.items() if key != "context_content_sha256"}
    return _sha256_bytes(_canonical_json(body))


def _evidence(
    root: Path, value: Any, label: str, *, required: bool
) -> dict[str, str] | None:
    if value is None:
        if required:
            raise ValueError(f"{label} is required for the asserted status")
        return None
    if not required:
        raise ValueError(f"{label} must be null for the asserted status")
    binding = normalize_binding(value, label)
    read_bound_bytes(root, binding, label, max_bytes=MAX_SEMANTIC_INPUT_BYTES)
    return binding


def normalize_evaluation_semantics(root: Path, value: Any) -> dict[str, Any]:
    """Validate a semantic ceiling/envelope and its bounded exact source."""

    from manage_agent_authority.evaluation_context import (
        validate_recorded_evaluation_context,
    )

    if not isinstance(value, dict):
        raise ValueError("Authority evaluation context must be an object")
    try:
        normalized = validate_recorded_evaluation_context(value)
    except SystemExit as exc:
        raise ValueError(str(exc)) from exc
    source = normalize_binding(
        normalized["goal_autonomy_envelope"]["source_binding"],
        "goal autonomy source",
    )
    read_bound_bytes(
        root,
        source,
        "goal autonomy source",
        max_bytes=MAX_SEMANTIC_INPUT_BYTES,
    )
    return normalized


def normalize_request_semantics(root: Path, value: Any) -> dict[str, Any]:
    """Validate the four semantic axes and their exact evidence bindings."""

    root = root.expanduser().resolve(strict=True)
    context = closed_object(value, CONTEXT_KEYS, "request context")
    if (
        context.get("external_input_status") not in EXTERNAL_INPUT
        or context.get("goal_truth_status") not in GOAL_TRUTH
        or context.get("risk_acceptance_status") not in DECISION_STATUS
        or context.get("design_selection_status") not in DECISION_STATUS
    ):
        raise ValueError("Authority request context integrity failed")
    return {
        "external_input_status": context["external_input_status"],
        "goal_truth_status": context["goal_truth_status"],
        "risk_acceptance_status": context["risk_acceptance_status"],
        "design_selection_status": context["design_selection_status"],
        "external_input_evidence": _evidence(
            root,
            context["external_input_evidence"],
            "external-input evidence",
            required=context["external_input_status"]
            in {"available", "missing_supplyable", "missing_unsupplyable"},
        ),
        "risk_acceptance_evidence": _evidence(
            root,
            context["risk_acceptance_evidence"],
            "risk-acceptance evidence",
            required=context["risk_acceptance_status"] == "resolved",
        ),
        "design_selection_evidence": _evidence(
            root,
            context["design_selection_evidence"],
            "design-selection evidence",
            required=context["design_selection_status"] == "resolved",
        ),
    }


def load_request_context(
    root: Path,
    binding_value: Any,
    bundle_binding_value: Any,
) -> tuple[dict[str, str], dict[str, Any], dict[str, Any], str]:
    """Load one exact, bundle-bound semantic request context."""

    root = root.expanduser().resolve(strict=True)
    binding = normalize_binding(
        binding_value, "selected-successor authority request context"
    )
    bundle_binding = normalize_binding(
        bundle_binding_value, "selected-successor authority context bundle"
    )
    path, raw = read_bound_bytes(
        root,
        binding,
        "selected-successor authority request context",
        max_bytes=MAX_CONTEXT_BYTES,
    )
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(
            "Selected-successor authority request context is unreadable"
        ) from exc
    value = closed_object(parsed, REQUEST_CONTEXT_KEYS, "authority request context")
    if raw != _canonical_json(value):
        raise ValueError("Authority request context must be canonical JSON")
    context = closed_object(value.get("context"), CONTEXT_KEYS, "request context")
    if (
        value.get("schema_version") != 1
        or value.get("artifact_kind") != "selected_successor_authority_request_context"
        or value.get("bundle") != bundle_binding
        or value.get("actor_rank") not in {"S0", "S1", "S2", "S3", "S4"}
        or value.get("context_content_sha256") != _sealed_content(value)
    ):
        raise ValueError("Authority request context integrity failed")
    expected_path = _successor_authority_request_context_path(
        root, value["context_content_sha256"]
    )
    if (
        path != expected_path
        or binding["ref"] != expected_path.relative_to(root).as_posix()
    ):
        raise ValueError("Authority request context is not producer CAS output")
    normalized = normalize_request_semantics(root, context)
    if normalized != context:
        raise ValueError("Authority request context is not normalized")
    compiler_context = {
        key: item for key, item in normalized.items() if not key.endswith("_evidence")
    }
    for key in (
        "external_input_evidence",
        "risk_acceptance_evidence",
        "design_selection_evidence",
    ):
        compiler_context[f"{key}_ref"] = (
            normalized[key]["ref"] if normalized[key] is not None else None
        )
    return binding, value, compiler_context, value["actor_rank"]


def load_evaluation_context(
    root: Path, binding_value: Any
) -> tuple[dict[str, str], dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Load one existing schema-v2 evaluator context without widening it."""

    root = root.expanduser().resolve(strict=True)
    binding = normalize_binding(
        binding_value, "selected-successor authority evaluation context"
    )
    path, raw = read_bound_bytes(
        root,
        binding,
        "authority evaluation context",
        max_bytes=MAX_CONTEXT_BYTES,
    )
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Authority evaluation context is unreadable") from exc
    if not isinstance(value, dict) or raw != _canonical_json(value):
        raise ValueError("Authority evaluation context must be canonical JSON")
    expected_path = _successor_authority_evaluation_context_path(
        root, binding["sha256"]
    )
    if (
        path != expected_path
        or binding["ref"] != expected_path.relative_to(root).as_posix()
    ):
        raise ValueError("Authority evaluation context is not producer CAS output")
    normalized = normalize_evaluation_semantics(root, value)
    if normalized != value:
        raise ValueError("Authority evaluation context is not normalized")
    session = normalized["session_ceiling"]
    envelope = normalized["goal_autonomy_envelope"]
    compiler_session = dict(session)
    compiler_envelope = {
        key: item for key, item in envelope.items() if key != "source_binding"
    }
    compiler_envelope["source_ref"] = envelope["source_binding"]["ref"]
    return binding, normalized, compiler_session, compiler_envelope


def normalize_grant_inputs(
    root: Path, value: Any
) -> tuple[
    dict[str, dict[str, Any]], dict[str, tuple[dict[str, Any], str, dict[str, Any]]]
]:
    """Validate action-wise exact grant bindings or explicit absence sentinels."""

    from manage_agent_authority.workflow_candidates import validated_grants

    if not isinstance(value, dict) or set(value) != set(ACTIONS):
        raise ValueError("Selected-successor grants require all three actions")
    has_bound = any(
        raw is not None and raw != {"status": "absent"} for raw in value.values()
    )
    records = validated_grants(root) if has_bound else {}
    descriptors: dict[str, dict[str, Any]] = {}
    selected: dict[str, tuple[dict[str, Any], str, dict[str, Any]]] = {}
    for action in ACTIONS:
        raw = value[action]
        if raw is None or raw == {"status": "absent"}:
            descriptors[action] = {"status": "absent"}
            continue
        if isinstance(raw, dict) and set(raw) == {"status", "binding"}:
            if raw.get("status") != "bound":
                raise ValueError(f"Selected-successor {action} grant status is invalid")
            raw = raw["binding"]
        binding = normalize_binding(raw, f"{action} authority grant")
        path, grant_value = read_bound_json(root, binding, f"{action} authority grant")
        grant_id = (
            grant_value.get("grant_id") if isinstance(grant_value, dict) else None
        )
        record = records.get(grant_id) if isinstance(grant_id, str) else None
        expected_ref = f".task/authorization/grants/{grant_id}.json"
        if (
            record is None
            or path.relative_to(root.resolve()).as_posix() != expected_ref
            or binding != {"ref": expected_ref, "sha256": record[1]}
            or record[0] != grant_value
        ):
            raise ValueError(f"Selected-successor {action} grant binding is invalid")
        descriptors[action] = {"status": "bound", "binding": binding}
        selected[action] = (record[0], record[1], record[2])
    return descriptors, selected


__all__ = (
    "MAX_CONTEXT_BYTES",
    "MAX_SEMANTIC_INPUT_BYTES",
    "load_evaluation_context",
    "load_request_context",
    "normalize_evaluation_semantics",
    "normalize_request_semantics",
    "normalize_grant_inputs",
)
