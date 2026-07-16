#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
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

TASK_STATE_MIGRATION_SCRIPTS = Path(__file__).resolve().parent
if str(TASK_STATE_MIGRATION_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(TASK_STATE_MIGRATION_SCRIPTS))

from task_state_migration import (  # noqa: E402
    load_sealed_events_if_present,
    validate_current_suffix_event,
)

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
TASK_SCAN_PRESERVED_NONEXECUTABLE_STATUSES = {
    "complete",
    "completed",
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


def _infer_legacy_event_kind(event: dict[str, Any]) -> str | None:
    """Infer only legacy shapes whose discriminator is unambiguous."""
    if all(isinstance(event.get(field), str) and event[field].strip() for field in ("type", "status", "path")):
        return "upsert"
    if isinstance(event.get("links"), list) and not any(field in event for field in ("type", "status", "path")):
        return "link"
    return None


def normalize_and_validate_event(
    event: Any,
    line_no: int,
    source: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if not isinstance(event, dict):
        raise ValueError(f"Malformed task-state JSONL {source} line {line_no}: expected a JSON object")

    # Detect the row version before applying the current event discriminator.
    # Versionless/format-v1 rows are legacy-compatible; current rows must carry
    # an explicit supported discriminator.
    raw_format_version = event.get("format_version")
    raw_schema_version = event.get("schema_version")
    format_version = _version(raw_format_version, field="format_version", line_no=line_no, source=source, default=1)
    schema_version = _version(raw_schema_version, field="schema_version", line_no=line_no, source=source, default=1)
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

    legacy_row = raw_format_version is None or format_version < INDEX_FORMAT_VERSION
    if not legacy_row and raw_schema_version is None:
        raise ValueError(
            f"Malformed task-state JSONL {source} line {line_no}: current format requires schema_version"
        )
    event_kind = event.get("event")
    normalized = dict(event)
    discriminator_inferred = False
    if event_kind is None and legacy_row:
        event_kind = _infer_legacy_event_kind(event)
        if event_kind is not None:
            normalized["event"] = event_kind
            discriminator_inferred = True
    if event_kind not in SUPPORTED_EVENT_KINDS:
        raise ValueError(f"Malformed task-state JSONL {source} line {line_no}: unsupported event {event_kind!r}")
    for field in ("id", "updated_at"):
        if not isinstance(normalized.get(field), str) or not normalized[field].strip():
            raise ValueError(f"Malformed task-state JSONL {source} line {line_no}: missing non-empty {field}")
    status = normalized.get("status")
    if status is not None and status not in LIFECYCLE_STATUSES:
        raise ValueError(f"Malformed task-state JSONL {source} line {line_no}: unsupported lifecycle status {status!r}")
    if "fields" in normalized and not isinstance(normalized.get("fields"), dict):
        raise ValueError(f"Malformed task-state JSONL {source} line {line_no}: fields must be an object")
    fields = normalized.get("fields") if isinstance(normalized.get("fields"), dict) else {}
    if "link_tombstones" in fields:
        tombstones = fields.get("link_tombstones")
        if not isinstance(tombstones, list) or any(
            not isinstance(link, dict) or not isinstance(link.get("rel"), str) or not isinstance(link.get("id"), str)
            for link in tombstones
        ):
            raise ValueError(f"Malformed task-state JSONL {source} line {line_no}: invalid link_tombstones")
    if "links" in normalized:
        links = normalized.get("links")
        if not isinstance(links, list):
            raise ValueError(f"Malformed task-state JSONL {source} line {line_no}: links must be a list")
        for link in links:
            if not isinstance(link, dict) or not isinstance(link.get("rel"), str) or not isinstance(link.get("id"), str):
                raise ValueError(f"Malformed task-state JSONL {source} line {line_no}: invalid relationship object")
    return normalized, {
        "line_no": line_no,
        "raw_format_version": format_version,
        "raw_schema_version": schema_version,
        "normalized_schema_version": INDEX_SCHEMA_VERSION,
        "normalized_event_kind": event_kind,
        "row_identity": normalized.get("id"),
        "migration_status": "normalized_legacy" if legacy_row else "current",
        "discriminator_inferred": discriminator_inferred,
        "malformed_reason": None,
        "projection_impact": "independent",
    }


def validate_event(event: Any, line_no: int, source: Path) -> dict[str, Any]:
    normalized, _read_result = normalize_and_validate_event(event, line_no, source)
    return normalized


def _safe_malformed_reason(exc: Exception, source: Path) -> str:
    """Return a bounded reason code without copying row content or locators."""
    if isinstance(exc, UnicodeDecodeError):
        return "invalid_utf8"
    if isinstance(exc, json.JSONDecodeError):
        return "malformed_json"
    message = str(exc).replace(str(source), source.name)
    if "format_version" in message:
        return "invalid_or_unsupported_format_version"
    if "schema_version" in message:
        return "invalid_or_unsupported_schema_version"
    if "unsupported event" in message:
        return "invalid_event_discriminator"
    if "lifecycle status" in message:
        return "invalid_lifecycle_status"
    if "relationship object" in message:
        return "invalid_relationship_contract"
    if "expected a JSON object" in message:
        return "non_object_row"
    return "invalid_row_contract"


def _current_projection_hint(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    return (
        value.get("type") == "task" and value.get("status") == "active"
    ) or value.get("path") == "task.md"


def _lineage_identities(value: Any) -> list[str]:
    if not isinstance(value, dict):
        return []
    identities = {
        str(value.get(field)).strip()
        for field in ("id", "parent_id")
        if isinstance(value.get(field), str) and str(value.get(field)).strip()
    }
    for link in value.get("links") or []:
        if isinstance(link, dict) and isinstance(link.get("id"), str) and link["id"].strip():
            identities.add(link["id"].strip())
    fields = value.get("fields") if isinstance(value.get("fields"), dict) else {}
    for field in ("canonical_id", "transaction_id"):
        if isinstance(fields.get(field), str) and fields[field].strip():
            identities.add(fields[field].strip())
    return sorted(identities)


def _load_events_for_audit_unlocked(root: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Read every row for audit while quarantining malformed history.

    Mutation paths continue to use `_load_events_unlocked` and therefore fail
    closed on any malformed or unsupported row.
    """
    _ensure_index_unlocked(root)
    sealed = load_sealed_events_if_present(root)
    if sealed is not None:
        return sealed
    events: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []
    source = jsonl_path(root)
    with source.open("rb") as handle:
        for line_no, raw_line in enumerate(handle, start=1):
            if not raw_line.strip():
                continue
            value: Any = None
            try:
                line = raw_line.decode("utf-8")
                value = json.loads(line)
                event, result = normalize_and_validate_event(value, line_no, source)
            except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
                row_identity = value.get("id") if isinstance(value, dict) and isinstance(value.get("id"), str) else None
                results.append(
                    {
                        "line_no": line_no,
                        "raw_format_version": value.get("format_version", 1) if isinstance(value, dict) else None,
                        "raw_schema_version": value.get("schema_version", 1) if isinstance(value, dict) else None,
                        "normalized_schema_version": None,
                        "normalized_event_kind": None,
                        "row_identity": row_identity,
                        "migration_status": "malformed_quarantined",
                        "malformed_reason": _safe_malformed_reason(exc, source),
                        "projection_impact": "affected" if row_identity else "unknown",
                        "_lineage_ids": _lineage_identities(value),
                        "_current_projection_hint": _current_projection_hint(value),
                    }
                )
                continue
            events.append(event)
            results.append(result)
    return events, results


def load_events_for_audit(root: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    with index_lock(root):
        return _load_events_for_audit_unlocked(root)


def _load_events_unlocked(root: Path) -> list[dict[str, Any]]:
    _ensure_index_unlocked(root)
    return _read_existing_events(root)


def _read_existing_events(root: Path) -> list[dict[str, Any]]:
    """Read and validate an existing index without creating workspace state."""

    sealed = load_sealed_events_if_present(root)
    if sealed is not None:
        events, _read_results = sealed
        return [validate_event(event, line_no, jsonl_path(root)) for line_no, event in enumerate(events, start=1)]
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


def load_events_read_only(root: Path) -> tuple[list[dict[str, Any]], str | None]:
    """Read the current ledger without creating a lock, index, or render."""

    root = root.resolve()
    source = jsonl_path(root)
    if not source.is_file():
        return [], None
    before = sha256_file(source)
    events = _read_existing_events(root)
    after = sha256_file(source)
    if before != after:
        raise ValueError("Task-state index changed during read-only scan preflight")
    return events, before


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
            tombstones = event["fields"].get("link_tombstones")
            if isinstance(tombstones, list):
                removed = {
                    (link.get("rel"), link.get("id"))
                    for link in tombstones
                    if isinstance(link, dict)
                }
                current["links"] = [
                    link for link in current.setdefault("links", [])
                    if (link.get("rel"), link.get("id")) not in removed
                ]
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


def normalize_bounded_markdown_scalar(value: str) -> str:
    """Strip one safe, balanced inline-code wrapper from scalar metadata."""
    normalized = value.strip()
    if (
        len(normalized) >= 3
        and normalized.startswith("`")
        and normalized.endswith("`")
        and normalized.count("`") == 2
        and normalized[1:-1].strip()
    ):
        return normalized[1:-1].strip()
    return normalized


def advice_pointer_file(path: Path) -> bool:
    fields = extract_advice_fields(path)
    return str(fields.get("not_active_record", "")).casefold() == "true"


def select_external_advice_scan_id(
    root: Path, state: dict[str, dict[str, Any]], path_value: str, advice_id: str,
) -> tuple[str, list[str]]:
    """Select canonical advice identity and bounded pointer aliases to retire."""
    exact = state.get(advice_id)
    if exact is not None:
        if exact.get("type") != "external_advice":
            raise ValueError(
                f"Canonical advice id {advice_id!r} is already bound to another artifact path"
            )
        exact_path = str(exact.get("path") or "")
        if exact_path != path_value:
            old_file = root / exact_path
            if old_file.exists() and not advice_pointer_file(old_file):
                raise ValueError(
                    f"Canonical advice id {advice_id!r} is already bound to another artifact path"
                )

    pointer_aliases: list[str] = []
    active_cross_path_aliases: list[str] = []
    for item_id, item in state.items():
        if item_id == advice_id:
            continue
        existing_fields = item.get("fields") if isinstance(item.get("fields"), dict) else {}
        existing_advice_id = normalize_bounded_markdown_scalar(str(existing_fields.get("advice_id") or ""))
        if not (
            item.get("type") == "external_advice"
            and existing_advice_id == advice_id
            and item.get("path") != path_value
            and item.get("status") not in NON_ACTIVE_STATUSES
        ):
            continue
        alias_file = root / str(item.get("path") or "")
        if alias_file.is_file() and advice_pointer_file(alias_file):
            pointer_aliases.append(item_id)
        else:
            active_cross_path_aliases.append(item_id)
    if active_cross_path_aliases:
        raise ValueError(
            f"Canonical advice id {advice_id!r} has an active cross-path alias"
        )
    return advice_id, sorted(pointer_aliases)


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


def validate_completed_task_alias_batch(
    existing_state: dict[str, dict[str, Any]],
    events: list[dict[str, Any]],
) -> None:
    event_ids = {
        str(event.get("id"))
        for event in events
        if isinstance(event.get("id"), str)
    }
    prospective_state = merge_state([*existing_state.values(), *events])
    for item_id, existing in existing_state.items():
        existing_fields = existing.get("fields") if isinstance(existing.get("fields"), dict) else {}
        completed_alias = bool(
            existing.get("type") == "task"
            and existing.get("path") == "task.md"
            and existing.get("status") in TASK_SCAN_PRESERVED_NONEXECUTABLE_STATUSES
            and existing_fields.get("record_class") == "mutable_alias"
            and existing_fields.get("canonical_id") == item_id
        )
        if not completed_alias or item_id not in event_ids:
            continue
        current = prospective_state[item_id]
        if current.get("content_sha256") != existing.get("content_sha256"):
            raise ValueError(
                "A completed current task alias cannot change body under the same identity"
            )
        current_fields = current.get("fields") if isinstance(current.get("fields"), dict) else {}
        if (
            current.get("status") in TASK_SCAN_PRESERVED_NONEXECUTABLE_STATUSES
            and current_fields.get("record_class") == "mutable_alias"
            and current_fields.get("canonical_id") == item_id
        ):
            continue
        successor_ids = {
            str(link.get("id"))
            for link in current.get("links") or []
            if isinstance(link, dict) and link.get("rel") == "superseded_by" and link.get("id")
        }
        valid_successor = False
        for successor_id in successor_ids.intersection(event_ids):
            if successor_id == item_id:
                continue
            successor = prospective_state.get(successor_id) or {}
            successor_fields = successor.get("fields") if isinstance(successor.get("fields"), dict) else {}
            supersedes = {
                str(link.get("id"))
                for link in successor.get("links") or []
                if isinstance(link, dict) and link.get("rel") == "supersedes" and link.get("id")
            }
            if (
                current.get("status") == "superseded"
                and current_fields.get("record_class") == "immutable_snapshot"
                and successor.get("type") == "task"
                and successor.get("path") == "task.md"
                and successor_fields.get("record_class") == "mutable_alias"
                and successor_fields.get("canonical_id") == successor_id
                and item_id in supersedes
            ):
                valid_successor = True
                break
        if not valid_successor:
            raise ValueError(
                "A completed task identity can change lifecycle only in one batch with a distinct linked successor"
            )


def _append_events_unlocked(root: Path, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    existing = _load_events_unlocked(root)
    existing_state = merge_state(existing)
    known_ids = set(existing_state)
    versioned = [versioned_event(event) for event in events]
    for offset, event in enumerate(versioned, start=1):
        validate_event(event, offset, jsonl_path(root))
        validate_current_suffix_event(event, known_ids)
    validate_completed_task_alias_batch(existing_state, versioned)
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


def _generated_at_from_markdown(payload: bytes) -> str | None:
    try:
        lines = payload.decode("utf-8").splitlines()
    except UnicodeDecodeError:
        return None
    prefix = "- Generated: "
    matches = [line[len(prefix) :].strip() for line in lines if line.startswith(prefix)]
    if len(matches) != 1 or not matches[0]:
        return None
    try:
        parsed = dt.datetime.fromisoformat(matches[0].replace("Z", "+00:00"))
    except ValueError:
        return None
    return matches[0] if parsed.tzinfo is not None else None


def _render_markdown_payload(state: dict[str, dict[str, Any]], generated_at: str) -> bytes:
    groups: dict[str, list[dict[str, Any]]] = {}
    for item in state.values():
        groups.setdefault(str(item.get("type", "unknown")), []).append(item)

    lines = [
        "# Task State Index",
        "",
        f"- Generated: {generated_at}",
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

    return ("\n".join(lines).rstrip() + "\n").encode("utf-8")


def _markdown_projection_matches(root: Path, state: dict[str, dict[str, Any]]) -> bool:
    path = markdown_path(root)
    if not path.is_file():
        return False
    existing = path.read_bytes()
    generated_at = _generated_at_from_markdown(existing)
    return bool(generated_at and existing == _render_markdown_payload(state, generated_at))


def _rebuild_markdown_unlocked(root: Path, events: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    state = merge_state(events if events is not None else _load_events_unlocked(root))
    path = markdown_path(root)
    existing = path.read_bytes() if path.is_file() else b""
    generated_at = _generated_at_from_markdown(existing) or now_iso()
    payload = _render_markdown_payload(state, generated_at)
    changed = payload != existing
    if changed:
        generated_at = now_iso()
        payload = _render_markdown_payload(state, generated_at)
        atomic_write_bytes(path, payload)
    return {
        "index_md": rel_path(root, path),
        "index_md_changed": changed,
        "generated_at": generated_at,
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
    retire_alias_ids: list[str] | None = None,
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
        existing_exact = state.get(item_id) if provided_item_id and item_id is not None else None
        existing_exact_fields = (
            existing_exact.get("fields")
            if isinstance(existing_exact, dict)
            and isinstance(existing_exact.get("fields"), dict)
            else {}
        )
        completed_exact_alias = bool(
            item_type == "task"
            and path_value == "task.md"
            and isinstance(existing_exact, dict)
            and existing_exact.get("status") in TASK_SCAN_PRESERVED_NONEXECUTABLE_STATUSES
            and existing_exact_fields.get("record_class") == "mutable_alias"
            and existing_exact_fields.get("canonical_id") == item_id
        )
        if completed_exact_alias:
            if existing_exact.get("content_sha256") != digest:
                raise ValueError(
                    "A completed current task alias changed body without a distinct successor identity"
                )
            if status not in TASK_SCAN_PRESERVED_NONEXECUTABLE_STATUSES:
                raise ValueError(
                    "A completed task identity cannot be reactivated; create a distinct successor identity"
                )
        canonical_advice_reactivation = bool(
            explicit_replacement
            and item_type == "external_advice"
            and replace_existing is False
            and isinstance(fields, dict)
            and fields.get("advice_id") == item_id
            and isinstance(existing_exact, dict)
            and existing_exact.get("type") == "external_advice"
            and existing_exact.get("path") == path_value
            and existing_exact.get("status") == "superseded"
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

        if explicit_replacement and item_id in state and not canonical_advice_reactivation:
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
        for alias_id in sorted(set(retire_alias_ids or [])):
            alias = state.get(alias_id)
            if (
                alias_id == item_id
                or not isinstance(alias, dict)
                or alias.get("type") != "external_advice"
                or alias.get("status") in NON_ACTIVE_STATUSES
            ):
                raise ValueError(f"Invalid external advice pointer alias retirement: {alias_id!r}")
            if all(existing_id != alias_id for existing_id, _existing in superseded_records):
                superseded_records.append((alias_id, alias))
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
                "replacement_reason": (
                    "canonical_advice_reactivation"
                    if canonical_advice_reactivation
                    else "explicit_id"
                    if explicit_replacement
                    else "semantic_replacement"
                ),
            }
            if canonical_advice_reactivation:
                lifecycle_transition_result["canonical_reactivated"] = True

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
        "not_active_record",
    }
    for raw_line in lines:
        match = re.match(r"^-\s+([A-Za-z0-9_]+):\s*(.*)$", raw_line.rstrip())
        if not match:
            continue
        key, value = match.groups()
        if key in scalar_keys and value:
            fields[key] = normalize_bounded_markdown_scalar(value)
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
        ordered = sorted(
            (item for item in items if isinstance(item, dict)),
            key=lambda item: item.get("order") if isinstance(item.get("order"), int) else 10**9,
        )
        if ordered:
            promotion = ordered[0].get("promotion")
            if isinstance(promotion, dict):
                for key in ("promotion_origin", "initial_selection_receipt_ref"):
                    if promotion.get(key) is not None:
                        fields[f"initial_{key}"] = str(promotion.get(key))
                receipt = promotion.get("initial_selection_receipt")
                if isinstance(receipt, dict):
                    for key in (
                        "pack_creation_snapshot_ref",
                        "authority_receipt_ref",
                        "authority_receipt_sha256",
                        "authority_mode",
                        "historical_selection_authority_status",
                    ):
                        if receipt.get(key) is not None:
                            fields[f"initial_{key}"] = str(receipt.get(key))
                normalization = promotion.get("provenance_normalization")
                if isinstance(normalization, dict):
                    fields["initial_normalization_mode"] = str(normalization.get("mode") or "")
                    fields["initial_historical_authority_verdict"] = str(
                        normalization.get("historical_authority_verdict") or ""
                    )
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
            if advice_pointer_file(path):
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


def scan_artifacts(root: Path, *, dry_run: bool = False) -> dict[str, Any]:
    root = root.resolve()
    artifacts = discover_standard_artifacts(root)
    for canonical_path in (jsonl_path(root), markdown_path(root)):
        if canonical_path.exists() and not canonical_path.is_file():
            raise ValueError(f"Task-state canonical path is not a regular file: {canonical_path}")
    had_jsonl = jsonl_path(root).is_file()
    had_markdown = markdown_path(root).is_file()
    if not dry_run and not artifacts and not had_jsonl and not had_markdown:
        return {
            "mode": "apply",
            "mutation_performed": False,
            "indexed_events": 0,
            "events": [],
            "index_md": None,
            "index_md_changed": False,
            "artifact_count": 0,
            "format_version": INDEX_FORMAT_VERSION,
            "schema_version": INDEX_SCHEMA_VERSION,
            "scan_evidence_status": "not_evaluated_no_artifacts",
        }
    if not dry_run:
        artifact_anchor = [
            (item_type, path_value, status, title, sha256_file(root / path_value))
            for item_type, path_value, status, title in artifacts
        ]
        preflight = scan_artifacts(root, dry_run=True)
        current_artifacts = discover_standard_artifacts(root)
        current_anchor = [
            (item_type, path_value, status, title, sha256_file(root / path_value))
            for item_type, path_value, status, title in current_artifacts
        ]
        if current_anchor != artifact_anchor:
            raise ValueError("Workspace artifacts changed during task-state scan preflight")
        if preflight.get("source_index_sha256") != sha256_file(jsonl_path(root)):
            raise ValueError("Task-state index changed after scan preflight")
        artifacts = current_artifacts
    source_index_sha256: str | None = None
    if dry_run:
        events, source_index_sha256 = load_events_read_only(root)
    else:
        ensure_index(root)
        events = load_events(root)
    added: list[dict[str, Any]] = []
    pending: list[dict[str, Any]] = []
    markdown_changed_during_scan = False
    state = merge_state(events)
    projected_state = copy.deepcopy(state)
    projected_markdown_forced = False
    projected_timestamp = now_iso()
    projected_pack_id_paths: dict[str, str] = {}
    for projected_item in projected_state.values():
        projected_fields = projected_item.get("fields") if isinstance(projected_item.get("fields"), dict) else {}
        projected_pack_id = str(projected_fields.get("pack_id") or "")
        projected_path = str(projected_item.get("path") or "")
        if projected_item.get("type") != "task_pack" or not projected_pack_id or not projected_path:
            continue
        previous_path = projected_pack_id_paths.setdefault(projected_pack_id, projected_path)
        if previous_path != projected_path:
            raise ValueError(
                f"Task pack id {projected_pack_id!r} is already bound to another artifact path"
            )

    def maybe_upsert(item_type: str, path_value: str, status: str, title: str) -> None:
        nonlocal markdown_changed_during_scan, projected_markdown_forced, state
        identity_state = projected_state if dry_run else state
        digest = sha256_file(root / path_value)
        fields = None
        retire_alias_ids: list[str] = []
        item_id = stable_path_id(identity_state, item_type, path_value)
        if item_type in {"schema_contract", "schema_map"}:
            fields = extract_schema_fields(root / path_value)
        elif item_type == "task_pack":
            fields = extract_task_pack_fields(root / path_value)
            if fields.get("render_path"):
                fields["render_path"] = rel_path(root, Path(fields["render_path"]))
            pack_id = fields.get("pack_id") if fields else None
            if pack_id:
                previous_path = projected_pack_id_paths.setdefault(str(pack_id), path_value)
                if previous_path != path_value:
                    raise ValueError(
                        f"Task pack id {pack_id!r} is already bound to another artifact path"
                    )
                for existing_id, existing in identity_state.items():
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
                item_id, retire_alias_ids = select_external_advice_scan_id(
                    root, identity_state, path_value, advice_id,
                )
        existing = identity_state.get(item_id) if item_id else None
        existing_fields = existing.get("fields") if isinstance(existing, dict) and isinstance(existing.get("fields"), dict) else {}
        completed_mutable_alias = bool(
            item_type == "task"
            and path_value == "task.md"
            and existing
            and existing.get("status") in TASK_SCAN_PRESERVED_NONEXECUTABLE_STATUSES
            and existing_fields.get("record_class") == "mutable_alias"
            and existing_fields.get("canonical_id") == item_id
        )
        if completed_mutable_alias:
            if existing.get("content_sha256") == digest:
                status = str(existing.get("status"))
            else:
                raise ValueError(
                    "A non-executable current task alias changed body without an explicit lifecycle switch"
                )
        if (
            existing
            and existing.get("path") == path_value
            and existing.get("content_sha256") == digest
            and existing.get("status") == status
            and existing.get("title") == title
            and all(existing_fields.get(key) == value for key, value in (fields or {}).items())
        ):
            return
        if dry_run:
            pending.append(
                {
                    "type": item_type,
                    "path": path_value,
                    "status": status,
                    "title": title,
                    "stable_id": item_id,
                    "identity_status": "existing" if item_id else "would_allocate_on_apply",
                    "content_sha256": digest,
                }
            )
            if item_id:
                projected = copy.deepcopy(projected_state.get(item_id) or {})
                projected.update(
                    {
                        "type": item_type,
                        "status": status,
                        "path": path_value,
                        "title": title,
                        "updated_at": projected_timestamp,
                        "content_sha256": digest,
                    }
                )
                if fields:
                    projected.setdefault("fields", {}).update(fields)
                projected_state[item_id] = projected
                for alias_id in retire_alias_ids:
                    if alias_id in projected_state:
                        projected_state[alias_id]["status"] = "superseded"
                        projected_state[alias_id]["updated_at"] = projected_timestamp
                        projected_markdown_forced = True
            if not item_id:
                projected_markdown_forced = True
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
            retire_alias_ids=retire_alias_ids,
        )
        added.append(result["event"])
        markdown_changed_during_scan = markdown_changed_during_scan or bool(result.get("index_md_changed"))
        state = merge_state(load_events(root))

    for item_type, path_value, status, title in artifacts:
        maybe_upsert(item_type, path_value, status, title)

    if dry_run:
        markdown_matches = _markdown_projection_matches(root, projected_state)
        has_index_context = bool(artifacts) or source_index_sha256 is not None or markdown_path(root).is_file()
        index_jsonl_would_change = bool(pending) or (source_index_sha256 is None and has_index_context)
        markdown_would_change = has_index_context and (projected_markdown_forced or not markdown_matches)
        if sha256_file(jsonl_path(root)) != source_index_sha256:
            raise ValueError("Task-state index changed during read-only scan planning")
        return {
            "mode": "dry_run",
            "mutation_performed": False,
            "indexed_events": 0,
            "events": [],
            "planned_artifact_updates": len(pending),
            "pending_artifacts": pending,
            "would_change": bool(pending) or index_jsonl_would_change or markdown_would_change,
            "index_jsonl_would_change": index_jsonl_would_change,
            "index_md_would_change": markdown_would_change,
            "source_index_sha256": source_index_sha256,
            "source_index_md_sha256": sha256_file(markdown_path(root)),
            "scan_evidence_status": "evaluated" if artifacts else "not_evaluated_no_artifacts",
        }

    rebuild = rebuild_markdown(root)
    rebuild["index_md_changed"] = markdown_changed_during_scan or bool(rebuild.get("index_md_changed"))
    index_created = not had_jsonl and jsonl_path(root).is_file()
    return {
        "mode": "apply",
        "mutation_performed": index_created or bool(added) or bool(rebuild.get("index_md_changed")),
        "index_jsonl_changed": index_created or bool(added),
        "indexed_events": len(added),
        "events": added,
        "scan_evidence_status": "evaluated" if artifacts else "not_evaluated_no_artifacts",
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
    events, read_results = load_events_for_audit(root)
    state = merge_state(events)
    issues: list[dict[str, Any]] = []
    active_tasks = [
        item_id
        for item_id, item in state.items()
        if item.get("type") == "task" and item.get("status") == "active"
    ]
    current_task_digest = sha256_file(root / "task.md") if (root / "task.md").is_file() else None
    current_task_alias_ids = [
        item_id
        for item_id, item in state.items()
        if item.get("type") == "task"
        and item.get("path") == "task.md"
        and item.get("content_sha256") == current_task_digest
        and (
            item.get("status") == "active"
            or (
                item.get("status") in TASK_SCAN_PRESERVED_NONEXECUTABLE_STATUSES
                and isinstance(item.get("fields"), dict)
                and item["fields"].get("record_class") == "mutable_alias"
                and item["fields"].get("canonical_id") == item_id
            )
        )
    ]
    current_surface_ids = set(current_task_alias_ids)
    while True:
        prior_size = len(current_surface_ids)
        for item_id, item in state.items():
            links = item.get("links") if isinstance(item.get("links"), list) else []
            if item_id in current_surface_ids:
                if isinstance(item.get("parent_id"), str) and item.get("parent_id"):
                    current_surface_ids.add(str(item["parent_id"]))
                current_surface_ids.update(
                    str(link.get("id"))
                    for link in links
                    if isinstance(link, dict) and isinstance(link.get("id"), str) and link.get("id")
                )
            if item.get("parent_id") in current_surface_ids or any(
                isinstance(link, dict) and link.get("id") in current_surface_ids for link in links
            ):
                current_surface_ids.add(item_id)
        if len(current_surface_ids) == prior_size:
            break

    malformed_results = [result for result in read_results if result.get("migration_status") == "malformed_quarantined"]
    legacy_results = [result for result in read_results if result.get("migration_status") == "normalized_legacy"]
    projection_not_evaluated_ids: set[str] = set()
    unknown_projection_impact = False
    for result in malformed_results:
        lineage_ids = {str(value) for value in result.pop("_lineage_ids", []) if str(value)}
        current_projection_hint = result.pop("_current_projection_hint", False) is True
        row_identity = str(result.get("row_identity") or "")
        if current_projection_hint:
            result["projection_impact"] = "affected"
            if row_identity:
                projection_not_evaluated_ids.add(row_identity)
            else:
                unknown_projection_impact = True
                projection_not_evaluated_ids.update(current_surface_ids)
        elif not row_identity:
            result["projection_impact"] = "unknown"
            unknown_projection_impact = True
            projection_not_evaluated_ids.update(current_surface_ids)
        elif row_identity in current_surface_ids or lineage_ids.intersection(current_surface_ids):
            result["projection_impact"] = "affected"
            projection_not_evaluated_ids.add(row_identity)
            projection_not_evaluated_ids.update(lineage_ids.intersection(current_surface_ids))
        else:
            result["projection_impact"] = "independent"
        add_issue(
            issues,
            "medium",
            "malformed_index_row",
            f"Index row {result.get('line_no')} was quarantined; projection impact is {result['projection_impact']}.",
            [row_identity] if row_identity else [],
        )

    current_projection_status = "evaluated"
    if projection_not_evaluated_ids or (unknown_projection_impact and ((root / "task.md").is_file() or current_surface_ids)):
        current_projection_status = "not_evaluated"
        add_issue(
            issues,
            "high",
            "current_projection_not_evaluated",
            "Malformed index history may affect the current projection; do not consume current traceability as pass.",
            sorted(projection_not_evaluated_ids),
            ["task.md"] if not projection_not_evaluated_ids and (root / "task.md").is_file() else [],
        )

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

    if len(active_tasks) > 1:
        add_issue(issues, "high", "multiple_active_tasks", "More than one task is marked active.", active_tasks)
    if (root / "task.md").is_file() and not current_task_alias_ids:
        add_issue(issues, "high", "current_canonical_id_missing", "Current task.md has no current canonical task ID.", paths=["task.md"])

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
        has_task_ref = item.get("parent_id") in current_task_alias_ids or any(
            link.get("id") in current_task_alias_ids or link.get("rel") in {"run_for", "audit_for", "miss_for", "validates", "issue_for", "tracks_task"}
            for link in links
            if isinstance(link, dict)
        )
        if current_task_alias_ids and not has_task_ref:
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

    current_blocker_codes = {
        "current_canonical_id_missing",
        "multiple_active_tasks",
        "current_projection_not_evaluated",
    }
    active_ids = set(current_task_alias_ids)
    designated_surface_ids = active_ids | set(active_packs)
    designated_surface_paths = {
        (str(state[item_id].get("type", "")), str(state[item_id].get("path", "")))
        for item_id in designated_surface_ids
        if item_id in state and state[item_id].get("path")
    }

    def duplicate_intersects_designated_surface(issue: dict[str, Any]) -> bool:
        if issue.get("code") != "duplicate_active_path" or current_projection_status != "evaluated":
            return False
        issue_ids = {str(item_id) for item_id in issue.get("ids") or []}
        if issue_ids.intersection(designated_surface_ids):
            return True
        return any(
            (
                str(state[item_id].get("type", "")),
                str(state[item_id].get("path", "")),
            )
            in designated_surface_paths
            for item_id in issue_ids
            if item_id in state
        )

    current_surface_blockers = [
        issue
        for issue in issues
        if issue.get("code") in current_blocker_codes
        or duplicate_intersects_designated_surface(issue)
        or (issue.get("code") == "broken_link" and active_ids.intersection(issue.get("ids") or []))
    ]
    historical_debt = [issue for issue in issues if issue not in current_surface_blockers]
    return {
        "format_version": INDEX_FORMAT_VERSION,
        "schema_version": INDEX_SCHEMA_VERSION,
        "workspace": str(root),
        "audited_at": now_iso(),
        "audit_evidence_status": (
            "not_evaluated_current_projection"
            if current_projection_status == "not_evaluated"
            else "evaluated"
            if events or discover_standard_artifacts(root)
            else "not_evaluated_no_artifacts"
        ),
        "current_projection_status": current_projection_status,
        "projection_completeness": "complete" if not malformed_results else "incomplete",
        "projection_not_evaluated_ids": sorted(projection_not_evaluated_ids),
        "legacy_normalized_count": len(legacy_results),
        "malformed_row_count": len(malformed_results),
        "raw_row_count": len(read_results),
        "index_read_results": [
            {key: value for key, value in result.items() if not key.startswith("_")}
            for result in read_results
            if result.get("migration_status") != "current"
        ][:100],
        "index_read_results_truncated_count": max(
            0,
            len([result for result in read_results if result.get("migration_status") != "current"]) - 100,
        ),
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
        "audit_evidence_status": audit.get("audit_evidence_status"),
        "current_projection_status": audit.get("current_projection_status"),
        "projection_completeness": audit.get("projection_completeness"),
        "projection_not_evaluated_ids": audit.get("projection_not_evaluated_ids", []),
        "legacy_normalized_count": audit.get("legacy_normalized_count", 0),
        "malformed_row_count": audit.get("malformed_row_count", 0),
        "raw_row_count": audit.get("raw_row_count", audit.get("event_count")),
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


def cmd_scan(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    read_only = bool(getattr(args, "dry_run", False) or getattr(args, "check", False))
    result = scan_artifacts(root, dry_run=read_only)
    result["mode"] = "check" if getattr(args, "check", False) else result["mode"]
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if getattr(args, "check", False) and result.get("would_change") else 0


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
    scan_mode = scan_parser.add_mutually_exclusive_group()
    scan_mode.add_argument("--dry-run", action="store_true", help="Report pending scan changes without creating or modifying task-state files.")
    scan_mode.add_argument("--check", action="store_true", help="Run the read-only scan and exit 1 when publication would change task-state files.")
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
    result = args.func(args)
    return int(result or 0)


if __name__ == "__main__":
    sys.exit(main())
