#!/usr/bin/env python3
"""Fail-quiet Stop-hook producer for repository-local conversation projections."""

from __future__ import annotations

import argparse
import datetime as dt
import errno
import json
import os
from pathlib import Path
import re
import secrets
import stat
import sys
from typing import Any


MAX_HOOK_BYTES = 64 * 1024
MAX_TRANSCRIPT_BYTES = 10 * 1024 * 1024
MAX_TRANSCRIPT_LINES = 10_000
TOOLS = {"codex", "claude-code"}
SAFE_SESSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
BLOCKED_USER_PREFIXES = (
    "<permissions",
    "<environment_context",
    "<user_instructions",
    "<skill",
    "<developer",
    "<system",
)
NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
CLOEXEC = getattr(os, "O_CLOEXEC", 0)
DIRECTORY = getattr(os, "O_DIRECTORY", 0)


class CaptureError(ValueError):
    """A privacy-safe capture failure that must not block the agent session."""


class DuplicateKeyError(ValueError):
    pass


def strict_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateKeyError("duplicate JSON key")
        result[key] = value
    return result


def absolute_path(raw: Any, *, label: str) -> Path:
    if not isinstance(raw, str) or not raw:
        raise CaptureError(f"{label} must be a non-empty absolute path")
    candidate = Path(raw).expanduser()
    if not candidate.is_absolute() or ".." in candidate.parts:
        raise CaptureError(f"{label} must be an absolute path without traversal")
    return candidate


def open_directory_nofollow(path: Path) -> int:
    """Open an absolute directory by descriptor without following any symlink."""

    if not path.is_absolute() or ".." in path.parts:
        raise CaptureError("directory path must be absolute without traversal")
    current = os.open("/", os.O_RDONLY | DIRECTORY | CLOEXEC)
    try:
        for part in path.parts[1:]:
            if part in {"", ".", ".."}:
                raise CaptureError("unsafe directory path component")
            try:
                child = os.open(
                    part,
                    os.O_RDONLY | DIRECTORY | NOFOLLOW | CLOEXEC,
                    dir_fd=current,
                )
            except OSError as exc:
                raise CaptureError("directory is unavailable or contains a symlink") from exc
            os.close(current)
            current = child
        if not stat.S_ISDIR(os.fstat(current).st_mode):
            raise CaptureError("path must name a directory")
        result = current
        current = -1
        return result
    finally:
        if current >= 0:
            os.close(current)


def open_regular_nofollow(path: Path) -> int:
    """Open an absolute regular file without following any path component."""

    if path.name in {"", ".", ".."}:
        raise CaptureError("transcript path must name a file")
    parent_fd = open_directory_nofollow(path.parent)
    try:
        try:
            fd = os.open(
                path.name,
                os.O_RDONLY | NOFOLLOW | CLOEXEC,
                dir_fd=parent_fd,
            )
        except OSError as exc:
            raise CaptureError("transcript is unavailable or is a symlink") from exc
    finally:
        os.close(parent_fd)
    if not stat.S_ISREG(os.fstat(fd).st_mode):
        os.close(fd)
        raise CaptureError("transcript must be a regular file")
    return fd


