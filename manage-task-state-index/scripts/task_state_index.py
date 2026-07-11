#!/usr/bin/env python3
from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import hashlib
import json
import os
import re
import sys
import tempfile
import threading
from pathlib import Path
from typing import Any, Iterator

AGENT_LOG_SCRIPTS = Path(__file__).resolve().parents[2] / "record-agent-work-log" / "scripts"
if str(AGENT_LOG_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(AGENT_LOG_SCRIPTS))

from agent_log_integrity import inspect_agent_log_store  # noqa: E402

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows fallback keeps thread safety only.
    fcntl = None  # type: ignore[assignment]


PREFIXES = {
    "task": "task",
    "task_pack": "pack",
    "past_task": "past",
    "candidate_task": "cand",
    "task_miss": "miss",
    "agent_log": "log",
    "execution": "run",
    "audit": "audit",
    "validation": "val",
    "goal": "goal",
    "goal_prompt": "prompt",
    "interview": "int",
    "environment": "env",
    "external_advice": "adv",
    "schema_contract": "schema",
    "schema_map": "schema-map",
    "issue": "issue",
    "issue_resolution": "issue-res",
    "issue_map": "issue-map",
}

INDEX_FORMAT_VERSION = 2
INDEX_SCHEMA_VERSION = 1
SUPPORTED_EVENT_KINDS = {"upsert", "link"}
LIFECYCLE_STATUSES = {
    "active",
    "applied",
    "archived",
    "blocked",
    "candidate",
    "closed",
    "complete",
    "completed",
    "deferred",
    "deleted",
    "deprecated",
    "failed",
    "in_progress",
    "informational",
    "logged",
    "needs_review",
    "not_applicable",
    "obsolete",
    "open",
    "partial",
    "partially_resolved",
    "passed",
    "raw",
    "rejected",
    "resolved",
    "running",
    "skipped",
    "stale",
    "superseded",
    "terminal_blocked",
}
NON_ACTIVE_STATUSES = {
    "applied",
    "archived",
    "closed",
    "deleted",
    "deprecated",
    "obsolete",
    "rejected",
    "resolved",
    "superseded",
}

_THREAD_LOCKS: dict[str, threading.RLock] = {}
_THREAD_LOCKS_GUARD = threading.Lock()


def now_iso() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def id_stamp() -> str:
    return dt.datetime.now().strftime("%Y%m%d-%H%M%S")


def slugify(value: str, fallback: str = "item") -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.lower()).strip("-")
    return (slug or fallback)[:48]


def rel_path(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def sha256_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_title(path: Path) -> str:
    if path.is_file():
        try:
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                stripped = line.strip()
                if stripped.startswith("#"):
                    return stripped.lstrip("#").strip()[:120] or path.stem
                if stripped:
                    return stripped[:120]
        except OSError:
            pass
    return path.stem.replace("-", " ").replace("_", " ")


def task_dir(root: Path) -> Path:
    return root / ".task"


def jsonl_path(root: Path) -> Path:
    return task_dir(root) / "index.jsonl"


def markdown_path(root: Path) -> Path:
    return task_dir(root) / "index.md"


def lock_path(root: Path) -> Path:
    return task_dir(root) / "index.lock"


def immutable_snapshot_path(root: Path, item_id: str, source_path: Path) -> Path:
    suffix = source_path.suffix or ".txt"
    return task_dir(root) / "snapshots" / f"{item_id}{suffix}"


def _thread_lock(root: Path) -> threading.RLock:
    key = str(root.resolve())
    with _THREAD_LOCKS_GUARD:
        return _THREAD_LOCKS.setdefault(key, threading.RLock())


@contextlib.contextmanager
def index_lock(root: Path) -> Iterator[None]:
    root = root.resolve()
    with _thread_lock(root):
        task_dir(root).mkdir(parents=True, exist_ok=True)
        with lock_path(root).open("a+b") as handle:
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


def atomic_write_bytes(path: Path, payload: bytes, mode: int = 0o644) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
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


def atomic_write_text(path: Path, text: str, mode: int = 0o644) -> None:
    atomic_write_bytes(path, text.encode("utf-8"), mode=mode)


def _ensure_index_unlocked(root: Path) -> None:
    task_dir(root).mkdir(parents=True, exist_ok=True)
    if not jsonl_path(root).exists():
        atomic_write_bytes(jsonl_path(root), b"")


def ensure_index(root: Path) -> None:
    with index_lock(root):
        _ensure_index_unlocked(root)


def _version(value: Any, *, field: str, line_no: int, source: Path, default: int) -> int:
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"Invalid {field} in {source} line {line_no}: expected a positive integer")
    return value


def validate_event(event: Any, line_no: int, source: Path) -> dict[str, Any]:
    if not isinstance(event, dict):
        raise ValueError(f"Malformed task-state JSONL {source} line {line_no}: expected a JSON object")
    event_kind = event.get("event")
    if event_kind not in SUPPORTED_EVENT_KINDS:
        raise ValueError(f"Malformed task-state JSONL {source} line {line_no}: unsupported event {event_kind!r}")
    for field in ("id", "updated_at"):
        if not isinstance(event.get(field), str) or not event[field].strip():
            raise ValueError(f"Malformed task-state JSONL {source} line {line_no}: missing non-empty {field}")
    format_version = _version(event.get("format_version"), field="format_version", line_no=line_no, source=source, default=1)
    schema_version = _version(event.get("schema_version"), field="schema_version", line_no=line_no, source=source, default=1)
    if format_version > INDEX_FORMAT_VERSION:
        raise ValueError(
            f"Unsupported task-state format_version {format_version} in {source} line {line_no}; "
            f"maximum supported is {INDEX_FORMAT_VERSION}"
        )
    if schema_version > INDEX_SCHEMA_VERSION:
        raise ValueError(
            f"Unsupported task-state schema_version {schema_version} in {source} line {line_no}; "
            f"maximum supported is {INDEX_SCHEMA_VERSION}"
        )
    status = event.get("status")
    if status is not None and status not in LIFECYCLE_STATUSES:
        raise ValueError(f"Malformed task-state JSONL {source} line {line_no}: unsupported lifecycle status {status!r}")
    if "fields" in event and not isinstance(event.get("fields"), dict):
        raise ValueError(f"Malformed task-state JSONL {source} line {line_no}: fields must be an object")
    if "links" in event:
        links = event.get("links")
        if not isinstance(links, list):
            raise ValueError(f"Malformed task-state JSONL {source} line {line_no}: links must be a list")
        for link in links:
            if not isinstance(link, dict) or not isinstance(link.get("rel"), str) or not isinstance(link.get("id"), str):
                raise ValueError(f"Malformed task-state JSONL {source} line {line_no}: invalid relationship object")
    return event


