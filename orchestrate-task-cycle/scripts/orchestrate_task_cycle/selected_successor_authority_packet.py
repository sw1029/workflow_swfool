"""Build selected-successor authority packet bodies from owner results."""

from __future__ import annotations

from typing import Any


def continuation_fields(
    compilations: list[dict[str, Any]],
    source_projection: dict[str, str] | None,
    root_grant_materialization: dict[str, str] | None,
) -> dict[str, Any]:
    """Validate continuation inputs before authority lifecycle writes."""

    if (source_projection is None) != (root_grant_materialization is None):
        raise ValueError(
            "Authority continuation packet requires projection and materialization"
        )
    compiled_times = {item["compiled_at"] for item in compilations}
    if len(compiled_times) != 1:
        raise ValueError("Selected-successor packet compilations disagree on time")
    if source_projection is None:
        return {}
    return {
        "compiled_at": next(iter(compiled_times)),
        "source_projection": source_projection,
        "root_grant_materialization": root_grant_materialization,
    }


def build_packet_body(
    *,
    at: str,
    bundle: dict[str, str],
    request_context: dict[str, str],
    evaluation_context: dict[str, str],
    grants: dict[str, dict[str, Any]],
    operation_manifests: dict[str, dict[str, str]],
    rows: list[dict[str, Any]],
    compilations: list[dict[str, Any]],
    compilation_bindings: list[dict[str, str]],
    decisions: list[dict[str, str]],
    proofs: dict[str, dict[str, Any]],
    continuation: dict[str, Any],
) -> dict[str, Any]:
    """Return the canonical packet body after lifecycle publication succeeds."""

    return {
        "schema_version": 2 if continuation else 1,
        "artifact_kind": "selected_successor_authority_packet",
        "status": "all_three_owner_proofs_current",
        "prepared_at": at,
        "bundle": bundle,
        "request_context": request_context,
        "evaluation_context": evaluation_context,
        "grants": grants,
        "operation_manifests": operation_manifests,
        "operations": [
            {
                "action": row["action"],
                "compilation": {"ref": binding["ref"], "sha256": binding["sha256"]},
                "request_sha256": compilation["request_sha256"],
                "decision": decision,
                "selected_grant": grants[row["action"]],
            }
            for row, binding, compilation, decision in zip(
                rows, compilation_bindings, compilations, decisions
            )
        ],
        "authority_proofs": proofs,
        "authority_effects": {
            "renderer_created_source_approvals": False,
            "renderer_created_grants": False,
            "decisions_issued_by": "manage-agent-authority:evaluate_and_publish",
            "selected_successor_effects_applied": False,
        },
        **continuation,
    }


__all__ = ("build_packet_body", "continuation_fields")
