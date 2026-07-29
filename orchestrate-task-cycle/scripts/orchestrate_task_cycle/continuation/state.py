"""Durable tracked continuation state and optimistic replay token."""

from __future__ import annotations

from copy import deepcopy
import fcntl
import json
import os
from pathlib import Path, PurePosixPath
import tempfile
from typing import Any

from .actions import validate_action
from .contracts import (
    ContinuationContractError,
    binding,
    canonical_bytes,
    digest,
    opaque,
    sha,
    timestamp,
)
from .safe_files import read_bytes_no_follow, read_named_bytes_no_follow


STATE_KIND = "orchestrate_continuation_session"
STATE_SCHEMA_VERSION = 1
DEFAULT_BUDGETS = {
    "max_cycles": 3,
    "max_agent_actions": 72,
    "max_concurrent_long_runs": 1,
    "max_commits_per_cycle": 1,
}


def state_ref(session_id: str) -> str:
    identifier = opaque(session_id, "session_id")
    return PurePosixPath(
        ".task",
        "authorization",
        "sessions",
        str(identifier),
        "workflow-session.json",
    ).as_posix()


def _state_path(
    workspace: Path,
    session_id: str,
    *,
    create_parent: bool,
) -> Path:
    ref = Path(state_ref(session_id))
    current = workspace
    for part in ref.parts[:-1]:
        current = current / part
        if current.is_symlink():
            raise ContinuationContractError(
                "continuation state path traverses a symlink"
            )
    if create_parent:
        (workspace / ref).parent.mkdir(parents=True, exist_ok=True)
        current = workspace
        for part in ref.parts[:-1]:
            current = current / part
            if current.is_symlink():
                raise ContinuationContractError(
                    "continuation state path traverses a symlink"
                )
    path = workspace / ref
    if path.is_symlink():
        raise ContinuationContractError(
            "continuation state target must not be a symlink"
        )
    return path


def _material(value: dict[str, Any]) -> dict[str, Any]:
    return {key: value[key] for key in value if key != "state_sha256"}


def _normalize_budgets(value: Any) -> dict[str, int]:
    if not isinstance(value, dict) or set(value) != set(DEFAULT_BUDGETS):
        raise ContinuationContractError("continuation budgets are not closed")
    normalized: dict[str, int] = {}
    for field in DEFAULT_BUDGETS:
        item = value[field]
        if isinstance(item, bool) or not isinstance(item, int) or item < 1:
            raise ContinuationContractError(f"{field} must be positive")
        normalized[field] = item
    return normalized


def _normalize_usage(value: Any) -> dict[str, Any]:
    fields = {"cycles", "agent_actions", "active_long_runs", "commits_by_cycle"}
    if not isinstance(value, dict) or set(value) != fields:
        raise ContinuationContractError("continuation usage is not closed")
    cycles = value["cycles"]
    actions = value["agent_actions"]
    if any(
        isinstance(item, bool) or not isinstance(item, int) or item < 0
        for item in (cycles, actions)
    ):
        raise ContinuationContractError("continuation counters must be non-negative")
    runs = [opaque(item, "active run id") for item in value["active_long_runs"]]
    if len(runs) != len(set(runs)):
        raise ContinuationContractError("active long runs must be unique")
    commits = value["commits_by_cycle"]
    if not isinstance(commits, dict):
        raise ContinuationContractError("commits_by_cycle must be an object")
    normalized_commits: dict[str, int] = {}
    for cycle_id, count in commits.items():
        key = opaque(cycle_id, "commit cycle id")
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise ContinuationContractError("commit count must be non-negative")
        normalized_commits[str(key)] = count
    return {
        "cycles": cycles,
        "agent_actions": actions,
        "active_long_runs": sorted(str(item) for item in runs),
        "commits_by_cycle": dict(sorted(normalized_commits.items())),
    }


