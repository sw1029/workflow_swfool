"""Migration mapping contract and event normalization helpers."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .contracts import (
    ARTIFACT_TYPES,
    EVENT_KINDS,
    INDEX_FORMAT_VERSION,
    INDEX_SCHEMA_VERSION,
    LIFECYCLE_STATUSES,
    MAPPING_SCHEMA_VERSION,
    MISSING_TOKEN,
    MigrationError,
)

def _relative(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _physical_lines(payload: bytes) -> list[bytes]:
    if not payload:
        return []
    return payload.splitlines(keepends=True)


def _token(value: Any) -> str:
    return value if isinstance(value, str) else MISSING_TOKEN


def _mapping_entry(table: Any, token: str, axis: str) -> tuple[str | None, str] | None:
    if not isinstance(table, dict) or token not in table:
        return None
    entry = table[token]
    if not isinstance(entry, dict):
        raise MigrationError(f"Mapping {axis}.{token} must be an object")
    target = entry.get("to")
    reason = entry.get("reason_code")
    if target is not None and not isinstance(target, str):
        raise MigrationError(f"Mapping {axis}.{token}.to must be a string or null")
    if not isinstance(reason, str) or not reason:
        raise MigrationError(f"Mapping {axis}.{token}.reason_code must be non-empty")
    return target, reason


def _validate_mapping(mapping: dict[str, Any]) -> None:
    if mapping.get("schema_version") != MAPPING_SCHEMA_VERSION:
        raise MigrationError("Unsupported mapping manifest schema_version")
    if not isinstance(mapping.get("mapping_policy_id"), str) or not mapping["mapping_policy_id"]:
        raise MigrationError("Mapping manifest requires mapping_policy_id")
    if mapping.get("mapping_method") != "exact_token_review":
        raise MigrationError("Mapping manifest requires mapping_method=exact_token_review")
    if mapping.get("pattern_inference_used") is not False:
        raise MigrationError("Mapping manifest must attest pattern_inference_used=false")
    if not isinstance(mapping.get("effective_at"), str) or not mapping["effective_at"]:
        raise MigrationError("Mapping manifest requires deterministic effective_at")
    for axis in ("status_mappings", "event_mappings", "type_mappings"):
        table = mapping.get(axis)
        if not isinstance(table, dict):
            raise MigrationError(f"Mapping manifest requires {axis}")
        for token in table:
            _mapping_entry(table, token, axis)
    reasons = mapping.get("reason_codes")
    if not isinstance(reasons, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in reasons.items()):
        raise MigrationError("Mapping manifest requires string reason_codes")
    resolutions = mapping.get("row_resolutions", [])
    if not isinstance(resolutions, list):
        raise MigrationError("row_resolutions must be a list")
    seen: set[tuple[int, str]] = set()
    for entry in resolutions:
        if not isinstance(entry, dict):
            raise MigrationError("row_resolutions entries must be objects")
        key = (entry.get("line"), entry.get("raw_line_sha256"))
        if not isinstance(key[0], int) or key[0] < 1 or not isinstance(key[1], str) or not re.fullmatch(r"[0-9a-f]{64}", key[1]):
            raise MigrationError("row_resolutions require line and raw_line_sha256")
        if key in seen:
            raise MigrationError("Duplicate row_resolutions identity")
        seen.add(key)


def _resolution_map(mapping: dict[str, Any]) -> dict[tuple[int, str], dict[str, Any]]:
    return {
        (entry["line"], entry["raw_line_sha256"]): entry
        for entry in mapping.get("row_resolutions", [])
    }


def _infer_event(value: dict[str, Any]) -> str | None:
    if all(isinstance(value.get(field), str) and value[field] for field in ("type", "path")):
        return "upsert"
    if isinstance(value.get("links"), list) and not any(field in value for field in ("type", "status", "path")):
        return "link"
    return None


def _normalize_links(value: Any) -> list[dict[str, str]] | None:
    if value is None:
        return []
    if not isinstance(value, list):
        return None
    normalized: list[dict[str, str]] = []
    for link in value:
        if isinstance(link, dict) and isinstance(link.get("rel"), str) and isinstance(link.get("id"), str):
            normalized.append({"rel": link["rel"], "id": link["id"]})
            continue
        if isinstance(link, str) and ":" in link:
            rel, target = link.split(":", 1)
            if rel and target:
                normalized.append({"rel": rel, "id": target})
                continue
        return None
    return normalized


def _validate_current_event(
    event: dict[str, Any], *, strict_type: bool = True, allow_sparse_upsert: bool = False,
) -> None:
    if event.get("format_version") != INDEX_FORMAT_VERSION or event.get("schema_version") != INDEX_SCHEMA_VERSION:
        raise MigrationError("Current suffix event has unsupported version")
    if event.get("event") not in EVENT_KINDS:
        raise MigrationError("Current suffix event has unsupported discriminator")
    if not isinstance(event.get("id"), str) or not event["id"] or not isinstance(event.get("updated_at"), str) or not event["updated_at"]:
        raise MigrationError("Current suffix event lacks id or updated_at")
    status = event.get("status")
    if status is not None and status not in LIFECYCLE_STATUSES:
        raise MigrationError("Current suffix event has unsupported status")
    if event["event"] == "upsert":
        if strict_type:
            if allow_sparse_upsert and "type" not in event:
                pass
            elif event.get("type") not in ARTIFACT_TYPES:
                raise MigrationError("Current suffix upsert has unsupported type")
        if not allow_sparse_upsert:
            for field in ("type", "status", "path"):
                if not isinstance(event.get(field), str) or not event[field]:
                    raise MigrationError(f"Current suffix upsert lacks {field}")
    links = _normalize_links(event.get("links"))
    if event.get("links") is not None and links is None:
        raise MigrationError("Current suffix event has invalid links")
    fields = event.get("fields")
    if fields is not None and not isinstance(fields, dict):
        raise MigrationError("Current suffix event fields must be an object")
    tombstones = fields.get("link_tombstones") if isinstance(fields, dict) else None
    if tombstones is not None and _normalize_links(tombstones) is None:
        raise MigrationError("Current suffix event has invalid link_tombstones")


def writer_sparse_upsert_kind(event: dict[str, Any]) -> str | None:
    """Recognize only the two sparse lifecycle shapes emitted by the writer."""
    if event.get("event") != "upsert":
        return None
    base = {"format_version", "schema_version", "event", "id", "updated_at"}
    payload = set(event) - base
    if payload == {"status"}:
        return "status"
    if payload == {"fields"}:
        return "fields"
    return None


def validate_current_suffix_event(event: dict[str, Any], known_ids: set[str]) -> None:
    """Validate one post-seal event and advance its sequential ID context."""
    sparse_kind = writer_sparse_upsert_kind(event)
    if sparse_kind is not None:
        _validate_current_event(event, allow_sparse_upsert=True)
        if sparse_kind == "status" and (
            not isinstance(event.get("status"), str) or not event["status"]
        ):
            raise MigrationError("Sparse current suffix upsert lacks a valid status")
        if event["id"] not in known_ids:
            raise MigrationError("Sparse current suffix upsert references an unknown ID")
        return
    _validate_current_event(event)
    if event["event"] == "upsert":
        known_ids.add(event["id"])


def _preserve_legacy_token(
    normalized: dict[str, Any], axis: str, original: str, target: str, reason_code: str,
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
    binding = {"token": original, "reason_code": reason_code}
    if key in fields and fields[key] != binding:
        return f"conflicting_{key}"
    fields[key] = binding
    normalized["fields"] = fields
    return None
