"""Manifest parsing and revision closure for repository-owned workflow adapters."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import stat
from typing import Any

from .adapter_architecture.manifest import compile_manifest_v3


SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
REQUIRED_PATH_FIELDS = (("implementation_path", "implementation_sha256"),)
OPTIONAL_PATH_FIELDS = (
    ("legacy_compatibility_path", "legacy_compatibility_sha256"),
    ("renderer_path", "renderer_sha256"),
    ("decision_identity_validator_path", "decision_identity_validator_sha256"),
    ("authority_projection_path", "authority_projection_sha256"),
)
COMPONENT_PATH_FIELDS = REQUIRED_PATH_FIELDS + OPTIONAL_PATH_FIELDS


def _canonical(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def _object_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_regular_file(root: Path, raw: str) -> tuple[Path, str]:
    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = root / candidate
    lexical = candidate.absolute()
    try:
        relative = lexical.relative_to(root)
    except ValueError as exc:
        raise ValueError("adapter component escapes repository root") from exc
    current = root
    for part in relative.parts:
        current /= part
        if current.is_symlink():
            raise ValueError("adapter component crosses a symlink")
    resolved = lexical.resolve(strict=True)
    if not stat.S_ISREG(resolved.lstat().st_mode):
        raise ValueError("adapter component is not a regular file")
    return resolved, resolved.relative_to(root).as_posix()


def _component(root: Path, raw: Any) -> tuple[str | None, str | None, str | None]:
    if not isinstance(raw, str) or not raw.strip():
        return None, None, "path_missing"
    try:
        path, relative = _safe_regular_file(root, raw)
    except (OSError, ValueError) as exc:
        return raw, None, type(exc).__name__
    return relative, _file_sha256(path), None


def _load_manifest(manifest_path: Path, base: dict[str, Any]) -> dict[str, Any] | None:
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        base["static_validation"]["errors"].append(
            f"manifest_load_failed:{type(exc).__name__}"
        )
        return None
    if not isinstance(manifest, dict):
        base["static_validation"]["errors"].append("manifest_not_object")
        return None
    return manifest


def _declared_registries(
    base: dict[str, Any], manifest: dict[str, Any]
) -> tuple[str, Any, Any, Any, Any]:
    adapter_id = str(manifest.get("adapter_id") or "").strip()
    hooks = manifest.get("hooks")
    phase_consumers = manifest.get("phase_consumers")
    phase_hooks = manifest.get("phase_hooks")
    required_consumers = manifest.get("required_consumer_ids")
    base.update(
        {
            "adapter_id": adapter_id,
            "status": str(manifest.get("status") or "unknown"),
            "not_goal_truth": manifest.get("not_goal_truth") is True,
            "not_validation_evidence": manifest.get("not_validation_evidence")
            is True,
            "required_consumer_ids": required_consumers
            if isinstance(required_consumers, list)
            else [],
            "phase_consumer_map": phase_consumers
            if isinstance(phase_consumers, dict)
            else {},
            "phase_hook_map": phase_hooks if isinstance(phase_hooks, dict) else {},
            "hooks": hooks if isinstance(hooks, list) else [],
        }
    )
    return adapter_id, hooks, phase_consumers, phase_hooks, required_consumers


def _validate_registries(
    manifest: dict[str, Any],
    errors: list[str],
    adapter_id: str,
    hooks: Any,
    phase_consumers: Any,
    phase_hooks: Any,
    required_consumers: Any,
) -> Any:
    if not adapter_id:
        errors.append("adapter_id_missing")
    format_version = manifest.get("format_version")
    if format_version not in {2, 3}:
        errors.append("unsupported_manifest_format")
    if (
        not isinstance(hooks, list)
        or any(not isinstance(item, str) for item in hooks)
        or len(set(hooks)) != len(hooks)
    ):
        errors.append("hook_registry_invalid")
    if (
        not isinstance(required_consumers, list)
        or any(
            not isinstance(item, str) or not item.strip() for item in required_consumers
        )
        or len(set(required_consumers)) != len(required_consumers)
    ):
        errors.append("required_consumer_registry_invalid")
    _validate_phase_registries(
        errors, hooks, phase_consumers, phase_hooks, required_consumers
    )
    return format_version


def _validate_phase_registries(
    errors: list[str],
    hooks: Any,
    phase_consumers: Any,
    phase_hooks: Any,
    required_consumers: Any,
) -> None:
    if not isinstance(phase_consumers, dict) or not isinstance(phase_hooks, dict):
        errors.append("phase_registry_invalid")
        return
    if set(phase_consumers) != set(phase_hooks):
        errors.append("phase_registry_divergence")
        return
    consumer_invalid = any(
        not isinstance(names, list)
        or any(not isinstance(name, str) or not name.strip() for name in names)
        or len(set(names)) != len(names)
        for names in phase_consumers.values()
    )
    if consumer_invalid:
        errors.append("phase_consumer_registry_invalid")
    elif isinstance(required_consumers, list) and any(
        name not in required_consumers
        for names in phase_consumers.values()
        for name in names
    ):
        errors.append("phase_consumer_undeclared")
    hook_invalid = any(
        not isinstance(names, list)
        or any(not isinstance(name, str) or not name.strip() for name in names)
        or len(set(names)) != len(names)
        for names in phase_hooks.values()
    )
    if hook_invalid:
        errors.append("phase_hook_registry_invalid")
    elif isinstance(hooks, list) and any(
        name not in hooks for names in phase_hooks.values() for name in names
    ):
        errors.append("phase_hook_undeclared")


def _bind_component_paths(
    root: Path,
    manifest: dict[str, Any],
    base: dict[str, Any],
    errors: list[str],
) -> None:
    for path_field, hash_field in REQUIRED_PATH_FIELDS:
        relative, digest, error = _component(root, manifest.get(path_field))
        base[path_field] = relative
        base[hash_field] = digest
        if error:
            errors.append(f"{path_field}:{error}")
    for path_field, hash_field in OPTIONAL_PATH_FIELDS:
        raw = manifest.get(path_field)
        if raw in (None, ""):
            base[path_field] = None
            base[hash_field] = None
            continue
        relative, digest, error = _component(root, raw)
        base[path_field] = relative
        base[hash_field] = digest
        if error:
            errors.append(f"{path_field}:{error}")


def _compile_v3_row(
    root: Path,
    manifest: dict[str, Any],
    base: dict[str, Any],
    errors: list[str],
) -> None:
    base.update(
        compile_manifest_v3(
            root,
            manifest,
            manifest_sha256=base["manifest_sha256"],
            phase_consumer_map=base["phase_consumer_map"],
            phase_hook_map=base["phase_hook_map"],
            errors=errors,
        )
    )
    component_paths = {
        str(item.get("path"))
        for item in base.get("components", [])
        if isinstance(item, dict)
    }
    for path_field, _hash_field in COMPONENT_PATH_FIELDS:
        path_value = base.get(path_field)
        if path_value and path_value not in component_paths:
            errors.append(f"{path_field}:not_registered_component")


def _compile_v2_row(
    manifest: dict[str, Any], base: dict[str, Any], adapter_id: str
) -> None:
    basis = {
        "adapter_id": adapter_id,
        "manifest_sha256": base["manifest_sha256"],
        "implementation_sha256": base.get("implementation_sha256"),
        "legacy_compatibility_sha256": base.get("legacy_compatibility_sha256"),
        "renderer_sha256": base.get("renderer_sha256"),
        "decision_identity_validator_sha256": base.get(
            "decision_identity_validator_sha256"
        ),
        "phase_consumer_map": base["phase_consumer_map"],
        "phase_hook_map": base["phase_hook_map"],
    }
    if "authority_projection_path" in manifest:
        basis["authority_projection_sha256"] = base.get(
            "authority_projection_sha256"
        )
    base.update(
        {
            "manifest_format_version": 2,
            "manifest_compatibility_status": "legacy_partial",
            "components": [],
            "component_registry_sha256": None,
            "runtime_closure": None,
            "hook_contract_path": None,
            "hook_contract_sha256": None,
            "hook_contracts": [],
            "code_convention_contract_path": None,
            "code_convention_contract_sha256": None,
            "adapter_revision_sha256": _object_sha256(basis),
        }
    )


def _adapter_row(root: Path, manifest_path: Path) -> dict[str, Any]:
    base: dict[str, Any] = {
        "manifest_path": manifest_path.relative_to(root).as_posix(),
        "manifest_sha256": _file_sha256(manifest_path),
        "static_validation": {"status": "block", "errors": []},
    }
    manifest = _load_manifest(manifest_path, base)
    if manifest is None:
        return base
    declared = _declared_registries(base, manifest)
    errors = base["static_validation"]["errors"]
    format_version = _validate_registries(manifest, errors, *declared)
    _bind_component_paths(root, manifest, base, errors)
    if format_version == 3:
        _compile_v3_row(root, manifest, base, errors)
    else:
        _compile_v2_row(manifest, base, declared[0])
    base["static_validation"]["status"] = "pass" if not errors else "block"
    return base


__all__ = (
    "COMPONENT_PATH_FIELDS",
    "OPTIONAL_PATH_FIELDS",
    "REQUIRED_PATH_FIELDS",
    "SHA256_PATTERN",
)
