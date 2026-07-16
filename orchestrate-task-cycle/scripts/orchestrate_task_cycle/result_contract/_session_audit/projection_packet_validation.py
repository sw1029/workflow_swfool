from __future__ import annotations

from typing import Any

from .core import (
    ARTIFACT_KIND,
    AUDIT_ID_RE,
    AUTO_REPAIR_TARGET,
    BINDING_STATUSES,
    CANONICAL_EVIDENCE_CLASSES,
    CAPTURE_MODES,
    CAPTURE_STATUSES,
    EVIDENCE_CLASSES,
    FINDING_SEVERITIES,
    FORMAT_VERSION,
    INTEGRITY_STATUSES,
    PARSER_VERSION,
    REPAIR_CLASSES,
    SAFE_ID_RE,
    SHA256_RE,
    TOOLS,
    _add,
    _is_non_empty_string,
)


def _validate_projected_packet(
    packet: dict[str, Any],
    path: str,
    errors: list[dict[str, Any]],
) -> None:
    _validate_projected_packet_identity(packet, path, errors)
    _validate_projected_packet_policy(packet, path, errors)
    _validate_projected_source_and_binding(packet, path, errors)
    _validate_projected_packet_metadata(packet, path, errors)
    _validate_projected_findings(packet.get("findings"), path, errors)


def _validate_projected_packet_identity(
    packet: dict[str, Any],
    path: str,
    errors: list[dict[str, Any]],
) -> None:
    if packet.get("contract_status") != "valid":
        _add(
            errors,
            "session_audit_projection_packet_status_invalid",
            f"{path}.contract_status",
            "projected packets must be validated",
        )
    if (
        packet.get("format_version") != FORMAT_VERSION
        or packet.get("artifact_kind") != ARTIFACT_KIND
    ):
        _add(
            errors,
            "session_audit_projection_packet_identity_invalid",
            path,
            "projected packet identity is invalid",
        )
    if packet.get("parser_version") != PARSER_VERSION:
        _add(
            errors,
            "session_audit_parser_version_invalid",
            f"{path}.parser_version",
            "projected parser version is invalid",
        )
    for field in ("audit_id", "session_id"):
        if not _is_non_empty_string(packet.get(field)):
            _add(
                errors,
                "session_audit_identifier_invalid",
                f"{path}.{field}",
                "projected identifier is invalid",
            )
    if not isinstance(packet.get("audit_id"), str) or not AUDIT_ID_RE.fullmatch(
        packet["audit_id"]
    ):
        _add(
            errors,
            "session_audit_identifier_invalid",
            f"{path}.audit_id",
            "projected audit_id is invalid",
        )
    if not isinstance(packet.get("session_id"), str) or not SAFE_ID_RE.fullmatch(
        packet["session_id"]
    ):
        _add(
            errors,
            "session_audit_identifier_invalid",
            f"{path}.session_id",
            "projected session_id is invalid",
        )
    for field, allowed, code, detail in (
        (
            "tool",
            TOOLS,
            "session_audit_tool_invalid",
            "tool is outside the closed vocabulary",
        ),
        (
            "capture_mode",
            CAPTURE_MODES,
            "session_audit_capture_mode_invalid",
            "capture mode is outside the closed vocabulary",
        ),
        (
            "capture_status",
            CAPTURE_STATUSES,
            "session_audit_capture_status_invalid",
            "capture status is outside the closed vocabulary",
        ),
        (
            "integrity_status",
            INTEGRITY_STATUSES,
            "session_audit_integrity_status_invalid",
            "integrity status is outside the closed vocabulary",
        ),
        (
            "repair_class",
            REPAIR_CLASSES,
            "session_audit_repair_class_invalid",
            "repair class is outside the closed vocabulary",
        ),
    ):
        if packet.get(field) not in allowed:
            _add(errors, code, f"{path}.{field}", detail)


