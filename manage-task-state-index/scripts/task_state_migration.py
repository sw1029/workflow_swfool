#!/usr/bin/env python3
"""Sealed, append-only migration for legacy task-state ledgers.

The migration keeps the original ``.task/index.jsonl`` prefix byte-for-byte,
classifies every physical prefix row, and appends current-schema correction,
seal, and receipt-anchor events.  The companion strict-reader hook calls
``load_sealed_events_if_present``; without a valid seal *and* receipt this
module never authorizes malformed-prefix quarantine.
"""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import fcntl
import hashlib
import json
import os
import re
import stat
import tempfile
import threading
from pathlib import Path
from typing import Any, Iterator


TOOL_VERSION = "1.1.0"
PLAN_SCHEMA_VERSION = 2
MAPPING_SCHEMA_VERSION = 1
MANIFEST_SCHEMA_VERSION = 2
RECEIPT_SCHEMA_VERSION = 2
INDEX_FORMAT_VERSION = 2
INDEX_SCHEMA_VERSION = 1
MISSING_TOKEN = "__MISSING__"
INFER_TOKEN = "__INFER__"

EVENT_KINDS = {"upsert", "link"}
LIFECYCLE_STATUSES = {
    "active", "applied", "archived", "blocked", "candidate", "closed",
    "complete", "completed", "deferred", "deleted", "deprecated", "failed",
    "in_progress", "informational", "logged", "needs_review", "not_applicable",
    "obsolete", "open", "partial", "partially_resolved", "passed", "raw",
    "rejected", "resolved", "running", "skipped", "stale", "superseded",
    "terminal_blocked",
}
NON_ACTIVE_STATUSES = {
    "applied", "archived", "closed", "deleted", "deprecated", "obsolete",
    "rejected", "resolved", "superseded",
}
ARTIFACT_TYPES = {
    "task", "task_pack", "past_task", "candidate_task", "task_miss",
    "agent_log", "execution", "audit", "validation", "goal", "goal_prompt",
    "interview", "environment", "external_advice", "issue", "issue_resolution",
    "issue_map", "schema_contract", "schema_map",
}
CLASSIFICATIONS = {
    "accepted_current", "normalized_legacy", "mapped_legacy",
    "quarantined_historical", "blocked_unknown_or_future",
}
PROJECTION_IMPACTS = {"independent", "affected", "unknown"}
MIGRATION_EVENT_FIELD = "task_state_migration_event"
SEAL_KIND = "task_state_migration_seal"
ANCHOR_KIND = "task_state_migration_receipt_anchor"

_THREAD_LOCKS: dict[str, threading.RLock] = {}
_THREAD_LOCKS_GUARD = threading.Lock()


class MigrationError(ValueError):
    """Fail-closed migration or sealed-reader error."""


def _now() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha_file(path: Path) -> str:
    return _sha256(path.read_bytes())


