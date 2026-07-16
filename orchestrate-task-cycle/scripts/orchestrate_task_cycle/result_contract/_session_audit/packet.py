from __future__ import annotations

# Validation is re-exported here for compatibility with existing consumers.
# ruff: noqa: F401

import functools
import hashlib
from pathlib import Path
from typing import Any

from .core import (
    CANONICAL_EVIDENCE_CLASSES,
    _add,
    _is_governed_canonical_path,
    _is_safe_relative_path,
    canonical_evidence_refs,
)
from .packet_validation import validate_session_audit_packet


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_packet_source(root: Path, packet: dict[str, Any]) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    source = packet.get("source")
    if not isinstance(source, dict) or not _is_safe_relative_path(source.get("path")):
        return [
            {
                "code": "session_audit_source_path_invalid",
                "path": "source.path",
                "detail": "source path is invalid",
            }
        ]
    relative = Path(source["path"])
    path = root / relative
    current = root
    try:
        for part in relative.parts:
            current /= part
            if current.is_symlink():
                raise ValueError("symlink path component")
        resolved = path.resolve(strict=True)
        resolved.relative_to(root.resolve())
        if not resolved.is_file():
            raise ValueError("source is not a regular file")
    except (OSError, ValueError):
        _add(
            errors,
            "session_audit_source_unavailable",
            "source.path",
            "source is unavailable, unsafe, or outside the workspace",
        )
        return errors
    try:
        stat = resolved.stat()
        actual_hash = sha256_file(resolved)
    except OSError:
        _add(
            errors,
            "session_audit_source_unavailable",
            "source.path",
            "source could not be read for verification",
        )
        return errors
    if stat.st_size != source.get("size_bytes") or actual_hash != source.get("sha256"):
        _add(
            errors,
            "session_audit_source_snapshot_mismatch",
            "source",
            "source size or SHA-256 no longer matches the packet",
        )
    return errors


@functools.lru_cache(maxsize=1)
def _bundled_projection_validator() -> Any:
    """Load the tracked producer validator that owns projection semantics."""

    from audit_session_governance.session_audit import validate_packet

    validator = validate_packet
    if not callable(validator):
        raise RuntimeError("bundled session-audit validator has no validate_packet")
    return validator


def verify_deterministic_source_projection(
    root: Path, packet: dict[str, Any]
) -> list[dict[str, Any]]:
    """Require exact parity with the bundled body-free source projection."""

    try:
        validator = _bundled_projection_validator()
        producer_errors = validator(packet, root, verify_source=True)
    except Exception:  # Fail closed if the tracked validator cannot execute.
        return [
            {
                "code": "session_audit_source_projection_validator_unavailable",
                "path": "source",
                "detail": "bundled deterministic source-projection validation was unavailable",
            }
        ]
    if producer_errors:
        return [
            {
                "code": "session_audit_source_projection_mismatch",
                "path": "source",
                "detail": "packet does not match the bundled deterministic source projection",
            }
        ]
    return []


def verify_canonical_evidence_refs(
    root: Path, packet: dict[str, Any]
) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    source = packet.get("source") if isinstance(packet.get("source"), dict) else {}
    source_path = source.get("path")
    for finding_index, finding in enumerate(packet.get("findings", [])):
        if not isinstance(finding, dict):
            continue
        if (
            finding.get("severity") != "block"
            or finding.get("evidence_class") not in CANONICAL_EVIDENCE_CLASSES
        ):
            continue
        for ref_index, ref in enumerate(canonical_evidence_refs(finding)):
            path_value = ref.get("path")
            path_label = (
                f"findings.{finding_index}.evidence.canonical_evidence_refs.{ref_index}"
            )
            if not _is_governed_canonical_path(path_value) or path_value == source_path:
                _add(
                    errors,
                    "session_audit_canonical_ref_outside_governed_artifacts",
                    path_label,
                    "canonical reference is outside the governed artifact allowlist",
                )
                continue
            relative = Path(path_value)
            path = root / relative
            current = root
            try:
                for part in relative.parts:
                    current /= part
                    if current.is_symlink():
                        raise ValueError("symlink path component")
                resolved = path.resolve(strict=True)
                resolved.relative_to(root.resolve())
                if not resolved.is_file() or sha256_file(resolved) != ref.get("sha256"):
                    raise ValueError("reference missing or hash mismatch")
            except (OSError, ValueError):
                _add(
                    errors,
                    "session_audit_canonical_ref_verification_failed",
                    path_label,
                    "canonical reference could not be independently verified",
                )
    return errors
