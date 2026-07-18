from __future__ import annotations

from pathlib import Path
from typing import Any

from .evaluator import evaluate
from .workflow_candidates import validated_grants
from .workflow_interaction import interaction_projection, wait_identity
from .workflow_sources import source_approvals_covering, source_recovery_identity
from .workflow_status import status_snapshot


def _decision_evidence(decision: dict[str, Any]) -> dict[str, Any]:
    return {
        "ref": None,
        "sha256": None,
        "decision_id": decision["decision_id"],
        "request_sha256": decision["request_sha256"],
        "decision": decision["decision"],
        "effective_authority_fingerprint": decision[
            "effective_authority_fingerprint"
        ],
        "selected_grants": decision["selected_grants"],
        "lineage_grants": decision["lineage_grants"],
    }


def _basis(
    kind: str,
    decision: dict[str, Any],
    *,
    source_approval: dict[str, Any] | None = None,
    blocker_codes: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "kind": kind,
        "request_sha256": decision["request_sha256"],
        "reservation": None,
        "reservation_state": None,
        "decision": _decision_evidence(decision),
        "source_approval": source_approval,
        "settlement_receipt": None,
        "blocker_codes": blocker_codes or [],
    }


def _source_blockers(source: dict[str, Any]) -> list[str]:
    return [
        code
        for item in source["unavailable_grants"]
        for code in item["blocker_codes"]
    ]


def _current_resolution(
    decision: dict[str, Any], current: dict[str, Any]
) -> dict[str, Any] | None:
    reusable_states = {
        "effect_reconciliation",
        "already_consumed",
        "already_released",
        "ready_to_resume",
        "reserved_authority_recovery",
        "ready_to_reserve",
        "source_approval_ready_for_grant",
        "source_authority_defect",
        "source_authority_exhausted",
    }
    state = current["workflow_state"]
    recovery_wait = (
        state == "needs_user_approval"
        and current["next_action"]["code"] == "approve_exact_recovery_projection"
    )
    if recovery_wait:
        reusable_states.add("needs_user_approval")
    if state not in reusable_states:
        return None
    reasons = list(decision["reason_codes"])
    recovery_identity = None
    current_wait_identity = wait_identity(decision)
    if state == "source_authority_exhausted":
        current_wait_identity = None
        recovery_identity = current["recovery_identity"]
        reasons = (
            ["source_recovery_window_closed"]
            if current["next_action"]["code"] == "prepare_fresh_recovery_plan"
            else sorted(
                {*reasons, "source_authority_no_usable_or_materializable_grant"}
            )
        )
    elif recovery_wait:
        current_wait_identity = current["wait_identity"]
        recovery_identity = current["recovery_identity"]
        reasons = ["source_authority_replacement_requires_exact_user_approval"]
    return {
        "resolution": state,
        "should_prompt": current["should_prompt"],
        "next_action": current["next_action"],
        "basis": current["workflow_basis"],
        "source_approvals": current["covering_source_approvals"],
        "reason_codes": reasons,
        "wait_identity": current_wait_identity,
        "recovery_identity": recovery_identity,
        "approval_projection": current.get("approval_projection"),
        "post_approval_handoff": current.get("post_approval_handoff"),
    }


