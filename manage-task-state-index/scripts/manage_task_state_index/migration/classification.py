"""Legacy-row classification, correction, and resolution manifest logic."""
from __future__ import annotations

import json
from typing import Any

from .contracts import (
    CLASSIFICATIONS,
    EVENT_KINDS,
    INFER_TOKEN,
    INDEX_FORMAT_VERSION,
    INDEX_SCHEMA_VERSION,
    LIFECYCLE_STATUSES,
    MANIFEST_SCHEMA_VERSION,
    NON_ACTIVE_STATUSES,
    PROJECTION_IMPACTS,
    MigrationError,
)
from .mapping import (
    _infer_event,
    _mapping_entry,
    _normalize_links,
    _physical_lines,
    _preserve_legacy_token,
    _resolution_map,
    _token,
    _validate_current_event,
)
from .storage import _canonical_bytes, _sha256

def _normalize_legacy(value: dict[str, Any], mapping: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str], str | None]:
    reasons: list[str] = []
    raw_event = _token(value.get("event"))
    event_entry = _mapping_entry(mapping["event_mappings"], raw_event, "event_mappings")
    if event_entry is None:
        return None, reasons, f"unmapped_event:{raw_event}"
    event_kind, reason = event_entry
    reasons.append(reason)
    if event_kind == INFER_TOKEN:
        event_kind = _infer_event(value)
    if event_kind not in EVENT_KINDS:
        return None, reasons, "ambiguous_or_invalid_event"

    normalized = dict(value)
    normalized["event"] = event_kind
    preserve_failure = _preserve_legacy_token(normalized, "event", raw_event, event_kind, reason)
    if preserve_failure is not None:
        return None, reasons, preserve_failure
    normalized["format_version"] = INDEX_FORMAT_VERSION
    normalized["schema_version"] = INDEX_SCHEMA_VERSION
    if "parent" in normalized and "parent_id" not in normalized:
        normalized["parent_id"] = normalized.pop("parent")
        reasons.append("legacy_parent_field")
    links = _normalize_links(normalized.get("links"))
    if normalized.get("links") is not None and links is None:
        return None, reasons, "invalid_legacy_links"
    if links is not None:
        normalized["links"] = links

    if event_kind == "upsert":
        raw_status = _token(value.get("status"))
        status_entry = _mapping_entry(mapping["status_mappings"], raw_status, "status_mappings")
        if status_entry is None:
            return None, reasons, f"unmapped_status:{raw_status}"
        status, status_reason = status_entry
        reasons.append(status_reason)
        raw_type = _token(value.get("type"))
        type_entry = _mapping_entry(mapping["type_mappings"], raw_type, "type_mappings")
        if type_entry is None:
            return None, reasons, f"unmapped_type:{raw_type}"
        item_type, type_reason = type_entry
        reasons.append(type_reason)
        normalized["status"] = status
        normalized["type"] = item_type
        if not isinstance(status, str) or not isinstance(item_type, str):
            return None, reasons, "invalid_mapped_status_or_type"
        preserve_failure = _preserve_legacy_token(normalized, "status", raw_status, status, status_reason)
        if preserve_failure is not None:
            return None, reasons, preserve_failure
        preserve_failure = _preserve_legacy_token(normalized, "type", raw_type, item_type, type_reason)
        if preserve_failure is not None:
            return None, reasons, preserve_failure
    try:
        _validate_current_event(normalized, strict_type=False, allow_sparse_upsert=True)
    except MigrationError as exc:
        return None, reasons, f"invalid_normalized_shape:{exc}"
    return normalized, reasons, None


