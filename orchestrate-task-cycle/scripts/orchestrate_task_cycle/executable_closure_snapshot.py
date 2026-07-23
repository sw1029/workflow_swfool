"""Stable mutable-input snapshots for executable-closure classification."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import stat
from typing import Any

from .selection_decision_store import normalize_binding
from .selected_successor_predecessor_snapshot import (
    reopen_predecessor_snapshot_binding,
)


COMPLETED_TASK_STATUSES = {"complete", "completed"}
TOPOLOGY_PREDECESSOR_STATUSES = {"active", *COMPLETED_TASK_STATUSES}
MAX_CURRENT_TASK_BYTES = 1024 * 1024


def _file_signature(value: os.stat_result) -> tuple[int, int, int, int, int, int]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


def _task_snapshot_hook(stage: str, root: Path) -> None:
    """Test seam for deterministic task-alias replacement races."""

    _ = stage, root


def _current_task_source(root: Path) -> dict[str, str] | None:
    """Hash bounded `task.md` bytes through one root-pinned, no-follow read."""

    directory_flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    file_flags = (
        os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    )
    try:
        root_descriptor = os.open(root, directory_flags)
    except OSError as exc:
        raise ValueError(
            "Executable-closure root must be one stable directory"
        ) from exc
    descriptor = -1
    try:
        root_before = os.fstat(root_descriptor)
        if not stat.S_ISDIR(root_before.st_mode):
            raise ValueError("Executable-closure root must be one stable directory")
        try:
            descriptor = os.open("task.md", file_flags, dir_fd=root_descriptor)
        except FileNotFoundError:
            return None
        except OSError:
            return None
        _task_snapshot_hook("after_task_open", root)
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            return None
        if before.st_size > MAX_CURRENT_TASK_BYTES:
            raise ValueError("Current task exceeds the executable-closure safety limit")
        digest = hashlib.sha256()
        total = 0
        while True:
            chunk = os.read(
                descriptor,
                min(1024 * 1024, MAX_CURRENT_TASK_BYTES + 1 - total),
            )
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_CURRENT_TASK_BYTES:
                raise ValueError(
                    "Current task exceeds the executable-closure safety limit"
                )
            digest.update(chunk)
        after = os.fstat(descriptor)
        try:
            visible = os.stat("task.md", dir_fd=root_descriptor, follow_symlinks=False)
            root_visible = root.stat(follow_symlinks=False)
        except OSError as exc:
            raise ValueError(
                "Current task changed during executable-closure read"
            ) from exc
        if (
            _file_signature(before) != _file_signature(after)
            or _file_signature(after) != _file_signature(visible)
            or (root_before.st_dev, root_before.st_ino)
            != (root_visible.st_dev, root_visible.st_ino)
        ):
            raise ValueError("Current task changed during executable-closure read")
        return {"ref": "task.md", "sha256": digest.hexdigest()}
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        os.close(root_descriptor)


def current_task_alias(
    root: Path,
) -> tuple[
    dict[str, Any] | None,
    dict[str, str] | None,
    dict[str, str] | None,
]:
    """Return one digest-matched current alias and task/index source bindings."""

    from manage_task_state_index.state.events import (
        load_events_read_only,
        merge_state,
    )

    task_source = _current_task_source(root)
    if task_source is None:
        return None, None, None
    task_digest = task_source["sha256"]
    events, index_digest = load_events_read_only(root)
    index_source = (
        {"ref": ".task/index.jsonl", "sha256": index_digest}
        if index_digest is not None
        else None
    )
    state = merge_state(events)
    active_ids = {
        item_id
        for item_id, item in state.items()
        if item.get("type") == "task" and item.get("status") == "active"
    }
    aliases: list[dict[str, Any]] = []
    for item_id, item in state.items():
        if (
            item.get("type") != "task"
            or item.get("path") != "task.md"
            or item.get("content_sha256") != task_digest
        ):
            continue
        status = str(item.get("status") or "")
        if status == "active":
            aliases.append(item)
            continue
        fields = item.get("fields") if isinstance(item.get("fields"), dict) else {}
        if (
            status in COMPLETED_TASK_STATUSES
            and fields.get("record_class") == "mutable_alias"
            and fields.get("canonical_id") == item_id
        ):
            aliases.append(item)
    if len(aliases) != 1:
        return None, task_source, index_source
    alias = aliases[0]
    alias_id = str(alias.get("id") or "")
    expected_active = {alias_id} if alias.get("status") == "active" else set()
    if active_ids != expected_active:
        return None, task_source, index_source
    return alias, task_source, index_source


def _predecessor_snapshot_binding(
    root: Path,
    alias: dict[str, Any],
    predecessor: dict[str, Any],
) -> dict[str, str] | None:
    alias_fields = alias.get("fields") if isinstance(alias.get("fields"), dict) else {}
    predecessor_fields = (
        predecessor.get("fields") if isinstance(predecessor.get("fields"), dict) else {}
    )
    digest = alias.get("content_sha256")
    binding = {
        "ref": alias_fields.get("snapshot_path"),
        "sha256": alias_fields.get("snapshot_digest"),
    }
    if (
        not isinstance(digest, str)
        or binding["sha256"] != digest
        or predecessor.get("content_sha256") != digest
        or predecessor_fields.get("snapshot_path") != binding["ref"]
        or predecessor_fields.get("snapshot_digest") != digest
    ):
        return None
    try:
        normalized = normalize_binding(
            binding, "selected-successor predecessor snapshot"
        )
        reopen_predecessor_snapshot_binding(
            root,
            normalized,
            "selected-successor predecessor snapshot",
        )
    except ValueError:
        return None
    return normalized


def topology_predecessor_binding(
    root: Path,
    bundle: dict[str, Any],
    *,
    alias: dict[str, Any] | None,
    task_source: dict[str, str] | None,
    index_source: dict[str, str] | None,
    task_id: str,
) -> dict[str, str] | None:
    """Reopen and bind a topology's exact still-current predecessor snapshot."""

    if alias is None or task_source is None or index_source is None:
        return None
    from manage_task_state_index.state.transition_plan_contract import (
        load_transition_plan,
    )
    from .selection_decision_store import read_bound_json
    from .selection_publication_v2 import normalize_prepare

    plan_binding = normalize_binding(
        bundle.get("task_state_plan"), "selected-successor task-state plan"
    )
    plan_path, plan, plan_sha256 = load_transition_plan(root, plan_binding["ref"])
    if plan_binding != {
        "ref": plan_path.relative_to(root).as_posix(),
        "sha256": plan_sha256,
    }:
        return None
    prepare_binding = normalize_binding(
        bundle.get("selection_prepare"), "selected-successor publication prepare"
    )
    prepare_path, raw_prepare = read_bound_json(
        root, prepare_binding, "selected-successor publication prepare"
    )
    if prepare_binding["ref"] != prepare_path.relative_to(root).as_posix():
        return None
    prepare = normalize_prepare(root, raw_prepare)

    ledger = plan.get("ledger")
    anchors = plan.get("artifact_anchors")
    events = plan.get("events")
    targets = prepare.get("targets")
    if (
        not isinstance(ledger, dict)
        or ledger.get("before_sha256") != index_source["sha256"]
        or not isinstance(anchors, list)
        or not isinstance(events, list)
        or not isinstance(targets, list)
    ):
        return None
    task_anchors = [
        item
        for item in anchors
        if isinstance(item, dict) and item.get("path") == "task.md"
    ]
    task_targets = [
        item
        for item in targets
        if isinstance(item, dict)
        and item.get("role") == "task_alias"
        and item.get("target_ref") == "task.md"
    ]
    predecessor_id = str(alias.get("id") or "")
    predecessors = [
        event
        for event in events
        if isinstance(event, dict)
        and event.get("id") == predecessor_id
        and event.get("type") == "task"
        and event.get("path") == "task.md"
        and event.get("status") == "superseded"
        and event.get("content_sha256") == task_source["sha256"]
        and event.get("links") == [{"id": task_id, "rel": "superseded_by"}]
    ]
    successor_digest = bundle.get("task_source", {}).get("sha256")
    successors = [
        event
        for event in events
        if isinstance(event, dict)
        and event.get("id") == task_id
        and event.get("type") == "task"
        and event.get("path") == "task.md"
        and event.get("status") == "active"
        and event.get("content_sha256") == successor_digest
        and event.get("links") == [{"id": predecessor_id, "rel": "supersedes"}]
    ]
    topology_matches = bool(
        prepare.get("selection_id") == task_id
        and len(task_anchors) == 1
        and task_anchors[0].get("before_sha256") == task_source["sha256"]
        and task_anchors[0].get("expected_sha256") == successor_digest
        and len(task_targets) == 1
        and task_targets[0].get("before_sha256") == task_source["sha256"]
        and task_targets[0].get("after_sha256") == successor_digest
        and len(predecessors) == 1
        and len(successors) == 1
    )
    if not topology_matches:
        return None
    return _predecessor_snapshot_binding(root, alias, predecessors[0])


