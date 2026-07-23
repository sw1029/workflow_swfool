from __future__ import annotations

from typing import Any

from .authority_rules import validate_authority_and_advice
from .context import ValidationContext, ValidationStage
from .index_snapshot_rules import validate_index_snapshot_revalidation
from .ordering_rules import (
    validate_anti_loop_handoff,
    validate_finalization_receipt,
    validate_ordering_gaps_and_bootstrap,
    validate_workflow_and_required_order,
)
from .progress_core_rules import (
    validate_disposition_gate,
    validate_goal_distance_gate,
    validate_positive_delta_gates,
    validate_sealed_semantic_gate,
)
from .progress_policy_rules import (
    validate_command_surface_budget,
    validate_gt_constraint_conflict,
    validate_provider_retry_gates,
    validate_root_axis_gate,
    validate_sealing_direction,
)
from .routing_rules import validate_routing_enforcement, validate_routing_request
from .runtime_rules import (
    validate_commit_readiness,
    validate_execution_status,
    validate_pending_long_runs,
    validate_report_readiness,
)
from .status_rules import validate_reasoned_statuses


VALIDATION_STAGES: tuple[ValidationStage, ...] = (
    validate_workflow_and_required_order,
    validate_finalization_receipt,
    validate_anti_loop_handoff,
    validate_ordering_gaps_and_bootstrap,
    validate_index_snapshot_revalidation,
    validate_reasoned_statuses,
    validate_disposition_gate,
    validate_positive_delta_gates,
    validate_sealed_semantic_gate,
    validate_goal_distance_gate,
    validate_provider_retry_gates,
    validate_root_axis_gate,
    validate_gt_constraint_conflict,
    validate_sealing_direction,
    validate_command_surface_budget,
    validate_authority_and_advice,
    validate_routing_request,
    validate_routing_enforcement,
    validate_execution_status,
    validate_pending_long_runs,
    validate_commit_readiness,
    validate_report_readiness,
)


def validate(
    context: dict[str, Any],
    stage: dict[str, Any],
    transition: str,
    routing: dict[str, Any] | None = None,
    workflow_mode: str = "normal",
) -> dict[str, Any]:
    state = ValidationContext(
        context=context,
        stage=stage,
        transition=transition,
        routing=routing,
        workflow_mode=workflow_mode,
    )
    for validation_stage in VALIDATION_STAGES:
        validation_stage(state)
    return state.result()
