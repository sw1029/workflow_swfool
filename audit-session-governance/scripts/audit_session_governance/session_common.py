"""Session-audit contracts and safe storage primitives."""

from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile
from typing import Any, Iterator

VERSION = 1
KIND = "session_governance_audit"
PARSER_VERSION = "session-audit/1"
MAX_BYTES = 10 * 1024 * 1024
MAX_ALLOWED_BYTES = 100 * 1024 * 1024
MAX_LINES = 10_000
TOOLS = {"codex", "claude-code"}
SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
SHA = re.compile(r"^[0-9a-f]{64}$")
AUDIT_ID = re.compile(r"^audit-[0-9a-f]{32}$")
TOP_KEYS = {
    "format_version", "artifact_kind", "parser_version", "audit_id", "tool",
    "session_id", "source", "capture_mode", "capture_status",
    "integrity_status", "binding", "consumable", "not_goal_truth",
    "not_validation_evidence", "repair_class", "auto_repair_allowed",
    "findings", "event_counts", "timestamp_bounds", "evidence_paths",
}
COUNT_KEYS = {
    "total_lines", "recognized_events", "unrecognized_events",
    "malformed_events", "blank_lines", "user_events", "assistant_events",
    "codex_events", "claude_code_events", "missing_timestamps",
    "tool_or_raw_events",
}
FINDINGS: dict[str, tuple[str, str, str]] = {
    "source_too_large": (
        "block", "transcript_observation",
        "Source exceeds the bounded inspection size.",
    ),
    "source_too_many_lines": (
        "block", "transcript_observation",
        "Source exceeds the bounded JSONL line count.",
    ),
    "invalid_utf8": (
        "block", "transcript_observation", "Source is not strict UTF-8.",
    ),
    "malformed_jsonl": (
        "block", "transcript_observation", "A source line is not valid JSON.",
    ),
    "blank_jsonl_line": (
        "warn", "transcript_observation", "A blank JSONL line was observed.",
    ),
    "non_object_event": (
        "block", "transcript_observation", "A JSONL event is not an object.",
    ),
    "unsupported_schema": (
        "block", "transcript_observation",
        "An event declares an unsupported schema version.",
    ),
    "raw_or_tool_event": (
        "block", "transcript_observation",
        "A raw, tool, reasoning, or metadata event was observed.",
    ),
    "unrecognized_event": (
        "block", "transcript_observation",
        "An event is outside the conversation projection allowlist.",
    ),
    "mixed_tool_schemas": (
        "block", "transcript_observation",
        "Events from multiple tool schemas were observed.",
    ),
    "declared_tool_mismatch": (
        "block", "transcript_observation",
        "Recognized events do not match the declared tool.",
    ),
    "missing_timestamp": (
        "warn", "absence_unknown",
        "A recognized event has no valid timestamp observation.",
    ),
    "empty_projection": (
        "warn", "absence_unknown",
        "No supported conversation event was observed.",
    ),
    "ambiguous_binding": (
        "warn", "absence_unknown",
        "Cycle and task binding must be supplied together.",
    ),
}


class AuditError(ValueError):
    pass


class DuplicateKeyError(ValueError):
    pass


def canonical(value: Any) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        + "\n"
    ).encode("utf-8")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def derived_id(prefix: str, value: Any) -> str:
    return f"{prefix}-{digest(canonical(value))[:32]}"


def root_path(raw: str | Path) -> Path:
    lexical = Path(raw).expanduser().absolute()
    if lexical.is_symlink():
        raise AuditError("repository root must not be a symlink")
    try:
        root = lexical.resolve(strict=True)
    except OSError as exc:
        raise AuditError(f"repository root is unavailable: {exc}") from exc
    if not root.is_dir():
        raise AuditError("repository root must be a directory")
    return root


def safe_file(
    root: Path, raw: str | Path, *, packet: bool = False
) -> tuple[Path, Path]:
    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        candidate = root / candidate
    lexical = candidate.absolute()
    try:
        relative = lexical.relative_to(root)
    except ValueError as exc:
        raise AuditError("path must stay inside repository root") from exc
    if ".." in relative.parts:
        raise AuditError("path traversal is not allowed")
    current = root
    for part in relative.parts:
        current /= part
        try:
            mode = current.lstat().st_mode
        except OSError as exc:
            raise AuditError(f"path is unavailable: {relative.as_posix()}") from exc
        if stat.S_ISLNK(mode):
            raise AuditError("symlink path components are not allowed")
    try:
        resolved = lexical.resolve(strict=True)
        resolved_relative = resolved.relative_to(root)
    except (OSError, ValueError) as exc:
        raise AuditError("resolved path must stay inside repository root") from exc
    if not stat.S_ISREG(resolved.lstat().st_mode):
        raise AuditError("path must name a regular file")
    audit_parent = Path(".task/session_audit")
    if packet:
        if resolved_relative.parent != audit_parent or resolved_relative.suffix != ".json":
            raise AuditError("packet must be directly under .task/session_audit")
    elif resolved_relative == audit_parent or audit_parent in resolved_relative.parents:
        raise AuditError("source must not be inside session-audit output")
    return resolved, resolved_relative


def audit_dir(root: Path) -> Path:
    current = root
    for part in (".task", "session_audit"):
        current /= part
        if current.exists() or current.is_symlink():
            mode = current.lstat().st_mode
            if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
                raise AuditError("session-audit output path is unsafe")
        else:
            current.mkdir(mode=0o700)
    return current


@contextlib.contextmanager
def locked(directory: Path, key: str) -> Iterator[None]:
    lock_dir = directory / ".locks"
    if lock_dir.exists() or lock_dir.is_symlink():
        mode = lock_dir.lstat().st_mode
        if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
            raise AuditError("session-audit lock directory is unsafe")
    else:
        lock_dir.mkdir(mode=0o700)
    lock_path = lock_dir / f"{digest(key.encode('utf-8'))}.lock"
    flags = os.O_CREAT | os.O_RDWR
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(lock_path, flags, 0o600)
    except OSError as exc:
        raise AuditError(f"cannot open audit lock: {exc}") from exc
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise AuditError("audit lock must be a regular file")
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)


def atomic_write(path: Path, data: bytes, *, immutable: bool = False) -> None:
    if path.exists() or path.is_symlink():
        mode = path.lstat().st_mode
        if stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
            raise AuditError("audit output target is unsafe")
        if immutable:
            if path.read_bytes() == data:
                return
            raise AuditError("content-addressed audit output already has conflicting bytes")
    fd, temp_name = tempfile.mkstemp(prefix=".session-audit-", dir=path.parent)
    temp = Path(temp_name)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if temp.exists():
            temp.unlink()


def read_snapshot(path: Path, limit: int) -> tuple[bytes | None, str, int]:
    before = path.stat()
    hasher = hashlib.sha256()
    chunks: list[bytes] | None = []
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
            if chunks is not None:
                if sum(map(len, chunks)) + len(chunk) <= limit:
                    chunks.append(chunk)
                else:
                    chunks = None
    after = path.stat()
    def identity(value: os.stat_result) -> tuple[int, int, int, int]:
        return value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns
    if identity(before) != identity(after):
        raise AuditError("source changed during inspection")
    return (
        b"".join(chunks) if chunks is not None else None,
        hasher.hexdigest(),
        after.st_size,
    )