def topology_predecessor_matches(
    root: Path,
    bundle: dict[str, Any],
    *,
    alias: dict[str, Any] | None,
    task_source: dict[str, str] | None,
    index_source: dict[str, str] | None,
    task_id: str,
) -> bool:
    """Require one exact topology and a bounded, no-follow snapshot reopen."""

    return (
        topology_predecessor_binding(
            root,
            bundle,
            alias=alias,
            task_source=task_source,
            index_source=index_source,
            task_id=task_id,
        )
        is not None
    )


def validate_selected_successor_predecessor_snapshot(
    root: Path,
    bundle: dict[str, Any],
) -> dict[str, str]:
    """Reopen the pristine bundle predecessor through its current alias and plan."""

    alias, task_source, index_source = current_task_alias(root)
    binding = topology_predecessor_binding(
        root,
        bundle,
        alias=alias,
        task_source=task_source,
        index_source=index_source,
        task_id=str(bundle.get("selected_task_id") or ""),
    )
    if binding is None:
        raise ValueError(
            "Selected-successor predecessor snapshot binding is no longer current"
        )
    return binding


def _current_epoch_predecessor(root: Path, value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) != {
        "task_id",
        "task_state_plan",
        "selection_prepare",
        "snapshot",
    }:
        raise ValueError("Executable closure predecessor epoch is invalid")
    snapshot = normalize_binding(
        value["snapshot"], "executable-closure predecessor snapshot"
    )
    reopen_predecessor_snapshot_binding(
        root,
        snapshot,
        "executable-closure predecessor snapshot",
    )
    return {**value, "snapshot": snapshot}