def _source_resolution(
    decision: dict[str, Any], sources: list[dict[str, Any]]
) -> dict[str, Any]:
    groups = {
        status: [item for item in sources if item["materialization_status"] == status]
        for status in ("ready", "defect", "fresh_authority_required")
    }
    if groups["ready"]:
        source = groups["ready"][0]
        action = (
            "materialize_grant"
            if source["materializable_grant_ids"]
            else "evaluate_existing_grant"
        )
        return {
            "resolution": "source_approval_ready_for_grant",
            "should_prompt": False,
            "next_action": {"actor": "system", "code": action},
            "basis": _basis("source_approval_ready", decision, source_approval=source),
            "reason_codes": list(decision["reason_codes"]),
            "wait_identity": wait_identity(decision),
            "recovery_identity": None,
        }
    if groups["defect"]:
        source = groups["defect"][0]
        return {
            "resolution": "source_authority_defect",
            "should_prompt": False,
            "next_action": {
                "actor": "system",
                "code": "repair_source_authority_candidate",
            },
            "basis": _basis(
                "source_authority_defect",
                decision,
                source_approval=source,
                blocker_codes=_source_blockers(source),
            ),
            "reason_codes": list(decision["reason_codes"]),
            "wait_identity": wait_identity(decision),
            "recovery_identity": None,
        }
    if groups["fresh_authority_required"]:
        exhausted = groups["fresh_authority_required"]
        source = exhausted[0]
        reasons = sorted(
            {
                *decision["reason_codes"],
                "source_authority_no_usable_or_materializable_grant",
            }
        )
        return {
            "resolution": "source_authority_exhausted",
            "should_prompt": False,
            "next_action": {
                "actor": "system",
                "code": "prepare_exact_recovery_recipe",
            },
            "basis": _basis(
                "source_authority_exhausted",
                decision,
                source_approval=source,
                blocker_codes=_source_blockers(source),
            ),
            "reason_codes": reasons,
            "wait_identity": None,
            "recovery_identity": source_recovery_identity(
                decision["request_sha256"], exhausted
            ),
            "approval_projection": None,
        }
    return {
        "resolution": "needs_user_approval",
        "should_prompt": True,
        "next_action": {"actor": "user", "code": "approve_exact_projection"},
        "basis": _basis("approval_wait", decision),
        "reason_codes": list(decision["reason_codes"]),
        "wait_identity": wait_identity(decision),
        "recovery_identity": None,
    }


def _fresh_resolution(
    root: Path,
    decision: dict[str, Any],
    evaluated_at: str,
    skills_root: Path | None,
) -> dict[str, Any]:
    if decision["decision"] == "allowed":
        return {
            "resolution": "ready_to_reserve",
            "should_prompt": False,
            "next_action": {"actor": "system", "code": "reserve_exact_decision"},
            "basis": _basis("fresh_allowed", decision),
            "source_approvals": [],
            "reason_codes": list(decision["reason_codes"]),
            "wait_identity": wait_identity(decision),
            "recovery_identity": None,
        }
    if decision["decision"] == "approval_required":
        sources = source_approvals_covering(
            root,
            decision["request"],
            decision["request_sha256"],
            decision["evaluation_context"],
            evaluated_at,
            skills_root,
            validated_grants(root),
        )
        return {**_source_resolution(decision, sources), "source_approvals": sources}
    state = f"decision_{decision['decision']}"
    return {
        "resolution": state,
        "should_prompt": False,
        "next_action": {"actor": "system", "code": "route_typed_decision"},
        "basis": _basis("typed_decision", decision),
        "source_approvals": [],
        "reason_codes": list(decision["reason_codes"]),
        "wait_identity": wait_identity(decision),
        "recovery_identity": None,
    }


def resolve_operation(
    root: Path,
    request: dict[str, Any],
    context: dict[str, Any],
    *,
    evaluated_at: str,
    skills_root: Path | None,
) -> dict[str, Any]:
    decision = evaluate(
        root,
        request,
        context,
        evaluated_at=evaluated_at,
        skills_root=skills_root,
    )
    current = status_snapshot(
        root,
        request_sha256=decision["request_sha256"],
        evaluated_at=evaluated_at,
        skills_root=skills_root,
    )
    selected = _current_resolution(decision, current) or _fresh_resolution(
        root, decision, evaluated_at, skills_root
    )
    resolution = selected["resolution"]
    interaction = interaction_projection(
        resolution, selected["should_prompt"], selected["next_action"]
    )
    return {
        "schema_version": 2,
        "status": "resolved",
        "resolution": resolution,
        **interaction,
        "workflow_basis": selected["basis"],
        "decision": decision["decision"],
        "reason_codes": selected["reason_codes"],
        "effective_authority_fingerprint": decision[
            "effective_authority_fingerprint"
        ],
        "approval_projection": (
            selected.get("approval_projection") or decision.get("approval_projection")
        )
        if selected["should_prompt"]
        else None,
        "post_approval_handoff": selected.get("post_approval_handoff"),
        "wait_identity": selected["wait_identity"],
        "recovery_identity": selected["recovery_identity"],
        "existing_reservations": current["reservations"],
        "covering_source_approvals": selected["source_approvals"],
    }


__all__ = ["resolve_operation"]
