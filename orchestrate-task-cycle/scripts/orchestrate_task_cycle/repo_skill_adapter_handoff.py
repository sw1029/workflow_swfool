"""Freshness validation and consumer handoff for registered repo adapters."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .repo_skill_adapter_manifest import (
    COMPONENT_PATH_FIELDS,
    _adapter_row,
    _file_sha256,
    _safe_regular_file,
)


RECOMPILED_ROW_FIELDS = (
    "adapter_id",
    "status",
    "implementation_path",
    "implementation_sha256",
    "legacy_compatibility_path",
    "legacy_compatibility_sha256",
    "renderer_path",
    "renderer_sha256",
    "decision_identity_validator_path",
    "decision_identity_validator_sha256",
    "authority_projection_path",
    "authority_projection_sha256",
    "phase_consumer_map",
    "phase_hook_map",
    "manifest_format_version",
    "manifest_compatibility_status",
    "components",
    "component_registry_sha256",
    "runtime_closure",
    "hook_contract_path",
    "hook_contract_sha256",
    "hook_contracts",
    "code_convention_contract_path",
    "code_convention_contract_sha256",
    "adapter_revision_sha256",
)

HANDOFF_ROW_FIELDS = (
    "adapter_id",
    "implementation_path",
    "implementation_sha256",
    "legacy_compatibility_path",
    "legacy_compatibility_sha256",
    "renderer_path",
    "renderer_sha256",
    "decision_identity_validator_path",
    "decision_identity_validator_sha256",
    "authority_projection_path",
    "authority_projection_sha256",
    "manifest_path",
    "manifest_sha256",
    "adapter_revision_sha256",
    "manifest_format_version",
    "manifest_compatibility_status",
    "components",
    "component_registry_sha256",
    "runtime_closure",
    "hook_contract_path",
    "hook_contract_sha256",
    "hook_contracts",
    "code_convention_contract_path",
    "code_convention_contract_sha256",
)


def _failure(
    status: str, *, registered: bool, classification: str
) -> dict[str, Any]:
    return {
        "status": status,
        "adapter_registered": registered,
        "adapter_loaded": False,
        "classification": classification,
    }


def _select_adapter(
    scan_packet: dict[str, Any], *, phase: str, consumer_id: str
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    container = scan_packet.get("repo_skill_adapter_packet")
    rows = container.get("adapters") if isinstance(container, dict) else None
    if not isinstance(rows, list):
        return None, _failure(
            "invalid_scan",
            registered=False,
            classification="adapter_scan_contract_defect",
        )
    active_rows = [
        row for row in rows if isinstance(row, dict) and row.get("status") == "active"
    ]
    malformed = [
        row
        for row in active_rows
        if not isinstance(row.get("phase_consumer_map"), dict)
        or any(
            not isinstance(value, list) for value in row["phase_consumer_map"].values()
        )
    ]
    if malformed:
        return None, _failure(
            "invalid_scan",
            registered=True,
            classification="adapter_scan_contract_defect",
        )
    matches = [
        row
        for row in active_rows
        if consumer_id in (row.get("phase_consumer_map") or {}).get(phase, [])
    ]
    if not matches:
        return None, _failure(
            "not_registered", registered=False, classification="adapter_absent"
        )
    if len(matches) != 1:
        return None, _failure(
            "ambiguous", registered=True, classification="adapter_wiring_defect"
        )
    return matches[0], None


def _component_staleness(repo_root: Path, row: dict[str, Any]) -> list[str]:
    stale: list[str] = []
    for path_field, hash_field in COMPONENT_PATH_FIELDS:
        if row.get(path_field) is None and row.get(hash_field) is None:
            continue
        try:
            path, relative = _safe_regular_file(
                repo_root, str(row.get(path_field) or "")
            )
        except (OSError, ValueError):
            stale.append(path_field)
            continue
        if relative != row.get(path_field) or _file_sha256(path) != row.get(hash_field):
            stale.append(path_field)
    components = row.get("components")
    if not isinstance(components, list):
        return stale
    for component in components:
        if not isinstance(component, dict):
            stale.append("components")
            continue
        path_value = str(component.get("path") or "")
        try:
            path, relative = _safe_regular_file(repo_root, path_value)
        except (OSError, ValueError):
            stale.append(f"component:{component.get('component_id')}")
            continue
        if relative != path_value or _file_sha256(path) != component.get("sha256"):
            stale.append(f"component:{component.get('component_id')}")
    return stale


def _recompiled_staleness(repo_root: Path, row: dict[str, Any]) -> list[str]:
    try:
        manifest, relative_manifest = _safe_regular_file(
            repo_root, str(row.get("manifest_path") or "")
        )
        stale = []
        if relative_manifest != row.get("manifest_path") or _file_sha256(
            manifest
        ) != row.get("manifest_sha256"):
            stale.append("manifest_path")
        current_row = _adapter_row(repo_root, manifest)
        stale.extend(
            field
            for field in RECOMPILED_ROW_FIELDS
            if current_row.get(field) != row.get(field)
        )
        return stale
    except (OSError, ValueError):
        return ["manifest_path"]


def _handoff_packet(
    row: dict[str, Any], *, phase: str, consumer_id: str, stale: list[str]
) -> dict[str, Any]:
    ready = bool(row.get("static_validation", {}).get("status") == "pass" and not stale)
    result = {
        "status": "ready" if ready else "registered_unavailable",
        **{field: row.get(field) for field in HANDOFF_ROW_FIELDS},
        "adapter_registered": True,
        "adapter_loaded": False,
        "classification": "registered_adapter_ready"
        if ready
        else "adapter_wiring_defect",
        "phase": phase,
        "consumer_id": consumer_id,
        "stale_components": sorted(set(stale)),
        "authority_granted": False,
    }
    return result


def registered_adapter_handoff(
    root: str | Path,
    scan_packet: dict[str, Any],
    *,
    phase: str,
    consumer_id: str,
) -> dict[str, Any]:
    repo_root = Path(root).expanduser().resolve(strict=True)
    row, failure = _select_adapter(
        scan_packet, phase=phase, consumer_id=consumer_id
    )
    if failure is not None:
        return failure
    assert row is not None
    stale = _component_staleness(repo_root, row)
    stale.extend(_recompiled_staleness(repo_root, row))
    return _handoff_packet(
        row, phase=phase, consumer_id=consumer_id, stale=stale
    )


__all__ = ("registered_adapter_handoff",)
