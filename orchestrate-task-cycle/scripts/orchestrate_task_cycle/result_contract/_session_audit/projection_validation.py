from __future__ import annotations

import re
from typing import Any

from .projection_packet_validation import _validate_projected_packet

from .core import (
    AUTO_REPAIR_TARGET,
    SHA256_RE,
    _add,
    _forbidden_body_paths,
    _is_string_list,
)


PROJECTION_PACKET_FIELDS = {
    "contract_status",
    "file",
    "format_version",
    "artifact_kind",
    "parser_version",
    "audit_id",
    "tool",
    "session_id",
    "source_sha256",
    "source_size_bytes",
    "capture_mode",
    "capture_status",
    "integrity_status",
    "binding",
    "source_projection_verified",
    "canonical_refs_verified",
    "consumable",
    "not_goal_truth",
    "not_validation_evidence",
    "repair_class",
    "auto_repair_allowed",
    "auto_repair_target",
    "event_counts",
    "timestamp_bounds",
    "evidence_path_hashes",
    "findings",
}


def validate_collection_projection(value: Any) -> list[dict[str, Any]]:
    """Validate the body-free projection emitted by the local collectors."""

    errors: list[dict[str, Any]] = []
    lists = _validate_projection_envelope(value, errors)
    if lists is None:
        return errors
    packets, invalid_packets = lists
    _validate_projection_counts(value, packets, invalid_packets, errors)
    for index, packet in enumerate(packets):
        path = f"packets.{index}"
        if not isinstance(packet, dict) or set(packet) != PROJECTION_PACKET_FIELDS:
            _add(
                errors,
                "session_audit_projection_packet_shape_invalid",
                path,
                "packet projection has a missing or unknown field",
            )
            continue
        _validate_projected_packet(packet, path, errors)
    _validate_invalid_packets(invalid_packets, errors)
    _validate_index_projection(value.get("index"), errors)
    return errors


def _validate_projection_envelope(
    value: Any,
    errors: list[dict[str, Any]],
) -> tuple[list[Any], list[Any]] | None:
    if (
        not isinstance(value, dict)
        or value.get("artifact_kind") != "session_audit_collection_projection"
    ):
        _add(
            errors,
            "session_audit_projection_invalid",
            "$",
            "collection projection has an invalid envelope",
        )
        return None
    if value.get("not_goal_truth") is not True:
        _add(
            errors,
            "session_audit_goal_truth_flag_invalid",
            "not_goal_truth",
            "collection must remain non-goal-truth",
        )
    if value.get("not_validation_evidence") is not True:
        _add(
            errors,
            "session_audit_validation_evidence_flag_invalid",
            "not_validation_evidence",
            "collection must remain non-validation evidence",
        )
    allowed = {
        "artifact_kind",
        "not_goal_truth",
        "not_validation_evidence",
        "directory",
        "packet_count",
        "total_packet_count",
        "scanned_packet_count",
        "truncated_count",
        "truncated",
        "valid_count",
        "invalid_count",
        "malformed_count",
        "packets",
        "invalid_packets",
        "index",
    }
    for field in sorted(set(value) - allowed):
        _add(
            errors,
            "session_audit_projection_unknown_field",
            field,
            "collection contains a field outside the closed projection schema",
        )
    for path in _forbidden_body_paths(value):
        _add(
            errors,
            "session_audit_body_field_forbidden",
            path,
            "projection contains a forbidden body field",
        )
    packets = value.get("packets")
    invalid_packets = value.get("invalid_packets")
    if not isinstance(packets, list) or not isinstance(invalid_packets, list):
        _add(
            errors,
            "session_audit_projection_lists_invalid",
            "$",
            "packets and invalid_packets must be lists",
        )
        return None
    return packets, invalid_packets


