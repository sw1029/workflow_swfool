#!/usr/bin/env python3
"""Write a standardized agent work log entry under .agent_log."""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
import subprocess
import stat
import sys
import tempfile
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterator, List


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from agent_log_integrity import (  # noqa: E402
    AgentLogIntegrityError,
    LOG_FORMAT_VERSION,
    LOG_SCHEMA_VERSION,
    LOG_STATUSES,
    content_id_for,
    ensure_log_root,
    ensure_safe_directory,
    expected_record_id,
    parse_index,
    sha256_bytes,
    validate_store_for_append,
    workspace_root,
)

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows fallback keeps thread safety only.
    fcntl = None  # type: ignore[assignment]


SENSITIVITY_CLASSES = ("confidential", "internal", "public", "restricted", "unspecified")

_THREAD_LOCKS: dict[str, threading.RLock] = {}
_THREAD_LOCKS_GUARD = threading.Lock()


def slugify(value: str, fallback: str = "agent-log") -> str:
    text = value.strip().lower()
    text = re.sub(r"[^a-z0-9가-힣._-]+", "-", text)
    text = re.sub(r"-{2,}", "-", text).strip("-._")
    return text[:80] or fallback


def git_value(root: Path, args: List[str]) -> str:
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), *args],
            check=False,
            text=True,
            capture_output=True,
            timeout=5,
        )
    except Exception:
        return ""
    if proc.returncode != 0:
        return ""
    return proc.stdout.strip()


def list_values(items: List[str]) -> str:
    if not items:
        return "- None"
    return "\n".join(f"- {item}" for item in items)


def paragraph(value: str) -> str:
    return value.strip() or "Not specified"


def non_blank(value: str) -> str:
    if not value.strip():
        raise argparse.ArgumentTypeError("value must not be empty")
    return value


def _thread_lock(root: Path) -> threading.RLock:
    key = str(root.resolve())
    with _THREAD_LOCKS_GUARD:
        return _THREAD_LOCKS.setdefault(key, threading.RLock())


@contextlib.contextmanager
def log_lock(root: Path) -> Iterator[None]:
    root = workspace_root(root)
    log_root = ensure_log_root(root, create=True)
    with _thread_lock(root):
        lock_path = log_root / "index.lock"
        if lock_path.exists() or lock_path.is_symlink():
            mode = lock_path.lstat().st_mode
            if stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
                raise AgentLogIntegrityError("agent-log index lock must be a regular non-symlink file")
        flags = os.O_CREAT | os.O_RDWR
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(lock_path, flags, 0o600)
        with os.fdopen(descriptor, "a+b", closefd=True) as handle:
            if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
                raise AgentLogIntegrityError("agent-log index lock must be a regular file")
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


def atomic_replace(path: Path, payload: bytes, mode: int = 0o600) -> None:
    if path.exists() or path.is_symlink():
        target_mode = path.lstat().st_mode
        if stat.S_ISLNK(target_mode) or not stat.S_ISREG(target_mode):
            raise AgentLogIntegrityError("agent-log index target must be a regular non-symlink file")
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


def publish_new(path: Path, payload: bytes, mode: int = 0o600) -> None:
    if path.exists() or path.is_symlink():
        raise AgentLogIntegrityError("agent-log output already exists or is unsafe")
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, mode)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, path)
        _fsync_directory(path.parent)
    finally:
        try:
            os.close(descriptor)
        except OSError:
            pass
        temporary.unlink(missing_ok=True)


def validate_index(payload: bytes, path: Path) -> None:
    parse_index(payload, path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create a .agent_log entry and append index.jsonl.")
    parser.add_argument("--root", default=".", help="Workspace/repository root.")
    parser.add_argument("--title", default="", help="Short entry title.")
    parser.add_argument("--status", required=True, choices=LOG_STATUSES, help="Explicit evidence-backed lifecycle status.")
    parser.add_argument("--intent", required=True, type=non_blank, help="Task intent.")
    parser.add_argument("--work", required=True, type=non_blank, help="Work performed.")
    parser.add_argument("--result", required=True, type=non_blank, help="Result.")
    parser.add_argument("--shortcomings", required=True, type=non_blank, help="Shortcomings, gaps, or None identified.")
    parser.add_argument("--agent-note", action="append", default=[], help="Normalization agent note. Repeatable.")
    parser.add_argument("--command", action="append", default=[], help="Command or validation run. Repeatable.")
    parser.add_argument("--changed-file", action="append", default=[], help="Changed file path. Repeatable.")
    parser.add_argument("--follow-up", action="append", default=[], help="Follow-up action. Repeatable.")
    parser.add_argument("--tag", action="append", default=[], help="Short tag. Repeatable.")
    parser.add_argument("--retention-class", default="unspecified", help="Opaque retention-policy class; does not imply deletion.")
    parser.add_argument("--archive-reference", help="Optional archive manifest or evidence reference.")
    parser.add_argument("--retention-exclusion-reason", help="Why normal retention handling does not apply.")
    parser.add_argument("--sensitivity", choices=SENSITIVITY_CLASSES, default="unspecified", help="Record sensitivity classification.")
    parser.add_argument("--actor", default=os.environ.get("USER", "codex"), help="Actor name.")
    return parser


def validate_args(args: argparse.Namespace) -> None:
    if args.status not in LOG_STATUSES:
        raise ValueError(f"Unsupported work-log status: {args.status!r}")
    if args.sensitivity not in SENSITIVITY_CLASSES:
        raise ValueError(f"Unsupported sensitivity class: {args.sensitivity!r}")
    for field in ("intent", "work", "result", "shortcomings"):
        value = getattr(args, field, None)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"Work-log field {field!r} must be explicitly non-empty")


