"""Validate the actual immutable parent closure behind an authority decision."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .decision_integrity import effective_authority_fingerprint
from .projection_io import load_grant_artifact
from .root_grant_request_binding import root_grant_request_binding_covers


def _records(decision: dict[str, Any], field: str) -> dict[str, dict[str, Any]]:
    values = decision[field]
    return {str(item["grant_id"]): item for item in values}


def _binding_matches(
    record: dict[str, Any],
    grant: dict[str, Any],
    digest: str,
) -> bool:
    return bool(
        record.get("grant_sha256") == digest
        and record.get("policy_snapshot") == grant.get("policy_snapshot")
    )


def validate_decision_grant_closure(
    root: Path,
    decision: dict[str, Any],
    request: dict[str, Any],
) -> None:
    """Require exact selected/ancestor roles from the actual parent graph."""

    selected = _records(decision, "selected_grants")
    lineage = _records(decision, "lineage_grants")
    expected_fingerprint = effective_authority_fingerprint(
        request,
        decision["evaluation_context"],
        decision["operation_manifest"],
        decision["selected_grants"],
        decision["lineage_grants"],
    )
    if decision["effective_authority_fingerprint"] != expected_fingerprint:
        raise SystemExit(
            "Authority decision effective fingerprint does not match its grant set."
        )
    if decision["decision"] != "allowed":
        return

    selected_grants: dict[str, tuple[dict[str, Any], str]] = {}
    for grant_id, record in selected.items():
        grant, digest = load_grant_artifact(root, grant_id)
        if not _binding_matches(record, grant, digest):
            raise SystemExit("Authority decision selected grant binding is invalid.")
        selected_grants[grant_id] = (grant, digest)

    expected_lineage: dict[str, tuple[dict[str, Any], str]] = {}
    for selected_id, (grant, _digest) in selected_grants.items():
        seen = {selected_id}
        parent_id = grant.get("parent_grant_id")
        while parent_id:
            if parent_id in seen:
                raise SystemExit("Authority decision grant lineage is circular.")
            seen.add(parent_id)
            parent, parent_digest = load_grant_artifact(root, parent_id)
            if parent_id not in selected:
                existing = expected_lineage.get(parent_id)
                if existing is not None and existing != (parent, parent_digest):
                    raise SystemExit(
                        "Authority decision grant lineage has conflicting ancestors."
                    )
                expected_lineage[parent_id] = (parent, parent_digest)
            parent_id = parent.get("parent_grant_id")

    if set(lineage) != set(expected_lineage):
        raise SystemExit(
            "Authority decision lineage grants do not match the actual parent closure."
        )
    for grant_id, record in lineage.items():
        grant, digest = expected_lineage[grant_id]
        if not _binding_matches(record, grant, digest):
            raise SystemExit("Authority decision ancestor grant binding is invalid.")

    for grant_id, (grant, _digest) in {
        **selected_grants,
        **expected_lineage,
    }.items():
        if not root_grant_request_binding_covers(grant, request):
            raise SystemExit(
                "Plan-bound root grant does not cover the decision's exact request: "
                f"{grant_id}."
            )


__all__ = ("validate_decision_grant_closure",)
