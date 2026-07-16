from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .core import (
    AUTO_REPAIR_TARGET,
    MAX_PACKET_BYTES,
    SHA256_RE,
    _add,
)
from .packet import (
    validate_session_audit_packet,
    verify_canonical_evidence_refs,
    verify_deterministic_source_projection,
    verify_packet_source,
)
from .projection import (
    _invalid_projection,
    _safe_file_metadata,
    project_valid_packet,
    validate_session_audit_index,
)


def _index_metadata(root: Path, directory: Path) -> dict[str, Any]:
    path = directory / "index.json"
    if path.is_symlink() or not path.is_file():
        return {}
    metadata = _safe_file_metadata(root, path)
    if path.stat().st_size > MAX_PACKET_BYTES:
        return {
            **metadata,
            "contract_status": "invalid",
            "error_codes": ["session_audit_index_oversize"],
        }
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            **metadata,
            "contract_status": "malformed",
            "error_codes": ["session_audit_index_malformed"],
        }
    errors = validate_session_audit_index(root, value)
    if errors:
        return {
            **metadata,
            "contract_status": "invalid",
            "error_codes": sorted({str(error.get("code")) for error in errors}),
        }
    entries = value.get("entries") if isinstance(value.get("entries"), list) else []
    return {
        **metadata,
        "contract_status": "valid",
        "index_id": value.get("index_id"),
        "entry_count": len(entries),
        "repair_class": "derived_metadata_only",
        "auto_repair_allowed": True,
        "auto_repair_target": AUTO_REPAIR_TARGET,
        "not_goal_truth": True,
        "not_validation_evidence": True,
        "evidence_path_hashes": [
            hashlib.sha256(str(path_value).encode("utf-8")).hexdigest()
            for path_value in value.get("evidence_paths", [])
        ],
    }


