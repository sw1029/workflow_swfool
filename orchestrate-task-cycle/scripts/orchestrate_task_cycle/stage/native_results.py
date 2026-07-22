"""Validated adapters from native deterministic packets to stage result fields."""

from __future__ import annotations

import hashlib
from typing import Any

from .contracts import canonical_bytes


_REPO_SCAN_FIELDS = {
    "schema_version",
    "artifact_kind",
    "step",
    "cycle_id",
    "adapter_scan_status",
    "adapter_count",
    "repo_skill_adapter_packet",
    "blockers",
    "evidence_paths",
    "scan_packet_sha256",
}
_REPO_SCAN_RESULT_FIELDS = (
    "adapter_scan_status",
    "adapter_count",
    "repo_skill_adapter_packet",
    "blockers",
    "evidence_paths",
)
_ADAPTER_VALIDATION_FIELDS = {
    "schema_version",
    "artifact_kind",
    "step",
    "cycle_id",
    "task_id",
    "adapter_validation_status",
    "adapter_consumability_status",
    "adapter_architecture_status",
    "adapter_change_count",
    "adapter_validation_count",
    "adapter_revision_before_sha256",
    "adapter_revision_after_sha256",
    "adapter_architecture",
    "field_origins",
    "blockers",
    "evidence_paths",
    "validation_packet_sha256",
}
_CODE_STRUCTURE_FIELDS = {
    "schema_version",
    "artifact_kind",
    "step",
    "cycle_id",
    "result",
    "field_origins",
    "audit_packet_sha256",
}


def _repo_scan_result(
    value: dict[str, Any], *, cycle_id: str, source_ref: str
) -> dict[str, Any]:
    if set(value) != _REPO_SCAN_FIELDS:
        raise ValueError("native repo adapter scan packet fields are invalid")
    if (
        value.get("schema_version") != 2
        or value.get("artifact_kind") != "repo_skill_adapter_scan_packet"
        or value.get("step") != "repo_skill_adapter_scan"
        or value.get("cycle_id") != cycle_id
    ):
        raise ValueError("native repo adapter scan packet scope is invalid")
    body = {
        key: item for key, item in value.items() if key != "scan_packet_sha256"
    }
    expected = hashlib.sha256(canonical_bytes(body) + b"\n").hexdigest()
    if value.get("scan_packet_sha256") != expected:
        raise ValueError("native repo adapter scan packet integrity failed")
    result = {key: value[key] for key in _REPO_SCAN_RESULT_FIELDS}
    evidence_paths = result.get("evidence_paths")
    if not isinstance(evidence_paths, list):
        raise ValueError("native repo adapter scan evidence_paths must be a list")
    if not evidence_paths:
        result["evidence_paths"] = [source_ref]
    return result


def _integrity(value: dict[str, Any], digest_field: str, label: str) -> None:
    body = {key: item for key, item in value.items() if key != digest_field}
    expected = hashlib.sha256(canonical_bytes(body) + b"\n").hexdigest()
    if value.get(digest_field) != expected:
        raise ValueError(f"native {label} packet integrity failed")


def _adapter_validation_result(
    value: dict[str, Any], *, cycle_id: str, source_ref: str
) -> dict[str, Any]:
    if set(value) != _ADAPTER_VALIDATION_FIELDS:
        raise ValueError("native adapter validation packet fields are invalid")
    if (
        value.get("schema_version") != 2
        or value.get("artifact_kind") != "repo_skill_adapter_validation_packet"
        or value.get("step") != "repo_skill_adapter_validate"
        or value.get("cycle_id") != cycle_id
    ):
        raise ValueError("native adapter validation packet scope is invalid")
    _integrity(value, "validation_packet_sha256", "adapter validation")
    result = {
        key: item
        for key, item in value.items()
        if key
        not in {
            "schema_version",
            "artifact_kind",
            "cycle_id",
            "validation_packet_sha256",
        }
    }
    if not isinstance(result.get("evidence_paths"), list):
        raise ValueError("native adapter validation evidence_paths must be a list")
    if not result["evidence_paths"]:
        result["evidence_paths"] = [source_ref]
    return result


def _code_structure_result(
    value: dict[str, Any], *, cycle_id: str, source_ref: str
) -> dict[str, Any]:
    if set(value) != _CODE_STRUCTURE_FIELDS:
        raise ValueError("native code structure packet fields are invalid")
    if (
        value.get("schema_version") != 2
        or value.get("artifact_kind") != "code_structure_audit_packet"
        or value.get("step") != "code_structure_audit"
        or value.get("cycle_id") != cycle_id
    ):
        raise ValueError("native code structure packet scope is invalid")
    _integrity(value, "audit_packet_sha256", "code structure")
    result = value.get("result")
    if not isinstance(result, dict):
        raise ValueError("native code structure result must be an object")
    result = dict(result)
    result["field_origins"] = value["field_origins"]
    evidence = result.get("evidence_paths")
    if not isinstance(evidence, list):
        raise ValueError("native code structure evidence_paths must be a list")
    if not evidence:
        result["evidence_paths"] = [source_ref]
    return result


def normalize_native_owner_result(
    target: str,
    value: dict[str, Any],
    *,
    cycle_id: str,
    source_ref: str,
) -> dict[str, Any]:
    """Remove only a registered, integrity-checked native packet envelope."""

    artifact_kind = value.get("artifact_kind")
    if target == "repo_skill_adapter_scan" and artifact_kind == (
        "repo_skill_adapter_scan_packet"
    ):
        return _repo_scan_result(value, cycle_id=cycle_id, source_ref=source_ref)
    if target == "repo_skill_adapter_validate" and artifact_kind == (
        "repo_skill_adapter_validation_packet"
    ):
        return _adapter_validation_result(
            value, cycle_id=cycle_id, source_ref=source_ref
        )
    if target == "code_structure_audit" and artifact_kind == (
        "code_structure_audit_packet"
    ):
        return _code_structure_result(value, cycle_id=cycle_id, source_ref=source_ref)
    return value


__all__ = ("normalize_native_owner_result",)
