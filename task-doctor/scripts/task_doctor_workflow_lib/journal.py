from __future__ import annotations

import contextlib
import fcntl
import json
import os
import stat
from pathlib import Path, PurePosixPath
from typing import Any, Iterator
import uuid

from .common import (
    SAFE_ID,
    WorkflowError,
    canonical_bytes,
    now,
    require,
)
from .journal_contract import validate_journal
from .task_transition_store import (
    _parent_descriptor,
    _read_leaf,
    _verify_directory_identity,
)


JOURNAL_PARENT = PurePosixPath(".task/task_doctor/workflows")


def workspace_root(value: str | Path) -> Path:
    root = Path(value).resolve()
    require(root.is_dir(), "invalid_root", f"workspace root is not a directory: {root}")
    return root


def workflow_paths(root: Path, workflow_id: str) -> tuple[Path, Path]:
    require(SAFE_ID.fullmatch(workflow_id) is not None, "invalid_workflow_id",
            f"invalid workflow id: {workflow_id}")
    directory = root / ".task" / "task_doctor" / "workflows"
    _validate_owned_directory(root, directory, create=False)
    for leaf in (directory / f"{workflow_id}.json", directory / f"{workflow_id}.lock"):
        if leaf.exists() or leaf.is_symlink():
            mode = os.lstat(leaf).st_mode
            require(stat.S_ISREG(mode) and not stat.S_ISLNK(mode), "invalid_journal_path",
                    f"task-doctor journal path must be a regular file: {leaf.name}")
    return directory / f"{workflow_id}.json", directory / f"{workflow_id}.lock"


def _validate_owned_directory(root: Path, directory: Path, *, create: bool) -> None:
    root = root.resolve()
    try:
        relative = directory.relative_to(root)
    except ValueError as error:
        raise WorkflowError("invalid_journal_path",
                            "task-doctor journal directory escapes workspace") from error
    current = root
    for part in relative.parts:
        current /= part
        try:
            mode = os.lstat(current).st_mode
        except FileNotFoundError:
            if not create:
                return
            try:
                os.mkdir(current, mode=0o700)
            except FileExistsError:
                pass
            mode = os.lstat(current).st_mode
        require(stat.S_ISDIR(mode) and not stat.S_ISLNK(mode), "invalid_journal_path",
                "task-doctor journal ancestors must be real directories")


@contextlib.contextmanager
def locked(root: Path, lock_path: Path) -> Iterator[None]:
    try:
        with _parent_descriptor(
            root, JOURNAL_PARENT, create=True,
        ) as (root_path, parent, identities):
            assert parent is not None
            _verify_directory_identity(root_path, JOURNAL_PARENT, identities)
            flags = os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0)
            descriptor = os.open(lock_path.name, flags, 0o600, dir_fd=parent)
            with os.fdopen(descriptor, "r+") as handle:
                require(stat.S_ISREG(os.fstat(handle.fileno()).st_mode),
                        "invalid_journal_path",
                        "task-doctor journal lock must be a regular file")
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
                try:
                    _verify_directory_identity(
                        root_path, JOURNAL_PARENT, identities
                    )
                    yield
                finally:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    except WorkflowError as error:
        if error.code == "invalid_owner_path":
            raise WorkflowError(
                "invalid_journal_path",
                "task-doctor journal ancestor identity is unsafe",
            ) from error
        raise


def atomic_write(root: Path, path: Path, value: dict[str, Any]) -> None:
    try:
        with _parent_descriptor(
            root, JOURNAL_PARENT, create=True,
        ) as (root_path, parent, identities):
            assert parent is not None
            _verify_directory_identity(root_path, JOURNAL_PARENT, identities)
            _read_leaf(parent, path.name, "task-doctor journal")
            temporary = f".{path.name}.{uuid.uuid4().hex}.tmp"
            flags = (
                os.O_WRONLY | os.O_CREAT | os.O_EXCL
                | getattr(os, "O_NOFOLLOW", 0)
            )
            descriptor = os.open(temporary, flags, 0o600, dir_fd=parent)
            try:
                payload = canonical_bytes(value)
                with os.fdopen(descriptor, "wb", closefd=False) as handle:
                    handle.write(payload)
                    handle.flush()
                    os.fsync(handle.fileno())
                _verify_directory_identity(root_path, JOURNAL_PARENT, identities)
                os.replace(
                    temporary, path.name, src_dir_fd=parent, dst_dir_fd=parent
                )
                os.fsync(parent)
                _verify_directory_identity(root_path, JOURNAL_PARENT, identities)
                require(_read_leaf(parent, path.name, "task-doctor journal") == payload,
                        "invalid_journal_path",
                        "journal publication did not preserve canonical bytes")
            finally:
                os.close(descriptor)
                try:
                    os.unlink(temporary, dir_fd=parent)
                except FileNotFoundError:
                    pass
    except WorkflowError as error:
        if error.code == "invalid_owner_path":
            raise WorkflowError(
                "invalid_journal_path",
                "task-doctor journal ancestor identity changed during publication",
            ) from error
        raise


def load(root: Path, workflow_id: str) -> tuple[Path, Path, dict[str, Any]]:
    journal_path, lock_path = workflow_paths(root, workflow_id)
    try:
        with _parent_descriptor(
            root, JOURNAL_PARENT, create=False,
        ) as (root_path, parent, identities):
            if parent is None:
                raise WorkflowError(
                    "workflow_not_found", f"workflow not found: {workflow_id}"
                )
            payload = _read_leaf(parent, journal_path.name, "task-doctor journal")
            _verify_directory_identity(root_path, JOURNAL_PARENT, identities)
        if payload is None:
            raise WorkflowError(
                "workflow_not_found", f"workflow not found: {workflow_id}"
            )
        decoded = json.loads(payload.decode("utf-8"))
        require(isinstance(decoded, dict), "invalid_journal",
                "workflow journal root must be an object")
        journal = decoded
    except WorkflowError as error:
        if error.code == "invalid_owner_path":
            raise WorkflowError(
                "invalid_journal_path", "task-doctor journal path is unsafe"
            ) from error
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise WorkflowError("invalid_journal", "workflow journal JSON is invalid") from error
    return journal_path, lock_path, validate_journal(journal, workflow_id)


def check_revision(journal: dict[str, Any], expected: int) -> None:
    require(journal["revision"] == expected, "revision_conflict",
            "workflow journal revision changed", retryable=True,
            next_action="reload_status",
            details={"expected": expected, "observed": journal["revision"]})


def event(journal: dict[str, Any], name: str, **fields: Any) -> None:
    journal["events"].append({"at": now(), "event": name, **fields})
    journal["updated_at"] = journal["events"][-1]["at"]
    journal["revision"] += 1


def operation(
    journal: dict[str, Any], operation_id: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    plan_operation = next(
        (item for item in journal["plan"]["operations"]
         if item["operation_id"] == operation_id), None
    )
    require(plan_operation is not None, "operation_not_found",
            f"unknown operation: {operation_id}")
    assert isinstance(plan_operation, dict)
    state = journal["operation_state"][operation_id]
    assert isinstance(state, dict)
    return plan_operation, state


def dependencies_complete(journal: dict[str, Any], item: dict[str, Any]) -> bool:
    return all(
        journal["operation_state"][dependency]["status"] in {"complete", "skipped"}
        for dependency in item["dependencies"]
    )
