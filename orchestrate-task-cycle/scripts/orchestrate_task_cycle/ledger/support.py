from __future__ import annotations

import fcntl
import hashlib
import json
import os
import stat
import sys
import threading
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from .constants import CYCLE_ID_PATTERN, EVENT_ID_PATTERN, SHA256_PATTERN


_THREAD_LOCKS: dict[str, threading.RLock] = {}
_THREAD_LOCKS_GUARD = threading.Lock()
_LOCK_STATE = threading.local()


def validate_cycle_id(cycle_id: str) -> str:
    value = str(cycle_id or "").strip()
    if not CYCLE_ID_PATTERN.fullmatch(value):
        raise ValueError("cycle_id must be 1-128 path-safe letters, digits, dots, underscores, or hyphens")
    return value


def validate_event_id(event_id: Any) -> str:
    value = str(event_id or "").strip()
    if not EVENT_ID_PATTERN.fullmatch(value):
        raise ValueError("event_id must be a non-empty path-free token of at most 255 characters")
    return value


def rel_path(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def cycle_dir(root: Path, cycle_id: str) -> Path:
    resolved_root = root.resolve()
    cycle_root = (resolved_root / ".task" / "cycle").resolve(strict=False)
    try:
        cycle_root.relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError("cycle ledger root escapes the workspace, including through a symlink") from exc
    path = (cycle_root / validate_cycle_id(cycle_id)).resolve(strict=False)
    try:
        path.relative_to(cycle_root)
    except ValueError as exc:
        raise ValueError("cycle directory escapes .task/cycle, including through a symlink") from exc
    return path


def ledger_path(root: Path, cycle_id: str) -> Path:
    return cycle_dir(root, cycle_id) / "stage.jsonl"


def current_stage_path(root: Path, cycle_id: str) -> Path:
    return cycle_dir(root, cycle_id) / "current_stage.json"


def initialization_path(root: Path, cycle_id: str) -> Path:
    return cycle_dir(root, cycle_id) / "initialization.json"


def finalizations_dir(root: Path, cycle_id: str) -> Path:
    directory = cycle_dir(root, cycle_id)
    path = (directory / "finalizations").resolve(strict=False)
    try:
        path.relative_to(directory)
    except ValueError as exc:
        raise ValueError("finalization directory escapes its cycle directory, including through a symlink") from exc
    return path


def finalization_snapshot_path(root: Path, cycle_id: str, finalization_token: str) -> Path:
    token = str(finalization_token or "").strip().lower()
    if not SHA256_PATTERN.fullmatch(token):
        raise ValueError("finalization_token must be a full lowercase SHA-256 digest")
    return finalizations_dir(root, cycle_id) / f"{token}.json"


def current_finalization_path(root: Path, cycle_id: str) -> Path:
    return cycle_dir(root, cycle_id) / "current_finalization.json"


def read_initialization_metadata(root: Path, cycle_id: str) -> dict[str, Any]:
    path = initialization_path(root, cycle_id)
    if not path.is_file():
        raise ValueError(f"cycle `{cycle_id}` must be initialized before stage append")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"malformed cycle initialization metadata: {path}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"cycle initialization metadata must be a JSON object: {path}")
    if str(value.get("cycle_id") or "") != cycle_id:
        raise ValueError(f"cycle initialization metadata does not match cycle `{cycle_id}`")
    return value


def ledger_lock_path(root: Path, cycle_id: str) -> Path:
    return cycle_dir(root, cycle_id) / ".ledger.lock"


class StableReadRaceError(ValueError):
    """A supposedly stable read overlapped a filesystem mutation."""


def _cycle_lock_key(root: Path, cycle_id: str) -> str:
    return f"{root.resolve()}\0{validate_cycle_id(cycle_id)}"


def _cycle_thread_lock(root: Path, cycle_id: str) -> threading.RLock:
    key = _cycle_lock_key(root, cycle_id)
    with _THREAD_LOCKS_GUARD:
        return _THREAD_LOCKS.setdefault(key, threading.RLock())


def _lock_depths() -> dict[str, dict[str, int]]:
    depths = getattr(_LOCK_STATE, "depths", None)
    if depths is None:
        depths = {}
        _LOCK_STATE.depths = depths
    return depths


def _lock_depth(root: Path, cycle_id: str, mode: str) -> int:
    return _lock_depths().get(_cycle_lock_key(root, cycle_id), {}).get(mode, 0)


def _change_lock_depth(root: Path, cycle_id: str, mode: str, delta: int) -> None:
    key = _cycle_lock_key(root, cycle_id)
    depths = _lock_depths()
    state = depths.setdefault(key, {})
    updated = state.get(mode, 0) + delta
    if updated < 0:
        raise RuntimeError("cycle ledger lock depth underflow")
    if updated:
        state[mode] = updated
    else:
        state.pop(mode, None)
    if not state:
        depths.pop(key, None)


def stable_file_token(path: Path) -> tuple[int, int, int, int, int, str] | None:
    """Hash one regular file while proving its identity and metadata stayed fixed."""

    if not path.exists() and not path.is_symlink():
        return None
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    try:
        descriptor = os.open(path, flags)
    except FileNotFoundError as exc:
        raise StableReadRaceError("read-only snapshot input disappeared") from exc
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise ValueError(f"read-only snapshot input must be a regular file: {path}")
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
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
        before.st_ctime_ns,
    )
    fields_after = (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
        after.st_ctime_ns,
    )
    try:
        current = path.stat(follow_symlinks=False)
    except FileNotFoundError as exc:
        raise StableReadRaceError("read-only snapshot input disappeared") from exc
    current_fields = (
        current.st_dev,
        current.st_ino,
        current.st_size,
        current.st_mtime_ns,
        current.st_ctime_ns,
    )
    if fields_before != fields_after or fields_after != current_fields:
        raise StableReadRaceError("read-only snapshot input changed while hashing")
    return (*fields_after, digest.hexdigest())