def _validate_projected_packet_policy(
    packet: dict[str, Any],
    path: str,
    errors: list[dict[str, Any]],
) -> None:
    if (
        packet.get("not_goal_truth") is not True
        or packet.get("not_validation_evidence") is not True
    ):
        _add(
            errors,
            "session_audit_projection_truth_flags_invalid",
            path,
            "projected packet truth flags are invalid",
        )
    if packet.get("source_projection_verified") is not True:
        _add(
            errors,
            "session_audit_source_projection_not_verified",
            path,
            "collector projection must assert bundled deterministic source validation",
        )
    if packet.get("canonical_refs_verified") is not True:
        _add(
            errors,
            "session_audit_canonical_refs_not_verified",
            path,
            "collector projection must assert independent canonical-ref verification",
        )
    if not isinstance(packet.get("consumable"), bool) or not isinstance(
        packet.get("auto_repair_allowed"), bool
    ):
        _add(
            errors,
            "session_audit_projection_boolean_invalid",
            path,
            "projected policy flags must be boolean",
        )
    elif packet.get("auto_repair_allowed") is not (
        packet.get("repair_class") == "derived_metadata_only"
    ):
        _add(
            errors,
            "session_audit_auto_repair_scope_invalid",
            path,
            "projected auto-repair scope is invalid",
        )
    expected_target = (
        AUTO_REPAIR_TARGET if packet.get("auto_repair_allowed") is True else None
    )
    if packet.get("auto_repair_target") != expected_target:
        _add(
            errors,
            "session_audit_auto_repair_target_invalid",
            path,
            "auto-repair can target only the derived session-audit index",
        )
    expected_consumable = (
        packet.get("capture_status") == "complete"
        and packet.get("integrity_status") != "unverified"
        and packet.get("capture_mode") != "unknown"
        and isinstance(packet.get("binding"), dict)
        and packet["binding"].get("status") == "bound"
    )
    if (
        isinstance(packet.get("consumable"), bool)
        and packet.get("consumable") is not expected_consumable
    ):
        _add(
            errors,
            "session_audit_consumability_inconsistent",
            path,
            "projected consumability is inconsistent",
        )


def _validate_projected_source_and_binding(
    packet: dict[str, Any],
    path: str,
    errors: list[dict[str, Any]],
) -> None:
    if not isinstance(packet.get("source_sha256"), str) or not SHA256_RE.fullmatch(
        packet["source_sha256"]
    ):
        _add(
            errors,
            "session_audit_source_hash_invalid",
            f"{path}.source_sha256",
            "projected source hash is invalid",
        )
    if (
        not isinstance(packet.get("source_size_bytes"), int)
        or isinstance(packet.get("source_size_bytes"), bool)
        or packet["source_size_bytes"] < 0
    ):
        _add(
            errors,
            "session_audit_source_size_invalid",
            f"{path}.source_size_bytes",
            "projected source size is invalid",
        )
    binding = packet.get("binding")
    if (
        not isinstance(binding, dict)
        or not set(binding) <= {"status", "cycle_id", "task_id"}
        or binding.get("status") not in BINDING_STATUSES
    ):
        _add(
            errors,
            "session_audit_binding_status_invalid",
            f"{path}.binding",
            "projected binding is invalid",
        )
        return
    identifiers = [binding.get("cycle_id"), binding.get("task_id")]
    if any(
        value is not None
        and (not isinstance(value, str) or not SAFE_ID_RE.fullmatch(value))
        for value in identifiers
    ):
        _add(
            errors,
            "session_audit_binding_identifier_invalid",
            f"{path}.binding",
            "projected binding identifier is invalid",
        )
    if binding.get("status") == "bound" and not all(
        isinstance(value, str) and SAFE_ID_RE.fullmatch(value) for value in identifiers
    ):
        _add(
            errors,
            "session_audit_bound_identifier_missing",
            f"{path}.binding",
            "bound projection lacks both identifiers",
        )
    if binding.get("status") in {"ambiguous", "unbound"} and any(
        _is_non_empty_string(value) for value in identifiers
    ):
        _add(
            errors,
            "session_audit_unbound_identifier_claimed",
            f"{path}.binding",
            "non-bound projection claims an identifier",
        )


