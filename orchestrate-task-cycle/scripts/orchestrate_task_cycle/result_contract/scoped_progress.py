"""Derive retrospective task, stable-root, and global progress facts."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Callable

from .accessors import boolish, deep_get, first_present
from .retained_change import RetainedChangeAssessment, classify_retained_change
from .scoped_progress_evidence import (
    goal_axis_receipt_valid,
    independent_observation_receipt_valid,
    self_grounded_evidence_valid,
)


PROGRESS_CLASSES = frozenset(
    {"semantic", "root_reduction", "task_local", "safety", "governance", "none"}
)
ROOT_VERIFICATION_STATUSES = frozenset(
    {"independently_verified", "explicit_self_grounded"}
)
GLOBAL_VERIFICATION_STATUSES = frozenset({"independently_verified"})
Emit = Callable[[str, str, dict[str, Any] | None], None]


@dataclass(frozen=True, slots=True)
class ScopedProgressAssessment:
    present: bool
    effective_progress_class: str
    task_progress_qualified: bool
    root_reset_allowed: bool
    global_reset_allowed: bool
    global_axes_complete: bool
    retained_change: RetainedChangeAssessment


def _mapping(result: dict[str, Any], *paths: str) -> dict[str, Any]:
    for path in paths:
        value = deep_get(result, path)
        if isinstance(value, dict):
            return value
    return {}


def _declared(result: dict[str, Any], *paths: str) -> bool:
    for path in paths:
        parts = path.split(".")
        current: Any = result
        for part in parts[:-1]:
            if not isinstance(current, dict) or part not in current:
                break
            current = current[part]
        else:
            if isinstance(current, dict) and parts[-1] in current:
                return True
    return False


def _text(value: Any) -> str:
    return str(value or "").strip().lower()


def _axis_status(result: dict[str, Any], axis: str) -> str:
    value = first_present(
        result,
        (axis, f"verdict_axes.{axis}", f"authoritative_projection.{axis}"),
    )
    if isinstance(value, dict):
        return _text(value.get("status") or value.get("verdict"))
    return _text(value)


def canonical_goal_axis_map_sha256(
    active_measurable_goals: list[str], goal_axis_map: dict[str, list[str]]
) -> str:
    material = {
        "active_measurable_goals": sorted(active_measurable_goals),
        "goal_axis_map": {
            goal: sorted(goal_axis_map[goal]) for goal in sorted(goal_axis_map)
        },
    }
    raw = json.dumps(
        material,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _bounded_ids(value: Any) -> list[str] | None:
    if not isinstance(value, list) or not value:
        return None
    normalized: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip() or len(item.strip()) > 512:
            return None
        normalized.append(item.strip())
    if len(set(normalized)) != len(normalized):
        return None
    return normalized


def _active_axis_inventory(result: dict[str, Any]) -> set[str] | None:
    gate = _mapping(
        result,
        "goal_axis_completeness_gate",
        "scoped_progress.goal_axis_completeness_gate",
    )
    active_goals = _bounded_ids(gate.get("active_measurable_goals"))
    axis_map = gate.get("goal_axis_map")
    if active_goals is None or not isinstance(axis_map, dict):
        return None
    if set(axis_map) != set(active_goals):
        return None
    normalized_map: dict[str, list[str]] = {}
    for goal in active_goals:
        axes = _bounded_ids(axis_map.get(goal))
        if axes is None:
            return None
        normalized_map[goal] = axes
    expected_digest = canonical_goal_axis_map_sha256(active_goals, normalized_map)
    owner_id = str(gate.get("goal_axis_map_owner_id") or "").strip()
    revision_id = str(gate.get("goal_axis_map_revision_id") or "").strip()
    adapter_revision = str(gate.get("adapter_revision_sha256") or "").strip()
    if (
        _text(gate.get("evaluation_status")) != "pass"
        or not owner_id
        or not revision_id
        or gate.get("goal_axis_map_sha256") != expected_digest
        or gate.get("unobserved_goal_axes") not in ([], ())
        or not goal_axis_receipt_valid(
            gate.get("goal_axis_map_receipt"),
            owner_id=owner_id,
            map_revision_id=revision_id,
            map_sha256=expected_digest,
            adapter_revision_sha256=adapter_revision,
        )
    ):
        return None
    flattened = {axis for axes in normalized_map.values() for axis in axes}
    return flattened or None


def _global_axes_complete(global_scope: dict[str, Any], result: dict[str, Any]) -> bool:
    expected_axes = _active_axis_inventory(result)
    if expected_axes is None:
        return False
    rows = global_scope.get("axis_observations")
    if not isinstance(rows, list):
        rows = first_present(
            result,
            ("goal_axis_observations", "goal_axis_completeness_gate.axis_observations"),
        )
    unobserved = first_present(
        result,
        ("unobserved_goal_axes", "goal_axis_completeness_gate.unobserved_goal_axes"),
    )
    conflicted = boolish(
        first_present(
            result,
            ("goal_axis_conflicted", "goal_axis_completeness_gate.conflicted"),
        )
    )
    if unobserved or conflicted:
        return False
    if isinstance(rows, list):
        active = [row for row in rows if isinstance(row, dict)]
        row_ids = [str(row.get("axis_id") or "").strip() for row in active]
        if (
            not active
            or len(set(row_ids)) != len(row_ids)
            or set(row_ids) != expected_axes
        ):
            return False
        return all(
            _text(row.get("status") or row.get("movement_status"))
            in {"pass", "passed", "ready", "improved"}
            and _text(row.get("provenance") or row.get("verification_status"))
            in GLOBAL_VERIFICATION_STATUSES
            and _text(
                row.get("binding_status") or row.get("observation_binding_status")
            )
            in {"exact_bound", "exact_current", "verified"}
            and isinstance(row.get("premise_satisfying_item_count"), int)
            and not isinstance(row.get("premise_satisfying_item_count"), bool)
            and row["premise_satisfying_item_count"] > 0
            and independent_observation_receipt_valid(
                row.get("independent_observation_receipt"),
                subject_id=str(row.get("axis_id") or ""),
                observed_relation="improved",
            )
            for row in active
        )
    return False


def _root_verification_qualified(root_scope: dict[str, Any]) -> bool:
    status = _text(root_scope.get("independent_verification_status"))
    if status in ROOT_VERIFICATION_STATUSES - {"explicit_self_grounded"}:
        relation = _text(root_scope.get("residual_relation_status"))
        return bool(
            _text(root_scope.get("observation_binding_status"))
            in {"exact_bound", "exact_current", "verified"}
            and relation in {"reduced", "resolved"}
            and independent_observation_receipt_valid(
                root_scope.get("independent_observation_receipt"),
                subject_id=str(root_scope.get("observation_subject_id") or ""),
                observed_relation=relation,
            )
        )
    return bool(
        status == "explicit_self_grounded"
        and _text(root_scope.get("self_grounded_contract_status"))
        in {"pass", "verified"}
        and _text(root_scope.get("premise_replay_status"))
        in {"pass", "replayed", "verified"}
        and _text(root_scope.get("observation_binding_status"))
        in {"exact_bound", "exact_current", "verified"}
        and self_grounded_evidence_valid(root_scope)
    )


def assess_scoped_progress(result: dict[str, Any]) -> ScopedProgressAssessment:
    contract = _mapping(
        result, "progress_scope_contract", "scoped_progress.progress_scope_contract"
    )
    observations = _mapping(
        result, "progress_observations", "scoped_progress.progress_observations"
    )
    closeout = _mapping(
        result, "closeout_projection", "scoped_progress.closeout_projection"
    )
    optional_paths = (
        ("progress_scope_contract", "scoped_progress.progress_scope_contract"),
        ("work_intent", "scoped_progress.work_intent"),
        ("progress_observations", "scoped_progress.progress_observations"),
        ("closeout_projection", "scoped_progress.closeout_projection"),
        (
            "retained_change_classification",
            "scoped_progress.retained_change_classification",
        ),
        ("retained_change_evidence", "scoped_progress.retained_change_evidence"),
    )
    retained = classify_retained_change(result)
    task_scope = (
        observations.get("task_scope")
        if isinstance(observations.get("task_scope"), dict)
        else {}
    )
    root_scope = (
        observations.get("root_scope")
        if isinstance(observations.get("root_scope"), dict)
        else {}
    )
    global_scope = (
        observations.get("global_scope")
        if isinstance(observations.get("global_scope"), dict)
        else {}
    )
    task_acceptance = _text(closeout.get("task_acceptance")) or _axis_status(
        result, "task_acceptance_verdict"
    )
    task_progress = _text(task_scope.get("progress_class"))
    task_qualified = task_acceptance == "pass" and task_progress in PROGRESS_CLASSES - {
        "none"
    }
    root_allowed = (
        _text(root_scope.get("progress_class")) == "root_reduction"
        and _text(root_scope.get("comparison_status")) == "comparable"
        and _text(root_scope.get("movement_status")) == "improved"
        and _text(root_scope.get("residual_relation_status")) in {"reduced", "resolved"}
        and _root_verification_qualified(root_scope)
        and (
            not retained.evaluated
            or retained.progress_cap in {"semantic", "root_reduction"}
        )
    )
    axes_complete = _global_axes_complete(global_scope, result)
    global_readiness = _text(closeout.get("global_readiness")) or (
        "ready"
        if _axis_status(result, "goal_readiness_verdict") == "pass"
        else "blocked"
    )
    global_allowed = (
        _text(contract.get("global_scope_applicability")) == "applicable"
        and _text(global_scope.get("progress_class")) == "semantic"
        and _text(global_scope.get("movement_status")) == "improved"
        and boolish(global_scope.get("high_water_moved"))
        and _text(global_scope.get("independent_verification_status"))
        in GLOBAL_VERIFICATION_STATUSES
        and _text(global_scope.get("observation_binding_status"))
        in {"exact_bound", "exact_current", "verified"}
        and axes_complete
        and global_readiness == "ready"
        and (not retained.evaluated or retained.progress_cap == "semantic")
    )
    if global_allowed:
        effective = "semantic"
    elif root_allowed:
        effective = "root_reduction"
    elif (
        task_qualified
        and retained.evaluated
        and retained.progress_cap in {"safety", "governance"}
    ):
        effective = retained.progress_cap
    elif task_qualified:
        effective = "task_local"
    else:
        effective = "none"
    return ScopedProgressAssessment(
        present=any(_declared(result, *paths) for paths in optional_paths),
        effective_progress_class=effective,
        task_progress_qualified=task_qualified,
        root_reset_allowed=root_allowed,
        global_reset_allowed=global_allowed,
        global_axes_complete=axes_complete,
        retained_change=retained,
    )


def validate_scoped_progress(
    result: dict[str, Any],
    target: str,
    emit: Emit,
) -> ScopedProgressAssessment:
    """Compatibility facade for the focused validator module."""

    from .scoped_progress_validation import validate_scoped_progress as validate

    return validate(result, target, emit)


__all__ = (
    "ScopedProgressAssessment",
    "assess_scoped_progress",
    "canonical_goal_axis_map_sha256",
    "validate_scoped_progress",
)
