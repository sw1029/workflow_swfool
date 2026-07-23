"""Validate source-approval lineage, grant issuance, and transitions."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .canonical import parse_time, resolve_workspace_path, sha256_file
from .contracts import rank_value, risk_value
from .source_approval_contract import (
    load_source_approval,
)
from .source_decision_validation import validate_source_decision_binding


def _scope_set(items: list[dict[str, Any]]) -> set[tuple[str, ...]]:
    return {tuple(str(item[key]) for key in sorted(item)) for item in items}


def _validate_delegated_subset(
    approval: dict[str, Any], parent: dict[str, Any]
) -> None:
    if rank_value(parent["source_rank"]) <= rank_value(approval["source_rank"]):
        raise SystemExit(
            "Delegated source approval must bind a strictly higher-rank source approval."
        )
    subset_fields = (
        "capabilities",
        "decision_classes",
        "cardinalities",
        "grant_ids",
        "request_digests",
        "lineage_ids",
    )
    for field in subset_fields:
        if not set(approval[field]).issubset(parent[field]):
            raise SystemExit(
                f"Delegated source approval {field} exceeds its higher-rank source."
            )
    for field in ("subjects", "operations"):
        if not _scope_set(approval[field]).issubset(_scope_set(parent[field])):
            raise SystemExit(
                f"Delegated source approval {field} exceeds its higher-rank source."
            )
    if risk_value(approval["risk_ceiling"]) > risk_value(parent["risk_ceiling"]):
        raise SystemExit(
            "Delegated source approval risk ceiling exceeds its higher-rank source."
        )
    if parent["max_uses"] is not None and (
        approval["max_uses"] is None
        or approval["max_uses"] > parent["max_uses"]
    ):
        raise SystemExit(
            "Delegated source approval use budget exceeds its higher-rank source."
        )
    if parse_time(approval["not_before"], "delegated source not_before") < parse_time(
        parent["not_before"], "higher-rank source not_before"
    ):
        raise SystemExit(
            "Delegated source approval begins before its higher-rank source."
        )
    parent_expiry = parent["expires_at"]
    approval_expiry = approval["expires_at"]
    if parent_expiry and (
        not approval_expiry
        or parse_time(approval_expiry, "delegated source expires_at")
        > parse_time(parent_expiry, "higher-rank source expires_at")
    ):
        raise SystemExit("Delegated source approval outlives its higher-rank source.")


def validate_delegation_lineage(
    root: Path, approval: dict[str, Any], *, effective_at: str
) -> None:
    """Prove every S1/S2 approval narrows an immutable higher-rank source."""

    now = parse_time(effective_at, "delegated source effective_at")
    current = approval
    seen_approvals: set[str] = set()
    seen_bindings: set[tuple[str, str]] = set()
    while True:
        approval_id = current["approval_id"]
        if approval_id in seen_approvals:
            raise SystemExit("Delegated source approval lineage is circular.")
        seen_approvals.add(approval_id)
        if now < parse_time(current["not_before"], "source approval not_before"):
            raise SystemExit("Delegated source approval lineage is not yet effective.")
        if current["expires_at"] and now >= parse_time(
            current["expires_at"], "source approval expires_at"
        ):
            raise SystemExit("Delegated source approval lineage has expired.")
        if current["source_rank"] in {"S3", "S4"}:
            return
        binding = current["delegation_binding"]
        if binding is None:
            raise SystemExit(
                "S1/S2 source approval lacks its higher-rank delegation binding."
            )
        binding_identity = (binding["ref"], binding["sha256"])
        if binding_identity in seen_bindings:
            raise SystemExit("Delegated source approval lineage is circular.")
        seen_bindings.add(binding_identity)
        parent_path = resolve_workspace_path(
            root, binding["ref"], "delegation_binding"
        )
        if sha256_file(parent_path) != binding["sha256"]:
            raise SystemExit("Delegation binding digest mismatch.")
        parent = load_source_approval(parent_path)
        _validate_delegated_subset(current, parent)
        current = parent


def validate_for_grant(
    root: Path,
    approval: dict[str, Any],
    grant: dict[str, Any],
    *,
    prospective: bool = True,
) -> None:
    if prospective:
        if approval["schema_version"] in {2, 4}:
            raise SystemExit(
                "Historical schema-v2/v4 source approvals cannot authorize a new grant."
            )
        else:
            decision_kind = validate_source_decision_binding(root, approval)
            if decision_kind == "authority_root_approval_decision":
                raise SystemExit(
                    "Historical full-echo root decisions cannot authorize a new grant."
                )
    if "authority.grant.issue" not in approval["capabilities"]:
        raise SystemExit("Source approval lacks authority.grant.issue.")
    if approval["source_rank"] != grant["issuer_rank"]:
        raise SystemExit("Grant issuer_rank must equal its source approval rank.")
    if grant["grant_id"] not in approval["grant_ids"]:
        raise SystemExit("Source approval does not bind this exact grant ID.")
    if grant["lineage_id"] not in approval["lineage_ids"]:
        raise SystemExit("Source approval does not bind this exact grant lineage.")
    if not set(grant["capabilities"]).issubset(approval["capabilities"]):
        raise SystemExit("Grant capabilities exceed its source approval.")
    if not {tuple(item.values()) for item in grant["subjects"]}.issubset(
        {tuple(item.values()) for item in approval["subjects"]}
    ):
        raise SystemExit("Grant subjects exceed its source approval.")
    if not {tuple(item.values()) for item in grant["operations"]}.issubset(
        {tuple(item.values()) for item in approval["operations"]}
    ):
        raise SystemExit("Grant operations exceed its source approval.")
    if risk_value(grant["risk_ceiling"]) > risk_value(approval["risk_ceiling"]):
        raise SystemExit("Grant risk ceiling exceeds its source approval.")
    if not set(grant["decision_classes"]).issubset(approval["decision_classes"]):
        raise SystemExit("Grant decision classes exceed its source approval.")
    if grant["cardinality"] not in approval["cardinalities"]:
        raise SystemExit("Grant cardinality exceeds its source approval.")
    if approval["max_uses"] is not None and (
        grant["max_uses"] is None or grant["max_uses"] > approval["max_uses"]
    ):
        raise SystemExit("Grant use budget exceeds its source approval.")
    if parse_time(grant["not_before"], "grant.not_before") < parse_time(
        approval["not_before"], "source approval not_before"
    ):
        raise SystemExit("Grant begins before its source approval.")
    created = parse_time(grant["created_at"], "grant.created_at")
    if created < parse_time(approval["not_before"], "source approval not_before"):
        raise SystemExit("Grant creation predates its source approval.")
    if approval["expires_at"] and created >= parse_time(
        approval["expires_at"], "source approval expires_at"
    ):
        raise SystemExit("Grant was created after its source approval expired.")
    if approval["expires_at"] and (
        not grant["expires_at"]
        or parse_time(grant["expires_at"], "grant.expires_at")
        > parse_time(approval["expires_at"], "source approval expires_at")
    ):
        raise SystemExit("Grant outlives its source approval.")
    if approval["schema_version"] in {4, 5}:
        if grant["schema_version"] != 3:
            raise SystemExit(
                "Plan-bound root approval requires a request-bound schema-v3 grant."
            )
        matching = [
            item
            for item in approval["grant_projections"]
            if item["grant_id"] == grant["grant_id"]
        ]
        if len(matching) != 1:
            raise SystemExit(
                "Plan-bound source approval lacks this grant's exact projection."
            )
        projection = matching[0]
        projected_fields = {
            "grant_id": "grant_id",
            "lineage_id": "lineage_id",
            "grant_idempotency_key": "idempotency_key",
            "request_sha256": "request_sha256",
            "holder_rank": "holder_rank",
            "capabilities": "capabilities",
            "subjects": "subjects",
            "operations": "operations",
            "risk_ceiling": "risk_ceiling",
            "decision_classes": "decision_classes",
            "cardinality": "cardinality",
            "max_uses": "max_uses",
            "session_id": "session_id",
            "task_id": "task_id",
            "improvement_id": "improvement_id",
            "policy_snapshot": "policy_snapshot",
            "root_materialization_ref": "root_materialization_ref",
        }
        differing = sorted(
            projection_field
            for projection_field, grant_field in projected_fields.items()
            if projection[projection_field] != grant[grant_field]
        )
        if (
            grant["parent_grant_id"] is not None
            or grant["issuer_rank"] != approval["source_rank"]
            or grant["not_before"] != approval["not_before"]
            or grant["created_at"] != approval["not_before"]
            or grant["expires_at"] != approval["expires_at"]
        ):
            differing.append("root_lifecycle_scope")
        if differing:
            raise SystemExit(
                "Plan-bound root grant differs from its exact per-request "
                f"projection: {', '.join(sorted(set(differing)))}."
            )
    validate_delegation_lineage(root, approval, effective_at=grant["created_at"])


def _validate_transition_delegation(
    root: Path,
    approval: dict[str, Any],
    grant: dict[str, Any],
    now: Any,
    source_rank: int,
) -> None:
    if source_rank >= rank_value(grant["issuer_rank"]):
        return
    binding = approval["delegation_binding"]
    if binding is None:
        raise SystemExit(
            "Lower-than-issuer transition requires delegation lineage evidence."
        )
    parent_path = resolve_workspace_path(
        root, binding["ref"], "transition delegation_binding"
    )
    if sha256_file(parent_path) != binding["sha256"]:
        raise SystemExit("Transition delegation binding digest mismatch.")
    parent = load_source_approval(parent_path)
    if rank_value(parent["source_rank"]) <= source_rank:
        raise SystemExit("Transition delegation source rank is not higher.")
    if (
        "authority.grant.transition" not in parent["capabilities"]
        or grant["grant_id"] not in parent["grant_ids"]
        or grant["lineage_id"] not in parent["lineage_ids"]
    ):
        raise SystemExit("Transition delegation lineage does not cover the target.")
    if now < parse_time(parent["not_before"], "delegation source not_before"):
        raise SystemExit("Transition delegation source is not yet effective.")
    if parent["expires_at"] and now >= parse_time(
        parent["expires_at"], "delegation source expires_at"
    ):
        raise SystemExit("Transition delegation source has expired.")


def validate_for_transition(
    root: Path,
    approval: dict[str, Any],
    grant: dict[str, Any],
    at: str,
    *,
    source_binding: dict[str, str] | None = None,
    prospective: bool = True,
) -> None:
    if prospective:
        if approval["schema_version"] == 2:
            raise SystemExit(
                "Historical schema-v2 source approvals cannot authorize transitions."
            )
        else:
            validate_source_decision_binding(root, approval)
    now = parse_time(at, "transition time")
    validate_delegation_lineage(root, approval, effective_at=at)
    if "authority.grant.transition" not in approval["capabilities"]:
        raise SystemExit("Source approval lacks authority.grant.transition.")
    if grant["grant_id"] not in approval["grant_ids"]:
        raise SystemExit("Transition approval does not bind the exact grant ID.")
    if grant["lineage_id"] not in approval["lineage_ids"]:
        raise SystemExit("Transition approval does not bind the exact grant lineage.")
    source_rank = rank_value(approval["source_rank"])
    if source_rank <= rank_value(grant["holder_rank"]):
        raise SystemExit("Transition source rank must be above the target holder rank.")
    _validate_transition_delegation(root, approval, grant, now, source_rank)
    if now < parse_time(approval["not_before"], "source approval not_before"):
        raise SystemExit("Transition approval is not yet effective.")
    if approval["expires_at"] and now >= parse_time(
        approval["expires_at"], "source approval expires_at"
    ):
        raise SystemExit("Transition approval has expired.")


__all__ = (
    "validate_delegation_lineage",
    "validate_for_grant",
    "validate_for_transition",
)
