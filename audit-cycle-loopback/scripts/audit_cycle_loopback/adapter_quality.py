"""Adapter quality-vector normalization and stable fingerprints."""

from __future__ import annotations

import hashlib
import inspect
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .common import VOLATILE_KEYS


AdapterCaller = Callable[..., tuple[Any, str | None]]
RelativePath = Callable[[Path, Path], str]
QualityNormalizer = Callable[
    [Any, Path], tuple[dict[str, Any], list[str], str | None]
]
Canonicalizer = Callable[[Any], Any]


def canonicalize(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): canonicalize(child)
            for key, child in sorted(value.items())
            if str(key) not in VOLATILE_KEYS
        }
    if isinstance(value, list):
        return [canonicalize(child) for child in value]
    return value


def fingerprint_rows(
    rows: list[dict[str, Any]], *, canonicalize_value: Canonicalizer = canonicalize
) -> str:
    canonical = [canonicalize_value(row) for row in rows]
    raw = json.dumps(
        canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _quality_signature_compatible(function: Any, kwargs: dict[str, Any]) -> bool:
    if not callable(function):
        return False
    try:
        signature = inspect.signature(function)
        accepts_kwargs = any(
            parameter.kind == inspect.Parameter.VAR_KEYWORD
            for parameter in signature.parameters.values()
        )
        accepted = (
            kwargs
            if accepts_kwargs
            else {key: value for key, value in kwargs.items() if key in signature.parameters}
        )
        signature.bind(**accepted)
        return accepts_kwargs or "decision_artifact_ref" in signature.parameters
    except (TypeError, ValueError):
        return False


def compute_quality(
    root: Path,
    paths: list[Path],
    adapter: Any | None,
    decision_artifact_ref: dict[str, Any] | None,
    *,
    call_adapter: AdapterCaller,
    rel_path: RelativePath,
    normalize_quality: QualityNormalizer,
) -> tuple[dict[str, Any], list[str], str | None, dict[str, bool]]:
    if adapter is not None:
        function = getattr(adapter, "quality_vector", None)
        kwargs = {
            "root": root,
            "artifact_paths": [rel_path(root, path) for path in paths],
            "absolute_artifact_paths": [path.as_posix() for path in paths],
            "decision_artifact_ref": dict(decision_artifact_ref or {}),
        }
        signature_compatible = _quality_signature_compatible(function, kwargs)
        adapter_value, adapter_error = call_adapter(
            adapter,
            "quality_vector",
            **kwargs,
        )
        receipt = {
            "hook_resolved": callable(function),
            "hook_signature_compatible": signature_compatible,
            "invocation_completed": bool(
                signature_compatible and adapter_error is None
            ),
            "return_contract_valid": bool(
                signature_compatible
                and adapter_error is None
                and isinstance(adapter_value, dict)
            ),
        }
        if adapter_error:
            return {}, [], adapter_error, receipt
        quality, evidence_paths, reason = normalize_quality(adapter_value, root)
        return quality, evidence_paths, reason, receipt

    evidence_paths = sorted(
        {rel_path(root, path) for path in paths if path.exists()}
    )
    return (
        {},
        evidence_paths,
        "domain_adapter_not_supplied",
        {
            "hook_resolved": False,
            "hook_signature_compatible": False,
            "invocation_completed": False,
            "return_contract_valid": False,
        },
    )
