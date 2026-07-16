from __future__ import annotations

import math
from typing import Any

from . import values as _values
from .quality_policy import _string_items, normalize_quality_delta_policy

def apply_quality_policy_compatibility(
    policy: Any,
    compatibility: dict[str, Any],
    *,
    policy_error: str | None = None,
) -> dict[str, Any]:
    """Project the existing gate-compatibility receipt onto decision metric IDs."""
    normalized = normalize_quality_delta_policy(policy)
    declared = normalized["declared_keys"]
    if not declared:
        return normalized
    gate_status = str(compatibility.get("gate_compatibility_status") or "not_evaluated").strip().lower()
    basis = str(compatibility.get("compatibility_basis") or "").strip().lower()
    if policy_error or basis in {
        "adapter_hook_return_contract_invalid",
        "adapter_hook_identity_echo_invalid",
        "gate_artifact_compatibility_signature_incompatible",
        "hook_error",
    }:
        projected_status = "invalid_contract"
        reason_code = "metric_policy_or_compatibility_invalid"
    elif gate_status == "incompatible":
        projected_status = "not_applicable"
        reason_code = "artifact_metric_incompatible"
    elif gate_status == "compatible":
        return normalized
    elif basis == "mapping_not_supplied":
        # The compatibility hook is optional. Its absence must not invalidate
        # a policy that already carries applicability rows, or a legacy
        # declared-key policy. Metric evidence is still checked below.
        return normalized
    else:
        projected_status = "insufficient_evidence"
        reason_code = "artifact_metric_compatibility_unresolved"
    projected = {
        key: {
            **normalized["applicability"].get(key, {}),
            "evaluation_status": projected_status,
            "reason_code": reason_code,
        }
        for key in declared
    }
    return normalize_quality_delta_policy(
        {
            "keys": declared,
            "aliases": normalized["aliases"],
            "applicability": projected,
        }
    )

def _numeric_metric_value(
    mapping: dict[str, Any],
    key: str,
    aliases: dict[str, Any] | None = None,
) -> tuple[bool, float | None]:
    candidates = _string_items((aliases or {}).get(key)) or [key]
    for candidate in candidates:
        if candidate not in mapping:
            continue
        value = mapping.get(candidate)
        if isinstance(value, bool):
            return False, None
        if isinstance(value, (int, float)):
            try:
                numeric = float(value)
            except OverflowError:
                return False, None
            return (True, numeric) if math.isfinite(numeric) else (False, None)
        if isinstance(value, str):
            try:
                numeric = float(value.strip())
                return (True, numeric) if math.isfinite(numeric) else (False, None)
            except ValueError:
                return False, None
        return False, None
    return False, None

def quality_metric_value(
    quality: dict[str, Any],
    key: str,
    aliases: dict[str, Any] | None = None,
) -> float:
    candidates = _string_items((aliases or {}).get(key)) or [key]
    for candidate in candidates:
        if candidate in quality:
            return _values.float_value(quality.get(candidate))
    return 0.0

def high_water_metric_value(
    high_water: dict[str, Any],
    key: str,
    aliases: dict[str, Any] | None = None,
) -> float:
    candidates = _string_items((aliases or {}).get(key)) or [key]
    for candidate in candidates:
        if candidate in high_water:
            return _values.float_value(high_water.get(candidate))
    return 0.0

def quality_high_water_for_policy(high_water: dict[str, Any], policy: Any) -> dict[str, Any]:
    normalized = normalize_quality_delta_policy(policy)
    result: dict[str, Any] = {}
    for key in normalized["keys"]:
        present, metric_value = _numeric_metric_value(high_water, key, normalized["aliases"])
        if present and metric_value is not None:
            result[key] = metric_value
    result["ever_provider_dispatch"] = _values.bool_value(high_water.get("ever_provider_dispatch"))
    return result

def public_quality_delta_policy(policy: Any) -> dict[str, Any]:
    """Preserve the legacy packet shape when no additive applicability is used."""
    normalized = normalize_quality_delta_policy(policy)
    if not normalized["applicability_supplied"] and not normalized["policy_contract_invalid"]:
        return {
            "keys": normalized["declared_keys"],
            "aliases": normalized["aliases"],
            "supplied": normalized["supplied"],
        }
    return normalized
