from __future__ import annotations

from typing import Any

from .workflow_evidence import settlement_receipt, workflow_basis


def _blocker_codes(source: dict[str, Any]) -> list[str]:
    return [
        code
        for item in source["unavailable_grants"]
        for code in item["blocker_codes"]
    ]


def _reservation_groups(
    inventory: dict[str, Any],
) -> dict[str, list[dict[str, Any]]]:
    reservations = inventory["reservations"]
    groups = {
        "quarantines": [
            item
            for item in reservations
            if item["state"]["status"] == "quarantined_unknown_effect"
        ],
        "consumed": [
            item for item in reservations if item["state"]["status"] == "consumed"
        ],
        "released": [
            item for item in reservations if item["state"]["status"] == "released"
        ],
    }
    for record in [*groups["consumed"], *groups["released"]]:
        record["settlement_receipt"] = settlement_receipt(
            record,
            record["state"]["status"],
            inventory["use_receipts"],
            inventory["release_receipts"],
            inventory["reconciliation_receipts"],
        )
    reserved = [
        item for item in reservations if item["state"]["status"] == "reserved"
    ]
    groups["resumable"] = [
        item for item in reserved if item["authority_effective_usable"]
    ]
    groups["blocked_reserved"] = [
        item for item in reserved if not item["authority_effective_usable"]
    ]
    return groups


def _authority_selection(candidates: dict[str, Any]) -> dict[str, Any]:
    if candidates["current_allowed"]:
        return {
            "workflow_state": "ready_to_reserve",
            "next_action": {"actor": "system", "code": "reserve_exact_decision"},
            "should_prompt": False,
            "basis": workflow_basis(
                "current_allowed", decision=candidates["current_allowed"][0]
            ),
            "recovery_identity": None,
        }
    if candidates["source_ready_waits"]:
        wait = candidates["source_ready_waits"][0]
        source = wait["source_approvals"][0]
        action = (
            "materialize_grant"
            if source["materializable_grant_ids"]
            else "evaluate_existing_grant"
        )
        return {
            "workflow_state": "source_approval_ready_for_grant",
            "next_action": {"actor": "system", "code": action},
            "should_prompt": False,
            "basis": workflow_basis(
                "source_approval_ready",
                decision=wait["decision"],
                source_approval=source,
            ),
            "recovery_identity": None,
        }
    if candidates["source_defect_waits"]:
        wait = candidates["source_defect_waits"][0]
        source = wait["source_approvals"][0]
        return {
            "workflow_state": "source_authority_defect",
            "next_action": {
                "actor": "system",
                "code": "repair_source_authority_candidate",
            },
            "should_prompt": False,
            "basis": workflow_basis(
                "source_authority_defect",
                decision=wait["decision"],
                source_approval=source,
                blocker_codes=_blocker_codes(source),
            ),
            "recovery_identity": None,
            "approval_projection": None,
            "wait_identity": None,
        }
    if candidates["recovery_replans"]:
        wait = candidates["recovery_replans"][0]
        source = wait["source_approvals"][0]
        return {
            "workflow_state": "source_authority_exhausted",
            "next_action": {
                "actor": "system",
                "code": "prepare_fresh_recovery_plan",
            },
            "should_prompt": False,
            "basis": workflow_basis(
                "source_recovery_window_closed",
                decision=wait["decision"],
                source_approval=source,
                recovery_recipe=wait["recovery_recipe"],
                blocker_codes=["source_recovery_window_closed"],
            ),
            "recovery_identity": wait["recovery_identity"],
            "approval_projection": None,
            "wait_identity": None,
            "post_approval_handoff": wait["post_approval_handoff"],
        }
    if candidates["recovery_waits"]:
        wait = candidates["recovery_waits"][0]
        source = wait["source_approvals"][0]
        return {
            "workflow_state": "needs_user_approval",
            "next_action": {
                "actor": "user",
                "code": "approve_exact_recovery_projection",
            },
            "should_prompt": True,
            "basis": workflow_basis(
                "source_authority_recovery_approval",
                decision=wait["decision"],
                source_approval=source,
                recovery_recipe=wait["recovery_recipe"],
                blocker_codes=_blocker_codes(source),
            ),
            "recovery_identity": wait["recovery_identity"],
            "approval_projection": wait["projection"],
            "wait_identity": wait["wait_identity"],
            "post_approval_handoff": wait["post_approval_handoff"],
        }
    if candidates["source_exhausted_waits"]:
        wait = candidates["source_exhausted_waits"][0]
        source = wait["source_approvals"][0]
        return {
            "workflow_state": "source_authority_exhausted",
            "next_action": {
                "actor": "system",
                "code": "prepare_exact_recovery_recipe",
            },
            "should_prompt": False,
            "basis": workflow_basis(
                "source_authority_exhausted",
                decision=wait["decision"],
                source_approval=source,
                blocker_codes=_blocker_codes(source),
            ),
            "recovery_identity": wait["recovery_identity"],
            "approval_projection": None,
            "wait_identity": None,
        }
    if candidates["waits"]:
        return {
            "workflow_state": "needs_user_approval",
            "next_action": {"actor": "user", "code": "approve_exact_projection"},
            "should_prompt": True,
            "basis": workflow_basis(
                "approval_wait", decision=candidates["waits"][0]["decision"]
            ),
            "recovery_identity": None,
            "approval_projection": candidates["waits"][0]["projection"],
            "wait_identity": candidates["waits"][0]["wait_identity"],
        }
    return {
        "workflow_state": "idle",
        "next_action": {"actor": "system", "code": "none"},
        "should_prompt": False,
        "basis": workflow_basis("idle"),
        "recovery_identity": None,
        "approval_projection": None,
        "wait_identity": None,
    }


