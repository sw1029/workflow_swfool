"""Sealed-reader validation and migration boundary projections."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .classification import (
    _bind_quarantine_corrections,
    _broken_links,
    _classify_rows,
    _merge_state,
    _validate_quarantine_correction_bindings,
)
from .contracts import (
    NON_ACTIVE_STATUSES,
    MigrationError,
)
from .mapping import (
    _validate_mapping,
)
from .storage import (
    _read_json,
    _safe_ref,
    _sha256,
)

def _normalized_events_from_plan(root: Path, plan: dict[str, Any], mapping_bytes: bytes | None = None) -> list[dict[str, Any]]:
    snapshot = _safe_ref(root, plan["source_snapshot_ref"])
    prefix = snapshot.read_bytes()
    if _sha256(prefix) != plan["source_prefix"]["sha256"]:
        raise MigrationError("Source snapshot digest mismatch")
    if mapping_bytes is None:
        mapping_path = _safe_ref(root, plan["mapping_manifest"]["snapshot_ref"])
        mapping_bytes = mapping_path.read_bytes()
    if _sha256(mapping_bytes) != plan["mapping_manifest"]["sha256"]:
        raise MigrationError("Mapping snapshot digest mismatch")
    try:
        mapping = json.loads(mapping_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MigrationError("Invalid mapping snapshot") from exc
    if not isinstance(mapping, dict):
        raise MigrationError("Invalid mapping snapshot object")
    _validate_mapping(mapping)
    rows, events, counts = _classify_rows(prefix, mapping)
    _bind_quarantine_corrections(
        rows, plan["correction_events"],
        plan["anchors"]["current_task"]["id"], plan["anchors"]["current_pack"]["id"],
    )
    _validate_quarantine_correction_bindings(rows, plan["correction_events"])
    expected_rows = plan["rows"]
    if rows != expected_rows or counts != plan["classification_counts"]:
        raise MigrationError("Prefix reclassification differs from sealed plan")
    return events

def _migration_boundary_projection(root: Path, receipt: dict[str, Any]) -> dict[str, Any]:
    """Reconstruct and verify the immutable projection at the migration seal."""
    plan = _read_json(_safe_ref(root, receipt["plan_ref"]), "sealed migration plan")
    task = receipt.get("canonical_task")
    pack = receipt.get("canonical_pack")
    if not isinstance(task, dict) or not isinstance(pack, dict):
        raise MigrationError("Migration receipt lacks canonical boundary identities")
    if task != plan.get("anchors", {}).get("current_task") or pack != plan.get("anchors", {}).get("current_pack"):
        raise MigrationError("Migration receipt boundary identities differ from the sealed plan")

    projection = plan.get("projection")
    if not isinstance(projection, dict):
        raise MigrationError("Sealed migration plan lacks boundary projection")
    receipt_projection_keys = (
        "active_task_count", "active_pack_count", "duplicate_active_alias_count",
        "current_broken_link_count", "current_active_pack_indexed",
        "current_projection_status", "projection_completeness",
        "current_surface_blocker_count",
    )
    if any(receipt.get(key) != projection.get(key) for key in receipt_projection_keys):
        raise MigrationError("Migration receipt boundary projection differs from the sealed plan")

    boundary_events = _normalized_events_from_plan(root, plan) + plan["correction_events"]
    boundary_state = _merge_state(boundary_events)
    task_id = task.get("id")
    pack_id = pack.get("id")
    task_path = task.get("path")
    active_tasks = sorted(
        item_id for item_id, item in boundary_state.items()
        if item.get("type") == "task" and item.get("status") == "active"
    )
    active_packs = sorted(
        item_id for item_id, item in boundary_state.items()
        if item.get("type") == "task_pack" and item.get("status") == "active"
    )
    duplicates = sorted(
        item_id for item_id, item in boundary_state.items()
        if item_id != task_id and item.get("type") == "task" and item.get("path") == task_path
        and item.get("status") not in NON_ACTIVE_STATUSES
    )
    broken = _broken_links(boundary_state, str(task_id)) if isinstance(task_id, str) else []
    boundary_task = boundary_state.get(str(task_id), {})
    boundary_pack = boundary_state.get(str(pack_id), {})
    task_identity_bound = (
        boundary_task.get("type") == "task"
        and boundary_task.get("status") == "active"
        and boundary_task.get("path") == task.get("path")
        and boundary_task.get("content_sha256") == task.get("sha256")
    )
    pack_identity_bound = (
        boundary_pack.get("type") == "task_pack"
        and boundary_pack.get("status") == "active"
        and boundary_pack.get("path") == pack.get("path")
        and boundary_pack.get("content_sha256") == pack.get("sha256")
    )
    complete = (
        isinstance(task_id, str) and isinstance(pack_id, str)
        and active_tasks == [task_id] and active_packs == [pack_id]
        and not duplicates and not broken
        and task_identity_bound and pack_identity_bound
    )
    if not complete:
        raise MigrationError("Migration boundary projection is incomplete")
    return {
        "migration_boundary_task_id": task_id,
        "migration_boundary_pack_id": pack_id,
        "migration_boundary_active_task_count": len(active_tasks),
        "migration_boundary_active_pack_count": len(active_packs),
        "migration_boundary_duplicate_active_alias_count": len(duplicates),
        "migration_boundary_broken_link_count": len(broken),
        "migration_boundary_projection_status": "evaluated",
        "migration_boundary_projection_completeness": "complete",
    }


def _current_projection(state: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Evaluate the live append-only projection independently of receipt anchors."""
    active_tasks = sorted(
        item_id for item_id, item in state.items()
        if item.get("type") == "task" and item.get("status") == "active"
    )
    active_packs = sorted(
        item_id for item_id, item in state.items()
        if item.get("type") == "task_pack" and item.get("status") == "active"
    )
    current_task_id = active_tasks[0] if len(active_tasks) == 1 else None
    current_pack_id = active_packs[0] if len(active_packs) == 1 else None
    current_task_path = state.get(current_task_id, {}).get("path") if current_task_id else None
    duplicates = sorted(
        item_id for item_id, item in state.items()
        if current_task_id is not None and item_id != current_task_id
        and item.get("type") == "task" and item.get("path") == current_task_path
        and item.get("status") not in NON_ACTIVE_STATUSES
    )
    broken = _broken_links(state, current_task_id) if current_task_id is not None else []
    task_indexed = (
        current_task_id is not None
        and state.get(current_task_id, {}).get("type") == "task"
        and state.get(current_task_id, {}).get("status") == "active"
    )
    pack_indexed = (
        current_pack_id is not None
        and state.get(current_pack_id, {}).get("type") == "task_pack"
        and state.get(current_pack_id, {}).get("status") == "active"
    )
    evaluated = task_indexed and pack_indexed
    complete = evaluated and not duplicates and not broken
    return {
        "active_task_ids": active_tasks,
        "active_pack_ids": active_packs,
        "current_active_task_id": current_task_id,
        "current_active_pack_id": current_pack_id,
        "active_task_count": len(active_tasks),
        "active_pack_count": len(active_packs),
        "duplicate_active_alias_count": len(duplicates),
        "current_broken_link_count": len(broken),
        "current_active_task_indexed": task_indexed,
        "current_active_pack_indexed": pack_indexed,
        "current_projection_status": "evaluated" if evaluated else "not_evaluated",
        "projection_completeness": "complete" if complete else "incomplete",
    }
