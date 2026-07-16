from __future__ import annotations

from typing import Any

from .core import (
    CANONICAL_EVIDENCE_CLASSES,
    EVIDENCE_CLASSES,
    FINDING_SEVERITIES,
    HASH_URN_RE,
    SHA256_RE,
    _add,
    _is_governed_canonical_path,
    _is_non_empty_string,
    _is_safe_relative_path,
    _is_string_list,
    canonical_evidence_refs,
    expected_audit_id,
)


def validate_findings(packet: dict[str, Any], errors: list[dict[str, Any]]) -> None:
    binding = packet.get("binding")
    findings = packet.get("findings")
    if not isinstance(findings, list):
        _add(
            errors,
            "session_audit_findings_invalid",
            "findings",
            "findings must be a JSON list",
        )
        return
    for index, finding in enumerate(findings):
        _validate_finding(binding, index, finding, errors)


def _validate_finding(
    binding: Any,
    index: int,
    finding: Any,
    errors: list[dict[str, Any]],
) -> None:
    path = f"findings.{index}"
    if not isinstance(finding, dict):
        _add(
            errors,
            "session_audit_finding_invalid",
            path,
            "finding must be an object",
        )
        return
    allowed = {
        "code",
        "severity",
        "message",
        "evidence_class",
        "resolved",
        "evidence",
    }
    if not set(finding) <= allowed:
        _add(
            errors,
            "session_audit_finding_unknown_field",
            path,
            "finding contains a field outside the closed schema",
        )
    for field in ("code", "message"):
        if not _is_non_empty_string(finding.get(field)):
            _add(
                errors,
                "session_audit_finding_field_invalid",
                f"{path}.{field}",
                "finding field must be non-empty",
            )
    if finding.get("severity") not in FINDING_SEVERITIES:
        _add(
            errors,
            "session_audit_finding_severity_invalid",
            f"{path}.severity",
            "finding severity is outside the closed vocabulary",
        )
    if finding.get("evidence_class") not in EVIDENCE_CLASSES:
        _add(
            errors,
            "session_audit_finding_evidence_class_invalid",
            f"{path}.evidence_class",
            "evidence class is outside the closed vocabulary",
        )
    if "resolved" in finding and not isinstance(finding.get("resolved"), bool):
        _add(
            errors,
            "session_audit_finding_resolution_invalid",
            f"{path}.resolved",
            "resolved must be boolean when supplied",
        )
    if (
        finding.get("severity") == "block"
        and finding.get("evidence_class") in CANONICAL_EVIDENCE_CLASSES
    ):
        _validate_canonical_finding_refs(binding, path, finding, errors)


def _validate_canonical_finding_refs(
    binding: Any,
    path: str,
    finding: dict[str, Any],
    errors: list[dict[str, Any]],
) -> None:
    refs = canonical_evidence_refs(finding)
    if not refs:
        _add(
            errors,
            "session_audit_canonical_evidence_missing",
            f"{path}.evidence",
            "blocking cross-source or canonical findings require structured canonical evidence references",
        )
    for ref_index, ref in enumerate(refs):
        ref_path = f"{path}.evidence.canonical_evidence_refs.{ref_index}"
        if set(ref) != {"path", "sha256", "cycle_id", "task_id"}:
            _add(
                errors,
                "session_audit_canonical_evidence_ref_invalid",
                ref_path,
                "canonical reference has an invalid shape",
            )
            continue
        if (
            not _is_governed_canonical_path(ref.get("path"))
            or not isinstance(ref.get("sha256"), str)
            or not SHA256_RE.fullmatch(ref["sha256"])
        ):
            _add(
                errors,
                "session_audit_canonical_evidence_ref_invalid",
                ref_path,
                "canonical reference path or hash is invalid",
            )
        if not isinstance(binding, dict) or any(
            ref.get(key) != binding.get(key) for key in ("cycle_id", "task_id")
        ):
            _add(
                errors,
                "session_audit_canonical_evidence_binding_invalid",
                ref_path,
                "canonical reference is not bound to the packet task and cycle",
            )


def validate_packet_metadata(
    packet: dict[str, Any], errors: list[dict[str, Any]]
) -> None:
    source = packet.get("source")
    event_counts = packet.get("event_counts")
    if not isinstance(event_counts, dict) or any(
        not isinstance(value, int) or isinstance(value, bool) or value < 0
        for value in event_counts.values()
    ):
        _add(
            errors,
            "session_audit_event_counts_invalid",
            "event_counts",
            "event counts must be a string-keyed map of non-negative integers",
        )
    timestamp_bounds = packet.get("timestamp_bounds")
    if not isinstance(timestamp_bounds, dict) or set(timestamp_bounds) != {
        "first",
        "last",
    }:
        _add(
            errors,
            "session_audit_timestamp_bounds_invalid",
            "timestamp_bounds",
            "timestamp bounds must contain only first and last",
        )
    elif any(
        value is not None and not _is_non_empty_string(value)
        for value in timestamp_bounds.values()
    ):
        _add(
            errors,
            "session_audit_timestamp_value_invalid",
            "timestamp_bounds",
            "timestamp values must be strings or null",
        )
    evidence_paths = packet.get("evidence_paths")
    if not _is_string_list(evidence_paths) or not evidence_paths:
        _add(
            errors,
            "session_audit_evidence_paths_invalid",
            "evidence_paths",
            "evidence_paths must be a non-empty string list",
        )
    elif (
        not isinstance(source, dict)
        or evidence_paths[0] != source.get("path")
        or not _is_safe_relative_path(evidence_paths[0])
    ):
        _add(
            errors,
            "session_audit_evidence_source_mismatch",
            "evidence_paths.0",
            "first evidence path must equal the safe source path",
        )
    elif any(not HASH_URN_RE.fullmatch(item) for item in evidence_paths[1:]):
        _add(
            errors,
            "session_audit_evidence_hash_urn_invalid",
            "evidence_paths",
            "remaining evidence entries must be SHA-256 URNs",
        )
    if isinstance(packet.get("audit_id"), str) and packet[
        "audit_id"
    ] != expected_audit_id(packet):
        _add(
            errors,
            "session_audit_id_content_mismatch",
            "audit_id",
            "audit_id does not match canonical packet content",
        )
