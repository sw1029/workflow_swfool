"""Filesystem paths, locking, hashing, and atomic writes for task state."""
from __future__ import annotations

import contextlib
import datetime as dt
import hashlib
import os
import re
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


def immutable_snapshot_path(root: Path, item_id: str, source_path: Path) -> Path:
    suffix = source_path.suffix or ".txt"
    return task_dir(root) / "snapshots" / f"{item_id}{suffix}"


def _thread_lock(root: Path) -> threading.RLock:
    key = str(root.resolve())
    with _THREAD_LOCKS_GUARD:
        return _THREAD_LOCKS.setdefault(key, threading.RLock())


@contextlib.contextmanager
def index_lock(root: Path) -> Iterator[None]:
    root = root.resolve()
    with _thread_lock(root):
        task_dir(root).mkdir(parents=True, exist_ok=True)
        with lock_path(root).open("a+b") as handle:
            if fcntl is not None:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
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
