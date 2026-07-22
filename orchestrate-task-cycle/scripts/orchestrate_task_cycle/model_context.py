"""Compact, evidence-bound projection for model-facing orchestration packets."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

from .git_worktree_identity import (
    bind_git_worktree_identity,
    legacy_git_changed_paths,
)


MAX_ESSENTIAL_ITEMS = 5_000
MAX_ESSENTIAL_BYTES = 262_144
VOLATILE_OBSERVATION_FIELDS = ("collected_at",)
DIRECTIVE_FIELDS = (
    "directive_id",
    "directive_state",
    "directive_text",
    "change_class",
    "classification",
    "consumption_state",
    "default_state",
    "target_owner",
    "selection_disposition",
    "grouping_only",
    "actionable_child",
    "actionable_child_consumption_state",
)
DECISION_SCALARS = (
    "validation_verdict",
    "progress_verdict",
    "authoritative_final",
    "execution_status",
    "review_status",
    "quality_verdict",
    "selection_outcome",
    "index_status",
    "commit_status",
)


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _file_binding(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict) or not value.get("path"):
        return None
    return {
        key: value.get(key)
        for key in ("path", "exists", "is_file", "size_bytes", "sha256")
        if key in value
    }


def _bounded(items: Iterable[Any], maximum: int) -> dict[str, Any]:
    values = list(items)
    return {
        "total_count": len(values),
        "included_count": min(len(values), maximum),
        "truncated": len(values) > maximum,
        "set_sha256": _sha256(values),
        "items": values[:maximum],
    }


def _event_projection(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    projected = {
        key: value.get(key)
        for key in (
            "step",
            "status",
            "event_id",
            "ledger_sequence",
            "task_id",
            "artifact_refs",
            "unchanged_refs",
            "blockers",
        )
        if key in value
    }
    decisions = {
        key: value.get(key)
        for key in DECISION_SCALARS
        if value.get(key) is None or isinstance(value.get(key), (str, int, float, bool))
    }
    if decisions:
        projected["decision_scalars"] = decisions
    return projected


def _cycle_projection(context: dict[str, Any]) -> dict[str, Any]:
    cycle = (
        context.get("cycle_state")
        if isinstance(context.get("cycle_state"), dict)
        else {}
    )
    current = (
        cycle.get("current_stage")
        if isinstance(cycle.get("current_stage"), dict)
        else {}
    )
    steps = current.get("steps") if isinstance(current.get("steps"), dict) else {}
    projected_steps = {
        str(step): _event_projection(event) for step, event in sorted(steps.items())
    }
    latest = _event_projection(current.get("latest_event"))
    latest_event_id = latest.get("event_id")
    latest_step = latest.get("step")
    latest_ref = None
    if latest_event_id and isinstance(projected_steps.get(str(latest_step)), dict):
        if projected_steps[str(latest_step)].get("event_id") == latest_event_id:
            latest_ref = {"step": latest_step, "event_id": latest_event_id}
    return {
        "latest_cycle_id": cycle.get("latest_cycle_id"),
        "event_count": current.get("event_count"),
        "status": current.get("status"),
        "steps": projected_steps,
        "latest_event_ref": latest_ref,
        "latest_event": None if latest_ref else latest,
    }


def _goal_projection(context: dict[str, Any]) -> dict[str, Any]:
    goal = (
        context.get("agent_goal") if isinstance(context.get("agent_goal"), dict) else {}
    )
    files = (
        goal.get("goal_truth_files")
        if isinstance(goal.get("goal_truth_files"), dict)
        else {}
    )
    return {
        "available_goal_truth": list(goal.get("available_goal_truth") or []),
        "used_goal_truth": list(goal.get("used_goal_truth") or []),
        "bindings": [
            binding
            for binding in (_file_binding(files[name]) for name in sorted(files))
            if binding is not None and binding.get("exists")
        ],
    }


def _directive_projection(record: dict[str, Any]) -> dict[str, Any]:
    return {field: record.get(field) for field in DIRECTIVE_FIELDS if field in record}


def _advice_projection(context: dict[str, Any]) -> dict[str, Any]:
    advice = (
        context.get("external_advice")
        if isinstance(context.get("external_advice"), dict)
        else {}
    )
    packet = (
        advice.get("normalized_packet")
        if isinstance(advice.get("normalized_packet"), dict)
        else None
    )
    if packet is None:
        return {
            "status": advice.get("normalized_packet_status", "unavailable"),
            "active_count": int(advice.get("active_count") or 0),
            "actionable_clause_ids": [],
            "items": [],
        }
    actionable = {str(item) for item in packet.get("actionable_clause_ids") or []}
    items: list[dict[str, Any]] = []
    for item in packet.get("used_advice") or []:
        if not isinstance(item, dict):
            continue
        fields = item.get("fields") if isinstance(item.get("fields"), dict) else {}
        directives = (
            fields.get("directives")
            if isinstance(fields.get("directives"), list)
            else []
        )
        items.append(
            {
                "advice_id": item.get("advice_id"),
                "path": item.get("path"),
                "source_digest": item.get("source_digest"),
                "normalized_content_digest": item.get("content_sha256"),
                "fidelity_status": fields.get("fidelity_status"),
                "raw_direct_reference_required": fields.get(
                    "raw_direct_reference_required"
                ),
                "directives": [
                    _directive_projection(record)
                    for record in directives
                    if isinstance(record, dict)
                    and str(record.get("directive_id") or "") in actionable
                ],
            }
        )
    active_count = int(advice.get("active_count") or len(items))
    incomplete = list(packet.get("incomplete_normalization_advice_ids") or [])
    status = "available"
    if incomplete:
        status = "incomplete"
    elif active_count != len(items):
        status = "registry_filesystem_mismatch"
    return {
        "status": status,
        "active_count": active_count,
        "not_goal_truth": True,
        "execution_plan_eligible": False,
        "normalized_packet_use": packet.get("normalized_packet_use"),
        "incomplete_normalization_advice_ids": incomplete,
        "canonical_clause_ids": list(packet.get("canonical_clause_ids") or []),
        "actionable_clause_ids": list(packet.get("actionable_clause_ids") or []),
        "source_digests": dict(packet.get("source_digests") or {}),
        "clause_source_digests": dict(packet.get("clause_source_digests") or {}),
        "duplicate_actionable_clause_ids": list(
            packet.get("duplicate_actionable_clause_ids") or []
        ),
        "advice_packet_digest": packet.get("advice_packet_digest"),
        "items": items,
    }


def _diagnostic_bindings(value: Any) -> list[dict[str, Any]]:
    bindings: dict[tuple[str, str | None], dict[str, Any]] = {}
    stack = [value]
    while stack:
        current = stack.pop()
        if isinstance(current, dict):
            binding = _file_binding(current)
            if binding is not None:
                key = (str(binding.get("path")), binding.get("sha256"))
                bindings[key] = binding
            stack.extend(current.values())
        elif isinstance(current, list):
            stack.extend(current)
    return [bindings[key] for key in sorted(bindings)]


def _task_projection(context: dict[str, Any]) -> dict[str, Any]:
    state = (
        context.get("task_state") if isinstance(context.get("task_state"), dict) else {}
    )
    pack = state.get("task_pack") if isinstance(state.get("task_pack"), dict) else {}
    miss = state.get("task_miss") if isinstance(state.get("task_miss"), dict) else {}
    return {
        "task_md": _file_binding(context.get("task_md")),
        "index": _file_binding(state.get("index_jsonl")),
        "index_entries": state.get("index_entries"),
        "task_pack": {
            key: pack.get(key)
            for key in (
                "count",
                "selection_status",
                "active_count",
                "selectable_live_count",
                "repair_required_count",
                "active_pack",
                "repair_required_packs",
            )
            if key in pack
        },
        "task_miss": {
            "count": miss.get("count"),
            "active_count": miss.get("active_count"),
            "status_counts": miss.get("status_counts"),
        },
    }


def _scalar_tree(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list):
        return [_scalar_tree(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _scalar_tree(item) for key, item in sorted(value.items())}
    return str(type(value).__name__)


def _authority_projection(context: dict[str, Any]) -> dict[str, Any]:
    cycle = (
        context.get("cycle_state")
        if isinstance(context.get("cycle_state"), dict)
        else {}
    )
    current = (
        cycle.get("current_stage")
        if isinstance(cycle.get("current_stage"), dict)
        else {}
    )
    steps = current.get("steps") if isinstance(current.get("steps"), dict) else {}
    authority = (
        steps.get("authority") if isinstance(steps.get("authority"), dict) else {}
    )
    return {
        key: _scalar_tree(authority.get(key))
        for key in (
            "event_id",
            "status",
            "decision_binding",
            "operation_binding",
            "subject",
            "scope",
            "axes",
            "reservation_binding",
            "dispatch_preflight",
            "effective_authority_fingerprint",
        )
        if key in authority
    }


def project_model_context(
    context: dict[str, Any],
    *,
    max_paths: int = 40,
    worktree_root: Path | None = None,
    collect_git_worktree_identity: bool = True,
    require_exact_git_worktree: bool = False,
) -> dict[str, Any]:
    """Return a bounded view without changing the legacy full context."""

    if max_paths < 1:
        raise ValueError("max_paths must be positive")
    advice = _advice_projection(context)
    diagnostics = _diagnostic_bindings(
        {
            key: context.get(key)
            for key in (
                "task_state",
                "issue",
                "validation_assets",
                "schema",
                "contract",
                "agent_log",
                "session_audit",
            )
        }
    )
    effective_root = worktree_root
    if effective_root is None:
        workspace = context.get("workspace")
        if isinstance(workspace, str) and workspace:
            candidate = Path(workspace)
            if candidate.is_dir():
                effective_root = candidate
    git = context.get("git") if isinstance(context.get("git"), dict) else None
    git_paths = legacy_git_changed_paths(git)
    worktree_identity = None
    if collect_git_worktree_identity:
        git_paths, worktree_identity = bind_git_worktree_identity(
            git,
            effective_root,
            max_paths,
            git_paths,
        )
    cycle_projection = _cycle_projection(context)
    goal_projection = _goal_projection(context)
    task_projection = _task_projection(context)
    authority_projection = _authority_projection(context)
    essential_count = (
        len(advice.get("actionable_clause_ids") or [])
        + sum(
            len(item.get("directives") or [])
            for item in advice.get("items") or []
            if isinstance(item, dict)
        )
        + len((cycle_projection.get("steps") or {}))
    )
    essential_bytes = len(
        _canonical_bytes(
            {
                "task": task_projection,
                "goal_truth": goal_projection,
                "advice": advice,
                "cycle": cycle_projection,
                "authority": authority_projection,
            }
        )
    )
    stop_reason = None
    if advice.get("active_count", 0) and advice.get("status") != "available":
        stop_reason = "awaiting_advice_normalization"
    elif essential_count > MAX_ESSENTIAL_ITEMS or essential_bytes > MAX_ESSENTIAL_BYTES:
        stop_reason = "model_context_budget_exceeded"
    elif require_exact_git_worktree and (
        not isinstance(worktree_identity, dict)
        or worktree_identity.get("binding_status") != "exact"
    ):
        stop_reason = "git_worktree_binding_incomplete"
    projection: dict[str, Any] = {
        "schema_version": 1,
        "artifact_kind": "orchestrate_model_context",
        "projection_status": "block" if stop_reason else "ready",
        "stop_reason": stop_reason,
        "workspace": context.get("workspace"),
        "task": task_projection,
        "goal_truth": goal_projection,
        "advice": advice,
        "cycle": cycle_projection,
        "selection_publication": context.get("selection_publication"),
        "authority": authority_projection,
        "pending_runs": [
            event
            for event in [((cycle_projection.get("steps") or {}).get("run"))]
            if event and event.get("status") in {"running", "pending", "in_progress"}
        ],
        "git": {
            "inside_work_tree": (context.get("git") or {}).get("inside_work_tree")
            if isinstance(context.get("git"), dict)
            else None,
            "head": (context.get("git") or {}).get("head")
            if isinstance(context.get("git"), dict)
            else None,
            "changed_paths": _bounded(git_paths, max_paths),
        },
        "diagnostic_artifacts": _bounded(diagnostics, max_paths),
    }
    if worktree_identity is not None:
        projection["git"]["worktree_identity"] = worktree_identity
    semantic_bytes = _canonical_bytes(projection)
    projection["semantic_context_binding"] = {
        "binding_scope": "model_projection_without_binding_and_metrics",
        "ref": None,
        "sha256": hashlib.sha256(semantic_bytes).hexdigest(),
        "size_bytes": len(semantic_bytes),
        "excluded_observation_fields": list(VOLATILE_OBSERVATION_FIELDS),
    }
    projected_bytes = len(_canonical_bytes(projection))
    projection["compiler_metrics"] = {
        "semantic_binding_bytes": len(semantic_bytes),
        "projected_payload_bytes_without_metrics": projected_bytes,
        "essential_item_count": essential_count,
        "essential_projected_bytes": essential_bytes,
        "diagnostic_path_count": len(diagnostics),
        "git_changed_path_count": len(git_paths),
        "git_worktree_binding_status": (
            worktree_identity.get("binding_status")
            if isinstance(worktree_identity, dict)
            else "not_selected"
        ),
        "git_worktree_identity_count": (
            worktree_identity.get("total_count")
            if isinstance(worktree_identity, dict)
            else 0
        ),
    }
    return projection


__all__ = [
    "MAX_ESSENTIAL_BYTES",
    "MAX_ESSENTIAL_ITEMS",
    "VOLATILE_OBSERVATION_FIELDS",
    "project_model_context",
]
