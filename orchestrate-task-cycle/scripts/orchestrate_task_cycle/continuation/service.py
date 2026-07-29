"""Deterministic continuation state machine.

The driver never invokes a model.  It advances registered deterministic work and
returns a closed action whenever an owner, user, host, or external actor is
required.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Protocol

from .actions import validate_action
from .action_builders import (
    boundary_action,
    complete_action,
    monitor_action,
    owner_action,
    reissue_action,
)
from .boundary_recheck import (
    boundary_evidence_sha256,
    recheck_pending_boundary,
    resolve_effect_class,
)
from .contracts import ContinuationContractError, digest
from .lifecycle import start_session, status_card, stop_session
from .state import evolve, validate_state
from .usage import usage_after_result as _usage_after_result


class ContinuationAdapter(Protocol):
    """Repository workflow adapter used by the deterministic session driver."""

    def advance(self, cycle_id: str, *, closure_only: bool) -> dict[str, Any]: ...

    def accept(
        self, action: dict[str, Any], result: dict[str, Any]
    ) -> dict[str, Any]: ...

    def recover(
        self, action: dict[str, Any]
    ) -> dict[str, Any]: ...

    def selected_successor(
        self, cycle_id: str
    ) -> dict[str, Any] | None: ...


def _selected_successor(
    state: dict[str, Any],
    adapter: ContinuationAdapter,
    *,
    at: str,
) -> dict[str, Any] | None:
    successor = adapter.selected_successor(state["active_cycle_id"])
    if not successor or successor.get("outcome") != "selected":
        return None
    fields = {
        "outcome",
        "cycle_id",
        "task_id",
        "goal_id",
        "task_family",
        "risk_envelope_match",
    }
    if set(successor) != fields:
        raise ContinuationContractError("selected successor receipt is not closed")
    if (
        successor["goal_id"] != state["goal_id"]
        or successor["task_family"] != state["task_family"]
        or successor["risk_envelope_match"] is not True
    ):
        return None
    if state["usage"]["cycles"] >= state["budgets"]["max_cycles"]:
        return None
    next_cycle = str(successor["cycle_id"])
    if next_cycle in state["cycle_ids"]:
        return None
    usage = deepcopy(state["usage"])
    usage["cycles"] += 1
    return evolve(
        state,
        at=at,
        cycle_ids=[*state["cycle_ids"], next_cycle],
        active_cycle_id=next_cycle,
        active_task_id=str(successor["task_id"]),
        status="active",
        usage=usage,
        last_stop_reason=None,
    )


def _host_boundary(
    state: dict[str, Any],
    *,
    at: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    pending = state.get("pending_action")
    if state["status"] == "host_boundary":
        action = boundary_action(
            state,
            actor="host",
            kind="request_host_approval",
            reason="host_session_not_live",
        )
        return state, action
    boundary_state = evolve(
        state,
        at=at,
        status="host_boundary",
        # Preserve the possible in-flight effect.  Replacing it with the host
        # prompt destroys the only durable recovery handle.
        pending_action=pending,
        last_stop_reason="host_session_not_live",
    )
    action = boundary_action(
        boundary_state,
        actor="host",
        kind="request_host_approval",
        reason="host_session_not_live",
    )
    return boundary_state, action


def _resume_after_host_boundary(
    state: dict[str, Any],
    adapter: ContinuationAdapter,
    *,
    at: str,
) -> tuple[dict[str, Any], dict[str, Any]] | None:
    """Recover a preserved agent effect before it can be offered again."""

    pending = state.get("pending_action")
    if not isinstance(pending, dict) or pending.get("actor") != "agent":
        return None
    resumed = evolve(
        state,
        at=at,
        status="waiting",
        last_stop_reason=str(pending.get("reason") or "owner_boundary"),
    )
    recovered, outcome = recover_session(resumed, adapter, at=at)
    disposition = str(outcome.get("status") or "")
    if disposition == "not_dispatched":
        original = recovered.get("pending_action")
        if not isinstance(original, dict):
            raise ContinuationContractError(
                "recovery lost a not-dispatched pending action"
            )
        cleared = evolve(
            recovered,
            at=at,
            status="active",
            pending_action=None,
            last_stop_reason=None,
        )
        action = reissue_action(cleared, original)
        waiting = evolve(
            cleared,
            at=at,
            status="waiting",
            pending_action=action,
            last_stop_reason=str(action.get("reason") or "owner_boundary"),
        )
        return waiting, action
    if recovered["status"] == "quarantined":
        return recovered, complete_action(
            recovered, recovered["last_stop_reason"] or "unknown_effect"
        )
    if disposition == "pending":
        waiting = evolve(
            recovered,
            at=at,
            status="host_boundary",
            last_stop_reason="awaiting_effect_settlement",
        )
        return waiting, boundary_action(
            waiting,
            actor="external",
            kind="wait_external",
            reason="awaiting_effect_settlement",
            target=str(pending.get("target") or "session"),
        )
    if disposition == "settled":
        quarantined = evolve(
            recovered,
            at=at,
            status="quarantined",
            pending_action=None,
            last_stop_reason="effect_result_missing_after_host_loss",
        )
        return quarantined, complete_action(
            quarantined, "effect_result_missing_after_host_loss"
        )
    # A recovered result may have advanced and cleared the pending action.
    return continue_session(recovered, adapter, at=at)


def _queue_agent_action(
    state: dict[str, Any],
    action: dict[str, Any],
    *,
    at: str,
    reason: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    usage = deepcopy(state["usage"])
    if usage["agent_actions"] >= state["budgets"]["max_agent_actions"]:
        stopped = evolve(
            state,
            at=at,
            status="stopped",
            last_stop_reason="agent_action_budget_exhausted",
        )
        return stopped, complete_action(
            stopped, "agent_action_budget_exhausted"
        )
    usage["agent_actions"] += 1
    waiting = evolve(
        state,
        at=at,
        status="waiting",
        pending_action=action,
        usage=usage,
        last_stop_reason=reason,
    )
    return waiting, action


def continue_session(
    value: dict[str, Any],
    adapter: ContinuationAdapter,
    *,
    at: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    state = validate_state(value)
    if state["status"] in {"stopped", "quarantined"}:
        action = complete_action(
            state, state["last_stop_reason"] or state["status"]
        )
        return state, action
    if state["status"] == "host_boundary":
        if not state["host_session_live"]:
            return _host_boundary(state, at=at)
        resumed = _resume_after_host_boundary(state, adapter, at=at)
        if resumed is not None:
            return resumed
        state = evolve(
            state,
            at=at,
            status="active",
            pending_action=None,
            last_stop_reason=None,
        )
    state, advanced, preserved, advanced_effect = recheck_pending_boundary(
        state, adapter, at=at
    )
    if preserved is not None:
        return state, preserved
    if state["status"] == "complete":
        successor = _selected_successor(state, adapter, at=at)
        if successor is None:
            return state, complete_action(state, "session_complete")
        state = successor
    if not state["host_session_live"]:
        return _host_boundary(state, at=at)
    result = advanced or adapter.advance(
        state["active_cycle_id"], closure_only=state["closure_only"]
    )
    status = str(result.get("status") or "")
    if status == "complete":
        completed = evolve(
            state,
            at=at,
            status="complete",
            last_stop_reason="cycle_complete",
        )
        successor = _selected_successor(completed, adapter, at=at)
        if successor is not None:
            return continue_session(successor, adapter, at=at)
        return completed, complete_action(completed, "cycle_complete")
    if status == "waiting" and isinstance(result.get("preparation"), dict):
        preparation = result["preparation"]
        resolved_effect = (
            advanced_effect
            if advanced is result and advanced_effect is not None
            else resolve_effect_class(state, preparation, adapter, at=at)
        )
        if resolved_effect in {"external", "unknown"}:
            reason = "awaiting_effect_classification"
            action = boundary_action(
                state,
                actor="user",
                kind="request_approval",
                reason=reason,
                target=str(preparation.get("target") or "session"),
                evidence_sha256=boundary_evidence_sha256(result),
            )
            return evolve(
                state,
                at=at,
                status="waiting",
                pending_action=action,
                last_stop_reason=reason,
            ), action
        action = owner_action(
            state, result, resolved_effect_class=resolved_effect
        )
        return _queue_agent_action(
            state,
            action,
            at=at,
            reason=str(result.get("stop_reason") or "owner_boundary"),
        )
    reason = str(result.get("stop_reason") or "workflow_blocked")
    if reason == "awaiting_running_execution":
        action = monitor_action(state, reason)
        return _queue_agent_action(state, action, at=at, reason=reason)
    if reason in {
        "awaiting_exact_approval",
        "awaiting_risk_acceptance",
        "awaiting_goal_truth",
        "awaiting_design_selection",
    }:
        action = boundary_action(
            state,
            actor="user",
            kind="request_approval",
            reason=reason,
            evidence_sha256=boundary_evidence_sha256(result),
        )
        return evolve(
            state,
            at=at,
            status="waiting",
            pending_action=action,
            last_stop_reason=reason,
        ), action
    if reason == "awaiting_external_input":
        action = boundary_action(
            state,
            actor="external",
            kind="wait_external",
            reason=reason,
            evidence_sha256=boundary_evidence_sha256(result),
        )
        return evolve(
            state,
            at=at,
            status="waiting",
            pending_action=action,
            last_stop_reason=reason,
        ), action
    quarantined = evolve(
        state,
        at=at,
        status="quarantined",
        last_stop_reason=reason,
    )
    return quarantined, complete_action(quarantined, reason)


def accept_action(
    value: dict[str, Any],
    *,
    action: dict[str, Any],
    result: dict[str, Any],
    adapter: ContinuationAdapter,
    at: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    state = validate_state(value)
    validated = validate_action(action)
    result_sha = digest(result)
    prior = state["accepted_actions"].get(validated["action_id"])
    if prior is not None:
        if prior != result_sha:
            raise ContinuationContractError(
                "accepted action replay changed its result"
            )
        return state, {"status": "reused", "result_sha256": result_sha}
    if state["pending_action"] != validated:
        raise ContinuationContractError("action is not the pending session action")
    token = validated["continuation_token"]
    if token["state_version"] != state["state_version"] - 1:
        raise ContinuationContractError("continuation token is stale or forged")
    # The action binds the state immediately before it was inserted as pending;
    # equality to the current state would therefore be circular.
    if token["state_sha256"] == state["state_sha256"]:
        raise ContinuationContractError("continuation token is circular")
    outcome = adapter.accept(validated, result)
    if outcome.get("status") not in {"accepted", "reused"}:
        if outcome.get("effect_status") == "unknown":
            quarantined = evolve(
                state,
                at=at,
                status="quarantined",
                pending_action=None,
                last_stop_reason="unknown_effect",
            )
            return quarantined, outcome
        raise ContinuationContractError("owner action result was not accepted")
    accepted = dict(state["accepted_actions"])
    accepted[validated["action_id"]] = result_sha
    usage = _usage_after_result(state, validated, result, outcome)
    closure_only = state["closure_only"] or (
        outcome.get("run_terminal_status") == "failed_closed"
    )
    updated = evolve(
        state,
        at=at,
        status="active",
        pending_action=None,
        accepted_actions=accepted,
        usage=usage,
        closure_only=closure_only,
        last_stop_reason=None,
    )
    return updated, outcome


def recover_session(
    value: dict[str, Any],
    adapter: ContinuationAdapter,
    *,
    at: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    state = validate_state(value)
    action = state["pending_action"]
    if action is None:
        return state, {"status": "nothing_to_recover"}
    recovery = adapter.recover(action)
    disposition = recovery.get("status")
    if disposition == "result_found" and isinstance(recovery.get("result"), dict):
        token = action["continuation_token"]
        if token["state_version"] != state["state_version"] - 1:
            cleared = evolve(
                state,
                at=at,
                status="active",
                pending_action=None,
                last_stop_reason=None,
            )
            action = reissue_action(cleared, action)
            state = evolve(
                cleared,
                at=at,
                status="waiting",
                pending_action=action,
                last_stop_reason=str(
                    action.get("reason") or "owner_boundary"
                ),
            )
        return accept_action(
            state,
            action=action,
            result=recovery["result"],
            adapter=adapter,
            at=at,
        )
    if disposition in {"not_dispatched", "pending", "settled"}:
        return state, recovery
    quarantined = evolve(
        state,
        at=at,
        status="quarantined",
        pending_action=None,
        last_stop_reason="unknown_effect",
    )
    return quarantined, {
        "status": "quarantined",
        "reason": "unknown_effect",
    }


__all__ = (
    "ContinuationAdapter",
    "accept_action",
    "continue_session",
    "recover_session",
    "start_session",
    "status_card",
    "stop_session",
)
