from __future__ import annotations

import datetime as dt
import fcntl
import hashlib
import json
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from typing import Iterator


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
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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
        loaded = json.loads(candidate.read_text(encoding="utf-8") if is_file else value)
    except (json.JSONDecodeError, OSError) as exc:
        raise SystemExit(f"JSON input is invalid: {exc}") from exc
    if not isinstance(loaded, dict):
        raise SystemExit("JSON input must be an object.")
    return loaded


def read_object(path: Path, label: str = "artifact") -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise SystemExit(f"{label} is not readable JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise SystemExit(f"{label} must be a JSON object.")
    return value


def write_json_atomic(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_value = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_value)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def write_immutable_json(path: Path, value: dict[str, Any], label: str) -> str:
    if path.exists():
        existing = read_object(path, label)
        if existing != value:
            raise SystemExit(f"Conflicting {label} already exists: {path}")
    else:
        write_json_atomic(path, value)
    return sha256_file(path)


@contextmanager
def authority_lock(root: Path) -> Iterator[None]:
    lock_path = root / ".task" / "authorization" / "state" / ".authority.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
