from __future__ import annotations

from .common import *

def quality_metric_value(quality: dict[str, Any], key: str) -> float:
    aliases = {
        "causal_edge_count": ("causal_edge_count", "causal_or_temporal_edge_count", "causal_temporal_edge_count"),
        "windows_covered": ("windows_covered", "source_windows_covered", "window_count", "selected_source_window_count"),
    }
    for candidate in aliases.get(key, (key,)):
        if candidate in quality:
            return float_value(quality.get(candidate))
    return 0.0

def high_water_metric_value(high_water: dict[str, Any], key: str) -> float:
    aliases = {
        "causal_edge_count": ("causal_edge_count", "causal_or_temporal_edge_count", "ever_causal_edge"),
        "windows_covered": ("windows_covered", "source_windows_covered", "window_count"),
    }
    for candidate in aliases.get(key, (key,)):
        if candidate in high_water:
            return float_value(high_water.get(candidate))
    return 0.0

def coverage_quality_delta_gate(
    quality: dict[str, Any],
    prev_high: dict[str, Any],
    provider_request_count: int,
    epsilon: float,
) -> dict[str, Any]:
    current = {key: quality_metric_value(quality, key) for key in QUALITY_DELTA_KEYS}
    previous = {key: high_water_metric_value(prev_high, key) for key in QUALITY_DELTA_KEYS}
    improved_fields = [
        key
        for key in QUALITY_DELTA_KEYS
        if current[key] > previous[key] + (epsilon if key.endswith("_ratio") else 0.0)
    ]
    provider_dispatch_delta = provider_request_count > 0 and not bool_value(prev_high.get("ever_provider_dispatch"))
    previous_high_water_all_zero = all(previous[key] <= 0 for key in QUALITY_DELTA_KEYS)
    current_quality_all_zero = all(current[key] <= 0 for key in QUALITY_DELTA_KEYS)
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
        "status": "pass" if improved_fields else "block",
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