def _strict_reader_probe(value: Any) -> str | None:
    """Mirror the ordinary reader's pre-migration legacy acceptance surface."""
    if not isinstance(value, dict):
        return "non_object_row"
    format_version = value.get("format_version", 1)
    schema_version = value.get("schema_version", 1)
    if isinstance(format_version, bool) or not isinstance(format_version, int) or format_version < 1:
        return "invalid_format_version"
    if isinstance(schema_version, bool) or not isinstance(schema_version, int) or schema_version < 1:
        return "invalid_schema_version"
    if format_version > INDEX_FORMAT_VERSION:
        return "future_format_version"
    if schema_version > INDEX_SCHEMA_VERSION:
        return "future_schema_version"
    legacy = value.get("format_version") is None or format_version < INDEX_FORMAT_VERSION
    if not legacy and value.get("schema_version") is None:
        return "current_missing_schema_version"
    event_kind = value.get("event")
    if event_kind is None and legacy:
        # Keep this inference byte-for-byte compatible with the normal reader,
        # not with the more capable explicit mapping normalizer.
        if all(isinstance(value.get(field), str) and value[field] for field in ("type", "status", "path")):
            event_kind = "upsert"
        elif isinstance(value.get("links"), list) and not any(field in value for field in ("type", "status", "path")):
            event_kind = "link"
    if event_kind not in EVENT_KINDS:
        return "invalid_event_discriminator"
    if not isinstance(value.get("id"), str) or not value["id"] or not isinstance(value.get("updated_at"), str) or not value["updated_at"]:
        return "missing_identity_or_timestamp"
    if value.get("status") is not None and value.get("status") not in LIFECYCLE_STATUSES:
        return "invalid_lifecycle_status"
    if value.get("fields") is not None and not isinstance(value.get("fields"), dict):
        return "invalid_fields"
    if value.get("links") is not None:
        links = value.get("links")
        if not isinstance(links, list) or any(
            not isinstance(link, dict) or not isinstance(link.get("rel"), str) or not isinstance(link.get("id"), str)
            for link in links
        ):
            return "invalid_relationship_contract"
    return None


def _classify_rows(prefix: bytes, mapping: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, int]]:
    resolutions = _resolution_map(mapping)
    rows: list[dict[str, Any]] = []
    normalized_events: list[dict[str, Any]] = []
    counts = {classification: 0 for classification in sorted(CLASSIFICATIONS)}
    used_resolutions: set[tuple[int, str]] = set()
    for line_no, raw_line in enumerate(_physical_lines(prefix), start=1):
        raw_sha = _sha256(raw_line)
        override = resolutions.get((line_no, raw_sha))
        entry: dict[str, Any] = {
            "line": line_no,
            "raw_line_sha256": raw_sha,
            "raw_byte_length": len(raw_line),
            "classification": None,
            "reason_codes": [],
            "projection_impact": "independent",
            "deterministic_identity": None,
            "resolution": None,
            "normalized_event_sha256": None,
            "correction_event_ids": [],
            "correction_event_sha256s": [],
        }
        value: Any = None
        parse_reason: str | None = None
        try:
            value = json.loads(raw_line.decode("utf-8"))
            if not isinstance(value, dict):
                parse_reason = "non_object_row"
        except UnicodeDecodeError:
            parse_reason = "invalid_utf8"
        except json.JSONDecodeError:
            parse_reason = "malformed_json"

        if override is not None:
            used_resolutions.add((line_no, raw_sha))
            disposition = override.get("disposition")
            impact = override.get("projection_impact")
            reason = override.get("reason_code")
            identity = override.get("deterministic_identity")
            resolution = override.get("resolution")
            if disposition != "quarantined_historical" or impact not in PROJECTION_IMPACTS or not isinstance(reason, str) or not reason:
                raise MigrationError(f"Invalid exact row resolution for line {line_no}")
            if impact != "independent" and not (
                isinstance(resolution, str)
                and resolution in {"projection_epoch_reset", "superseded_by_canonical_task", "superseded_by_canonical_pack", "link_retracted"}
            ):
                entry["classification"] = "blocked_unknown_or_future"
                entry["reason_codes"] = ["current_impact_without_correction"]
                entry["projection_impact"] = impact
            else:
                entry["classification"] = "quarantined_historical"
                entry["reason_codes"] = [parse_reason or _strict_reader_probe(value) or "exact_caller_quarantine", reason]
                entry["projection_impact"] = impact
                entry["deterministic_identity"] = identity
                entry["resolution"] = resolution
            counts[entry["classification"]] += 1
            rows.append(entry)
            continue

        if parse_reason is None and isinstance(value, dict):
            entry["deterministic_identity"] = value.get("id") if isinstance(value.get("id"), str) else None
            current = value.get("format_version") == INDEX_FORMAT_VERSION and value.get("schema_version") == INDEX_SCHEMA_VERSION
            if current:
                try:
                    _validate_current_event(value)
                except MigrationError as exc:
                    parse_reason = f"invalid_current:{exc}"
                else:
                    entry["classification"] = "accepted_current"
                    entry["reason_codes"] = ["current_schema_valid"]
                    entry["normalized_event_sha256"] = _sha256(_canonical_bytes(value))
                    normalized_events.append(value)
            else:
                future = (
                    isinstance(value.get("format_version"), int) and value["format_version"] > INDEX_FORMAT_VERSION
                ) or (
                    isinstance(value.get("schema_version"), int) and value["schema_version"] > INDEX_SCHEMA_VERSION
                )
                if future:
                    parse_reason = "future_version"
                else:
                    normalized, reasons, failure = _normalize_legacy(value, mapping)
                    if normalized is None:
                        parse_reason = failure or "legacy_normalization_failed"
                    else:
                        mapped = any(
                            normalized.get(axis) != value.get(axis)
                            for axis in ("event", "status", "type")
                            if axis in normalized
                        )
                        entry["classification"] = "mapped_legacy" if mapped else "normalized_legacy"
                        entry["reason_codes"] = reasons
                        entry["normalized_event_sha256"] = _sha256(_canonical_bytes(normalized))
                        normalized_events.append(normalized)

        if entry["classification"] is None:
            entry["classification"] = "blocked_unknown_or_future"
            entry["reason_codes"] = [parse_reason or "unclassified"]
            entry["projection_impact"] = "unknown"
        counts[entry["classification"]] += 1
        rows.append(entry)
    if len(rows) != len(_physical_lines(prefix)):
        raise MigrationError("Row accounting failed")
    if used_resolutions != set(resolutions):
        raise MigrationError("Mapping manifest contains stale or unmatched exact row resolutions")
    return rows, normalized_events, counts


