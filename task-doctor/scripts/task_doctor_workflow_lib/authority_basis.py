from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from .authority import _authority_call
from .authority_grant import (
    load_bound_materialization,
    verify_materialized_grant,
)
from .common import (
    expect_keys,
    read_json,
    require,
    sha256_json,
    workspace_file,
    workspace_regular_file,
)

from manage_agent_authority.source_approval import (  # noqa: E402
    load_source_approval,
)


def verify_declared_basis(root: Path, plan: dict[str, Any]) -> None:
    basis = plan.get("authorization_basis")
    if basis is None:
        return
    approvals = {item["operation_id"]: item["source_approval"]
                 for item in basis["approvals"]}
    required = [item for item in plan["operations"]
                if item["authority"]["applicability"] == "required"]
    require(set(approvals) == {item["operation_id"] for item in required},
            "invalid_authorization_basis",
            "declared authorization must bind every governed operation exactly once")
    for item in required:
        verify_operation_source_approval(
            root, item, approvals[item["operation_id"]],
        )


def verify_operation_source_approval(
    root: Path, item: dict[str, Any], binding: dict[str, str],
) -> dict[str, str]:
    """Verify one content-addressed source decision against one exact operation."""

    expected_ref = (
        ".task/authorization/source_snapshots/"
        f"source_approval-{binding['sha256']}.json"
    )
    require(binding["ref"] == expected_ref, "invalid_authorization_basis",
            "source decision must bind a content-addressed approval snapshot")
    path = workspace_file(root, binding["ref"], binding["sha256"],
                          f"source_approval.{item['operation_id']}")
    approval = _authority_call(
        "invalid_authorization_basis", "operation source approval",
        lambda: load_source_approval(path),
    )
    if approval["schema_version"] != 6:
        _verify_snapshot_metadata(root, binding)
    _verify_source_approval(root, approval, item, binding)
    return {"ref": binding["ref"], "sha256": binding["sha256"]}


def _verify_snapshot_metadata(root: Path, binding: dict[str, str]) -> None:
    metadata_path = workspace_regular_file(
        root, f"{binding['ref']}.json", "source_snapshot_metadata"
    )
    metadata = read_json(metadata_path, "invalid_authorization_basis")
    expect_keys(metadata, {"schema_version", "artifact_kind", "source_ref",
                           "source_sha256", "snapshot_ref", "snapshot_sha256"},
                set(), "source snapshot metadata", "invalid_authorization_basis")
    require(metadata["schema_version"] == 2
            and metadata["artifact_kind"] == "source_approval_snapshot"
            and metadata["source_sha256"] == binding["sha256"]
            and metadata["snapshot_ref"] == binding["ref"]
            and metadata["snapshot_sha256"] == binding["sha256"],
            "invalid_authorization_basis",
            "declared source snapshot metadata binding is invalid")


def _verify_source_approval(
    root: Path, approval: dict[str, Any], item: dict[str, Any],
    binding: dict[str, str],
) -> None:
    authority = item["authority"]
    loaded = _authority_call(
        "invalid_authorization_basis",
        "producer-owned authority materialization",
        lambda: load_bound_materialization(
            root,
            binding,
            authority["request"],
            authority["materialization"]["policy_snapshot"],
        ),
    )
    require(loaded["source_approval"] == approval,
            "invalid_authorization_basis",
            "source approval changed during producer verification")
    _authority_call(
        "invalid_authorization_basis",
        "materialized grant",
        lambda: verify_materialized_grant(
            root, loaded["grant"], authority
        ),
    )


def materialization_item(item: dict[str, Any]) -> dict[str, Any]:
    authority = item["authority"]
    if authority["applicability"] == "none":
        return {"applicability": "none",
                "operation": copy.deepcopy(authority["operation"]),
                "operation_manifest": copy.deepcopy(authority["operation_manifest"])}
    materialization = authority["materialization"]
    request = authority["request"]
    grant = materialization["grant_spec"]
    source = authority.get("source_approval")
    return {
        "applicability": "required", "request": copy.deepcopy(request),
        "request_sha256": authority["request_sha256"],
        "subject": copy.deepcopy(request["subject"]),
        "operation_manifest": copy.deepcopy(authority["operation_manifest"]),
        "snapshot_sources": {
            "policy_snapshot": copy.deepcopy(materialization["policy_snapshot"]),
            "source_approval": copy.deepcopy(source),
            "source_approval_requirements": {
                "decision_type": "grant_authority",
                "accepted_schema_versions": [2, 3, 4, 5, 6],
                "request_sha256": authority["request_sha256"],
                "grant_id": grant["grant_id"], "lineage_id": grant["lineage_id"],
            },
        },
        "evaluate": {"evaluation_context": copy.deepcopy(materialization["evaluation_context"]),
                     "evaluation_context_sha256": materialization["evaluation_context_sha256"],
                     "evaluated_at": materialization["evaluated_at"]},
        "grant_replay": {
            "grant_id": grant["grant_id"],
            "request_sha256": authority["request_sha256"],
            "source_approval": copy.deepcopy(source),
        },
        "reserve": copy.deepcopy(materialization["reservation"]),
    }


def authority_bundle(
    journal: dict[str, Any], operation_ids: list[str], kind: str,
) -> dict[str, Any]:
    """Build one deterministic projection bundle from immutable plan rows."""

    operations = {
        item["operation_id"]: item for item in journal["plan"]["operations"]
    }
    items = []
    for operation_id in operation_ids:
        item = operations[operation_id]
        items.append({
            "operation_id": operation_id,
            "workflow_role": item["workflow_role"],
            "owner_skill": item["owner_skill"],
            "effect_class": item["effect_class"],
            "effect_summary": item["effect_summary"],
            "required": item["required"],
            "plan_sha256": item["plan_sha256"],
            "plan_binding": item["plan_binding"],
            "authority": materialization_item(item),
        })
    body = {
        "kind": kind,
        "workflow_id": journal["workflow_id"],
        "plan_sha256": journal["plan_sha256"],
        "items": items,
    }
    digest = sha256_json(body)
    return {
        **body,
        "bundle_id": f"tdw-bundle-{digest[:20]}",
        "fingerprint": digest,
    }


__all__ = [
    "authority_bundle",
    "materialization_item",
    "verify_declared_basis",
    "verify_operation_source_approval",
]
