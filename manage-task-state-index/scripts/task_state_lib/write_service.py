"""Task-state identity resolution and atomic write services."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .contracts import (
    LIFECYCLE_STATUSES,
    NON_ACTIVE_STATUSES,
    TASK_SCAN_PRESERVED_NONEXECUTABLE_STATUSES,
)
from .events import (
    _append_events_unlocked,
    _load_events_unlocked,
    make_id,
    merge_state,
    path_records,
    stable_path_id,
)
from .render import _rebuild_markdown_unlocked
from .storage import (
    atomic_write_bytes,
    immutable_snapshot_path,
    index_lock,
    now_iso,
    read_title,
    rel_path,
    sha256_file,
)


@dataclass(frozen=True)
class _IdentityDecision:
    item_id: str
    active_records: list[tuple[str, dict[str, Any]]]
    semantic_replacement: bool
    canonical_advice_reactivation: bool
    explicit_replacement: bool


def _validate_completed_alias(
    existing: dict[str, Any] | None,
    *,
    item_type: str,
    path_value: str,
    item_id: str | None,
    digest: str | None,
    status: str,
) -> None:
    existing_fields = (
        existing.get("fields")
        if isinstance(existing, dict) and isinstance(existing.get("fields"), dict)
        else {}
    )
    completed_alias = bool(
        item_type == "task"
        and path_value == "task.md"
        and isinstance(existing, dict)
        and existing.get("status") in TASK_SCAN_PRESERVED_NONEXECUTABLE_STATUSES
        and existing_fields.get("record_class") == "mutable_alias"
        and existing_fields.get("canonical_id") == item_id
    )
    if not completed_alias:
        return
    if existing.get("content_sha256") != digest:
        raise ValueError(
            "A completed current task alias changed body without a distinct successor identity"
        )
    if status not in TASK_SCAN_PRESERVED_NONEXECUTABLE_STATUSES:
        raise ValueError(
            "A completed task identity cannot be reactivated; create a distinct successor identity"
        )


def _resolve_identity(
    state: dict[str, dict[str, Any]],
    *,
    item_type: str,
    path_value: str,
    status: str,
    title: str,
    item_id: str | None,
    fields: dict[str, str] | None,
    replace_existing: bool | None,
    digest: str | None,
) -> _IdentityDecision:
    active_records = path_records(state, item_type, path_value, active_only=True)
    provided = item_id is not None
    explicit = bool(
        provided
        and active_records
        and all(existing_id != item_id for existing_id, _ in active_records)
    )
    existing = state.get(item_id) if provided and item_id is not None else None
    _validate_completed_alias(
        existing,
        item_type=item_type,
        path_value=path_value,
        item_id=item_id,
        digest=digest,
        status=status,
    )
    canonical_reactivation = bool(
        explicit
        and item_type == "external_advice"
        and replace_existing is False
        and isinstance(fields, dict)
        and fields.get("advice_id") == item_id
        and isinstance(existing, dict)
        and existing.get("type") == "external_advice"
        and existing.get("path") == path_value
        and existing.get("status") == "superseded"
    )
    legacy_replacement = bool(
        replace_existing is None
        and not provided
        and item_type == "task"
        and path_value == "task.md"
        and digest
        and any(row.get("content_sha256") != digest for _, row in active_records)
    )
    semantic = bool(replace_existing) or explicit or legacy_replacement
    if semantic and not provided:
        item_id = make_id(item_type, title, path_value)
    elif not semantic:
        item_id = (
            item_id
            or stable_path_id(state, item_type, path_value)
            or make_id(item_type, title, path_value)
        )
    assert item_id is not None
    if explicit and item_id in state and not canonical_reactivation:
        raise ValueError(f"Replacement id {item_id!r} must be new")
    if replace_existing and provided and any(row_id == item_id for row_id, _ in active_records):
        raise ValueError("--replace requires a new explicit id or no --id")
    if provided and item_id in state:
        prior = state[item_id]
        if prior.get("type") != item_type:
            raise ValueError(f"Explicit id {item_id!r} already belongs to another artifact")
        if prior.get("path") != path_value and replace_existing is not False:
            raise ValueError(f"Explicit id {item_id!r} already belongs to another artifact path")
    if not provided:
        base_id = item_id
        suffix = 2
        while item_id in state and (
            semantic
            or state[item_id].get("type") != item_type
            or state[item_id].get("path") != path_value
        ):
            item_id = f"{base_id}-{suffix}"
            suffix += 1
    return _IdentityDecision(
        item_id,
        active_records,
        semantic,
        canonical_reactivation,
        explicit,
    )


def _replacement_records(
    state: dict[str, dict[str, Any]],
    decision: _IdentityDecision,
    retire_alias_ids: list[str] | None,
) -> tuple[list[tuple[str, dict[str, Any]]], dict[str, Any] | None]:
    records = [
        (existing_id, existing)
        for existing_id, existing in decision.active_records
        if existing_id != decision.item_id
    ]
    for alias_id in sorted(set(retire_alias_ids or [])):
        alias = state.get(alias_id)
        if (
            alias_id == decision.item_id
            or not isinstance(alias, dict)
            or alias.get("type") != "external_advice"
            or alias.get("status") in NON_ACTIVE_STATUSES
        ):
            raise ValueError(f"Invalid external advice pointer alias retirement: {alias_id!r}")
        if all(existing_id != alias_id for existing_id, _ in records):
            records.append((alias_id, alias))
    if not (decision.semantic_replacement and records):
        return records, None
    result: dict[str, Any] = {
        "previous_snapshot_preserved": True,
        "previous_active_superseded": False,
        "new_canonical_id_added": False,
        "mutable_alias_updated": False,
        "links_updated": False,
        "index_rendered": False,
        "atomic": False,
        "replacement_reason": (
            "canonical_advice_reactivation"
            if decision.canonical_advice_reactivation
            else "explicit_id"
            if decision.explicit_replacement
            else "semantic_replacement"
        ),
    }
    if decision.canonical_advice_reactivation:
        result["canonical_reactivated"] = True
    return records, result


def _supersession_events(
    root: Path,
    *,
    item_type: str,
    path_value: str,
    item_id: str,
    timestamp: str,
    records: list[tuple[str, dict[str, Any]]],
    lifecycle: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    outgoing: list[dict[str, Any]] = []
    for previous_id, previous in records:
        prior_fields = previous.get("fields") if isinstance(previous.get("fields"), dict) else {}
        if item_type == "task" and path_value == "task.md":
            snapshot_value = prior_fields.get("snapshot_path")
            snapshot_exists = bool(snapshot_value and (root / str(snapshot_value)).is_file())
            if lifecycle is not None and not snapshot_exists:
                lifecycle["previous_snapshot_preserved"] = False
            outgoing.append({
                "event": "upsert",
                "id": previous_id,
                "updated_at": timestamp,
                "fields": {
                    **prior_fields,
                    "record_class": "immutable_snapshot",
                    "snapshot_digest": previous.get("content_sha256"),
                    "snapshot_path": snapshot_value,
                    "alias_path": path_value,
                    "canonical_id": previous_id,
                },
            })
        outgoing.extend([
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
        ])
    if lifecycle is not None:
        lifecycle["previous_active_superseded"] = True
    return outgoing


def _current_event(
    root: Path,
    state: dict[str, dict[str, Any]],
    *,
    decision: _IdentityDecision,
    item_type: str,
    path_value: str,
    status: str,
    title: str,
    timestamp: str,
    digest: str | None,
    parent_id: str | None,
    links: list[dict[str, str]] | None,
    fields: dict[str, str] | None,
    note: str | None,
    records: list[tuple[str, dict[str, Any]]],
) -> dict[str, Any]:
    merged_fields = dict(fields or {})
    event_links = list(links or [])
    event_links.extend({"rel": "supersedes", "id": row_id} for row_id, _ in records)
    path = root / path_value
    if item_type == "task" and path_value == "task.md" and path.is_file():
        snapshot = immutable_snapshot_path(root, decision.item_id, path)
        atomic_write_bytes(snapshot, path.read_bytes())
        merged_fields.update({
            "record_class": "mutable_alias",
            "snapshot_digest": digest or "",
            "snapshot_path": rel_path(root, snapshot),
            "canonical_id": decision.item_id,
            "alias_path": path_value,
        })
    event: dict[str, Any] = {
        "event": "upsert",
        "id": decision.item_id,
        "type": item_type,
        "status": status,
        "path": path_value,
        "title": title,
        "updated_at": timestamp,
        "content_sha256": digest,
    }
    if decision.item_id not in state:
        event["created_at"] = timestamp
    if parent_id:
        event["parent_id"] = parent_id
    if event_links:
        event["links"] = event_links
    if merged_fields:
        event["fields"] = merged_fields
    if note:
        event["note"] = note
    return event


def _finish_lifecycle(lifecycle: dict[str, Any] | None) -> None:
    if lifecycle is None:
        return
    lifecycle.update({
        "new_canonical_id_added": True,
        "mutable_alias_updated": True,
        "links_updated": True,
        "index_rendered": True,
    })
    lifecycle["atomic"] = all(
        lifecycle[field]
        for field in (
            "previous_snapshot_preserved",
            "previous_active_superseded",
            "new_canonical_id_added",
            "mutable_alias_updated",
            "links_updated",
            "index_rendered",
        )
    )


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
    *,
    _now_fn: Callable[[], str] = now_iso,
) -> dict[str, Any]:
    root = root.resolve()
    if status not in LIFECYCLE_STATUSES:
        raise ValueError(f"Unsupported lifecycle status: {status!r}")
    with index_lock(root):
        state = merge_state(_load_events_unlocked(root))
        path = root / path_value
        digest = sha256_file(path)
        resolved_title = title or read_title(path)
        timestamp = _now_fn()
        decision = _resolve_identity(
            state,
            item_type=item_type,
            path_value=path_value,
            status=status,
            title=resolved_title,
            item_id=item_id,
            fields=fields,
            replace_existing=replace_existing,
            digest=digest,
        )
        records, lifecycle = _replacement_records(state, decision, retire_alias_ids)
        outgoing = _supersession_events(
            root,
            item_type=item_type,
            path_value=path_value,
            item_id=decision.item_id,
            timestamp=timestamp,
            records=records,
            lifecycle=lifecycle,
        )
        outgoing.append(_current_event(
            root,
            state,
            decision=decision,
            item_type=item_type,
            path_value=path_value,
            status=status,
            title=resolved_title,
            timestamp=timestamp,
            digest=digest,
            parent_id=parent_id,
            links=links,
            fields=fields,
            note=note,
            records=records,
        ))
        versioned = _append_events_unlocked(root, outgoing)
        rebuild = _rebuild_markdown_unlocked(root, now_fn=_now_fn)
        _finish_lifecycle(lifecycle)
        return {
            "id": decision.item_id,
            "event": next(
                row for row in versioned
                if row.get("id") == decision.item_id and row.get("type") == item_type
            ),
            "lifecycle_transition_result": lifecycle,
            "duplicate_active_paths_repaired": (
                len(records) if not decision.semantic_replacement else 0
            ),
            **rebuild,
        }


def link_item(
    root: Path,
    source_id: str,
    links: list[dict[str, str]],
    note: str | None = None,
    *,
    _now_fn: Callable[[], str] = now_iso,
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
            "updated_at": _now_fn(),
        }
        if note:
            event["note"] = note
        versioned = _append_events_unlocked(root, [event])[0]
        return {
            "id": source_id,
            "event": versioned,
            **_rebuild_markdown_unlocked(root, now_fn=_now_fn),
        }


