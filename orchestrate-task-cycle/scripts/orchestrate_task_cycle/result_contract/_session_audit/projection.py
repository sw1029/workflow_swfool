from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from .core import (
    AUDIT_ID_RE,
    AUTO_REPAIR_TARGET,
    BINDING_STATUSES,
    CAPTURE_STATUSES,
    FORMAT_VERSION,
    INDEX_ARTIFACT_KIND,
    SAFE_ID_RE,
    SHA256_RE,
    TOOLS,
    _add,
    _is_safe_relative_path,
    canonical_evidence_ref_hashes,
    expected_index_id,
)
from .packet import sha256_file


def _safe_file_metadata(root: Path, path: Path) -> dict[str, Any]:
    stat = path.stat()
    return {
        "path": path.relative_to(root).as_posix(),
        "sha256": sha256_file(path),
        "size_bytes": stat.st_size,
    }


def project_valid_packet(
    packet: dict[str, Any], file_metadata: dict[str, Any]
) -> dict[str, Any]:
    binding = packet.get("binding") if isinstance(packet.get("binding"), dict) else {}
    source = packet.get("source") if isinstance(packet.get("source"), dict) else {}
    findings = []
    for finding in packet.get("findings", []):
        if not isinstance(finding, dict):
            continue
        findings.append(
            {
                "code": finding.get("code"),
                "severity": finding.get("severity"),
                "evidence_class": finding.get("evidence_class"),
                "resolved": finding.get("resolved") is True,
                "canonical_evidence_ref_hashes": canonical_evidence_ref_hashes(finding),
            }
        )
    return {
        "contract_status": "valid",
        "file": file_metadata,
        "format_version": packet.get("format_version"),
        "artifact_kind": packet.get("artifact_kind"),
        "parser_version": packet.get("parser_version"),
        "audit_id": packet.get("audit_id"),
        "tool": packet.get("tool"),
        "session_id": packet.get("session_id"),
        "source_sha256": source.get("sha256"),
        "source_size_bytes": source.get("size_bytes"),
        "capture_mode": packet.get("capture_mode"),
        "capture_status": packet.get("capture_status"),
        "integrity_status": packet.get("integrity_status"),
        "binding": {
            key: binding[key]
            for key in ("status", "cycle_id", "task_id")
            if key in binding
        },
        "source_projection_verified": True,
        "canonical_refs_verified": True,
        "consumable": packet.get("consumable"),
        "not_goal_truth": packet.get("not_goal_truth"),
        "not_validation_evidence": packet.get("not_validation_evidence"),
        "repair_class": packet.get("repair_class"),
        "auto_repair_allowed": packet.get("auto_repair_allowed"),
        "auto_repair_target": AUTO_REPAIR_TARGET
        if packet.get("auto_repair_allowed") is True
        else None,
        "event_counts": packet.get("event_counts"),
        "timestamp_bounds": packet.get("timestamp_bounds"),
        "evidence_path_hashes": [
            hashlib.sha256(str(value).encode("utf-8")).hexdigest()
            for value in packet.get("evidence_paths", [])
        ],
        "findings": findings,
    }


def _invalid_projection(
    file_metadata: dict[str, Any],
    status: str,
    errors: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "contract_status": status,
        "file": file_metadata,
        "error_codes": sorted({str(error.get("code")) for error in errors}),
    }


def validate_session_audit_index(root: Path, value: Any) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    required = {
        "format_version",
        "artifact_kind",
        "not_goal_truth",
        "not_validation_evidence",
        "repair_class",
        "auto_repair_allowed",
        "entries",
        "evidence_paths",
        "index_id",
    }
    if not isinstance(value, dict) or set(value) != required:
        return [
            {
                "code": "session_audit_index_schema_invalid",
                "path": "index.json",
                "detail": "index schema is not closed",
            }
        ]
    _validate_index_header(value, errors)
    entries = value.get("entries")
    evidence_paths = value.get("evidence_paths")
    if not isinstance(entries, list) or not isinstance(evidence_paths, list):
        _add(
            errors,
            "session_audit_index_entries_invalid",
            "index.json",
            "index entries and evidence_paths must be lists",
        )
        return errors
    expected_paths = _validate_index_entries(root, entries, errors)
    if entries != sorted(
        entries,
        key=lambda item: str(item.get("audit_id")) if isinstance(item, dict) else "",
    ):
        _add(
            errors,
            "session_audit_index_order_invalid",
            "entries",
            "index entries must be audit_id sorted",
        )
    if evidence_paths != sorted(expected_paths):
        _add(
            errors,
            "session_audit_index_evidence_invalid",
            "evidence_paths",
            "index evidence paths must exactly match indexed packets",
        )
    return errors


