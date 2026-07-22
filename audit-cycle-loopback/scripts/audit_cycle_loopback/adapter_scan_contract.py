"""Versioned, read-only validation of repository adapter scan rows."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Callable


DigestFunction = Callable[[Path], str]


def _object_sha256(value: Any) -> str:
    raw = (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _sha256(value: Any) -> bool:
    return bool(
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def scan_packet_valid(value: dict[str, Any]) -> bool:
    digest = value.get("scan_packet_sha256")
    body = {key: item for key, item in value.items() if key != "scan_packet_sha256"}
    return bool(
        value.get("schema_version") == 2
        and value.get("artifact_kind") == "repo_skill_adapter_scan_packet"
        and isinstance(digest, str)
        and digest == _object_sha256(body)
    )


def _manifest_v3_matches(
    manifest: dict[str, Any], row: dict[str, Any]
) -> bool:
    direct_fields = (
        "adapter_id",
        "status",
        "implementation_path",
        "legacy_compatibility_path",
        "renderer_path",
        "decision_identity_validator_path",
        "authority_projection_path",
        "hook_contract_path",
        "code_convention_contract_path",
    )
    if any(manifest.get(field) != row.get(field) for field in direct_fields):
        return False
    if (
        manifest.get("format_version") != 3
        or row.get("manifest_format_version") != 3
        or row.get("manifest_compatibility_status") != "v3_closed"
        or manifest.get("phase_consumers") != row.get("phase_consumer_map")
        or manifest.get("phase_hooks") != row.get("phase_hook_map")
    ):
        return False
    raw_components = manifest.get("components")
    scan_components = row.get("components")
    if not isinstance(raw_components, list) or not isinstance(scan_components, list):
        return False
    normalized_scan = [
        {key: value for key, value in item.items() if key != "sha256"}
        for item in scan_components
        if isinstance(item, dict)
    ]
    if len(normalized_scan) != len(scan_components):
        return False
    def sort_key(item: dict[str, Any]) -> str:
        return str(item.get("component_id", ""))
    if sorted(raw_components, key=sort_key) != sorted(normalized_scan, key=sort_key):
        return False
    raw_closure = manifest.get("runtime_closure")
    scan_closure = row.get("runtime_closure")
    if not isinstance(raw_closure, dict) or not isinstance(scan_closure, dict):
        return False
    return all(
        raw_closure.get(field) == scan_closure.get(field)
        for field in (
            "entry_component_ids",
            "dynamic_dependency_ids",
            "unresolved_local_import_policy",
        )
    )


def _safe_current_digest(
    root: Path, raw_path: Any, expected: Any, digest_file: DigestFunction
) -> bool:
    candidate = Path(str(raw_path or ""))
    candidate = candidate if candidate.is_absolute() else root / candidate
    try:
        resolved = candidate.expanduser().resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError):
        return False
    return bool(
        resolved.is_file()
        and _sha256(expected)
        and digest_file(resolved) == expected
    )


def _v3_components_current(
    root: Path,
    row: dict[str, Any],
    digest_file: DigestFunction,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]] | None:
    fields = {
        "component_id",
        "path",
        "kind",
        "role",
        "required",
        "revision_included",
        "runtime_included",
        "architecture_audit_scope",
        "depends_on",
        "sha256",
    }
    raw = row.get("components")
    if not isinstance(raw, list) or not raw:
        return None
    by_id: dict[str, dict[str, Any]] = {}
    basis: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict) or set(item) != fields:
            return None
        component_id = item.get("component_id")
        if (
            not isinstance(component_id, str)
            or component_id in by_id
            or not _safe_current_digest(
                root, item.get("path"), item.get("sha256"), digest_file
            )
        ):
            return None
        by_id[component_id] = item
        basis.append(dict(item))
    basis.sort(key=lambda item: str(item["component_id"]))
    return basis, by_id


def _v3_closure_current(
    root: Path,
    row: dict[str, Any],
    components: dict[str, dict[str, Any]],
    digest_file: DigestFunction,
) -> str | None:
    closure = row.get("runtime_closure")
    if not isinstance(closure, dict):
        return None
    digest = closure.get("runtime_closure_sha256")
    body = {
        key: value for key, value in closure.items() if key != "runtime_closure_sha256"
    }
    if not _sha256(digest) or digest != _object_sha256(body):
        return None
    component_ids = closure.get("component_ids")
    component_hashes = closure.get("component_sha256")
    discovered = closure.get("discovered_transitive_sha256")
    paths = closure.get("paths")
    if (
        not isinstance(component_ids, list)
        or not isinstance(component_hashes, dict)
        or not isinstance(discovered, dict)
        or not isinstance(paths, list)
        or set(component_ids) != set(component_hashes)
    ):
        return None
    declared_paths: set[str] = set()
    for component_id in component_ids:
        component = components.get(str(component_id))
        if (
            component is None
            or not component.get("runtime_included")
            or component_hashes.get(component_id) != component.get("sha256")
        ):
            return None
        declared_paths.add(str(component["path"]))
    if any(
        not _safe_current_digest(root, path, expected, digest_file)
        for path, expected in discovered.items()
    ):
        return None
    if set(paths) != declared_paths | set(discovered):
        return None
    path_set = set(paths)
    edges = closure.get("internal_import_edges")
    if not isinstance(edges, list) or any(
        not isinstance(edge, dict)
        or set(edge) != {"source_path", "target_path"}
        or edge["source_path"] not in path_set
        or edge["target_path"] not in path_set
        for edge in edges
    ):
        return None
    return str(digest)


def _v3_revision_valid(
    root: Path, row: dict[str, Any], digest_file: DigestFunction
) -> bool:
    current = _v3_components_current(root, row, digest_file)
    if current is None:
        return False
    component_basis, component_by_id = current
    component_registry_sha256 = _object_sha256(component_basis)
    if row.get("component_registry_sha256") != component_registry_sha256:
        return False
    closure_digest = _v3_closure_current(
        root, row, component_by_id, digest_file
    )
    if closure_digest is None:
        return False
    basis = {
        "algorithm_revision": "repo-skill-adapter-manifest-v3-closure-v1",
        "manifest_sha256": row.get("manifest_sha256"),
        "components": [
            item for item in component_basis if item.get("revision_included")
        ],
        "component_registry_sha256": component_registry_sha256,
        "runtime_closure_sha256": closure_digest,
        "hook_contract_sha256": row.get("hook_contract_sha256"),
        "code_convention_contract_sha256": row.get(
            "code_convention_contract_sha256"
        ),
        "phase_consumer_map": row.get("phase_consumer_map"),
        "phase_hook_map": row.get("phase_hook_map"),
        "interpreter_abi": sys.implementation.cache_tag,
    }
    return bool(
        _sha256(row.get("adapter_revision_sha256"))
        and row["adapter_revision_sha256"] == _object_sha256(basis)
    )


def _legacy_revision_valid(row: dict[str, Any]) -> bool:
    basis = {
        "adapter_id": row.get("adapter_id"),
        "manifest_sha256": row.get("manifest_sha256"),
        "implementation_sha256": row.get("implementation_sha256"),
        "legacy_compatibility_sha256": row.get("legacy_compatibility_sha256"),
        "renderer_sha256": row.get("renderer_sha256"),
        "decision_identity_validator_sha256": row.get(
            "decision_identity_validator_sha256"
        ),
        "phase_consumer_map": row.get("phase_consumer_map"),
        "phase_hook_map": row.get("phase_hook_map"),
    }
    if row.get("authority_projection_path") is not None:
        basis["authority_projection_sha256"] = row.get(
            "authority_projection_sha256"
        )
    revision = str(row.get("adapter_revision_sha256") or "").lower()
    return _sha256(revision) and revision == _object_sha256(basis)


def _legacy_manifest_matches(
    manifest: dict[str, Any], row: dict[str, Any]
) -> bool:
    return all(
        manifest.get(manifest_field) == row.get(row_field)
        for manifest_field, row_field in (
            ("adapter_id", "adapter_id"),
            ("status", "status"),
            ("implementation_path", "implementation_path"),
            ("legacy_compatibility_path", "legacy_compatibility_path"),
            ("renderer_path", "renderer_path"),
            ("decision_identity_validator_path", "decision_identity_validator_path"),
            ("authority_projection_path", "authority_projection_path"),
            ("phase_consumers", "phase_consumer_map"),
            ("phase_hooks", "phase_hook_map"),
        )
    )


def adapter_revision_valid(
    root: Path,
    row: dict[str, Any],
    manifest_path: Path,
    digest_file: DigestFunction,
) -> bool:
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return False
    if row.get("static_validation", {}).get("status") != "pass":
        return False
    if row.get("manifest_format_version") == 3:
        return _manifest_v3_matches(manifest, row) and _v3_revision_valid(
            root, row, digest_file
        )
    return _legacy_manifest_matches(manifest, row) and _legacy_revision_valid(row)


__all__ = ("adapter_revision_valid", "scan_packet_valid")