def _load_events_unlocked(root: Path) -> list[dict[str, Any]]:
    _ensure_index_unlocked(root)
    events: list[dict[str, Any]] = []
    source = jsonl_path(root)
    with source.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Malformed task-state JSONL {source} line {line_no}: {exc}") from exc
            events.append(validate_event(event, line_no, source))
    return events


def load_events(root: Path) -> list[dict[str, Any]]:
    with index_lock(root):
        return _load_events_unlocked(root)


def merge_state(events: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    state: dict[str, dict[str, Any]] = {}
    for event in events:
        item_id = event.get("id")
        if not item_id:
            continue
        current = state.setdefault(
            item_id,
            {
                "id": item_id,
                "created_at": event.get("created_at") or event.get("updated_at"),
                "links": [],
                "fields": {},
            },
        )
        current["updated_at"] = event.get("updated_at") or now_iso()
        for key in ("type", "status", "path", "title", "parent_id", "content_sha256", "note"):
            if key in event and event[key] is not None:
                current[key] = event[key]
        if isinstance(event.get("fields"), dict):
            current.setdefault("fields", {}).update(event["fields"])
        if isinstance(event.get("links"), list):
            seen = {(link.get("rel"), link.get("id")) for link in current.setdefault("links", [])}
            for link in event["links"]:
                if not isinstance(link, dict):
                    continue
                pair = (link.get("rel"), link.get("id"))
                if pair[0] and pair[1] and pair not in seen:
                    current["links"].append({"rel": pair[0], "id": pair[1]})
                    seen.add(pair)
    return state


def parse_key_value(values: list[str]) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for value in values:
        if "=" not in value:
            raise SystemExit(f"Expected key=value, got: {value}")
        key, raw = value.split("=", 1)
        key = key.strip()
        if not key:
            raise SystemExit(f"Empty key in field: {value}")
        parsed[key] = raw.strip()
    return parsed


def parse_links(values: list[str]) -> list[dict[str, str]]:
    links: list[dict[str, str]] = []
    for value in values:
        separator = "=" if "=" in value else ":"
        if separator not in value:
            raise SystemExit(f"Expected rel:id or rel=id, got: {value}")
        rel, target = value.split(separator, 1)
        rel = rel.strip()
        target = target.strip()
        if not rel or not target:
            raise SystemExit(f"Invalid link: {value}")
        links.append({"rel": rel, "id": target})
    return links


def find_existing_id(state: dict[str, dict[str, Any]], item_type: str, path: str, digest: str | None) -> str | None:
    for item_id, item in state.items():
        if item.get("type") != item_type or item.get("path") != path:
            continue
        if digest and item.get("content_sha256") == digest:
            return item_id
        if not digest and item.get("status") not in {"deleted"}:
            return item_id
    return None


def path_records(
    state: dict[str, dict[str, Any]],
    item_type: str,
    path: str,
    *,
    active_only: bool = False,
) -> list[tuple[str, dict[str, Any]]]:
    records = [
        (item_id, item)
        for item_id, item in state.items()
        if item.get("type") == item_type
        and item.get("path") == path
        and (not active_only or item.get("status") not in NON_ACTIVE_STATUSES)
    ]
    return sorted(
        records,
        key=lambda pair: (str(pair[1].get("updated_at") or pair[1].get("created_at") or ""), pair[0]),
        reverse=True,
    )


def stable_path_id(state: dict[str, dict[str, Any]], item_type: str, path: str) -> str | None:
    active = path_records(state, item_type, path, active_only=True)
    if active:
        return active[0][0]
    records = path_records(state, item_type, path)
    return records[0][0] if records else None


def make_id(item_type: str, title: str, path: str) -> str:
    prefix = PREFIXES.get(item_type, slugify(item_type, "item"))
    label = title or Path(path).stem or item_type
    return f"{prefix}-{id_stamp()}-{slugify(label, item_type)}"


def versioned_event(event: dict[str, Any]) -> dict[str, Any]:
    return {
        **event,
        "format_version": INDEX_FORMAT_VERSION,
        "schema_version": INDEX_SCHEMA_VERSION,
    }


def _append_events_unlocked(root: Path, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    existing = _load_events_unlocked(root)
    del existing  # Reading first is the fail-closed integrity gate.
    versioned = [versioned_event(event) for event in events]
    for offset, event in enumerate(versioned, start=1):
        validate_event(event, offset, jsonl_path(root))
    payload = jsonl_path(root).read_bytes()
    if payload and not payload.endswith(b"\n"):
        payload += b"\n"
    payload += b"".join(
        (json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
        for event in versioned
    )
    atomic_write_bytes(jsonl_path(root), payload)
    return versioned


def append_event(root: Path, event: dict[str, Any]) -> None:
    with index_lock(root):
        _append_events_unlocked(root, [event])


def escape_md(value: Any) -> str:
    text = "" if value is None else str(value)
    return text.replace("|", "\\|").replace("\n", " ")


def _rebuild_markdown_unlocked(root: Path, events: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    state = merge_state(events if events is not None else _load_events_unlocked(root))
    groups: dict[str, list[dict[str, Any]]] = {}
    for item in state.values():
        groups.setdefault(str(item.get("type", "unknown")), []).append(item)

    lines = [
        "# Task State Index",
        "",
        f"- Generated: {now_iso()}",
        "- Canonical JSONL: `.task/index.jsonl`",
        f"- Format version: {INDEX_FORMAT_VERSION}",
        f"- Schema version: {INDEX_SCHEMA_VERSION}",
        f"- Artifact count: {len(state)}",
        "",
    ]

    for item_type in sorted(groups):
        items = sorted(groups[item_type], key=lambda item: (str(item.get("status", "")), str(item.get("id", ""))))
        lines.extend(
            [
                f"## {item_type}",
                "",
                "| ID | Status | Title | Path | Parent | Links | Updated |",
                "| --- | --- | --- | --- | --- | --- | --- |",
            ]
        )
        for item in items:
            links = ", ".join(f"{link.get('rel')}:{link.get('id')}" for link in item.get("links", []))
            lines.append(
                "| "
                + " | ".join(
                    [
                        escape_md(item.get("id")),
                        escape_md(item.get("status")),
                        escape_md(item.get("title")),
                        escape_md(item.get("path")),
                        escape_md(item.get("parent_id")),
                        escape_md(links),
                        escape_md(item.get("updated_at")),
                    ]
                )
                + " |"
            )
        lines.append("")

    atomic_write_text(markdown_path(root), "\n".join(lines).rstrip() + "\n")
    return {
        "index_md": rel_path(root, markdown_path(root)),
        "artifact_count": len(state),
        "format_version": INDEX_FORMAT_VERSION,
        "schema_version": INDEX_SCHEMA_VERSION,
    }


def rebuild_markdown(root: Path) -> dict[str, Any]:
    with index_lock(root):
        return _rebuild_markdown_unlocked(root)


def upsert_item(
    root: Path,
    item_type: str,
    path_value: str,
    status: str,
    title: str | None = None,
    item_id: str | None = None,
    parent_id: str | None = None,
    links: list[dict[str, str]] | None = None,
    fields: dict[str, str] | None = None,
    note: str | None = None,
    replace_existing: bool | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    if status not in LIFECYCLE_STATUSES:
        raise ValueError(f"Unsupported lifecycle status: {status!r}")
    with index_lock(root):
        state = merge_state(_load_events_unlocked(root))
        path = root / path_value
        digest = sha256_file(path)
        title = title or read_title(path)
        timestamp = now_iso()
        active_records = path_records(state, item_type, path_value, active_only=True)
        provided_item_id = item_id is not None
        explicit_replacement = bool(
            provided_item_id
            and active_records
            and all(existing_id != item_id for existing_id, _ in active_records)
        )
        legacy_task_replacement = bool(
            replace_existing is None
            and not provided_item_id
            and item_type == "task"
            and path_value == "task.md"
            and digest
            and any(existing.get("content_sha256") != digest for _, existing in active_records)
        )
        semantic_replacement = bool(replace_existing) or explicit_replacement or legacy_task_replacement

        if semantic_replacement and not provided_item_id:
            item_id = make_id(item_type, title, path_value)
        elif not semantic_replacement:
            item_id = item_id or stable_path_id(state, item_type, path_value) or make_id(item_type, title, path_value)
        assert item_id is not None

        if explicit_replacement and item_id in state:
            raise ValueError(f"Replacement id {item_id!r} must be new")
        if replace_existing and provided_item_id and any(existing_id == item_id for existing_id, _ in active_records):
            raise ValueError("--replace requires a new explicit id or no --id")

        if provided_item_id and item_id in state:
            existing = state[item_id]
            if existing.get("type") != item_type:
                raise ValueError(f"Explicit id {item_id!r} already belongs to another artifact")
            if existing.get("path") != path_value and replace_existing is not False:
                raise ValueError(f"Explicit id {item_id!r} already belongs to another artifact path")
        if not provided_item_id:
            base_id = item_id
            suffix = 2
            while item_id in state and (
                semantic_replacement
                or state[item_id].get("type") != item_type
                or state[item_id].get("path") != path_value
            ):
                item_id = f"{base_id}-{suffix}"
                suffix += 1

        superseded_records = [
            (existing_id, existing)
            for existing_id, existing in active_records
            if existing_id != item_id
        ]
        lifecycle_transition_result: dict[str, Any] | None = None
        if semantic_replacement and superseded_records:
            lifecycle_transition_result = {
                "previous_snapshot_preserved": True,
                "previous_active_superseded": False,
                "new_canonical_id_added": False,
                "mutable_alias_updated": False,
                "links_updated": False,
                "index_rendered": False,
                "atomic": False,
                "replacement_reason": "explicit_id" if explicit_replacement else "semantic_replacement",
            }

        outgoing: list[dict[str, Any]] = []
        for previous_id, previous in superseded_records:
            previous_fields = previous.get("fields") if isinstance(previous.get("fields"), dict) else {}
            if item_type == "task" and path_value == "task.md":
                snapshot_value = previous_fields.get("snapshot_path")
                snapshot_exists = bool(snapshot_value and (root / str(snapshot_value)).is_file())
                if lifecycle_transition_result is not None and not snapshot_exists:
                    lifecycle_transition_result["previous_snapshot_preserved"] = False
                outgoing.append(
                    {
                        "event": "upsert",
                        "id": previous_id,
                        "updated_at": timestamp,
                        "fields": {
                            **previous_fields,
                            "record_class": "immutable_snapshot",
                            "snapshot_digest": previous.get("content_sha256"),
                            "snapshot_path": snapshot_value,
                            "alias_path": path_value,
                            "canonical_id": previous_id,
                        },
                    }
                )
            outgoing.extend(
                [
                    {
                        "event": "upsert",
                        "id": previous_id,
                        "status": "superseded",
                        "updated_at": timestamp,
                    },
                    {
                        "event": "link",
                        "id": previous_id,
                        "updated_at": timestamp,
                        "links": [{"rel": "superseded_by", "id": item_id}],
                    },
                ]
            )
        if lifecycle_transition_result is not None:
            lifecycle_transition_result["previous_active_superseded"] = True

        merged_fields = dict(fields or {})
        event_links = list(links or [])
        if superseded_records:
            event_links.extend({"rel": "supersedes", "id": previous_id} for previous_id, _ in superseded_records)

        if item_type == "task" and path_value == "task.md" and path.is_file():
            snapshot = immutable_snapshot_path(root, item_id, path)
            # Stable IDs track ordinary edits; explicit/semantic replacement creates a new immutable body.
            atomic_write_bytes(snapshot, path.read_bytes())
            merged_fields.update(
                {
                    "record_class": "mutable_alias",
                    "snapshot_digest": digest or "",
                    "snapshot_path": rel_path(root, snapshot),
                    "canonical_id": item_id,
                    "alias_path": path_value,
                }
            )

        event: dict[str, Any] = {
            "event": "upsert",
            "id": item_id,
            "type": item_type,
            "status": status,
            "path": path_value,
            "title": title,
            "updated_at": timestamp,
            "content_sha256": digest,
        }
        if item_id not in state:
            event["created_at"] = timestamp
        if parent_id:
            event["parent_id"] = parent_id
        if event_links:
            event["links"] = event_links
        if merged_fields:
            event["fields"] = merged_fields
        if note:
            event["note"] = note
        outgoing.append(event)

        versioned = _append_events_unlocked(root, outgoing)
        rebuild = _rebuild_markdown_unlocked(root)
        if lifecycle_transition_result is not None:
            lifecycle_transition_result.update(
                {
                    "new_canonical_id_added": True,
                    "mutable_alias_updated": True,
                    "links_updated": True,
                    "index_rendered": True,
                }
            )
            lifecycle_transition_result["atomic"] = all(
                lifecycle_transition_result[field]
                for field in (
                    "previous_snapshot_preserved",
                    "previous_active_superseded",
                    "new_canonical_id_added",
                    "mutable_alias_updated",
                    "links_updated",
                    "index_rendered",
                )
            )
        return {
            "id": item_id,
            "event": next(item for item in versioned if item.get("id") == item_id and item.get("type") == item_type),
            "lifecycle_transition_result": lifecycle_transition_result,
            "duplicate_active_paths_repaired": len(superseded_records) if not semantic_replacement else 0,
            **rebuild,
        }


def infer_miss_status(path: Path) -> str:
    name = path.name.lower()
    if "deleted" in name:
        return "deleted"
    if "partially_resolved" in name or "partially-resolved" in name:
        return "partially_resolved"
    if "resolved" in name:
        return "resolved"
    try:
        text = path.read_text(encoding="utf-8", errors="replace").lower()
    except OSError:
        return "open"
    if "partially_resolved" in text or "partially-resolved" in text or "status: partial" in text:
        return "partially_resolved"
    if "resolved_delete" in text or "deleted" in text:
        return "deleted"
    if "resolved_archive" in text or "resolved" in text:
        return "resolved"
    if "obsolete_scope" in text or "obsolete" in text:
        return "obsolete"
    return "open"


def infer_schema_status(path: Path) -> str:
    name = path.name.lower()
    try:
        text = path.read_text(encoding="utf-8", errors="replace").lower()
    except OSError:
        text = ""
    combined = f"{name}\n{text}"
    if "status: superseded" in combined or '"status": "superseded"' in combined or '"status":"superseded"' in combined:
        return "superseded"
    if "status: deprecated" in combined or '"status": "deprecated"' in combined or '"status":"deprecated"' in combined:
        return "deprecated"
    if "status: needs_review" in combined or '"status": "needs_review"' in combined or '"status":"needs_review"' in combined:
        return "needs_review"
    return "active"


def infer_issue_status(path: Path) -> str:
    name = path.name.lower()
    parts = {part.lower() for part in path.parts}
    try:
        text = path.read_text(encoding="utf-8", errors="replace").lower()
    except OSError:
        text = ""
    combined = f"{name}\n{text}"
    if "closed" in parts or "status: closed" in combined:
        return "closed"
    if "resolved" in parts or "status: resolved" in combined:
        return "resolved"
    if "archived" in parts or "status: archived" in combined:
        return "archived"
    if "status: superseded" in combined:
        return "superseded"
    if "status: blocked" in combined:
        return "blocked"
    if "status: in_progress" in combined or "status: in-progress" in combined:
        return "in_progress"
    return "open"


def infer_advice_status(path: Path) -> str:
    parts = {part.lower() for part in path.parts}
    try:
        text = path.read_text(encoding="utf-8", errors="replace").lower()
    except OSError:
        text = ""
    combined = f"{path.name.lower()}\n{text}"
    if "applied" in parts or "status: applied" in combined:
        return "applied"
    if "rejected" in parts or "status: rejected" in combined:
        return "rejected"
    if "deferred" in parts or "status: deferred" in combined:
        return "deferred"
    if "raw" in parts:
        return "raw"
    return "active"


def extract_schema_fields(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return {}

    fields: dict[str, str] = {}
    scalar_keys = {
        "contract_id",
        "type",
        "status",
        "version",
        "owner_path",
        "updated_at",
    }
    list_keys = {
        "target_modules",
        "target_scripts",
        "producers",
        "consumers",
        "compatible_with",
    }
    current_list_key: str | None = None
    collected_lists: dict[str, list[str]] = {key: [] for key in list_keys}

    for raw_line in lines:
        line = raw_line.rstrip()
        scalar_match = re.match(r"^-\s+([A-Za-z0-9_]+):\s*(.*)$", line)
        if scalar_match:
            key, value = scalar_match.groups()
            if key in scalar_keys and value:
                fields[key] = value.strip()
                current_list_key = None
                continue
            if key in list_keys:
                current_list_key = key
                if value:
                    collected_lists[key].append(value.strip())
                continue
            current_list_key = None
            continue

        list_match = re.match(r"^\s+-\s+(.+)$", line)
        if current_list_key and list_match:
            collected_lists[current_list_key].append(list_match.group(1).strip())
        elif line and not line.startswith(" "):
            current_list_key = None

    for key, values in collected_lists.items():
        if values:
            fields[key] = ", ".join(values)

    if path.suffix.lower() == ".jsonl" and not fields:
        for raw_line in lines:
            if not raw_line.strip():
                continue
            try:
                event = json.loads(raw_line)
            except json.JSONDecodeError:
                break
            if isinstance(event, dict):
                for key in scalar_keys | list_keys:
                    value = event.get(key)
                    if isinstance(value, list):
                        fields[key] = ", ".join(str(item) for item in value)
                    elif value is not None:
                        fields[key] = str(value)
            break

    return fields


def extract_issue_fields(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return {}

    fields: dict[str, str] = {}
    scalar_keys = {
        "issue_id",
        "status",
        "source",
        "remote_url",
        "remote_number",
        "task_id",
        "task_path",
        "priority",
        "goal_fit",
        "branch",
        "worktree_path",
        "validation_status",
        "created_at",
        "updated_at",
    }
    for raw_line in lines:
        match = re.match(r"^-\s+([A-Za-z0-9_]+):\s*(.*)$", raw_line.rstrip())
        if not match:
            continue
        key, value = match.groups()
        if key in scalar_keys and value:
            fields[key] = value.strip()
    return fields


def extract_advice_fields(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return {}
    fields: dict[str, str] = {}
    scalar_keys = {
        "advice_id",
        "status",
        "not_goal_truth",
        "raw_source_path",
        "received_at",
        "normalized_at",
        "scope",
        "priority",
        "source_label",
    }
    for raw_line in lines:
        match = re.match(r"^-\s+([A-Za-z0-9_]+):\s*(.*)$", raw_line.rstrip())
        if not match:
            continue
        key, value = match.groups()
        if key in scalar_keys and value:
            fields[key] = value.strip()
    return fields


def extract_task_pack_fields(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    fields: dict[str, str] = {}
    for key in ("pack_id", "status", "language", "goal", "current_item_id"):
        value = data.get(key)
        if value is not None:
            fields[key] = str(value)
    items = data.get("items")
    if isinstance(items, list):
        fields["item_count"] = str(len(items))
        fields["planned_item_count"] = str(sum(1 for item in items if isinstance(item, dict) and item.get("status") in {"planned", "inserted", "reordered"}))
    render_path = path.with_suffix(".md")
    if render_path.is_file():
        fields["render_path"] = render_path.as_posix()
    if data.get("terminal_blocker"):
        fields["terminal_blocker"] = "true"
    return fields


def discover_standard_artifacts(root: Path) -> list[tuple[str, str, str, str]]:
    artifacts: list[tuple[str, str, str, str]] = []

    task_md = root / "task.md"
    if task_md.is_file():
        artifacts.append(("task", "task.md", "active", read_title(task_md)))

    candidate_dir = root / ".task" / "candidate_task"
    if candidate_dir.is_dir():
        for path in sorted(candidate_dir.glob("*.md")):
            artifacts.append(("candidate_task", rel_path(root, path), "candidate", read_title(path)))

    task_pack_dir = root / ".task" / "task_pack"
    if task_pack_dir.is_dir():
        for path in sorted(task_pack_dir.glob("*.json")):
            fields = extract_task_pack_fields(path)
            status = fields.get("status", "active")
            title = fields.get("pack_id") or fields.get("goal") or path.stem
            artifacts.append(("task_pack", rel_path(root, path), status, title[:120]))

    miss_dir = root / ".task" / "task_miss"
    if miss_dir.is_dir():
        for path in sorted(miss_dir.rglob("*.md")):
            artifacts.append(("task_miss", rel_path(root, path), infer_miss_status(path), read_title(path)))

    validation_dir = root / ".task" / "validation"
    if validation_dir.is_dir():
        for path in sorted(validation_dir.glob("*.md")):
            status = "partial"
            try:
                text = path.read_text(encoding="utf-8", errors="replace").lower()
            except OSError:
                text = ""
            if "verdict: complete" in text:
                status = "passed"
            elif "verdict: failed" in text:
                status = "failed"
            artifacts.append(("validation", rel_path(root, path), status, read_title(path)))

    id_audit_dir = root / ".task" / "id_audit"
    if id_audit_dir.is_dir():
        for path in sorted(id_audit_dir.glob("*.md")):
            artifacts.append(("audit", rel_path(root, path), "logged", read_title(path)))

    log_integrity, log_markdown, _ = inspect_agent_log_store(root)
    if log_integrity["status"] in {"valid", "legacy_unverified"}:
        for path in log_markdown:
            title = read_title(path)
            item_type = "past_task" if "past_task" in title.lower() or "past-task" in path.name.lower() else "agent_log"
            artifacts.append((item_type, rel_path(root, path), "logged", title))

    goal_dir = root / ".agent_goal"
    if goal_dir.is_dir():
        for path in sorted(goal_dir.glob("*.md")):
            artifacts.append(("goal", rel_path(root, path), "active", read_title(path)))

    interview_dir = root / ".interview"
    if interview_dir.is_dir():
        for path in sorted(interview_dir.rglob("*.md")):
            artifacts.append(("interview", rel_path(root, path), "active", read_title(path)))

    advice_dir = root / ".agent_advice"
    if advice_dir.is_dir():
        for path in sorted(advice_dir.rglob("*.md")):
            if path.name.lower() == "index.md":
                continue
            artifacts.append(("external_advice", rel_path(root, path), infer_advice_status(path), read_title(path)))

    issue_dir = root / ".issue"
    if issue_dir.is_dir():
        for path in sorted(issue_dir.rglob("*.md")):
            relative_parts = {part.lower() for part in path.relative_to(issue_dir).parts}
            if path.name.lower() == "index.md":
                artifacts.append(("issue_map", rel_path(root, path), "active", read_title(path)))
                continue
            status = infer_issue_status(path)
            item_type = "issue_resolution" if relative_parts & {"resolved", "closed", "archived"} else "issue"
            artifacts.append((item_type, rel_path(root, path), status, read_title(path)))

    schema_dir = root / ".schema"
    if schema_dir.is_dir():
        seen_schema_paths: set[str] = set()

        def add_schema_artifact(item_type: str, path: Path, status: str) -> None:
            relative = rel_path(root, path)
            if relative in seen_schema_paths:
                return
            seen_schema_paths.add(relative)
            artifacts.append((item_type, relative, status, read_title(path)))

        for name in ("index.md", "causal_map.md", "compatibility_map.md", "contracts.jsonl"):
            path = schema_dir / name
            if path.is_file():
                add_schema_artifact("schema_map", path, "active")

        for path in sorted(schema_dir.glob("*.md")) + sorted(schema_dir.glob("*.jsonl")) + sorted(schema_dir.glob("*.json")):
            if path.is_file():
                add_schema_artifact("schema_map", path, "active")

        contract_suffixes = {".md", ".json", ".jsonl", ".yaml", ".yml"}
        for directory_name in ("schemas", "modules", "scripts", "contracts"):
            directory = schema_dir / directory_name
            if not directory.is_dir():
                continue
            for path in sorted(directory.rglob("*")):
                if path.is_file() and path.suffix.lower() in contract_suffixes:
                    add_schema_artifact("schema_contract", path, infer_schema_status(path))

    contract_dir = root / ".contract"
    if contract_dir.is_dir():
        seen_contract_paths: set[str] = set()

        def add_contract_artifact(item_type: str, path: Path, status: str) -> None:
            relative = rel_path(root, path)
            if relative in seen_contract_paths:
                return
            seen_contract_paths.add(relative)
            artifacts.append((item_type, relative, status, read_title(path)))

        map_names = {"index.md", "causal_map.md", "compatibility_map.md", "contracts.jsonl"}
        for name in sorted(map_names):
            path = contract_dir / name
            if path.is_file():
                add_contract_artifact("schema_map", path, "active")

        contract_suffixes = {".md", ".json", ".jsonl", ".yaml", ".yml"}
        for path in sorted(contract_dir.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in contract_suffixes:
                continue
            item_type = "schema_map" if path.name in map_names else "schema_contract"
            status = "active" if item_type == "schema_map" else infer_schema_status(path)
            add_contract_artifact(item_type, path, status)

    return artifacts


def scan_artifacts(root: Path) -> dict[str, Any]:
    ensure_index(root)
    added: list[dict[str, Any]] = []
    state = merge_state(load_events(root))

    def maybe_upsert(item_type: str, path_value: str, status: str, title: str) -> None:
        nonlocal state
        digest = sha256_file(root / path_value)
        fields = None
        item_id = stable_path_id(state, item_type, path_value)
        if item_type in {"schema_contract", "schema_map"}:
            fields = extract_schema_fields(root / path_value)
        elif item_type == "task_pack":
            fields = extract_task_pack_fields(root / path_value)
            if fields.get("render_path"):
                fields["render_path"] = rel_path(root, Path(fields["render_path"]))
            pack_id = fields.get("pack_id") if fields else None
            if pack_id:
                for existing_id, existing in state.items():
                    existing_fields = existing.get("fields") if isinstance(existing.get("fields"), dict) else {}
                    if existing.get("type") == "task_pack" and existing_fields.get("pack_id") == pack_id:
                        item_id = existing_id
                        break
        elif item_type in {"issue", "issue_resolution", "issue_map"}:
            fields = extract_issue_fields(root / path_value)
        elif item_type == "external_advice":
            fields = extract_advice_fields(root / path_value)
            if fields is not None:
                fields["status"] = status
            advice_id = fields.get("advice_id") if fields else None
            if advice_id:
                for existing_id, existing in state.items():
                    existing_fields = existing.get("fields") if isinstance(existing.get("fields"), dict) else {}
                    if existing.get("type") == "external_advice" and existing_fields.get("advice_id") == advice_id:
                        item_id = existing_id
                        break
        existing = state.get(item_id) if item_id else None
        existing_fields = existing.get("fields") if isinstance(existing, dict) and isinstance(existing.get("fields"), dict) else {}
        if (
            existing
            and existing.get("path") == path_value
            and existing.get("content_sha256") == digest
            and existing.get("status") == status
            and existing.get("title") == title
            and all(existing_fields.get(key) == value for key, value in (fields or {}).items())
        ):
            return
        result = upsert_item(
            root,
            item_type,
            path_value,
            status,
            title=title,
            item_id=item_id,
            fields=fields,
            replace_existing=False,
        )
        added.append(result["event"])
        state = merge_state(load_events(root))

    for item_type, path_value, status, title in discover_standard_artifacts(root):
        maybe_upsert(item_type, path_value, status, title)

    rebuild = rebuild_markdown(root)
    return {
        "indexed_events": len(added),
        "events": added,
        "scan_evidence_status": "evaluated" if discover_standard_artifacts(root) else "not_evaluated_no_artifacts",
        **rebuild,
    }


def link_item(
    root: Path,
    source_id: str,
    links: list[dict[str, str]],
    note: str | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    with index_lock(root):
        state = merge_state(_load_events_unlocked(root))
        if source_id not in state:
            raise ValueError(f"Unknown source id: {source_id}")
        event: dict[str, Any] = {
            "event": "link",
            "id": source_id,
            "links": links,
            "updated_at": now_iso(),
        }
        if note:
            event["note"] = note
        versioned = _append_events_unlocked(root, [event])[0]
        return {"id": source_id, "event": versioned, **_rebuild_markdown_unlocked(root)}


def add_issue(
    issues: list[dict[str, Any]],
    severity: str,
    code: str,
    message: str,
    ids: list[str] | None = None,
    paths: list[str] | None = None,
) -> None:
    issues.append(
        {
            "severity": severity,
            "code": code,
            "message": message,
            "ids": ids or [],
            "paths": paths or [],
        }
    )


def audit_index(root: Path) -> dict[str, Any]:
    events = load_events(root)
    state = merge_state(events)
    issues: list[dict[str, Any]] = []

    for item_id, item in sorted(state.items()):
        item_type = str(item.get("type", ""))
        expected_prefix = PREFIXES.get(item_type)
        if expected_prefix and not item_id.startswith(f"{expected_prefix}-"):
            add_issue(
                issues,
                "medium",
                "prefix_mismatch",
                f"ID prefix does not match type {item_type}; expected {expected_prefix}-.",
                [item_id],
            )

        path_value = item.get("path")
        status = str(item.get("status", ""))
        if path_value and status not in {"deleted"}:
            path = root / str(path_value)
            if not path.exists() and status not in {"obsolete", "superseded"}:
                add_issue(issues, "high", "missing_path", "Indexed artifact path does not exist.", [item_id], [str(path_value)])
            fields = item.get("fields") if isinstance(item.get("fields"), dict) else {}
            if fields.get("record_class") == "immutable_snapshot":
                snapshot_value = fields.get("snapshot_path")
                snapshot_path = root / str(snapshot_value) if snapshot_value else None
                if snapshot_path is None or not snapshot_path.is_file():
                    add_issue(issues, "medium", "immutable_snapshot_missing", "Historical record lacks its immutable snapshot body.", [item_id], [str(snapshot_value or path_value)])
                else:
                    snapshot_digest = sha256_file(snapshot_path)
                    if fields.get("snapshot_digest") and snapshot_digest != fields.get("snapshot_digest"):
                        add_issue(issues, "medium", "immutable_snapshot_digest_mismatch", "Historical snapshot body differs from its immutable digest.", [item_id], [str(snapshot_value)])
            elif path.is_file():
                digest = sha256_file(path)
                if item.get("content_sha256") and digest and digest != item.get("content_sha256"):
                    add_issue(
                        issues,
                        "medium",
                        "digest_mismatch",
                        "Indexed artifact content changed since its latest upsert event.",
                        [item_id],
                        [str(path_value)],
                    )

        parent_id = item.get("parent_id")
        if parent_id and parent_id not in state:
            add_issue(issues, "high", "missing_parent", "Artifact references a parent_id that is not indexed.", [item_id, str(parent_id)])

        for link in item.get("links", []):
            if not isinstance(link, dict):
                continue
            target_id = link.get("id")
            if not target_id:
                add_issue(issues, "medium", "empty_link_target", "Artifact contains a link without a target id.", [item_id])
                continue
            if target_id == item_id:
                add_issue(issues, "low", "self_link", "Artifact links to itself.", [item_id])
            elif target_id not in state:
                add_issue(issues, "high", "broken_link", "Artifact links to an unknown id.", [item_id, str(target_id)])

    active_tasks = [
        item_id
        for item_id, item in state.items()
        if item.get("type") == "task" and item.get("status") == "active"
    ]
    if len(active_tasks) > 1:
        add_issue(issues, "high", "multiple_active_tasks", "More than one task is marked active.", active_tasks)
    if (root / "task.md").is_file() and not active_tasks:
        add_issue(issues, "high", "current_canonical_id_missing", "Current task.md has no active canonical task ID.", paths=["task.md"])

    active_packs = [
        item_id
        for item_id, item in state.items()
        if item.get("type") == "task_pack" and item.get("status") == "active"
    ]
    if len(active_packs) > 1:
        add_issue(issues, "high", "multiple_active_task_packs", "More than one task pack is marked active.", active_packs)

    active_by_path: dict[tuple[str, str], list[str]] = {}
    for item_id, item in state.items():
        path_value = item.get("path")
        status = str(item.get("status", ""))
        if path_value and status not in NON_ACTIVE_STATUSES:
            active_by_path.setdefault((str(item.get("type", "")), str(path_value)), []).append(item_id)
    for (item_type, path_value), ids in sorted(active_by_path.items()):
        if len(ids) > 1:
            add_issue(
                issues,
                "medium",
                "duplicate_active_path",
                f"Multiple non-closed {item_type} IDs point to the same path.",
                ids,
                [path_value],
            )

    task_like_types = {"task_pack", "candidate_task", "task_miss", "execution", "audit", "validation", "environment", "issue", "issue_resolution"}
    for item_id, item in state.items():
        if item.get("type") not in task_like_types or item.get("status") in NON_ACTIVE_STATUSES:
            continue
        links = item.get("links", [])
        has_task_ref = item.get("parent_id") in active_tasks or any(
            link.get("id") in active_tasks or link.get("rel") in {"run_for", "audit_for", "miss_for", "validates", "issue_for", "tracks_task"}
            for link in links
            if isinstance(link, dict)
        )
        if active_tasks and not has_task_ref:
            add_issue(issues, "low", "unlinked_task_artifact", "Artifact is not linked to an active task.", [item_id])

    state_paths = {
        (str(item.get("type", "")), str(item.get("path", "")), item.get("content_sha256"))
        for item in state.values()
        if item.get("path")
    }
    for item_type, path_value, _status, _title in discover_standard_artifacts(root):
        digest = sha256_file(root / path_value)
        if (item_type, path_value, digest) not in state_paths:
            add_issue(issues, "medium", "unindexed_artifact", "Workspace artifact is not represented by a matching index event.", paths=[path_value])

    index_jsonl = jsonl_path(root)
    index_md = markdown_path(root)
    if not index_md.exists():
        add_issue(issues, "medium", "missing_markdown_index", ".task/index.md is missing.")
    elif index_jsonl.exists() and index_md.stat().st_mtime < index_jsonl.stat().st_mtime:
        add_issue(issues, "low", "stale_markdown_index", ".task/index.md is older than .task/index.jsonl.")

    counts_by_type: dict[str, int] = {}
    for item in state.values():
        counts_by_type[str(item.get("type", "unknown"))] = counts_by_type.get(str(item.get("type", "unknown")), 0) + 1

    current_blocker_codes = {"current_canonical_id_missing", "multiple_active_tasks", "duplicate_active_path"}
    active_ids = set(active_tasks)
    current_surface_blockers = [
        issue
        for issue in issues
        if issue.get("code") in current_blocker_codes
        or (issue.get("code") == "broken_link" and active_ids.intersection(issue.get("ids") or []))
    ]
    historical_debt = [issue for issue in issues if issue not in current_surface_blockers]
    return {
        "format_version": INDEX_FORMAT_VERSION,
        "schema_version": INDEX_SCHEMA_VERSION,
        "workspace": str(root),
        "audited_at": now_iso(),
        "audit_evidence_status": "evaluated" if events or discover_standard_artifacts(root) else "not_evaluated_no_artifacts",
        "event_count": len(events),
        "artifact_count": len(state),
        "counts_by_type": counts_by_type,
        "issue_count": len(issues),
        "issues": issues,
        "current_surface_blockers": current_surface_blockers,
        "historical_debt": historical_debt,
    }


def write_audit_report(root: Path, audit: dict[str, Any]) -> Path:
    report_dir = task_dir(root) / "id_audit"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / f"{dt.datetime.now().strftime('%Y%m%d-%H%M%S-%f')}-id-consistency-audit.md"
    lines = [
        "# ID Consistency Audit",
        "",
        f"- Timestamp: {audit['audited_at']}",
        f"- Workspace: {audit['workspace']}",
        f"- Events: {audit['event_count']}",
        f"- Artifacts: {audit['artifact_count']}",
        f"- Issues: {audit['issue_count']}",
        "",
        "## Counts By Type",
        "",
    ]
    for item_type, count in sorted(audit["counts_by_type"].items()):
        lines.append(f"- {item_type}: {count}")
    lines.extend(["", "## Issues", ""])
    if audit["issues"]:
        for issue in audit["issues"]:
            ids = ", ".join(issue.get("ids", [])) or "N/A"
            paths = ", ".join(issue.get("paths", [])) or "N/A"
            lines.extend(
                [
                    f"- [{issue['severity']}] {issue['code']}: {issue['message']}",
                    f"  IDs: {ids}",
                    f"  Paths: {paths}",
                ]
            )
    else:
        lines.append("- None")
    atomic_write_text(report_path, "\n".join(lines).rstrip() + "\n")
    return report_path


def severity_counts(issues: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for issue in issues:
        severity = str(issue.get("severity") or "unknown")
        counts[severity] = counts.get(severity, 0) + 1
    return counts


def issue_matches_focus(issue: dict[str, Any], focus_paths: list[str]) -> bool:
    if not focus_paths:
        return True
    paths = [str(path) for path in issue.get("paths", []) if path is not None]
    ids = [str(item_id) for item_id in issue.get("ids", []) if item_id is not None]
    haystack = paths + ids
    for focus in focus_paths:
        focus = focus.strip()
        if not focus:
            continue
        for value in haystack:
            if value == focus or value.startswith(focus.rstrip("/") + "/") or focus in value:
                return True
    return False


def summarize_audit(audit: dict[str, Any], focus_paths: list[str], limit: int = 20) -> dict[str, Any]:
    issues = [issue for issue in audit.get("issues", []) if isinstance(issue, dict)]
    focused = [issue for issue in issues if issue_matches_focus(issue, focus_paths)]
    return {
        "workspace": audit.get("workspace"),
        "audited_at": audit.get("audited_at"),
        "summary_only": True,
        "focus_paths": [path for path in focus_paths if path],
        "event_count": audit.get("event_count"),
        "artifact_count": audit.get("artifact_count"),
        "counts_by_type": audit.get("counts_by_type", {}),
        "issue_count": audit.get("issue_count", len(issues)),
        "severity_counts": severity_counts(issues),
        "focused_issue_count": len(focused),
        "focused_severity_counts": severity_counts(focused),
        "focused_issues": focused[:limit],
        "omitted_issue_count": max(0, len(issues) - min(len(focused), limit)) if focus_paths else max(0, len(issues) - limit),
        "historical_debt_note": "summary_only preserves global counts while limiting emitted issues to focus paths; run audit without --summary-only for the full issue list.",
    }


def cmd_init(args: argparse.Namespace) -> None:
    root = Path(args.root).resolve()
    result = rebuild_markdown(root)
    print(json.dumps({"initialized": True, "evidence_status": "not_evaluated", **result}, ensure_ascii=False, indent=2))


def cmd_scan(args: argparse.Namespace) -> None:
    root = Path(args.root).resolve()
    print(json.dumps(scan_artifacts(root), ensure_ascii=False, indent=2))


def cmd_add(args: argparse.Namespace) -> None:
    root = Path(args.root).resolve()
    result = upsert_item(
        root,
        args.type,
        args.path,
        args.status,
        title=args.title,
        item_id=args.id,
        parent_id=args.parent_id,
        links=parse_links(args.link),
        fields=parse_key_value(args.field),
        note=args.note,
        replace_existing=args.replace,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


def cmd_link(args: argparse.Namespace) -> None:
    root = Path(args.root).resolve()
    try:
        result = link_item(root, args.source_id, parse_links(args.link), args.note)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    print(json.dumps(result, ensure_ascii=False, indent=2))


def cmd_rebuild(args: argparse.Namespace) -> None:
    root = Path(args.root).resolve()
    print(json.dumps({"ok": True, **rebuild_markdown(root)}, ensure_ascii=False, indent=2))


def cmd_audit(args: argparse.Namespace) -> None:
    root = Path(args.root).resolve()
    audit = audit_index(root)
    if args.write_report:
        report_path = write_audit_report(root, audit)
        result = upsert_item(
            root,
            "audit",
            rel_path(root, report_path),
            "logged" if audit["issue_count"] == 0 else "partial",
            title="ID Consistency Audit",
            note=f"ID audit found {audit['issue_count']} issue(s).",
        )
        audit["report_path"] = rel_path(root, report_path)
        audit["audit_id"] = result["id"]
    if args.summary_only:
        summary = summarize_audit(audit, args.focus_path or [])
        if audit.get("report_path"):
            summary["report_path"] = audit["report_path"]
            summary["audit_id"] = audit.get("audit_id")
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(audit, ensure_ascii=False, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Maintain .task/index.jsonl and .task/index.md.")
    parser.add_argument("--root", default=".", help="Workspace root.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Initialize and rebuild the task state index.")
    init_parser.set_defaults(func=cmd_init)

    scan_parser = subparsers.add_parser("scan", help="Index standard task artifacts in the workspace.")
    scan_parser.set_defaults(func=cmd_scan)

    add_parser = subparsers.add_parser("add", help="Append an upsert event for one artifact.")
    add_parser.add_argument("--type", required=True, help="Artifact type.")
    add_parser.add_argument("--path", required=True, help="Workspace-relative artifact path.")
    add_parser.add_argument("--status", required=True, choices=sorted(LIFECYCLE_STATUSES), help="Lifecycle status.")
    add_parser.add_argument("--title", help="Short title.")
    add_parser.add_argument("--id", help="Explicit artifact ID.")
    add_parser.add_argument("--parent-id", help="Parent artifact ID.")
    add_parser.add_argument("--link", action="append", default=[], help="Relationship in rel:id or rel=id form.")
    add_parser.add_argument("--field", action="append", default=[], help="Structured metadata as key=value.")
    add_parser.add_argument("--note", help="Concise factual note.")
    add_parser.add_argument("--replace", action="store_true", help="Create a new semantic artifact ID and supersede the active same-path record.")
    add_parser.set_defaults(func=cmd_add)

    link_parser = subparsers.add_parser("link", help="Append relationship links to an existing artifact.")
    link_parser.add_argument("--source-id", required=True, help="Source artifact ID.")
    link_parser.add_argument("--link", action="append", required=True, help="Relationship in rel:id or rel=id form.")
    link_parser.add_argument("--note", help="Concise factual note.")
    link_parser.set_defaults(func=cmd_link)

    rebuild_parser = subparsers.add_parser("rebuild", help="Regenerate .task/index.md from JSONL.")
    rebuild_parser.set_defaults(func=cmd_rebuild)

    audit_parser = subparsers.add_parser("audit", help="Audit global ID consistency; optionally write and index a report.")
    audit_parser.add_argument("--write-report", action="store_true", help="Write .task/id_audit/*.md and index it.")
    audit_parser.add_argument("--summary-only", action="store_true", help="Print compact counts and focused issues instead of the full historical issue list.")
    audit_parser.add_argument("--focus-path", action="append", default=[], help="Limit emitted issues to workspace-relative paths or IDs while preserving global counts.")
    audit_parser.set_defaults(func=cmd_audit)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
