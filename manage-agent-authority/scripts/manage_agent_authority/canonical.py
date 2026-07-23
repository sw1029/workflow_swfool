from __future__ import annotations

import datetime as dt
import hashlib
import json
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from typing import Iterator

from .stable_store import atomic_replace
from .stable_store import locked_file
from .stable_store import publish_immutable
from .stable_store import read_regular


_AUTHORITY_THREAD_LOCKS: dict[str, threading.RLock] = {}
_AUTHORITY_THREAD_LOCKS_GUARD = threading.Lock()
_AUTHORITY_LOCK_STATE = threading.local()


def _authority_thread_lock(root: Path) -> threading.RLock:
    key = str(root)
    with _AUTHORITY_THREAD_LOCKS_GUARD:
        return _AUTHORITY_THREAD_LOCKS.setdefault(key, threading.RLock())


def _authority_lock_depths() -> dict[str, int]:
    depths = getattr(_AUTHORITY_LOCK_STATE, "depths", None)
    if depths is None:
        depths = {}
        _AUTHORITY_LOCK_STATE.depths = depths
    return depths


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def object_sha256(value: Any) -> str:
    return sha256_bytes(canonical_bytes(value))


def sha256_file(path: Path) -> str:
    payload = read_regular(path, label="SHA-256 source")
    assert payload is not None
    return sha256_bytes(payload)


def parse_time(value: Any, label: str) -> dt.datetime:
    raw = str(value or "").strip()
    if not raw:
        raise SystemExit(f"{label} is required.")
    try:
        parsed = dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SystemExit(f"{label} must be RFC3339-compatible.") from exc
    if parsed.tzinfo is None:
        raise SystemExit(f"{label} must include a timezone.")
    return parsed


def normalized_time(value: Any, label: str) -> str:
    return parse_time(value, label).isoformat()


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def resolve_workspace_path(
    root: Path,
    value: Any,
    label: str,
    *,
    must_exist: bool = True,
    regular_file: bool = True,
) -> Path:
    raw_value = str(value or "").strip()
    raw = Path(raw_value)
    if not raw_value or raw.is_absolute():
        raise SystemExit(f"{label} must be a workspace-relative path.")
    root = root.resolve()
    candidate = root
    for part in raw.parts:
        candidate /= part
        if candidate.is_symlink():
            raise SystemExit(f"{label} must not traverse a symlink component.")
    path = candidate.resolve(strict=False)
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise SystemExit(f"{label} escapes the workspace.") from exc
    if must_exist and (not path.is_file() if regular_file else not path.exists()):
        raise SystemExit(
            f"{label} does not identify an existing path: {raw.as_posix()}"
        )
    return path


def load_object(value: str) -> dict[str, Any]:
    try:
        candidate = Path(value)
        is_file = candidate.is_file()
    except OSError:
        is_file = False
    try:
        if is_file:
            payload = read_regular(candidate.absolute(), label="JSON input")
            assert payload is not None
            source = payload.decode("utf-8")
        else:
            source = value
        loaded = json.loads(source)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SystemExit(f"JSON input is invalid: {exc}") from exc
    if not isinstance(loaded, dict):
        raise SystemExit("JSON input must be an object.")
    return loaded


def read_object(path: Path, label: str = "artifact") -> dict[str, Any]:
    try:
        payload = read_regular(path, label=label)
        assert payload is not None
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SystemExit(f"{label} is not readable JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise SystemExit(f"{label} must be a JSON object.")
    return value


def write_json_atomic(path: Path, value: dict[str, Any]) -> None:
    payload = (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    atomic_replace(path, payload)


def write_immutable_json(path: Path, value: dict[str, Any], label: str) -> str:
    payload = (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    try:
        publish_immutable(path, payload)
    except SystemExit as exc:
        raise SystemExit(f"Conflicting {label} already exists: {path}") from exc
    return sha256_bytes(payload)


@contextmanager
def authority_lock(root: Path) -> Iterator[None]:
    root = root.resolve()
    key = str(root)
    with _authority_thread_lock(root):
        depths = _authority_lock_depths()
        if depths.get(key, 0):
            depths[key] += 1
            try:
                yield
            finally:
                depths[key] -= 1
            return
        lock_path = root / ".task" / "authorization" / "state" / ".authority.lock"
        with locked_file(lock_path):
            depths[key] = 1
            try:
                yield
            finally:
                depths.pop(key, None)
