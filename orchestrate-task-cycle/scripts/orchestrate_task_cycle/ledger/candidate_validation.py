from __future__ import annotations

from typing import Any

from ..result_contract.integrity import actual_report_body_divergences
from .constants import (
    DURABLE_STATE_MODES,
    FINALIZATION_SCHEMA_VERSION,
    FINAL_CANDIDATE_KIND,
    SENSITIVE_DURABLE_KEYS,
    SENSITIVE_DURABLE_KEY_PARTS,
    SHA256_PATTERN,
    VERDICT_AXES,
    VERDICT_AXIS_STATUSES,
)
from .event_model import truthy_delta
from .operation_contract import (
    validate_no_change_candidate,
    validate_typed_operations_candidate,
)
from .support import canonical_json_bytes, validate_cycle_id, validate_event_id


def _candidate_expected_revision(candidate: dict[str, Any]) -> int | None:
    if "expected_previous_revision" not in candidate:
        raise ValueError("final candidate requires explicit expected_previous_revision, including null for first publication")
    value = candidate.get("expected_previous_revision")
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError("expected_previous_revision must be null or a positive integer")
    return value


def _candidate_expected_identifier(candidate: dict[str, Any], field: str) -> str | None:
    if field not in candidate:
        raise ValueError(f"final candidate requires explicit {field}, including null for first publication")
    value = candidate.get(field)
    if value is None:
        return None
    normalized = str(value).strip()
    if not normalized:
        raise ValueError(f"{field} must be null or a non-empty opaque identifier")
    if field == "expected_previous_finalization_token":
        normalized = normalized.lower()
        if not SHA256_PATTERN.fullmatch(normalized):
            raise ValueError("expected_previous_finalization_token must be null or a full lowercase SHA-256 digest")
    else:
        validate_event_id(normalized)
    return normalized


def _positive_progress_markers(value: Any, prefix: str = "durable_state_candidate") -> dict[str, list[str]]:
    markers: dict[str, list[str]] = {"semantic": [], "goal": [], "combined": []}
    if isinstance(value, dict):
        for raw_key, item in value.items():
            key = str(raw_key).strip().lower()
            path = f"{prefix}.{raw_key}"
            normalized = str(item).strip().lower() if not isinstance(item, (dict, list)) else ""
            positive_boolean = item is True or normalized in {"true", "yes", "1"}
            if key in {"semantic_progress", "authoritative_semantic_progress"} and positive_boolean:
                markers["semantic"].append(path)
            if key == "goal_productive" and positive_boolean:
                markers["goal"].append(path)
            if key == "progress_kind" and normalized == "goal_productive":
                markers["combined"].append(path)
            if key == "progress_verdict" and normalized in {"advanced", "success", "succeeded", "goal_productive"}:
                markers["combined"].append(path)
            nested = _positive_progress_markers(item, path)
            for category, paths in nested.items():
                markers[category].extend(paths)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            nested = _positive_progress_markers(item, f"{prefix}[{index}]")
            for category, paths in nested.items():
                markers[category].extend(paths)
    return markers


def _durable_key_is_sensitive(key: str) -> bool:
    normalized = key.strip().lower()
    return bool(
        normalized in SENSITIVE_DURABLE_KEYS
        or normalized.endswith("_path")
        or normalized.endswith("_paths")
        or normalized.startswith("path_")
        or any(part in normalized for part in SENSITIVE_DURABLE_KEY_PARTS)
    )


def _durable_string_looks_like_path(value: str) -> bool:
    text = value.strip()
    return bool(text.startswith(("/", "./", "../", "~")) or "\\" in text or "/" in text)


