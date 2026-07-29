"""Stable user/external boundary identity and deterministic recheck helpers."""

from __future__ import annotations

from typing import Any

from .action_builders import effect_class
from .contracts import digest
from .state import evolve


_USER_REASONS = frozenset(
    {
        "awaiting_exact_approval",
        "awaiting_risk_acceptance",
        "awaiting_goal_truth",
        "awaiting_design_selection",
    }
)


def resolve_effect_class(
    state: dict[str, Any],
    preparation: dict[str, Any],
    adapter: Any,
    *,
    at: str,
) -> str:
    resolved = effect_class(preparation)
    if resolved != "unknown" or preparation.get("target") != "run":
        return resolved
    classifier = getattr(adapter, "classify_effect", None)
    if not callable(classifier):
        return resolved
    candidate = classifier(state, preparation, at=at)
    return "local_long_run" if candidate == "local_long_run" else resolved


def boundary_evidence_sha256(result: dict[str, Any]) -> str:
    preparation = result.get("preparation")
    publication = result.get("preparation_publication")
    prepared = preparation if isinstance(preparation, dict) else {}
    published = publication if isinstance(publication, dict) else {}
    return digest(
        {
            "status": result.get("status"),
            "stop_reason": result.get("stop_reason"),
            "blocked_target": result.get("blocked_target"),
            "closure_only": result.get("closure_only"),
            "preparation": {
                key: prepared.get(key)
                for key in (
                    "schema_version",
                    "preparation_id",
                    "target",
                    "state_fingerprint",
                    "next_action",
                )
                if key in prepared
            },
            "preparation_publication": {
                key: published.get(key)
                for key in (
                    "preparation_ref",
                    "preparation_sha256",
                    "preparation_body_sha256",
                )
                if key in published
            },
        }
    )


def _descriptor(
    result: dict[str, Any], resolved_effect: str | None
) -> tuple[str, str, str, str] | None:
    preparation = result.get("preparation")
    if (
        str(result.get("status") or "") == "waiting"
        and isinstance(preparation, dict)
        and resolved_effect in {"external", "unknown"}
    ):
        return (
            "user",
            "request_approval",
            "awaiting_effect_classification",
            str(preparation.get("target") or "session"),
        )
    reason = str(result.get("stop_reason") or "workflow_blocked")
    if reason in _USER_REASONS:
        return ("user", "request_approval", reason, "session")
    if reason == "awaiting_external_input":
        return ("external", "wait_external", reason, "session")
    return None


def same_pending_boundary(
    pending: dict[str, Any],
    result: dict[str, Any],
    *,
    resolved_effect: str | None,
) -> bool:
    descriptor = _descriptor(result, resolved_effect)
    if descriptor is None:
        return False
    actor, kind, reason, target = descriptor
    return (
        pending.get("actor") == actor
        and pending.get("kind") == kind
        and pending.get("reason") == reason
        and pending.get("target") == target
        and pending.get("routing")
        == {
            "boundary_evidence_sha256": boundary_evidence_sha256(result)
        }
    )


def recheck_pending_boundary(
    state: dict[str, Any],
    adapter: Any,
    *,
    at: str,
) -> tuple[
    dict[str, Any],
    dict[str, Any] | None,
    dict[str, Any] | None,
    str | None,
]:
    pending = state.get("pending_action")
    if pending is None or not state["host_session_live"]:
        return state, None, None, None
    if pending.get("actor") not in {"user", "external"}:
        return state, None, pending, None
    advanced = adapter.advance(
        state["active_cycle_id"], closure_only=state["closure_only"]
    )
    prepared = advanced.get("preparation")
    resolved = (
        resolve_effect_class(state, prepared, adapter, at=at)
        if isinstance(prepared, dict)
        else None
    )
    if same_pending_boundary(
        pending, advanced, resolved_effect=resolved
    ):
        return state, None, pending, resolved
    return (
        evolve(
            state,
            at=at,
            status="active",
            pending_action=None,
            last_stop_reason=None,
        ),
        advanced,
        None,
        resolved,
    )


__all__ = (
    "boundary_evidence_sha256",
    "recheck_pending_boundary",
    "resolve_effect_class",
    "same_pending_boundary",
)
