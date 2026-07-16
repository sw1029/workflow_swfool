from __future__ import annotations

from typing import Any

from .core import (
    ALLOWED_TOP_LEVEL_FIELDS,
    ARTIFACT_KIND,
    AUDIT_ID_RE,
    AUTO_REPAIR_TARGET,
    BINDING_STATUSES,
    CAPTURE_MODES,
    CAPTURE_STATUSES,
    FORMAT_VERSION,
    INTEGRITY_STATUSES,
    PARSER_VERSION,
    REPAIR_CLASSES,
    REQUIRED_TOP_LEVEL_FIELDS,
    SAFE_ID_RE,
    SHA256_RE,
    TOOLS,
    _add,
    _forbidden_body_paths,
    _is_non_empty_string,
    _is_safe_relative_path,
)
from .packet_content_validation import validate_findings, validate_packet_metadata


def validate_session_audit_packet(packet: Any) -> list[dict[str, Any]]:
    """Validate a body-free audit sidecar without treating it as workflow truth."""

    errors: list[dict[str, Any]] = []
    if not isinstance(packet, dict):
        _add(
            errors,
            "session_audit_not_object",
            "$",
            "session audit packet must be a JSON object",
        )
        return errors
    _validate_packet_schema(packet, errors)
    _validate_packet_identity_and_policy(packet, errors)
    _validate_source_binding_and_consumability(packet, errors)
    validate_findings(packet, errors)
    validate_packet_metadata(packet, errors)
    return errors


def _validate_packet_schema(
    packet: dict[str, Any], errors: list[dict[str, Any]]
) -> None:
    for field in sorted(REQUIRED_TOP_LEVEL_FIELDS - set(packet)):
        _add(
            errors,
            "session_audit_required_field_missing",
            field,
            "required field is absent",
        )
    for field in sorted(set(packet) - ALLOWED_TOP_LEVEL_FIELDS):
        _add(
            errors,
            "session_audit_unknown_field",
            field,
            "top-level field is outside the closed schema",
        )
    for path in _forbidden_body_paths(packet):
        _add(
            errors,
            "session_audit_body_field_forbidden",
            path,
            "transcript, message, or raw-body fields are forbidden",
        )


def _validate_packet_identity_and_policy(
    packet: dict[str, Any], errors: list[dict[str, Any]]
) -> None:
    if packet.get("format_version") != FORMAT_VERSION:
        _add(
            errors,
            "session_audit_format_version_invalid",
            "format_version",
            "expected format_version 1",
        )
    if packet.get("artifact_kind") != ARTIFACT_KIND:
        _add(
            errors,
            "session_audit_artifact_kind_invalid",
            "artifact_kind",
            "unexpected artifact kind",
        )
    if packet.get("parser_version") != PARSER_VERSION:
        _add(
            errors,
            "session_audit_parser_version_invalid",
            "parser_version",
            f"expected parser_version {PARSER_VERSION}",
        )
    for field in ("audit_id", "session_id"):
        if not _is_non_empty_string(packet.get(field)):
            _add(
                errors,
                "session_audit_identifier_invalid",
                field,
                "identifier must be a non-empty string",
            )
    if not isinstance(packet.get("audit_id"), str) or not AUDIT_ID_RE.fullmatch(
        packet["audit_id"]
    ):
        _add(
            errors,
            "session_audit_identifier_invalid",
            "audit_id",
            "audit_id must use the content-derived format",
        )
    if not isinstance(packet.get("session_id"), str) or not SAFE_ID_RE.fullmatch(
        packet["session_id"]
    ):
        _add(
            errors,
            "session_audit_identifier_invalid",
            "session_id",
            "session_id must be a path-safe identifier",
        )
    for field, allowed, code, label in (
        ("tool", TOOLS, "session_audit_tool_invalid", "tool"),
        (
            "capture_mode",
            CAPTURE_MODES,
            "session_audit_capture_mode_invalid",
            "capture mode",
        ),
        (
            "capture_status",
            CAPTURE_STATUSES,
            "session_audit_capture_status_invalid",
            "capture status",
        ),
        (
            "integrity_status",
            INTEGRITY_STATUSES,
            "session_audit_integrity_status_invalid",
            "integrity status",
        ),
        (
            "repair_class",
            REPAIR_CLASSES,
            "session_audit_repair_class_invalid",
            "repair class",
        ),
    ):
        if packet.get(field) not in allowed:
            _add(
                errors,
                code,
                field,
                f"{label} is outside the closed vocabulary",
            )
    _validate_policy_flags(packet, errors)


