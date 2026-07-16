from __future__ import annotations

from .runtime_dependencies import (
    Any,
    now_iso,
    rel_path,
)

from .evaluation_frame import _require_values


def _finalization_fields(state: dict[str, Any]) -> dict[str, Any]:
    (
        evidence_paths, finalized_cycle_id, finalized_state_error, finalized_state_status,
        registry_path, registry_state_source, root,
    ) = _require_values(
        state,
        (
            'evidence_paths', 'finalized_cycle_id', 'finalized_state_error',
            'finalized_state_status', 'registry_path', 'registry_state_source', 'root',
        ),
    )
    return {
        "registry_path": rel_path(root, registry_path),
        "finalized_state_cycle_id": finalized_cycle_id,
        "finalized_state_status": finalized_state_status,
        "finalized_state_error": finalized_state_error,
        "registry_state_source": registry_state_source,
        "finalization_required": True,
        "finalization_state": "candidate",
        "authoritative_consumption_allowed": False,
        "evidence_paths": evidence_paths,
        "not_goal_truth": True,
        "not_gold": True,
        "not_ready": True,
        "updated_at": now_iso(),
    }
