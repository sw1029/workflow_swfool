"""Directory-bound storage primitives for task-scope owner transactions."""

from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
from typing import Any, Iterator
import uuid

from .common import WorkflowError, canonical_bytes, require
from .task_transition_plan import validate_task_transition_plan


TRANSACTION_ROOT = PurePosixPath(".task/task_doctor/transitions")
PLAN_ROOT = PurePosixPath(".task/task_doctor/transition-plans")
REVIEW_ROOT = PurePosixPath(".task/task_doctor/reviews")
WORKFLOW_PLAN_ROOT = PurePosixPath(".task/task_doctor/workflow-plans")
BUNDLE_ROOT = PurePosixPath(".task/task_doctor/bundles")


def _canonical_ref(value: str, label: str) -> PurePosixPath:
    candidate = PurePosixPath(value)
    require(
        bool(value)
        and not candidate.is_absolute()
        and candidate.as_posix() == value
        and all(part not in {"", ".", ".."} for part in candidate.parts),
        "invalid_owner_plan",
        f"{label} must be one canonical workspace-relative POSIX ref",
    )
    return candidate


def _directory_flags() -> int:
    return (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )


def _identity(descriptor: int) -> tuple[int, int]:
    observed = os.fstat(descriptor)
    require(stat.S_ISDIR(observed.st_mode), "invalid_owner_path",
            "task transition ancestor is not a directory")
    return observed.st_dev, observed.st_ino


def _open_directory(
    name: str | Path, *, dir_fd: int | None = None,
) -> int:
    try:
        return os.open(name, _directory_flags(), dir_fd=dir_fd)
    except (FileNotFoundError, NotADirectoryError, OSError) as error:
        raise WorkflowError(
            "invalid_owner_path",
            "task transition owned ancestors must be stable real directories",
        ) from error


@contextlib.contextmanager
def _parent_descriptor(
    root: Path, relative_parent: PurePosixPath, *, create: bool,
) -> Iterator[tuple[Path, int | None, tuple[tuple[int, int], ...]]]:
    root_path = root.resolve()
    descriptors: list[int] = []
    try:
        root_descriptor = _open_directory(root_path)
        descriptors.append(root_descriptor)
        identities = [_identity(root_descriptor)]
        current = root_descriptor
        for part in relative_parent.parts:
            try:
                child = os.open(part, _directory_flags(), dir_fd=current)
            except FileNotFoundError:
                if not create:
                    yield root_path, None, tuple(identities)
                    return
                try:
                    os.mkdir(part, mode=0o700, dir_fd=current)
                except FileExistsError:
                    pass
                child = _open_directory(part, dir_fd=current)
            except (NotADirectoryError, OSError) as error:
                raise WorkflowError(
                    "invalid_owner_path",
                    "task transition owned ancestors must be real directories",
                ) from error
            descriptors.append(child)
            identities.append(_identity(child))
            current = child
        yield root_path, current, tuple(identities)
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def _verify_directory_identity(
    root_path: Path, relative_parent: PurePosixPath,
    expected: tuple[tuple[int, int], ...],
) -> None:
    descriptors: list[int] = []
    try:
        current = _open_directory(root_path)
        descriptors.append(current)
        observed = [_identity(current)]
        for part in relative_parent.parts:
            current = _open_directory(part, dir_fd=current)
            descriptors.append(current)
            observed.append(_identity(current))
        require(tuple(observed) == expected, "invalid_owner_path",
                "task transition ancestor identity changed during publication")
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def _read_leaf(parent: int, name: str, label: str) -> bytes | None:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(name, flags, dir_fd=parent)
    except FileNotFoundError:
        return None
    except OSError as error:
        raise WorkflowError(
            "invalid_owner_path", f"{label} must be a regular file"
        ) from error
    try:
        require(stat.S_ISREG(os.fstat(descriptor).st_mode), "invalid_owner_path",
                f"{label} must be a regular file")
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                return b"".join(chunks)
            chunks.append(chunk)
    finally:
        os.close(descriptor)


