"""Application services for session inspection and derived-index repair."""

from __future__ import annotations

import json
from pathlib import Path
import stat
from typing import Any

from .session_common import (
    AuditError,
    DuplicateKeyError,
    MAX_BYTES,
    VERSION,
    atomic_write,
    audit_dir,
    canonical,
    derived_id,
    digest,
    locked,
    read_snapshot,
    root_path,
    safe_file,
)
from .session_packets import build_packet, validate_packet
from .session_parsing import strict_json_object

def inspect(
    root_raw: str | Path,
    source_raw: str | Path,
    *,
    tool: str,
    session_id: str | None = None,
    cycle_id: str | None = None,
    task_id: str | None = None,
    max_bytes: int = MAX_BYTES,
) -> tuple[dict[str, Any], Path]:
    root = root_path(root_raw)
    source, relative = safe_file(root, source_raw)
    packet = build_packet(
        source, relative, tool=tool, session_id=session_id,
        cycle_id=cycle_id, task_id=task_id, max_bytes=max_bytes,
    )
    errors = validate_packet(packet, root)
    if errors:
        raise AuditError("generated packet is invalid: " + "; ".join(errors))
    directory = audit_dir(root)
    output = directory / f"{packet['audit_id']}.json"
    with locked(directory, packet["session_id"]):
        atomic_write(output, canonical(packet), immutable=True)
    return packet, output


def load_json(path: Path) -> tuple[Any, bytes]:
    data, _, _ = read_snapshot(path, 2 * 1024 * 1024)
    if data is None:
        raise AuditError("JSON artifact exceeds size limit")
    try:
        return json.loads(
            data.decode("utf-8", errors="strict"),
            object_pairs_hook=strict_json_object,
        ), data
    except (UnicodeDecodeError, json.JSONDecodeError, DuplicateKeyError) as exc:
        raise AuditError(f"invalid strict JSON artifact: {exc}") from exc


def validate_file(
    root_raw: str | Path, packet_raw: str | Path
) -> tuple[dict[str, Any], list[str]]:
    root = root_path(root_raw)
    path, _ = safe_file(root, packet_raw, packet=True)
    packet, _ = load_json(path)
    return packet, validate_packet(packet, root)


def rebuild_index(root_raw: str | Path) -> tuple[dict[str, Any], Path]:
    root = root_path(root_raw)
    directory = audit_dir(root)
    entries: list[dict[str, Any]] = []
    evidence: list[str] = []
    with locked(directory, "index"):
        for path in sorted(directory.glob("audit-*.json")):
            if path.is_symlink() or not path.is_file():
                raise AuditError("index input must be a regular non-symlink packet")
            packet, packet_bytes = load_json(path)
            errors = validate_packet(packet, root)
            if errors:
                raise AuditError(f"invalid packet {path.name}: {'; '.join(errors)}")
            relative = path.relative_to(root).as_posix()
            entries.append({
                "audit_id": packet["audit_id"],
                "path": relative,
                "packet_sha256": digest(packet_bytes),
                "session_id": packet["session_id"],
                "tool": packet["tool"],
                "capture_status": packet["capture_status"],
                "binding_status": packet["binding"]["status"],
                "consumable": packet["consumable"],
            })
            evidence.append(relative)
        entries.sort(key=lambda item: item["audit_id"])
        evidence.sort()
        index: dict[str, Any] = {
            "format_version": VERSION,
            "artifact_kind": "session_governance_audit_index",
            "not_goal_truth": True,
            "not_validation_evidence": True,
            "repair_class": "derived_metadata_only",
            "auto_repair_allowed": True,
            "entries": entries,
            "evidence_paths": evidence,
        }
        index["index_id"] = derived_id("index", index)
        output = directory / "index.json"
        atomic_write(output, canonical(index))
    return index, output


def _load_mode_resolution_validator() -> Any:
    try:
        from orchestrate_task_cycle.mode_profile import validate_resolution
    except (ImportError, AttributeError) as exc:
        raise AuditError("tracked mode-profile validator is unavailable") from exc
    return validate_resolution


def auto_rebuild_index(
    root_raw: str | Path,
    resolution_raw: str | Path,
) -> tuple[dict[str, Any], Path]:
    """Perform the sole unattended repair under a validated mode resolution."""

    root = root_path(root_raw)
    resolution_path, _ = safe_file(root, resolution_raw)
    resolution_value, _ = load_json(resolution_path)
    try:
        resolution = _load_mode_resolution_validator()(resolution_value)
    except (OSError, ValueError) as exc:
        raise AuditError(f"mode resolution is invalid: {exc}") from exc
    effective = resolution.get("effective_profile")
    repairs = effective.get("allowed_repairs") if isinstance(effective, dict) else None
    if (
        resolution.get("activation_source") == "default"
        or resolution.get("repair_receipt_required") is not True
        or resolution.get("allowed_effects", {}).get("derived_metadata_repair_allowed") is not True
        or repairs
        != [
            {
                "operation": "rebuild_index",
                "target": ".task/session_audit/index.json",
            }
        ]
    ):
        raise AuditError("mode resolution does not authorize exact audit-index repair")

    index_path = root / ".task" / "session_audit" / "index.json"
    before_sha256: str | None = None
    if index_path.exists() or index_path.is_symlink():
        mode = index_path.lstat().st_mode
        if stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
            raise AuditError("session-audit index target is unsafe")
        before_sha256 = digest(index_path.read_bytes())

    index, output = rebuild_index(root)
    after_sha256 = digest(output.read_bytes())
    receipt: dict[str, Any] = {
        "format_version": 1,
        "artifact_kind": "workflow_mode_repair_receipt",
        "status": "complete",
        "resolution_id": resolution["resolution_id"],
        "activation_source": resolution["activation_source"],
        "operation": "rebuild_index",
        "target": ".task/session_audit/index.json",
        "before_sha256": before_sha256,
        "after_sha256": after_sha256,
        "index_id": index["index_id"],
        "not_goal_truth": True,
        "not_validation_evidence": True,
    }
    receipt["receipt_id"] = derived_id("repair-receipt", receipt)
    return receipt, output