def fsync_directory(path: Path) -> None:
    try:
        descriptor = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


@contextmanager
def ledger_lock(root: Path, cycle_id: str, *, exclusive: bool) -> Iterator[None]:
    root = root.resolve()
    cycle_id = validate_cycle_id(cycle_id)
    if not exclusive:
        with existing_ledger_read_lock(root, cycle_id) as locked:
            if locked:
                yield
                return
            lock_path = ledger_lock_path(root, cycle_id)
            try:
                yield
            finally:
                # A cooperating writer creates this persistent lock before its
                # first mutation. Do not mask an exception already raised by
                # the reader, but reject an otherwise successful racing read.
                if sys.exc_info()[0] is None and (
                    lock_path.exists() or lock_path.is_symlink()
                ):
                    raise StableReadRaceError(
                        "cycle ledger lock appeared during read-only snapshot"
                    )
        return
    directory = cycle_dir(root, cycle_id)
    with _cycle_thread_lock(root, cycle_id):
        if _lock_depth(root, cycle_id, "writer"):
            _change_lock_depth(root, cycle_id, "writer", 1)
            try:
                yield
            finally:
                _change_lock_depth(root, cycle_id, "writer", -1)
            return
        if _lock_depth(root, cycle_id, "reader"):
            raise ValueError("Cannot upgrade a cycle ledger read lock to a writer lock")
        directory.mkdir(parents=True, exist_ok=True)
        lock_path = ledger_lock_path(root, cycle_id)
        descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
        with os.fdopen(descriptor, "a+b", closefd=True) as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            _change_lock_depth(root, cycle_id, "writer", 1)
            try:
                yield
            finally:
                _change_lock_depth(root, cycle_id, "writer", -1)
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@contextmanager
def existing_ledger_read_lock(root: Path, cycle_id: str) -> Iterator[bool]:
    """Share an existing writer lock without creating directories or lock files."""

    root = root.resolve()
    cycle_id = validate_cycle_id(cycle_id)
    with _cycle_thread_lock(root, cycle_id):
        if _lock_depth(root, cycle_id, "writer") or _lock_depth(
            root, cycle_id, "reader"
        ):
            _change_lock_depth(root, cycle_id, "reader", 1)
            try:
                yield True
            finally:
                _change_lock_depth(root, cycle_id, "reader", -1)
            return
        path = ledger_lock_path(root, cycle_id)
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
                raise ValueError("cycle ledger lock must be a regular file")
            fcntl.flock(handle.fileno(), fcntl.LOCK_SH)
            _change_lock_depth(root, cycle_id, "reader", 1)
            try:
                yield True
                try:
                    current = path.stat(follow_symlinks=False)
                except FileNotFoundError as exc:
                    raise StableReadRaceError("cycle ledger lock changed during read") from exc
                if (opened.st_dev, opened.st_ino) != (current.st_dev, current.st_ino):
                    raise StableReadRaceError("cycle ledger lock changed during read")
            finally:
                _change_lock_depth(root, cycle_id, "reader", -1)
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}-{uuid.uuid4().hex}")
    try:
        with temporary.open("x", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        fsync_directory(path.parent)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def immutable_write_bytes(path: Path, content: bytes) -> bool:
    """Publish one content-addressed object and report an actual new link."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}-{uuid.uuid4().hex}")
    mutation_performed = False
    try:
        with temporary.open("xb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, path)
            fsync_directory(path.parent)
            mutation_performed = True
        except FileExistsError:
            if path.read_bytes() != content:
                raise ValueError(f"immutable finalization object already exists with different content: {path}")
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
    return mutation_performed


def durable_append_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    existed = path.exists()
    payload = (json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
    with path.open("ab") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    if not existed:
        fsync_directory(path.parent)


def load_json_value(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    if value == "-":
        raw = sys.stdin.read()
        return json.loads(raw) if raw.strip() else {}
    if value.lstrip().startswith("{"):
        return json.loads(value)
    path = Path(value)
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except OSError:
        pass
    return json.loads(value)


def normalize_list(*values: Any) -> list[str]:
    result: list[str] = []
    for value in values:
        if value is None:
            continue
        if isinstance(value, list):
            result.extend(str(item) for item in value if item is not None and str(item) != "")
        elif isinstance(value, tuple):
            result.extend(str(item) for item in value if item is not None and str(item) != "")
        elif str(value) != "":
            result.append(str(value))
    return result


def file_sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError:
        return None
    return digest.hexdigest()


def artifact_path(root: Path, artifact: str) -> Path:
    path = Path(artifact)
    return path if path.is_absolute() else root / path
