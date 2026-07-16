from __future__ import annotations

import fcntl
import hashlib
import json
import os
import sys
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from .constants import CYCLE_ID_PATTERN, EVENT_ID_PATTERN, SHA256_PATTERN


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
    directory = cycle_dir(root, cycle_id)
    directory.mkdir(parents=True, exist_ok=True)
    lock_path = ledger_lock_path(root, cycle_id)
    descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    with os.fdopen(descriptor, "a+b", closefd=True) as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
        try:
            yield
        finally:
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


def immutable_write_bytes(path: Path, content: bytes) -> None:
    """Publish one content-addressed object without replacing an existing object."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}-{uuid.uuid4().hex}")
    try:
        with temporary.open("xb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, path)
            fsync_directory(path.parent)
        except FileExistsError:
            if path.read_bytes() != content:
                raise ValueError(f"immutable finalization object already exists with different content: {path}")
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


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