def _merge_state(events: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    state: dict[str, dict[str, Any]] = {}
    for event in events:
        item_id = event.get("id")
        if not isinstance(item_id, str) or not item_id:
            continue
        current = state.setdefault(item_id, {"id": item_id, "links": [], "fields": {}})
        for key in ("type", "status", "path", "title", "parent_id", "content_sha256", "note", "updated_at"):
            if event.get(key) is not None:
                current[key] = event[key]
        fields = event.get("fields") if isinstance(event.get("fields"), dict) else {}
        tombstones = _normalize_links(fields.get("link_tombstones")) or []
        if tombstones:
            removed = {(item["rel"], item["id"]) for item in tombstones}
            current["links"] = [link for link in current.get("links", []) if (link.get("rel"), link.get("id")) not in removed]
        current.setdefault("fields", {}).update(fields)
        links = _normalize_links(event.get("links")) or []
        seen = {(link.get("rel"), link.get("id")) for link in current.setdefault("links", [])}
        for link in links:
            pair = (link["rel"], link["id"])
            if pair not in seen:
                current["links"].append(link)
                seen.add(pair)
    return state


def _broken_links(state: dict[str, dict[str, Any]], item_id: str) -> list[dict[str, str]]:
    item = state.get(item_id, {})
    return [
        {"rel": link["rel"], "id": link["id"]}
        for link in item.get("links", [])
        if isinstance(link, dict) and link.get("id") not in state
    ]


def _versioned(event: dict[str, Any]) -> dict[str, Any]:
    return {**event, "format_version": INDEX_FORMAT_VERSION, "schema_version": INDEX_SCHEMA_VERSION}


def _make_corrections(
    events: list[dict[str, Any]], mapping: dict[str, Any], migration_id: str,
    current_task_id: str, current_task_path: str, current_task_sha: str,
    current_pack_id: str, current_pack_path: str, current_pack_sha: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    effective_at = mapping["effective_at"]
    state = _merge_state(events)
    corrections: list[dict[str, Any]] = []
    superseded_tasks: list[str] = []
    superseded_packs: list[str] = []
    before_active_tasks = sorted(
        item_id for item_id, item in state.items()
        if item.get("type") == "task" and item.get("status") == "active"
    )
    before_active_packs = sorted(
        item_id for item_id, item in state.items()
        if item.get("type") == "task_pack" and item.get("status") == "active"
    )
    before_duplicate_aliases = sorted(
        item_id for item_id, item in state.items()
        if item_id != current_task_id and item.get("type") == "task" and item.get("path") == current_task_path
        and item.get("status") not in NON_ACTIVE_STATUSES
    )
    before_broken_links = [
        {"source_id": item_id, "rel": link["rel"], "id": link["id"]}
        for item_id in before_active_tasks
        for link in state.get(item_id, {}).get("links", [])
        if isinstance(link, dict) and link.get("id") not in state
    ]

    for item_id, item in sorted(state.items()):
        if item_id == current_task_id or item.get("type") != "task":
            continue
        if item.get("status") == "active" or (item.get("path") == current_task_path and item.get("status") not in NON_ACTIVE_STATUSES):
            corrections.append(_versioned({
                "event": "upsert", "id": item_id, "type": "task", "status": "superseded",
                "path": str(item.get("path") or current_task_path),
                "title": str(item.get("title") or item_id), "updated_at": effective_at,
                "fields": {"migration_id": migration_id, "superseded_by": current_task_id},
            }))
            superseded_tasks.append(item_id)
    for item_id, item in sorted(state.items()):
        if item_id == current_pack_id or item.get("type") != "task_pack":
            continue
        if item.get("status") == "active":
            corrections.append(_versioned({
                "event": "upsert", "id": item_id, "type": "task_pack", "status": "superseded",
                "path": str(item.get("path") or ".task/task_pack"),
                "title": str(item.get("title") or item_id), "updated_at": effective_at,
                "fields": {"migration_id": migration_id, "superseded_by": current_pack_id},
            }))
            superseded_packs.append(item_id)

    current_links = state.get(current_task_id, {}).get("links", [])
    tombstones = [
        {"rel": link["rel"], "id": link["id"]}
        for link in current_links
        if isinstance(link, dict) and (
            link.get("id") not in state
            or link.get("rel") == "promoted_from_pack"
            or (link.get("rel") == "pack_for_task" and link.get("id") != current_pack_id)
        )
    ]
    corrections.append(_versioned({
        "event": "upsert", "id": current_task_id, "type": "task", "status": "active",
        "path": current_task_path, "title": str(state.get(current_task_id, {}).get("title") or current_task_id),
        "content_sha256": current_task_sha, "updated_at": effective_at,
        "fields": {
            "record_class": "mutable_alias", "canonical_id": current_task_id,
            "projection_epoch": migration_id, "link_tombstones": tombstones,
        },
        "links": [{"rel": "pack_for_task", "id": current_pack_id}],
    }))
    corrections.append(_versioned({
        "event": "upsert", "id": current_pack_id, "type": "task_pack", "status": "active",
        "path": current_pack_path, "title": str(state.get(current_pack_id, {}).get("title") or current_pack_id),
        "content_sha256": current_pack_sha, "updated_at": effective_at,
        "fields": {"pack_id": current_pack_id, "projection_epoch": migration_id, "planning_relationship": "non_promotion"},
        "links": [{"rel": "pack_for_task", "id": current_task_id}],
    }))
    for ordinal, event in enumerate(corrections, start=1):
        fields = dict(event.get("fields") or {})
        fields["migration_correction_event_id"] = f"{migration_id}-correction-{ordinal:06d}"
        event["fields"] = fields
    final_state = _merge_state(events + corrections)
    active_tasks = sorted(item_id for item_id, item in final_state.items() if item.get("type") == "task" and item.get("status") == "active")
    active_packs = sorted(item_id for item_id, item in final_state.items() if item.get("type") == "task_pack" and item.get("status") == "active")
    duplicate_aliases = sorted(
        item_id for item_id, item in final_state.items()
        if item_id != current_task_id and item.get("type") == "task" and item.get("path") == current_task_path
        and item.get("status") not in NON_ACTIVE_STATUSES
    )
    remaining_broken = _broken_links(final_state, current_task_id)
    projection = {
        "before_active_task_ids": before_active_tasks,
        "before_active_task_count": len(before_active_tasks),
        "before_active_pack_ids": before_active_packs,
        "before_active_pack_count": len(before_active_packs),
        "before_duplicate_active_alias_ids": before_duplicate_aliases,
        "before_duplicate_active_alias_count": len(before_duplicate_aliases),
        "before_current_broken_links": before_broken_links,
        "before_current_broken_link_count": len(before_broken_links),
        "active_task_ids": active_tasks,
        "active_task_count": len(active_tasks),
        "active_pack_ids": active_packs,
        "active_pack_count": len(active_packs),
        "duplicate_active_alias_ids": duplicate_aliases,
        "duplicate_active_alias_count": len(duplicate_aliases),
        "current_broken_links": remaining_broken,
        "current_broken_link_count": len(remaining_broken),
        "current_active_pack_indexed": current_pack_id in final_state,
        "current_projection_status": "evaluated",
        "projection_completeness": "complete",
        "current_surface_blocker_count": int(active_tasks != [current_task_id])
        + int(active_packs != [current_pack_id]) + len(duplicate_aliases) + len(remaining_broken),
        "superseded_task_ids": superseded_tasks,
        "superseded_pack_ids": superseded_packs,
        "retracted_links": tombstones,
    }
    return corrections, projection


def _correction_identity(event: dict[str, Any]) -> tuple[str, str]:
    fields = event.get("fields") if isinstance(event.get("fields"), dict) else {}
    correction_id = fields.get("migration_correction_event_id")
    if not isinstance(correction_id, str) or not correction_id:
        raise MigrationError("Correction event lacks deterministic correction ID")
    return correction_id, _sha256(_canonical_bytes(event))


def _bind_quarantine_corrections(
    rows: list[dict[str, Any]], corrections: list[dict[str, Any]],
    current_task_id: str, current_pack_id: str,
) -> None:
    indexed: list[tuple[dict[str, Any], str, str]] = [
        (event, *_correction_identity(event)) for event in corrections
    ]
    if len({correction_id for _event, correction_id, _sha in indexed}) != len(indexed):
        raise MigrationError("Duplicate migration correction event ID")
    for row in rows:
        if row.get("classification") != "quarantined_historical" or row.get("projection_impact") == "independent":
            continue
        resolution = row.get("resolution")
        identity = row.get("deterministic_identity")
        candidates: list[tuple[dict[str, Any], str, str]] = []
        if resolution == "projection_epoch_reset":
            candidates = [item for item in indexed if item[0].get("id") in {current_task_id, current_pack_id}]
        elif resolution == "superseded_by_canonical_task":
            candidates = [
                item for item in indexed
                if item[0].get("id") == identity and item[0].get("type") == "task" and item[0].get("status") == "superseded"
            ]
        elif resolution == "superseded_by_canonical_pack":
            candidates = [
                item for item in indexed
                if item[0].get("id") == identity and item[0].get("type") == "task_pack" and item[0].get("status") == "superseded"
            ]
        elif resolution == "link_retracted":
            candidates = [
                item for item in indexed
                if item[0].get("id") == current_task_id
                and isinstance(item[0].get("fields"), dict)
                and bool(item[0]["fields"].get("link_tombstones"))
            ]
        if not candidates:
            raise MigrationError(
                f"Non-independent quarantine line {row.get('line')} lacks an exact correction event binding"
            )
        row["correction_event_ids"] = [correction_id for _event, correction_id, _sha in candidates]
        row["correction_event_sha256s"] = [event_sha for _event, _id, event_sha in candidates]


def _validate_quarantine_correction_bindings(
    rows: list[dict[str, Any]], corrections: list[dict[str, Any]],
) -> None:
    correction_graph = {
        correction_id: event_sha
        for event in corrections
        for correction_id, event_sha in [_correction_identity(event)]
    }
    if len(correction_graph) != len(corrections):
        raise MigrationError("Duplicate correction event identity in sealed suffix")
    for row in rows:
        ids = row.get("correction_event_ids")
        hashes = row.get("correction_event_sha256s")
        non_independent = (
            row.get("classification") == "quarantined_historical"
            and row.get("projection_impact") != "independent"
        )
        if not isinstance(ids, list) or not isinstance(hashes, list) or len(ids) != len(hashes):
            raise MigrationError("Resolution manifest has invalid correction binding shape")
        if non_independent and not ids:
            raise MigrationError("Non-independent quarantine lacks correction binding")
        if not non_independent and (ids or hashes):
            raise MigrationError("Independent row carries an unauthorized correction binding")
        if len(set(ids)) != len(ids):
            raise MigrationError("Resolution manifest repeats a correction event ID")
        for correction_id, expected_sha in zip(ids, hashes, strict=True):
            if correction_graph.get(correction_id) != expected_sha:
                raise MigrationError("Quarantine correction event binding mismatch")


def _manifest_payload(migration_id: str, prefix: bytes, rows: list[dict[str, Any]], counts: dict[str, int]) -> dict[str, Any]:
    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "kind": "task_state_index_resolution_manifest",
        "migration_id": migration_id,
        "source_prefix_sha256": _sha256(prefix),
        "source_prefix_byte_length": len(prefix),
        "source_raw_row_count": len(rows),
        "classification_counts": counts,
        "rows": rows,
        "raw_row_bodies_included": False,
    }
