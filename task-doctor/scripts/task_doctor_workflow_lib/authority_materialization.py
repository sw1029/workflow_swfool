"""Validation and normalization for exact task-doctor authority recipes."""

from __future__ import annotations

import copy
from typing import Any, Callable, TypeVar

from manage_agent_authority.canonical import object_sha256, parse_time
from manage_agent_authority.projection_contracts import identifier

from .common import WorkflowError, expect_keys, require


T = TypeVar("T")


def _public(label: str, action: Callable[[], T]) -> T:
    try:
        return action()
    except (SystemExit, KeyError, TypeError, ValueError) as error:
        message = str(error) or error.__class__.__name__
        raise WorkflowError(
            "invalid_authority_contract", f"{label} is invalid: {message}"
        ) from error


def normalize_materialization(raw: Any, request: dict[str, Any]) -> dict[str, Any]:
    require(isinstance(raw, dict), "invalid_plan",
            "authority.materialization must be an object")
    expect_keys(raw, {"evaluation_context", "evaluated_at", "grant_spec",
                      "policy_snapshot", "reservation"}, set(),
                "authority.materialization")
    context = raw["evaluation_context"]
    require(isinstance(context, dict), "invalid_plan",
            "evaluation_context must be an object")
    grant = raw["grant_spec"]
    require(isinstance(grant, dict), "invalid_plan", "grant_spec must be an object")
    expect_keys(grant, {"grant_id", "lineage_id", "holder_rank", "cardinality",
                        "max_uses", "not_before", "expires_at", "idempotency_key"},
                set(), "grant_spec")
    reservation = raw["reservation"]
    require(isinstance(reservation, dict), "invalid_plan",
            "reservation must be an object")
    expect_keys(reservation, {"reserved_at", "idempotency_key"}, set(), "reservation")
    policy = raw["policy_snapshot"]
    require(isinstance(policy, dict), "invalid_plan",
            "policy_snapshot must be an exact binding")
    expect_keys(policy, {"ref", "sha256"}, set(), "policy_snapshot")
    require(grant["holder_rank"] == request["actor_rank"], "invalid_authority_contract",
            "grant holder rank must equal request actor rank")
    require(grant["cardinality"] == request["cardinality_requested"],
            "invalid_authority_contract", "grant cardinality must equal request cardinality")
    require(grant["max_uses"] == request["use_budget_requested"],
            "invalid_authority_contract", "grant budget must equal request budget")
    maximum = grant["max_uses"]
    require(grant["cardinality"] == "single_use"
            and isinstance(maximum, int) and not isinstance(maximum, bool)
            and maximum == 1,
            "invalid_authority_contract",
            "task-doctor grant recipes must remain exact single-use grants")
    for label, value in (("grant_id", grant["grant_id"]),
                         ("lineage_id", grant["lineage_id"]),
                         ("grant.idempotency_key", grant["idempotency_key"]),
                         ("reservation.idempotency_key", reservation["idempotency_key"])):
        _public(label, lambda value=value, label=label: identifier(value, label))
    evaluated_at = _public(
        "evaluated_at", lambda: parse_time(raw["evaluated_at"], "evaluated_at")
    )
    not_before = _public(
        "grant.not_before", lambda: parse_time(grant["not_before"], "grant.not_before")
    )
    reserved_at = _public(
        "reservation.reserved_at",
        lambda: parse_time(reservation["reserved_at"], "reservation.reserved_at"),
    )
    expires_at = (
        None
        if grant["expires_at"] is None
        else _public(
            "grant.expires_at",
            lambda: parse_time(grant["expires_at"], "grant.expires_at"),
        )
    )
    require(not_before <= evaluated_at <= reserved_at, "invalid_authority_contract",
            "authority times must satisfy not_before <= evaluated_at <= reserved_at")
    require(expires_at is None or reserved_at < expires_at,
            "invalid_authority_contract",
            "reservation must occur before the grant expires")
    normalized_grant = copy.deepcopy(grant)
    normalized_grant["not_before"] = not_before.isoformat()
    normalized_grant["expires_at"] = expires_at.isoformat() if expires_at else None
    normalized_reservation = copy.deepcopy(reservation)
    normalized_reservation["reserved_at"] = reserved_at.isoformat()
    return {
        "evaluation_context": copy.deepcopy(context),
        "evaluation_context_sha256": object_sha256(context),
        "evaluated_at": evaluated_at.isoformat(),
        "grant_spec": normalized_grant,
        "policy_snapshot": copy.deepcopy(policy),
        "reservation": normalized_reservation,
    }


__all__ = ["normalize_materialization"]
