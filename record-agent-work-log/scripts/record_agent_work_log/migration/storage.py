"""Filesystem, hashing, path, and atomic-publication primitives."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import stat
import tempfile
from typing import Any

from ..integrity import sha256_bytes, sha256_file, workspace_root
from .contracts import MigrationError


def _canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")

def _sha256_path(path: Path) -> str:
    return sha256_file(path)

def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

def _strict_fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    descriptor = os.open(path, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)

def _strict_atomic_replace(path: Path, payload: bytes, mode: int = 0o600) -> None:
    if path.exists() or path.is_symlink():
        target_mode = path.lstat().st_mode
        if stat.S_ISLNK(target_mode) or not stat.S_ISREG(target_mode):
            raise MigrationError(f"migration target is not a regular file: {path}")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    descriptor_open = True
    try:
        os.fchmod(descriptor, mode)
        with os.fdopen(descriptor, "wb") as handle:
            descriptor_open = False
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        _strict_fsync_directory(path.parent)
    except BaseException:
        if descriptor_open:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)
        raise

def _strict_publish_new(path: Path, payload: bytes, mode: int = 0o600) -> None:
    if path.exists() or path.is_symlink():
        raise MigrationError(f"migration artifact already exists: {path}")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    descriptor_open = True
    try:
        os.fchmod(descriptor, mode)
        with os.fdopen(descriptor, "wb") as handle:
            descriptor_open = False
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, path)
        temporary.unlink()
        _strict_fsync_directory(path.parent)
    except BaseException:
        if descriptor_open:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)
        raise

def _root_identity(root: Path) -> dict[str, Any]:
    resolved = workspace_root(root)
    metadata = resolved.stat()
    basis = {
        "resolved_path": str(resolved),
        "device": metadata.st_dev,
        "inode": metadata.st_ino,
    }
    return {**basis, "sha256": sha256_bytes(_canonical_json_bytes(basis))}

def _relative_or_absolute(root: Path, path: Path) -> str:
    resolved = path.expanduser().absolute().resolve(strict=False)
    try:
        return resolved.relative_to(root).as_posix()
    except ValueError:
        return str(resolved)

def _resolve_ref(root: Path, value: Any) -> Path:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise MigrationError("migration reference must be a non-empty path")
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        candidate = root / candidate
    lexical = candidate.absolute()
    if lexical.is_symlink():
        raise MigrationError(f"migration reference must not be a symlink: {value}")
    try:
        resolved = lexical.resolve(strict=True)
    except OSError as exc:
        raise MigrationError(f"migration reference is unavailable: {value}: {exc}") from exc
    if not stat.S_ISREG(resolved.lstat().st_mode):
        raise MigrationError(f"migration reference is not a regular file: {value}")
    return resolved

def _safe_migration_path(root: Path, value: Any, *, must_exist: bool = True) -> Path:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise MigrationError("migration sidecar path must be a non-empty string")
    relative = Path(value)
    if (
        relative.is_absolute()
        or value != relative.as_posix()
        or any(part in {"", ".", ".."} for part in relative.parts)
        or len(relative.parts) < 3
        or relative.parts[:2] != (".agent_log", "migrations")
    ):
        raise MigrationError(f"unsafe migration sidecar path: {value!r}")
    current = root
    for part in relative.parts:
        current /= part
        if current.exists() or current.is_symlink():
            mode = current.lstat().st_mode
            if stat.S_ISLNK(mode):
                raise MigrationError(f"migration sidecar path contains a symlink: {value}")
        elif must_exist:
            raise MigrationError(f"migration sidecar is missing: {value}")
    candidate = root / relative
    if must_exist and not stat.S_ISREG(candidate.lstat().st_mode):
        raise MigrationError(f"migration sidecar is not a regular file: {value}")
    try:
        candidate.resolve(strict=must_exist).relative_to(root)
    except (OSError, ValueError) as exc:
        raise MigrationError(f"migration sidecar escapes the workspace: {value}") from exc
    return candidate

def _index_path(root: Path) -> Path:
    return root / ".agent_log" / "index.jsonl"

def _read_index(root: Path) -> bytes:
    path = _index_path(root)
    if path.is_symlink():
        raise MigrationError(".agent_log/index.jsonl must not be a symlink")
    if not path.exists():
        return b""
    if not stat.S_ISREG(path.lstat().st_mode):
        raise MigrationError(".agent_log/index.jsonl must be a regular file")
    return path.read_bytes()