def validate_durable_payload_privacy(value: Any, prefix: str) -> None:
    if isinstance(value, dict):
        for raw_key, child in value.items():
            key = str(raw_key)
            if _durable_key_is_sensitive(key):
                raise ValueError(f"durable state payload contains prohibited source metadata at {prefix}.{key}")
            validate_durable_payload_privacy(child, f"{prefix}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            validate_durable_payload_privacy(child, f"{prefix}[{index}]")
    elif isinstance(value, str) and _durable_string_looks_like_path(value):
        raise ValueError(f"durable state payload contains a path-like string at {prefix}")


def validate_durable_state_candidate(
    durable_state: Any,
    semantic_status: str,
    goal_status: str,
    attempt_identity: str,
) -> dict[str, Any]:
    if not isinstance(durable_state, dict):
        raise ValueError("final candidate requires a durable_state_candidate JSON object")
    durable_state_mode = str(durable_state.get("mode") or "").strip()
    if durable_state_mode not in DURABLE_STATE_MODES:
        raise ValueError("durable_state_candidate mode must be complete_projection or typed_operations")
    if durable_state_mode == "complete_projection":
        validate_no_change_candidate(
            durable_state, attempt_identity=attempt_identity
        )
    else:
        validate_typed_operations_candidate(
            durable_state, attempt_identity=attempt_identity
        )
        for index, operation in enumerate(durable_state["operations"]):
            validate_durable_payload_privacy(
                operation["payload"],
                f"durable_state_candidate.operations[{index}].payload",
            )
    positive_markers = _positive_progress_markers(durable_state)
    if positive_markers["semantic"] and (semantic_status != "pass" or goal_status != "pass"):
        raise ValueError(
            "durable state contains positive semantic progress that contradicts the final artifact semantic verdict or goal readiness verdict"
        )
    if positive_markers["goal"] and (semantic_status != "pass" or goal_status != "pass"):
        raise ValueError(
            "durable state contains positive goal progress that contradicts the final artifact semantic verdict or goal readiness verdict"
        )
    if positive_markers["combined"] and (semantic_status != "pass" or goal_status != "pass"):
        raise ValueError("durable state contains an advanced progress verdict that contradicts final semantic or goal axes")
    return durable_state


def _validate_verdict_axes(normalized: dict[str, Any]) -> None:
    verdict_contract_version = normalized.get("verdict_contract_version")
    if isinstance(verdict_contract_version, bool) or verdict_contract_version != 1:
        raise ValueError("final candidate verdict_contract_version must be 1")
    for axis in VERDICT_AXES:
        value = normalized.get(axis)
        if not isinstance(value, dict):
            raise ValueError(f"final candidate requires object verdict axis {axis}")
        status = str(value.get("status") or value.get("verdict") or "").strip().lower()
        if status not in VERDICT_AXIS_STATUSES:
            raise ValueError(f"final candidate verdict axis {axis} has invalid status")
        evidence = value.get("evidence_ref") or value.get("evidence_refs")
        if status != "not_applicable" and evidence in (None, "", []):
            raise ValueError(f"final candidate verdict axis {axis} requires bounded evidence")
        if evidence not in (None, "", []):
            validate_durable_payload_privacy(evidence, f"final_candidate.{axis}.evidence")
        normalized[axis] = {**value, "status": status}


def _validate_verdict_aliases(normalized: dict[str, Any]) -> None:
    alias_containers = [
        normalized.get("verdict_axes"),
        normalized.get("result"),
        normalized.get("result", {}).get("verdict_axes") if isinstance(normalized.get("result"), dict) else None,
    ]
    for axis in VERDICT_AXES:
        canonical_status = normalized[axis]["status"]
        for container in alias_containers:
            if not isinstance(container, dict) or axis not in container:
                continue
            alias = container[axis]
            alias_status = (
                str(alias.get("status") or alias.get("verdict") or "").strip().lower()
                if isinstance(alias, dict)
                else str(alias or "").strip().lower()
            )
            if alias_status != canonical_status:
                raise ValueError(f"final candidate verdict alias conflicts with canonical axis {axis}")


def _has_body_divergence(normalized: dict[str, Any]) -> bool:
    divergence_paths = (
        ("report_body_divergence",),
        ("actual_artifact_truth", "report_body_divergence"),
        ("quality_review", "report_body_divergence"),
        ("validation", "actual_artifact_truth", "report_body_divergence"),
        ("result", "report_body_divergence"),
        ("result", "actual_artifact_truth", "report_body_divergence"),
        ("result", "quality_review", "report_body_divergence"),
        ("result", "validation", "actual_artifact_truth", "report_body_divergence"),
    )
    for divergence_path in divergence_paths:
        current: Any = normalized
        for path_part in divergence_path:
            if not isinstance(current, dict) or path_part not in current:
                current = None
                break
            current = current[path_part]
        if truthy_delta(current):
            return True
    return bool(actual_report_body_divergences(normalized))


def normalize_final_candidate(cycle_id: str, candidate: dict[str, Any]) -> dict[str, Any]:
    cycle_id = validate_cycle_id(cycle_id)
    if not isinstance(candidate, dict):
        raise ValueError("final candidate must be a JSON object")
    normalized = dict(candidate)
    schema_version = normalized.get("schema_version")
    if isinstance(schema_version, bool) or schema_version != FINALIZATION_SCHEMA_VERSION:
        raise ValueError("final candidate schema_version must be 1")
    if normalized.get("kind") != FINAL_CANDIDATE_KIND:
        raise ValueError(f"final candidate kind must be {FINAL_CANDIDATE_KIND}")
    if normalized.get("final_candidate") is not True:
        raise ValueError("completion output must explicitly mark final_candidate true")
    if str(normalized.get("cycle_id") or "") != cycle_id:
        raise ValueError("final candidate cycle_id does not match finalization cycle")
    normalized["attempt_id"] = validate_event_id(normalized.get("attempt_id"))
    owner_fields = {
        "attempt_revision", "supersedes_revision", "supersedes_finalization_token",
        "finalization_token", "state_commit_status", "receipt_hash", "authoritative_final",
    }
    supplied_owner_fields = sorted(owner_fields.intersection(normalized))
    if supplied_owner_fields:
        raise ValueError(
            "revision, supersession, receipt, and authoritative verdict fields are assigned only by the finalization owner: "
            + ", ".join(supplied_owner_fields)
        )
    projection_fields = sorted({
        "authoritative_projection", "authoritative_projection_digest",
        "authoritative_projection_id", "validation_axes_digest",
    }.intersection(normalized))
    nested_projection = (
        isinstance(normalized.get("finalization"), dict)
        and isinstance(normalized["finalization"].get("authoritative_projection"), dict)
    ) or (
        isinstance(normalized.get("result"), dict)
        and isinstance(normalized["result"].get("authoritative_projection"), dict)
    )
    if projection_fields or nested_projection:
        raise ValueError("authoritative projection fields are assigned only by the finalization owner")
    normalized["expected_previous_revision"] = _candidate_expected_revision(normalized)
    normalized["expected_previous_attempt_id"] = _candidate_expected_identifier(normalized, "expected_previous_attempt_id")
    normalized["expected_previous_finalization_token"] = _candidate_expected_identifier(
        normalized, "expected_previous_finalization_token"
    )
    _validate_verdict_axes(normalized)
    _validate_verdict_aliases(normalized)
    if _has_body_divergence(normalized):
        truth_status = normalized["artifact_truth_verdict"]["status"]
        semantic_status = normalized["artifact_semantic_verdict"]["status"]
        goal_status = normalized["goal_readiness_verdict"]["status"]
        if "conflicted" not in {truth_status, semantic_status} or semantic_status == "pass" or goal_status == "pass":
            raise ValueError(
                "body/report divergence requires a conflicted artifact axis and blocks favorable semantic or goal publication"
            )
    semantic_status = normalized["artifact_semantic_verdict"]["status"]
    goal_status = normalized["goal_readiness_verdict"]["status"]
    normalized["durable_state_candidate"] = validate_durable_state_candidate(
        normalized.get("durable_state_candidate"),
        semantic_status,
        goal_status,
        normalized["attempt_id"],
    )
    try:
        canonical_json_bytes(normalized)
    except (TypeError, ValueError) as exc:
        raise ValueError("final candidate must contain only JSON-serializable values") from exc
    return normalized


def authoritative_final_from_axes(axes: dict[str, dict[str, Any]]) -> str:
    statuses = {str(value.get("status") or "") for value in axes.values()}
    if "fail" in statuses:
        return "failure"
    if "conflicted" in statuses or "blocked" in statuses:
        return "blocked"
    if "partial" in statuses:
        return "partial"
    if "not_evaluated" in statuses:
        return "not_evaluated"
    return "success"


def final_candidate_commit_material(candidate: dict[str, Any]) -> dict[str, Any]:
    """Select only decision-bound candidate fields for idempotency and receipts."""
    fields = (
        "schema_version", "kind", "final_candidate", "cycle_id", "attempt_id",
        "expected_previous_revision", "expected_previous_attempt_id",
        "expected_previous_finalization_token", "verdict_contract_version",
        *VERDICT_AXES, "durable_state_candidate",
    )
    return {field: candidate[field] for field in fields}
