"""Repository-owned adapter loading and invocation boundaries."""

from __future__ import annotations

import importlib.util
import inspect
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .common import DOMAIN_ADAPTER_ENV
from .context import RuntimeCache


AdapterLoader = Callable[[Path, str], Any | None]
AdapterCandidates = Callable[[Path, str | None], list[Path]]
AdapterGetter = Callable[[], Any | None]
AdapterBinder = Callable[[Any | None, str | None], None]


def load_python_module(path: Path, module_name: str) -> Any | None:
    """Load an explicitly selected repository-owned Python adapter file."""
    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        return None
    spec = importlib.util.spec_from_file_location(module_name, resolved)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def domain_adapter_candidate_paths(
    root: Path, explicit_path: str | None
) -> list[Path]:
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
        not resolved_candidates
        or cache.domain_adapter_path in resolved_candidates
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