def collect_session_audit_directory(root: Path, max_files: int) -> dict[str, Any]:
    """Collect only validated packet projections and body-free invalid-file diagnostics."""

    root = root.resolve()
    directory = root / ".task" / "session_audit"
    base: dict[str, Any] = {
        "artifact_kind": "session_audit_collection_projection",
        "not_goal_truth": True,
        "not_validation_evidence": True,
        "directory": {"path": ".task/session_audit", "exists": directory.exists()},
        "packet_count": 0,
        "total_packet_count": 0,
        "scanned_packet_count": 0,
        "truncated_count": 0,
        "truncated": False,
        "valid_count": 0,
        "invalid_count": 0,
        "malformed_count": 0,
        "packets": [],
        "invalid_packets": [],
        "index": {},
    }
    if not directory.exists():
        return base
    if directory.is_symlink() or not directory.is_dir():
        base["directory"]["status"] = "unsafe_or_not_directory"
        base["packet_count"] = 1
        base["total_packet_count"] = 1
        base["scanned_packet_count"] = 1
        base["invalid_count"] = 1
        base["invalid_packets"] = [
            {
                "contract_status": "unsafe",
                "file": {"path": ".task/session_audit"},
                "error_codes": ["session_audit_directory_unsafe"],
            }
        ]
        return base
    try:
        directory.resolve().relative_to(root)
    except ValueError:
        base["directory"]["status"] = "outside_workspace"
        base["packet_count"] = 1
        base["total_packet_count"] = 1
        base["scanned_packet_count"] = 1
        base["invalid_count"] = 1
        base["invalid_packets"] = [
            {
                "contract_status": "unsafe",
                "file": {"path": ".task/session_audit"},
                "error_codes": ["session_audit_directory_outside_workspace"],
            }
        ]
        return base

    candidates = [
        path for path in directory.glob("*.json") if path.name != "index.json"
    ]

    def safe_mtime(path: Path) -> float:
        if path.is_symlink():
            return 0
        try:
            return path.stat().st_mtime
        except OSError:
            return 0

    ordered = sorted(candidates, key=safe_mtime, reverse=True)
    selected = ordered[: max(0, max_files)]
    base["packet_count"] = len(ordered)
    base["total_packet_count"] = len(ordered)
    base["scanned_packet_count"] = len(selected)
    base["truncated_count"] = len(ordered) - len(selected)
    base["truncated"] = bool(base["truncated_count"])
    for path in selected:
        relative = {"path": path.relative_to(root).as_posix()}
        if path.is_symlink() or not path.is_file():
            base["invalid_packets"].append(
                _invalid_projection(
                    relative, "unsafe", [{"code": "session_audit_packet_file_unsafe"}]
                )
            )
            continue
        try:
            path.resolve().relative_to(directory.resolve())
            metadata = _safe_file_metadata(root, path)
            if path.stat().st_size > MAX_PACKET_BYTES:
                base["invalid_packets"].append(
                    _invalid_projection(
                        metadata, "invalid", [{"code": "session_audit_packet_oversize"}]
                    )
                )
                continue
            packet = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            metadata = relative
            try:
                metadata = _safe_file_metadata(root, path)
            except OSError:
                pass
            base["invalid_packets"].append(
                _invalid_projection(
                    metadata, "malformed", [{"code": "session_audit_packet_malformed"}]
                )
            )
            continue
        errors = validate_session_audit_packet(packet)
        if (
            isinstance(packet, dict)
            and packet.get("audit_id")
            and path.name != f"{packet['audit_id']}.json"
        ):
            _add(
                errors,
                "session_audit_filename_mismatch",
                "audit_id",
                "packet filename must equal its content-derived audit_id",
            )
        if not errors and isinstance(packet, dict):
            errors.extend(verify_packet_source(root, packet))
        if not errors and isinstance(packet, dict):
            errors.extend(verify_deterministic_source_projection(root, packet))
        if not errors and isinstance(packet, dict):
            errors.extend(verify_canonical_evidence_refs(root, packet))
        if errors:
            base["invalid_packets"].append(
                _invalid_projection(metadata, "invalid", errors)
            )
        else:
            base["packets"].append(project_valid_packet(packet, metadata))
    base["valid_count"] = len(base["packets"])
    base["invalid_count"] = len(base["invalid_packets"])
    base["malformed_count"] = sum(
        1
        for packet in base["invalid_packets"]
        if packet.get("contract_status") == "malformed"
    )
    base["index"] = _index_metadata(root, directory)
    return base


def sanitize_collection_summary(
    value: Any, max_packets: int | None = None
) -> dict[str, Any] | None:
    """Re-project a collector summary before embedding it in a subskill packet."""

    if (
        not isinstance(value, dict)
        or value.get("artifact_kind") != "session_audit_collection_projection"
    ):
        return None
    result: dict[str, Any] = {
        "artifact_kind": "session_audit_collection_projection",
        "not_goal_truth": value.get("not_goal_truth") is True,
        "not_validation_evidence": value.get("not_validation_evidence") is True,
        "packet_count": value.get("packet_count")
        if isinstance(value.get("packet_count"), int)
        else 0,
        "total_packet_count": value.get("total_packet_count")
        if isinstance(value.get("total_packet_count"), int)
        else 0,
        "scanned_packet_count": 0,
        "truncated_count": value.get("truncated_count")
        if isinstance(value.get("truncated_count"), int)
        else 0,
        "truncated": value.get("truncated") is True,
        "valid_count": 0,
        "invalid_count": 0,
        "malformed_count": 0,
        "packets": [],
        "invalid_packets": [],
        "index": {},
    }
    packet_limit = max_packets if max_packets is not None else 10_000
    valid_source = (
        value.get("packets", []) if isinstance(value.get("packets"), list) else []
    )
    invalid_source = (
        value.get("invalid_packets", [])
        if isinstance(value.get("invalid_packets"), list)
        else []
    )
    selected_valid = valid_source[:packet_limit]
    selected_invalid = invalid_source[: max(0, packet_limit - len(selected_valid))]
    omitted = (
        len(valid_source)
        + len(invalid_source)
        - len(selected_valid)
        - len(selected_invalid)
    )
    result["truncated_count"] += omitted
    result["truncated"] = bool(result["truncated_count"])
    for packet in selected_valid:
        if not isinstance(packet, dict):
            continue
        result["packets"].append(_sanitize_valid_packet(packet))
    for packet in selected_invalid:
        if isinstance(packet, dict):
            result["invalid_packets"].append(_sanitize_invalid_packet(packet))
    result["valid_count"] = len(result["packets"])
    result["invalid_count"] = len(result["invalid_packets"])
    result["malformed_count"] = sum(
        1
        for packet in result["invalid_packets"]
        if packet.get("contract_status") == "malformed"
    )
    result["scanned_packet_count"] = result["valid_count"] + result["invalid_count"]
    index = value.get("index")
    if isinstance(index, dict):
        result["index"] = _sanitize_index(index)
    return result


