from __future__ import annotations

from .common import *

def _string_items(value: Any) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, (list, tuple, set)):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def normalize_quality_delta_policy(value: Any) -> dict[str, Any]:
    """Normalize an explicit adapter-owned metric-key/alias contract."""
    if isinstance(value, (list, tuple, set)):
        raw_keys = value
        raw_aliases: Any = {}
    elif isinstance(value, dict):
        raw_keys = (
            value.get("keys")
            or value.get("quality_delta_keys")
            or value.get("metric_keys")
            or value.get("axes")
            or []
        )
        raw_aliases = (
            value.get("aliases")
            or value.get("quality_metric_aliases")
            or value.get("metric_aliases")
            or {}
        )
    else:
        raw_keys = []
        raw_aliases = {}

    keys = list(dict.fromkeys(_string_items(raw_keys)))
    aliases: dict[str, list[str]] = {}
    if isinstance(raw_aliases, dict):
        for key in keys:
            candidates = [key, *_string_items(raw_aliases.get(key))]
            aliases[key] = list(dict.fromkeys(candidates))
    else:
        aliases = {key: [key] for key in keys}
    return {
        "keys": keys,
        "aliases": aliases,
        "supplied": bool(keys),
    }


def quality_metric_value(
    quality: dict[str, Any],
    key: str,
    aliases: dict[str, Any] | None = None,
) -> float:
    candidates = _string_items((aliases or {}).get(key)) or [key]
    for candidate in candidates:
        if candidate in quality:
            return float_value(quality.get(candidate))
    return 0.0

def high_water_metric_value(
    high_water: dict[str, Any],
    key: str,
    aliases: dict[str, Any] | None = None,
) -> float:
    candidates = _string_items((aliases or {}).get(key)) or [key]
    for candidate in candidates:
        if candidate in high_water:
            return float_value(high_water.get(candidate))
    return 0.0


def quality_high_water_for_policy(high_water: dict[str, Any], policy: Any) -> dict[str, Any]:
    normalized = normalize_quality_delta_policy(policy)
    result = {
        key: high_water_metric_value(high_water, key, normalized["aliases"])
        for key in normalized["keys"]
    }
    result["ever_provider_dispatch"] = bool_value(high_water.get("ever_provider_dispatch"))
    return result

def coverage_quality_delta_gate(
    quality: dict[str, Any],
    prev_high: dict[str, Any],
    provider_request_count: int,
    epsilon: float,
    quality_delta_policy: Any = None,
) -> dict[str, Any]:
    policy = normalize_quality_delta_policy(quality_delta_policy)
    keys = policy["keys"]
    current = {key: quality_metric_value(quality, key, policy["aliases"]) for key in keys}
    previous = {key: high_water_metric_value(prev_high, key, policy["aliases"]) for key in keys}
    improved_fields = [
        key
        for key in keys
        if current[key] > previous[key] + (epsilon if key.endswith("_ratio") else 0.0)
    ]
    provider_dispatch_delta = provider_request_count > 0 and not bool_value(prev_high.get("ever_provider_dispatch"))
    previous_high_water_all_zero = bool(keys) and all(previous[key] <= 0 for key in keys)
    current_quality_all_zero = bool(keys) and all(current[key] <= 0 for key in keys)
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
        "evaluation_status": "evaluated" if keys else "not_evaluated",
        "status": "pass" if improved_fields else ("block" if keys else "not_evaluated"),
    }

def provider_scale_dispatch_gate(
    prev_high: dict[str, Any],
    coverage_gate: dict[str, Any],
    provider_request_count: int,
) -> dict[str, Any]:
    dispatch_required = (
        not bool_value(prev_high.get("ever_provider_dispatch"))
        and bool_value(coverage_gate.get("high_water_all_zero"))
        and provider_request_count == 0
    )
    return {
        "gate": "G-DISPATCH",
        "ever_provider_dispatch": bool_value(prev_high.get("ever_provider_dispatch")) or provider_request_count > 0,
        "provider_request_count": provider_request_count,
        "high_water_all_zero": bool_value(coverage_gate.get("high_water_all_zero")),
        "dispatch_required": dispatch_required,
        "hard_stop_required": dispatch_required,
        "constrains_disposition": dispatch_required,
        "allowed_dispositions": ["goal_productive", "terminal_blocked", "user_escalation"],
        "blocked_surface_only_work": dispatch_required,
        "status": "block" if dispatch_required else "ok",
    }