def build_state(
    *,
    session_id: str,
    session_lease_binding: dict[str, str],
    goal_id: str,
    task_family: str,
    cycle_id: str,
    task_id: str,
    created_at: str,
    budgets: dict[str, int] | None = None,
) -> dict[str, Any]:
    value: dict[str, Any] = {
        "schema_version": STATE_SCHEMA_VERSION,
        "artifact_kind": STATE_KIND,
        "profile_id": "adaptive_session_v1",
        "session_id": opaque(session_id, "session_id"),
        "session_lease_binding": binding(
            session_lease_binding, "session_lease_binding"
        ),
        "goal_id": opaque(goal_id, "goal_id"),
        "task_family": opaque(task_family, "task_family"),
        "cycle_ids": [opaque(cycle_id, "cycle_id")],
        "active_cycle_id": opaque(cycle_id, "cycle_id"),
        "active_task_id": opaque(task_id, "task_id"),
        "status": "active",
        "host_session_live": True,
        "closure_only": False,
        "budgets": _normalize_budgets(budgets or dict(DEFAULT_BUDGETS)),
        "usage": {
            "cycles": 1,
            "agent_actions": 0,
            "active_long_runs": [],
            "commits_by_cycle": {},
        },
        "pending_action": None,
        "accepted_actions": {},
        "last_stop_reason": None,
        "created_at": timestamp(created_at, "created_at"),
        "updated_at": timestamp(created_at, "updated_at"),
        "state_version": 1,
    }
    value["state_sha256"] = digest(_material(value))
    return validate_state(value)


