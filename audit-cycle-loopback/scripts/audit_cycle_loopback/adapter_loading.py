"""Repository-owned adapter loading and invocation boundaries."""

from __future__ import annotations

import importlib.util
import inspect
import hashlib
import json
import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .common import DOMAIN_ADAPTER_ENV
from .context import RuntimeCache
from .adapter_scan_contract import adapter_revision_valid, scan_packet_valid


AdapterLoader = Callable[[Path, str], Any | None]
AdapterCandidates = Callable[[Path, str | None], list[Path]]
AdapterGetter = Callable[[], Any | None]
AdapterBinder = Callable[[Any | None, str | None], None]
_MISSING_MODULE = object()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _scan_value(root: Path, raw: str) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        candidate = Path(raw)
        if not candidate.is_absolute():
            candidate = root / candidate
        resolved = candidate.expanduser().resolve(strict=True)
        resolved.relative_to(root)
        if not resolved.is_file() or resolved.is_symlink():
            raise ValueError("adapter scan packet is not a safe regular file")
        value = json.loads(resolved.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("adapter scan packet is not an object")
    if not scan_packet_valid(value):
        raise ValueError("adapter scan packet integrity is invalid")
    return value


_SCAN_COMPONENT_FIELDS = (
    ("manifest_path", "manifest_sha256"),
    ("implementation_path", "implementation_sha256"),
    ("legacy_compatibility_path", "legacy_compatibility_sha256"),
    ("renderer_path", "renderer_sha256"),
    ("decision_identity_validator_path", "decision_identity_validator_sha256"),
    ("authority_projection_path", "authority_projection_sha256"),
)


def _current_adapter_components(
    root: Path, row: dict[str, Any]
) -> dict[str, tuple[str, str]]:
    current: dict[str, tuple[str, str]] = {}
    for path_field, hash_field in _SCAN_COMPONENT_FIELDS:
        if row.get(path_field) is None and row.get(hash_field) is None:
            continue
        candidate = Path(str(row.get(path_field) or ""))
        candidate = candidate if candidate.is_absolute() else root / candidate
        resolved = candidate.expanduser().resolve(strict=True)
        resolved.relative_to(root)
        digest = file_sha256(resolved)
        if digest != row.get(hash_field):
            raise ValueError(f"stale component: {path_field}")
        current[path_field] = (resolved.as_posix(), digest)
    return current


def registered_adapter_from_scan(
    root: Path,
    raw: str | None,
    *,
    phase: str,
    consumer_id: str,
) -> dict[str, Any]:
    """Resolve one hash-current registered adapter without importing it."""

    root = root.expanduser().resolve(strict=True)
    if not raw:
        return {
            "status": "not_supplied",
            "adapter_registered": False,
            "implementation_path": None,
            "adapter_revision_sha256": None,
        }
    try:
        packet = _scan_value(root, raw)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return {
            "status": "invalid_scan",
            "adapter_registered": False,
            "implementation_path": None,
            "adapter_revision_sha256": None,
            "error": f"adapter_scan_invalid:{type(exc).__name__}",
        }
    container = packet.get("repo_skill_adapter_packet")
    rows = container.get("adapters") if isinstance(container, dict) else None
    if not isinstance(rows, list):
        return {
            "status": "invalid_scan",
            "adapter_registered": False,
            "implementation_path": None,
            "adapter_revision_sha256": None,
            "error": "adapter_scan_rows_missing",
        }
    matches = [
        row
        for row in rows
        if isinstance(row, dict)
        and row.get("status") == "active"
        and consumer_id in (row.get("phase_consumer_map") or {}).get(phase, [])
    ]
    if not matches:
        return {
            "status": "not_registered",
            "adapter_registered": False,
            "implementation_path": None,
            "adapter_revision_sha256": None,
        }
    if len(matches) != 1:
        return {
            "status": "wiring_defect",
            "adapter_registered": True,
            "implementation_path": None,
            "adapter_revision_sha256": None,
            "error": "adapter_scan_ambiguous_registration",
        }
    row = matches[0]
    try:
        current_components = _current_adapter_components(root, row)
        resolved = Path(current_components["implementation_path"][0])
        current_sha256 = current_components["implementation_path"][1]
    except (OSError, ValueError) as exc:
        return {
            "status": "wiring_defect",
            "adapter_registered": True,
            "implementation_path": row.get("implementation_path"),
            "adapter_revision_sha256": row.get("adapter_revision_sha256"),
            "error": f"registered_adapter_unavailable:{type(exc).__name__}",
        }
    revision = str(row.get("adapter_revision_sha256") or "").lower()
    valid = bool(
        adapter_revision_valid(
            root,
            row,
            Path(current_components["manifest_path"][0]),
            file_sha256,
        )
        and current_sha256 == row.get("implementation_sha256")
    )
    return {
        "status": "ready" if valid else "wiring_defect",
        "adapter_registered": True,
        "implementation_path": resolved.as_posix(),
        "implementation_sha256": current_sha256,
        "legacy_compatibility_path": row.get("legacy_compatibility_path"),
        "legacy_compatibility_sha256": row.get("legacy_compatibility_sha256"),
        "renderer_path": row.get("renderer_path"),
        "renderer_sha256": row.get("renderer_sha256"),
        "decision_identity_validator_path": row.get("decision_identity_validator_path"),
        "decision_identity_validator_sha256": row.get(
            "decision_identity_validator_sha256"
        ),
        "authority_projection_path": row.get("authority_projection_path"),
        "authority_projection_sha256": row.get("authority_projection_sha256"),
        "manifest_path": row.get("manifest_path"),
        "manifest_sha256": row.get("manifest_sha256"),
        "adapter_revision_sha256": revision or None,
        "phase": phase,
        "consumer_id": consumer_id,
        "required_consumer_ids": list(
            (row.get("phase_consumer_map") or {}).get(phase, [])
        ),
        "available_hook_ids": list((row.get("phase_hook_map") or {}).get(phase, [])),
        "error": None if valid else "registered_adapter_scan_stale",
    }


def load_python_module(path: Path, module_name: str) -> Any | None:
    """Load an explicitly selected repository-owned Python adapter file."""
    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        return None
    spec = importlib.util.spec_from_file_location(module_name, resolved)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    prior_module = sys.modules.get(module_name, _MISSING_MODULE)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        if prior_module is _MISSING_MODULE:
            sys.modules.pop(module_name, None)
        else:
            sys.modules[module_name] = prior_module
        raise
    return module


def domain_adapter_candidate_paths(root: Path, explicit_path: str | None) -> list[Path]:
    candidates: list[Path] = []
    for raw in (
        explicit_path,
        os.environ.get(DOMAIN_ADAPTER_ENV),
        os.environ.get("DOMAIN_ADAPTER_PATH"),
    ):
        if not raw:
            continue
        candidate = Path(raw)
        if not candidate.is_absolute():
            candidate = root / candidate
        candidates.append(candidate)
    return candidates


def load_domain_adapter(
    root: Path,
    explicit_path: str | None,
    *,
    cache: RuntimeCache,
    cached_adapter: AdapterGetter,
    bind_adapter: AdapterBinder,
    candidate_paths: AdapterCandidates,
    load_module: AdapterLoader,
) -> tuple[Any | None, str | None, str | None]:
    """Resolve an adapter while retaining the caller-owned path-bound cache."""
    cached = cached_adapter()
    candidates = candidate_paths(root, explicit_path)
    resolved_candidates = [
        candidate.expanduser().resolve().as_posix() for candidate in candidates
    ]
    if cached is not None and (
        not resolved_candidates or cache.domain_adapter_path in resolved_candidates
    ):
        return cached, None, None

    seen: set[str] = set()
    for candidate in candidates:
        resolved = candidate.expanduser().resolve()
        resolved_path = resolved.as_posix()
        if resolved_path in seen:
            continue
        seen.add(resolved_path)
        try:
            module = load_module(resolved, "task_cycle_domain_adapter")
        except Exception as exc:  # pragma: no cover - defensive import boundary
            return (
                None,
                resolved_path,
                f"domain_adapter_import_failed:{type(exc).__name__}",
            )
        if module is not None:
            bind_adapter(module, resolved_path)
            return module, resolved_path, None
    if candidates:
        return None, None, "domain_adapter_not_found"
    return None, None, None


def call_adapter(
    adapter: Any | None, function_name: str, **kwargs: Any
) -> tuple[Any, str | None]:
    if adapter is None or not hasattr(adapter, function_name):
        return None, None
    function = getattr(adapter, function_name)
    try:
        signature = inspect.signature(function)
        accepts_kwargs = any(
            parameter.kind == inspect.Parameter.VAR_KEYWORD
            for parameter in signature.parameters.values()
        )
        if accepts_kwargs:
            return function(**kwargs), None
        accepted = {
            key: value for key, value in kwargs.items() if key in signature.parameters
        }
        return function(**accepted), None
    except TypeError:
        try:
            return function(), None
        except Exception as exc:  # pragma: no cover - adapter-owned code
            return None, f"{function_name}_failed:{type(exc).__name__}"
    except Exception as exc:  # pragma: no cover - adapter-owned code
        return None, f"{function_name}_failed:{type(exc).__name__}"
