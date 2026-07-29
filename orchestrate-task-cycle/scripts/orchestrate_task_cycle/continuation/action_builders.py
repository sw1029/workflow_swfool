"""Closed action projections for the continuation state machine."""

from __future__ import annotations

from typing import Any

from .actions import build_action
from .contracts import ContinuationContractError


def continuation_token(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "state_version": state["state_version"],
        "state_sha256": state["state_sha256"],
    }


def effect_class(
    preparation: dict[str, Any],
    *,
    local_long_run_authorized: bool = False,
) -> str:
    """Resolve only effect classes safe for deterministic agent dispatch."""

    from ..stage.executor_registry import continuation_effect_class

    executor = preparation.get("executor_spec")
    if not isinstance(executor, dict):
        return "unknown"
    executor_kind = str(
        preparation.get("executor_kind")
        or executor.get("executor_kind")
        or ""
    )
    return continuation_effect_class(
        str(preparation.get("target") or ""),
        executor_kind=executor_kind,
        side_effect_class=str(executor.get("side_effect_class") or ""),
        local_long_run_authorized=local_long_run_authorized,
    )


def owner_action(
    state: dict[str, Any],
    advance_result: dict[str, Any],
    *,
    resolved_effect_class: str | None = None,
) -> dict[str, Any]:
    preparation = advance_result.get("preparation")
    if not isinstance(preparation, dict):
        raise ContinuationContractError(
            "owner boundary is missing a stage preparation"
        )
    executor = preparation.get("executor_spec")
    if not isinstance(executor, dict):
        raise ContinuationContractError(
            "stage preparation is missing executor_spec"
        )
    executor_kind = str(
        preparation.get("executor_kind") or executor.get("executor_kind") or ""
    )
    if executor_kind not in {"owner", "hybrid"}:
        raise ContinuationContractError(
            "continuation owner boundary has an unsupported executor"
        )
    publication = advance_result.get("preparation_publication")
    if not isinstance(publication, dict):
        raise ContinuationContractError(
            "owner boundary preparation was not durably published"
        )
    prep_binding = {
        "ref": publication.get("preparation_ref"),
        "sha256": publication.get("preparation_sha256"),
    }
    work = preparation.get("work_order_binding")
    work_binding = (
        {"ref": work.get("ref"), "sha256": work.get("sha256")}
        if isinstance(work, dict)
        else None
    )
    allowed_profiles = executor.get("allowed_routing_profiles")
    profile_id = (
        sorted(str(item) for item in allowed_profiles)[0]
        if isinstance(allowed_profiles, list) and allowed_profiles
        else None
    )
    return build_action(
        actor="agent",
        kind="run_hybrid" if executor_kind == "hybrid" else "run_owner",
        session_id=state["session_id"],
        cycle_id=state["active_cycle_id"],
        task_id=state["active_task_id"],
        target=str(preparation.get("target") or ""),
        owner_skill=str(executor.get("owner_id") or ""),
        preparation_binding=prep_binding,
        work_order_binding=work_binding,
        routing={"profile_id": profile_id} if profile_id else {},
        continuation_token=continuation_token(state),
        effect_class=resolved_effect_class or effect_class(preparation),
        required_result_contract=dict(preparation.get("result_contract") or {}),
        reason=str(advance_result.get("stop_reason") or "owner_boundary"),
    )


def boundary_action(
    state: dict[str, Any],
    *,
    actor: str,
    kind: str,
    reason: str,
    target: str = "session",
    evidence_sha256: str | None = None,
) -> dict[str, Any]:
    return build_action(
        actor=actor,
        kind=kind,
        session_id=state["session_id"],
        cycle_id=state["active_cycle_id"],
        task_id=state["active_task_id"],
        target=target,
        owner_skill=None,
        preparation_binding=None,
        work_order_binding=None,
        routing=(
            {"boundary_evidence_sha256": evidence_sha256}
            if evidence_sha256
            else {}
        ),
        continuation_token=continuation_token(state),
        effect_class="external" if actor == "external" else "unknown",
        required_result_contract={},
        reason=reason,
    )


def complete_action(state: dict[str, Any], reason: str) -> dict[str, Any]:
    return build_action(
        actor="system",
        kind="complete",
        session_id=state["session_id"],
        cycle_id=state["active_cycle_id"],
        task_id=state["active_task_id"],
        target="cycle",
        owner_skill=None,
        preparation_binding=None,
        work_order_binding=None,
        routing={},
        continuation_token=continuation_token(state),
        effect_class="observe_only",
        required_result_contract={},
        reason=reason,
    )


def monitor_action(state: dict[str, Any], reason: str) -> dict[str, Any]:
    return build_action(
        actor="agent",
        kind="monitor_run",
        session_id=state["session_id"],
        cycle_id=state["active_cycle_id"],
        task_id=state["active_task_id"],
        target="run",
        owner_skill="monitor-running-execution",
        preparation_binding=None,
        work_order_binding=None,
        routing={},
        continuation_token=continuation_token(state),
        effect_class="observe_only",
        required_result_contract={},
        reason=reason,
    )


def reissue_action(
    state: dict[str, Any], action: dict[str, Any]
) -> dict[str, Any]:
    """Rebind a proved-not-dispatched action to the current state token."""

    return build_action(
        actor=str(action["actor"]),
        kind=str(action["kind"]),
        session_id=state["session_id"],
        cycle_id=state["active_cycle_id"],
        task_id=state["active_task_id"],
        target=str(action["target"]),
        owner_skill=action.get("owner_skill"),
        preparation_binding=action.get("preparation_binding"),
        work_order_binding=action.get("work_order_binding"),
        routing=dict(action.get("routing") or {}),
        continuation_token=continuation_token(state),
        effect_class=str(action["effect_class"]),
        required_result_contract=dict(
            action.get("required_result_contract") or {}
        ),
        reason=action.get("reason"),
    )


__all__ = (
    "boundary_action",
    "complete_action",
    "continuation_token",
    "effect_class",
    "monitor_action",
    "owner_action",
    "reissue_action",
)