def _sanitize_valid_packet(packet: dict[str, Any]) -> dict[str, Any]:
    projected = {
        key: packet.get(key)
        for key in (
            "contract_status",
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
            "source_projection_verified",
            "canonical_refs_verified",
            "consumable",
            "not_goal_truth",
            "not_validation_evidence",
            "repair_class",
            "auto_repair_allowed",
            "auto_repair_target",
        )
    }
    file_metadata = packet.get("file")
    projected["file"] = (
        {
            key: file_metadata.get(key)
            for key in ("path", "sha256", "size_bytes")
            if key in file_metadata
        }
        if isinstance(file_metadata, dict)
        else {}
    )
    binding = packet.get("binding")
    projected["binding"] = (
        {
            key: binding.get(key)
            for key in ("status", "cycle_id", "task_id")
            if key in binding
        }
        if isinstance(binding, dict)
        else {}
    )
    event_counts = packet.get("event_counts")
    projected["event_counts"] = (
        {
            str(key): count
            for key, count in event_counts.items()
            if isinstance(count, int) and not isinstance(count, bool) and count >= 0
        }
        if isinstance(event_counts, dict)
        else {}
    )
    timestamp_bounds = packet.get("timestamp_bounds")
    projected["timestamp_bounds"] = (
        {
            key: timestamp_bounds.get(key)
            for key in ("first", "last")
            if key in timestamp_bounds
        }
        if isinstance(timestamp_bounds, dict)
        else {}
    )
    hashes = packet.get("evidence_path_hashes")
    projected["evidence_path_hashes"] = (
        [
            str(value)
            for value in hashes
            if isinstance(value, str) and SHA256_RE.fullmatch(value)
        ]
        if isinstance(hashes, list)
        else []
    )
    projected["findings"] = [
        {
            key: finding.get(key)
            for key in (
                "code",
                "severity",
                "evidence_class",
                "resolved",
                "canonical_evidence_ref_hashes",
            )
        }
        for finding in packet.get("findings", [])
        if isinstance(finding, dict)
    ]
    return projected


def _sanitize_invalid_packet(packet: dict[str, Any]) -> dict[str, Any]:
    metadata = packet.get("file")
    return {
        "contract_status": packet.get("contract_status"),
        "file": (
            {
                key: metadata.get(key)
                for key in ("path", "sha256", "size_bytes")
                if key in metadata
            }
            if isinstance(metadata, dict)
            else {}
        ),
        "error_codes": (
            [
                str(code)
                for code in packet.get("error_codes", [])
                if isinstance(code, str) and code.strip()
            ]
            if isinstance(packet.get("error_codes"), list)
            else []
        ),
    }


def _sanitize_index(index: dict[str, Any]) -> dict[str, Any]:
    return {
        key: index.get(key)
        for key in (
            "path",
            "sha256",
            "size_bytes",
            "contract_status",
            "error_codes",
            "index_id",
            "entry_count",
            "repair_class",
            "auto_repair_allowed",
            "auto_repair_target",
            "not_goal_truth",
            "not_validation_evidence",
            "evidence_path_hashes",
        )
        if key in index
    }