def _validate_index_header(value: dict[str, Any], errors: list[dict[str, Any]]) -> None:
    if (
        value.get("format_version") != FORMAT_VERSION
        or value.get("artifact_kind") != INDEX_ARTIFACT_KIND
    ):
        _add(
            errors,
            "session_audit_index_identity_invalid",
            "index.json",
            "index version or kind is invalid",
        )
    if (
        value.get("not_goal_truth") is not True
        or value.get("not_validation_evidence") is not True
    ):
        _add(
            errors,
            "session_audit_index_truth_flags_invalid",
            "index.json",
            "index truth flags are invalid",
        )
    if (
        value.get("repair_class") != "derived_metadata_only"
        or value.get("auto_repair_allowed") is not True
    ):
        _add(
            errors,
            "session_audit_index_repair_scope_invalid",
            "index.json",
            "only the derived index is auto-repairable",
        )
    if value.get("index_id") != expected_index_id(value):
        _add(
            errors,
            "session_audit_index_id_mismatch",
            "index.json",
            "index_id does not match canonical index content",
        )


def _validate_index_entries(
    root: Path, entries: list[Any], errors: list[dict[str, Any]]
) -> list[str]:
    expected_paths: list[str] = []
    seen: set[str] = set()
    for index, entry in enumerate(entries):
        path = f"entries.{index}"
        expected_path = _validate_index_entry(root, path, entry, seen, errors)
        if expected_path is not None:
            expected_paths.append(expected_path)
    return expected_paths


def _validate_index_entry(
    root: Path,
    path: str,
    entry: Any,
    seen: set[str],
    errors: list[dict[str, Any]],
) -> str | None:
    expected_fields = {
        "audit_id",
        "path",
        "packet_sha256",
        "session_id",
        "tool",
        "capture_status",
        "binding_status",
        "consumable",
    }
    if not isinstance(entry, dict) or set(entry) != expected_fields:
        _add(
            errors,
            "session_audit_index_entry_invalid",
            path,
            "index entry schema is invalid",
        )
        return None
    audit_id = entry.get("audit_id")
    expected_path = f".task/session_audit/{audit_id}.json"
    if (
        not isinstance(audit_id, str)
        or not AUDIT_ID_RE.fullmatch(audit_id)
        or audit_id in seen
    ):
        _add(
            errors,
            "session_audit_index_entry_id_invalid",
            path,
            "index audit_id is invalid or duplicated",
        )
    seen.add(str(audit_id))
    if entry.get("path") != expected_path or not _is_safe_relative_path(
        entry.get("path")
    ):
        _add(
            errors,
            "session_audit_index_entry_path_invalid",
            path,
            "index packet path is invalid",
        )
    if not isinstance(entry.get("packet_sha256"), str) or not SHA256_RE.fullmatch(
        entry["packet_sha256"]
    ):
        _add(
            errors,
            "session_audit_index_entry_hash_invalid",
            path,
            "index packet hash is invalid",
        )
    if not isinstance(entry.get("session_id"), str) or not SAFE_ID_RE.fullmatch(
        entry["session_id"]
    ):
        _add(
            errors,
            "session_audit_index_entry_session_invalid",
            path,
            "index session_id is invalid",
        )
    if (
        entry.get("tool") not in TOOLS
        or entry.get("capture_status") not in CAPTURE_STATUSES
        or entry.get("binding_status") not in BINDING_STATUSES
    ):
        _add(
            errors,
            "session_audit_index_entry_vocabulary_invalid",
            path,
            "index entry vocabulary is invalid",
        )
    if not isinstance(entry.get("consumable"), bool):
        _add(
            errors,
            "session_audit_index_entry_consumable_invalid",
            path,
            "index consumable flag is invalid",
        )
    packet_path = root / expected_path
    try:
        if (
            packet_path.is_symlink()
            or not packet_path.is_file()
            or sha256_file(packet_path) != entry.get("packet_sha256")
        ):
            raise OSError("packet unavailable or hash mismatch")
    except OSError:
        _add(
            errors,
            "session_audit_index_entry_packet_mismatch",
            path,
            "index entry does not match its packet file",
        )
    return expected_path
