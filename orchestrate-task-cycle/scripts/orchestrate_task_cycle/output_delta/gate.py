from __future__ import annotations

import math
from typing import Any

from .common import number_value, policy_items
from .policy import normalize_quality_delta_policy


def quality_metric_value(
    quality: dict[str, Any], key: str, aliases: dict[str, Any] | None = None
) -> float:
    candidates = policy_items((aliases or {}).get(key)) or [key]
    for candidate in candidates:
        if candidate in quality:
            return number_value(quality.get(candidate))
    return 0.0


def numeric_metric_value(
    quality: dict[str, Any], key: str, aliases: dict[str, Any] | None = None
) -> tuple[bool, float | None]:
    candidates = policy_items((aliases or {}).get(key)) or [key]
    for candidate in candidates:
        if candidate not in quality:
            continue
        value = quality.get(candidate)
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


def quality_delta_gate(
    current_quality: dict[str, Any],
    previous_quality: dict[str, Any],
    epsilon: float = 1e-9,
    quality_delta_policy: Any = None,
) -> dict[str, Any]:
    policy = normalize_quality_delta_policy(quality_delta_policy)
    keys = policy["keys"]
    try:
        epsilon_value = (
            float(epsilon) if not isinstance(epsilon, bool) else float("nan")
        )
    except (OverflowError, TypeError, ValueError):
        epsilon_value = float("nan")
    epsilon_valid = math.isfinite(epsilon_value) and epsilon_value >= 0
    effective_epsilon = epsilon_value if epsilon_valid else 0.0
    current: dict[str, float] = {}
    previous: dict[str, float] = {}
    missing: list[str] = []
    for key in keys:
        current_present, current_value = numeric_metric_value(
            current_quality, key, policy["aliases"]
        )
        previous_present, previous_value = numeric_metric_value(
            previous_quality, key, policy["aliases"]
        )
        if current_present and current_value is not None:
            current[key] = current_value
        if previous_present and previous_value is not None:
            previous[key] = previous_value
        if not current_present or not previous_present:
            missing.append(key)
    invalid = list(policy["invalid_contract_fields"])
    if not epsilon_valid:
        invalid = list(dict.fromkeys([*invalid, *policy["declared_keys"]]))
    insufficient = sorted(set([*policy["insufficient_evidence_fields"], *missing]))
    evaluated = bool(keys) and not invalid and not insufficient
    improved_fields = [
        key
        for key in keys
        if evaluated
        and current[key]
        > previous[key] + (effective_epsilon if key.endswith("_ratio") else 0.0)
    ]
    if policy.get("policy_contract_invalid") or invalid:
        evaluation_status = "invalid_contract"
    elif insufficient:
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
        "previous_quality_vector": previous,
        "quality_delta_policy": policy,
        "quality_delta_policy_supplied": policy["supplied"],
        "not_applicable_fields": policy["not_applicable_fields"],
        "insufficient_evidence_fields": insufficient,
        "invalid_contract_fields": invalid,
        "evaluation_status": evaluation_status,
        "status": "pass"
        if improved_fields
        else ("block" if evaluation_status == "evaluated" else evaluation_status),
    }