def _digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _owned_relative(ref: str) -> PurePosixPath:
    relative = _canonical_ref(ref, "owned artifact ref")
    transaction_artifact = relative.parts[:3] == TRANSACTION_ROOT.parts
    plan_artifact = relative.parent in {
        PLAN_ROOT, REVIEW_ROOT, WORKFLOW_PLAN_ROOT, BUNDLE_ROOT,
    }
    require(transaction_artifact or plan_artifact, "invalid_owner_path",
            "task transition artifact escapes its owned roots")
    return relative


def owned_ref(transition_id: str, kind: str, suffix: str) -> str:
    require(kind in {
        "archives", "intents", "receipts", "locks", "successors", "observations",
        "dependency-cancellations",
    }, "invalid_owner_path", "unknown task transition artifact kind")
    return (TRANSACTION_ROOT / kind / f"{transition_id}.{suffix}").as_posix()


def owned_path(root: Path, ref: str, *, create_parent: bool = False) -> Path:
    """Return a convenience path only after a directory-identity safety check."""

    relative = _owned_relative(ref)
    with _parent_descriptor(
        root, relative.parent, create=create_parent,
    ) as (root_path, parent, identities):
        require(parent is not None, "invalid_owner_path",
                "task transition artifact parent is missing")
        assert parent is not None
        _verify_directory_identity(root_path, relative.parent, identities)
        payload = _read_leaf(parent, relative.name, "task transition artifact")
        if payload is not None:
            _verify_directory_identity(root_path, relative.parent, identities)
        return root_path / relative


def file_bytes(root: Path, ref: str, label: str) -> bytes | None:
    """Read one regular file through stable directory descriptors."""

    relative = _canonical_ref(ref, label)
    with _parent_descriptor(
        root, relative.parent, create=False,
    ) as (root_path, parent, identities):
        if parent is None:
            return None
        payload = _read_leaf(parent, relative.name, label)
        _verify_directory_identity(root_path, relative.parent, identities)
        return payload


def publish_immutable(
    root: Path, ref: str, value: dict[str, Any] | bytes,
) -> tuple[bool, str]:
    """Publish immutable bytes through one bound parent descriptor."""

    relative = _owned_relative(ref)
    payload = canonical_bytes(value) if isinstance(value, dict) else value
    with _parent_descriptor(
        root, relative.parent, create=True,
    ) as (root_path, parent, identities):
        assert parent is not None
        _verify_directory_identity(root_path, relative.parent, identities)
        existing = _read_leaf(parent, relative.name, "immutable owner artifact")
        if existing is not None:
            require(existing == payload, "owner_artifact_conflict",
                    f"immutable task transition artifact conflicts: {ref}")
            return False, _digest(existing)
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(relative.name, flags, 0o600, dir_fd=parent)
        except FileExistsError:
            existing = _read_leaf(parent, relative.name, "immutable owner artifact")
            require(existing == payload, "owner_artifact_conflict",
                    f"immutable task transition artifact conflicts: {ref}")
            assert existing is not None
            return False, _digest(existing)
        try:
            with os.fdopen(descriptor, "wb", closefd=False) as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
        finally:
            os.close(descriptor)
        os.fsync(parent)
        _verify_directory_identity(root_path, relative.parent, identities)
    observed = file_bytes(root, ref, "published immutable owner artifact")
    require(observed == payload, "invalid_owner_path",
            "published artifact is not reachable through its canonical directory chain")
    return True, _digest(payload)


