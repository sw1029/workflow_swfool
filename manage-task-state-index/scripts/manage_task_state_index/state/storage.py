"""Filesystem paths, locking, hashing, and atomic writes for task state."""
from __future__ import annotations

import contextlib
import datetime as dt
import hashlib
import os
import re
import stat
import tempfile
import threading
from pathlib import Path
from typing import Iterator

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows fallback keeps thread safety only.
    fcntl = None  # type: ignore[assignment]

_THREAD_LOCKS: dict[str, threading.RLock] = {}
_THREAD_LOCKS_GUARD = threading.Lock()
_LOCK_STATE = threading.local()


def now_iso() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def id_stamp() -> str:
    return dt.datetime.now().strftime("%Y%m%d-%H%M%S")


def slugify(value: str, fallback: str = "item") -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.lower()).strip("-")
    return (slug or fallback)[:48]


def rel_path(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def sha256_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_title(path: Path) -> str:
    if path.is_file():
        try:
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                stripped = line.strip()
                if stripped.startswith("#"):
                    return stripped.lstrip("#").strip()[:120] or path.stem
                if stripped:
                    return stripped[:120]
        except OSError:
            pass
    return path.stem.replace("-", " ").replace("_", " ")


def task_dir(root: Path) -> Path:
    return root / ".task"


def jsonl_path(root: Path) -> Path:
    return task_dir(root) / "index.jsonl"


def markdown_path(root: Path) -> Path:
    return task_dir(root) / "index.md"


def lock_path(root: Path) -> Path:
    return task_dir(root) / "index.lock"


class StableReadRaceError(ValueError):
    """A read-only task-index snapshot overlapped a filesystem mutation."""


def stable_file_token(path: Path) -> tuple[int, int, int, int, int, str] | None:
    """Hash one regular file only when its identity and metadata remain stable."""

    if not path.exists() and not path.is_symlink():
        return None
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    try:
        descriptor = os.open(path, flags)
    except FileNotFoundError as exc:
        raise StableReadRaceError("task-index snapshot input disappeared") from exc
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise ValueError("Task-index snapshot input must be a regular file")
        digest = hashlib.sha256()
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    fields_before = (
        before.st_dev, before.st_ino, before.st_size,
        before.st_mtime_ns, before.st_ctime_ns,
    )
    fields_after = (
        after.st_dev, after.st_ino, after.st_size,
        after.st_mtime_ns, after.st_ctime_ns,
    )
    try:
        current = path.stat(follow_symlinks=False)
    except FileNotFoundError as exc:
        raise StableReadRaceError("task-index snapshot input disappeared") from exc
    current_fields = (
        current.st_dev, current.st_ino, current.st_size,
        current.st_mtime_ns, current.st_ctime_ns,
    )
    if fields_before != fields_after or fields_after != current_fields:
        raise StableReadRaceError("task-index snapshot input changed while hashing")
    return (*fields_after, digest.hexdigest())


def immutable_snapshot_path(root: Path, item_id: str, source_path: Path) -> Path:
    suffix = source_path.suffix or ".txt"
    return task_dir(root) / "snapshots" / f"{item_id}{suffix}"


def _thread_lock(root: Path) -> threading.RLock:
    key = str(root.resolve())
    with _THREAD_LOCKS_GUARD:
        return _THREAD_LOCKS.setdefault(key, threading.RLock())


def _lock_depths() -> dict[str, dict[str, int]]:
    depths = getattr(_LOCK_STATE, "depths", None)
    if depths is None:
        depths = {}
        _LOCK_STATE.depths = depths
    return depths


def _lock_depth(root: Path, mode: str) -> int:
    return _lock_depths().get(str(root.resolve()), {}).get(mode, 0)


def _change_lock_depth(root: Path, mode: str, delta: int) -> None:
    key = str(root.resolve())
    depths = _lock_depths()
    state = depths.setdefault(key, {})
    updated = state.get(mode, 0) + delta
    if updated < 0:
        raise RuntimeError("task-state lock depth underflow")
    if updated:
        state[mode] = updated
    else:
        state.pop(mode, None)
    if not state:
        depths.pop(key, None)


def _ensure_owned_task_directory(root: Path) -> Path:
    path = root.resolve() / ".task"
    if not path.exists() and not path.is_symlink():
        try:
            os.mkdir(path, mode=0o700)
        except FileExistsError:
            pass
    mode = path.lstat().st_mode
    if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
        raise ValueError("Task-state root must be a regular owned directory")
    return path


@contextlib.contextmanager
def _owned_lock_handle(root: Path) -> Iterator[object]:
    directory = _ensure_owned_task_directory(root)
    if os.name != "posix":  # pragma: no cover - platform fallback
        path = directory / "index.lock"
        if path.exists() or path.is_symlink():
            mode = path.lstat().st_mode
            if stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
                raise ValueError("Task-state lock must be a regular file")
        with path.open("a+b") as handle:
            yield handle
        return
    directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    directory_flags |= getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    directory_fd = os.open(directory, directory_flags)
    descriptor = -1
    try:
        lock_flags = os.O_RDWR | os.O_CREAT | os.O_APPEND
        lock_flags |= getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
        try:
            descriptor = os.open("index.lock", lock_flags, 0o600, dir_fd=directory_fd)
        except OSError as exc:
            raise ValueError("Task-state lock must be a regular owned file") from exc
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise ValueError("Task-state lock must be a regular file")
        with os.fdopen(descriptor, "a+b") as handle:
            descriptor = -1
            yield handle
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        os.close(directory_fd)


@contextlib.contextmanager
def index_lock(root: Path) -> Iterator[None]:
    root = root.resolve()
    with _thread_lock(root):
        if _lock_depth(root, "writer"):
            _change_lock_depth(root, "writer", 1)
            try:
                yield
            finally:
                _change_lock_depth(root, "writer", -1)
            return
        if _lock_depth(root, "reader"):
            raise ValueError("Cannot upgrade a task-state read lock to a writer lock")
        with _owned_lock_handle(root) as handle:
            if fcntl is not None:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            _change_lock_depth(root, "writer", 1)
            try:
                yield
            finally:
                _change_lock_depth(root, "writer", -1)
                if fcntl is not None:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@contextlib.contextmanager
def existing_index_read_lock(root: Path) -> Iterator[bool]:
    """Share an existing writer lock without creating `.task` or `index.lock`."""

    root = root.resolve()
    with _thread_lock(root):
        if _lock_depth(root, "writer") or _lock_depth(root, "reader"):
            _change_lock_depth(root, "reader", 1)
            try:
                yield True
            finally:
                _change_lock_depth(root, "reader", -1)
            return
        directory = task_dir(root)
        if not directory.exists() and not directory.is_symlink():
            yield False
            return
        mode = directory.lstat().st_mode
        if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
            raise ValueError("Task-state root must be a regular owned directory")
        path = lock_path(root)
        if not path.exists() and not path.is_symlink():
            yield False
            return
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
        try:
            descriptor = os.open(path, flags)
        except FileNotFoundError:
            yield False
            return
        with os.fdopen(descriptor, "rb", closefd=True) as handle:
            opened = os.fstat(handle.fileno())
            if not stat.S_ISREG(opened.st_mode):
                raise ValueError("Task-state lock must be a regular file")
            if fcntl is not None:
                fcntl.flock(handle.fileno(), fcntl.LOCK_SH)
            _change_lock_depth(root, "reader", 1)
            try:
                yield True
                try:
                    current = path.stat(follow_symlinks=False)
                except FileNotFoundError as exc:
                    raise StableReadRaceError(
                        "task-index lock changed during read"
                    ) from exc
                if (opened.st_dev, opened.st_ino) != (
                    current.st_dev, current.st_ino
                ):
                    raise StableReadRaceError("task-index lock changed during read")
            finally:
                _change_lock_depth(root, "reader", -1)
                if fcntl is not None:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _fsync_directory(path: Path) -> None:
    try:
        descriptor = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def atomic_write_bytes(path: Path, payload: bytes, mode: int = 0o644) -> None:
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
        _fsync_directory(path.parent)
    except BaseException:
        try:
            os.close(descriptor)
        except OSError:
            pass
        temporary.unlink(missing_ok=True)
        raise


def atomic_write_text(path: Path, text: str, mode: int = 0o644) -> None:
    atomic_write_bytes(path, text.encode("utf-8"), mode=mode)


def _ensure_index_unlocked(root: Path) -> None:
    task_dir(root).mkdir(parents=True, exist_ok=True)
    if not jsonl_path(root).exists():
        atomic_write_bytes(jsonl_path(root), b"")


def ensure_index(root: Path) -> None:
    with index_lock(root):
        _ensure_index_unlocked(root)
