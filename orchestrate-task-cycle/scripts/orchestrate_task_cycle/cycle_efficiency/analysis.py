from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from .budgets import artifact_sprawl_budget, command_surface_budget
from .common import (
    artifact_payload_identity,
    artifact_ref_identity,
    boolish,
    bounded_opaque_id,
    current_cycle_events,
    first_present,
)
from .findings import append_budget_findings, base_findings, recommendations
from .observations import observation_state
from .scope import scope_state
from .state import CostProjection, ObservationState, ScopeState


def _cost_projection(
    root: Path, events: list[dict[str, Any]], scope: ScopeState, obs: ObservationState
) -> CostProjection:
    surface_budget = command_surface_budget(root, len(obs.global_metadata_only_events))
    sprawl_budget = artifact_sprawl_budget(root)
    cost_events = (
        scope.scoped_events
        if not scope.profile_scope_unverified
        else current_cycle_events(events)
    )
    scoped_unchanged_refs = [
        ref
        for event in cost_events
        for ref in (event.get("unchanged_refs") or [])
        if isinstance(ref, dict)
    ]
    unchanged_ids = sorted(
        {
            artifact_ref_identity(ref)
            for ref in scoped_unchanged_refs
            if artifact_payload_identity(ref) is not None
        }
    )
    artifact_ids = {
        artifact_ref_identity(ref)
        for event in cost_events
        for ref in (event.get("artifact_refs") or [])
        if isinstance(ref, dict) and artifact_payload_identity(ref) is not None
    }
    new_ids = sorted(artifact_ids - set(unchanged_ids))
    stage_ids = sorted(
        {
            bounded_opaque_id(event.get("event_id")) or f"ledger_event_{index + 1}"
            for index, event in enumerate(cost_events)
            if not boolish(event.get("replayed"))
        }
    )
    return CostProjection(
        surface_budget=surface_budget,
        sprawl_budget=sprawl_budget,
        unique_unchanged_artifact_ids=unchanged_ids,
        unique_new_artifact_ids=new_ids,
        fresh_stage_event_ids=stage_ids,
        cycle_fixed_cost=max(1, len(new_ids) + len(stage_ids)),
    )


def _result(
    events: list[dict[str, Any]],
    task_id: str | None,
    scope: ScopeState,
    obs: ObservationState,
    cost: CostProjection,
    findings: list[dict[str, Any]],
) -> dict[str, Any]:
    recommendation_values = recommendations(findings)
    event_task_id = (
        first_present(events[-1], ("task_id", "owner_task_id")) if events else None
    )
    effective_task_id = bounded_opaque_id(task_id) or bounded_opaque_id(event_task_id)
    return {
        "format_version": 1,
        "step": "cycle_efficiency_profile",
        "task_id": effective_task_id or None,
        "status": "warn"
        if any(item["severity"] == "warn" for item in findings)
        else "ok",
        "event_count": len(events),
        "progress_counts": dict(Counter(obs.progress_values)),
        "progress_kind_counts": dict(Counter(obs.progress_kinds)),
        "metadata_only_count": len(obs.metadata_only_events),
        "unchanged_ref_count": len(obs.unchanged_refs),
        "cycle_fixed_cost": cost.cycle_fixed_cost,
        "cycle_cost_basis": {
            "unique_new_artifact_ids": cost.unique_new_artifact_ids,
            "unique_unchanged_artifact_ids": cost.unique_unchanged_artifact_ids,
            "fresh_stage_event_ids": cost.fresh_stage_event_ids,
            "denominator": "max(1, unique_new_artifact_count + fresh_stage_event_count)",
            "scope": "verified_family"
            if not scope.profile_scope_unverified
            else "current_cycle_available_evidence",
        },
        "profile_scope": scope.latest_scope,
        "profile_scope_unverified": scope.profile_scope_unverified,
        "family_scoped_event_count": len(scope.scoped_events),
        "family_scoped_hard_gate": False,
        "goal_axis_stagnation_projection": scope.goal_axis_projection,
        "execution_scope": scope.latest_execution_scope,
        "execution_scope_status": "evaluated"
        if scope.execution_scope_known
        else "scope_unknown",
        "scope_evidence_required": scope.execution_scope_evidence_required,
        "execution_starvation_status": scope.execution_starvation_status,
        "execution_starvation": scope.execution_starvation,
        "recent_cycle_run_ids": scope.recent_run_ids,
        "recent_cycle_run_id_count": len(scope.recent_run_ids),
        "execution_starvation_window": scope.execution_starvation_window,
        "execution_starvation_window_status": scope.execution_starvation_window_status,
        "execution_candidate_priority_boost": scope.execution_starvation is True,
        "global_aggregate": {
            "blocker_counts": dict(Counter(obs.global_blockers)),
            "blocker_signature_counts": dict(Counter(obs.global_blocker_signatures)),
            "progress_counts": dict(
                Counter(
                    str(event.get("progress_verdict")).lower()
                    for event in events
                    if event.get("progress_verdict")
                )
            ),
            "metadata_only_count": len(obs.global_metadata_only_events),
            "dashboard_only": True,
            "hard_gate": False,
        },
        "vacuous_untried_streak": obs.vacuous_untried_streak,
        "hypothesis_exhausted": obs.hypothesis_exhausted,
        "forward_mutation_vacuous_count": obs.forward_mutation_vacuous_count,
        "validation_profile_counts": dict(Counter(obs.validation_profiles)),
        "blocker_signature_counts": dict(Counter(obs.blocker_signatures)),
        "validation_set_build_count": len(obs.validation_set_events),
        "command_surface_budget": cost.surface_budget,
        "artifact_sprawl_budget": cost.sprawl_budget,
        "findings": findings,
        "recommendation": recommendation_values[0]
        if recommendation_values
        else "continue",
        "recommendations": recommendation_values or ["continue"],
        "blockers": [item for item in findings if item.get("severity") == "block"],
        "evidence_paths": ["stdout:cycle_efficiency_profile"],
    }


def analyze(
    root: Path,
    events: list[dict[str, Any]],
    index_records: list[dict[str, Any]],
    task_id: str | None = None,
) -> dict[str, Any]:
    scope = scope_state(events)
    observations = observation_state(events, scope)
    findings = base_findings(scope, observations, index_records)
    cost = _cost_projection(root, events, scope, observations)
    append_budget_findings(findings, cost)
    return _result(events, task_id, scope, observations, cost, findings)