def _validate_projected_packet_metadata(
    packet: dict[str, Any],
    path: str,
    errors: list[dict[str, Any]],
) -> None:
    event_counts = packet.get("event_counts")
    if not isinstance(event_counts, dict) or any(
        not isinstance(value, int) or isinstance(value, bool) or value < 0
        for value in event_counts.values()
    ):
        _add(
            errors,
            "session_audit_event_counts_invalid",
            f"{path}.event_counts",
            "projected event counts are invalid",
        )
    bounds = packet.get("timestamp_bounds")
    if not isinstance(bounds, dict) or set(bounds) != {"first", "last"}:
        _add(
            errors,
            "session_audit_timestamp_bounds_invalid",
            f"{path}.timestamp_bounds",
            "projected timestamp bounds are invalid",
        )
    elif any(
        value is not None and not _is_non_empty_string(value)
        for value in bounds.values()
    ):
        _add(
            errors,
            "session_audit_timestamp_value_invalid",
            f"{path}.timestamp_bounds",
            "projected timestamp value is invalid",
        )
    hashes = packet.get("evidence_path_hashes")
    if (
        not isinstance(hashes, list)
        or not hashes
        or any(
            not isinstance(value, str) or not SHA256_RE.fullmatch(value)
            for value in hashes
        )
    ):
        _add(
            errors,
            "session_audit_evidence_hash_projection_invalid",
            f"{path}.evidence_path_hashes",
            "projected evidence hashes are invalid",
        )
    metadata = packet.get("file")
    if not isinstance(metadata, dict) or not set(metadata) <= {
        "path",
        "sha256",
        "size_bytes",
    }:
        _add(
            errors,
            "session_audit_projection_file_invalid",
            f"{path}.file",
            "projected file metadata is invalid",
        )
    elif (
        metadata.get("path") != f".task/session_audit/{packet.get('audit_id')}.json"
        or not isinstance(metadata.get("sha256"), str)
        or not SHA256_RE.fullmatch(metadata["sha256"])
        or not isinstance(metadata.get("size_bytes"), int)
        or isinstance(metadata.get("size_bytes"), bool)
        or metadata["size_bytes"] < 0
    ):
        _add(
            errors,
            "session_audit_projection_file_invalid",
            f"{path}.file",
            "projected file metadata values are invalid",
        )


def _validate_projected_findings(
    findings: Any,
    packet_path: str,
    errors: list[dict[str, Any]],
) -> None:
    if not isinstance(findings, list):
        _add(
            errors,
            "session_audit_findings_invalid",
            f"{packet_path}.findings",
            "projected findings must be a list",
        )
        return
    required = {
        "code",
        "severity",
        "evidence_class",
        "resolved",
        "canonical_evidence_ref_hashes",
    }
    for index, finding in enumerate(findings):
        path = f"{packet_path}.findings.{index}"
        if not isinstance(finding, dict) or set(finding) != required:
            _add(
                errors,
                "session_audit_projection_finding_shape_invalid",
                path,
                "projected finding shape is invalid",
            )
            continue
        if (
            finding.get("severity") not in FINDING_SEVERITIES
            or finding.get("evidence_class") not in EVIDENCE_CLASSES
        ):
            _add(
                errors,
                "session_audit_projection_finding_vocabulary_invalid",
                path,
                "projected finding vocabulary is invalid",
            )
        if not _is_non_empty_string(finding.get("code")):
            _add(
                errors,
                "session_audit_projection_finding_code_invalid",
                path,
                "projected finding code is invalid",
            )
        hashes = finding.get("canonical_evidence_ref_hashes")
        if (
            not isinstance(finding.get("resolved"), bool)
            or not isinstance(hashes, list)
            or any(
                not isinstance(value, str) or not SHA256_RE.fullmatch(value)
                for value in hashes
            )
        ):
            _add(
                errors,
                "session_audit_projection_finding_value_invalid",
                path,
                "projected finding values are invalid",
            )
        if (
            finding.get("severity") == "block"
            and finding.get("evidence_class") in CANONICAL_EVIDENCE_CLASSES
            and not hashes
        ):
            _add(
                errors,
                "session_audit_canonical_evidence_missing",
                path,
                "canonical block finding lacks references",
            )
