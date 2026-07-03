from __future__ import annotations

import inspect
from typing import Any

from . import (
    acceptance,
    adapters,
    advice,
    assembly,
    blockers,
    chain,
    cli,
    common,
    constant_registry,
    context,
    domain,
    evaluator,
    failure,
    families,
    findings,
    io_utils,
    measurement,
    outcome,
    packet,
    quality,
    registry,
    root_cause,
    root_cause_runtime,
    values,
    vectors,
    verification,
)

_MODULES = [
    common,
    constant_registry,
    context,
    io_utils,
    adapters,
    assembly,
    families,
    registry,
    values,
    failure,
    findings,
    verification,
    outcome,
    packet,
    root_cause,
    root_cause_runtime,
    vectors,
    acceptance,
    domain,
    measurement,
    blockers,
    advice,
    quality,
    chain,
    evaluator,
    cli,
]


def _is_exportable(name: str, value: Any) -> bool:
    if name.startswith('__') or name in {'annotations'}:
        return False
    if inspect.ismodule(value):
        return False
    return True


def _collect_exports() -> dict[str, Any]:
    exports: dict[str, Any] = {}
    for module in _MODULES:
        for name, value in module.__dict__.items():
            if _is_exportable(name, value):
                exports[name] = value
    return exports


def _bind_modules(exports: dict[str, Any]) -> None:
    for module in _MODULES:
        module.__dict__.update(exports)


def get_runtime_caches() -> dict[str, Any]:
    return {
        '_DOMAIN_ADAPTER_MODULE': adapters._DOMAIN_ADAPTER_MODULE,
        '_QUALITY_METRICS_MODULE': adapters._QUALITY_METRICS_MODULE,
    }


def set_runtime_caches(values: dict[str, Any]) -> None:
    if '_DOMAIN_ADAPTER_MODULE' in values:
        adapters._DOMAIN_ADAPTER_MODULE = values['_DOMAIN_ADAPTER_MODULE']
    if '_QUALITY_METRICS_MODULE' in values:
        adapters._QUALITY_METRICS_MODULE = values['_QUALITY_METRICS_MODULE']
    _bind_modules(_collect_exports())


_EXPORTS = _collect_exports()
_bind_modules(_EXPORTS)
globals().update(_EXPORTS)
__all__ = sorted(name for name in _EXPORTS if not name.startswith('_'))
