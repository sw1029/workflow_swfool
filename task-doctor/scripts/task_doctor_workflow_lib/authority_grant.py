from __future__ import annotations

from pathlib import Path
from typing import Any

from manage_agent_authority.artifact_store import verify_binding
from manage_agent_authority.canonical import object_sha256, parse_time
from manage_agent_authority.projection_io import load_grant_artifact
from manage_agent_authority.root_grant_transaction import (
    payload_binding,
    validate_root_grant_receipt_chain,
)
from manage_agent_authority.source_approval import (
    load_source_approval,
    validate_for_grant,
    validate_source_decision_binding,
)

from .common import WorkflowError, require


OPERATION_KEYS = ("skill_id", "skill_version", "operation_id", "operation_version")
CURRENT_SOURCE_SCHEMAS = {5, 6}


def _iso_time(value: str | None) -> str | None:
    if value is None:
        return None
    try:
        return parse_time(value, "task-doctor grant time").isoformat()
    except SystemExit as error:
        raise WorkflowError("invalid_authority_contract", str(error)) from error


def _source(
    root: Path, binding: dict[str, str],
) -> dict[str, Any]:
    path = verify_binding(root, binding, "task-doctor source approval")
    return load_source_approval(path)


def _projection(
    approval: dict[str, Any], request_sha256: str,
) -> dict[str, Any] | None:
    schema = approval["schema_version"]
    if schema in {4, 5}:
        matches = [
            row for row in approval["grant_projections"]
            if row["request_sha256"] == request_sha256
        ]
        if len(matches) != 1:
            raise SystemExit(
                "Plan-bound source must contain one exact request projection."
            )
        return matches[0]
    if schema == 6:
        child = approval["activation_child"]
        if child["request_sha256"] != request_sha256:
            raise SystemExit(
                "Session child source binds a different exact request."
            )
        return child
    return None


def _request_matches_grant(
    request: dict[str, Any], grant: dict[str, Any],
) -> bool:
    operation = {key: request[key] for key in OPERATION_KEYS}
    return (
        grant["holder_rank"] == request["actor_rank"]
        and grant["capabilities"] == request["required_capabilities"]
        and grant["subjects"] == [request["subject"]]
        and grant["operations"] == [operation]
        and grant["risk_ceiling"] == request["risk_tier"]
        and grant["decision_classes"] == [request["decision_class"]]
        and grant["cardinality"] == request["cardinality_requested"]
        and grant["max_uses"] == request["use_budget_requested"]
        and grant["task_id"] == request["task_id"]
        and grant["improvement_id"] == request["pack_id"]
    )


def _legacy_grant(
    root: Path,
    approval: dict[str, Any],
    binding: dict[str, str],
    request: dict[str, Any],
    policy: dict[str, str],
) -> tuple[dict[str, Any], str]:
    candidates: list[tuple[dict[str, Any], str]] = []
    for grant_id in approval["grant_ids"]:
        try:
            grant, digest = load_grant_artifact(root, grant_id)
            validate_for_grant(root, approval, grant, prospective=False)
        except (SystemExit, KeyError, TypeError, ValueError):
            continue
        if (
            grant["source_approval"] == binding
            and grant["policy_snapshot"] == policy
            and _request_matches_grant(request, grant)
        ):
            candidates.append((grant, digest))
    if len(candidates) != 1:
        raise SystemExit(
            "Historical source must resolve to one existing exact grant."
        )
    return candidates[0]


def _verify_root_receipt(
    root: Path,
    approval_binding: dict[str, str],
    grant: dict[str, Any],
    grant_digest: str,
) -> None:
    assets = validate_root_grant_receipt_chain(
        root, grant["root_materialization_ref"]
    )
    if (
        assets["source_binding"] != approval_binding
        or payload_binding(
            root, assets["receipt_path"], assets["receipt_payload"]
        )["ref"] != grant["root_materialization_ref"]
    ):
        raise SystemExit(
            "Root grant materialization does not bind the selected source."
        )
    exact = [
        row for row in assets["grant_assets"]
        if row["grant"]["grant_id"] == grant["grant_id"]
    ]
    if (
        len(exact) != 1
        or exact[0]["grant"] != grant
        or exact[0]["grant_sha256"] != grant_digest
    ):
        raise SystemExit(
            "Root grant differs from its producer materialization receipt."
        )