@contextlib.contextmanager
def transition_lock(root: Path, transition_id: str) -> Iterator[None]:
    relative = _owned_relative(owned_ref(transition_id, "locks", "lock"))
    with _parent_descriptor(
        root, relative.parent, create=True,
    ) as (root_path, parent, identities):
        assert parent is not None
        _verify_directory_identity(root_path, relative.parent, identities)
        flags = os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(relative.name, flags, 0o600, dir_fd=parent)
        except OSError as error:
            raise WorkflowError(
                "invalid_owner_path", "task transition lock is unsafe"
            ) from error
        with os.fdopen(descriptor, "r+") as handle:
            require(stat.S_ISREG(os.fstat(handle.fileno()).st_mode),
                    "invalid_owner_path", "task transition lock is not regular")
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                _verify_directory_identity(root_path, relative.parent, identities)
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def replace_canonical_task(
    root: Path, payload: bytes, before: dict[str, Any], after_sha256: str,
) -> None:
    """Recheck exact CAS and atomically replace canonical task bytes."""

    observed = file_bytes(root, "task.md", "canonical task")
    require(
        (observed is not None) == before["exists"]
        and (observed is None or _digest(observed) == before["sha256"]),
        "task_transition_cas_mismatch",
        "canonical task changed immediately before atomic replacement",
    )
    require(_digest(payload) == after_sha256, "invalid_owner_plan",
            "prospective task bytes differ from the planned after digest")
    with _parent_descriptor(
        root, PurePosixPath(), create=False,
    ) as (root_path, parent, identities):
        assert parent is not None
        _verify_directory_identity(root_path, PurePosixPath(), identities)
        temporary = f".task.md.{uuid.uuid4().hex}.tmp"
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(temporary, flags, 0o600, dir_fd=parent)
        try:
            with os.fdopen(descriptor, "wb", closefd=False) as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            _verify_directory_identity(root_path, PurePosixPath(), identities)
            os.replace(temporary, "task.md", src_dir_fd=parent, dst_dir_fd=parent)
            os.fsync(parent)
            _verify_directory_identity(root_path, PurePosixPath(), identities)
        finally:
            os.close(descriptor)
            try:
                os.unlink(temporary, dir_fd=parent)
            except FileNotFoundError:
                pass
    current = file_bytes(root, "task.md", "canonical task")
    require(current is not None and _digest(current) == after_sha256,
            "task_transition_write_failed",
            "canonical task replacement did not produce the planned bytes")


def publish_task_transition_plan(
    root: Path, plan: dict[str, Any],
) -> dict[str, Any]:
    """Publish or replay one canonical immutable task-transition plan."""

    normalized = validate_task_transition_plan(plan)
    ref = (PLAN_ROOT / f"{normalized['transition_id']}.json").as_posix()
    created, digest = publish_immutable(root, ref, normalized)
    return {
        "plan_ref": ref,
        "plan_file_sha256": digest,
        "created": created,
        "replayed": not created,
    }


def load_task_transition_plan(
    root: Path, path_value: str | Path,
) -> tuple[Path, dict[str, Any], str, str]:
    root_path = root.resolve()
    raw = Path(path_value)
    if raw.is_absolute():
        try:
            ref = raw.relative_to(root_path).as_posix()
        except ValueError as error:
            raise WorkflowError(
                "invalid_owner_plan", "task transition plan escapes workspace"
            ) from error
    else:
        ref = raw.as_posix()
    relative = _canonical_ref(ref, "task transition plan ref")
    require(relative.parent == PLAN_ROOT,
            "invalid_owner_plan",
            "task transition plan must use "
            ".task/task_doctor/transition-plans/<id>.json")
    payload = file_bytes(root_path, ref, "task transition plan")
    require(payload is not None, "invalid_owner_plan",
            "task transition plan is missing")
    assert payload is not None
    try:
        decoded = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise WorkflowError(
            "invalid_owner_plan", "task transition plan is not canonical JSON"
        ) from error
    plan = validate_task_transition_plan(decoded)
    require(payload == canonical_bytes(plan), "invalid_owner_plan",
            "task transition plan bytes must use canonical JSON encoding")
    require(relative.name == f"{plan['transition_id']}.json", "invalid_owner_plan",
            "task transition plan filename must match transition_id")
    return root_path / relative, plan, _digest(payload), ref


__all__ = [
    "file_bytes",
    "load_task_transition_plan",
    "owned_path",
    "owned_ref",
    "publish_immutable",
    "publish_task_transition_plan",
    "replace_canonical_task",
    "transition_lock",
]
