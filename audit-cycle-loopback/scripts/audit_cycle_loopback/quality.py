"""Metric policy normalization, values, and gate evaluation facade."""

from __future__ import annotations

from .quality_policy import (
    METRIC_APPLICABILITY_STATUSES,
    METRIC_POLICY_CONTRACT_ERROR_CODES,
    OPAQUE_ID_MAX_LENGTH,
    normalize_quality_delta_policy,
)

from .quality_values import (
    apply_quality_policy_compatibility,
    quality_metric_value,
    high_water_metric_value,
    quality_high_water_for_policy,
    public_quality_delta_policy,
)

from .quality_gates import (
    metric_stall_observation_allowed,
    coverage_quality_delta_gate,
    provider_scale_dispatch_gate,
)

__all__ = (
    "METRIC_APPLICABILITY_STATUSES",
    "METRIC_POLICY_CONTRACT_ERROR_CODES",
    "OPAQUE_ID_MAX_LENGTH",
    "normalize_quality_delta_policy",
    "apply_quality_policy_compatibility",
    "quality_metric_value",
    "high_water_metric_value",
    "quality_high_water_for_policy",
    "public_quality_delta_policy",
    "metric_stall_observation_allowed",
    "coverage_quality_delta_gate",
    "provider_scale_dispatch_gate",
)
