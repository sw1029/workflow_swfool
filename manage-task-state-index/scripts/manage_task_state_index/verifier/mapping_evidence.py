"""Independent legacy mapping and prefix classification."""

from __future__ import annotations

import json
from typing import Any

from .core import (
    ARTIFACT_TYPES,
    CLASSIFICATIONS,
    EVENT_KINDS,
    INDEX_FORMAT_VERSION,
    INDEX_SCHEMA_VERSION,
    INFER_TOKEN,
    LIFECYCLE_STATUSES,
    MAPPING_SCHEMA_VERSION,
    MISSING_TOKEN,
    PROJECTION_IMPACTS,
    _canonical_json,
    _is_int,
    _is_sha256,
    _normalize_links,
    _physical_lines,
    _require,
    _sha256,
    _validate_current_event,
)

from .evidence_contracts import (
    MAPPING_ENTRY_KEYS,
    MAPPING_KEYS,
    ROW_KEYS,
    ROW_RESOLUTION_KEYS,
)


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
