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
    evaluation_decision,
    evaluation_failure,
    evaluation_finalize,
    evaluation_frame,
    evaluation_progress,
    evaluation_setup,
    evaluator,
    failure,
    families,
    finding_acceptance,
    finding_adapter,
    finding_mutation,
    finding_policy,
    finding_policy_base,
    finding_policy_enforcement,
    finding_progress,
    finding_progress_routing,
    finding_root_cause,
    finding_root_resolution,
    finding_terminal,
    findings,
    io_utils,
    measurement,
    outcome,
    packet,
    packet_finalization_fields,
    packet_gate_fields,
    packet_identity_fields,
    packet_progress_fields,
    packet_verification_fields,
    quality,
    registry,
    root_cause,
    root_cause_runtime,
    values,
    vectors,
    verification,
)
from .evaluation_stages import _STAGE_MODULES

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
    finding_policy_base,
    finding_policy_enforcement,
    finding_acceptance,
    finding_root_resolution,
    finding_progress_routing,
    finding_mutation,
    finding_policy,
    finding_root_cause,
    finding_progress,
    finding_adapter,
    finding_terminal,
    findings,
    verification,
    outcome,
    packet,
    packet_identity_fields,
    packet_gate_fields,
    packet_progress_fields,
    packet_verification_fields,
    packet_finalization_fields,
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
    *_STAGE_MODULES,
    evaluation_frame,
    evaluation_setup,
    evaluation_failure,
    evaluation_progress,
    evaluation_decision,
    evaluation_finalize,
    evaluator,
    cli,
]

_EXPLICIT_RUNTIME_MODULES = {
    assembly,
    findings,
    root_cause_runtime,
    packet_identity_fields,
    packet_gate_fields,
    packet_progress_fields,
    packet_verification_fields,
    packet_finalization_fields,
    finding_policy_base,
    finding_policy_enforcement,
    finding_acceptance,
    finding_root_resolution,
    finding_progress_routing,
    finding_mutation,
    finding_policy,
    finding_root_cause,
    finding_progress,
    finding_adapter,
    finding_terminal,
    *_STAGE_MODULES,
    evaluation_frame,
    evaluation_setup,
    evaluation_failure,
    evaluation_progress,
    evaluation_decision,
    evaluation_finalize,
    evaluator,
}


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
        if module not in _EXPLICIT_RUNTIME_MODULES:
            module.__dict__.update(exports)


def get_runtime_caches() -> dict[str, Any]:
    return {'_DOMAIN_ADAPTER_MODULE': adapters._DOMAIN_ADAPTER_MODULE}


def set_runtime_caches(values: dict[str, Any]) -> None:
    if '_DOMAIN_ADAPTER_MODULE' in values:
        adapters._DOMAIN_ADAPTER_MODULE = values['_DOMAIN_ADAPTER_MODULE']
    _bind_modules(_collect_exports())


_EXPORTS = _collect_exports()
_bind_modules(_EXPORTS)
__all__ = sorted(name for name in _EXPORTS if not name.startswith('_'))


def __getattr__(name: str) -> Any:
    try:
        return _EXPORTS[name]
    except KeyError as error:
        raise AttributeError(name) from error


def __dir__() -> list[str]:
    return sorted({*globals(), *_EXPORTS})
