from __future__ import annotations

import math
from typing import Any

from . import values as _values
from .quality_policy import normalize_quality_delta_policy
from .quality_values import _numeric_metric_value

def metric_stall_observation_allowed(
    evaluation_status: Any,
    *,
    policy_supplied: bool,
    producer_absence_reason: Any = None,
) -> bool:
    """Separate evaluated metrics from legacy producer-absence observations."""
    status = str(evaluation_status or "not_evaluated").strip().lower()
    if status == "evaluated":
        return True
    return bool(status == "not_evaluated" and not policy_supplied and producer_absence_reason)

def coverage_quality_delta_gate(
    quality: dict[str, Any],
    prev_high: dict[str, Any],
    provider_request_count: int,
    epsilon: float,
    quality_delta_policy: Any = None,
) -> dict[str, Any]:
    policy = normalize_quality_delta_policy(quality_delta_policy)
    keys = policy["keys"]
    try:
        epsilon_value = float(epsilon) if not isinstance(epsilon, bool) else float("nan")
    except (OverflowError, TypeError, ValueError):
        epsilon_value = float("nan")
    epsilon_valid = math.isfinite(epsilon_value) and epsilon_value >= 0
    effective_epsilon = epsilon_value if epsilon_valid else 0.0
    current: dict[str, float] = {}
    previous: dict[str, float] = {}
    missing_observations: list[str] = []
    previous_binding_count = sum(
        1
        for key in keys
        if any(candidate in prev_high for candidate in policy["aliases"].get(key, [key]))
    )
    baseline_absent = bool(keys) and previous_binding_count == 0
    for key in keys:
        current_present, current_value = _numeric_metric_value(quality, key, policy["aliases"])
        previous_present, previous_value = _numeric_metric_value(prev_high, key, policy["aliases"])
        if current_present and current_value is not None:
            current[key] = current_value
        if previous_present and previous_value is not None:
            previous[key] = previous_value
        elif baseline_absent:
            previous[key] = 0.0
        if not current_present or (not previous_present and not baseline_absent):
            missing_observations.append(key)
    invalid_contract_fields = list(policy["invalid_contract_fields"])
    if not epsilon_valid:
        invalid_contract_fields = list(dict.fromkeys([*invalid_contract_fields, *policy["declared_keys"]]))
    insufficient_evidence_fields = sorted(set([*policy["insufficient_evidence_fields"], *missing_observations]))
    evaluated = bool(keys) and not invalid_contract_fields and not insufficient_evidence_fields
    improved_fields = [
        key
        for key in keys
        if evaluated and current[key] > previous[key] + (effective_epsilon if key.endswith("_ratio") else 0.0)
    ]
    provider_dispatch_delta = provider_request_count > 0 and not _values.bool_value(prev_high.get("ever_provider_dispatch"))
    previous_high_water_all_zero = evaluated and all(previous[key] <= 0 for key in keys)
    current_quality_all_zero = evaluated and all(current[key] <= 0 for key in keys)
    if policy.get("policy_contract_invalid") or invalid_contract_fields:
        evaluation_status = "invalid_contract"
    elif insufficient_evidence_fields:
        evaluation_status = "insufficient_evidence"
    elif not policy["supplied"]:
        evaluation_status = "not_evaluated"
    elif not keys and policy["not_applicable_fields"]:
        evaluation_status = "not_applicable"
    else:
        evaluation_status = "evaluated"
    return {
        "gate": "G-COV",
        "quality_delta_pass": bool(improved_fields),
        "improved_fields": improved_fields,
        "current_quality_vector": current,
        "previous_high_water_vector": previous,
        "provider_dispatch_delta": provider_dispatch_delta,
        "previous_high_water_all_zero": previous_high_water_all_zero,
        "current_quality_all_zero": current_quality_all_zero,
        "high_water_all_zero": previous_high_water_all_zero and current_quality_all_zero,
        "quality_delta_policy": policy,
        "quality_delta_policy_supplied": policy["supplied"],
        "not_applicable_fields": policy["not_applicable_fields"],
        "insufficient_evidence_fields": insufficient_evidence_fields,
        "invalid_contract_fields": invalid_contract_fields,
        "evaluation_status": evaluation_status,
        "status": "pass" if improved_fields else ("block" if evaluation_status == "evaluated" else evaluation_status),
    }

def provider_scale_dispatch_gate(
    prev_high: dict[str, Any],
    coverage_gate: dict[str, Any],
    provider_request_count: int,
) -> dict[str, Any]:
    dispatch_required = (
        not _values.bool_value(prev_high.get("ever_provider_dispatch"))
        and _values.bool_value(coverage_gate.get("high_water_all_zero"))
        and provider_request_count == 0
    )
    return {
        "gate": "G-DISPATCH",
        "ever_provider_dispatch": _values.bool_value(prev_high.get("ever_provider_dispatch")) or provider_request_count > 0,
        "provider_request_count": provider_request_count,
        "high_water_all_zero": _values.bool_value(coverage_gate.get("high_water_all_zero")),
        "dispatch_required": dispatch_required,
        "hard_stop_required": dispatch_required,
        "constrains_disposition": dispatch_required,
        "allowed_dispositions": ["goal_productive", "terminal_blocked", "user_escalation"],
        "blocked_surface_only_work": dispatch_required,
        "status": "block" if dispatch_required else "ok",
    }
