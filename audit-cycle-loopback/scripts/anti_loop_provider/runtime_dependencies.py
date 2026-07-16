"""Compatibility boundary for dependencies used by decomposed runtime modules.

The legacy provider is assembled from small modules whose public symbols are
historically rebound by :mod:`anti_loop_provider.api`.  New runtime modules
declare every dependency explicitly and resolve legacy symbols through this
read-only boundary instead of depending on ambient module globals.
"""

from __future__ import annotations

from typing import Any

from . import (
    acceptance,
    adapters,
    advice,
    blockers,
    chain,
    common,
    constant_registry,
    context,
    domain,
    failure,
    families,
    io_utils,
    measurement,
    outcome,
    packet,
    quality,
    registry,
    root_cause,
    values,
    vectors,
    verification,
)


_LEGACY_MODULES = (
    common,
    constant_registry,
    context,
    io_utils,
    adapters,
    families,
    registry,
    values,
    failure,
    verification,
    outcome,
    packet,
    root_cause,
    vectors,
    acceptance,
    domain,
    measurement,
    blockers,
    advice,
    quality,
    chain,
)


def _collect_legacy_dependencies() -> dict[str, Any]:
    exports: dict[str, Any] = {}
    for module in _LEGACY_MODULES:
        exports.update(
            (name, value)
            for name, value in module.__dict__.items()
            if not name.startswith("__") and name != "annotations"
        )
    return exports


_DEPENDENCIES = _collect_legacy_dependencies()


def __getattr__(name: str) -> Any:
    try:
        return _DEPENDENCIES[name]
    except KeyError as error:
        raise AttributeError(name) from error


def __dir__() -> list[str]:
    return sorted({*globals(), *_DEPENDENCIES})
