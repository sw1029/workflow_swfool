"""Strict index parsing and store traversal."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .contracts import AgentLogIntegrityError, LOG_FORMAT_VERSION, LOG_SCHEMA_VERSION, LOG_STATUSES
from .core import _safe_relative_path


def _parse_index(payload: bytes, path: Path) -> list[dict[str, Any]]:
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise AgentLogIntegrityError(
            f"Malformed agent-log index {path}: invalid UTF-8"
        ) from exc
    records: list[dict[str, Any]] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise AgentLogIntegrityError(
                f"Malformed agent-log index {path} line {line_no}: {exc}"
            ) from exc
        if not isinstance(record, dict):
            raise AgentLogIntegrityError(
                f"Malformed agent-log index {path} line {line_no}: expected a JSON object"
            )
        for field in ("timestamp", "status", "path"):
            if not isinstance(record.get(field), str) or not record[field].strip():
                raise AgentLogIntegrityError(
                    f"Malformed agent-log index {path} line {line_no}: missing non-empty {field}"
                )
        if record["status"] not in LOG_STATUSES:
            raise AgentLogIntegrityError(
                f"Malformed agent-log index {path} line {line_no}: unsupported status {record['status']!r}"
            )
        for field, current in (
            ("format_version", LOG_FORMAT_VERSION),
            ("schema_version", LOG_SCHEMA_VERSION),
        ):
            value = record.get(field, 1)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise AgentLogIntegrityError(
                    f"Malformed agent-log index {path} line {line_no}: invalid {field}"
                )
            if value > current:
                raise AgentLogIntegrityError(
                    f"Unsupported agent-log {field} {value} in {path} line {line_no}"
                )
        if _safe_relative_path(record["path"]) is None:
            raise AgentLogIntegrityError(
                f"Malformed agent-log index {path} line {line_no}: unsafe path"
            )
        records.append(record)
    return records

def parse_index(payload: bytes, path: Path) -> list[dict[str, Any]]:
    return _parse_index(payload, path)

def _walk_store(log_root: Path) -> tuple[list[Path], list[Path]]:
    markdown: list[Path] = []
    jsonl: list[Path] = []
    pending = [log_root]
    while pending:
        directory = pending.pop()
        with os.scandir(directory) as entries:
            for entry in entries:
                path = Path(entry.path)
                if entry.is_symlink():
                    raise AgentLogIntegrityError(
                        f"agent-log path component is a symlink: {path}"
                    )
                if entry.is_dir(follow_symlinks=False):
                    pending.append(path)
                    continue
                if not entry.is_file(follow_symlinks=False):
                    raise AgentLogIntegrityError(
                        f"agent-log entry is not a regular file: {path}"
                    )
                if path.suffix.lower() == ".md":
                    markdown.append(path)
                elif path.suffix.lower() == ".jsonl":
                    jsonl.append(path)
    return sorted(markdown), sorted(jsonl)