def _validate_projection_counts(
    value: dict[str, Any],
    packets: list[Any],
    invalid_packets: list[Any],
    errors: list[dict[str, Any]],
) -> None:
    for field in (
        "packet_count",
        "total_packet_count",
        "scanned_packet_count",
        "truncated_count",
        "valid_count",
        "invalid_count",
        "malformed_count",
    ):
        count = value.get(field)
        if not isinstance(count, int) or isinstance(count, bool) or count < 0:
            _add(
                errors,
                "session_audit_projection_count_invalid",
                field,
                "projection count must be non-negative",
            )
    if not isinstance(value.get("truncated"), bool):
        _add(
            errors,
            "session_audit_projection_truncated_invalid",
            "truncated",
            "truncated must be boolean",
        )
    if value.get("valid_count") != len(packets) or value.get("invalid_count") != len(
        invalid_packets
    ):
        _add(
            errors,
            "session_audit_projection_count_mismatch",
            "$",
            "projection counts do not match packet lists",
        )
    if value.get("scanned_packet_count") != len(packets) + len(invalid_packets):
        _add(
            errors,
            "session_audit_projection_scan_count_mismatch",
            "$",
            "scanned count does not match projected packets",
        )
    count_values = [
        value.get(field)
        for field in (
            "packet_count",
            "total_packet_count",
            "scanned_packet_count",
            "truncated_count",
        )
    ]
    if all(
        isinstance(count, int) and not isinstance(count, bool) for count in count_values
    ) and (
        count_values[0] != count_values[1]
        or count_values[1] != count_values[2] + count_values[3]
    ):
        _add(
            errors,
            "session_audit_projection_total_count_mismatch",
            "$",
            "total, scanned, and truncated counts are inconsistent",
        )
    if value.get("truncated") is not bool(value.get("truncated_count")):
        _add(
            errors,
            "session_audit_projection_truncation_mismatch",
            "$",
            "truncation flag and count are inconsistent",
        )


def _validate_invalid_packets(packets: list[Any], errors: list[dict[str, Any]]) -> None:
    for index, packet in enumerate(packets):
        if (
            not isinstance(packet, dict)
            or set(packet) != {"contract_status", "file", "error_codes"}
            or packet.get("contract_status") not in {"invalid", "malformed", "unsafe"}
            or not _is_string_list(packet.get("error_codes"))
        ):
            _add(
                errors,
                "session_audit_invalid_projection_invalid",
                f"invalid_packets.{index}",
                "invalid packet diagnostic is malformed",
            )


def _validate_index_projection(index: Any, errors: list[dict[str, Any]]) -> None:
    if not isinstance(index, dict):
        _add(
            errors,
            "session_audit_index_projection_invalid",
            "index",
            "index projection must be an object",
        )
        return
    if not index:
        return
    status = index.get("contract_status")
    base_fields = {"path", "sha256", "size_bytes", "contract_status"}
    valid_fields = base_fields | {
        "index_id",
        "entry_count",
        "repair_class",
        "auto_repair_allowed",
        "auto_repair_target",
        "not_goal_truth",
        "not_validation_evidence",
        "evidence_path_hashes",
    }
    invalid_fields = base_fields | {"error_codes"}
    expected_fields = valid_fields if status == "valid" else invalid_fields
    if set(index) != expected_fields or status not in {"valid", "invalid", "malformed"}:
        _add(
            errors,
            "session_audit_index_projection_invalid",
            "index",
            "index projection schema is invalid",
        )
    elif (
        index.get("path") != AUTO_REPAIR_TARGET
        or not isinstance(index.get("sha256"), str)
        or not SHA256_RE.fullmatch(index["sha256"])
        or not isinstance(index.get("size_bytes"), int)
        or isinstance(index.get("size_bytes"), bool)
        or index["size_bytes"] < 0
    ):
        _add(
            errors,
            "session_audit_index_projection_file_invalid",
            "index",
            "index file metadata is invalid",
        )
    elif status == "valid":
        _validate_valid_index_policy(index, errors)
    elif not _is_string_list(index.get("error_codes")):
        _add(
            errors,
            "session_audit_index_projection_errors_invalid",
            "index.error_codes",
            "invalid index diagnostics are malformed",
        )


def _validate_valid_index_policy(
    index: dict[str, Any], errors: list[dict[str, Any]]
) -> None:
    hashes = index.get("evidence_path_hashes")
    if (
        not isinstance(index.get("index_id"), str)
        or not re.fullmatch(r"index-[0-9a-f]{32}", index["index_id"])
        or not isinstance(index.get("entry_count"), int)
        or isinstance(index.get("entry_count"), bool)
        or index["entry_count"] < 0
        or index.get("repair_class") != "derived_metadata_only"
        or index.get("auto_repair_allowed") is not True
        or index.get("auto_repair_target") != AUTO_REPAIR_TARGET
        or index.get("not_goal_truth") is not True
        or index.get("not_validation_evidence") is not True
        or not isinstance(hashes, list)
        or any(
            not isinstance(item, str) or not SHA256_RE.fullmatch(item)
            for item in hashes
        )
    ):
        _add(
            errors,
            "session_audit_index_projection_policy_invalid",
            "index",
            "validated index projection policy is invalid",
        )