def _canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _event_bytes(events: list[dict[str, Any]]) -> bytes:
    return b"".join(_canonical_bytes(event) for event in events)


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MigrationError(f"Invalid {label}: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise MigrationError(f"Invalid {label}: expected a JSON object: {path}")
    return value


def _atomic_write(path: Path, payload: bytes, mode: int = 0o644) -> None:
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
        _fsync_dir(path.parent)
    except BaseException:
        try:
            os.close(descriptor)
        except OSError:
            pass
        temporary.unlink(missing_ok=True)
        raise


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    _atomic_write(path, _canonical_bytes(value))


def _fsync_dir(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _thread_lock(root: Path) -> threading.RLock:
    key = str(root.resolve())
    with _THREAD_LOCKS_GUARD:
        return _THREAD_LOCKS.setdefault(key, threading.RLock())


@contextlib.contextmanager
def _index_lock(root: Path) -> Iterator[None]:
    root = root.resolve()
    task = root / ".task"
    if task.is_symlink() or (task.exists() and not task.is_dir()):
        raise MigrationError("Unsafe .task path")
    task.mkdir(parents=True, exist_ok=True)
    lock = task / "index.lock"
    flags = os.O_CREAT | os.O_RDWR
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    with _thread_lock(root):
        try:
            descriptor = os.open(lock, flags, 0o644)
        except OSError as exc:
            raise MigrationError("Unable to open non-symlink .task/index.lock") from exc
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            os.close(descriptor)
            raise MigrationError(".task/index.lock is not a regular file")
        with os.fdopen(descriptor, "a+b") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _root_identity(root: Path) -> dict[str, Any]:
    resolved = root.resolve(strict=True)
    stat = resolved.stat()
    return {"resolved_path": str(resolved), "device": stat.st_dev, "inode": stat.st_ino}


def _index_path(root: Path) -> Path:
    path = root / ".task" / "index.jsonl"
    if path.is_symlink() or not path.is_file():
        raise MigrationError(".task/index.jsonl must be a regular non-symlink file")
    return path


def _safe_ref(root: Path, ref: str, *, must_exist: bool = True) -> Path:
    if not isinstance(ref, str) or not ref or Path(ref).is_absolute():
        raise MigrationError(f"Unsafe migration sidecar ref: {ref!r}")
    root_resolved = root.resolve()
    candidate = root / ref
    if any(part in {"", ".", ".."} for part in Path(ref).parts):
        raise MigrationError(f"Unsafe migration sidecar ref: {ref!r}")
    current = root_resolved
    for part in Path(ref).parts:
        current = current / part
        if current.is_symlink():
            raise MigrationError(f"Symlink migration sidecar ref: {ref!r}")
    try:
        resolved = candidate.resolve(strict=must_exist)
    except OSError as exc:
        raise MigrationError(f"Missing or inaccessible migration sidecar ref: {ref!r}") from exc
    try:
        resolved.relative_to(root_resolved)
    except ValueError as exc:
        raise MigrationError(f"Migration sidecar escapes root: {ref!r}") from exc
    if must_exist and not resolved.is_file():
        raise MigrationError(f"Migration sidecar is not a regular file: {ref!r}")
    return resolved


def _validate_plan_anchors(root: Path, plan: dict[str, Any]) -> None:
    """Recheck caller-designated task/pack identities without trusting paths."""
    anchors = plan.get("anchors")
    if not isinstance(anchors, dict):
        raise MigrationError("Migration plan lacks exact caller anchors")
    checked: dict[str, tuple[Path, dict[str, Any]]] = {}
    for key, label in (("current_task", "current task"), ("current_pack", "current pack")):
        anchor = anchors.get(key)
        if not isinstance(anchor, dict):
            raise MigrationError(f"Migration plan lacks exact {label} anchor")
        relative = anchor.get("path")
        expected_sha = anchor.get("sha256")
        identity = anchor.get("id")
        if (
            not isinstance(relative, str)
            or not isinstance(identity, str)
            or not identity
            or not isinstance(expected_sha, str)
            or re.fullmatch(r"[0-9a-f]{64}", expected_sha) is None
        ):
            raise MigrationError(f"Invalid exact {label} anchor contract")
        try:
            path = _safe_ref(root, relative)
        except MigrationError as exc:
            raise MigrationError(f"Exact {label} anchor path is unsafe") from exc
        if _sha_file(path) != expected_sha:
            raise MigrationError(f"Exact {label} anchor mismatch")
        checked[key] = (path, anchor)
    pack_path, pack_anchor = checked["current_pack"]
    pack_value = _read_json(pack_path, "current pack anchor")
    if pack_value.get("pack_id") != pack_anchor["id"]:
        raise MigrationError("Current pack ID does not match caller-designated identity")


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


def inspect_store(root: Path) -> dict[str, Any]:
    root = root.resolve()
    prefix = _index_path(root).read_bytes()
    token_sets: dict[str, set[str]] = {"events": set(), "statuses": set(), "types": set()}
    malformed: list[dict[str, Any]] = []
    future: list[dict[str, Any]] = []
    strict_invalid: list[dict[str, Any]] = []
    for line_no, raw in enumerate(_physical_lines(prefix), start=1):
        try:
            value = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            malformed.append({"line": line_no, "raw_line_sha256": _sha256(raw), "reason": "malformed_json_or_utf8"})
            strict_invalid.append({"line": line_no, "raw_line_sha256": _sha256(raw), "reason": "malformed_json_or_utf8", "deterministic_identity": None})
            continue
        if not isinstance(value, dict):
            malformed.append({"line": line_no, "raw_line_sha256": _sha256(raw), "reason": "non_object_row"})
            strict_invalid.append({"line": line_no, "raw_line_sha256": _sha256(raw), "reason": "non_object_row", "deterministic_identity": None})
            continue
        token_sets["events"].add(_token(value.get("event")))
        token_sets["statuses"].add(_token(value.get("status")))
        token_sets["types"].add(_token(value.get("type")))
        if (isinstance(value.get("format_version"), int) and value["format_version"] > INDEX_FORMAT_VERSION) or (
            isinstance(value.get("schema_version"), int) and value["schema_version"] > INDEX_SCHEMA_VERSION
        ):
            future.append({"line": line_no, "raw_line_sha256": _sha256(raw)})
        strict_reason = _strict_reader_probe(value)
        if strict_reason is not None:
            strict_invalid.append({
                "line": line_no, "raw_line_sha256": _sha256(raw), "reason": strict_reason,
                "deterministic_identity": value.get("id") if isinstance(value.get("id"), str) else None,
            })
    return {
        "root_identity": _root_identity(root),
        "index_path": ".task/index.jsonl",
        "index_sha256": _sha256(prefix),
        "index_byte_length": len(prefix),
        "raw_row_count": len(_physical_lines(prefix)),
        "exact_tokens": {key: sorted(values) for key, values in token_sets.items()},
        "malformed_rows": malformed,
        "future_rows": future,
        "strict_reader_invalid_rows": strict_invalid,
        "strict_reader_invalid_count": len(strict_invalid),
        "mutation_performed": False,
    }


def build_plan(
    root: Path,
    expected_index_sha256: str,
    current_task_id: str,
    current_task_path: str,
    current_task_sha256: str,
    current_pack_id: str,
    current_pack_path: str,
    current_pack_sha256: str,
    mapping_path: Path,
) -> dict[str, Any]:
    root = root.resolve()
    prefix_path = _index_path(root)
    prefix = prefix_path.read_bytes()
    if _sha256(prefix) != expected_index_sha256:
        raise MigrationError("Source index SHA-256 drifted before planning")
    anchor_contract = {
        "anchors": {
            "current_task": {"id": current_task_id, "path": current_task_path, "sha256": current_task_sha256},
            "current_pack": {"id": current_pack_id, "path": current_pack_path, "sha256": current_pack_sha256},
        }
    }
    _validate_plan_anchors(root, anchor_contract)

    mapping_path = mapping_path.resolve(strict=True)
    mapping = _read_json(mapping_path, "mapping manifest")
    _validate_mapping(mapping)
    mapping_bytes = mapping_path.read_bytes()
    rows, normalized_events, counts = _classify_rows(prefix, mapping)
    seed = {
        "source_sha256": expected_index_sha256,
        "mapping_sha256": _sha256(mapping_bytes),
        "current_task_id": current_task_id,
        "current_task_sha256": current_task_sha256,
        "current_pack_id": current_pack_id,
        "current_pack_sha256": current_pack_sha256,
    }
    migration_id = f"tsm-{_sha256(_canonical_bytes(seed))[:24]}"
    corrections, projection = _make_corrections(
        normalized_events, mapping, migration_id,
        current_task_id, current_task_path, current_task_sha256,
        current_pack_id, current_pack_path, current_pack_sha256,
    )
    _bind_quarantine_corrections(rows, corrections, current_task_id, current_pack_id)
    _validate_quarantine_correction_bindings(rows, corrections)
    manifest = _manifest_payload(migration_id, prefix, rows, counts)
    manifest_sha = _sha256(_canonical_bytes(manifest))
    tx_ref = f".task/migrations/{migration_id}"
    correction_payload = _event_bytes(corrections)
    joiner = b"\n" if prefix and not prefix.endswith(b"\n") else b""
    correction_segment = joiner + correction_payload
    core: dict[str, Any] = {
        "schema_version": PLAN_SCHEMA_VERSION,
        "kind": "task_state_index_migration_plan",
        "tool_version": TOOL_VERSION,
        "migration_id": migration_id,
        "root_identity": _root_identity(root),
        "source_prefix": {
            "ref": ".task/index.jsonl", "sha256": expected_index_sha256,
            "byte_length": len(prefix), "raw_row_count": len(rows),
        },
        "mapping_manifest": {
            "source_ref": str(mapping_path), "sha256": _sha256(mapping_bytes),
            "schema_version": mapping["schema_version"], "mapping_policy_id": mapping["mapping_policy_id"],
            "snapshot_ref": f"{tx_ref}/mapping-manifest.json",
        },
        "resolution_manifest": {"ref": f"{tx_ref}/resolution-manifest.json", "sha256": manifest_sha},
        "source_snapshot_ref": f"{tx_ref}/legacy-prefix.jsonl",
        "plan_snapshot_ref": f"{tx_ref}/plan.json",
        "classification_counts": counts,
        "unclassified_count": counts["blocked_unknown_or_future"],
        "rows": rows,
        "correction_events": corrections,
        "projection": projection,
        "anchors": {
            "current_task": {"id": current_task_id, "path": current_task_path, "sha256": current_task_sha256},
            "current_pack": {"id": current_pack_id, "path": current_pack_path, "sha256": current_pack_sha256},
        },
        "effective_at": mapping["effective_at"],
        "transaction_directory_ref": tx_ref,
        "historical_rows_removed": 0,
        "historical_rows_reordered": 0,
        "original_row_bytes_modified": 0,
        "prefix_preserved": True,
    }
    contract_sha = _sha256(_canonical_bytes(core))
    seal_id = f"schema-{migration_id}-seal"
    seal = _versioned({
        "event": "upsert", "id": seal_id, "type": "schema_contract", "status": "informational",
        "path": f"{tx_ref}/receipt.json", "title": "Task state legacy migration seal",
        "updated_at": mapping["effective_at"],
        "fields": {
            MIGRATION_EVENT_FIELD: SEAL_KIND,
            "migration_id": migration_id,
            "plan_contract_sha256": contract_sha,
            "source_prefix_sha256": expected_index_sha256,
            "source_prefix_byte_length": len(prefix),
            "source_raw_row_count": len(rows),
            "mapping_manifest_sha256": _sha256(mapping_bytes),
            "resolution_manifest_sha256": manifest_sha,
            "correction_suffix_sha256": _sha256(correction_segment),
            "correction_suffix_byte_length": len(correction_segment),
        },
    })
    seal_line = _canonical_bytes(seal)
    boundary = prefix + correction_segment + seal_line
    plan = {
        **core,
        "plan_contract_sha256": contract_sha,
        "correction_suffix": {
            "ref": f"{tx_ref}/correction-suffix.jsonl", "sha256": _sha256(correction_segment),
            "byte_length": len(correction_segment), "event_count": len(corrections),
            "offset": len(prefix),
        },
        "seal": {
            "id": seal_id, "event": seal, "line_sha256": _sha256(seal_line),
            "offset": len(prefix) + len(correction_segment), "byte_length": len(seal_line),
        },
        "expected_after_index_sha256": _sha256(boundary),
        "expected_commit_boundary_byte_length": len(boundary),
        "receipt_ref": f"{tx_ref}/receipt.json",
        "receipt_anchor_id": seal_id,
        "journal_ref": f"{tx_ref}/journal.json",
        "prepare_journal_ref": f"{tx_ref}/journal-prepare.json",
        "completion_marker_ref": f"{tx_ref}/journal-completion.json",
        "render_snapshot_ref": f"{tx_ref}/rendered-index.md",
    }
    return plan


def _plan_manifest(plan: dict[str, Any]) -> dict[str, Any]:
    prefix_meta = plan["source_prefix"]
    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "kind": "task_state_index_resolution_manifest",
        "migration_id": plan["migration_id"],
        "source_prefix_sha256": prefix_meta["sha256"],
        "source_prefix_byte_length": prefix_meta["byte_length"],
        "source_raw_row_count": prefix_meta["raw_row_count"],
        "classification_counts": plan["classification_counts"],
        "rows": plan["rows"],
        "raw_row_bodies_included": False,
    }


def _validate_plan_contract(root: Path, plan_path: Path, expected_plan_sha: str, expected_index_sha: str) -> tuple[dict[str, Any], bytes, dict[str, Any], bytes]:
    plan_bytes = plan_path.read_bytes()
    if _sha256(plan_bytes) != expected_plan_sha:
        raise MigrationError("Plan SHA-256 mismatch")
    plan = _read_json(plan_path, "migration plan")
    if plan.get("schema_version") != PLAN_SCHEMA_VERSION or plan.get("kind") != "task_state_index_migration_plan":
        raise MigrationError("Unsupported migration plan")
    if plan.get("source_prefix", {}).get("sha256") != expected_index_sha:
        raise MigrationError("Expected source SHA does not match plan")
    if plan.get("root_identity") != _root_identity(root):
        raise MigrationError("Plan root identity mismatch")
    core_keys = {
        "schema_version", "kind", "tool_version", "migration_id", "root_identity", "source_prefix",
        "mapping_manifest", "resolution_manifest", "source_snapshot_ref", "plan_snapshot_ref",
        "classification_counts", "unclassified_count", "rows", "correction_events", "projection",
        "anchors", "effective_at", "transaction_directory_ref", "historical_rows_removed",
        "historical_rows_reordered", "original_row_bytes_modified", "prefix_preserved",
    }
    core = {key: plan[key] for key in core_keys}
    if _sha256(_canonical_bytes(core)) != plan.get("plan_contract_sha256"):
        raise MigrationError("Plan contract digest mismatch")
    mapping_source = Path(plan["mapping_manifest"]["source_ref"])
    mapping_bytes = mapping_source.read_bytes()
    if _sha256(mapping_bytes) != plan["mapping_manifest"]["sha256"]:
        raise MigrationError("Mapping manifest drifted after planning")
    mapping = _read_json(mapping_source, "mapping manifest")
    _validate_mapping(mapping)
    manifest = _plan_manifest(plan)
    if _sha256(_canonical_bytes(manifest)) != plan["resolution_manifest"]["sha256"]:
        raise MigrationError("Resolution manifest digest mismatch")
    # The exact segment (including a possible delimiter) is reconstructed from
    # the planned offset/length and the source bytes below.
    current_index = _index_path(root).read_bytes()
    prefix_length = plan["source_prefix"]["byte_length"]
    if len(current_index) < prefix_length:
        raise MigrationError("Source prefix drifted after planning")
    prefix = current_index[:prefix_length]
    if _sha256(prefix) != plan["source_prefix"]["sha256"]:
        raise MigrationError("Source prefix drifted after planning")
    joiner = b"\n" if prefix and not prefix.endswith(b"\n") else b""
    correction_segment = joiner + _event_bytes(plan["correction_events"])
    if _sha256(correction_segment) != plan["correction_suffix"]["sha256"] or len(correction_segment) != plan["correction_suffix"]["byte_length"]:
        raise MigrationError("Correction suffix digest mismatch")
    seal_line = _canonical_bytes(plan["seal"]["event"])
    if _sha256(seal_line) != plan["seal"]["line_sha256"]:
        raise MigrationError("Seal digest mismatch")
    if _sha256(prefix + correction_segment + seal_line) != plan["expected_after_index_sha256"]:
        raise MigrationError("Expected commit boundary digest mismatch")
    return plan, plan_bytes, mapping, mapping_bytes


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
        lines.extend([f"## {item_type}", "", "| ID | Status | Title | Path | Parent | Links | Updated |", "| --- | --- | --- | --- | --- | --- | --- |"])
        for item in sorted(groups[item_type], key=lambda row: (str(row.get("status", "")), str(row.get("id", "")))):
            links = ", ".join(f"{link.get('rel')}:{link.get('id')}" for link in item.get("links", []))
            values = [item.get("id"), item.get("status"), item.get("title"), item.get("path"), item.get("parent_id"), links, item.get("updated_at")]
            escaped = [str(value or "").replace("|", "\\|").replace("\n", " ") for value in values]
            lines.append("| " + " | ".join(escaped) + " |")
        lines.append("")
    return ("\n".join(lines).rstrip() + "\n").encode("utf-8")


def _receipt_payload(
    plan: dict[str, Any], plan_sha: str, prepare_journal_sha: str,
    journal_sha: str, completion_marker_sha: str, render_sha: str,
    recovery_status: str, committed_at: str,
) -> dict[str, Any]:
    counts = plan["classification_counts"]
    projection = plan["projection"]
    return {
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "kind": "task_state_index_migration",
        "transaction_id": plan["migration_id"],
        "tool_version": TOOL_VERSION,
        "transaction_started_at": committed_at,
        "transaction_committed_at": committed_at,
        "status": "committed",
        "source_prefix_ref": plan["source_snapshot_ref"],
        "source_prefix_sha256": plan["source_prefix"]["sha256"],
        "source_prefix_byte_length": plan["source_prefix"]["byte_length"],
        "source_raw_row_count": plan["source_prefix"]["raw_row_count"],
        "accepted_current_count": counts["accepted_current"],
        "normalized_legacy_count": counts["normalized_legacy"],
        "mapped_legacy_count": counts["mapped_legacy"],
        "quarantined_historical_count": counts["quarantined_historical"],
        "blocked_count": counts["blocked_unknown_or_future"],
        "mapping_manifest_ref": plan["mapping_manifest"]["snapshot_ref"],
        "mapping_manifest_sha256": plan["mapping_manifest"]["sha256"],
        "resolution_manifest_ref": plan["resolution_manifest"]["ref"],
        "resolution_manifest_sha256": plan["resolution_manifest"]["sha256"],
        "plan_ref": plan["plan_snapshot_ref"],
        "plan_sha256": plan_sha,
        "plan_contract_sha256": plan["plan_contract_sha256"],
        "correction_suffix_ref": plan["correction_suffix"]["ref"],
        "correction_suffix_sha256": plan["correction_suffix"]["sha256"],
        "correction_suffix_byte_length": plan["correction_suffix"]["byte_length"],
        "correction_suffix_count": plan["correction_suffix"]["event_count"],
        "correction_suffix_offset": plan["correction_suffix"]["offset"],
        "seal_id": plan["seal"]["id"],
        "seal_sha256": plan["seal"]["line_sha256"],
        "seal_offset": plan["seal"]["offset"],
        "seal_byte_length": plan["seal"]["byte_length"],
        "commit_boundary_length": plan["expected_commit_boundary_byte_length"],
        "commit_boundary_sha256": plan["expected_after_index_sha256"],
        "prefix_preserved": True,
        "historical_rows_removed": 0,
        "historical_rows_reordered": 0,
        "original_row_bytes_modified": 0,
        "canonical_task": plan["anchors"]["current_task"],
        "canonical_pack": plan["anchors"]["current_pack"],
        "superseded_task_id_digest": _sha256(_canonical_bytes(projection["superseded_task_ids"])),
        "superseded_pack_id_digest": _sha256(_canonical_bytes(projection["superseded_pack_ids"])),
        "retracted_link_pair_digest": _sha256(_canonical_bytes(projection["retracted_links"])),
        "active_task_count": projection["active_task_count"],
        "active_pack_count": projection["active_pack_count"],
        "duplicate_active_alias_count": projection["duplicate_active_alias_count"],
        "current_broken_link_count": projection["current_broken_link_count"],
        "before_active_task_count": projection["before_active_task_count"],
        "before_active_pack_count": projection["before_active_pack_count"],
        "before_duplicate_active_alias_count": projection["before_duplicate_active_alias_count"],
        "before_current_broken_link_count": projection["before_current_broken_link_count"],
        "current_active_pack_indexed": projection["current_active_pack_indexed"],
        "current_projection_status": projection["current_projection_status"],
        "projection_completeness": projection["projection_completeness"],
        "current_surface_blocker_count": projection["current_surface_blocker_count"],
        "strict_reader_status": "pass",
        "append_simulation_status": "pass",
        "audit_status": "current_projection_pass_historical_debt_preserved",
        "rendered_index_ref": plan["render_snapshot_ref"],
        "rendered_index_sha256": render_sha,
        "prepare_journal_ref": plan["prepare_journal_ref"],
        "prepare_journal_sha256": prepare_journal_sha,
        "journal_ref": plan["journal_ref"],
        "journal_sha256": journal_sha,
        "completion_marker_ref": plan["completion_marker_ref"],
        "completion_marker_sha256": completion_marker_sha,
        "recovery_status": recovery_status,
    }


def _committed_journal_payload(
    plan: dict[str, Any], prepare: dict[str, Any], committed_at: str,
    render_sha: str, recovery_status: str,
) -> dict[str, Any]:
    return {
        **prepare,
        "kind": "task_state_index_migration_journal",
        "state": "committed",
        "journal_updated_at": committed_at,
        "receipt_ref": plan["receipt_ref"],
        "seal_sha256": plan["seal"]["line_sha256"],
        "commit_boundary_sha256": plan["expected_after_index_sha256"],
        "rendered_index_ref": plan["render_snapshot_ref"],
        "rendered_index_sha256": render_sha,
        "recovery_status": recovery_status,
    }


def _completion_marker_payload(
    plan: dict[str, Any], prepare_sha: str, journal_sha: str,
    render_sha: str, recovery_status: str, committed_at: str, plan_sha: str,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": "task_state_index_migration_completion_marker",
        "transaction_id": plan["migration_id"],
        "state": "committed",
        "committed_at": committed_at,
        "prepare_journal_ref": plan["prepare_journal_ref"],
        "prepare_journal_sha256": prepare_sha,
        "journal_ref": plan["journal_ref"],
        "journal_sha256": journal_sha,
        "receipt_ref": plan["receipt_ref"],
        "plan_ref": plan["plan_snapshot_ref"],
        "plan_sha256": plan_sha,
        "seal_sha256": plan["seal"]["line_sha256"],
        "commit_boundary_length": plan["expected_commit_boundary_byte_length"],
        "commit_boundary_sha256": plan["expected_after_index_sha256"],
        "rendered_index_ref": plan["render_snapshot_ref"],
        "rendered_index_sha256": render_sha,
        "recovery_status": recovery_status,
    }
def _anchor_event(
    plan: dict[str, Any], receipt_sha: str, journal_sha: str = "0" * 64,
    completion_marker_sha: str = "0" * 64,
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
            "completion_marker_sha256": completion_marker_sha,
        },
    })


