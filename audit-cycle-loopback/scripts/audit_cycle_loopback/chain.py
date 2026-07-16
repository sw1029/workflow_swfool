"""Cohesive anti-loop chain policies exposed through a stable facade."""

from __future__ import annotations

from .chain_adapter import (
    row_vector_delta_passed,
    adapter_contract_unmet_fields,
    row_adapter_contract_unmet,
    adapter_missing_streak,
    adapter_mandate_gate,
    adapter_wiring_gate,
)

from .consumer_context import (
    consumer_receipt_pass,
    consumer_receipt_binding_sha256,
    consumer_context_conformance_gate,
)

from .chain_stall import (
    cumulative_goal_distance_scope_key,
    row_goal_distance_scope,
    cumulative_goal_distance_gate,
    first_actionable_capability_ladder_option,
    chain_stall_forced_retarget_gate,
)

from .primary_metric import (
    semantic_progress_from_high_water,
    updated_high_water,
    previous_primary_metric_value,
    primary_metric_zero_movement_streak,
    primary_metric_registry_high_water,
    primary_metric_artifact_binding,
    normalize_primary_metric_gate,
)

__all__ = (
    "row_vector_delta_passed",
    "adapter_contract_unmet_fields",
    "row_adapter_contract_unmet",
    "adapter_missing_streak",
    "adapter_mandate_gate",
    "adapter_wiring_gate",
    "consumer_receipt_pass",
    "consumer_receipt_binding_sha256",
    "consumer_context_conformance_gate",
    "cumulative_goal_distance_scope_key",
    "row_goal_distance_scope",
    "cumulative_goal_distance_gate",
    "first_actionable_capability_ladder_option",
    "chain_stall_forced_retarget_gate",
    "semantic_progress_from_high_water",
    "updated_high_water",
    "previous_primary_metric_value",
    "primary_metric_zero_movement_streak",
    "primary_metric_registry_high_water",
    "primary_metric_artifact_binding",
    "normalize_primary_metric_gate",
)
