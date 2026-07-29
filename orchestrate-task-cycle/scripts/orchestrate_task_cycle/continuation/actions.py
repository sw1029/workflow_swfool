"""Closed ``continuation_action@v1`` producer and validator."""

from __future__ import annotations

from typing import Any

from .contracts import (
    ContinuationContractError,
    binding,
    digest,
    opaque,
    sha,
)


ACTION_CONTRACT_ID = "continuation_action@v1"
ACTORS = frozenset({"system", "agent", "user", "host", "external"})
KINDS = frozenset(
    {
        "run_owner",
        "run_hybrid",
        "request_approval",
        "request_host_approval",
        "wait_external",
        "monitor_run",
        "complete",
        "stop",
    }
)
EFFECT_CLASSES = frozenset(
    {
        "observe_only",
        "local_reversible",
        "local_long_run",
        "local_commit",
        "external",
        "unknown",
    }
)
_ACTOR_KINDS = {
    "system": {"monitor_run", "complete", "stop"},
    "agent": {"run_owner", "run_hybrid", "monitor_run"},
    "user": {"request_approval", "stop"},
    "host": {"request_host_approval"},
    "external": {"wait_external"},
}


def _closed_object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ContinuationContractError(f"{label} must be an object")
    return value


def _material(value: dict[str, Any]) -> dict[str, Any]:
    return {key: value[key] for key in value if key != "action_id"}


def build_action(
    *,
    actor: str,
    kind: str,
    session_id: str,
    cycle_id: str,
    task_id: str,
    target: str,
    owner_skill: str | None,
    preparation_binding: dict[str, Any] | None,
    work_order_binding: dict[str, Any] | None,
    routing: dict[str, Any],
    continuation_token: dict[str, Any],
    effect_class: str,
    required_result_contract: dict[str, Any],
    reason: str | None = None,
) -> dict[str, Any]:
    action: dict[str, Any] = {
        "contract_id": ACTION_CONTRACT_ID,
        "actor": actor,
        "kind": kind,
        "session_id": session_id,
        "cycle_id": cycle_id,
        "task_id": task_id,
        "target": target,
        "owner_skill": owner_skill,
        "preparation_binding": preparation_binding,
        "work_order_binding": work_order_binding,
        "routing": routing,
        "continuation_token": continuation_token,
        "effect_class": effect_class,
        "required_result_contract": required_result_contract,
        "reason": reason,
    }
    normalized = _normalize_action(action)
    normalized["action_id"] = f"action-{digest(normalized)[:32]}"
    return validate_action(normalized)


def _normalize_action(value: dict[str, Any]) -> dict[str, Any]:
    actor = str(value.get("actor") or "")
    kind = str(value.get("kind") or "")
    if actor not in ACTORS or kind not in KINDS:
        raise ContinuationContractError("unsupported continuation actor or kind")
    if kind not in _ACTOR_KINDS[actor]:
        raise ContinuationContractError("continuation actor/kind combination is invalid")
    effect_class = str(value.get("effect_class") or "")
    if effect_class not in EFFECT_CLASSES:
        raise ContinuationContractError("unsupported continuation effect_class")
    if effect_class in {"external", "unknown"} and actor == "agent":
        raise ContinuationContractError(
            "agent actions cannot automatically dispatch external or unknown effects"
        )
    owner_skill = opaque(value.get("owner_skill"), "owner_skill", nullable=True)
    if effect_class == "local_long_run" and (
        actor != "agent"
        or kind != "run_owner"
        or value.get("target") != "run"
        or owner_skill != "run-task-code-and-log"
    ):
        raise ContinuationContractError(
            "local_long_run is restricted to the registered run owner"
        )
    if kind in {"run_owner", "run_hybrid"} and owner_skill is None:
        raise ContinuationContractError("owner actions require owner_skill")
    if kind not in {"run_owner", "run_hybrid", "monitor_run"} and owner_skill is not None:
        raise ContinuationContractError("non-owner actions cannot carry owner_skill")
    continuation = _closed_object(
        value.get("continuation_token"), "continuation_token"
    )
    if set(continuation) != {"state_version", "state_sha256"}:
        raise ContinuationContractError("continuation_token fields are not closed")
    state_version = continuation.get("state_version")
    if isinstance(state_version, bool) or not isinstance(state_version, int) or state_version < 1:
        raise ContinuationContractError("continuation state_version must be positive")
    reason = value.get("reason")
    if reason is not None:
        reason = opaque(reason, "reason")
    return {
        "contract_id": ACTION_CONTRACT_ID,
        "actor": actor,
        "kind": kind,
        "session_id": opaque(value.get("session_id"), "session_id"),
        "cycle_id": opaque(value.get("cycle_id"), "cycle_id"),
        "task_id": opaque(value.get("task_id"), "task_id"),
        "target": opaque(value.get("target"), "target"),
        "owner_skill": owner_skill,
        "preparation_binding": binding(
            value.get("preparation_binding"),
            "preparation_binding",
            nullable=True,
        ),
        "work_order_binding": binding(
            value.get("work_order_binding"),
            "work_order_binding",
            nullable=True,
        ),
        "routing": _closed_object(value.get("routing"), "routing"),
        "continuation_token": {
            "state_version": state_version,
            "state_sha256": sha(
                continuation.get("state_sha256"),
                "continuation_token.state_sha256",
            ),
        },
        "effect_class": effect_class,
        "required_result_contract": _closed_object(
            value.get("required_result_contract"),
            "required_result_contract",
        ),
        "reason": reason,
    }


def validate_action(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ContinuationContractError("continuation action must be an object")
    fields = {
        "contract_id",
        "action_id",
        "actor",
        "kind",
        "session_id",
        "cycle_id",
        "task_id",
        "target",
        "owner_skill",
        "preparation_binding",
        "work_order_binding",
        "routing",
        "continuation_token",
        "effect_class",
        "required_result_contract",
        "reason",
    }
    if set(value) != fields or value.get("contract_id") != ACTION_CONTRACT_ID:
        raise ContinuationContractError("continuation action contract is not closed")
    normalized = _normalize_action(value)
    expected = f"action-{digest(normalized)[:32]}"
    if value.get("action_id") != expected:
        raise ContinuationContractError("continuation action identity mismatch")
    return {**normalized, "action_id": expected}


__all__ = (
    "ACTION_CONTRACT_ID",
    "ACTORS",
    "EFFECT_CLASSES",
    "KINDS",
    "ContinuationContractError",
    "build_action",
    "validate_action",
)
