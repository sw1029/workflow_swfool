from __future__ import annotations

from typing import Any

from .common import (
    cycle_groups,
    execution_scope,
    family_scope,
    first_present,
    fresh_run_id,
    same_execution_scope,
    same_family_scope,
    semantic_goal_movement,
    stable_scope_value,
)
from .state import ScopeState


def _starvation_window(events: list[dict[str, Any]]) -> tuple[int | None, str]:
    raw = first_present(
        events[-1] if events else {},
        ("execution_starvation_window", "profile_contract.execution_starvation_window"),
    )
    try:
        if isinstance(raw, bool) or raw is None:
            raise ValueError
        window: int | None = int(raw)
        if window < 1:
            raise ValueError
        return window, "supplied"
    except (TypeError, ValueError):
        return None, "not_supplied" if raw is None else "malformed"


def _goal_axis_projection(
    events: list[dict[str, Any]], latest_execution_scope: dict[str, str]
) -> dict[str, Any]:
    current_goal_axis = latest_execution_scope["goal_axis"]
    axis_events = [
        event
        for event in events
        if current_goal_axis
        and stable_scope_value(
            first_present(event, ("goal_axis", "profile_scope.goal_axis"))
        )
        == current_goal_axis
    ]
    groups = cycle_groups(axis_events)
    stagnation_streak = 0
    for _, group in reversed(groups):
        if any(semantic_goal_movement(event, current_goal_axis) for event in group):
            break
        stagnation_streak += 1
    family_ids = {
        stable_scope_value(
            first_present(
                event,
                (
                    "root_family_key",
                    "blocker_root_family",
                    "profile_scope.root_family_key",
                ),
            )
        )
        for event in axis_events
    }
    family_ids.discard("")
    return {
        "status": "evaluated" if current_goal_axis else "scope_unknown",
        "goal_axis": current_goal_axis or None,
        "cycle_count": len(groups),
        "family_ids": sorted(family_ids),
        "semantic_movement_cycle_count": sum(
            1
            for _, group in groups
            if any(semantic_goal_movement(event, current_goal_axis) for event in group)
        ),
        "producer_run_cycle_count": sum(
            1 for _, group in groups if any(fresh_run_id(event) for event in group)
        ),
        "safety_or_governance_cycle_count": sum(
            1
            for _, group in groups
            if any(
                str(event.get("progress_verdict") or "").lower() == "safety_only"
                or str(
                    first_present(event, ("effective_progress_kind", "progress_kind"))
                    or ""
                ).lower()
                == "governance_only"
                for event in group
            )
        ),
        "no_semantic_movement_streak": stagnation_streak,
        "family_change_resets_streak": False,
        "hard_gate": False,
    }


def scope_state(events: list[dict[str, Any]]) -> ScopeState:
    latest_scope = family_scope(events[-1]) if events else family_scope({})
    profile_scope_unverified = not all(latest_scope.values())
    scoped_events = (
        [event for event in events if same_family_scope(event, latest_scope)]
        if not profile_scope_unverified
        else []
    )
    latest_execution_scope = (
        execution_scope(events[-1]) if events else execution_scope({})
    )
    missing = sorted(key for key, value in latest_execution_scope.items() if not value)
    window, window_status = _starvation_window(events)
    evidence_required = [*missing]
    if window is None:
        evidence_required.append("execution_starvation_window")
    scope_known = not evidence_required
    recent_groups = cycle_groups(events)[-window:] if window else []
    recent_events = [event for _, group in recent_groups for event in group]
    recent_execution_events = (
        [
            event
            for event in recent_events
            if same_execution_scope(event, latest_execution_scope)
        ]
        if scope_known
        else []
    )
    recent_run_ids = sorted(
        {run_id for event in recent_execution_events if (run_id := fresh_run_id(event))}
    )
    if not scope_known:
        starvation_status, starvation = "scope_unknown", None
    elif recent_run_ids:
        starvation_status, starvation = "absent", False
    else:
        starvation_status, starvation = "present", True
    return ScopeState(
        latest_scope=latest_scope,
        profile_scope_unverified=profile_scope_unverified,
        scoped_events=scoped_events,
        decision_events=scoped_events if not profile_scope_unverified else [],
        latest_execution_scope=latest_execution_scope,
        execution_scope_known=scope_known,
        execution_scope_evidence_required=evidence_required,
        execution_starvation_status=starvation_status,
        execution_starvation=starvation,
        recent_run_ids=recent_run_ids,
        execution_starvation_window=window,
        execution_starvation_window_status=window_status,
        goal_axis_projection=_goal_axis_projection(events, latest_execution_scope),
    )
