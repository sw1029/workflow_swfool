"""Identity, hashing, workspace, and safe-path primitives."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import stat
from typing import Any

from .contracts import AgentLogIntegrityError


def canonical_record_bytes(record: dict[str, Any]) -> bytes:
    payload = {key: value for key, value in record.items() if key != "record_id"}
    return (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")

def expected_record_id(record: dict[str, Any]) -> str:
    return (
        "log-record-" + hashlib.sha256(canonical_record_bytes(record)).hexdigest()[:32]
    )

def content_id_for(body_sha256: str) -> str:
    return f"log-content-{body_sha256[:32]}"

def expected_content_id(record: dict[str, Any]) -> str:
    body_sha256 = record.get("body_sha256")
    if not isinstance(body_sha256, str):
        return ""
    if record.get("content_id_scheme") is not None:
        return ""
    return content_id_for(body_sha256)

def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()

def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

def workspace_root(raw: str | Path) -> Path:
    lexical = Path(raw).expanduser().absolute()
    if lexical.is_symlink():
        raise AgentLogIntegrityError("workspace root must not be a symlink")
    try:
        root = lexical.resolve(strict=True)
    except OSError as exc:
        raise AgentLogIntegrityError(f"workspace root is unavailable: {exc}") from exc
    if not root.is_dir():
        raise AgentLogIntegrityError("workspace root must be a directory")
    return root

def _safe_relative_path(value: Any) -> Path | None:
    if not isinstance(value, str) or not value or "\x00" in value:
        return None
    path = Path(value)
    if (
        path.is_absolute()
        or value != path.as_posix()
        or any(part in {"", ".", ".."} for part in path.parts)
        or len(path.parts) < 3
        or path.parts[0] != ".agent_log"
        or path.suffix.lower() != ".md"
    ):
        return None
    return path

def _directory_projection(root: Path, log_root: Path) -> dict[str, Any]:
    projection: dict[str, Any] = {
        "path": ".agent_log",
        "exists": log_root.exists() or log_root.is_symlink(),
        "is_file": False,
        "is_dir": False,
        "is_symlink": log_root.is_symlink(),
    }
    if not projection["exists"] or projection["is_symlink"]:
        return projection
    try:
        mode = log_root.lstat().st_mode
        projection["is_file"] = stat.S_ISREG(mode)
        projection["is_dir"] = stat.S_ISDIR(mode)
        projection["size_bytes"] = log_root.lstat().st_size
    except OSError:
        pass
    return projection

def ensure_log_root(root: Path, *, create: bool) -> Path:
    root = workspace_root(root)
    log_root = root / ".agent_log"
    if log_root.exists() or log_root.is_symlink():
        mode = log_root.lstat().st_mode
        if stat.S_ISLNK(mode):
            raise AgentLogIntegrityError(".agent_log must not be a symlink")
        if not stat.S_ISDIR(mode):
            raise AgentLogIntegrityError(
                ".agent_log must be a workspace-local directory"
            )
    elif create:
        try:
            log_root.mkdir(mode=0o700)
        except FileExistsError:
            mode = log_root.lstat().st_mode
            if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
                raise AgentLogIntegrityError(
                    ".agent_log must be a workspace-local non-symlink directory"
                )
    return log_root

def ensure_safe_directory(root: Path, relative: Path, *, create: bool) -> Path:
    root = workspace_root(root)
    if relative.is_absolute() or any(
        part in {"", ".", ".."} for part in relative.parts
    ):
        raise AgentLogIntegrityError(
            "agent-log directory path must stay inside the workspace"
        )
    current = root
    for part in relative.parts:
        current /= part
        if current.exists() or current.is_symlink():
            mode = current.lstat().st_mode
            if stat.S_ISLNK(mode):
                raise AgentLogIntegrityError(
                    f"agent-log path component is a symlink: {current}"
                )
            if not stat.S_ISDIR(mode):
                raise AgentLogIntegrityError(
                    f"agent-log path component is not a directory: {current}"
                )
        elif create:
            try:
                current.mkdir(mode=0o700)
            except FileExistsError:
                mode = current.lstat().st_mode
                if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
                    raise AgentLogIntegrityError(
                        f"agent-log path component is not a safe directory: {current}"
                    )
        else:
            break
    try:
        current.resolve(strict=False).relative_to(root)
    except ValueError as exc:
        raise AgentLogIntegrityError(
            "agent-log directory escapes the workspace"
        ) from exc
    return current

def safe_log_file(root: Path, value: Any, *, must_exist: bool) -> Path:
    root = workspace_root(root)
    relative = _safe_relative_path(value)
    if relative is None:
        raise AgentLogIntegrityError(f"unsafe agent-log Markdown path: {value!r}")
    candidate = root / relative
    current = root
    for part in relative.parts:
        current /= part
        if not (current.exists() or current.is_symlink()):
            if must_exist:
                raise AgentLogIntegrityError(
                    f"indexed agent-log Markdown is missing: {value}"
                )
            break
        mode = current.lstat().st_mode
        if stat.S_ISLNK(mode):
            raise AgentLogIntegrityError(
                f"agent-log path component is a symlink: {value}"
            )
    try:
        candidate.resolve(strict=must_exist).relative_to(root)
    except (OSError, ValueError) as exc:
        raise AgentLogIntegrityError(
            f"agent-log path escapes the workspace: {value}"
        ) from exc
    if must_exist and not stat.S_ISREG(candidate.lstat().st_mode):
        raise AgentLogIntegrityError(
            f"indexed agent-log path is not a regular file: {value}"
        )
    return candidate