def load_bound_materialization(
    root: Path,
    binding: dict[str, str],
    request: dict[str, Any],
    policy: dict[str, str],
) -> dict[str, Any]:
    """Load one existing grant selected by a closed source approval."""

    approval = _source(root, binding)
    request_sha256 = object_sha256(request)
    projection = _projection(approval, request_sha256)
    if projection is None:
        grant, grant_digest = _legacy_grant(
            root, approval, binding, request, policy
        )
    else:
        grant, grant_digest = load_grant_artifact(
            root, projection["grant_id"]
        )
        if (
            projection["lineage_id"] != grant["lineage_id"]
            or projection["grant_idempotency_key"] != grant["idempotency_key"]
        ):
            raise SystemExit(
                "Producer projection and materialized grant identity differ."
            )
    if (
        grant["source_approval"] != binding
        or grant["policy_snapshot"] != policy
        or not _request_matches_grant(request, grant)
    ):
        raise SystemExit(
            "Materialized grant differs from the exact task-doctor request."
        )
    if grant["schema_version"] in {3, 4} and (
        grant["request_sha256"] != request_sha256
    ):
        raise SystemExit(
            "Materialized grant binds a different request digest."
        )
    validate_for_grant(root, approval, grant, prospective=False)
    if approval["schema_version"] in {3, 4, 5}:
        validate_source_decision_binding(root, approval)
    if approval["schema_version"] == 5:
        if grant["schema_version"] != 3:
            raise SystemExit(
                "Signed root source requires a schema-v3 grant."
            )
        _verify_root_receipt(root, binding, grant, grant_digest)
    if approval["schema_version"] == 6 and grant["schema_version"] != 4:
        raise SystemExit(
            "Session child source requires a schema-v4 grant."
        )
    return {
        "source_approval": approval,
        "source_binding": dict(binding),
        "projection": projection,
        "grant": grant,
        "grant_sha256": grant_digest,
    }


def materialization_spec(
    root: Path,
    binding: dict[str, str],
    request: dict[str, Any],
    policy: dict[str, str],
) -> dict[str, Any]:
    loaded = load_bound_materialization(
        root, binding, request, policy
    )
    grant = loaded["grant"]
    return {
        **loaded,
        "evaluated_at": grant["created_at"],
        "grant_spec": {
            "grant_id": grant["grant_id"],
            "lineage_id": grant["lineage_id"],
            "holder_rank": grant["holder_rank"],
            "cardinality": grant["cardinality"],
            "max_uses": grant["max_uses"],
            "not_before": grant["not_before"],
            "expires_at": grant["expires_at"],
            "idempotency_key": grant["idempotency_key"],
        },
    }


def verify_materialized_grant(
    root: Path, grant: dict[str, Any], authority: dict[str, Any],
) -> None:
    request = authority["request"]
    spec = authority["materialization"]["grant_spec"]
    source_binding = authority.get("source_approval", grant.get("source_approval"))
    require(isinstance(source_binding, dict), "authority_binding_mismatch",
            "materialized grant lacks its source approval binding")
    loaded = load_bound_materialization(
        root,
        source_binding,
        request,
        authority["materialization"]["policy_snapshot"],
    )
    expected_grant = loaded["grant"]
    require(grant == expected_grant, "authority_binding_mismatch",
            "selected grant differs from its producer-owned artifact")
    expected = {
        "grant_id": spec["grant_id"],
        "lineage_id": spec["lineage_id"],
        "holder_rank": spec["holder_rank"],
        "cardinality": spec["cardinality"],
        "max_uses": spec["max_uses"],
        "not_before": _iso_time(spec["not_before"]),
        "expires_at": _iso_time(spec["expires_at"]),
        "created_at": _iso_time(authority["materialization"]["evaluated_at"]),
        "idempotency_key": spec["idempotency_key"],
    }
    mismatched = sorted(
        key for key, value in expected.items() if grant.get(key) != value
    )
    require(not mismatched, "authority_binding_mismatch",
            f"materialized grant differs from plan projection: {mismatched}")


__all__ = [
    "CURRENT_SOURCE_SCHEMAS",
    "load_bound_materialization",
    "materialization_spec",
    "verify_materialized_grant",
]
