"""Migration filesystem, hash, path, lock, and anchor primitives."""
from __future__ import annotations

import contextlib
import datetime as dt
import fcntl
import hashlib
import json
import os
import re
import stat
import tempfile
import threading
from pathlib import Path
from typing import Any, Iterator

from .contracts import MigrationError

_THREAD_LOCKS: dict[str, threading.RLock] = {}
_THREAD_LOCKS_GUARD = threading.Lock()

def _now() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha_file(path: Path) -> str:
    return _sha256(path.read_bytes())


def _canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _event_bytes(events: list[dict[str, Any]]) -> bytes:
    return b"".join(_canonical_bytes(event) for event in events)


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MigrationError(f"Invalid {label}: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise MigrationError(f"Invalid {label}: expected a JSON object: {path}")
    return value


def _atomic_write(path: Path, payload: bytes, mode: int = 0o644) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, mode)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        _fsync_dir(path.parent)
    except BaseException:
        try:
            os.close(descriptor)
        except OSError:
            pass
        temporary.unlink(missing_ok=True)
        raise


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    _atomic_write(path, _canonical_bytes(value))


def _fsync_dir(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _thread_lock(root: Path) -> threading.RLock:
    key = str(root.resolve())
    with _THREAD_LOCKS_GUARD:
        return _THREAD_LOCKS.setdefault(key, threading.RLock())


@contextlib.contextmanager
def _index_lock(root: Path) -> Iterator[None]:
    root = root.resolve()
    task = root / ".task"
    if task.is_symlink() or (task.exists() and not task.is_dir()):
        raise MigrationError("Unsafe .task path")
    task.mkdir(parents=True, exist_ok=True)
    lock = task / "index.lock"
    flags = os.O_CREAT | os.O_RDWR
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    with _thread_lock(root):
        try:
            descriptor = os.open(lock, flags, 0o644)
        except OSError as exc:
            raise MigrationError("Unable to open non-symlink .task/index.lock") from exc
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            os.close(descriptor)
            raise MigrationError(".task/index.lock is not a regular file")
        with os.fdopen(descriptor, "a+b") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _root_identity(root: Path) -> dict[str, Any]:
    resolved = root.resolve(strict=True)
    stat = resolved.stat()
    return {"resolved_path": str(resolved), "device": stat.st_dev, "inode": stat.st_ino}


def _index_path(root: Path) -> Path:
    path = root / ".task" / "index.jsonl"
    if path.is_symlink() or not path.is_file():
        raise MigrationError(".task/index.jsonl must be a regular non-symlink file")
    return path


def _safe_ref(root: Path, ref: str, *, must_exist: bool = True) -> Path:
    if not isinstance(ref, str) or not ref or Path(ref).is_absolute():
        raise MigrationError(f"Unsafe migration sidecar ref: {ref!r}")
    root_resolved = root.resolve()
    candidate = root / ref
    if any(part in {"", ".", ".."} for part in Path(ref).parts):
        raise MigrationError(f"Unsafe migration sidecar ref: {ref!r}")
    current = root_resolved
    for part in Path(ref).parts:
        current = current / part
        if current.is_symlink():
            raise MigrationError(f"Symlink migration sidecar ref: {ref!r}")
    try:
        resolved = candidate.resolve(strict=must_exist)
    except OSError as exc:
        raise MigrationError(f"Missing or inaccessible migration sidecar ref: {ref!r}") from exc
    try:
        resolved.relative_to(root_resolved)
    except ValueError as exc:
        raise MigrationError(f"Migration sidecar escapes root: {ref!r}") from exc
    if must_exist and not resolved.is_file():
        raise MigrationError(f"Migration sidecar is not a regular file: {ref!r}")
    return resolved


def _validate_plan_anchors(root: Path, plan: dict[str, Any]) -> None:
    """Recheck caller-designated task/pack identities without trusting paths."""
    anchors = plan.get("anchors")
    if not isinstance(anchors, dict):
        raise MigrationError("Migration plan lacks exact caller anchors")
    checked: dict[str, tuple[Path, dict[str, Any]]] = {}
    for key, label in (("current_task", "current task"), ("current_pack", "current pack")):
        anchor = anchors.get(key)
        if not isinstance(anchor, dict):
            raise MigrationError(f"Migration plan lacks exact {label} anchor")
        relative = anchor.get("path")
        expected_sha = anchor.get("sha256")
        identity = anchor.get("id")
        if (
            not isinstance(relative, str)
            or not isinstance(identity, str)
            or not identity
            or not isinstance(expected_sha, str)
            or re.fullmatch(r"[0-9a-f]{64}", expected_sha) is None
        ):
            raise MigrationError(f"Invalid exact {label} anchor contract")
        try:
            path = _safe_ref(root, relative)
        except MigrationError as exc:
            raise MigrationError(f"Exact {label} anchor path is unsafe") from exc
        if _sha_file(path) != expected_sha:
            raise MigrationError(f"Exact {label} anchor mismatch")
        checked[key] = (path, anchor)
    pack_path, pack_anchor = checked["current_pack"]
    pack_value = _read_json(pack_path, "current pack anchor")
    if pack_value.get("pack_id") != pack_anchor["id"]:
        raise MigrationError("Current pack ID does not match caller-designated identity")
