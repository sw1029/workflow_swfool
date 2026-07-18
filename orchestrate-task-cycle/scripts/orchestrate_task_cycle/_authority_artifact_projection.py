"""Deterministic owner projections for authority artifact verification."""

from __future__ import annotations

from typing import Any

from .authority_boundary import canonical_sha256


def _projected_approval_intent(request: dict[str, Any], reasons: list[str]) -> str:
    if "risk_acceptance_unresolved" in reasons:
        return "accept_risk_or_cost"
    if "goal_or_design_decision_unresolved" in reasons:
        return "select_design_option"
    return str(request.get("intent_type"))


def scope_projection(request: dict[str, Any]) -> dict[str, Any]:
    decision_class = request.get("decision_class")
    if decision_class == "D0":
        scope_kind = (
            "authority_policy"
            if (request.get("subject") or {}).get("kind") == "authority_policy"
            else "goal"
        )
    elif decision_class == "D1":
        scope_kind = "design"
    elif decision_class == "D2":
        scope_kind = "improvement" if request.get("pack_id") else "task"
    else:
        scope_kind = "action"
    return {
        "cycle_id": request.get("cycle_id"),
        "task_id": request.get("task_id"),
        "pack_id": request.get("pack_id"),
        "attempt_id": request.get("attempt_id"),
        "scope_kind": scope_kind,
        "decision_class": decision_class,
        "intent_type": request.get("intent_type"),
        "required_source_rank": request.get("actor_rank"),
        "risk_tier": request.get("risk_tier"),
    }


def axis_projection(decision: dict[str, Any]) -> dict[str, dict[str, Any]]:
    request = (
        decision.get("request") if isinstance(decision.get("request"), dict) else {}
    )
    context = request.get("context") if isinstance(request.get("context"), dict) else {}
    intent = request.get("intent_type")
    outcome = decision.get("decision")
    if intent != "grant_authority":
        authority = "not_applicable"
    else:
        authority = {
            "allowed": "granted",
            "approval_required": "approval_required",
            "denied": "denied",
            "classification_repair": "unverified",
            "conflict": "unverified",
        }.get(str(outcome), "not_applicable")
    local = {
        "allowed": "available",
        "not_applicable": "available",
        "classification_repair": "unverified",
        "conflict": "unverified",
    }.get(str(outcome), "unavailable")
    risk = {
        "not_required": "not_required",
        "resolved": "accepted",
        "unresolved": "confirmation_required",
        "unverified": "unverified",
    }.get(str(context.get("risk_acceptance_status")), "unverified")
    external = str(context.get("external_input_status") or "unverified")
    reasons = (
        decision.get("reason_codes")
        if isinstance(decision.get("reason_codes"), list)
        else []
    )
    external_unsupplyable = (
        "external_input_unsupplyable_route_local_or_descope" in reasons
    )
    goal = str(context.get("goal_truth_status") or "unverified")
    if outcome == "blocked_by_goal_truth" and not external_unsupplyable:
        goal = "blocked"
    statuses = {
        "authority": authority,
        "local_resolution": local,
        "external_input": external,
        "risk_cost": risk,
        "goal_truth": goal,
    }
    no_evidence = {"not_required", "not_applicable", "unverified"}
    decision_id = str(decision.get("decision_id") or "")
    return {
        name: {
            "status": status,
            "evidence_ids": [] if status in no_evidence else [f"{decision_id}:{name}"],
        }
        for name, status in statuses.items()
    }


def approval_projection(decision: dict[str, Any]) -> dict[str, Any] | None:
    if decision.get("decision") != "approval_required":
        return None
    request = (
        decision.get("request") if isinstance(decision.get("request"), dict) else {}
    )
    context = (
        decision.get("evaluation_context")
        if isinstance(decision.get("evaluation_context"), dict)
        else {}
    )
    ceiling = (
        context.get("session_ceiling")
        if isinstance(context.get("session_ceiling"), dict)
        else {}
    )
    reasons = sorted(decision.get("reason_codes") or [])
    typed_intent = _projected_approval_intent(request, reasons)
    alternative = "request_narrowest_covering_grant_or_proceed_read_only"
    if "risk_acceptance_unresolved" in reasons:
        alternative = "resolve_risk_acceptance_or_reduce_risk"
    elif "goal_or_design_decision_unresolved" in reasons:
        alternative = "select_bounded_design_or_use_ratified_default"
    elif request.get("intent_type") == "ratify_goal_truth":
        alternative = "request_goal_owner_ratification_or_preserve_current_gt"
    core = {
        "schema_version": 2,
        "artifact_kind": "authority_approval_projection",
        "typed_intent": typed_intent,
        "request_id": request.get("request_id"),
        "operation": {
            key: request.get(key)
            for key in (
                "skill_id",
                "skill_version",
                "operation_id",
                "operation_version",
            )
        },
        "subject": request.get("subject"),
        "capabilities": request.get("required_capabilities"),
        "effect": {
            key: request.get(key)
            for key in (
                "effect_class",
                "data_class",
                "mutation_class",
                "reversibility",
                "risk_tier",
                "decision_class",
            )
        },
        "scope": {
            "cardinality": request.get("cardinality_requested"),
            "use_budget": request.get("use_budget_requested"),
            "session_id": ceiling.get("evidence_id"),
            "cycle_id": request.get("cycle_id"),
            "task_id": request.get("task_id"),
            "improvement_id": request.get("pack_id"),
            "attempt_id": request.get("attempt_id"),
        },
        "excluded_effects": sorted(
            {
                "accept_risk_or_cost",
                "add_capabilities",
                "broaden_subject_or_operation",
                "change_goal_truth",
                "increase_risk_or_irreversibility",
                "reuse_beyond_scope_or_budget",
                "select_design_option",
                "supply_external_input",
            }
            - {
                {
                    "accept_risk_or_cost": "accept_risk_or_cost",
                    "ratify_goal_truth": "change_goal_truth",
                    "select_design_option": "select_design_option",
                    "supply_external_input": "supply_external_input",
                }.get(typed_intent, "")
            }
        ),
        "safe_alternative": alternative,
        "reason_codes": reasons,
        "exact_replay_key": request.get("idempotency_key"),
    }
    return {"projection_id": "authp-" + canonical_sha256(core)[:24], **core}


def axes_match(decision: dict[str, Any], actual: object) -> bool:
    if not isinstance(actual, dict):
        return False
    expected = axis_projection(decision)
    for name in ("authority", "external_input", "risk_cost", "goal_truth"):
        if actual.get(name) != expected[name]:
            return False
    local = actual.get("local_resolution")
    if local == expected["local_resolution"]:
        return True
    return (
        isinstance(local, dict)
        and local.get("status") == "available"
        and isinstance(local.get("evidence_ids"), list)
        and bool(local["evidence_ids"])
        and expected["local_resolution"].get("status") == "unavailable"
    )


__all__ = (
    "approval_projection",
    "axes_match",
    "axis_projection",
    "scope_projection",
)
