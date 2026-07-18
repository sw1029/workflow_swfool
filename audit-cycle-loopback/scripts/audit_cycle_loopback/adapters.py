"""Explicit compatibility facade for adapter-related services."""

from __future__ import annotations

import hashlib
import inspect
import json
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
from .adapter_loading import file_sha256 as _file_sha256
from .adapter_loading import registered_adapter_from_scan as _registered_adapter_from_scan
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
_ADAPTER_INVOCATION_RECEIPTS: list[dict[str, Any]] = []
_PUBLIC_INVOCATION_FIELDS = {
    "acceptance_required",
    "hook_id",
    "input_sha256",
    "invocation_index",
    "output_sha256",
    "return_contract_valid",
    "semantic_status",
    "signature_sha256",
    "status",
    "value_consumed_by_decision",
}


def _receipt_digest(value: Any) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=lambda item: {"opaque_type": type(item).__name__},
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def reset_adapter_invocation_receipts() -> None:
    _ADAPTER_INVOCATION_RECEIPTS.clear()


def adapter_invocation_receipts() -> list[dict[str, Any]]:
    return [
        {key: value for key, value in row.items() if key in _PUBLIC_INVOCATION_FIELDS}
        for row in _ADAPTER_INVOCATION_RECEIPTS
    ]


def bind_adapter_invocation_result(
    hook_id: str,
    *,
    return_contract_valid: bool,
    semantic_accepted: bool,
    value_consumed_by_decision: bool,
    acceptance_required: bool = False,
) -> bool:
    """Bind the latest unbound hook call to its consumer-owned result verdict."""

    for row in reversed(_ADAPTER_INVOCATION_RECEIPTS):
        if row.get("hook_id") != hook_id or row.get("_result_bound") is True:
            continue
        accepted = bool(
            row.get("status") == "completed"
            and return_contract_valid
            and semantic_accepted
        )
        row.update(
            {
                "return_contract_valid": bool(return_contract_valid),
                "acceptance_required": bool(acceptance_required),
                "semantic_status": "accepted" if accepted else "not_evaluated",
                "value_consumed_by_decision": bool(
                    accepted and value_consumed_by_decision
                ),
                "_result_bound": True,
            }
        )
        return True
    return False


def _signature_digest(function: Any) -> str:
    if not callable(function):
        return _receipt_digest("unavailable")
    try:
        return _receipt_digest(str(inspect.signature(function)))
    except (TypeError, ValueError):
        return _receipt_digest("signature_unavailable")


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


def registered_adapter_from_scan(
    root: Path, raw: str | None, *, phase: str, consumer_id: str
) -> dict[str, Any]:
    return _registered_adapter_from_scan(
        root, raw, phase=phase, consumer_id=consumer_id
    )


def adapter_file_sha256(path: Path) -> str:
    return _file_sha256(path)


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
    function = getattr(adapter, function_name, None) if adapter is not None else None
    value, error = _call_adapter(adapter, function_name, **kwargs)
    _ADAPTER_INVOCATION_RECEIPTS.append(
        {
            "invocation_index": len(_ADAPTER_INVOCATION_RECEIPTS),
            "hook_id": function_name,
            "input_sha256": _receipt_digest(kwargs),
            "output_sha256": _receipt_digest({"value": value, "error": error}),
            "signature_sha256": _signature_digest(function),
            "return_contract_valid": False,
            "acceptance_required": False,
            "semantic_status": "not_evaluated",
            "value_consumed_by_decision": False,
            "status": "completed"
            if callable(function) and error is None
            else "failed"
            if error
            else "unavailable",
            "_result_bound": False,
        }
    )
    return value, error


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
