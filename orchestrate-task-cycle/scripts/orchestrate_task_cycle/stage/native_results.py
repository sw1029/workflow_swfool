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
    return value


__all__ = ("normalize_native_owner_result",)
