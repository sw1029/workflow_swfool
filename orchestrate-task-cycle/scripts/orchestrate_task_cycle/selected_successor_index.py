"""Immutable O(1) lookup from exact successor inputs to one bundle."""

from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path
import stat
from typing import Any

from manage_task_state_index.state.selected_successor import (
    MAX_SELECTED_SUCCESSOR_TASK_BYTES,
    MAX_SELECTION_DECISION_BYTES,
)

from .selection_decision_store import normalize_binding, read_bound_bytes
from .selection_publication_store import (
    _bounded_payload,
    _canonical_json,
    _sha256_bytes,
    _successor_prepare_index_path,
    _write_once,
)


INDEX_SCHEMA_VERSION = 1
MAX_PREPARE_INDEX_BYTES = 64 * 1024
INDEX_KEYS = {
    "schema_version",
    "artifact_kind",
    "input_sha256",
    "source_decision",
    "task_source",
    "created_at",
    "bundle",
    "index_content_sha256",
}


def _signature(value: os.stat_result) -> tuple[int, int, int, int, int, int]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


def _read_prepare_index(path: Path) -> bytes:
    """Read one internal index leaf with a hard 64 KiB/max+1 ceiling."""

    try:
        before = path.lstat()
    except OSError as exc:
        raise ValueError("Selected-successor prepare-input index is unreadable") from exc
    if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_PREPARE_INDEX_BYTES:
        raise ValueError(
            "Selected-successor prepare-input index exceeds the 64 KiB limit"
        )
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise ValueError("Selected-successor prepare-input index is unreadable") from exc
    try:
        opened = os.fstat(descriptor)
        if _signature(opened) != _signature(before):
            raise ValueError("Selected-successor prepare-input index changed during read")
        chunks: list[bytes] = []
        remaining = MAX_PREPARE_INDEX_BYTES + 1
        while remaining:
            chunk = os.read(descriptor, min(1024 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        after = os.fstat(descriptor)
        current = path.lstat()
        if (
            len(raw) > MAX_PREPARE_INDEX_BYTES
            or _signature(opened) != _signature(after)
            or _signature(after) != _signature(current)
        ):
            raise ValueError("Selected-successor prepare-input index changed during read")
        return raw
    finally:
        os.close(descriptor)


def _timestamp(value: Any) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(
            "Selected-successor created_at must be a timezone-aware RFC3339 timestamp"
        )
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(
            "Selected-successor created_at must be a timezone-aware RFC3339 timestamp"
        ) from exc
    if parsed.tzinfo is None:
        raise ValueError(
            "Selected-successor created_at must be a timezone-aware RFC3339 timestamp"
        )
    return value


def prepare_input_identity(
    source_decision: Any, task_source: Any, at: Any
) -> tuple[dict[str, Any], str]:
    identity = {
        "schema_version": 1,
        "artifact_kind": "selected_successor_prepare_input",
        "source_decision": normalize_binding(
            source_decision, "selected-successor source decision"
        ),
        "task_source": normalize_binding(
            task_source, "selected-successor task source"
        ),
        "created_at": _timestamp(at),
    }
    return identity, _sha256_bytes(_canonical_json(identity))


def _content(value: dict[str, Any]) -> str:
    body = {
        key: item for key, item in value.items() if key != "index_content_sha256"
    }
    return _sha256_bytes(_canonical_json(body))


def load_prepare_index(
    root: Path,
    source_decision: Any,
    task_source: Any,
    at: Any,
) -> dict[str, Any] | None:
    """Validate exact input files, then load their one immutable bundle pointer."""

    root = root.expanduser().resolve(strict=True)
    identity, input_sha256 = prepare_input_identity(
        source_decision, task_source, at
    )
    read_bound_bytes(
        root,
        identity["source_decision"],
        "selection decision receipt",
        max_bytes=MAX_SELECTION_DECISION_BYTES,
    )
    read_bound_bytes(
        root,
        identity["task_source"],
        "selected successor source",
        max_bytes=MAX_SELECTED_SUCCESSOR_TASK_BYTES,
    )
    path = _successor_prepare_index_path(root, input_sha256)
    if not path.exists():
        return None
    if path.is_symlink() or not path.is_file():
        raise ValueError("Selected-successor prepare-input index is not a regular file")
    raw = _read_prepare_index(path)
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Selected-successor prepare-input index is unreadable") from exc
    if not isinstance(value, dict) or raw != _canonical_json(value):
        raise ValueError("Selected-successor prepare-input index is not canonical JSON")
    if (
        set(value) != INDEX_KEYS
        or value.get("schema_version") != INDEX_SCHEMA_VERSION
        or value.get("artifact_kind") != "selected_successor_prepare_index"
        or value.get("input_sha256") != input_sha256
        or value.get("source_decision") != identity["source_decision"]
        or value.get("task_source") != identity["task_source"]
        or value.get("created_at") != identity["created_at"]
        or value.get("index_content_sha256") != _content(value)
    ):
        raise ValueError("Selected-successor prepare-input index integrity failed")
    bundle = normalize_binding(value.get("bundle"), "selected-successor indexed bundle")
    return {**value, "bundle": bundle}


def write_prepare_index(
    root: Path,
    source_decision: Any,
    task_source: Any,
    at: Any,
    bundle: Any,
) -> tuple[dict[str, Any], bool]:
    root = root.expanduser().resolve(strict=True)
    identity, input_sha256 = prepare_input_identity(
        source_decision, task_source, at
    )
    bundle_binding = normalize_binding(bundle, "selected-successor bundle")
    read_bound_bytes(
        root,
        identity["source_decision"],
        "selection decision receipt",
        max_bytes=MAX_SELECTION_DECISION_BYTES,
    )
    read_bound_bytes(
        root,
        identity["task_source"],
        "selected successor source",
        max_bytes=MAX_SELECTED_SUCCESSOR_TASK_BYTES,
    )
    read_bound_bytes(root, bundle_binding, "selected-successor bundle")
    body = {
        "schema_version": INDEX_SCHEMA_VERSION,
        "artifact_kind": "selected_successor_prepare_index",
        "input_sha256": input_sha256,
        "source_decision": identity["source_decision"],
        "task_source": identity["task_source"],
        "created_at": identity["created_at"],
        "bundle": bundle_binding,
    }
    value = {**body, "index_content_sha256": _content(body)}
    path = _successor_prepare_index_path(root, input_sha256)
    created = not path.exists() and not path.is_symlink()
    payload = _bounded_payload(
        _canonical_json(value),
        MAX_PREPARE_INDEX_BYTES,
        "selected-successor prepare-input index",
    )
    _write_once(
        path,
        payload,
        "selected-successor prepare-input index",
    )
    return value, created


__all__ = (
    "MAX_PREPARE_INDEX_BYTES",
    "load_prepare_index",
    "prepare_input_identity",
    "write_prepare_index",
)