def _crash(point: str) -> None:
    if os.environ.get("TASK_STATE_MIGRATION_CRASH_AT") == point:
        raise RuntimeError(f"injected crash at {point}")


def _append_fsync(path: Path, payload: bytes) -> None:
    with path.open("ab", buffering=0) as handle:
        handle.write(payload)
        os.fsync(handle.fileno())
    _fsync_dir(path.parent)


def _validate_journal_base(journal: dict[str, Any], prepare: dict[str, Any]) -> None:
    if any(journal.get(key) != value for key, value in prepare.items() if key != "state"):
        raise MigrationError("Migration journal does not match immutable prepare contract")


def _stage_sidecars(
    root: Path, plan: dict[str, Any], plan_bytes: bytes, mapping_bytes: bytes,
    prefix: bytes, *, allow_existing_journal: bool,
) -> tuple[Path, dict[str, Any], str, dict[str, Any] | None]:
    tx_dir = _safe_ref(root, plan["transaction_directory_ref"], must_exist=False)
    if tx_dir.exists() and tx_dir.is_symlink():
        raise MigrationError("Unsafe migration transaction directory")
    tx_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "source": _safe_ref(root, plan["source_snapshot_ref"], must_exist=False),
        "plan": _safe_ref(root, plan["plan_snapshot_ref"], must_exist=False),
        "mapping": _safe_ref(root, plan["mapping_manifest"]["snapshot_ref"], must_exist=False),
        "manifest": _safe_ref(root, plan["resolution_manifest"]["ref"], must_exist=False),
        "correction": _safe_ref(root, plan["correction_suffix"]["ref"], must_exist=False),
        "prepare_journal": _safe_ref(root, plan["prepare_journal_ref"], must_exist=False),
        "journal": _safe_ref(root, plan["journal_ref"], must_exist=False),
    }
    manifest_bytes = _canonical_bytes(_plan_manifest(plan))
    joiner = b"\n" if prefix and not prefix.endswith(b"\n") else b""
    correction_bytes = joiner + _event_bytes(plan["correction_events"])
    for key, payload in (
        ("source", prefix), ("plan", plan_bytes), ("mapping", mapping_bytes),
        ("manifest", manifest_bytes), ("correction", correction_bytes),
    ):
        path = paths[key]
        if path.exists() and path.read_bytes() != payload:
            raise MigrationError(f"Conflicting existing migration sidecar: {path}")
        if not path.exists():
            _atomic_write(path, payload)
    prepare = {
        "schema_version": 1, "kind": "task_state_index_migration_journal_prepare",
        "transaction_id": plan["migration_id"], "state": "prepared",
        "prefix_sha256": plan["source_prefix"]["sha256"],
        "prefix_byte_length": plan["source_prefix"]["byte_length"],
        "expected_boundary_sha256": plan["expected_after_index_sha256"],
        "expected_boundary_byte_length": plan["expected_commit_boundary_byte_length"],
        "plan_ref": plan["plan_snapshot_ref"], "plan_sha256": _sha256(plan_bytes),
    }
    prepare_bytes = _canonical_bytes(prepare)
    if paths["prepare_journal"].exists() and paths["prepare_journal"].read_bytes() != prepare_bytes:
        raise MigrationError("Conflicting prepare journal")
    if not paths["prepare_journal"].exists():
        _atomic_write(paths["prepare_journal"], prepare_bytes)
    existing_journal: dict[str, Any] | None = None
    if paths["journal"].exists():
        if not allow_existing_journal:
            raise MigrationError("Existing migration journal requires explicit recover")
        existing_journal = _read_json(paths["journal"], "migration journal")
        _validate_journal_base(existing_journal, prepare)
    else:
        _atomic_json(paths["journal"], {**prepare, "journal_updated_at": _now()})
    return paths["journal"], prepare, _sha256(prepare_bytes), existing_journal


