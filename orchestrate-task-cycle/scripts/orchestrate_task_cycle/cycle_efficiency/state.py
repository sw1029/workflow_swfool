from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ScopeState:
    latest_scope: dict[str, str]
    profile_scope_unverified: bool
    scoped_events: list[dict[str, Any]]
    decision_events: list[dict[str, Any]]
    latest_execution_scope: dict[str, str]
    execution_scope_known: bool
    execution_scope_evidence_required: list[str]
    execution_starvation_status: str
    execution_starvation: bool | None
    recent_run_ids: list[str]
    execution_starvation_window: int | None
    execution_starvation_window_status: str
    goal_axis_projection: dict[str, Any]


@dataclass(frozen=True)
class ObservationState:
    progress_values: list[str]
    progress_kinds: list[str]
    global_blockers: list[str]
    blockers: list[str]
    unchanged_refs: list[dict[str, Any]]
    missing_unchanged_payload_refs: list[dict[str, Any]]
    validation_profiles: list[str]
    global_blocker_signatures: list[str]
    blocker_signatures: list[str]
    validation_set_events: list[dict[str, Any]]
    validation_set_artifacts: list[str]
    validation_set_blockers: list[str]
    repeated_blockers: list[dict[str, Any]]
    repeated_signatures: list[dict[str, Any]]
    duplicate_artifacts: list[dict[str, Any]]
    metadata_only_events: list[dict[str, Any]]
    global_metadata_only_events: list[dict[str, Any]]
    vacuous_untried_streak: int
    hypothesis_exhausted: bool
    forward_mutation_vacuous_count: int
    full_chain_without_reason: list[dict[str, Any]]


@dataclass(frozen=True)
class CostProjection:
    surface_budget: dict[str, Any]
    sprawl_budget: dict[str, Any]
    unique_unchanged_artifact_ids: list[str]
    unique_new_artifact_ids: list[str]
    fresh_stage_event_ids: list[str]
    cycle_fixed_cost: int
