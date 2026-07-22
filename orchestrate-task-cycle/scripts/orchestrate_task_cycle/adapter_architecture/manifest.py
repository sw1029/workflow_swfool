"""Strict manifest-v3 component, hook, and revision contract compiler."""

from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any

from .contracts import file_sha256, object_sha256, safe_regular_file
from .graph import strongly_connected_components
from .runtime_closure import compile_runtime_closure


MANIFEST_V3_REVISION = "repo-skill-adapter-manifest-v3-closure-v1"
COMPONENT_FIELDS = {
    "component_id",
    "path",
    "kind",
    "role",
    "required",
    "revision_included",
    "runtime_included",
    "architecture_audit_scope",
    "depends_on",
}
HOOK_FIELDS = {
    "hook_id",
    "input_schema_id",
    "output_schema_id",
    "phases",
    "consumer_ids",
    "side_effect_class",
    "owner",
    "fail_policy",
}


def _strings(value: Any) -> bool:
    return isinstance(value, list) and all(
        isinstance(item, str) and bool(item.strip()) for item in value
    ) and len(set(value)) == len(value)


def _component_rows(
    root: Path, manifest: dict[str, Any], errors: list[str]
) -> list[dict[str, Any]]:
    raw = manifest.get("components")
    if not isinstance(raw, list) or not raw:
        errors.append("component_registry_invalid")
        return []
    rows: list[dict[str, Any]] = []
    ids: set[str] = set()
    paths: set[str] = set()
    for index, item in enumerate(raw):
        label = f"components[{index}]"
        if not isinstance(item, dict) or set(item) != COMPONENT_FIELDS:
            errors.append(f"{label}:closed_schema_invalid")
            continue
        component_id = str(item.get("component_id") or "").strip()
        kind = str(item.get("kind") or "").strip()
        role = str(item.get("role") or "").strip()
        if not component_id or component_id in ids:
            errors.append(f"{label}:component_id_invalid")
            continue
        if not kind or not role:
            errors.append(f"{label}:kind_or_role_invalid")
        if any(
            type(item.get(field)) is not bool
            for field in (
                "required",
                "revision_included",
                "runtime_included",
                "architecture_audit_scope",
            )
        ):
            errors.append(f"{label}:boolean_field_invalid")
        if not _strings(item.get("depends_on")):
            errors.append(f"{label}:depends_on_invalid")
        try:
            path, relative = safe_regular_file(root, str(item.get("path") or ""))
            digest = file_sha256(path)
        except (OSError, ValueError) as exc:
            errors.append(f"{label}:path_{type(exc).__name__}")
            continue
        if relative in paths:
            errors.append(f"{label}:component_path_duplicate")
        ids.add(component_id)
        paths.add(relative)
        rows.append(
            {
                **item,
                "component_id": component_id,
                "path": relative,
                "kind": kind,
                "role": role,
                "depends_on": list(item["depends_on"]),
                "sha256": digest,
            }
        )
    by_id = {row["component_id"]: row for row in rows}
    for row in rows:
        unknown = sorted(set(row["depends_on"]) - set(by_id))
        if unknown:
            errors.append(
                f"component_dependency_unknown:{row['component_id']}:{','.join(unknown)}"
            )
    graph_edges = [
        (row["component_id"], dependency)
        for row in rows
        for dependency in row["depends_on"]
        if dependency in by_id
    ]
    cycles = [
        group
        for group in strongly_connected_components(by_id, graph_edges)
        if len(group) > 1
    ]
    self_cycles = sorted(
        source for source, target in graph_edges if source == target
    )
    if cycles or self_cycles:
        errors.append("component_dependency_cycle")
    return sorted(rows, key=lambda row: row["component_id"])


def _bound_contract(
    root: Path,
    manifest: dict[str, Any],
    field: str,
    components: list[dict[str, Any]],
    errors: list[str],
) -> tuple[str | None, str | None, Any]:
    raw = manifest.get(field)
    if not isinstance(raw, str) or not raw.strip():
        errors.append(f"{field}:path_missing")
        return None, None, None
    try:
        path, relative = safe_regular_file(root, raw)
        digest = file_sha256(path)
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
        errors.append(f"{field}:{type(exc).__name__}")
        return raw, None, None
    component = next((item for item in components if item["path"] == relative), None)
    if component is None or not component.get("revision_included"):
        errors.append(f"{field}:not_revision_bound_component")
    return relative, digest, value


def _owner_modules(components: list[dict[str, Any]]) -> list[tuple[str, str]]:
    owners: list[tuple[str, str]] = []
    for component in components:
        path = Path(str(component["path"]))
        if path.suffix != ".py":
            continue
        parts = list(path.with_suffix("").parts)
        if "scripts" in parts:
            parts = parts[parts.index("scripts") + 1 :]
        if parts and parts[-1] == "__init__":
            parts.pop()
        if parts:
            owners.append((".".join(parts), str(component["component_id"])))
    return sorted(owners, key=lambda item: len(item[0]), reverse=True)


def _normalize_owner(
    owner: Any,
    owner_modules: list[tuple[str, str]],
    *,
    label: str,
    errors: list[str],
) -> tuple[str | None, Any]:
    if isinstance(owner, dict) and set(owner) == {"component_id", "symbol"}:
        if all(
            isinstance(owner.get(key), str) and owner[key].strip()
            for key in owner
        ):
            return str(owner["component_id"]), owner
    elif isinstance(owner, str) and ":" in owner:
        return owner.split(":", 1)[0], owner
    elif isinstance(owner, str) and "." in owner:
        match = next(
            (
                (module_name, component_id)
                for module_name, component_id in owner_modules
                if owner == module_name or owner.startswith(f"{module_name}.")
            ),
            None,
        )
        if match:
            return match[1], {"component_id": match[1], "symbol": owner}
        errors.append(f"{label}:owner_component_unresolved")
        return None, owner
    errors.append(f"{label}:owner_invalid")
    return None, owner