def _update_journal(path: Path, prepare: dict[str, Any], state: str, **fields: Any) -> None:
    _atomic_json(path, {**prepare, "state": state, "journal_updated_at": _now(), **fields})


def _validate_partial_tail_ownership(
    tail: bytes, boundary_tail: bytes, journal: dict[str, Any] | None,
) -> None:
    if journal is None or journal.get("state") != "partial_suffix":
        raise MigrationError("Unsealed tail lacks an existing partial-suffix journal")
    appended_length = journal.get("appended_byte_length")
    appended_sha = journal.get("appended_sha256")
    if appended_length != len(tail) or appended_sha != _sha256(tail):
        raise MigrationError("Partial-suffix journal does not bind the exact appended tail")
    if not tail or len(tail) >= len(boundary_tail) or not boundary_tail.startswith(tail):
        raise MigrationError("Unsealed tail is not an exact prefix of the journal-owned boundary payload")


def _find_anchor_lines(payload: bytes) -> list[tuple[int, bytes, dict[str, Any]]]:
    anchors: list[tuple[int, bytes, dict[str, Any]]] = []
    offset = 0
    for raw_line in _physical_lines(payload):
        try:
            value = json.loads(raw_line.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            offset += len(raw_line)
            continue
        fields = value.get("fields") if isinstance(value, dict) and isinstance(value.get("fields"), dict) else {}
        if fields.get(MIGRATION_EVENT_FIELD) == ANCHOR_KIND:
            anchors.append((offset, raw_line, value))
        offset += len(raw_line)
    return anchors


def _matching_plan_anchor(payload: bytes, plan: dict[str, Any]) -> tuple[int, bytes, dict[str, Any]] | None:
    for offset, raw, anchor in reversed(_find_anchor_lines(payload)):
        fields = anchor.get("fields", {})
        if fields.get("migration_id") != plan["migration_id"]:
            continue
        return offset, raw, anchor
    return None


def _committed_for_plan(root: Path, payload: bytes, plan: dict[str, Any]) -> dict[str, Any] | None:
    matching = _matching_plan_anchor(payload, plan)
    if matching is None:
        return None
    events, _results, receipt = _validate_receipt_graph(root, payload, *matching)
    return {"idempotent": True, "receipt": receipt, "event_count": len(events)}


def _apply_locked(
    root: Path, plan: dict[str, Any], plan_bytes: bytes, mapping_bytes: bytes,
    *, recovery_status: str,
) -> dict[str, Any]:
    index = _index_path(root)
    current = index.read_bytes()
    try:
        committed = _committed_for_plan(root, current, plan)
    except MigrationError:
        if recovery_status == "forward_completed" and _matching_plan_anchor(current, plan) is not None:
            return _forward_complete_anchored(root, plan, current)
        raise
    if committed is not None:
        if recovery_status == "forward_completed":
            receipt = committed["receipt"]
            render_snapshot = _safe_ref(root, receipt["rendered_index_ref"])
            _atomic_write(root / ".task" / "index.md", render_snapshot.read_bytes())
            committed["recovery_status"] = "forward_completed"
        return committed
    prefix_len = plan["source_prefix"]["byte_length"]
    prefix_sha = plan["source_prefix"]["sha256"]
    if len(current) < prefix_len or _sha256(current[:prefix_len]) != prefix_sha:
        raise MigrationError("Source prefix drift prevents migration or recovery")
    prefix = current[:prefix_len]
    if recovery_status != "forward_completed" and current != prefix:
        raise MigrationError("Initial apply requires the exact planned source prefix")
    if len(current) > prefix_len and not current.startswith(_safe_ref(root, plan["source_snapshot_ref"]).read_bytes()):
        raise MigrationError("Index does not retain the planned source prefix")

    journal_path, prepare, prepare_sha, existing_journal = _stage_sidecars(
        root, plan, plan_bytes, mapping_bytes, prefix,
        allow_existing_journal=recovery_status == "forward_completed",
    )
    _crash("after_prepare")
    correction = _safe_ref(root, plan["correction_suffix"]["ref"]).read_bytes()
    seal_line = _canonical_bytes(plan["seal"]["event"])
    boundary_tail = correction + seal_line
    boundary = prefix + boundary_tail

    current = index.read_bytes()
    if current == prefix:
        if os.environ.get("TASK_STATE_MIGRATION_CRASH_AT") == "after_partial_suffix":
            partial = boundary_tail[: max(1, len(boundary_tail) // 2)]
            _append_fsync(index, partial)
            _update_journal(
                journal_path, prepare, "partial_suffix",
                appended_byte_length=len(partial), appended_sha256=_sha256(partial),
            )
            _crash("after_partial_suffix")
        _append_fsync(index, boundary_tail)
    elif current == boundary:
        pass
    elif current.startswith(prefix) and len(current) < len(boundary):
        if recovery_status != "forward_completed":
            raise MigrationError("Initial apply refuses a non-prefix source tail; use explicit recover")
        tail = current[prefix_len:]
        _validate_partial_tail_ownership(tail, boundary_tail, existing_journal)
        with index.open("r+b") as handle:
            handle.truncate(prefix_len)
            handle.flush()
            os.fsync(handle.fileno())
        _append_fsync(index, boundary_tail)
    else:
        raise MigrationError("Conflicting tail prevents migration recovery")
    if _sha256(index.read_bytes()[: len(boundary)]) != plan["expected_after_index_sha256"]:
        raise MigrationError("Published seal boundary digest mismatch")
    _update_journal(journal_path, prepare, "sealed")
    _crash("after_suffix")

    # Build a deterministic administrative projection.  The receipt anchor
    # reuses the seal ID, title, path, status, and timestamp, so it is a
    # projection no-op apart from integrity fields not rendered in index.md.
    manifest_events = _normalized_events_from_plan(root, plan, mapping_bytes)
    placeholder_anchor = _anchor_event(plan, "0" * 64)
    render = _render_markdown(
        manifest_events + plan["correction_events"] + [plan["seal"]["event"], placeholder_anchor],
        plan["effective_at"],
    )
    render_snapshot = _safe_ref(root, plan["render_snapshot_ref"], must_exist=False)
    _atomic_write(render_snapshot, render)
    committed_at = _now()
    journal_payload = _committed_journal_payload(
        plan, prepare, committed_at, _sha256(render), recovery_status,
    )
    journal_bytes = _canonical_bytes(journal_payload)
    marker_payload = _completion_marker_payload(
        plan, prepare_sha, _sha256(journal_bytes), _sha256(render),
        recovery_status, committed_at, _sha256(plan_bytes),
    )
    marker_bytes = _canonical_bytes(marker_payload)
    receipt = _receipt_payload(
        plan, _sha256(plan_bytes), prepare_sha, _sha256(journal_bytes),
        _sha256(marker_bytes), _sha256(render), recovery_status, committed_at,
    )
    receipt_path = _safe_ref(root, plan["receipt_ref"], must_exist=False)
    receipt_bytes = _canonical_bytes(receipt)
    _atomic_write(receipt_path, receipt_bytes)
    _update_journal(journal_path, prepare, "receipt_written", receipt_sha256=_sha256(receipt_bytes))
    _crash("after_receipt")
    _crash("after_receipt_before_marker")

    anchor = _anchor_event(
        plan, _sha256(receipt_bytes), _sha256(journal_bytes), _sha256(marker_bytes),
    )
    anchor_line = _canonical_bytes(anchor)
    current = index.read_bytes()
    anchor_present = any(
        isinstance(value, dict)
        and isinstance(value.get("fields"), dict)
        and value["fields"].get(MIGRATION_EVENT_FIELD) == ANCHOR_KIND
        and value["fields"].get("migration_id") == plan["migration_id"]
        and value["fields"].get("receipt_sha256") == _sha256(receipt_bytes)
        for _offset, _raw, value in _find_anchor_lines(current)
    )
    if not anchor_present:
        _append_fsync(index, anchor_line)
    _update_journal(journal_path, prepare, "receipt_anchored", receipt_sha256=_sha256(receipt_bytes))
    _crash("after_anchor")

    _atomic_write(journal_path, journal_bytes)
    completion_marker = _safe_ref(root, plan["completion_marker_ref"], must_exist=False)
    if completion_marker.exists() and completion_marker.read_bytes() != marker_bytes:
        raise MigrationError("Conflicting immutable migration completion marker")
    if not completion_marker.exists():
        _atomic_write(completion_marker, marker_bytes)
    _crash("after_completion_marker_before_render")
    _atomic_write(root / ".task" / "index.md", render)
    _crash("after_render")
    events_and_results = load_sealed_events_if_present(root)
    if events_and_results is None:
        raise MigrationError("Committed migration was not accepted by the strict sealed reader")
    return {
        "idempotent": False,
        "transaction_id": plan["migration_id"],
        "receipt_ref": plan["receipt_ref"],
        "receipt_sha256": _sha256(receipt_bytes),
        "commit_boundary_sha256": plan["expected_after_index_sha256"],
        "final_index_sha256": _sha_file(index),
        "event_count": len(events_and_results[0]),
        "recovery_status": recovery_status,
    }


def apply_plan(
    root: Path, plan_path: Path, expected_plan_sha: str, expected_index_sha: str,
    *, dry_run: bool = False, recovery_status: str = "not_required",
) -> dict[str, Any]:
    root = root.resolve()
    plan, plan_bytes, _mapping, mapping_bytes = _validate_plan_contract(
        root, plan_path.resolve(strict=True), expected_plan_sha, expected_index_sha,
    )
    if plan.get("unclassified_count") != 0:
        raise MigrationError("Migration apply requires unclassified_count=0")
    projection = plan.get("projection", {})
    required = {
        "active_task_count": 1, "active_pack_count": 1,
        "duplicate_active_alias_count": 0, "current_broken_link_count": 0,
        "current_surface_blocker_count": 0,
    }
    if any(projection.get(key) != value for key, value in required.items()) or projection.get("projection_completeness") != "complete":
        raise MigrationError("Migration plan does not reconcile the current projection")
    if dry_run:
        current = _index_path(root).read_bytes()
        if _sha256(current) != expected_index_sha:
            raise MigrationError("Source drift before dry-run")
        _validate_plan_anchors(root, plan)
        return {
            "dry_run": True, "mutation_performed": False,
            "transaction_id": plan["migration_id"], "plan_sha256": expected_plan_sha,
            "expected_commit_boundary_sha256": plan["expected_after_index_sha256"],
            "projection": projection,
        }
    _validate_plan_anchors(root, plan)
    with _index_lock(root):
        _validate_plan_anchors(root, plan)
        return _apply_locked(root, plan, plan_bytes, mapping_bytes, recovery_status=recovery_status)


def recover_transaction(root: Path, transaction_id: str) -> dict[str, Any]:
    root = root.resolve()
    if not re.fullmatch(r"tsm-[0-9a-f]{24}", transaction_id):
        raise MigrationError("Invalid transaction ID")
    plan_path = _safe_ref(root, f".task/migrations/{transaction_id}/plan.json")
    plan_bytes = plan_path.read_bytes()
    plan = _read_json(plan_path, "migration recovery plan")
    mapping_path = _safe_ref(root, plan["mapping_manifest"]["snapshot_ref"])
    mapping_bytes = mapping_path.read_bytes()
    if _sha256(mapping_bytes) != plan["mapping_manifest"]["sha256"]:
        raise MigrationError("Recovery mapping snapshot mismatch")
    with _index_lock(root):
        _validate_plan_anchors(root, plan)
        return _apply_locked(root, plan, plan_bytes, mapping_bytes, recovery_status="forward_completed")


def _forward_complete_anchored(
    root: Path, plan: dict[str, Any], payload: bytes,
) -> dict[str, Any]:
    matching = _matching_plan_anchor(payload, plan)
    if matching is None:
        raise MigrationError("Forward completion requires the exact transaction anchor")
    events, _results, receipt = _validate_receipt_graph(
        root, payload, *matching, allow_pending_completion=True,
    )
    marker_path = _safe_ref(root, receipt["completion_marker_ref"], must_exist=False)
    if marker_path.exists():
        raise MigrationError("Completion marker exists but the committed graph is invalid")
    prepare_path = _safe_ref(root, receipt["prepare_journal_ref"])
    prepare = _read_json(prepare_path, "immutable migration prepare journal")
    committed_at = receipt.get("transaction_committed_at")
    recovery_status = receipt.get("recovery_status")
    if not isinstance(committed_at, str) or not isinstance(recovery_status, str):
        raise MigrationError("Migration receipt lacks completion timing or recovery status")
    expected_journal = _canonical_bytes(_committed_journal_payload(
        plan, prepare, committed_at, receipt["rendered_index_sha256"], recovery_status,
    ))
    expected_marker = _canonical_bytes(_completion_marker_payload(
        plan, receipt["prepare_journal_sha256"], _sha256(expected_journal),
        receipt["rendered_index_sha256"], recovery_status, committed_at,
        receipt["plan_sha256"],
    ))
    if _sha256(expected_journal) != receipt["journal_sha256"]:
        raise MigrationError("Receipt does not bind the reconstructable committed journal")
    if _sha256(expected_marker) != receipt["completion_marker_sha256"]:
        raise MigrationError("Receipt does not bind the reconstructable completion marker")
    journal_path = _safe_ref(root, receipt["journal_ref"])
    if journal_path.read_bytes() != expected_journal:
        pending = _read_json(journal_path, "pending migration journal")
        _validate_journal_base(pending, prepare)
        if pending.get("state") not in {"receipt_written", "receipt_anchored", "committed_render_pending"}:
            raise MigrationError("Pending journal state is not eligible for forward completion")
        receipt_sha = _sha_file(_safe_ref(root, plan["receipt_ref"]))
        if pending.get("receipt_sha256") != receipt_sha:
            raise MigrationError("Pending journal does not bind the anchored receipt")
    render = _safe_ref(root, receipt["rendered_index_ref"]).read_bytes()
    _atomic_write(journal_path, expected_journal)
    _atomic_write(marker_path, expected_marker)
    _atomic_write(root / ".task" / "index.md", render)
    checked_events, _checked_results, _checked_receipt = _validate_receipt_graph(
        root, _index_path(root).read_bytes(), *matching,
    )
    return {
        "idempotent": True,
        "transaction_id": plan["migration_id"],
        "receipt_ref": plan["receipt_ref"],
        "receipt_sha256": _sha_file(_safe_ref(root, plan["receipt_ref"])),
        "event_count": len(checked_events),
        "recovery_status": "forward_completed",
    }


def _normalized_events_from_plan(root: Path, plan: dict[str, Any], mapping_bytes: bytes | None = None) -> list[dict[str, Any]]:
    snapshot = _safe_ref(root, plan["source_snapshot_ref"])
    prefix = snapshot.read_bytes()
    if _sha256(prefix) != plan["source_prefix"]["sha256"]:
        raise MigrationError("Source snapshot digest mismatch")
    if mapping_bytes is None:
        mapping_path = _safe_ref(root, plan["mapping_manifest"]["snapshot_ref"])
        mapping_bytes = mapping_path.read_bytes()
    if _sha256(mapping_bytes) != plan["mapping_manifest"]["sha256"]:
        raise MigrationError("Mapping snapshot digest mismatch")
    try:
        mapping = json.loads(mapping_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MigrationError("Invalid mapping snapshot") from exc
    if not isinstance(mapping, dict):
        raise MigrationError("Invalid mapping snapshot object")
    _validate_mapping(mapping)
    rows, events, counts = _classify_rows(prefix, mapping)
    _bind_quarantine_corrections(
        rows, plan["correction_events"],
        plan["anchors"]["current_task"]["id"], plan["anchors"]["current_pack"]["id"],
    )
    _validate_quarantine_correction_bindings(rows, plan["correction_events"])
    expected_rows = plan["rows"]
    if rows != expected_rows or counts != plan["classification_counts"]:
        raise MigrationError("Prefix reclassification differs from sealed plan")
    return events


def _validate_receipt_graph(
    root: Path, payload: bytes, anchor_offset: int, anchor_raw: bytes,
    anchor: dict[str, Any], *, allow_pending_completion: bool = False,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    _validate_current_event(anchor)
    fields = anchor.get("fields", {})
    receipt_ref = fields.get("receipt_ref")
    receipt_sha = fields.get("receipt_sha256")
    if not isinstance(receipt_ref, str) or not isinstance(receipt_sha, str):
        raise MigrationError("Migration receipt anchor lacks exact receipt binding")
    receipt_path = _safe_ref(root, receipt_ref)
    receipt_bytes = receipt_path.read_bytes()
    if _sha256(receipt_bytes) != receipt_sha:
        raise MigrationError("Migration receipt digest mismatch")
    receipt = _read_json(receipt_path, "migration receipt")
    if receipt.get("kind") != "task_state_index_migration" or receipt.get("status") != "committed":
        raise MigrationError("Migration receipt is not committed")
    if receipt.get("transaction_id") != fields.get("migration_id") or receipt.get("seal_sha256") != fields.get("seal_sha256"):
        raise MigrationError("Migration receipt subject mismatch")
    for key in ("journal_ref", "journal_sha256", "completion_marker_ref", "completion_marker_sha256"):
        if fields.get(key) != receipt.get(key):
            raise MigrationError("Migration anchor completion binding mismatch")
    prefix_len = receipt.get("source_prefix_byte_length")
    if not isinstance(prefix_len, int) or prefix_len < 0 or len(payload) < prefix_len:
        raise MigrationError("Invalid sealed prefix boundary")
    prefix = payload[:prefix_len]
    if _sha256(prefix) != receipt.get("source_prefix_sha256"):
        raise MigrationError("Sealed prefix digest mismatch")
    snapshot = _safe_ref(root, receipt["source_prefix_ref"])
    if snapshot.read_bytes() != prefix:
        raise MigrationError("Immutable prefix snapshot is not byte-identical")
    for ref_key, sha_key in (
        ("mapping_manifest_ref", "mapping_manifest_sha256"),
        ("resolution_manifest_ref", "resolution_manifest_sha256"),
        ("plan_ref", "plan_sha256"),
        ("correction_suffix_ref", "correction_suffix_sha256"),
        ("rendered_index_ref", "rendered_index_sha256"),
        ("prepare_journal_ref", "prepare_journal_sha256"),
    ):
        sidecar = _safe_ref(root, receipt[ref_key])
        if _sha_file(sidecar) != receipt[sha_key]:
            raise MigrationError(f"Migration sidecar digest mismatch: {ref_key}")
    if not allow_pending_completion:
        for ref_key, sha_key in (
            ("journal_ref", "journal_sha256"),
            ("completion_marker_ref", "completion_marker_sha256"),
        ):
            sidecar = _safe_ref(root, receipt[ref_key])
            if _sha_file(sidecar) != receipt[sha_key]:
                raise MigrationError(f"Migration sidecar digest mismatch: {ref_key}")
        journal = _read_json(_safe_ref(root, receipt["journal_ref"]), "committed migration journal")
        marker = _read_json(_safe_ref(root, receipt["completion_marker_ref"]), "migration completion marker")
        if journal.get("state") != "committed" or journal.get("transaction_id") != receipt["transaction_id"]:
            raise MigrationError("Committed migration journal subject mismatch")
        marker_bindings = {
            "kind": "task_state_index_migration_completion_marker",
            "transaction_id": receipt["transaction_id"],
            "state": "committed",
            "prepare_journal_ref": receipt["prepare_journal_ref"],
            "prepare_journal_sha256": receipt["prepare_journal_sha256"],
            "journal_ref": receipt["journal_ref"],
            "journal_sha256": receipt["journal_sha256"],
            "receipt_ref": receipt_ref,
            "plan_ref": receipt["plan_ref"],
            "plan_sha256": receipt["plan_sha256"],
            "seal_sha256": receipt["seal_sha256"],
            "commit_boundary_length": receipt["commit_boundary_length"],
            "commit_boundary_sha256": receipt["commit_boundary_sha256"],
            "rendered_index_ref": receipt["rendered_index_ref"],
            "rendered_index_sha256": receipt["rendered_index_sha256"],
            "recovery_status": receipt["recovery_status"],
        }
        if any(marker.get(key) != value for key, value in marker_bindings.items()):
            raise MigrationError("Migration completion marker graph mismatch")
    manifest = _read_json(_safe_ref(root, receipt["resolution_manifest_ref"]), "resolution manifest")
    if manifest.get("migration_id") != receipt["transaction_id"] or manifest.get("source_prefix_sha256") != receipt["source_prefix_sha256"]:
        raise MigrationError("Resolution manifest subject mismatch")
    raw_lines = _physical_lines(prefix)
    manifest_rows = manifest.get("rows")
    if not isinstance(manifest_rows, list) or len(manifest_rows) != len(raw_lines) or len(raw_lines) != receipt["source_raw_row_count"]:
        raise MigrationError("Resolution manifest does not account for every prefix row")
    seen: set[tuple[int, str]] = set()
    for line_no, (raw, entry) in enumerate(zip(raw_lines, manifest_rows, strict=True), start=1):
        if not isinstance(entry, dict) or entry.get("line") != line_no or entry.get("raw_line_sha256") != _sha256(raw):
            raise MigrationError("Resolution manifest line/hash mismatch")
        key = (line_no, entry["raw_line_sha256"])
        if key in seen or entry.get("classification") not in CLASSIFICATIONS:
            raise MigrationError("Resolution manifest has duplicate or invalid disposition")
        seen.add(key)
    if any(entry.get("classification") == "blocked_unknown_or_future" for entry in manifest_rows):
        raise MigrationError("Committed manifest contains blocked rows")

    correction_offset = receipt["correction_suffix_offset"]
    correction_length = receipt["correction_suffix_byte_length"]
    seal_offset = receipt["seal_offset"]
    seal_length = receipt["seal_byte_length"]
    if correction_offset != prefix_len or seal_offset != correction_offset + correction_length:
        raise MigrationError("Migration boundary offsets are inconsistent")
    correction = payload[correction_offset:seal_offset]
    if len(correction) != correction_length or _sha256(correction) != receipt["correction_suffix_sha256"]:
        raise MigrationError("Correction suffix boundary mismatch")
    seal_raw = payload[seal_offset:seal_offset + seal_length]
    if len(seal_raw) != seal_length or _sha256(seal_raw) != receipt["seal_sha256"]:
        raise MigrationError("Migration seal boundary mismatch")
    if receipt["commit_boundary_length"] != seal_offset + seal_length or _sha256(payload[:receipt["commit_boundary_length"]]) != receipt["commit_boundary_sha256"]:
        raise MigrationError("Migration commit boundary mismatch")
    try:
        seal = json.loads(seal_raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MigrationError("Migration seal is invalid JSON") from exc
    _validate_current_event(seal)
    seal_fields = seal.get("fields", {})
    if seal_fields.get(MIGRATION_EVENT_FIELD) != SEAL_KIND or seal_fields.get("migration_id") != receipt["transaction_id"]:
        raise MigrationError("Migration seal subject mismatch")
    if seal_fields.get("plan_contract_sha256") != receipt["plan_contract_sha256"] or seal_fields.get("resolution_manifest_sha256") != receipt["resolution_manifest_sha256"]:
        raise MigrationError("Migration seal graph binding mismatch")
    if anchor_offset < receipt["commit_boundary_length"]:
        raise MigrationError("Receipt anchor precedes migration seal")

    plan = _read_json(_safe_ref(root, receipt["plan_ref"]), "sealed migration plan")
    if plan.get("rows") != manifest_rows:
        raise MigrationError("Plan and resolution manifest row bindings differ")
    correction_events: list[dict[str, Any]] = []
    for raw in _physical_lines(correction):
        if not raw.strip():
            continue
        try:
            correction_event = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise MigrationError("Correction suffix contains malformed JSON") from exc
        if not isinstance(correction_event, dict):
            raise MigrationError("Correction suffix contains a non-object event")
        _validate_current_event(correction_event)
        correction_events.append(correction_event)
    _validate_quarantine_correction_bindings(manifest_rows, correction_events)
    events = _normalized_events_from_plan(root, plan)
    known_suffix_ids = {
        str(event["id"])
        for event in events
        if isinstance(event.get("id"), str) and event["id"]
    }
    suffix = payload[prefix_len:]
    suffix_events: list[dict[str, Any]] = []
    suffix_results: list[dict[str, Any]] = []
    for relative_line_no, raw in enumerate(_physical_lines(suffix), start=1):
        if not raw.strip():
            continue
        try:
            event = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise MigrationError("Malformed post-prefix suffix row") from exc
        if not isinstance(event, dict):
            raise MigrationError("Non-object post-prefix suffix row")
        validate_current_suffix_event(event, known_suffix_ids)
        suffix_events.append(event)
        suffix_results.append({
            "line_no": len(raw_lines) + relative_line_no,
            "migration_status": "current", "projection_impact": "independent",
            "row_identity": event.get("id"), "malformed_reason": None,
        })
    prefix_results = [
        {
            "line_no": entry["line"], "migration_status": entry["classification"],
            "projection_impact": entry["projection_impact"],
            "row_identity": entry.get("deterministic_identity"), "malformed_reason": None,
        }
        for entry in manifest_rows
    ]
    return events + suffix_events, prefix_results + suffix_results, receipt


def load_sealed_events_if_present(root: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]] | None:
    """Return exact sealed projection, or ``None`` when no seal is present.

    If any receipt-anchor marker exists but its graph is invalid, raise instead
    of falling back to permissive legacy parsing.
    """
    root = Path(root).resolve()
    index = root / ".task" / "index.jsonl"
    if not index.is_file() or index.is_symlink():
        return None
    payload = index.read_bytes()
    anchors = _find_anchor_lines(payload)
    if not anchors:
        return None
    errors: list[str] = []
    for offset, raw, anchor in reversed(anchors):
        try:
            events, results, _receipt = _validate_receipt_graph(root, payload, offset, raw, anchor)
            return events, results
        except (KeyError, TypeError, MigrationError) as exc:
            errors.append(str(exc))
    raise MigrationError("No valid task-state migration receipt graph: " + "; ".join(errors[:3]))


def _migration_boundary_projection(root: Path, receipt: dict[str, Any]) -> dict[str, Any]:
    """Reconstruct and verify the immutable projection at the migration seal."""
    plan = _read_json(_safe_ref(root, receipt["plan_ref"]), "sealed migration plan")
    task = receipt.get("canonical_task")
    pack = receipt.get("canonical_pack")
    if not isinstance(task, dict) or not isinstance(pack, dict):
        raise MigrationError("Migration receipt lacks canonical boundary identities")
    if task != plan.get("anchors", {}).get("current_task") or pack != plan.get("anchors", {}).get("current_pack"):
        raise MigrationError("Migration receipt boundary identities differ from the sealed plan")

    projection = plan.get("projection")
    if not isinstance(projection, dict):
        raise MigrationError("Sealed migration plan lacks boundary projection")
    receipt_projection_keys = (
        "active_task_count", "active_pack_count", "duplicate_active_alias_count",
        "current_broken_link_count", "current_active_pack_indexed",
        "current_projection_status", "projection_completeness",
        "current_surface_blocker_count",
    )
    if any(receipt.get(key) != projection.get(key) for key in receipt_projection_keys):
        raise MigrationError("Migration receipt boundary projection differs from the sealed plan")

    boundary_events = _normalized_events_from_plan(root, plan) + plan["correction_events"]
    boundary_state = _merge_state(boundary_events)
    task_id = task.get("id")
    pack_id = pack.get("id")
    task_path = task.get("path")
    active_tasks = sorted(
        item_id for item_id, item in boundary_state.items()
        if item.get("type") == "task" and item.get("status") == "active"
    )
    active_packs = sorted(
        item_id for item_id, item in boundary_state.items()
        if item.get("type") == "task_pack" and item.get("status") == "active"
    )
    duplicates = sorted(
        item_id for item_id, item in boundary_state.items()
        if item_id != task_id and item.get("type") == "task" and item.get("path") == task_path
        and item.get("status") not in NON_ACTIVE_STATUSES
    )
    broken = _broken_links(boundary_state, str(task_id)) if isinstance(task_id, str) else []
    boundary_task = boundary_state.get(str(task_id), {})
    boundary_pack = boundary_state.get(str(pack_id), {})
    task_identity_bound = (
        boundary_task.get("type") == "task"
        and boundary_task.get("status") == "active"
        and boundary_task.get("path") == task.get("path")
        and boundary_task.get("content_sha256") == task.get("sha256")
    )
    pack_identity_bound = (
        boundary_pack.get("type") == "task_pack"
        and boundary_pack.get("status") == "active"
        and boundary_pack.get("path") == pack.get("path")
        and boundary_pack.get("content_sha256") == pack.get("sha256")
    )
    complete = (
        isinstance(task_id, str) and isinstance(pack_id, str)
        and active_tasks == [task_id] and active_packs == [pack_id]
        and not duplicates and not broken
        and task_identity_bound and pack_identity_bound
    )
    if not complete:
        raise MigrationError("Migration boundary projection is incomplete")
    return {
        "migration_boundary_task_id": task_id,
        "migration_boundary_pack_id": pack_id,
        "migration_boundary_active_task_count": len(active_tasks),
        "migration_boundary_active_pack_count": len(active_packs),
        "migration_boundary_duplicate_active_alias_count": len(duplicates),
        "migration_boundary_broken_link_count": len(broken),
        "migration_boundary_projection_status": "evaluated",
        "migration_boundary_projection_completeness": "complete",
    }


def _current_projection(state: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Evaluate the live append-only projection independently of receipt anchors."""
    active_tasks = sorted(
        item_id for item_id, item in state.items()
        if item.get("type") == "task" and item.get("status") == "active"
    )
    active_packs = sorted(
        item_id for item_id, item in state.items()
        if item.get("type") == "task_pack" and item.get("status") == "active"
    )
    current_task_id = active_tasks[0] if len(active_tasks) == 1 else None
    current_pack_id = active_packs[0] if len(active_packs) == 1 else None
    current_task_path = state.get(current_task_id, {}).get("path") if current_task_id else None
    duplicates = sorted(
        item_id for item_id, item in state.items()
        if current_task_id is not None and item_id != current_task_id
        and item.get("type") == "task" and item.get("path") == current_task_path
        and item.get("status") not in NON_ACTIVE_STATUSES
    )
    broken = _broken_links(state, current_task_id) if current_task_id is not None else []
    task_indexed = (
        current_task_id is not None
        and state.get(current_task_id, {}).get("type") == "task"
        and state.get(current_task_id, {}).get("status") == "active"
    )
    pack_indexed = (
        current_pack_id is not None
        and state.get(current_pack_id, {}).get("type") == "task_pack"
        and state.get(current_pack_id, {}).get("status") == "active"
    )
    evaluated = task_indexed and pack_indexed
    complete = evaluated and not duplicates and not broken
    return {
        "active_task_ids": active_tasks,
        "active_pack_ids": active_packs,
        "current_active_task_id": current_task_id,
        "current_active_pack_id": current_pack_id,
        "active_task_count": len(active_tasks),
        "active_pack_count": len(active_packs),
        "duplicate_active_alias_count": len(duplicates),
        "current_broken_link_count": len(broken),
        "current_active_task_indexed": task_indexed,
        "current_active_pack_indexed": pack_indexed,
        "current_projection_status": "evaluated" if evaluated else "not_evaluated",
        "projection_completeness": "complete" if complete else "incomplete",
    }


def validate_migration(root: Path, receipt_path: Path, flags: argparse.Namespace | None = None) -> dict[str, Any]:
    root = root.resolve()
    receipt_path = receipt_path.resolve(strict=True)
    payload = _index_path(root).read_bytes()
    anchors = _find_anchor_lines(payload)
    if not anchors:
        raise MigrationError("No committed sealed migration is present")
    receipt_sha = _sha_file(receipt_path)
    matching = [
        anchor for anchor in anchors
        if anchor[2].get("fields", {}).get("receipt_sha256") == receipt_sha
    ]
    if not matching:
        raise MigrationError("Requested receipt is not anchored")
    graph_errors: list[str] = []
    loaded_graph: tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]] | None = None
    for anchor in reversed(matching):
        try:
            loaded_graph = _validate_receipt_graph(root, payload, *anchor)
            break
        except (KeyError, TypeError, MigrationError) as exc:
            graph_errors.append(str(exc))
    if loaded_graph is None:
        raise MigrationError("Requested receipt graph is invalid: " + "; ".join(graph_errors[:3]))
    events, _results, receipt = loaded_graph
    boundary = _migration_boundary_projection(root, receipt)
    state = _merge_state(events)
    current = _current_projection(state)
    appendable = False
    if current["current_active_task_id"] is not None:
        append_probe = _versioned({
            "event": "link", "id": current["current_active_task_id"],
            "updated_at": receipt["transaction_committed_at"], "links": [],
        })
        validate_current_suffix_event(append_probe, set(state))
        appendable = True
    prefix_preserved = (
        _safe_ref(root, receipt["source_prefix_ref"]).read_bytes()
        == payload[:receipt["source_prefix_byte_length"]]
    )
    checks = {
        "strict_reader_status": "pass",
        "append_simulation_status": "pass" if appendable else "fail",
        **current,
        **boundary,
        "prefix_preserved": prefix_preserved,
    }
    if flags is not None:
        requirements = {
            "require_current_projection_evaluated": checks["current_projection_status"] == "evaluated",
            "require_single_active_task": checks["active_task_count"] == 1,
            "require_single_active_pack": checks["active_pack_count"] == 1,
            "require_appendable": checks["append_simulation_status"] == "pass",
        }
        failed = [name for name, passed in requirements.items() if getattr(flags, name, False) and not passed]
        if failed:
            raise MigrationError("Migration validation requirement failed: " + ", ".join(failed))
    if (
        checks["projection_completeness"] != "complete"
        or checks["append_simulation_status"] != "pass"
        or not checks["prefix_preserved"]
    ):
        raise MigrationError("Committed migration projection or prefix integrity is incomplete")
    return {"valid": True, "receipt": receipt, **checks}


def _write_plan(path: Path, plan: dict[str, Any], root: Path) -> None:
    resolved = path.resolve()
    task_root = (root.resolve() / ".task").resolve()
    try:
        resolved.relative_to(task_root)
    except ValueError:
        pass
    else:
        raise MigrationError("Plan output must remain outside canonical .task state until apply")
    _atomic_write(resolved, _canonical_bytes(plan))


def _cmd_inspect(args: argparse.Namespace) -> None:
    print(json.dumps(inspect_store(Path(args.root)), ensure_ascii=False, indent=2, sort_keys=True))


def _cmd_plan(args: argparse.Namespace) -> None:
    root = Path(args.root).resolve()
    plan = build_plan(
        root, args.expected_index_sha256, args.current_task_id, args.current_task_path,
        args.current_task_sha256, args.current_pack_id, args.current_pack_path,
        args.current_pack_sha256, Path(args.mapping_manifest),
    )
    _write_plan(Path(args.output_plan), plan, root)
    print(json.dumps({
        "planned": True, "mutation_performed_on_canonical_index": False,
        "plan": str(Path(args.output_plan).resolve()),
        "plan_sha256": _sha_file(Path(args.output_plan).resolve()),
        "migration_id": plan["migration_id"],
        "classification_counts": plan["classification_counts"],
        "unclassified_count": plan["unclassified_count"],
        "projection": plan["projection"],
        "expected_after_index_sha256": plan["expected_after_index_sha256"],
    }, ensure_ascii=False, indent=2, sort_keys=True))


def _cmd_apply(args: argparse.Namespace) -> None:
    result = apply_plan(
        Path(args.root), Path(args.plan), args.expected_plan_sha256,
        args.expected_index_sha256, dry_run=args.dry_run,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


def _cmd_validate(args: argparse.Namespace) -> None:
    result = validate_migration(Path(args.root), Path(args.receipt), args)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


def _cmd_recover(args: argparse.Namespace) -> None:
    result = recover_transaction(Path(args.root), args.transaction_id)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inspect, plan, apply, validate, and recover sealed task-state legacy migrations."
    )
    parser.add_argument("--root", default=".", help="Workspace root.")
    commands = parser.add_subparsers(dest="command", required=True)
    inspect_parser = commands.add_parser("inspect", help="Read-only exact token and row inventory.")
    inspect_parser.set_defaults(func=_cmd_inspect)

    migrate = commands.add_parser("migrate", help="Manage a sealed legacy-prefix migration.")
    migrate_commands = migrate.add_subparsers(dest="migrate_command", required=True)
    plan_parser = migrate_commands.add_parser("plan", help="Create a deterministic zero-canonical-mutation plan.")
    plan_parser.add_argument("--expected-index-sha256", required=True)
    plan_parser.add_argument("--current-task-id", required=True)
    plan_parser.add_argument("--current-task-path", required=True)
    plan_parser.add_argument("--current-task-sha256", required=True)
    plan_parser.add_argument("--current-pack-id", required=True)
    plan_parser.add_argument("--current-pack-path", required=True)
    plan_parser.add_argument("--current-pack-sha256", required=True)
    plan_parser.add_argument("--mapping-manifest", required=True)
    plan_parser.add_argument("--output-plan", required=True)
    plan_parser.set_defaults(func=_cmd_plan)

    apply_parser = migrate_commands.add_parser("apply", help="Apply one expected-hash-bound locked transaction.")
    apply_parser.add_argument("--plan", required=True)
    apply_parser.add_argument("--expected-plan-sha256", required=True)
    apply_parser.add_argument("--expected-index-sha256", required=True)
    apply_parser.add_argument("--dry-run", action="store_true")
    apply_parser.set_defaults(func=_cmd_apply)

    validate_parser = migrate_commands.add_parser("validate", help="Validate receipt, seal, prefix, projection, and appendability.")
    validate_parser.add_argument("--receipt", required=True)
    validate_parser.add_argument("--require-current-projection-evaluated", action="store_true")
    validate_parser.add_argument("--require-single-active-task", action="store_true")
    validate_parser.add_argument("--require-single-active-pack", action="store_true")
    validate_parser.add_argument("--require-appendable", action="store_true")
    validate_parser.set_defaults(func=_cmd_validate)

    recover_parser = migrate_commands.add_parser("recover", help="Recover or forward-complete one journaled transaction.")
    recover_parser.add_argument("--transaction-id", required=True)
    recover_parser.set_defaults(func=_cmd_recover)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        args.func(args)
    except (MigrationError, OSError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, sort_keys=True), file=os.sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