def read_bounded_transcript(path: Path) -> bytes:
    fd = open_regular_nofollow(path)
    try:
        before = os.fstat(fd)
        if before.st_size > MAX_TRANSCRIPT_BYTES:
            raise CaptureError("transcript exceeds the bounded capture size")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(fd, min(64 * 1024, MAX_TRANSCRIPT_BYTES + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > MAX_TRANSCRIPT_BYTES:
                raise CaptureError("transcript exceeds the bounded capture size")
        after = os.fstat(fd)
        identity = lambda value: (  # noqa: E731 - compact immutable snapshot
            value.st_dev,
            value.st_ino,
            value.st_size,
            value.st_mtime_ns,
        )
        if identity(before) != identity(after):
            raise CaptureError("transcript changed during capture")
        return b"".join(chunks)
    finally:
        os.close(fd)


def parse_transcript(data: bytes) -> list[dict[str, Any]]:
    try:
        text = data.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise CaptureError("transcript is not strict UTF-8") from exc
    lines = text.splitlines()
    if len(lines) > MAX_TRANSCRIPT_LINES:
        raise CaptureError("transcript exceeds the bounded JSONL line count")
    if not lines:
        raise CaptureError("transcript contains no JSONL events")
    events: list[dict[str, Any]] = []
    for line in lines:
        if not line.strip():
            raise CaptureError("transcript contains a blank JSONL line")
        try:
            event = json.loads(line, object_pairs_hook=strict_json_object)
        except (json.JSONDecodeError, DuplicateKeyError) as exc:
            raise CaptureError("transcript contains malformed JSONL") from exc
        if not isinstance(event, dict):
            raise CaptureError("transcript contains a non-object JSONL event")
        schema_version = event.get("schema_version", 1)
        if isinstance(schema_version, bool) or schema_version not in (1, "1"):
            raise CaptureError("transcript declares an unsupported schema version")
        events.append(event)
    return events


def normalize_timestamp(value: Any) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    candidate = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = dt.datetime.fromisoformat(candidate)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return (
        parsed.astimezone(dt.timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def conversation_text(content: Any, text_types: set[str]) -> str | None:
    if isinstance(content, str):
        text = content.strip()
        return text or None
    if not isinstance(content, list):
        return None
    parts: list[str] = []
    for block in content:
        if (
            isinstance(block, dict)
            and block.get("type") in text_types
            and isinstance(block.get("text"), str)
            and block["text"].strip()
        ):
            parts.append(block["text"].strip())
    return "\n".join(parts) if parts else None


def with_timestamp(event: dict[str, Any], normalized: dict[str, Any]) -> dict[str, Any]:
    timestamp = normalize_timestamp(event.get("timestamp"))
    if timestamp is not None:
        normalized["timestamp"] = timestamp
    return normalized


def blocked_user_text(role: str, text: str) -> bool:
    return role == "user" and text.lstrip().lower().startswith(BLOCKED_USER_PREFIXES)


def codex_event_message(event: dict[str, Any]) -> dict[str, Any] | None:
    if event.get("type") != "event_msg" or not set(event) <= {
        "timestamp", "type", "payload", "schema_version"
    }:
        return None
    payload = event.get("payload")
    if not isinstance(payload, dict) or payload.get("type") not in {
        "user_message", "agent_message"
    }:
        return None
    allowed = (
        {"type", "message", "images", "local_images", "text_elements"}
        if payload["type"] == "user_message"
        else {"type", "message", "phase", "memory_citation"}
    )
    if not set(payload) <= allowed:
        return None
    text = payload.get("message")
    if not isinstance(text, str) or not text.strip():
        return None
    role = "user" if payload["type"] == "user_message" else "assistant"
    text = text.strip()
    if blocked_user_text(role, text):
        return None
    return with_timestamp(
        event,
        {
            "schema_version": 1,
            "type": "event_msg",
            "payload": {
                "type": "user_message" if role == "user" else "agent_message",
                "message": text,
            },
        },
    )


def codex_response_message(event: dict[str, Any]) -> dict[str, Any] | None:
    if event.get("type") != "response_item" or not set(event) <= {
        "timestamp", "type", "payload", "schema_version"
    }:
        return None
    payload = event.get("payload")
    if not isinstance(payload, dict) or payload.get("role") not in {"user", "assistant"}:
        return None
    if not set(payload) <= {"type", "role", "content", "phase", "id", "status"}:
        return None
    role = payload["role"]
    text = conversation_text(payload.get("content"), {"input_text", "output_text", "text"})
    if text is None or blocked_user_text(role, text):
        return None
    block_type = "input_text" if role == "user" else "output_text"
    return with_timestamp(
        event,
        {
            "schema_version": 1,
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": role,
                "content": [{"type": block_type, "text": text}],
            },
        },
    )


def claude_message(event: dict[str, Any]) -> dict[str, Any] | None:
    role = event.get("type")
    if role not in {"user", "assistant"}:
        return None
    allowed_event_keys = {
        "parentUuid", "isSidechain", "userType", "cwd", "sessionId",
        "version", "gitBranch", "type", "message", "uuid", "timestamp",
        "isMeta", "isVisibleInTranscript", "requestId", "agentId",
        "schema_version",
    }
    if not set(event) <= allowed_event_keys or event.get("isMeta") is True:
        return None
    message = event.get("message")
    allowed_message_keys = {
        "role", "content", "model", "id", "type", "stop_reason",
        "stop_sequence", "usage", "context_management",
    }
    if (
        not isinstance(message, dict)
        or not set(message) <= allowed_message_keys
        or message.get("role") != role
    ):
        return None
    text = conversation_text(message.get("content"), {"text"})
    if text is None or blocked_user_text(role, text):
        return None
    return with_timestamp(
        event,
        {
            "schema_version": 1,
            "type": role,
            "message": {
                "role": role,
                "content": [{"type": "text", "text": text}],
            },
        },
    )


def normalize_projection(data: bytes, tool: str) -> bytes:
    events = parse_transcript(data)
    if tool == "codex":
        primary = [item for event in events if (item := codex_event_message(event))]
        projected = primary or [
            item for event in events if (item := codex_response_message(event))
        ]
    elif tool == "claude-code":
        projected = [item for event in events if (item := claude_message(event))]
    else:
        raise CaptureError("tool must be codex or claude-code")
    if not projected:
        raise CaptureError("transcript contains no supported conversation events")
    return b"".join(
        (
            json.dumps(item, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
            + "\n"
        ).encode("utf-8")
        for item in projected
    )


def ensure_child_directory(parent_fd: int, name: str) -> int:
    if not SAFE_SESSION.fullmatch(name):
        raise CaptureError("unsafe output directory name")
    flags = os.O_RDONLY | DIRECTORY | NOFOLLOW | CLOEXEC
    try:
        return os.open(name, flags, dir_fd=parent_fd)
    except OSError as exc:
        if exc.errno != errno.ENOENT:
            raise CaptureError("output directory is unsafe") from exc
    try:
        os.mkdir(name, mode=0o700, dir_fd=parent_fd)
    except FileExistsError:
        pass
    try:
        child = os.open(name, flags, dir_fd=parent_fd)
    except OSError as exc:
        raise CaptureError("output directory is unsafe") from exc
    if not stat.S_ISDIR(os.fstat(child).st_mode):
        os.close(child)
        raise CaptureError("output path component must be a directory")
    return child


def atomic_overwrite(directory_fd: int, filename: str, data: bytes) -> None:
    try:
        existing = os.stat(filename, dir_fd=directory_fd, follow_symlinks=False)
    except FileNotFoundError:
        existing = None
    if existing is not None and not stat.S_ISREG(existing.st_mode):
        raise CaptureError("projection destination is unsafe")
    temporary = f".{filename}.{os.getpid()}.{secrets.token_hex(8)}.tmp"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | NOFOLLOW | CLOEXEC
    fd = -1
    try:
        fd = os.open(temporary, flags, 0o600, dir_fd=directory_fd)
        view = memoryview(data)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                raise CaptureError("projection write did not make progress")
            view = view[written:]
        os.fsync(fd)
        os.close(fd)
        fd = -1
        os.replace(
            temporary,
            filename,
            src_dir_fd=directory_fd,
            dst_dir_fd=directory_fd,
        )
        os.fsync(directory_fd)
    finally:
        if fd >= 0:
            os.close(fd)
        try:
            os.unlink(temporary, dir_fd=directory_fd)
        except FileNotFoundError:
            pass


def capture(root: Path, tool: str, payload: dict[str, Any]) -> Path:
    if tool not in TOOLS:
        raise CaptureError("tool must be codex or claude-code")
    session_id = payload.get("session_id")
    if not isinstance(session_id, str) or not SAFE_SESSION.fullmatch(session_id):
        raise CaptureError("session_id is missing or unsafe")
    transcript = absolute_path(payload.get("transcript_path"), label="transcript_path")
    projection = normalize_projection(read_bounded_transcript(transcript), tool)

    root_fd = open_directory_nofollow(root)
    logs_fd = tool_fd = -1
    try:
        logs_fd = ensure_child_directory(root_fd, "logs")
        tool_fd = ensure_child_directory(logs_fd, tool)
        atomic_overwrite(tool_fd, f"{session_id}.jsonl", projection)
    finally:
        if tool_fd >= 0:
            os.close(tool_fd)
        if logs_fd >= 0:
            os.close(logs_fd)
        os.close(root_fd)
    return root / "logs" / tool / f"{session_id}.jsonl"


def read_hook_payload() -> dict[str, Any]:
    raw = sys.stdin.buffer.read(MAX_HOOK_BYTES + 1)
    if len(raw) > MAX_HOOK_BYTES:
        raise CaptureError("Stop-hook input exceeds the bounded payload size")
    try:
        payload = json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=strict_json_object,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, DuplicateKeyError) as exc:
        raise CaptureError("Stop-hook input is not strict JSON") from exc
    if not isinstance(payload, dict):
        raise CaptureError("Stop-hook input must be a JSON object")
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Capture a body-minimized repository-local conversation projection."
    )
    parser.add_argument("--root", required=True, help="absolute repository root")
    parser.add_argument("--tool", required=True, choices=sorted(TOOLS))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        root = absolute_path(args.root, label="repository root")
        payload = read_hook_payload()
        capture(root, args.tool, payload)
    except CaptureError as exc:
        print(f"capture_projection: {exc}", file=sys.stderr)
    except Exception as exc:  # noqa: BLE001 - Stop-hook logging must fail quiet
        print(
            f"capture_projection: unexpected logging failure ({type(exc).__name__})",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
