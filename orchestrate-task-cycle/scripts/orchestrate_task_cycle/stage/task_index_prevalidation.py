"""Normalize compiler-owned task-index prevalidation owner results."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from .contracts import canonical_bytes


def normalize_task_index_prevalidation(
    root: Path,
    value: dict[str, Any],
    *,
    source_ref: str,
) -> dict[str, Any]:
    try:
        from manage_task_state_index.state.prevalidation_compiler import (
            validate_prevalidation_binding,
        )
    except ImportError as exc:
        raise ValueError(
            "registered task-index prevalidation verifier is unavailable; "
            "launch the cycle through the workflow dependency registry"
        ) from exc
    payload = canonical_bytes(value) + b"\n"
    verified = validate_prevalidation_binding(
        root,
        {
            "ref": source_ref,
            "sha256": hashlib.sha256(payload).hexdigest(),
            "size_bytes": len(payload),
        },
    )
    result = verified.get("result")
    if not isinstance(result, dict) or set(result) != {
        "index_status",
        "index_snapshot_id",
        "blockers",
        "evidence_paths",
        "audit_observation_scope",
        "live_revalidation_required",
    }:
        raise ValueError("native task-index prevalidation result is not closed")
    index_status = result.get("index_status")
    if index_status not in {"pass", "blocked", "not_evaluated"}:
        raise ValueError("native task-index prevalidation status is invalid")
    return {
        **result,
        "index_status": (
            "snapshot_current" if index_status == "pass" else index_status
        ),
        "prevalidation_owner_result_binding": verified[
            "owner_result_binding"
        ],
    }


__all__ = ("normalize_task_index_prevalidation",)
