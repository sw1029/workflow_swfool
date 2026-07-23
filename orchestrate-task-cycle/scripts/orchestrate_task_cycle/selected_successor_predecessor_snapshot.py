"""Pinned predecessor-snapshot bindings for selected-successor execution."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from .selection_decision_store import normalize_binding
from .selection_publication_gc_fs import read_relative


MAX_PREDECESSOR_SNAPSHOT_BYTES = 32 * 1024 * 1024


def reopen_predecessor_snapshot_binding(
    root: Path,
    value: Any,
    label: str,
) -> dict[str, str]:
    """Read one exact binding through a root-pinned, all-component no-follow path."""

    binding = normalize_binding(value, label)
    payload = read_relative(
        root.expanduser().resolve(strict=True),
        binding["ref"],
        label,
        max_bytes=MAX_PREDECESSOR_SNAPSHOT_BYTES,
    )
    if payload is None or hashlib.sha256(payload).hexdigest() != binding["sha256"]:
        raise ValueError(f"{label} SHA-256 differs from its exact binding")
    return binding


def _load_exact_plan(root: Path, value: Any) -> dict[str, Any]:
    from manage_task_state_index.state.transition_plan_contract import (
        load_transition_plan,
    )

    binding = normalize_binding(
        value,
        "selected-successor plan-owned predecessor plan",
    )
    path, plan, digest = load_transition_plan(root, binding["ref"])
    observed = {"ref": path.relative_to(root).as_posix(), "sha256": digest}
    if observed != binding:
        raise ValueError("Selected-successor predecessor plan binding differs")
    return plan


def _plan_snapshot_binding(
    plan: dict[str, Any],
    *,
    task_id: Any,
    successor_binding: Any,
) -> dict[str, str]:
    task_source = normalize_binding(
        successor_binding, "selected-successor plan task source"
    )
    events = plan.get("events")
    anchors = plan.get("artifact_anchors")
    if not isinstance(task_id, str) or not isinstance(events, list):
        raise ValueError("Selected-successor predecessor plan topology is invalid")
    predecessors = [
        event
        for event in events
        if isinstance(event, dict)
        and event.get("type") == "task"
        and event.get("path") == "task.md"
        and event.get("status") == "superseded"
        and event.get("links") == [{"id": task_id, "rel": "superseded_by"}]
    ]
    if len(events) != 2 or len(predecessors) != 1:
        raise ValueError("Selected-successor predecessor plan topology is invalid")
    predecessor = predecessors[0]
    predecessor_id = predecessor.get("id")
    successors = [
        event
        for event in events
        if isinstance(event, dict)
        and event.get("id") == task_id
        and event.get("type") == "task"
        and event.get("path") == "task.md"
        and event.get("status") == "active"
        and event.get("content_sha256") == task_source["sha256"]
        and event.get("links") == [{"id": predecessor_id, "rel": "supersedes"}]
    ]
    task_anchors = [
        anchor
        for anchor in anchors or []
        if isinstance(anchor, dict) and anchor.get("path") == "task.md"
    ]
    fields = (
        predecessor.get("fields") if isinstance(predecessor.get("fields"), dict) else {}
    )
    digest = predecessor.get("content_sha256")
    binding = {
        "ref": fields.get("snapshot_path"),
        "sha256": fields.get("snapshot_digest"),
    }
    if (
        len(successors) != 1
        or len(task_anchors) != 1
        or fields.get("record_class") != "immutable_snapshot"
        or fields.get("canonical_id") != predecessor_id
        or fields.get("alias_path") != "task.md"
        or binding["sha256"] != digest
        or task_anchors[0].get("before_sha256") != digest
        or task_anchors[0].get("expected_sha256") != task_source["sha256"]
    ):
        raise ValueError("Selected-successor predecessor plan binding is invalid")
    return normalize_binding(
        binding, "selected-successor plan-owned predecessor snapshot"
    )


def validate_plan_owned_predecessor_snapshot(
    root: Path, bundle: dict[str, Any]
) -> dict[str, str]:
    """Derive and reopen a predecessor without consulting the mutable task alias."""

    try:
        binding = _plan_snapshot_binding(
            _load_exact_plan(root, bundle.get("task_state_plan")),
            task_id=bundle.get("selected_task_id"),
            successor_binding=bundle.get("task_source"),
        )
        return reopen_predecessor_snapshot_binding(
            root,
            binding,
            "selected-successor plan-owned predecessor snapshot",
        )
    except ValueError as exc:
        raise ValueError(
            "Selected-successor plan-owned predecessor snapshot binding is invalid"
        ) from exc


def validate_prepare_owned_predecessor_snapshot(
    root: Path, prepare: dict[str, Any]
) -> dict[str, str]:
    """Reopen the plan predecessor from the locked publication prepare."""

    targets = prepare.get("targets")
    target = targets[0] if isinstance(targets, list) and len(targets) == 1 else {}
    if (
        not isinstance(target, dict)
        or target.get("role") != "task_alias"
        or target.get("target_ref") != "task.md"
    ):
        raise ValueError("Selected-successor publication predecessor target is invalid")
    successor = {
        "ref": target.get("payload_ref"),
        "sha256": target.get("after_sha256"),
    }
    try:
        binding = _plan_snapshot_binding(
            _load_exact_plan(root, prepare.get("task_state_plan")),
            task_id=prepare.get("selection_id"),
            successor_binding=successor,
        )
        return reopen_predecessor_snapshot_binding(
            root,
            binding,
            "selected-successor publication predecessor snapshot",
        )
    except ValueError as exc:
        raise ValueError(
            "Selected-successor publication predecessor snapshot binding is invalid"
        ) from exc


__all__ = (
    "MAX_PREDECESSOR_SNAPSHOT_BYTES",
    "reopen_predecessor_snapshot_binding",
    "validate_plan_owned_predecessor_snapshot",
    "validate_prepare_owned_predecessor_snapshot",
)
