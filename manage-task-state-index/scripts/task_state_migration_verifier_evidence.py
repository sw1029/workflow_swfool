"""Independent prefix classification and projection reconstruction."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from task_state_migration_verifier_core import (
    ANCHOR_KIND,
    ARTIFACT_TYPES,
    CLASSIFICATIONS,
    EVENT_KINDS,
    INDEX_FORMAT_VERSION,
    INDEX_SCHEMA_VERSION,
    INFER_TOKEN,
    LIFECYCLE_STATUSES,
    MIGRATION_EVENT_FIELD,
    MAPPING_SCHEMA_VERSION,
    MISSING_TOKEN,
    NON_ACTIVE_STATUSES,
    PROJECTION_IMPACTS,
    _broken_links,
    _canonical_json,
    _is_int,
    _is_sha256,
    _merge_state,
    _normalize_links,
    _physical_lines,
    _require,
    _sha256,
    _validate_current_event,
    _versioned,
    _workspace_ref,
)


MAPPING_KEYS = {
    "schema_version",
    "mapping_policy_id",
    "mapping_method",
    "pattern_inference_used",
    "effective_at",
    "event_mappings",
    "status_mappings",
    "type_mappings",
    "reason_codes",
    "row_resolutions",
}
MAPPING_ENTRY_KEYS = {"to", "reason_code"}
ROW_RESOLUTION_KEYS = {
    "line",
    "raw_line_sha256",
    "disposition",
    "projection_impact",
    "reason_code",
    "deterministic_identity",
    "resolution",
}
ROW_KEYS = {
    "line",
    "raw_line_sha256",
    "raw_byte_length",
    "classification",
    "reason_codes",
    "projection_impact",
    "deterministic_identity",
    "resolution",
    "normalized_event_sha256",
    "correction_event_ids",
    "correction_event_sha256s",
}


def _token(value: Any) -> str:
    return value if isinstance(value, str) else MISSING_TOKEN


def _validate_mapping(mapping: dict[str, Any]) -> None:
    _require(set(mapping) == MAPPING_KEYS, "caller mapping has unknown or missing fields")
    _require(
        _is_int(mapping.get("schema_version"))
        and mapping["schema_version"] == MAPPING_SCHEMA_VERSION,
        "caller mapping schema version is invalid",
    )
    _require(
        isinstance(mapping.get("mapping_policy_id"), str)
        and bool(mapping["mapping_policy_id"]),
        "caller mapping policy identity is missing",
    )
    _require(
        mapping.get("mapping_method") == "exact_token_review"
        and mapping.get("pattern_inference_used") is False,
        "caller mapping is not exact-token reviewed",
    )
    _require(
        isinstance(mapping.get("effective_at"), str) and bool(mapping["effective_at"]),
        "caller mapping effective time is missing",
    )
    reasons = mapping.get("reason_codes")
    _require(
        isinstance(reasons, dict)
        and all(isinstance(key, str) and key and isinstance(value, str) and value for key, value in reasons.items()),
        "caller mapping reason codes are malformed",
    )
    for axis in ("event_mappings", "status_mappings", "type_mappings"):
        table = mapping.get(axis)
        _require(isinstance(table, dict), "caller mapping table is missing")
        for source, entry in table.items():
            _require(isinstance(source, str) and source, "caller mapping token is invalid")
            _require(isinstance(entry, dict) and set(entry) == MAPPING_ENTRY_KEYS, "caller mapping entry shape is invalid")
            _require(
                entry.get("to") is None or isinstance(entry.get("to"), str),
                "caller mapping target is invalid",
            )
            target = entry.get("to")
            if axis == "event_mappings":
                _require(target in EVENT_KINDS | {INFER_TOKEN}, "caller mapping target is unsupported")
            elif axis == "status_mappings":
                _require(target is None or target in LIFECYCLE_STATUSES, "caller mapping target is unsupported")
            else:
                _require(target is None or target in ARTIFACT_TYPES, "caller mapping target is unsupported")
            _require(
                isinstance(entry.get("reason_code"), str)
                and entry["reason_code"] in reasons,
                "caller mapping reason is not exact-bound",
            )
    resolutions = mapping.get("row_resolutions")
    _require(isinstance(resolutions, list), "caller mapping row resolutions are missing")
    seen: set[tuple[int, str]] = set()
    for entry in resolutions:
        _require(isinstance(entry, dict) and set(entry) == ROW_RESOLUTION_KEYS, "caller row resolution shape is invalid")
        line = entry.get("line")
        digest = entry.get("raw_line_sha256")
        _require(
            _is_int(line)
            and line > 0
            and _is_sha256(digest),
            "caller row resolution identity is invalid",
        )
        key = (line, digest)
        _require(key not in seen, "caller mapping repeats a row resolution")
        seen.add(key)
        _require(
            entry.get("disposition") == "quarantined_historical"
            and entry.get("projection_impact") in PROJECTION_IMPACTS
            and isinstance(entry.get("reason_code"), str)
            and entry["reason_code"] in reasons,
            "caller row resolution disposition is invalid",
        )
        _require(
            entry.get("deterministic_identity") is None
            or isinstance(entry.get("deterministic_identity"), str),
            "caller row resolution deterministic identity is invalid",
        )
        _require(
            isinstance(entry.get("resolution"), str) and bool(entry["resolution"]),
            "caller row resolution recovery disposition is invalid",
        )


def _mapping_entry(
    mapping: dict[str, Any], axis: str, token: str
) -> tuple[str | None, str] | None:
    table = mapping[axis]
    if token not in table:
        return None
    entry = table[token]
    return entry["to"], entry["reason_code"]


def _infer_event(value: dict[str, Any]) -> str | None:
    if all(isinstance(value.get(field), str) and value[field] for field in ("type", "path")):
        return "upsert"
    if isinstance(value.get("links"), list) and not any(field in value for field in ("type", "status", "path")):
        return "link"
    return None


def _preserve_legacy_token(
    normalized: dict[str, Any], axis: str, original: str, target: str, reason: str
) -> str | None:
    if original == target:
        return None
    fields = normalized.get("fields")
    if fields is None:
        fields = {}
    elif not isinstance(fields, dict):
        return "invalid_fields"
    else:
        fields = dict(fields)
    key = f"legacy_original_{axis}"
    binding = {"token": original, "reason_code": reason}
    if key in fields and fields[key] != binding:
        return f"conflicting_{key}"
    fields[key] = binding
    normalized["fields"] = fields
    return None


def _normalize_legacy(
    value: dict[str, Any], mapping: dict[str, Any]
) -> tuple[dict[str, Any] | None, list[str], str | None]:
    reasons: list[str] = []
    raw_event = _token(value.get("event"))
    event_entry = _mapping_entry(mapping, "event_mappings", raw_event)
    if event_entry is None:
        return None, reasons, f"unmapped_event:{raw_event}"
    event_kind, event_reason = event_entry
    reasons.append(event_reason)
    if event_kind == INFER_TOKEN:
        event_kind = _infer_event(value)
    if event_kind not in EVENT_KINDS:
        return None, reasons, "ambiguous_or_invalid_event"
    normalized = dict(value)
    normalized["event"] = event_kind
    failure = _preserve_legacy_token(normalized, "event", raw_event, event_kind, event_reason)
    if failure:
        return None, reasons, failure
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
        for axis, field in (("status_mappings", "status"), ("type_mappings", "type")):
            original = _token(value.get(field))
            entry = _mapping_entry(mapping, axis, original)
            if entry is None:
                return None, reasons, f"unmapped_{field}:{original}"
            target, reason = entry
            reasons.append(reason)
            if not isinstance(target, str) or not target:
                return None, reasons, f"invalid_mapped_{field}"
            normalized[field] = target
            failure = _preserve_legacy_token(normalized, field, original, target, reason)
            if failure:
                return None, reasons, failure
        if normalized.get("type") not in ARTIFACT_TYPES:
            return None, reasons, "invalid_mapped_type"
    try:
        _validate_current_event(normalized, allow_sparse_upsert=True)
    except (ValueError, TypeError) as exc:
        return None, reasons, f"invalid_normalized_shape:{exc}"
    return normalized, reasons, None


def _strict_reader_reason(value: Any) -> str | None:
    if not isinstance(value, dict):
        return "non_object_row"
    format_version = value.get("format_version", 1)
    schema_version = value.get("schema_version", 1)
    if not _is_int(format_version) or format_version < 1:
        return "invalid_format_version"
    if not _is_int(schema_version) or schema_version < 1:
        return "invalid_schema_version"
    if format_version > INDEX_FORMAT_VERSION:
        return "future_format_version"
    if schema_version > INDEX_SCHEMA_VERSION:
        return "future_schema_version"
    legacy = value.get("format_version") is None or format_version < INDEX_FORMAT_VERSION
    if not legacy and value.get("schema_version") is None:
        return "current_missing_schema_version"
    event = value.get("event")
    if event is None and legacy:
        if all(isinstance(value.get(field), str) and value[field] for field in ("type", "status", "path")):
            event = "upsert"
        elif isinstance(value.get("links"), list) and not any(field in value for field in ("type", "status", "path")):
            event = "link"
    if event not in EVENT_KINDS:
        return "invalid_event_discriminator"
    if not isinstance(value.get("id"), str) or not value["id"] or not isinstance(value.get("updated_at"), str) or not value["updated_at"]:
        return "missing_identity_or_timestamp"
    if value.get("status") is not None and value.get("status") not in LIFECYCLE_STATUSES:
        return "invalid_lifecycle_status"
    if value.get("fields") is not None and not isinstance(value.get("fields"), dict):
        return "invalid_fields"
    if value.get("links") is not None:
        links = value["links"]
        if not isinstance(links, list) or any(
            not isinstance(link, dict)
            or not isinstance(link.get("rel"), str)
            or not isinstance(link.get("id"), str)
            for link in links
        ):
            return "invalid_relationship_contract"
    return None


def _classify_prefix(
    prefix: bytes, mapping: dict[str, Any]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, int]]:
    _validate_mapping(mapping)
    resolutions = {
        (entry["line"], entry["raw_line_sha256"]): entry
        for entry in mapping["row_resolutions"]
    }
    used: set[tuple[int, str]] = set()
    rows: list[dict[str, Any]] = []
    normalized_events: list[dict[str, Any]] = []
    counts = {classification: 0 for classification in sorted(CLASSIFICATIONS)}
    for line_number, raw in enumerate(_physical_lines(prefix), start=1):
        digest = _sha256(raw)
        override = resolutions.get((line_number, digest))
        entry: dict[str, Any] = {
            "line": line_number,
            "raw_line_sha256": digest,
            "raw_byte_length": len(raw),
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
            value = json.loads(raw.decode("utf-8"))
            if not isinstance(value, dict):
                parse_reason = "non_object_row"
        except UnicodeDecodeError:
            parse_reason = "invalid_utf8"
        except json.JSONDecodeError:
            parse_reason = "malformed_json"
        if override is not None:
            used.add((line_number, digest))
            impact = override["projection_impact"]
            resolution = override["resolution"]
            if impact != "independent" and resolution not in {
                "projection_epoch_reset",
                "superseded_by_canonical_task",
                "superseded_by_canonical_pack",
                "link_retracted",
            }:
                entry.update(
                    classification="blocked_unknown_or_future",
                    reason_codes=["current_impact_without_correction"],
                    projection_impact=impact,
                )
            else:
                entry.update(
                    classification="quarantined_historical",
                    reason_codes=[parse_reason or _strict_reader_reason(value) or "exact_caller_quarantine", override["reason_code"]],
                    projection_impact=impact,
                    deterministic_identity=override["deterministic_identity"],
                    resolution=resolution,
                )
            counts[entry["classification"]] += 1
            rows.append(entry)
            continue
        if parse_reason is None and isinstance(value, dict):
            entry["deterministic_identity"] = value.get("id") if isinstance(value.get("id"), str) else None
            current = value.get("format_version") == INDEX_FORMAT_VERSION and value.get("schema_version") == INDEX_SCHEMA_VERSION
            if current:
                try:
                    _validate_current_event(value)
                except (ValueError, TypeError) as exc:
                    parse_reason = f"invalid_current:{exc}"
                else:
                    entry.update(
                        classification="accepted_current",
                        reason_codes=["current_schema_valid"],
                        normalized_event_sha256=_sha256(_canonical_json(value)),
                    )
                    normalized_events.append(value)
            else:
                future = (
                    _is_int(value.get("format_version"))
                    and value["format_version"] > INDEX_FORMAT_VERSION
                ) or (
                    _is_int(value.get("schema_version"))
                    and value["schema_version"] > INDEX_SCHEMA_VERSION
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
                        classification = "mapped_legacy" if mapped else "normalized_legacy"
                        entry.update(
                            classification=classification,
                            reason_codes=reasons,
                            normalized_event_sha256=_sha256(_canonical_json(normalized)),
                        )
                        normalized_events.append(normalized)
        if entry["classification"] is None:
            entry.update(
                classification="blocked_unknown_or_future",
                reason_codes=[parse_reason or "unclassified"],
                projection_impact="unknown",
            )
        counts[entry["classification"]] += 1
        rows.append(entry)
    _require(used == set(resolutions), "caller mapping contains stale row resolutions")
    _require(all(set(row) == ROW_KEYS for row in rows), "independent row projection shape mismatch")
    return rows, normalized_events, counts


def _make_corrections(
    events: list[dict[str, Any]],
    mapping: dict[str, Any],
    transaction_id: str,
    task_anchor: dict[str, str],
    pack_anchor: dict[str, str],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    effective_at = mapping["effective_at"]
    task_id, pack_id = task_anchor["id"], pack_anchor["id"]
    task_path, pack_path = task_anchor["path"], pack_anchor["path"]
    state = _merge_state(events)
    corrections: list[dict[str, Any]] = []
    superseded_tasks: list[str] = []
    superseded_packs: list[str] = []
    before_tasks = sorted(
        item_id for item_id, item in state.items()
        if item.get("type") == "task" and item.get("status") == "active"
    )
    before_packs = sorted(
        item_id for item_id, item in state.items()
        if item.get("type") == "task_pack" and item.get("status") == "active"
    )
    before_aliases = sorted(
        item_id for item_id, item in state.items()
        if item_id != task_id
        and item.get("type") == "task"
        and item.get("path") == task_path
        and item.get("status") not in NON_ACTIVE_STATUSES
    )
    before_broken = [
        {"source_id": item_id, "rel": link["rel"], "id": link["id"]}
        for item_id in before_tasks
        for link in state.get(item_id, {}).get("links", [])
        if isinstance(link, dict) and link.get("id") not in state
    ]
    for item_id, item in sorted(state.items()):
        if item_id == task_id or item.get("type") != "task":
            continue
        if item.get("status") == "active" or (
            item.get("path") == task_path and item.get("status") not in NON_ACTIVE_STATUSES
        ):
            corrections.append(_versioned({
                "event": "upsert", "id": item_id, "type": "task", "status": "superseded",
                "path": str(item.get("path") or task_path), "title": str(item.get("title") or item_id),
                "updated_at": effective_at,
                "fields": {"migration_id": transaction_id, "superseded_by": task_id},
            }))
            superseded_tasks.append(item_id)
    for item_id, item in sorted(state.items()):
        if item_id == pack_id or item.get("type") != "task_pack":
            continue
        if item.get("status") == "active":
            corrections.append(_versioned({
                "event": "upsert", "id": item_id, "type": "task_pack", "status": "superseded",
                "path": str(item.get("path") or ".task/task_pack"), "title": str(item.get("title") or item_id),
                "updated_at": effective_at,
                "fields": {"migration_id": transaction_id, "superseded_by": pack_id},
            }))
            superseded_packs.append(item_id)
    current_links = state.get(task_id, {}).get("links", [])
    tombstones = [
        {"rel": link["rel"], "id": link["id"]}
        for link in current_links
        if isinstance(link, dict) and (
            link.get("id") not in state
            or link.get("rel") == "promoted_from_pack"
            or (link.get("rel") == "pack_for_task" and link.get("id") != pack_id)
        )
    ]
    corrections.append(_versioned({
        "event": "upsert", "id": task_id, "type": "task", "status": "active",
        "path": task_path, "title": str(state.get(task_id, {}).get("title") or task_id),
        "content_sha256": task_anchor["sha256"], "updated_at": effective_at,
        "fields": {"record_class": "mutable_alias", "canonical_id": task_id,
                   "projection_epoch": transaction_id, "link_tombstones": tombstones},
        "links": [{"rel": "pack_for_task", "id": pack_id}],
    }))
    corrections.append(_versioned({
        "event": "upsert", "id": pack_id, "type": "task_pack", "status": "active",
        "path": pack_path, "title": str(state.get(pack_id, {}).get("title") or pack_id),
        "content_sha256": pack_anchor["sha256"], "updated_at": effective_at,
        "fields": {"pack_id": pack_id, "projection_epoch": transaction_id,
                   "planning_relationship": "non_promotion"},
        "links": [{"rel": "pack_for_task", "id": task_id}],
    }))
    for ordinal, event in enumerate(corrections, start=1):
        fields = dict(event.get("fields") or {})
        fields["migration_correction_event_id"] = f"{transaction_id}-correction-{ordinal:06d}"
        event["fields"] = fields
    final = _merge_state(events + corrections)
    active_tasks = sorted(item_id for item_id, item in final.items() if item.get("type") == "task" and item.get("status") == "active")
    active_packs = sorted(item_id for item_id, item in final.items() if item.get("type") == "task_pack" and item.get("status") == "active")
    aliases = sorted(
        item_id for item_id, item in final.items()
        if item_id != task_id and item.get("type") == "task" and item.get("path") == task_path
        and item.get("status") not in NON_ACTIVE_STATUSES
    )
    broken = _broken_links(final, task_id)
    projection = {
        "before_active_task_ids": before_tasks,
        "before_active_task_count": len(before_tasks),
        "before_active_pack_ids": before_packs,
        "before_active_pack_count": len(before_packs),
        "before_duplicate_active_alias_ids": before_aliases,
        "before_duplicate_active_alias_count": len(before_aliases),
        "before_current_broken_links": before_broken,
        "before_current_broken_link_count": len(before_broken),
        "active_task_ids": active_tasks,
        "active_task_count": len(active_tasks),
        "active_pack_ids": active_packs,
        "active_pack_count": len(active_packs),
        "duplicate_active_alias_ids": aliases,
        "duplicate_active_alias_count": len(aliases),
        "current_broken_links": broken,
        "current_broken_link_count": len(broken),
        "current_active_pack_indexed": pack_id in final,
        "current_projection_status": "evaluated",
        "projection_completeness": "complete",
        "current_surface_blocker_count": int(active_tasks != [task_id]) + int(active_packs != [pack_id]) + len(aliases) + len(broken),
        "superseded_task_ids": superseded_tasks,
        "superseded_pack_ids": superseded_packs,
        "retracted_links": tombstones,
    }
    return corrections, projection


def _correction_identity(event: dict[str, Any]) -> tuple[str, str]:
    fields = event.get("fields") if isinstance(event.get("fields"), dict) else {}
    identity = fields.get("migration_correction_event_id")
    _require(isinstance(identity, str) and identity, "correction event identity is missing")
    return identity, _sha256(_canonical_json(event))


def _bind_quarantine_corrections(
    rows: list[dict[str, Any]],
    corrections: list[dict[str, Any]],
    task_id: str,
    pack_id: str,
) -> None:
    indexed = [(event, *_correction_identity(event)) for event in corrections]
    _require(len({identity for _event, identity, _digest in indexed}) == len(indexed), "correction identities repeat")
    for row in rows:
        if row["classification"] != "quarantined_historical" or row["projection_impact"] == "independent":
            continue
        resolution, identity = row["resolution"], row["deterministic_identity"]
        candidates: list[tuple[dict[str, Any], str, str]] = []
        if resolution == "projection_epoch_reset":
            candidates = [item for item in indexed if item[0].get("id") in {task_id, pack_id}]
        elif resolution == "superseded_by_canonical_task":
            candidates = [item for item in indexed if item[0].get("id") == identity and item[0].get("type") == "task" and item[0].get("status") == "superseded"]
        elif resolution == "superseded_by_canonical_pack":
            candidates = [item for item in indexed if item[0].get("id") == identity and item[0].get("type") == "task_pack" and item[0].get("status") == "superseded"]
        elif resolution == "link_retracted":
            candidates = [item for item in indexed if item[0].get("id") == task_id and bool(item[0].get("fields", {}).get("link_tombstones"))]
        _require(bool(candidates), f"quarantine line {row['line']} lacks exact correction ownership")
        row["correction_event_ids"] = [item[1] for item in candidates]
        row["correction_event_sha256s"] = [item[2] for item in candidates]


def _validate_quarantine_bindings(rows: list[dict[str, Any]], corrections: list[dict[str, Any]]) -> None:
    graph = {identity: digest for event in corrections for identity, digest in [_correction_identity(event)]}
    _require(len(graph) == len(corrections), "correction graph repeats an identity")
    for row in rows:
        ids, digests = row.get("correction_event_ids"), row.get("correction_event_sha256s")
        _require(isinstance(ids, list) and isinstance(digests, list) and len(ids) == len(digests), "row correction binding shape is invalid")
        non_independent = row.get("classification") == "quarantined_historical" and row.get("projection_impact") != "independent"
        _require(not non_independent or bool(ids), "non-independent quarantine lacks a correction binding")
        _require(non_independent or not ids, "independent row carries a correction binding")
        _require(len(set(ids)) == len(ids), "row repeats a correction identity")
        for identity, digest in zip(ids, digests, strict=True):
            _require(graph.get(identity) == digest, "quarantine correction binding mismatch")


def _manifest(
    transaction_id: str,
    prefix: bytes,
    rows: list[dict[str, Any]],
    counts: dict[str, int],
) -> dict[str, Any]:
    return {
        "schema_version": 2,
        "kind": "task_state_index_resolution_manifest",
        "migration_id": transaction_id,
        "source_prefix_sha256": _sha256(prefix),
        "source_prefix_byte_length": len(prefix),
        "source_raw_row_count": len(rows),
        "classification_counts": counts,
        "rows": rows,
        "raw_row_bodies_included": False,
    }


def _anchor_event(
    plan: dict[str, Any], receipt_sha: str, journal_sha: str, marker_sha: str
) -> dict[str, Any]:
    return _versioned({
        "event": "upsert", "id": plan["receipt_anchor_id"], "type": "schema_contract",
        "status": "informational", "path": plan["receipt_ref"],
        "title": "Task state legacy migration seal", "updated_at": plan["effective_at"],
        "fields": {
            MIGRATION_EVENT_FIELD: ANCHOR_KIND,
            "migration_id": plan["migration_id"],
            "receipt_ref": plan["receipt_ref"],
            "receipt_sha256": receipt_sha,
            "seal_sha256": plan["seal"]["line_sha256"],
            "commit_boundary_sha256": plan["expected_after_index_sha256"],
            "journal_ref": plan["journal_ref"],
            "journal_sha256": journal_sha,
            "completion_marker_ref": plan["completion_marker_ref"],
            "completion_marker_sha256": marker_sha,
        },
    })


def _render_markdown(events: list[dict[str, Any]], generated_at: str) -> bytes:
    state = _merge_state(events)
    groups: dict[str, list[dict[str, Any]]] = {}
    for item in state.values():
        groups.setdefault(str(item.get("type", "unknown")), []).append(item)
    lines = [
        "# Task State Index", "", f"- Generated: {generated_at}",
        "- Canonical JSONL: `.task/index.jsonl`", f"- Format version: {INDEX_FORMAT_VERSION}",
        f"- Schema version: {INDEX_SCHEMA_VERSION}", f"- Artifact count: {len(state)}", "",
    ]
    for item_type in sorted(groups):
        lines.extend([
            f"## {item_type}", "", "| ID | Status | Title | Path | Parent | Links | Updated |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ])
        for item in sorted(groups[item_type], key=lambda row: (str(row.get("status", "")), str(row.get("id", "")))):
            links = ", ".join(f"{link.get('rel')}:{link.get('id')}" for link in item.get("links", []))
            values = [item.get("id"), item.get("status"), item.get("title"), item.get("path"), item.get("parent_id"), links, item.get("updated_at")]
            escaped = [str(value or "").replace("|", "\\|").replace("\n", " ") for value in values]
            lines.append("| " + " | ".join(escaped) + " |")
        lines.append("")
    return ("\n".join(lines).rstrip() + "\n").encode("utf-8")


def _current_projection(
    state: dict[str, dict[str, Any]], root: Path
) -> tuple[dict[str, Any], dict[str, Any]]:
    tasks = sorted(item_id for item_id, item in state.items() if item.get("type") == "task" and item.get("status") == "active")
    packs = sorted(item_id for item_id, item in state.items() if item.get("type") == "task_pack" and item.get("status") == "active")
    _require(len(tasks) == 1 and len(packs) == 1, "current projection lacks exactly one active task and pack")
    task_id, pack_id = tasks[0], packs[0]
    task, pack = state[task_id], state[pack_id]
    aliases = sorted(
        item_id for item_id, item in state.items()
        if item_id != task_id and item.get("type") == "task" and item.get("path") == task.get("path")
        and item.get("status") not in NON_ACTIVE_STATUSES
    )
    broken = _broken_links(state, task_id)
    _require(not aliases and not broken, "current projection has duplicate aliases or broken task links")
    identities: dict[str, Any] = {}
    for label, item_id, item, expected_type in (
        ("task", task_id, task, "task"), ("pack", pack_id, pack, "task_pack")
    ):
        path_value = item.get("path")
        digest = item.get("content_sha256")
        _require(isinstance(path_value, str) and path_value, f"current {label} path is missing")
        candidate = Path(path_value)
        _require(not candidate.is_absolute() and all(part not in {"", ".", ".."} for part in candidate.parts), f"current {label} path is unsafe")
        path = _workspace_ref(root, path_value, f"current {label} artifact")
        _require(_is_sha256(digest), f"current {label} content hash is missing")
        _require(_sha256(path.read_bytes()) == digest, f"current {label} content hash mismatch")
        if label == "pack":
            try:
                pack_document = json.loads(path.read_text(encoding="utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ValueError("current pack is not valid JSON") from exc
            _require(isinstance(pack_document, dict) and pack_document.get("pack_id") == item_id, "current pack embedded identity mismatch")
        identities[label] = {
            "id": item_id,
            "type": expected_type,
            "path_sha256": _sha256(path_value.encode("utf-8")),
            "content_sha256": digest,
        }
    projection = {
        "active_task_count": 1,
        "active_pack_count": 1,
        "duplicate_active_alias_count": 0,
        "current_broken_link_count": 0,
        "projection_completeness": "complete",
    }
    return projection, identities
