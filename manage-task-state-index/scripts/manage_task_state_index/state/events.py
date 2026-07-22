"""Task-state event validation, reading, merging, and append operations."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, TypeVar

from ..migration.api import load_sealed_events_if_present

from .contracts import (
    INDEX_FORMAT_VERSION,
    INDEX_SCHEMA_VERSION,
    LIFECYCLE_STATUSES,
    NON_ACTIVE_STATUSES,
    PREFIXES,
    SUPPORTED_EVENT_KINDS,
)
from .storage import (
    _ensure_index_unlocked,
    atomic_write_bytes,
    existing_index_read_lock,
    id_stamp,
    index_lock,
    jsonl_path,
    lock_path,
    now_iso,
    sha256_file,
    StableReadRaceError,
    stable_file_token,
    slugify,
)


ReadResult = TypeVar("ReadResult")
READ_SNAPSHOT_ATTEMPTS = 3

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
    sealed = load_sealed_events_if_present(root)
    if sealed is not None:
        return sealed
    events: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []
    source = jsonl_path(root)
    if not source.exists() and not source.is_symlink():
        return events, results
    if source.is_symlink() or not source.is_file():
        raise ValueError("Task-state index must be a regular file")
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


def _stable_index_read(root: Path, reader: Callable[[], ReadResult]) -> ReadResult:
    root = root.resolve()
    source = jsonl_path(root)
    lock = lock_path(root)
    for _attempt in range(READ_SNAPSHOT_ATTEMPTS):
        try:
            with existing_index_read_lock(root) as locked:
                if locked:
                    return reader()
                before = stable_file_token(source)
                error: OSError | UnicodeError | ValueError | None = None
                result: ReadResult | None = None
                try:
                    result = reader()
                except (OSError, UnicodeError, ValueError) as exc:
                    error = exc
                after = stable_file_token(source)
                lock_appeared = lock.exists() or lock.is_symlink()
                if before != after or lock_appeared:
                    continue
                if error is not None:
                    raise error
                return result  # type: ignore[return-value]
        except StableReadRaceError:
            continue
    raise ValueError("Task-state index changed during read-only snapshot")


def load_events_for_audit(root: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    return _stable_index_read(
        root, lambda: _load_events_for_audit_unlocked(root.resolve())
    )


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
    if source.is_symlink() or not source.is_file():
        raise ValueError("Task-state index must be a regular file")
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

    def load() -> tuple[list[dict[str, Any]], str | None]:
        if not source.exists() and not source.is_symlink():
            return [], None
        events = _read_existing_events(root)
        return events, sha256_file(source)

    return _stable_index_read(root, load)


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


def _append_events_unlocked(
    root: Path,
    events: list[dict[str, Any]],
    *,
    allowed_transition_plan_id: str | None = None,
) -> list[dict[str, Any]]:
    from .transition_intent import assert_no_pending_transition_intents
    from .event_batch_validation import validate_event_batch

    assert_no_pending_transition_intents(
        root, allowed_plan_id=allowed_transition_plan_id
    )
    existing = _load_events_unlocked(root)
    versioned = validate_event_batch(existing, events, source=jsonl_path(root))
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
