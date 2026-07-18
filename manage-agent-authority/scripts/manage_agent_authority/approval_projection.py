from __future__ import annotations

from typing import Any

from .canonical import object_sha256


def _projected_intent(request: dict[str, Any], reasons: list[str]) -> str:
    if "risk_acceptance_unresolved" in reasons:
        return "accept_risk_or_cost"
    if "goal_or_design_decision_unresolved" in reasons:
        return "select_design_option"
    return str(request["intent_type"])


def build_approval_projection(
    request: dict[str, Any], context: dict[str, Any], reasons: list[str]
) -> dict[str, Any]:
    typed_intent = _projected_intent(request, reasons)
    alternative = "request_narrowest_covering_grant_or_proceed_read_only"
    if "risk_acceptance_unresolved" in reasons:
        alternative = "resolve_risk_acceptance_or_reduce_risk"
    elif "goal_or_design_decision_unresolved" in reasons:
        alternative = "select_bounded_design_or_use_ratified_default"
    elif request["intent_type"] == "ratify_goal_truth":
        alternative = "request_goal_owner_ratification_or_preserve_current_gt"
    core = {
        "schema_version": 2,
        "artifact_kind": "authority_approval_projection",
        "typed_intent": typed_intent,
        "request_id": request["request_id"],
        "operation": {
            key: request[key]
            for key in (
                "skill_id",
                "skill_version",
                "operation_id",
                "operation_version",
            )
        },
        "subject": request["subject"],
        "capabilities": request["required_capabilities"],
        "effect": {
            key: request[key]
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
            "cardinality": request["cardinality_requested"],
            "use_budget": request["use_budget_requested"],
            "session_id": context["session_ceiling"]["evidence_id"],
            "cycle_id": request["cycle_id"],
            "task_id": request["task_id"],
            "improvement_id": request["pack_id"],
            "attempt_id": request["attempt_id"],
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
        "reason_codes": sorted(reasons),
        "exact_replay_key": request["idempotency_key"],
    }
    return {"projection_id": f"authp-{object_sha256(core)[:24]}", **core}
