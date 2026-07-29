"""Session start, stop, and human-readable status projection."""

from __future__ import annotations

from typing import Any

from .contracts import ContinuationContractError
from .state import build_state, evolve, validate_state


def start_session(
    *,
    session_lease: dict[str, Any],
    session_lease_binding: dict[str, str],
    cycle_id: str,
    task_id: str,
    created_at: str,
) -> dict[str, Any]:
    """Start a session from a validated authority lease."""

    from manage_agent_authority.session_lease import validate_session_lease

    lease = validate_session_lease(session_lease)
    if lease["lifecycle"]["status"] != "live":
        raise ContinuationContractError("cannot start from an inactive session lease")
    return build_state(
        session_id=lease["session_binding"]["session_id"],
        session_lease_binding=session_lease_binding,
        goal_id=lease["goal_id"],
        task_family=lease["task_family"],
        cycle_id=cycle_id,
        task_id=task_id,
        created_at=created_at,
        budgets=lease["budgets"],
    )


def stop_session(
    value: dict[str, Any], *, at: str, reason: str = "user_stop"
) -> dict[str, Any]:
    state = validate_state(value)
    return evolve(
        state,
        at=at,
        status="stopped",
        host_session_live=False,
        pending_action=state["pending_action"],
        last_stop_reason=reason,
    )


def status_card(value: dict[str, Any]) -> dict[str, Any]:
    state = validate_state(value)
    pending = state["pending_action"] or {}
    if state["status"] in {"stopped", "complete", "quarantined"}:
        next_actor = None
        next_action = None
        next_target = None
    elif (
        state["status"] == "host_boundary"
        and state["last_stop_reason"] == "awaiting_effect_settlement"
    ):
        next_actor = "external"
        next_action = "wait_external"
        next_target = pending.get("target")
    elif state["status"] == "host_boundary":
        next_actor = "host"
        next_action = "request_host_approval"
        next_target = "session"
    else:
        next_actor = pending.get("actor")
        next_action = pending.get("kind")
        next_target = pending.get("target")
    return {
        "session": state["session_id"],
        "profile": state["profile_id"],
        "status": state["status"],
        "goal": state["goal_id"],
        "task_family": state["task_family"],
        "cycle": state["active_cycle_id"],
        "task": state["active_task_id"],
        "next_actor": next_actor,
        "next_action": next_action,
        "next_target": next_target,
        "reason": state["last_stop_reason"],
        "remaining": {
            "cycles": max(
                0, state["budgets"]["max_cycles"] - state["usage"]["cycles"]
            ),
            "agent_actions": max(
                0,
                state["budgets"]["max_agent_actions"]
                - state["usage"]["agent_actions"],
            ),
            "long_run_slots": max(
                0,
                state["budgets"]["max_concurrent_long_runs"]
                - len(state["usage"]["active_long_runs"]),
            ),
        },
    }


__all__ = ("start_session", "status_card", "stop_session")