def _validate_policy_flags(
    packet: dict[str, Any], errors: list[dict[str, Any]]
) -> None:
    if packet.get("not_goal_truth") is not True:
        _add(
            errors,
            "session_audit_goal_truth_flag_invalid",
            "not_goal_truth",
            "audit packets must assert not_goal_truth=true",
        )
    if packet.get("not_validation_evidence") is not True:
        _add(
            errors,
            "session_audit_validation_evidence_flag_invalid",
            "not_validation_evidence",
            "audit packets must assert not_validation_evidence=true",
        )
    if not isinstance(packet.get("consumable"), bool):
        _add(
            errors,
            "session_audit_consumable_invalid",
            "consumable",
            "consumable must be boolean",
        )
    if not isinstance(packet.get("auto_repair_allowed"), bool):
        _add(
            errors,
            "session_audit_auto_repair_flag_invalid",
            "auto_repair_allowed",
            "auto-repair flag must be boolean",
        )
    elif packet.get("auto_repair_allowed") is not (
        packet.get("repair_class") == "derived_metadata_only"
    ):
        _add(
            errors,
            "session_audit_auto_repair_scope_invalid",
            "auto_repair_allowed",
            "auto-repair is allowed if and only if repair_class is derived_metadata_only",
        )


def _validate_source_binding_and_consumability(
    packet: dict[str, Any], errors: list[dict[str, Any]]
) -> None:
    source = packet.get("source")
    if not isinstance(source, dict) or set(source) != {"path", "sha256", "size_bytes"}:
        _add(
            errors,
            "session_audit_source_invalid",
            "source",
            "source must contain only path, sha256, and size_bytes",
        )
    else:
        _validate_source(source, errors)
    binding = packet.get("binding")
    if not isinstance(binding, dict) or not set(binding) <= {
        "status",
        "cycle_id",
        "task_id",
    }:
        _add(
            errors,
            "session_audit_binding_invalid",
            "binding",
            "binding must use only status, cycle_id, and task_id",
        )
    else:
        _validate_binding(binding, errors)
    _validate_consumability(packet, binding, errors)


def _validate_source(source: dict[str, Any], errors: list[dict[str, Any]]) -> None:
    if (
        not _is_safe_relative_path(source.get("path"))
        or source.get("path") == AUTO_REPAIR_TARGET
        or str(source.get("path", "")).startswith(".task/session_audit/")
    ):
        _add(
            errors,
            "session_audit_source_path_invalid",
            "source.path",
            "source path must be safe and workspace-relative",
        )
    if not isinstance(source.get("sha256"), str) or not SHA256_RE.fullmatch(
        source["sha256"]
    ):
        _add(
            errors,
            "session_audit_source_hash_invalid",
            "source.sha256",
            "source SHA-256 must be lowercase hexadecimal",
        )
    if (
        not isinstance(source.get("size_bytes"), int)
        or isinstance(source.get("size_bytes"), bool)
        or source["size_bytes"] < 0
    ):
        _add(
            errors,
            "session_audit_source_size_invalid",
            "source.size_bytes",
            "source size must be a non-negative integer",
        )


def _validate_binding(binding: dict[str, Any], errors: list[dict[str, Any]]) -> None:
    status = binding.get("status")
    if status not in BINDING_STATUSES:
        _add(
            errors,
            "session_audit_binding_status_invalid",
            "binding.status",
            "binding status is outside the closed vocabulary",
        )
    identifiers = [binding.get("cycle_id"), binding.get("task_id")]
    if any(
        value is not None
        and (not isinstance(value, str) or not SAFE_ID_RE.fullmatch(value))
        for value in identifiers
    ):
        _add(
            errors,
            "session_audit_binding_identifier_invalid",
            "binding",
            "binding identifiers must be non-empty strings",
        )
    if status == "bound" and not all(
        _is_non_empty_string(value) for value in identifiers
    ):
        _add(
            errors,
            "session_audit_bound_identifier_missing",
            "binding",
            "bound status requires both cycle_id and task_id",
        )
    if status in {"ambiguous", "unbound"} and any(
        _is_non_empty_string(value) for value in identifiers
    ):
        _add(
            errors,
            "session_audit_unbound_identifier_claimed",
            "binding",
            "non-bound status cannot claim a cycle or task binding",
        )


def _validate_consumability(
    packet: dict[str, Any], binding: Any, errors: list[dict[str, Any]]
) -> None:
    consumable = packet.get("consumable")
    expected = (
        packet.get("capture_status") == "complete"
        and packet.get("integrity_status") != "unverified"
        and packet.get("capture_mode") != "unknown"
        and isinstance(binding, dict)
        and binding.get("status") == "bound"
    )
    if isinstance(consumable, bool) and consumable is not expected:
        _add(
            errors,
            "session_audit_consumability_inconsistent",
            "consumable",
            "consumable=true requires complete capture, known mode, and evaluated integrity",
        )
    if (
        packet.get("capture_status") in {"quarantined", "failed"}
        and consumable is not False
    ):
        _add(
            errors,
            "session_audit_quarantine_consumable",
            "consumable",
            "quarantined or failed capture must not be consumable",
        )
