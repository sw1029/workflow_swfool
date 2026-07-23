"""Validate one exact selected-successor projection for root batching."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .selected_successor_authority_validation import (
    validate_authority_projection,
    validate_authority_projection_snapshot,
)
from .selected_successor_execution_support import ACTIONS


def validate_approval_batch_source(
    root: Path,
    projection_binding: dict[str, str],
    *,
    skills_root: Path | None = None,
) -> dict[str, Any]:
    """Return a closed read-only receipt for the fixed authority bridge."""

    from manage_agent_authority.canonical import object_sha256

    root = root.expanduser().resolve(strict=True)
    validate_authority_projection(root, projection_binding, skills_root=skills_root)
    binding, projection, selected = validate_authority_projection_snapshot(
        root, projection_binding, skills_root=skills_root
    )
    projected = [
        operation
        for operation in projection["operations"]
        if operation["approval_projection"] is not None
    ]
    if (
        len(projected) != len(ACTIONS)
        or len(selected) != len(ACTIONS)
        or any(
            descriptor.get("status") != "absent"
            for descriptor in projection["grants"].values()
        )
        or any(
            operation["approval_projection"].get("typed_intent") != "grant_authority"
            for operation in projected
        )
    ):
        raise ValueError(
            "Initial root batching requires three absent grant-authority decisions"
        )
    rows = []
    for compilation_binding, compilation in selected:
        request = compilation["request"]
        rows.append(
            {
                "compilation": compilation_binding,
                "request_sha256": compilation["request_sha256"],
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
            }
        )
    body = {
        "schema_version": 1,
        "artifact_kind": "selected_successor_approval_batch_source_validation",
        "validation_status": "valid",
        "projection_source": binding,
        "compiled_at": projection["prepared_at"],
        "operation_compilations": rows,
        "operation_count": len(rows),
    }
    return {**body, "receipt_sha256": object_sha256(body)}


__all__ = ("validate_approval_batch_source",)