def validate_state(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ContinuationContractError("continuation state must be an object")
    fields = {
        "schema_version",
        "artifact_kind",
        "profile_id",
        "session_id",
        "session_lease_binding",
        "goal_id",
        "task_family",
        "cycle_ids",
        "active_cycle_id",
        "active_task_id",
        "status",
        "host_session_live",
        "closure_only",
        "budgets",
        "usage",
        "pending_action",
        "accepted_actions",
        "last_stop_reason",
        "created_at",
        "updated_at",
        "state_version",
        "state_sha256",
    }
    if set(value) != fields:
        raise ContinuationContractError("continuation state fields are not closed")
    if (
        value.get("schema_version") != STATE_SCHEMA_VERSION
        or value.get("artifact_kind") != STATE_KIND
        or value.get("profile_id") != "adaptive_session_v1"
    ):
        raise ContinuationContractError("unsupported continuation state contract")
    status = str(value.get("status") or "")
    if status not in {
        "active",
        "waiting",
        "stopped",
        "complete",
        "quarantined",
        "host_boundary",
    }:
        raise ContinuationContractError("invalid continuation status")
    if not isinstance(value.get("host_session_live"), bool) or not isinstance(
        value.get("closure_only"), bool
    ):
        raise ContinuationContractError("continuation lifecycle flags must be boolean")
    cycle_ids = [opaque(item, "cycle_id") for item in value.get("cycle_ids") or []]
    if not cycle_ids or len(cycle_ids) != len(set(cycle_ids)):
        raise ContinuationContractError("cycle_ids must be non-empty and unique")
    active_cycle = opaque(value.get("active_cycle_id"), "active_cycle_id")
    if active_cycle not in cycle_ids:
        raise ContinuationContractError("active cycle is outside the session")
    pending = value.get("pending_action")
    normalized_pending = validate_action(pending) if pending is not None else None
    accepted = value.get("accepted_actions")
    if not isinstance(accepted, dict):
        raise ContinuationContractError("accepted_actions must be an object")
    normalized_accepted: dict[str, str] = {}
    for action_id, result_sha in accepted.items():
        normalized_accepted[str(opaque(action_id, "accepted action id"))] = sha(
            result_sha,
            "accepted action result digest",
        )
    state_version = value.get("state_version")
    if (
        isinstance(state_version, bool)
        or not isinstance(state_version, int)
        or state_version < 1
    ):
        raise ContinuationContractError("state_version must be positive")
    normalized: dict[str, Any] = {
        "schema_version": STATE_SCHEMA_VERSION,
        "artifact_kind": STATE_KIND,
        "profile_id": "adaptive_session_v1",
        "session_id": opaque(value.get("session_id"), "session_id"),
        "session_lease_binding": binding(
            value.get("session_lease_binding"), "session_lease_binding"
        ),
        "goal_id": opaque(value.get("goal_id"), "goal_id"),
        "task_family": opaque(value.get("task_family"), "task_family"),
        "cycle_ids": [str(item) for item in cycle_ids],
        "active_cycle_id": active_cycle,
        "active_task_id": opaque(value.get("active_task_id"), "active_task_id"),
        "status": status,
        "host_session_live": value["host_session_live"],
        "closure_only": value["closure_only"],
        "budgets": _normalize_budgets(value.get("budgets")),
        "usage": _normalize_usage(value.get("usage")),
        "pending_action": normalized_pending,
        "accepted_actions": dict(sorted(normalized_accepted.items())),
        "last_stop_reason": opaque(
            value.get("last_stop_reason"), "last_stop_reason", nullable=True
        ),
        "created_at": timestamp(value.get("created_at"), "created_at"),
        "updated_at": timestamp(value.get("updated_at"), "updated_at"),
        "state_version": state_version,
    }
    expected = digest(_material(normalized))
    if value.get("state_sha256") != expected:
        raise ContinuationContractError("continuation state digest mismatch")
    return {**normalized, "state_sha256": expected}


def evolve(value: dict[str, Any], *, at: str, **changes: Any) -> dict[str, Any]:
    current = validate_state(value)
    updated = deepcopy(current)
    for field, item in changes.items():
        if field not in current or field in {
            "schema_version",
            "artifact_kind",
            "profile_id",
            "session_id",
            "created_at",
            "state_sha256",
        }:
            raise ContinuationContractError(
                f"continuation state field cannot be changed: {field}"
            )
        updated[field] = item
    updated["updated_at"] = timestamp(at, "updated_at")
    updated["state_version"] = current["state_version"] + 1
    updated["state_sha256"] = digest(_material(updated))
    return validate_state(updated)


def write_state(
    root: str | Path,
    value: dict[str, Any],
    *,
    expected_state_sha256: str | None = None,
) -> Path:
    state = validate_state(value)
    workspace = Path(root).resolve(strict=True)
    path = _state_path(
        workspace, state["session_id"], create_parent=True
    )
    payload = json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    directory_descriptor = os.open(
        path.parent,
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0),
    )
    try:
        fcntl.flock(directory_descriptor, fcntl.LOCK_EX)
        current: dict[str, Any] | None = None
        if path.is_symlink():
            raise ContinuationContractError(
                "continuation state target must not be a symlink"
            )
        if path.exists():
            try:
                current = validate_state(
                    json.loads(
                        read_named_bytes_no_follow(
                            directory_descriptor,
                            path.name,
                            label="continuation state",
                        )
                    )
                )
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                raise ContinuationContractError(
                    "existing continuation state is invalid"
                ) from exc
            if current == state:
                return path
            if expected_state_sha256 is None:
                raise ContinuationContractError(
                    "continuation state already exists"
                )
            if current["state_sha256"] != expected_state_sha256:
                raise ContinuationContractError(
                    "continuation state compare-and-swap failed"
                )
        elif expected_state_sha256 is not None:
            raise ContinuationContractError(
                "continuation state disappeared before update"
            )
        descriptor, temporary = tempfile.mkstemp(
            prefix=".workflow-session-", dir=path.parent
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
            os.fsync(directory_descriptor)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
    finally:
        fcntl.flock(directory_descriptor, fcntl.LOCK_UN)
        os.close(directory_descriptor)
    return path


def load_state(root: str | Path, session_id: str) -> dict[str, Any]:
    workspace = Path(root).resolve(strict=True)
    path = _state_path(workspace, session_id, create_parent=False)
    try:
        value = json.loads(
            read_bytes_no_follow(path, label="continuation state")
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise ContinuationContractError(
            f"cannot load continuation state: {exc}"
        ) from exc
    return validate_state(value)


__all__ = (
    "DEFAULT_BUDGETS",
    "STATE_KIND",
    "STATE_SCHEMA_VERSION",
    "build_state",
    "evolve",
    "load_state",
    "state_ref",
    "validate_state",
    "write_state",
)
