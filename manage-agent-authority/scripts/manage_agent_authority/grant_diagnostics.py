from __future__ import annotations

from typing import Any

from .canonical import parse_time
from .contracts import (
    cardinality_covers,
    rank_value,
    reservation_units,
    risk_value,
)
from .root_grant_request_binding import root_grant_request_binding_covers


def near_miss_reasons(
    request: dict[str, Any],
    records: list[tuple[dict[str, Any], str, dict[str, Any]]],
    at: Any,
    rank_floor: str,
    session_id: str,
) -> list[str]:
    if not records:
        return ["no_authority_grants_registered"]
    reasons: set[str] = set()
    operation = {
        key: request[key]
        for key in ("skill_id", "skill_version", "operation_id", "operation_version")
    }
    for grant, _, state in records:
        checks = {
            "covering_grant_inactive": state.get("status") != "active",
            "covering_grant_holder_mismatch": grant["holder_rank"]
            != request["actor_rank"],
            "covering_root_grant_exact_request_mismatch": (
                not root_grant_request_binding_covers(grant, request)
            ),
            "covering_grant_not_yet_valid": parse_time(
                grant["not_before"], "grant.not_before"
            )
            > at,
            "covering_grant_expired": bool(
                grant.get("expires_at")
                and parse_time(grant["expires_at"], "grant.expires_at") <= at
            ),
            "covering_grant_source_rank_insufficient": rank_value(grant["issuer_rank"])
            < rank_value(rank_floor),
            "covering_grant_capability_mismatch": not set(
                request["required_capabilities"]
            ).issubset(grant["capabilities"]),
            "covering_grant_subject_mismatch": request["subject"]
            not in grant["subjects"],
            "covering_grant_operation_mismatch": operation not in grant["operations"],
            "covering_grant_risk_ceiling_insufficient": risk_value(request["risk_tier"])
            > risk_value(grant["risk_ceiling"]),
            "covering_grant_decision_class_mismatch": request["decision_class"]
            not in grant["decision_classes"],
            "covering_grant_cardinality_mismatch": not cardinality_covers(
                grant["cardinality"], request["cardinality_requested"]
            ),
            "covering_grant_session_scope_mismatch": bool(
                grant["session_id"] and grant["session_id"] != session_id
            ),
            "covering_grant_task_scope_mismatch": bool(
                grant["task_id"] and grant["task_id"] != request["task_id"]
            ),
            "covering_grant_improvement_scope_mismatch": bool(
                grant["improvement_id"]
                and grant["improvement_id"] != request["pack_id"]
            ),
            "covering_grant_budget_scope_insufficient": bool(
                grant.get("max_uses") is not None
                and grant["max_uses"] < request["use_budget_requested"]
            ),
            "covering_grant_dispatch_units_unavailable": bool(
                state.get("remaining_uses") is not None
                and state["remaining_uses"] - int(state.get("reserved_uses", 0))
                < reservation_units(request)
            ),
        }
        reasons.update(code for code, failed in checks.items() if failed)
    return sorted(reasons)