def assert_executable_closure_epoch_current(
    root: Path, closure: dict[str, Any]
) -> None:
    """Fail closed when mutable task/index inputs leave a ready closure epoch."""

    expected = closure.get("closure_epoch")
    if closure.get("status") != "ready" or not isinstance(expected, dict):
        raise ValueError("Executable closure does not carry one ready epoch")
    try:
        alias, task_source, index_source = current_task_alias(root)
        predecessor = _current_epoch_predecessor(
            root, expected.get("selected_successor_predecessor")
        )
    except ValueError as exc:
        raise ValueError(
            "Executable closure epoch changed before authority reservation"
        ) from exc
    observed = {
        "task_source": task_source,
        "task_index": index_source,
        "current_alias_id": (str(alias.get("id") or "") if alias is not None else None),
        "selected_successor_predecessor": predecessor,
    }
    if observed != expected:
        raise ValueError(
            "Executable closure epoch changed before authority reservation"
        )


def build_closure_epoch(
    *,
    alias_id: str | None,
    task_source: dict[str, str] | None,
    index_source: dict[str, str] | None,
    bundle: dict[str, Any] | None,
    topology_exact: bool,
    predecessor_snapshot: dict[str, str] | None,
) -> dict[str, Any] | None:
    if task_source is None or index_source is None:
        return None
    return {
        "task_source": task_source,
        "task_index": index_source,
        "current_alias_id": alias_id,
        "selected_successor_predecessor": (
            {
                "task_id": alias_id,
                "task_state_plan": bundle["task_state_plan"],
                "selection_prepare": bundle["selection_prepare"],
                "snapshot": predecessor_snapshot,
            }
            if (
                topology_exact
                and bundle is not None
                and predecessor_snapshot is not None
            )
            else None
        ),
    }


__all__ = (
    "assert_executable_closure_epoch_current",
    "build_closure_epoch",
    "current_task_alias",
    "topology_predecessor_binding",
    "topology_predecessor_matches",
    "validate_selected_successor_predecessor_snapshot",
)