def _hook_contracts(
    value: Any,
    manifest: dict[str, Any],
    components: list[dict[str, Any]],
    errors: list[str],
) -> list[dict[str, Any]]:
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        errors.append("hook_contract_schema_invalid")
        return []
    raw = value.get("hooks")
    if not isinstance(raw, list):
        errors.append("hook_contract_registry_invalid")
        return []
    component_ids = {row["component_id"] for row in components}
    owner_modules = _owner_modules(components)
    phase_hook_map = manifest.get("phase_hooks") or {}
    phase_consumer_map = manifest.get("phase_consumers") or {}
    rows: list[dict[str, Any]] = []
    ids: set[str] = set()
    for index, item in enumerate(raw):
        label = f"hook_contracts[{index}]"
        if (
            not isinstance(item, dict)
            or not HOOK_FIELDS <= set(item)
            or set(item) - HOOK_FIELDS - {"test_component_ids"}
        ):
            errors.append(f"{label}:closed_schema_invalid")
            continue
        hook_id = str(item.get("hook_id") or "").strip()
        if not hook_id or hook_id in ids:
            errors.append(f"{label}:hook_id_invalid")
            continue
        ids.add(hook_id)
        for field in (
            "input_schema_id",
            "output_schema_id",
            "side_effect_class",
            "fail_policy",
        ):
            if not isinstance(item.get(field), str) or not item[field].strip():
                errors.append(f"{label}:{field}_invalid")
        for field in ("phases", "consumer_ids"):
            if not _strings(item.get(field)):
                errors.append(f"{label}:{field}_invalid")
        tests = item.get("test_component_ids", [])
        if not _strings(tests):
            errors.append(f"{label}:test_component_ids_invalid")
        owner_component, normalized_owner = _normalize_owner(
            item.get("owner"), owner_modules, label=label, errors=errors
        )
        referenced = {str(owner_component), *(str(test) for test in tests)}
        if not referenced <= component_ids:
            errors.append(f"{label}:component_unknown")
        expected_phases = sorted(
            str(phase)
            for phase, hook_ids in phase_hook_map.items()
            if isinstance(hook_ids, list) and hook_id in hook_ids
        )
        if sorted(item.get("phases") or []) != expected_phases:
            errors.append(f"{label}:phase_map_divergence")
        expected_consumers = sorted(
            {
                str(consumer)
                for phase in item.get("phases") or []
                for consumer in phase_consumer_map.get(phase, [])
            }
        )
        if sorted(item.get("consumer_ids") or []) != expected_consumers:
            errors.append(f"{label}:consumer_map_divergence")
        rows.append({**item, "owner": normalized_owner})
    manifest_hooks = manifest.get("hooks")
    if isinstance(manifest_hooks, list) and set(manifest_hooks) != ids:
        errors.append("hook_contract_manifest_registry_divergence")
    return sorted(rows, key=lambda row: str(row["hook_id"]))


def _component_basis(components: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "component_id": row["component_id"],
            "path": row["path"],
            "sha256": row["sha256"],
            "kind": row["kind"],
            "role": row["role"],
            "required": row["required"],
            "revision_included": row["revision_included"],
            "runtime_included": row["runtime_included"],
            "architecture_audit_scope": row["architecture_audit_scope"],
            "depends_on": row["depends_on"],
        }
        for row in components
    ]


def compile_manifest_v3(
    root: Path,
    manifest: dict[str, Any],
    *,
    manifest_sha256: str,
    phase_consumer_map: dict[str, Any],
    phase_hook_map: dict[str, Any],
    errors: list[str],
) -> dict[str, Any]:
    components = _component_rows(root, manifest, errors)
    closure = compile_runtime_closure(root, manifest, components, errors)
    hook_path, hook_digest, hook_value = _bound_contract(
        root, manifest, "hook_contract_path", components, errors
    )
    convention_path, convention_digest, convention_value = _bound_contract(
        root, manifest, "code_convention_contract_path", components, errors
    )
    hooks = _hook_contracts(hook_value, manifest, components, errors)
    if not isinstance(convention_value, dict):
        errors.append("code_convention_contract_invalid")
    component_basis = _component_basis(components)
    component_registry_sha256 = object_sha256(component_basis)
    revision_basis = {
        "algorithm_revision": MANIFEST_V3_REVISION,
        "manifest_sha256": manifest_sha256,
        "components": [
            row for row in component_basis if row["revision_included"]
        ],
        "component_registry_sha256": component_registry_sha256,
        "runtime_closure_sha256": closure["runtime_closure_sha256"],
        "hook_contract_sha256": hook_digest,
        "code_convention_contract_sha256": convention_digest,
        "phase_consumer_map": phase_consumer_map,
        "phase_hook_map": phase_hook_map,
        "interpreter_abi": sys.implementation.cache_tag,
    }
    return {
        "manifest_format_version": 3,
        "manifest_compatibility_status": "v3_closed",
        "components": component_basis,
        "component_registry_sha256": component_registry_sha256,
        "runtime_closure": closure,
        "hook_contract_path": hook_path,
        "hook_contract_sha256": hook_digest,
        "hook_contracts": hooks,
        "code_convention_contract_path": convention_path,
        "code_convention_contract_sha256": convention_digest,
        "adapter_revision_sha256": object_sha256(revision_basis),
    }


__all__ = ("compile_manifest_v3",)
