from __future__ import annotations

from typing import Any

from manage_agent_authority.canonical import parse_time

from .common import WorkflowError, require


OPERATION_KEYS = ("skill_id", "skill_version", "operation_id", "operation_version")


def _iso_time(value: str) -> str:
    try:
        return parse_time(value, "task-doctor grant time").isoformat()
    except SystemExit as error:
        raise WorkflowError("invalid_authority_contract", str(error)) from error


def verify_materialized_grant(
    grant: dict[str, Any], authority: dict[str, Any],
) -> None:
    request = authority["request"]
    spec = authority["materialization"]["grant_spec"]
    operation = {key: request[key] for key in OPERATION_KEYS}
    expected = {
        "grant_id": spec["grant_id"], "lineage_id": spec["lineage_id"],
        "parent_grant_id": None, "issuer_rank": "S3",
        "holder_rank": spec["holder_rank"],
        "capabilities": request["required_capabilities"],
        "subjects": [request["subject"]], "operations": [operation],
        "risk_ceiling": request["risk_tier"],
        "decision_classes": [request["decision_class"]],
        "cardinality": spec["cardinality"], "max_uses": spec["max_uses"],
        "not_before": _iso_time(spec["not_before"]),
        "expires_at": _iso_time(spec["expires_at"]) if spec["expires_at"] else None,
        "session_id": None, "task_id": request["task_id"],
        "improvement_id": request["pack_id"],
        "policy_snapshot": authority["materialization"]["policy_snapshot"],
        "created_at": _iso_time(authority["materialization"]["evaluated_at"]),
        "idempotency_key": spec["idempotency_key"],
    }
    if authority.get("source_approval") is not None:
        expected["source_approval"] = authority["source_approval"]
    mismatched = sorted(key for key, value in expected.items()
                        if grant.get(key) != value)
    require(not mismatched, "authority_binding_mismatch",
            f"reserved grant differs from materialization recipe: {mismatched}")
