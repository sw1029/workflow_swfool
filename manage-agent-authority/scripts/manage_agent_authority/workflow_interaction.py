from __future__ import annotations

from typing import Any

from .canonical import object_sha256


def projection_wait_identity(
    projection: dict[str, Any], effective_authority_fingerprint: str
) -> str:
    core = {
        "projection_id": projection.get("projection_id"),
        "exact_replay_key": projection.get("exact_replay_key"),
        "effective_authority_fingerprint": effective_authority_fingerprint,
    }
    return f"authw-{object_sha256(core)[:24]}"


def wait_identity(decision: dict[str, Any]) -> str | None:
    projection = decision.get("approval_projection")
    if not isinstance(projection, dict):
        return None
    return projection_wait_identity(
        projection, decision["effective_authority_fingerprint"]
    )


def interaction_projection(
    workflow_state: str, should_prompt: bool, next_action: dict[str, str]
) -> dict[str, Any]:
    return {
        "outcome": workflow_state,
        "workflow_state": workflow_state,
        "should_prompt": should_prompt,
        "user_action": next_action if next_action["actor"] == "user" else None,
        "next_action": next_action,
    }


__all__ = ["interaction_projection", "projection_wait_identity", "wait_identity"]
