"""Fail closed when a snapshot-scoped index audit is consumed as live state."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .access import step_event
from .context import ValidationContext


AUDIT_OBSERVATION_SCOPE = "immutable_bounded_input_snapshot"
SNAPSHOT_CURRENT = "snapshot_current"
POST_INDEX_TRANSITIONS = frozenset(
    {
        "pre_commit",
        "pre_dashboard",
        "pre_report",
        "pre_closeout_commit",
    }
)
INTERMEDIATE_INDEX_TRANSITIONS = frozenset(
    {
        "pre_issue",
        "pre_schema_pre_derive",
        "pre_derive",
        "pre_schema_post_derive",
        "pre_index",
    }
)


def _validate_snapshot_event(
    state: ValidationContext,
    event: dict[str, object],
    *,
    step: str,
) -> None:
    if event.get("live_revalidation_required") is not True:
        state.add(
            "block",
            f"{step}_live_revalidation_contract_invalid",
            f"`{step}` must preserve the compiler-owned live-revalidation flag.",
        )
    if event.get("audit_observation_scope") != AUDIT_OBSERVATION_SCOPE:
        state.add(
            "block",
            f"{step}_audit_observation_scope_invalid",
            f"`{step}` must preserve its immutable bounded snapshot scope.",
        )
    if event.get("index_status") != SNAPSHOT_CURRENT:
        state.add(
            "block",
            f"{step}_snapshot_not_current",
            f"`{step}` must be revalidated as snapshot_current at this boundary.",
        )


def _workspace(state: ValidationContext) -> Path | None:
    value = state.context.get("workspace")
    if not isinstance(value, str) or not value:
        state.add(
            "block",
            "index_live_revalidation_workspace_missing",
            "Snapshot-scoped index evidence requires the exact workspace path.",
        )
        return None
    raw = Path(value)
    if not raw.is_absolute():
        state.add(
            "block",
            "index_live_revalidation_workspace_invalid",
            "Snapshot-scoped index evidence requires an absolute workspace path.",
        )
        return None
    try:
        resolved = raw.resolve(strict=True)
    except OSError as exc:
        state.add(
            "block",
            "index_live_revalidation_workspace_invalid",
            "Snapshot-scoped index evidence workspace cannot be reopened.",
            {"error": str(exc)},
        )
        return None
    if not resolved.is_dir() or str(resolved) != value:
        state.add(
            "block",
            "index_live_revalidation_workspace_invalid",
            "Snapshot-scoped index evidence workspace is not canonical.",
        )
        return None
    return resolved


def _normalized_status(result: dict[str, Any]) -> Any:
    status = result.get("index_status")
    return "snapshot_current" if status == "pass" else status


def _binding_projection_matches(
    event: dict[str, Any],
    verified: dict[str, Any],
    *,
    step: str,
) -> bool:
    result = verified.get("result")
    snapshot = verified.get("index_snapshot")
    if not isinstance(result, dict) or not isinstance(snapshot, dict):
        return False
    common = {
        "index_status": _normalized_status(result),
        "index_snapshot_id": result.get("index_snapshot_id"),
        "audit_observation_scope": result.get("audit_observation_scope"),
        "live_revalidation_required": result.get(
            "live_revalidation_required"
        ),
    }
    if any(event.get(key) != value for key, value in common.items()):
        return False
    if step == "index_pre_validate":
        return (
            event.get("blockers") == result.get("blockers")
            and event.get("evidence_paths") == result.get("evidence_paths")
        )
    return (
        event.get("audit_blockers") == result.get("blockers")
        and event.get("audit_input_manifest")
        == snapshot.get("audit_input_manifest")
    )


def _validate_bound_snapshot(
    state: ValidationContext,
    event: dict[str, Any],
    *,
    step: str,
    binding_field: str,
) -> None:
    binding = event.get(binding_field)
    if binding is None:
        state.add(
            "block",
            f"{step}_owner_result_binding_missing",
            f"`{step}` requires its exact compiler-owned audit binding.",
        )
        return
    workspace = _workspace(state)
    if workspace is None:
        return
    try:
        from manage_task_state_index.state.prevalidation_compiler import (
            validate_prevalidation_binding,
        )

        verified = validate_prevalidation_binding(workspace, binding)
    except (ImportError, OSError, UnicodeError, ValueError) as exc:
        state.add(
            "block",
            f"{step}_owner_result_binding_invalid",
            f"`{step}` audit binding is missing, stale, or invalid.",
            {"error": str(exc)},
        )
        return
    if not _binding_projection_matches(event, verified, step=step):
        state.add(
            "block",
            f"{step}_owner_result_projection_mismatch",
            f"`{step}` fields differ from its compiler-owned audit binding.",
        )


def _validate_fresh_intermediate_snapshot(
    state: ValidationContext,
) -> None:
    workspace = _workspace(state)
    if workspace is None:
        return
    audited_at = state.context.get("collected_at")
    if not isinstance(audited_at, str) or not audited_at:
        state.add(
            "block",
            "index_live_revalidation_timestamp_missing",
            "Intermediate index revalidation requires the collected_at timestamp.",
        )
        return
    try:
        from manage_task_state_index.state.prevalidation_compiler import (
            audit_projection,
        )

        audited = audit_projection(
            workspace,
            at=audited_at,
            publish=False,
        )
    except (ImportError, OSError, UnicodeError, ValueError) as exc:
        state.add(
            "block",
            "index_live_revalidation_failed",
            "Intermediate boundary audit could not be rederived.",
            {"error": str(exc)},
        )
        return
    result = audited.get("result")
    if not isinstance(result, dict) or result.get("index_status") != "pass":
        state.add(
            "block",
            "index_live_revalidation_not_current",
            "Intermediate boundary requires a fresh non-blocked index audit.",
            {
                "index_status": (
                    result.get("index_status")
                    if isinstance(result, dict)
                    else None
                ),
                "blockers": (
                    result.get("blockers")
                    if isinstance(result, dict)
                    else None
                ),
            },
        )


def validate_index_snapshot_revalidation(state: ValidationContext) -> None:
    """Require compiler-owned point-in-time audits at their consumption boundaries."""

    prevalidation = step_event(state.stage, "index_pre_validate")
    if "live_revalidation_required" not in prevalidation:
        return
    _validate_snapshot_event(
        state,
        prevalidation,
        step="index_pre_validate",
    )
    if state.transition == "pre_validate":
        _validate_bound_snapshot(
            state,
            prevalidation,
            step="index_pre_validate",
            binding_field="prevalidation_owner_result_binding",
        )
        return
    if state.transition in INTERMEDIATE_INDEX_TRANSITIONS:
        _validate_fresh_intermediate_snapshot(state)
        return
    if state.transition not in POST_INDEX_TRANSITIONS:
        return
    final_index = step_event(state.stage, "index")
    if not final_index:
        state.add(
            "block",
            "post_effect_index_revalidation_missing",
            "Commit/report boundaries require a fresh post-effect index audit.",
        )
        return
    _validate_snapshot_event(state, final_index, step="index")
    _validate_bound_snapshot(
        state,
        final_index,
        step="index",
        binding_field="post_audit_owner_result_binding",
    )


__all__ = [
    "INTERMEDIATE_INDEX_TRANSITIONS",
    "POST_INDEX_TRANSITIONS",
    "validate_index_snapshot_revalidation",
]