def write_log(args: argparse.Namespace) -> dict[str, Any]:
    validate_args(args)

    root = workspace_root(args.root)
    now = datetime.now().astimezone()
    date = now.strftime("%Y-%m-%d")
    time_part = now.strftime("%H%M%S%f")
    title = args.title.strip() or args.intent.strip().splitlines()[0][:80] or "Agent work log"
    slug = slugify(title)
    branch = git_value(root, ["branch", "--show-current"])
    commit = git_value(root, ["rev-parse", "--short", "HEAD"])
    index_path = root / ".agent_log" / "index.jsonl"

    with log_lock(root):
        if index_path.exists() or index_path.is_symlink():
            mode = index_path.lstat().st_mode
            if stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
                raise AgentLogIntegrityError("agent-log index must be a regular non-symlink file")
        current_index = index_path.read_bytes() if index_path.exists() else b""
        validate_store_for_append(root, current_index, index_path)
        token = uuid.uuid4().hex[:16]
        log_id = f"log-{now.strftime('%Y%m%d-%H%M%S%f')}-{token}"
        log_dir = ensure_safe_directory(root, Path(".agent_log") / date, create=True)
        path = log_dir / f"{time_part}-{slug}-{token}.md"
        rel_path = path.relative_to(root)
        content = f"""# {title}

- Log ID: {log_id}
- Timestamp: {now.isoformat()}
- Status: {args.status}
- Workspace: {root}
- Actor: {args.actor}
- Git branch: {branch or "N/A"}
- Git commit: {commit or "N/A"}
- Retention class: {args.retention_class}
- Archive reference: {args.archive_reference or "N/A"}
- Retention exclusion reason: {args.retention_exclusion_reason or "N/A"}
- Sensitivity: {args.sensitivity}

## Task Intent

{paragraph(args.intent)}

## Work Performed

{paragraph(args.work)}

## Result

{paragraph(args.result)}

## Shortcomings

{paragraph(args.shortcomings)}

## Commands / Validation

{list_values(args.command)}

## Changed Files

{list_values(args.changed_file)}

## Agent Notes

{list_values(args.agent_note)}

## Follow-ups

{list_values(args.follow_up)}

## Tags

{list_values(args.tag)}
"""
        content_bytes = content.encode("utf-8")
        body_sha256 = sha256_bytes(content_bytes)
        record: Dict[str, Any] = {
            "format_version": LOG_FORMAT_VERSION,
            "schema_version": LOG_SCHEMA_VERSION,
            "log_id": log_id,
            "body_sha256": body_sha256,
            "content_id": content_id_for(body_sha256),
            "timestamp": now.isoformat(),
            "status": args.status,
            "title": title,
            "path": str(rel_path),
            "workspace": str(root),
            "actor": args.actor,
            "git_branch": branch or None,
            "git_commit": commit or None,
            "task_intent": args.intent,
            "work_performed": args.work,
            "result": args.result,
            "shortcomings": args.shortcomings,
            "commands": args.command,
            "changed_files": args.changed_file,
            "agent_notes": args.agent_note,
            "follow_ups": args.follow_up,
            "tags": args.tag,
            "retention_class": args.retention_class,
            "archive_reference": args.archive_reference,
            "retention_exclusion_reason": args.retention_exclusion_reason,
            "sensitivity": args.sensitivity,
        }
        record["record_id"] = expected_record_id(record)
        publish_new(path, content_bytes)
        try:
            payload = current_index
            if payload and not payload.endswith(b"\n"):
                payload += b"\n"
            payload += (json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
            atomic_replace(index_path, payload)
        except BaseException:
            path.unlink(missing_ok=True)
            raise
    return {
        "format_version": LOG_FORMAT_VERSION,
        "schema_version": LOG_SCHEMA_VERSION,
        "log_id": log_id,
        "content_id": record["content_id"],
        "record_id": record["record_id"],
        "path": str(path),
        "index": str(index_path),
    }


def main(argv: List[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = write_log(args)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
