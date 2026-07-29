"""Bind compact task-doctor reviews to existing authority producer output."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from manage_agent_authority.canonical import parse_time

from .authority_grant import CURRENT_SOURCE_SCHEMAS, materialization_spec
from .common import WorkflowError, require


def _time(value: str, label: str):
    try:
        return parse_time(value, label)
    except SystemExit as error:
        raise WorkflowError("invalid_authorization_basis", str(error)) from error


def projected_materialization(
    root: Path,
    row: dict[str, Any],
    source: dict[str, str],
    at: str,
    expires_at: str,
    policy: dict[str, str],
) -> dict[str, Any]:
    request = row["compiled_operation"]["request"]
    try:
        projected = materialization_spec(root, source, request, policy)
    except (SystemExit, KeyError, TypeError, ValueError) as error:
        raise WorkflowError(
            "invalid_authorization_basis",
            f"producer materialization is invalid: {error}",
        ) from error
    grant = projected["grant"]
    start = max(
        _time(at, "plan materialization time"),
        _time(grant["not_before"], "grant not_before"),
    )
    review_end = _time(expires_at, "review expires_at")
    grant_end = (
        review_end
        if grant["expires_at"] is None
        else _time(grant["expires_at"], "grant expires_at")
    )
    end = min(review_end, grant_end)
    require(start < end, "invalid_authorization_basis",
            "producer grant has no usable reservation window")
    identity = row.get("reservation_identity")
    if identity is None:
        identity = row.get("materialization_identity")
    require(isinstance(identity, dict)
            and isinstance(identity.get("reservation_idempotency_key"), str),
            "invalid_review", "review lacks its reservation identity")
    return {
        "evaluation_context": row["compiled_operation"]["evaluation_context"],
        "evaluated_at": projected["evaluated_at"],
        "policy_snapshot": policy,
        "grant_spec": projected["grant_spec"],
        "reservation": {
            "not_before": start.isoformat(),
            "expires_at": end.isoformat(),
            "idempotency_key": identity["reservation_idempotency_key"],
        },
    }


def verify_new_source(
    approval: dict[str, Any],
    *,
    decided_at: str,
    root_evidence_id: str,
) -> None:
    schema = approval["schema_version"]
    require(schema in CURRENT_SOURCE_SCHEMAS,
            "invalid_authorization_basis",
            "new review authority must come from a current producer")
    require(
        _time(approval["not_before"], "source not_before")
        >= _time(decided_at, "review decided_at"),
        "invalid_authorization_basis",
        "new source approval predates the review decision",
    )
    if schema == 5:
        require(
            approval["decision_trust_class"]
            == "host_user_signed_exact_plan"
            and approval["evidence_id"] == root_evidence_id,
            "invalid_authorization_basis",
            "root source does not bind the accepted exact review",
        )
    else:
        require(
            approval["decision_trust_class"]
            == "host_user_signed_mode_activation_child",
            "invalid_authorization_basis",
            "session source lacks its signed activation trust class",
        )


__all__ = ["projected_materialization", "verify_new_source"]
