"""Explicit compatibility facade for adapter-related services."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from . import domain as _domain
from . import io_utils as _io_utils
from .adapter_loading import call_adapter as _call_adapter
from .adapter_loading import (
    domain_adapter_candidate_paths as _domain_adapter_candidate_paths,
)
from .adapter_loading import load_domain_adapter as _load_domain_adapter
from .adapter_loading import load_python_module as _load_python_module
from .adapter_quality import canonicalize as _canonicalize
from .adapter_quality import compute_quality as _compute_quality
from .adapter_quality import fingerprint_rows as _fingerprint_rows
from .artifact_compatibility import (
    apply_gate_artifact_compatibility as _apply_gate_artifact_compatibility,
)
from .artifact_compatibility import (
    gate_artifact_compatibility_result as _gate_artifact_compatibility_result,
)
from .artifact_selection import load_artifact_selection as _load_artifact_selection
from .context import RuntimeCache


_RUNTIME_CACHE = RuntimeCache()


def _cached_domain_adapter() -> Any | None:
    return _RUNTIME_CACHE.domain_adapter_module


def _set_cached_domain_adapter(module: Any | None, path: str | None = None) -> None:
    _RUNTIME_CACHE.bind_domain_adapter(module, path)


def load_python_module(path: Path, module_name: str) -> Any | None:
    return _load_python_module(path, module_name)


def domain_adapter_candidate_paths(
    root: Path, explicit_path: str | None
) -> list[Path]:
    return _domain_adapter_candidate_paths(root, explicit_path)


def load_domain_adapter(
    root: Path, explicit_path: str | None
) -> tuple[Any | None, str | None, str | None]:
    return _load_domain_adapter(
        root,
        explicit_path,
        cache=_RUNTIME_CACHE,
        cached_adapter=_cached_domain_adapter,
        bind_adapter=_set_cached_domain_adapter,
        candidate_paths=domain_adapter_candidate_paths,
        load_module=load_python_module,
    )


def call_adapter(
    adapter: Any | None, function_name: str, **kwargs: Any
) -> tuple[Any, str | None]:
    return _call_adapter(adapter, function_name, **kwargs)


def load_artifact_selection(
    root: Path,
    artifact_paths_json: str | None,
    artifact_paths: list[str],
    *,
    artifact_ref_json: str | None = None,
    artifact_family: str | None = None,
) -> tuple[list[Path], dict[str, Any]]:
    return _load_artifact_selection(
        root,
        artifact_paths_json,
        artifact_paths,
        artifact_ref_json=artifact_ref_json,
        artifact_family=artifact_family,
    )


def load_artifact_paths(
    root: Path, artifact_paths_json: str | None, artifact_paths: list[str]
) -> list[Path]:
    paths, _ = load_artifact_selection(root, artifact_paths_json, artifact_paths)
    return paths


def gate_artifact_compatibility_result(
    adapter: Any | None,
    gate_id: str,
    artifact_ref: dict[str, Any],
    gate: dict[str, Any] | None = None,
    **context: Any,
) -> dict[str, Any]:
    return _gate_artifact_compatibility_result(
        adapter,
        gate_id,
        artifact_ref,
        gate,
        context,
        call_adapter=call_adapter,
    )


def apply_gate_artifact_compatibility(
    gate: dict[str, Any],
    compatibility: dict[str, Any],
    *,
    pass_fields: tuple[str, ...] = (),
) -> dict[str, Any]:
    return _apply_gate_artifact_compatibility(
        gate, compatibility, pass_fields=pass_fields
    )


def canonicalize(value: Any) -> Any:
    return _canonicalize(value)


def fingerprint_rows(rows: list[dict[str, Any]]) -> str:
    return _fingerprint_rows(rows, canonicalize_value=canonicalize)


def compute_quality(
    root: Path,
    paths: list[Path],
    adapter: Any | None,
    decision_artifact_ref: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], list[str], str | None, dict[str, bool]]:
    return _compute_quality(
        root,
        paths,
        adapter,
        decision_artifact_ref,
        call_adapter=call_adapter,
        rel_path=_io_utils.rel_path,
        normalize_quality=_domain.normalize_adapter_quality_result,
    )