def select_workflow(
    inventory: dict[str, Any], candidates: dict[str, Any]
) -> dict[str, Any]:
    groups = _reservation_groups(inventory)
    if groups["quarantines"]:
        selected = {
            "workflow_state": "effect_reconciliation",
            "next_action": {"actor": "system", "code": "reconcile_effect"},
            "should_prompt": False,
            "basis": workflow_basis(
                "quarantined", reservation=groups["quarantines"][0]
            ),
            "recovery_identity": None,
        }
    elif groups["consumed"]:
        record = groups["consumed"][0]
        selected = {
            "workflow_state": "already_consumed",
            "next_action": {"actor": "system", "code": "return_existing_result"},
            "should_prompt": False,
            "basis": workflow_basis(
                "consumed",
                reservation=record,
                settlement_receipt=record["settlement_receipt"],
            ),
            "recovery_identity": None,
        }
    elif groups["released"]:
        record = groups["released"][0]
        selected = {
            "workflow_state": "already_released",
            "next_action": {
                "actor": "system",
                "code": "return_existing_no_effect_settlement",
            },
            "should_prompt": False,
            "basis": workflow_basis(
                "released",
                reservation=record,
                settlement_receipt=record["settlement_receipt"],
            ),
            "recovery_identity": None,
        }
    elif groups["resumable"]:
        selected = {
            "workflow_state": "ready_to_resume",
            "next_action": {
                "actor": "system",
                "code": "resume_reserved_operation",
            },
            "should_prompt": False,
            "basis": workflow_basis(
                "reserved_usable", reservation=groups["resumable"][0]
            ),
            "recovery_identity": None,
        }
    elif groups["blocked_reserved"]:
        record = groups["blocked_reserved"][0]
        selected = {
            "workflow_state": "reserved_authority_recovery",
            "next_action": {
                "actor": "system",
                "code": "revalidate_reserved_effect_and_authority",
            },
            "should_prompt": False,
            "basis": workflow_basis(
                "reserved_authority_recovery",
                reservation=record,
                blocker_codes=record["authority_blocker_codes"],
            ),
            "recovery_identity": None,
        }
    else:
        selected = _authority_selection(candidates)
    return {**selected, **groups}


__all__ = ["select_workflow"]
