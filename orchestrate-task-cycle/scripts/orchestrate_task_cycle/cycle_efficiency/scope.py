from __future__ import annotations

from typing import Any

from .common import (
    cycle_groups,
    execution_scope,
    family_scope,
    first_present,
    same_execution_scope,
    same_family_scope,
    semantic_goal_movement,
    stable_scope_value,
)
from .producer_receipts import (
    execution_applicability,
    matching_fresh_run,
    required_input_binding,
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
    events: list[dict[str, Any]],
    latest_execution_scope: dict[str, str],
    input_binding: dict[str, str] | None,
    *,
    strict_binding: bool,
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

    def has_matching_run(event: dict[str, Any]) -> bool:
        return (
            matching_fresh_run(
                event,
                input_binding,
                strict_binding=strict_binding,
            )[0]
            is not None
        )

    stagnation_streak = 0
    for _, group in reversed(groups):
        if any(
            has_matching_run(event) and semantic_goal_movement(event, current_goal_axis)
            for event in group
        ):
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
            if any(
                has_matching_run(event)
                and semantic_goal_movement(event, current_goal_axis)
                for event in group
            )
        ),
        "producer_run_cycle_count": sum(
            1 for _, group in groups if any(has_matching_run(event) for event in group)
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


def _unique_matched_runs(
    events: list[dict[str, Any]],
    input_binding: dict[str, str] | None,
    *,
    strict_binding: bool,
) -> tuple[list[str], list[dict[str, Any]]]:
    matched = [
        pair
        for event in events
        if (
            pair := matching_fresh_run(
                event,
                input_binding,
                strict_binding=strict_binding,
            )
        )[0]
    ]
    receipt_hashes_by_run: dict[str, set[str]] = {}
    receipts_by_run: dict[str, dict[str, Any]] = {}
    for run_id, receipt in matched:
        if receipt is None:
            continue
        receipt_hashes_by_run.setdefault(run_id, set()).add(receipt["receipt_sha256"])
        receipts_by_run[run_id] = receipt
    conflicted = {
        run_id
        for run_id, receipt_hashes in receipt_hashes_by_run.items()
        if len(receipt_hashes) > 1
    }
    run_ids = sorted({run_id for run_id, _receipt in matched} - conflicted)
    receipts = [
        receipts_by_run[run_id] for run_id in run_ids if run_id in receipts_by_run
    ]
    return run_ids, receipts


def _terminal_scope_state(
    events: list[dict[str, Any]],
    latest_scope: dict[str, str],
    profile_scope_unverified: bool,
    scoped_events: list[dict[str, Any]],
    latest_execution_scope: dict[str, str],
    applicability: str,
    exclusion_reason: str | None,
    window: int | None,
    window_status: str,
) -> ScopeState | None:
    if applicability not in {"not_applicable", "excluded_by_task"}:
        return None
    not_applicable = applicability == "not_applicable"
    return ScopeState(
        latest_scope=latest_scope,
        profile_scope_unverified=profile_scope_unverified,
        scoped_events=scoped_events,
        decision_events=scoped_events if not profile_scope_unverified else [],
        latest_execution_scope=latest_execution_scope,
        execution_scope_applicability=applicability,
        execution_scope_exclusion_reason_id=exclusion_reason,
        execution_scope_status=(
            "not_applicable" if not_applicable else "excluded_by_task"
        ),
        execution_scope_known=not not_applicable,
        execution_scope_evidence_required=[],
        required_input_binding=None,
        execution_starvation_status=("not_applicable" if not_applicable else "present"),
        execution_starvation=None if not_applicable else True,
        recent_run_ids=[],
        recent_run_receipts=[],
        execution_starvation_window=None if not_applicable else window,
        execution_starvation_window_status=(
            "not_applicable" if not_applicable else window_status
        ),
        goal_axis_projection=_goal_axis_projection(
            events,
            latest_execution_scope,
            None,
            strict_binding=True,
        ),
    )


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
    latest_event = events[-1] if events else {}
    applicability, exclusion_reason = execution_applicability(latest_event)
    input_binding, input_binding_status = required_input_binding(latest_event)
    excluded_has_execution_evidence = (
        first_present(
            latest_event,
            (
                "run_id",
                "execution.run_id",
                "run.run_id",
                "fresh_run_id",
                "producer_run_receipt",
                "execution.producer_run_receipt",
                "run.producer_run_receipt",
            ),
        )
        is not None
    )
    if applicability in {"excluded_by_task", "not_applicable"} and (
        exclusion_reason is None
        or input_binding_status != "absent"
        or excluded_has_execution_evidence
    ):
        applicability = "scope_unknown"
    missing = sorted(key for key, value in latest_execution_scope.items() if not value)
    window, window_status = _starvation_window(events)
    if applicability == "excluded_by_task" and (missing or window is None):
        applicability = "scope_unknown"
    terminal = _terminal_scope_state(
        events,
        latest_scope,
        profile_scope_unverified,
        scoped_events,
        latest_execution_scope,
        applicability,
        exclusion_reason,
        window,
        window_status,
    )
    if terminal is not None:
        return terminal
    evidence_required = [*missing]
    if window is None:
        evidence_required.append("execution_starvation_window")
    strict_binding = (
        applicability in {"applicable", "scope_unknown"}
        or input_binding_status != "absent"
    )
    if applicability == "scope_unknown":
        evidence_required.append("execution_scope_applicability")
    if (
        applicability == "applicable" and input_binding_status != "valid"
    ) or input_binding_status == "invalid":
        evidence_required.append("required_input_binding")
    evidence_required = sorted(set(evidence_required))
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
    recent_run_ids, recent_run_receipts = _unique_matched_runs(
        recent_execution_events,
        input_binding,
        strict_binding=strict_binding,
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
        execution_scope_applicability=applicability,
        execution_scope_exclusion_reason_id=exclusion_reason,
        execution_scope_status="evaluated" if scope_known else "scope_unknown",
        execution_scope_known=scope_known,
        execution_scope_evidence_required=evidence_required,
        required_input_binding=input_binding,
        execution_starvation_status=starvation_status,
        execution_starvation=starvation,
        recent_run_ids=recent_run_ids,
        recent_run_receipts=recent_run_receipts,
        execution_starvation_window=window,
        execution_starvation_window_status=window_status,
        goal_axis_projection=_goal_axis_projection(
            events,
            latest_execution_scope,
            input_binding,
            strict_binding=strict_binding,
        ),
    )
