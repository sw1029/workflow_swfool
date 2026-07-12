#!/usr/bin/env python3
"""Plan and publish a sealed, content-preserving ``.agent_log`` migration.

The migration never rewrites Markdown bodies.  It replaces a legacy canonical
index only after publishing a byte-identical source snapshot and hash-bound
sidecars.  The resulting index is a strict current-format prefix that may be
extended by the standard writer.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
import time
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from agent_log_integrity import (  # noqa: E402
    AgentLogIntegrityError,
    LOG_FORMAT_VERSION,
    LOG_SCHEMA_VERSION,
    LOG_STATUSES,
    content_id_for,
    expected_record_id,
    inspect_agent_log_store,
    safe_log_file,
    sha256_bytes,
    sha256_file,
    validate_store_for_append,
    workspace_root,
)
from write_agent_log import log_lock  # noqa: E402


TOOL_VERSION = "1.0.0"
PLAN_SCHEMA_VERSION = 1
STATUS_MAP_SCHEMA_VERSION = 1
MANIFEST_SCHEMA_VERSION = 1
RECEIPT_SCHEMA_VERSION = 1
MARKER_SCHEMA_VERSION = 1
JOURNAL_SCHEMA_VERSION = 1
MISSING_STATUS_KEY = "__MISSING_STATUS__"
MIGRATION_KIND = "agent_log_legacy_migration"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class MigrationError(ValueError):
    """Raised when a migration cannot proceed without weakening evidence."""


def _canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def _sha256_path(path: Path) -> str:
    return sha256_file(path)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _strict_fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    descriptor = os.open(path, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _strict_atomic_replace(path: Path, payload: bytes, mode: int = 0o600) -> None:
    if path.exists() or path.is_symlink():
        target_mode = path.lstat().st_mode
        if stat.S_ISLNK(target_mode) or not stat.S_ISREG(target_mode):
            raise MigrationError(f"migration target is not a regular file: {path}")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    descriptor_open = True
    try:
        os.fchmod(descriptor, mode)
        with os.fdopen(descriptor, "wb") as handle:
            descriptor_open = False
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        _strict_fsync_directory(path.parent)
    except BaseException:
        if descriptor_open:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)
        raise


def _strict_publish_new(path: Path, payload: bytes, mode: int = 0o600) -> None:
    if path.exists() or path.is_symlink():
        raise MigrationError(f"migration artifact already exists: {path}")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    descriptor_open = True
    try:
        os.fchmod(descriptor, mode)
        with os.fdopen(descriptor, "wb") as handle:
            descriptor_open = False
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, path)
        temporary.unlink()
        _strict_fsync_directory(path.parent)
    except BaseException:
        if descriptor_open:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)
        raise


def _root_identity(root: Path) -> dict[str, Any]:
    resolved = workspace_root(root)
    metadata = resolved.stat()
    basis = {
        "resolved_path": str(resolved),
        "device": metadata.st_dev,
        "inode": metadata.st_ino,
    }
    return {**basis, "sha256": sha256_bytes(_canonical_json_bytes(basis))}


def _relative_or_absolute(root: Path, path: Path) -> str:
    resolved = path.expanduser().absolute().resolve(strict=False)
    try:
        return resolved.relative_to(root).as_posix()
    except ValueError:
        return str(resolved)


def _resolve_ref(root: Path, value: Any) -> Path:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise MigrationError("migration reference must be a non-empty path")
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        candidate = root / candidate
    lexical = candidate.absolute()
    if lexical.is_symlink():
        raise MigrationError(f"migration reference must not be a symlink: {value}")
    try:
        resolved = lexical.resolve(strict=True)
    except OSError as exc:
        raise MigrationError(f"migration reference is unavailable: {value}: {exc}") from exc
    if not stat.S_ISREG(resolved.lstat().st_mode):
        raise MigrationError(f"migration reference is not a regular file: {value}")
    return resolved


def _safe_migration_path(root: Path, value: Any, *, must_exist: bool = True) -> Path:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise MigrationError("migration sidecar path must be a non-empty string")
    relative = Path(value)
    if (
        relative.is_absolute()
        or value != relative.as_posix()
        or any(part in {"", ".", ".."} for part in relative.parts)
        or len(relative.parts) < 3
        or relative.parts[:2] != (".agent_log", "migrations")
    ):
        raise MigrationError(f"unsafe migration sidecar path: {value!r}")
    current = root
    for part in relative.parts:
        current /= part
        if current.exists() or current.is_symlink():
            mode = current.lstat().st_mode
            if stat.S_ISLNK(mode):
                raise MigrationError(f"migration sidecar path contains a symlink: {value}")
        elif must_exist:
            raise MigrationError(f"migration sidecar is missing: {value}")
    candidate = root / relative
    if must_exist and not stat.S_ISREG(candidate.lstat().st_mode):
        raise MigrationError(f"migration sidecar is not a regular file: {value}")
    try:
        candidate.resolve(strict=must_exist).relative_to(root)
    except (OSError, ValueError) as exc:
        raise MigrationError(f"migration sidecar escapes the workspace: {value}") from exc
    return candidate


def _index_path(root: Path) -> Path:
    return root / ".agent_log" / "index.jsonl"


def _read_index(root: Path) -> bytes:
    path = _index_path(root)
    if path.is_symlink():
        raise MigrationError(".agent_log/index.jsonl must not be a symlink")
    if not path.exists():
        return b""
    if not stat.S_ISREG(path.lstat().st_mode):
        raise MigrationError(".agent_log/index.jsonl must be a regular file")
    return path.read_bytes()


def _split_source_rows(payload: bytes) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    byte_offset = 0
    for physical_line, raw_line in enumerate(payload.splitlines(keepends=True), start=1):
        start = byte_offset
        byte_offset += len(raw_line)
        content = raw_line.rstrip(b"\r\n")
        if not content.strip():
            continue
        row: dict[str, Any] = {
            "source_line": physical_line,
            "source_byte_start": start,
            "source_byte_end": byte_offset,
            "source_row_sha256": sha256_bytes(raw_line),
            "raw": raw_line,
            "parsed": None,
            "parse_error": None,
        }
        try:
            decoded = content.decode("utf-8")
            parsed = json.loads(decoded)
            if not isinstance(parsed, dict):
                raise ValueError("expected a JSON object")
            row["parsed"] = parsed
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            row["parse_error"] = str(exc)
        rows.append(row)
    if byte_offset < len(payload):
        # ``splitlines(keepends=True)`` normally consumes all bytes, including a
        # final unterminated line.  Keep this fail-close assertion explicit.
        raise MigrationError("source index byte accounting is incomplete")
    return rows


def _walk_markdown(root: Path) -> list[dict[str, Any]]:
    log_root = root / ".agent_log"
    if not log_root.exists():
        return []
    if log_root.is_symlink() or not log_root.is_dir():
        raise MigrationError(".agent_log must be a regular non-symlink directory")
    entries: list[dict[str, Any]] = []
    pending = [log_root]
    while pending:
        directory = pending.pop()
        with os.scandir(directory) as iterator:
            for item in iterator:
                path = Path(item.path)
                if item.is_symlink():
                    raise MigrationError(f"agent-log inventory contains a symlink: {path}")
                if item.is_dir(follow_symlinks=False):
                    pending.append(path)
                    continue
                if not item.is_file(follow_symlinks=False):
                    raise MigrationError(f"agent-log inventory contains a non-regular entry: {path}")
                if path.suffix.lower() != ".md":
                    continue
                relative = path.relative_to(root).as_posix()
                safe_log_file(root, relative, must_exist=True)
                entries.append(
                    {
                        "path": relative,
                        "body_sha256": _sha256_path(path),
                        "size": path.stat().st_size,
                    }
                )
    return sorted(entries, key=lambda item: item["path"])


def _inventory_document(root: Path, index_payload: bytes) -> dict[str, Any]:
    rows = _split_source_rows(index_payload)
    markdown = _walk_markdown(root)
    basis = {
        "index_sha256": sha256_bytes(index_payload),
        "index_size": len(index_payload),
        "source_row_count": len(rows),
        "markdown": markdown,
    }
    return {**basis, "inventory_sha256": sha256_bytes(_canonical_json_bytes(basis))}


def inspect_store(root_raw: str | Path) -> dict[str, Any]:
    root = workspace_root(root_raw)
    payload = _read_index(root)
    rows = _split_source_rows(payload)
    inventory = _inventory_document(root, payload)
    status_counts: Counter[str] = Counter()
    path_count = 0
    malformed = 0
    for row in rows:
        parsed = row["parsed"]
        if parsed is None:
            malformed += 1
            continue
        if "status" not in parsed or parsed.get("status") is None:
            status_counts[MISSING_STATUS_KEY] += 1
        elif isinstance(parsed.get("status"), str):
            status_counts[str(parsed["status"])] += 1
        else:
            status_counts[f"__NON_STRING__:{type(parsed.get('status')).__name__}"] += 1
        if isinstance(parsed.get("path"), str) and parsed["path"]:
            path_count += 1
    unique_paths = {
        row["parsed"].get("path")
        for row in rows
        if isinstance(row.get("parsed"), dict)
        and isinstance(row["parsed"].get("path"), str)
        and row["parsed"]["path"]
    }
    markdown_paths = {item["path"] for item in inventory["markdown"]}
    return {
        "schema_version": PLAN_SCHEMA_VERSION,
        "tool_version": TOOL_VERSION,
        "root_identity": _root_identity(root),
        "source_index": {
            "path": ".agent_log/index.jsonl",
            "sha256": inventory["index_sha256"],
            "size": inventory["index_size"],
            "raw_row_count": inventory["source_row_count"],
            "malformed_row_count": malformed,
        },
        "source_inventory_sha256": inventory["inventory_sha256"],
        "markdown_count": len(inventory["markdown"]),
        "path_bearing_row_count": path_count,
        "unique_indexed_path_count": len(unique_paths),
        "orphan_markdown_count": len(markdown_paths - unique_paths),
        "status_counts": dict(sorted(status_counts.items())),
        "status_map_missing_key": MISSING_STATUS_KEY,
    }


def _load_status_map(path: Path) -> tuple[dict[str | None, dict[str, Any]], dict[str, Any], bytes]:
    payload = path.read_bytes()
    try:
        document = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MigrationError(f"status map is not valid UTF-8 JSON: {exc}") from exc
    if not isinstance(document, dict) or document.get("schema_version") != STATUS_MAP_SCHEMA_VERSION:
        raise MigrationError(f"status map schema_version must be {STATUS_MAP_SCHEMA_VERSION}")
    if not isinstance(document.get("mapping_policy_id"), str) or not document["mapping_policy_id"]:
        raise MigrationError("status map requires mapping_policy_id")
    if not isinstance(document.get("version"), (str, int)) or isinstance(document.get("version"), bool):
        raise MigrationError("status map requires a scalar version")
    entries = document.get("entries")
    if not isinstance(entries, list):
        raise MigrationError("status map entries must be a list")
    mappings: dict[str | None, dict[str, Any]] = {}
    for position, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict):
            raise MigrationError(f"status map entry {position} must be an object")
        original = entry.get("original_status")
        if original is not None and (not isinstance(original, str) or not original):
            raise MigrationError(f"status map entry {position} original_status must be string or null")
        if original in mappings:
            raise MigrationError(f"status map contains duplicate exact status: {original!r}")
        normalized = entry.get("normalized_status")
        if normalized not in LOG_STATUSES:
            raise MigrationError(f"status map entry {position} has unsupported normalized_status")
        reason = entry.get("reason")
        if not isinstance(reason, str) or not reason:
            raise MigrationError(f"status map entry {position} requires a reason")
        if normalized == "completed" and original != "completed":
            raise MigrationError("migration status maps may not create a new completed claim")
        if original is None and normalized != "informational":
            raise MigrationError("missing status may only map to informational")
        evidence = entry.get("status_evidence")
        if original is None and evidence != "not_evaluated":
            raise MigrationError("missing status mapping requires status_evidence=not_evaluated")
        mappings[original] = {
            "normalized_status": normalized,
            "reason": reason,
            "status_evidence": evidence,
        }
    return mappings, document, payload


def _body_metadata(path: Path) -> dict[str, str]:
    # Metadata is used only for duplicate resolution.  Neither the body nor
    # extracted free-form sections are persisted in plans or manifests.
    metadata: dict[str, str] = {}
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line_no, line in enumerate(handle, start=1):
                stripped = line.rstrip("\r\n")
                if line_no == 1 and stripped.startswith("# "):
                    metadata["title"] = stripped[2:].strip()
                bullet = re.match(
                    r"^-\s*(log[ _-]?id|timestamp|updated_at|status)\s*:\s*(.*?)\s*$",
                    stripped,
                    flags=re.IGNORECASE,
                )
                if bullet:
                    raw_key = bullet.group(1).lower().replace("-", "_").replace(" ", "_")
                    key = "log_id" if raw_key in {"logid", "log_id"} else raw_key
                    metadata[key] = bullet.group(2).strip().strip("`").strip()
                if line_no >= 80:
                    break
    except UnicodeDecodeError:
        # The body hash remains valid evidence; incomplete structure simply
        # means duplicate selection has fewer corroborating fields.
        return {}
    return metadata


def _body_text_for_matching(path: Path) -> str:
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return ""
    return re.sub(r"\s+", " ", text.replace("`", "").lower()).strip()


def _status_mapping(
    parsed: dict[str, Any], mappings: dict[str | None, dict[str, Any]]
) -> tuple[str | None, str | None, str | None, str | None]:
    if "status" not in parsed or parsed.get("status") is None:
        original: str | None = None
    elif not isinstance(parsed.get("status"), str) or not parsed["status"]:
        return None, None, None, "status is not a non-empty string or null"
    else:
        original = parsed["status"]
    mapping = mappings.get(original)
    if mapping is None:
        return original, None, None, f"exact status is not mapped: {original!r}"
    return original, mapping["normalized_status"], mapping["reason"], None


def _safe_source_path(root: Path, value: Any) -> tuple[Path | None, str | None]:
    if value is None:
        return None, None
    if not isinstance(value, str) or not value:
        return None, "source path is not a non-empty string"
    try:
        return safe_log_file(root, value, must_exist=True), None
    except AgentLogIntegrityError as exc:
        return None, str(exc)


def _candidate_score(
    parsed: dict[str, Any],
    body_sha: str,
    metadata: dict[str, str],
    body_text: str = "",
) -> tuple[int, ...] | None:
    declared_sha = parsed.get("body_sha256")
    if declared_sha is not None:
        if not isinstance(declared_sha, str) or declared_sha != body_sha:
            return None
        total = 20
    else:
        total = 0
    matched = 0
    mismatched = 0
    for key, weight in (("log_id", 8), ("status", 6), ("timestamp", 3), ("title", 1)):
        row_value = parsed.get(key)
        body_value = metadata.get(key)
        alternate = metadata.get("updated_at") if key == "timestamp" else None
        if row_value is None or (body_value is None and alternate is None):
            continue
        if isinstance(row_value, str) and row_value in {body_value, alternate}:
            total += weight
            matched += 1
        else:
            total -= weight
            mismatched += 1
    content_hits = 0
    content_score = 0
    normalized_values: list[str] = []
    if body_text:
        scalar_fields = ("task_intent", "work_performed", "result", "shortcomings", "title")
        list_fields = ("commands", "agent_notes", "follow_ups", "tags")
        values: list[str] = []
        for field in scalar_fields:
            value = parsed.get(field)
            if isinstance(value, str):
                values.append(value)
        for field in list_fields:
            value = parsed.get(field)
            if isinstance(value, list):
                values.extend(item for item in value if isinstance(item, str))
        for value in values:
            normalized = re.sub(r"\s+", " ", value.replace("`", "").lower()).strip()
            normalized_values.append(normalized)
            if len(normalized) >= 12 and normalized in body_text:
                content_hits += 1
                content_score += 2 + min(len(normalized), 240) // 80
    total += content_score
    body_tokens = Counter(re.findall(r"[a-z0-9_./-]{4,}", body_text))
    candidate_tokens = Counter(
        token
        for value in normalized_values
        for token in re.findall(r"[a-z0-9_./-]{4,}", value)
    )
    token_overlap = sum(
        min(count, body_tokens.get(token, 0)) for token, count in candidate_tokens.items()
    )
    token_total = sum(candidate_tokens.values())
    token_precision = (token_overlap * 1000 // token_total) if token_total else 0
    return total, content_hits, token_overlap, token_precision, matched, -mismatched


def _is_current_record_valid(parsed: dict[str, Any], body_sha: str) -> bool:
    if (
        parsed.get("format_version") != LOG_FORMAT_VERSION
        or parsed.get("schema_version") != LOG_SCHEMA_VERSION
        or parsed.get("content_id_scheme") is not None
    ):
        return False
    if parsed.get("body_sha256") != body_sha:
        return False
    if parsed.get("content_id") != content_id_for(body_sha):
        return False
    return parsed.get("record_id") == expected_record_id(parsed)


def _canonical_record(
    *,
    root: Path,
    migration_id: str,
    source: dict[str, Any] | None,
    path: str,
    body_sha: str,
    normalized_status: str,
    mapping_reason: str,
    original_status: str | None,
    orphan: bool,
) -> dict[str, Any]:
    parsed = source["parsed"] if source is not None else None
    if isinstance(parsed, dict) and _is_current_record_valid(parsed, body_sha):
        if parsed.get("status") != normalized_status:
            raise MigrationError("a current integrity-bound record may not be status-rewritten")
        return parsed
    body_path = safe_log_file(root, path, must_exist=True)
    metadata = _body_metadata(body_path)
    source_line = source["source_line"] if source is not None else None
    source_sha = source["source_row_sha256"] if source is not None else None
    log_id_value = parsed.get("log_id") if isinstance(parsed, dict) else None
    if not isinstance(log_id_value, str) or not log_id_value:
        log_id_value = metadata.get("log_id")
    if not isinstance(log_id_value, str) or not log_id_value:
        log_id_value = "log-legacy-" + sha256_bytes((path + "\0" + body_sha).encode("utf-8"))[:32]
    timestamp = parsed.get("timestamp") if isinstance(parsed, dict) else None
    if not isinstance(timestamp, str) or not timestamp:
        timestamp = metadata.get("timestamp") or "1970-01-01T00:00:00Z"
    title = parsed.get("title") if isinstance(parsed, dict) else None
    if not isinstance(title, str) or not title:
        title = metadata.get("title") or Path(path).stem
    record: dict[str, Any] = {
        "format_version": LOG_FORMAT_VERSION,
        "schema_version": LOG_SCHEMA_VERSION,
        "log_id": log_id_value,
        "body_sha256": body_sha,
        "content_id": content_id_for(body_sha),
        "timestamp": timestamp,
        "status": normalized_status,
        "title": title,
        "path": path,
        "migration_id": migration_id,
        "legacy_import": True,
        "structured_fields_status": "not_evaluated" if orphan else "source_index_limited",
        "original_status": original_status,
        "status_mapping_reason": mapping_reason,
        "status_evidence": "not_evaluated" if original_status is None else "legacy_source_only",
        "source_line": source_line,
        "source_row_sha256": source_sha,
        "historical_claims_upgraded": False,
    }
    record["record_id"] = expected_record_id(record)
    return record


def _build_plan(root: Path, status_map_path: Path) -> tuple[dict[str, Any], bytes]:
    source_payload = _read_index(root)
    inventory = _inventory_document(root, source_payload)
    source_rows = _split_source_rows(source_payload)
    mappings, status_document, status_payload = _load_status_map(status_map_path)
    migration_basis = {
        "tool_version": TOOL_VERSION,
        "root_identity": _root_identity(root)["sha256"],
        "source_index_sha256": inventory["index_sha256"],
        "source_inventory_sha256": inventory["inventory_sha256"],
        "status_map_sha256": sha256_bytes(status_payload),
    }
    migration_id = "agent-log-migration-" + sha256_bytes(_canonical_json_bytes(migration_basis))[:24]
    markdown_by_path = {item["path"]: item for item in inventory["markdown"]}
    row_plans: dict[int, dict[str, Any]] = {}
    grouped: dict[str, list[dict[str, Any]]] = {}

    def base_row(row: dict[str, Any]) -> dict[str, Any]:
        parsed = row.get("parsed")
        original = parsed.get("status") if isinstance(parsed, dict) and isinstance(parsed.get("status"), str) else None
        source_path = parsed.get("path") if isinstance(parsed, dict) and isinstance(parsed.get("path"), str) else None
        source_body_sha = parsed.get("body_sha256") if isinstance(parsed, dict) and isinstance(parsed.get("body_sha256"), str) else None
        return {
            "source_line": row["source_line"],
            "source_row_sha256": row["source_row_sha256"],
            "original_status": original,
            "source_path": source_path,
            "source_body_sha256": source_body_sha,
            "classification": "unresolved",
            "normalized_status": None,
            "status_mapping_reason": None,
            "canonical_target_path": None,
            "canonical_target_source_line": None,
            "disposition": "block",
            "unresolved_reason": None,
        }

    for row in source_rows:
        entry = base_row(row)
        row_plans[row["source_line"]] = entry
        parsed = row.get("parsed")
        if not isinstance(parsed, dict):
            entry["unresolved_reason"] = f"malformed_json:{row.get('parse_error') or 'unknown'}"
            continue
        original, normalized, mapping_reason, status_error = _status_mapping(parsed, mappings)
        entry["original_status"] = original
        entry["normalized_status"] = normalized
        entry["status_mapping_reason"] = mapping_reason
        if status_error:
            entry["unresolved_reason"] = status_error
            continue
        if parsed.get("path") is None:
            entry.update(
                {
                    "classification": "foreign_event",
                    "canonical_target_path": None,
                    "canonical_target_source_line": None,
                    "disposition": "quarantine_foreign_event",
                    "unresolved_reason": None,
                }
            )
            continue
        if not isinstance(parsed.get("path"), str) or not parsed["path"]:
            entry["unresolved_reason"] = "source path is not a non-empty string or null"
            continue
        body_path, path_error = _safe_source_path(root, parsed["path"])
        if path_error or body_path is None:
            entry["unresolved_reason"] = path_error or "source body is unavailable"
            continue
        entry["source_path"] = parsed["path"]
        versions: list[tuple[str, Any, int]] = [
            ("format_version", parsed.get("format_version", 1), LOG_FORMAT_VERSION),
            ("schema_version", parsed.get("schema_version", 1), LOG_SCHEMA_VERSION),
        ]
        version_error = next(
            (
                f"invalid or future {field}: {value!r}"
                for field, value, current in versions
                if isinstance(value, bool)
                or not isinstance(value, int)
                or value < 1
                or value > current
            ),
            None,
        )
        if version_error:
            entry["unresolved_reason"] = version_error
            continue
        format_version = parsed.get("format_version", 1)
        schema_version = parsed.get("schema_version", 1)
        integrity_bound = (
            format_version >= LOG_FORMAT_VERSION
            or schema_version >= LOG_SCHEMA_VERSION
        )
        if integrity_bound:
            actual_body_sha = sha256_file(body_path)
            if not _is_current_record_valid(parsed, actual_body_sha):
                entry["unresolved_reason"] = (
                    "current integrity-bound record is invalid or tampered"
                )
                continue
            if normalized != parsed.get("status"):
                entry["unresolved_reason"] = (
                    "current integrity-bound status mapping is not identity-preserving"
                )
                continue
        grouped.setdefault(parsed["path"], []).append(row)

    canonical_sources: list[dict[str, Any]] = []
    for path, candidates in sorted(grouped.items()):
        inventory_entry = markdown_by_path.get(path)
        if inventory_entry is None:
            for candidate in candidates:
                row_plans[candidate["source_line"]]["unresolved_reason"] = "indexed Markdown is absent from inventory"
            continue
        body_sha = inventory_entry["body_sha256"]
        if len(candidates) > 1 and any(
            candidate["parsed"].get("format_version") == LOG_FORMAT_VERSION
            or candidate["parsed"].get("schema_version") == LOG_SCHEMA_VERSION
            for candidate in candidates
        ):
            for candidate in candidates:
                row_plans[candidate["source_line"]]["unresolved_reason"] = (
                    "duplicate current integrity-bound path requires separate governed resolution"
                )
            continue
        metadata = _body_metadata(root / path)
        body_text = _body_text_for_matching(root / path)
        scored: list[tuple[tuple[int, ...], dict[str, Any]]] = []
        for candidate in candidates:
            score = _candidate_score(candidate["parsed"], body_sha, metadata, body_text)
            if score is not None:
                scored.append((score, candidate))
        if not scored:
            for candidate in candidates:
                row_plans[candidate["source_line"]]["unresolved_reason"] = "declared body integrity does not match Markdown"
            continue
        best_score = max(score for score, _ in scored)
        winners = [candidate for score, candidate in scored if score == best_score]
        score_by_line = {
            candidate["source_line"]: list(score) for score, candidate in scored
        }
        if len(winners) > 1:
            winner_hashes = {candidate["source_row_sha256"] for candidate in winners}
            if len(winner_hashes) != 1:
                for candidate in candidates:
                    unresolved = row_plans[candidate["source_line"]]
                    unresolved["unresolved_reason"] = "duplicate path has a metadata tie or conflict"
                    unresolved["duplicate_candidate_score"] = score_by_line.get(
                        candidate["source_line"]
                    )
                    unresolved["duplicate_selection_basis"] = (
                        "body_sha_log_metadata_content_token_score_v1"
                    )
                continue
            winners.sort(key=lambda candidate: candidate["source_line"])
        canonical = winners[0]
        canonical_entry = row_plans[canonical["source_line"]]
        canonical_entry.update(
            {
                "classification": "canonical_log",
                "canonical_target_path": path,
                "canonical_target_source_line": canonical["source_line"],
                "disposition": "bind_existing_body",
                "unresolved_reason": None,
                "duplicate_candidate_count": len(candidates),
                "duplicate_candidate_score": score_by_line.get(
                    canonical["source_line"]
                ),
                "duplicate_selection_basis": (
                    "exact_row_bytes_equivalent"
                    if len(winners) > 1
                    else "body_sha_log_metadata_content_token_score_v1"
                ),
            }
        )
        canonical_sources.append(canonical)
        for candidate in candidates:
            if candidate is canonical:
                continue
            alias = row_plans[candidate["source_line"]]
            if alias.get("unresolved_reason") and candidate not in winners:
                # A body-hash-mismatched alias remains evidence but is not safe
                # to treat as a harmless duplicate.
                continue
            alias.update(
                {
                    "classification": "duplicate_alias",
                    "canonical_target_path": path,
                    "canonical_target_source_line": canonical["source_line"],
                    "disposition": "retain_as_alias_evidence",
                    "unresolved_reason": None,
                    "duplicate_candidate_count": len(candidates),
                    "duplicate_candidate_score": score_by_line.get(
                        candidate["source_line"]
                    ),
                    "duplicate_selection_basis": canonical_entry[
                        "duplicate_selection_basis"
                    ],
                }
            )

    # The current contract binds one content_id to one body hash and rejects
    # duplicate content IDs.  Byte-identical bodies at distinct paths therefore
    # cannot both become canonical rows.  Preserve one deterministic canonical
    # body and seal the other path/row pairs as non-consumable alias evidence.
    canonical_by_body: dict[str, list[dict[str, Any]]] = {}
    for source in canonical_sources:
        path = row_plans[source["source_line"]]["source_path"]
        assert isinstance(path, str)
        canonical_by_body.setdefault(markdown_by_path[path]["body_sha256"], []).append(source)
    body_alias_paths: set[str] = set()
    retained_sources: list[dict[str, Any]] = []
    for body_sha, candidates in sorted(canonical_by_body.items()):
        if len(candidates) == 1:
            retained_sources.append(candidates[0])
            continue
        if any(
            candidate["parsed"].get("format_version") == LOG_FORMAT_VERSION
            or candidate["parsed"].get("schema_version") == LOG_SCHEMA_VERSION
            for candidate in candidates
        ):
            for candidate in candidates:
                entry = row_plans[candidate["source_line"]]
                entry.update(
                    {
                        "classification": "unresolved",
                        "disposition": "block",
                        "unresolved_reason": (
                            "duplicate current integrity-bound content_id requires separate governed resolution"
                        ),
                    }
                )
            retained_sources.extend(candidates)
            continue
        ranked: list[tuple[tuple[int, ...], str, str, dict[str, Any]]] = []
        for candidate in candidates:
            entry = row_plans[candidate["source_line"]]
            path = entry["source_path"]
            assert isinstance(path, str)
            score = _candidate_score(
                candidate["parsed"],
                body_sha,
                _body_metadata(root / path),
                _body_text_for_matching(root / path),
            )
            ranked.append((score or tuple(), path, candidate["source_row_sha256"], candidate))
        ranked.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)
        canonical = ranked[0][3]
        canonical_entry = row_plans[canonical["source_line"]]
        canonical_path = canonical_entry["source_path"]
        canonical_entry["body_alias_selection_basis"] = (
            "body_sha_log_metadata_content_token_score_then_path_hash_v1"
        )
        canonical_entry["body_alias_candidate_count"] = len(candidates)
        retained_sources.append(canonical)
        for alias_score, alias_path, _, alias in ranked[1:]:
            alias_entry = row_plans[alias["source_line"]]
            alias_entry.update(
                {
                    "classification": "duplicate_alias",
                    "canonical_target_path": canonical_path,
                    "canonical_target_source_line": canonical["source_line"],
                    "disposition": "retain_as_alias_evidence",
                    "unresolved_reason": None,
                    "alias_reason": "byte_identical_body_different_path",
                    "body_alias_candidate_score": list(alias_score),
                    "body_alias_selection_basis": canonical_entry[
                        "body_alias_selection_basis"
                    ],
                }
            )
            body_alias_paths.add(alias_path)
    canonical_sources = retained_sources

    referenced_paths = set(grouped)
    orphan_entries: list[dict[str, Any]] = []
    for inventory_entry in inventory["markdown"]:
        if inventory_entry["path"] in referenced_paths:
            continue
        orphan_entries.append(
            {
                "path": inventory_entry["path"],
                "body_sha256": inventory_entry["body_sha256"],
                "size": inventory_entry["size"],
                "disposition": "bind_as_legacy_import",
                "structured_fields_status": "not_evaluated",
            }
        )

    canonical_body_targets: dict[str, str] = {}
    for source in canonical_sources:
        path = row_plans[source["source_line"]]["source_path"]
        assert isinstance(path, str)
        canonical_body_targets[markdown_by_path[path]["body_sha256"]] = path
    for orphan in sorted(orphan_entries, key=lambda item: item["path"]):
        target = canonical_body_targets.get(orphan["body_sha256"])
        if target is not None:
            orphan["disposition"] = "quarantine_nonlog_body"
            orphan["canonical_target_path"] = target
            orphan["alias_reason"] = "byte_identical_body_different_path"
            body_alias_paths.add(orphan["path"])
            continue
        canonical_body_targets[orphan["body_sha256"]] = orphan["path"]

    canonical_paths = {
        row_plans[source["source_line"]]["source_path"] for source in canonical_sources
    }
    orphan_paths = {
        entry["path"]
        for entry in orphan_entries
        if entry["disposition"] == "bind_as_legacy_import"
    }
    body_resolutions: list[dict[str, Any]] = []
    for entry in inventory["markdown"]:
        path = entry["path"]
        if path in canonical_paths:
            disposition = "bind_existing_body"
        elif path in orphan_paths:
            disposition = "bind_as_legacy_import"
        elif path in body_alias_paths:
            disposition = (
                "quarantine_nonlog_body"
                if any(
                    item["path"] == path
                    and item["disposition"] == "quarantine_nonlog_body"
                    for item in orphan_entries
                )
                else "retain_as_alias_evidence"
            )
        else:
            disposition = "block"
        body_resolutions.append(
            {
                "path": path,
                "body_sha256": entry["body_sha256"],
                "size": entry["size"],
                "disposition": disposition,
            }
        )

    rows = [row_plans[row["source_line"]] for row in source_rows]
    unresolved_count = sum(1 for row in rows if row["classification"] == "unresolved")
    counts = Counter(row["classification"] for row in rows)
    counts["orphan_markdown"] = len(orphan_entries)
    counts["legacy_import_markdown"] = sum(
        1 for entry in orphan_entries if entry["disposition"] == "bind_as_legacy_import"
    )
    counts["body_alias_markdown"] = len(body_alias_paths)
    records: list[dict[str, Any]] = []
    if unresolved_count == 0:
        for source in sorted(canonical_sources, key=lambda item: item["source_line"]):
            source_entry = row_plans[source["source_line"]]
            path = source_entry["source_path"]
            assert isinstance(path, str)
            records.append(
                _canonical_record(
                    root=root,
                    migration_id=migration_id,
                    source=source,
                    path=path,
                    body_sha=markdown_by_path[path]["body_sha256"],
                    normalized_status=source_entry["normalized_status"],
                    mapping_reason=source_entry["status_mapping_reason"],
                    original_status=source_entry["original_status"],
                    orphan=False,
                )
            )
        for orphan in orphan_entries:
            if orphan["disposition"] != "bind_as_legacy_import":
                continue
            records.append(
                _canonical_record(
                    root=root,
                    migration_id=migration_id,
                    source=None,
                    path=orphan["path"],
                    body_sha=orphan["body_sha256"],
                    normalized_status="informational",
                    mapping_reason="orphan_body_structure_not_evaluated",
                    original_status=None,
                    orphan=True,
                )
            )
    after_payload = b"".join(_canonical_json_bytes(record) for record in records)
    duplicate_fields: dict[str, int] = {}
    for field in ("log_id", "path", "content_id", "record_id"):
        values = [record.get(field) for record in records]
        duplicate_fields[field] = len(values) - len(set(values))
    if unresolved_count == 0 and any(duplicate_fields.values()):
        # Duplicate legacy log IDs are possible even when paths differ.  They
        # must be given deterministic migration aliases without discarding the
        # original identifier.
        seen_log_ids: set[str] = set()
        repaired = False
        for record in records:
            value = record["log_id"]
            if value in seen_log_ids:
                record["original_log_id"] = value
                record["log_id"] = "log-legacy-" + sha256_bytes(
                    (record["path"] + "\0" + record["body_sha256"]).encode("utf-8")
                )[:32]
                record["record_id"] = expected_record_id(record)
                repaired = True
            seen_log_ids.add(record["log_id"])
        if repaired:
            after_payload = b"".join(_canonical_json_bytes(record) for record in records)
        for field in ("log_id", "path", "content_id", "record_id"):
            values = [record.get(field) for record in records]
            duplicate_fields[field] = len(values) - len(set(values))
        if any(duplicate_fields.values()):
            unresolved_count += 1
            counts["unresolved"] += 1

    plan = {
        "schema_version": PLAN_SCHEMA_VERSION,
        "migration_id": migration_id,
        "tool_version": TOOL_VERSION,
        "root_identity": _root_identity(root),
        "source_index": {
            "path": ".agent_log/index.jsonl",
            "sha256": inventory["index_sha256"],
            "size": inventory["index_size"],
            "raw_row_count": inventory["source_row_count"],
        },
        "source_inventory_sha256": inventory["inventory_sha256"],
        "source_markdown_count": len(inventory["markdown"]),
        "status_map": {
            "ref": _relative_or_absolute(root, status_map_path),
            "sha256": sha256_bytes(status_payload),
            "schema_version": status_document["schema_version"],
            "mapping_policy_id": status_document["mapping_policy_id"],
            "version": status_document["version"],
        },
        "rows": rows,
        "orphans": orphan_entries,
        "body_resolutions": body_resolutions,
        "classification_counts": dict(sorted(counts.items())),
        "unresolved_count": unresolved_count,
        "expected_after_index_sha256": sha256_bytes(after_payload) if unresolved_count == 0 else None,
        "expected_after_index_size": len(after_payload) if unresolved_count == 0 else None,
        "expected_after_row_count": len(records) if unresolved_count == 0 else None,
        "body_mutation_count": 0,
        "historical_claims_upgraded": False,
    }
    return plan, after_payload


def write_plan(
    root_raw: str | Path,
    *,
    expected_index_sha256: str,
    status_map_raw: str | Path,
    output_raw: str | Path,
) -> dict[str, Any]:
    root = workspace_root(root_raw)
    source_payload = _read_index(root)
    actual_sha = sha256_bytes(source_payload)
    if actual_sha != expected_index_sha256:
        raise MigrationError(f"source index drift: expected {expected_index_sha256}, observed {actual_sha}")
    status_map_path = _resolve_ref(root, str(status_map_raw))
    plan, _ = _build_plan(root, status_map_path)
    output = Path(output_raw).expanduser().absolute()
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.is_symlink() or (output.exists() and not output.is_file()):
        raise MigrationError("plan output must be a regular non-symlink file")
    payload = _canonical_json_bytes(plan)
    _strict_atomic_replace(output, payload)
    return {
        "status": "planned" if plan["unresolved_count"] == 0 else "blocked",
        "plan": str(output),
        "plan_sha256": sha256_bytes(payload),
        "migration_id": plan["migration_id"],
        "unresolved_count": plan["unresolved_count"],
        "expected_after_index_sha256": plan["expected_after_index_sha256"],
    }


def _load_plan(path: Path) -> tuple[dict[str, Any], bytes]:
    payload = path.read_bytes()
    try:
        plan = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MigrationError(f"plan is not valid UTF-8 JSON: {exc}") from exc
    if not isinstance(plan, dict) or plan.get("schema_version") != PLAN_SCHEMA_VERSION:
        raise MigrationError(f"plan schema_version must be {PLAN_SCHEMA_VERSION}")
    return plan, payload


def _canonical_records_from_plan(root: Path, plan: dict[str, Any]) -> tuple[list[dict[str, Any]], bytes]:
    source_payload = _read_index(root)
    source_rows = {row["source_line"]: row for row in _split_source_rows(source_payload)}
    inventory = _inventory_document(root, source_payload)
    markdown_by_path = {item["path"]: item for item in inventory["markdown"]}
    records: list[dict[str, Any]] = []
    plan_rows = plan.get("rows")
    if not isinstance(plan_rows, list):
        raise MigrationError("plan rows are missing")
    for row_entry in plan_rows:
        if row_entry.get("classification") != "canonical_log":
            continue
        source_line = row_entry.get("source_line")
        source = source_rows.get(source_line)
        if source is None or source["source_row_sha256"] != row_entry.get("source_row_sha256"):
            raise MigrationError(f"source row drift at line {source_line}")
        path = row_entry.get("source_path")
        if not isinstance(path, str) or path not in markdown_by_path:
            raise MigrationError(f"planned canonical body is unavailable: {path}")
        records.append(
            _canonical_record(
                root=root,
                migration_id=plan["migration_id"],
                source=source,
                path=path,
                body_sha=markdown_by_path[path]["body_sha256"],
                normalized_status=row_entry["normalized_status"],
                mapping_reason=row_entry["status_mapping_reason"],
                original_status=row_entry["original_status"],
                orphan=False,
            )
        )
    for orphan in plan.get("orphans", []):
        if orphan.get("disposition") != "bind_as_legacy_import":
            continue
        path = orphan.get("path")
        if not isinstance(path, str) or path not in markdown_by_path:
            raise MigrationError(f"planned orphan body is unavailable: {path}")
        if markdown_by_path[path]["body_sha256"] != orphan.get("body_sha256"):
            raise MigrationError(f"planned orphan body drift: {path}")
        records.append(
            _canonical_record(
                root=root,
                migration_id=plan["migration_id"],
                source=None,
                path=path,
                body_sha=orphan["body_sha256"],
                normalized_status="informational",
                mapping_reason="orphan_body_structure_not_evaluated",
                original_status=None,
                orphan=True,
            )
        )
    # Apply the same deterministic duplicate-log-id aliasing as planning.
    seen: set[str] = set()
    for record in records:
        if record["log_id"] in seen:
            record["original_log_id"] = record["log_id"]
            record["log_id"] = "log-legacy-" + sha256_bytes(
                (record["path"] + "\0" + record["body_sha256"]).encode("utf-8")
            )[:32]
            record["record_id"] = expected_record_id(record)
        seen.add(record["log_id"])
    payload = b"".join(_canonical_json_bytes(record) for record in records)
    return records, payload


def _manifest_for(plan: dict[str, Any], inventory: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "kind": "agent_log_migration_resolution_manifest",
        "migration_id": plan["migration_id"],
        "source_index_sha256": plan["source_index"]["sha256"],
        "source_inventory_sha256": plan["source_inventory_sha256"],
        "source_rows": plan["rows"],
        "markdown_inventory": inventory["markdown"],
        "markdown_resolutions": plan["body_resolutions"],
        "orphans": plan["orphans"],
        "classification_counts": plan["classification_counts"],
        "unresolved_count": plan["unresolved_count"],
        "body_mutation_count": 0,
        "historical_claims_upgraded": False,
    }


def _ensure_directory(path: Path) -> None:
    if path.exists() or path.is_symlink():
        mode = path.lstat().st_mode
        if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
            raise MigrationError(f"migration directory is unsafe: {path}")
        return
    path.mkdir(mode=0o700, parents=True)
    _strict_fsync_directory(path.parent)


def _publish_identical(path: Path, payload: bytes) -> None:
    if path.exists() or path.is_symlink():
        if path.is_symlink() or not path.is_file():
            raise MigrationError(f"migration artifact is unsafe: {path}")
        if path.read_bytes() != payload:
            raise MigrationError(f"conflicting migration artifact already exists: {path}")
        return
    _strict_publish_new(path, payload)


def _failpoint(name: str) -> None:
    if os.environ.get("AGENT_LOG_MIGRATION_FAILPOINT") == name:
        raise RuntimeError(f"injected migration crash at {name}")


def _journal_payload(
    *,
    plan: dict[str, Any],
    plan_sha: str,
    source_inventory_sha: str,
    source_snapshot_ref: str,
    source_snapshot_sha: str,
    status_map_ref: str,
    status_map_sha: str,
    plan_ref: str,
    manifest_ref: str,
    manifest_sha: str,
    staged_ref: str,
    after_sha: str,
    after_size: int,
    after_rows: int,
    phase: str,
    prepared_at: str,
) -> dict[str, Any]:
    return {
        "schema_version": JOURNAL_SCHEMA_VERSION,
        "kind": "agent_log_migration_journal",
        "migration_id": plan["migration_id"],
        "tool_version": TOOL_VERSION,
        "phase": phase,
        "prepared_at": prepared_at,
        "root_identity": plan["root_identity"],
        "source_index_sha256": plan["source_index"]["sha256"],
        "source_index_size": plan["source_index"]["size"],
        "source_inventory_sha256": source_inventory_sha,
        "source_snapshot_ref": source_snapshot_ref,
        "source_snapshot_sha256": source_snapshot_sha,
        "status_map_ref": status_map_ref,
        "status_map_sha256": status_map_sha,
        "plan_ref": plan_ref,
        "plan_sha256": plan_sha,
        "manifest_ref": manifest_ref,
        "manifest_sha256": manifest_sha,
        "staged_index_ref": staged_ref,
        "after_index_sha256": after_sha,
        "after_index_size": after_size,
        "after_row_count": after_rows,
        "recovery_status": "not_needed",
    }


def _receipt_from_journal(root: Path, journal: dict[str, Any]) -> tuple[dict[str, Any], bytes]:
    manifest_path = _safe_migration_path(root, journal["manifest_ref"])
    if _sha256_path(manifest_path) != journal["manifest_sha256"]:
        raise MigrationError("resolution manifest hash mismatch")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    counts = manifest["classification_counts"]
    receipt = {
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "kind": MIGRATION_KIND,
        "migration_id": journal["migration_id"],
        "tool_version": journal["tool_version"],
        "transaction_status": "committed",
        "prepared_at": journal["prepared_at"],
        "committed_at": _utc_now(),
        "source_index_ref": ".agent_log/index.jsonl",
        "source_index_sha256": journal["source_index_sha256"],
        "source_index_size": journal["source_index_size"],
        "source_snapshot_ref": journal["source_snapshot_ref"],
        "source_snapshot_sha256": journal["source_snapshot_sha256"],
        "source_inventory_sha256": journal["source_inventory_sha256"],
        "plan_ref": journal["plan_ref"],
        "plan_sha256": journal["plan_sha256"],
        "status_map_ref": journal["status_map_ref"],
        "status_map_sha256": journal["status_map_sha256"],
        "resolution_manifest_ref": journal["manifest_ref"],
        "resolution_manifest_sha256": journal["manifest_sha256"],
        "journal_ref": (
            f".agent_log/migrations/{journal['migration_id']}/journal.json"
        ),
        "before_row_count": sum(counts.get(name, 0) for name in ("canonical_log", "duplicate_alias", "foreign_event", "unresolved")),
        "after_row_count": journal["after_row_count"],
        "before_index_sha256": journal["source_index_sha256"],
        "after_index_sha256": journal["after_index_sha256"],
        "after_index_size": journal["after_index_size"],
        "canonicalized_count": counts.get("canonical_log", 0),
        "legacy_import_count": counts.get("legacy_import_markdown", 0),
        "duplicate_alias_count": counts.get("duplicate_alias", 0),
        "body_alias_count": counts.get("body_alias_markdown", 0),
        "foreign_event_count": counts.get("foreign_event", 0),
        "orphan_count": counts.get("orphan_markdown", 0),
        "unresolved_count": counts.get("unresolved", 0),
        "body_mutation_count": 0,
        "missing_body_count": 0,
        "post_integrity_status": "valid",
        "post_legacy_count": 0,
        "post_orphan_count": 0,
        "post_duplicate_count": 0,
        "appendability_status": "pass",
        "historical_claims_upgraded": False,
        "recovery_status": journal.get("recovery_status", "not_needed"),
    }
    return receipt, _canonical_json_bytes(receipt)


def _marker_for(
    journal: dict[str, Any],
    receipt_ref: str,
    receipt_sha: str,
    journal_ref: str,
    journal_sha: str,
) -> dict[str, Any]:
    return {
        "schema_version": MARKER_SCHEMA_VERSION,
        "kind": "agent_log_migration_commit_marker",
        "transaction_status": "committed",
        "migration_id": journal["migration_id"],
        "tool_version": journal["tool_version"],
        "plan_sha256": journal["plan_sha256"],
        "receipt_ref": receipt_ref,
        "receipt_sha256": receipt_sha,
        "journal_ref": journal_ref,
        "journal_sha256": journal_sha,
        "after_index_sha256": journal["after_index_sha256"],
        "after_index_size": journal["after_index_size"],
    }


def _current_prefix_matches(index_payload: bytes, expected_sha: str, expected_size: int) -> bool:
    return len(index_payload) >= expected_size and sha256_bytes(index_payload[:expected_size]) == expected_sha


def _active_marker(root: Path) -> tuple[dict[str, Any], bytes] | None:
    path = root / ".agent_log" / "migrations" / "active.json"
    if not path.exists() and not path.is_symlink():
        return None
    if path.is_symlink() or not path.is_file():
        raise MigrationError("active migration marker is unsafe")
    payload = path.read_bytes()
    try:
        marker = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MigrationError(f"active migration marker is invalid: {exc}") from exc
    if not isinstance(marker, dict):
        raise MigrationError("active migration marker must be an object")
    return marker, payload


def _validate_existing_idempotent(root: Path, plan_sha: str, plan: dict[str, Any]) -> dict[str, Any] | None:
    active = _active_marker(root)
    if active is None:
        return None
    marker, _ = active
    if marker.get("plan_sha256") != plan_sha or marker.get("migration_id") != plan.get("migration_id"):
        raise MigrationError("a different migration is already committed")
    index_payload = _read_index(root)
    if not _current_prefix_matches(index_payload, marker.get("after_index_sha256", ""), marker.get("after_index_size", -1)):
        raise MigrationError("committed migration prefix does not match the current index")
    receipt_path = _safe_migration_path(root, marker.get("receipt_ref"))
    if _sha256_path(receipt_path) != marker.get("receipt_sha256"):
        raise MigrationError("committed migration receipt hash mismatch")
    validate_receipt(root, receipt_path, require_appendable=True)
    return {
        "status": "already_committed",
        "migration_id": plan["migration_id"],
        "receipt": str(receipt_path),
        "receipt_sha256": marker["receipt_sha256"],
        "after_index_sha256": marker["after_index_sha256"],
        "idempotent": True,
    }


def apply_plan(
    root_raw: str | Path,
    *,
    plan_raw: str | Path,
    expected_plan_sha256: str,
    expected_index_sha256: str,
    expected_inventory_sha256: str,
    dry_run: bool = False,
) -> dict[str, Any]:
    root = workspace_root(root_raw)
    plan_path = _resolve_ref(root, str(plan_raw))
    plan, plan_payload = _load_plan(plan_path)
    plan_sha = sha256_bytes(plan_payload)
    if plan_sha != expected_plan_sha256:
        raise MigrationError(f"plan SHA-256 mismatch: expected {expected_plan_sha256}, observed {plan_sha}")
    if plan.get("unresolved_count") != 0:
        raise MigrationError("migration apply is blocked while unresolved_count is nonzero")
    if plan.get("source_index", {}).get("sha256") != expected_index_sha256:
        raise MigrationError("expected index SHA does not match the plan")
    if plan.get("source_inventory_sha256") != expected_inventory_sha256:
        raise MigrationError("expected inventory SHA does not match the plan")
    if plan.get("root_identity") != _root_identity(root):
        raise MigrationError("plan root identity does not match this workspace")

    active = _validate_existing_idempotent(root, plan_sha, plan)
    if active is not None:
        return active

    status_map_path = _resolve_ref(root, plan["status_map"]["ref"])
    status_map_payload = status_map_path.read_bytes()
    if sha256_bytes(status_map_payload) != plan["status_map"]["sha256"]:
        raise MigrationError("status map drift detected before apply")
    if dry_run:
        source_payload = _read_index(root)
        if sha256_bytes(source_payload) != expected_index_sha256:
            raise MigrationError("source index drift detected before dry-run")
        inventory = _inventory_document(root, source_payload)
        if inventory["inventory_sha256"] != expected_inventory_sha256:
            raise MigrationError("source Markdown inventory drift detected before dry-run")
        _, after_payload = _canonical_records_from_plan(root, plan)
        after_sha = sha256_bytes(after_payload)
        if after_sha != plan.get("expected_after_index_sha256") or len(after_payload) != plan.get("expected_after_index_size"):
            raise MigrationError("reconstructed after-index does not match the plan")
        return {
            "status": "dry_run_pass",
            "migration_id": plan["migration_id"],
            "source_index_sha256": expected_index_sha256,
            "source_inventory_sha256": expected_inventory_sha256,
            "after_index_sha256": after_sha,
            "after_row_count": plan["expected_after_row_count"],
            "zero_canonical_mutation": True,
        }

    with log_lock(root):
        active = _validate_existing_idempotent(root, plan_sha, plan)
        if active is not None:
            return active
        source_payload = _read_index(root)
        if sha256_bytes(source_payload) != expected_index_sha256:
            raise MigrationError("source index drift detected inside migration lock")
        inventory = _inventory_document(root, source_payload)
        if inventory["inventory_sha256"] != expected_inventory_sha256:
            raise MigrationError("source inventory drift detected inside migration lock")
        _, after_payload = _canonical_records_from_plan(root, plan)
        after_sha = sha256_bytes(after_payload)
        if after_sha != plan.get("expected_after_index_sha256") or len(after_payload) != plan.get("expected_after_index_size"):
            raise MigrationError("reconstructed after-index does not match the plan")

        migration_root = root / ".agent_log" / "migrations"
        transaction_root = migration_root / plan["migration_id"]
        _ensure_directory(migration_root)
        _ensure_directory(transaction_root)
        source_snapshot = transaction_root / "source-index.snapshot"
        status_map_copy = transaction_root / "status-map.json"
        plan_copy = transaction_root / "plan.json"
        manifest_path = transaction_root / "resolution-manifest.json"
        staged_path = transaction_root / "staged-index.snapshot"
        journal_path = transaction_root / "journal.json"
        receipt_path = transaction_root / "receipt.json"
        marker_path = migration_root / "active.json"
        refs = {
            name: path.relative_to(root).as_posix()
            for name, path in (
                ("source", source_snapshot),
                ("status_map", status_map_copy),
                ("plan", plan_copy),
                ("manifest", manifest_path),
                ("staged", staged_path),
                ("journal", journal_path),
                ("receipt", receipt_path),
            )
        }
        _publish_identical(source_snapshot, source_payload)
        _failpoint("after_snapshot")
        _publish_identical(status_map_copy, status_map_payload)
        _publish_identical(plan_copy, plan_payload)
        manifest = _manifest_for(plan, inventory)
        manifest_payload = _canonical_json_bytes(manifest)
        _publish_identical(manifest_path, manifest_payload)
        _publish_identical(staged_path, after_payload)
        _failpoint("after_sidecars")
        prepared_at = _utc_now()
        journal = _journal_payload(
            plan=plan,
            plan_sha=plan_sha,
            source_inventory_sha=expected_inventory_sha256,
            source_snapshot_ref=refs["source"],
            source_snapshot_sha=sha256_bytes(source_payload),
            status_map_ref=refs["status_map"],
            status_map_sha=sha256_bytes(status_map_payload),
            plan_ref=refs["plan"],
            manifest_ref=refs["manifest"],
            manifest_sha=sha256_bytes(manifest_payload),
            staged_ref=refs["staged"],
            after_sha=after_sha,
            after_size=len(after_payload),
            after_rows=plan["expected_after_row_count"],
            phase="prepared",
            prepared_at=prepared_at,
        )
        _strict_atomic_replace(journal_path, _canonical_json_bytes(journal))
        _failpoint("after_prepare")
        hold = os.environ.get("AGENT_LOG_MIGRATION_LOCK_HOLD_SECONDS")
        if hold:
            time.sleep(min(max(float(hold), 0.0), 10.0))
        _strict_atomic_replace(_index_path(root), after_payload)
        journal["phase"] = "switched"
        _strict_atomic_replace(journal_path, _canonical_json_bytes(journal))
        _failpoint("after_switch")
        receipt, receipt_payload = _receipt_from_journal(root, journal)
        _strict_atomic_replace(receipt_path, receipt_payload)
        _failpoint("after_receipt")
        journal["phase"] = "committed"
        journal["committed_at"] = _utc_now()
        journal["receipt_ref"] = refs["receipt"]
        journal["receipt_sha256"] = sha256_bytes(receipt_payload)
        _strict_atomic_replace(journal_path, _canonical_json_bytes(journal))
        _failpoint("after_journal_commit")
        journal_sha = _sha256_path(journal_path)
        marker = _marker_for(
            journal,
            refs["receipt"],
            sha256_bytes(receipt_payload),
            refs["journal"],
            journal_sha,
        )
        _strict_atomic_replace(marker_path, _canonical_json_bytes(marker))
        _failpoint("after_marker")
        validation = validate_receipt(root, receipt_path, require_appendable=True)
        if validation["status"] != "valid":
            raise MigrationError("post-publication receipt validation failed")
        return {
            "status": "committed",
            "migration_id": plan["migration_id"],
            "receipt": str(receipt_path),
            "receipt_sha256": sha256_bytes(receipt_payload),
            "manifest": str(manifest_path),
            "manifest_sha256": sha256_bytes(manifest_payload),
            "source_snapshot": str(source_snapshot),
            "source_snapshot_sha256": sha256_bytes(source_payload),
            "before_index_sha256": expected_index_sha256,
            "after_index_sha256": after_sha,
            "after_row_count": plan["expected_after_row_count"],
            "idempotent": False,
        }


def _load_journal(root: Path, transaction_id: str) -> tuple[Path, dict[str, Any]]:
    if not re.fullmatch(r"agent-log-migration-[0-9a-f]{24}", transaction_id):
        raise MigrationError("invalid transaction ID")
    path = root / ".agent_log" / "migrations" / transaction_id / "journal.json"
    if path.is_symlink() or not path.is_file():
        raise MigrationError("migration journal is missing or unsafe")
    try:
        journal = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MigrationError(f"migration journal is invalid: {exc}") from exc
    if not isinstance(journal, dict) or journal.get("migration_id") != transaction_id:
        raise MigrationError("migration journal identity mismatch")
    return path, journal


def recover(root_raw: str | Path, transaction_id: str) -> dict[str, Any]:
    root = workspace_root(root_raw)
    with log_lock(root):
        journal_path, journal = _load_journal(root, transaction_id)
        if journal.get("root_identity") != _root_identity(root):
            raise MigrationError("migration journal root identity mismatch")
        source_snapshot = _safe_migration_path(root, journal["source_snapshot_ref"])
        staged = _safe_migration_path(root, journal["staged_index_ref"])
        if _sha256_path(source_snapshot) != journal["source_snapshot_sha256"]:
            raise MigrationError("source snapshot hash mismatch; automatic recovery is forbidden")
        if _sha256_path(staged) != journal["after_index_sha256"] or staged.stat().st_size != journal["after_index_size"]:
            raise MigrationError("staged index hash mismatch; automatic recovery is forbidden")
        index_payload = _read_index(root)
        source_exact = sha256_bytes(index_payload) == journal["source_index_sha256"]
        after_prefix = _current_prefix_matches(index_payload, journal["after_index_sha256"], journal["after_index_size"])
        if source_exact:
            journal["phase"] = "prepared_aborted"
            journal["recovery_status"] = "prepared_sidecars_retained_source_unchanged"
            journal["recovered_at"] = _utc_now()
            _strict_atomic_replace(journal_path, _canonical_json_bytes(journal))
            return {
                "status": "prepared_aborted",
                "migration_id": transaction_id,
                "source_index_unchanged": True,
                "retry_apply_allowed": True,
            }
        if not after_prefix:
            raise MigrationError("index drift prevents automatic migration recovery")
        receipt_path = root / ".agent_log" / "migrations" / transaction_id / "receipt.json"
        receipt_ref = receipt_path.relative_to(root).as_posix()
        receipt, receipt_payload = _receipt_from_journal(root, {**journal, "recovery_status": "forward_completed"})
        _strict_atomic_replace(receipt_path, receipt_payload)
        journal["phase"] = "committed"
        journal["recovery_status"] = "forward_completed"
        journal["recovered_at"] = _utc_now()
        journal["receipt_ref"] = receipt_ref
        journal["receipt_sha256"] = sha256_bytes(receipt_payload)
        _strict_atomic_replace(journal_path, _canonical_json_bytes(journal))
        journal_ref = journal_path.relative_to(root).as_posix()
        marker = _marker_for(
            journal,
            receipt_ref,
            sha256_bytes(receipt_payload),
            journal_ref,
            _sha256_path(journal_path),
        )
        marker_path = root / ".agent_log" / "migrations" / "active.json"
        _strict_atomic_replace(marker_path, _canonical_json_bytes(marker))
        validate_receipt(root, receipt_path, require_appendable=True)
        return {
            "status": "forward_completed",
            "migration_id": transaction_id,
            "receipt": str(receipt_path),
            "receipt_sha256": sha256_bytes(receipt_payload),
        }


def _verify_hashed_ref(root: Path, receipt: dict[str, Any], ref_field: str, sha_field: str) -> Path:
    path = _safe_migration_path(root, receipt.get(ref_field))
    observed = _sha256_path(path)
    if observed != receipt.get(sha_field):
        raise MigrationError(f"{ref_field} SHA-256 mismatch")
    return path


def validate_receipt(
    root_raw: str | Path,
    receipt_raw: str | Path,
    *,
    require_appendable: bool = False,
) -> dict[str, Any]:
    root = workspace_root(root_raw)
    receipt_path = Path(receipt_raw)
    if not receipt_path.is_absolute():
        receipt_path = root / receipt_path
    try:
        receipt_relative = receipt_path.resolve(strict=True).relative_to(root).as_posix()
    except (OSError, ValueError) as exc:
        raise MigrationError("receipt must be a regular workspace-local file") from exc
    receipt_path = _safe_migration_path(root, receipt_relative)
    receipt_payload = receipt_path.read_bytes()
    try:
        receipt = json.loads(receipt_payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MigrationError(f"receipt is invalid: {exc}") from exc
    if not isinstance(receipt, dict):
        raise MigrationError("receipt must be an object")
    if receipt.get("schema_version") != RECEIPT_SCHEMA_VERSION or receipt.get("kind") != MIGRATION_KIND:
        raise MigrationError("receipt kind or schema_version mismatch")
    if receipt.get("transaction_status") != "committed":
        raise MigrationError("receipt is not committed")
    if receipt.get("unresolved_count") != 0 or receipt.get("body_mutation_count") != 0:
        raise MigrationError("receipt reports unresolved rows or body mutation")
    source_snapshot = _verify_hashed_ref(root, receipt, "source_snapshot_ref", "source_snapshot_sha256")
    _verify_hashed_ref(root, receipt, "plan_ref", "plan_sha256")
    _verify_hashed_ref(root, receipt, "status_map_ref", "status_map_sha256")
    manifest_path = _verify_hashed_ref(root, receipt, "resolution_manifest_ref", "resolution_manifest_sha256")
    if source_snapshot.stat().st_size != receipt.get("source_index_size"):
        raise MigrationError("source snapshot size mismatch")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("migration_id") != receipt.get("migration_id"):
        raise MigrationError("resolution manifest migration identity mismatch")
    source_rows = manifest.get("source_rows")
    markdown_inventory = manifest.get("markdown_inventory")
    if not isinstance(source_rows, list) or len(source_rows) != receipt.get("before_row_count"):
        raise MigrationError("resolution manifest source-row accounting mismatch")
    if len({row.get("source_line") for row in source_rows}) != len(source_rows):
        raise MigrationError("resolution manifest source rows are not unique")
    if not isinstance(markdown_inventory, list) or len({row.get("path") for row in markdown_inventory}) != len(markdown_inventory):
        raise MigrationError("resolution manifest Markdown accounting mismatch")
    active = _active_marker(root)
    if active is None:
        raise MigrationError("committed migration marker is missing")
    marker, _ = active
    if marker.get("transaction_status") != "committed" or marker.get("migration_id") != receipt.get("migration_id"):
        raise MigrationError("committed migration marker identity mismatch")
    if marker.get("receipt_ref") != receipt_relative or marker.get("receipt_sha256") != sha256_bytes(receipt_payload):
        raise MigrationError("committed migration marker receipt binding mismatch")
    index_payload = _read_index(root)
    if not _current_prefix_matches(index_payload, receipt.get("after_index_sha256", ""), receipt.get("after_index_size", -1)):
        raise MigrationError("canonical index does not contain the committed migration prefix")
    inspection, _, _ = inspect_agent_log_store(root)
    if inspection.get("status") != "valid":
        raise MigrationError(f"post-migration integrity is not valid: {inspection.get('findings', [])[:1]}")
    if any(inspection.get(field, 0) for field in ("legacy_count", "tampered_count", "missing_count", "duplicate_count", "orphan_count")):
        raise MigrationError("post-migration integrity counters are nonzero")
    appendability = "not_requested"
    if require_appendable:
        validate_store_for_append(root, index_payload, _index_path(root))
        appendability = "pass"
    return {
        "status": "valid",
        "kind": MIGRATION_KIND,
        "migration_id": receipt["migration_id"],
        "receipt": str(receipt_path),
        "receipt_sha256": sha256_bytes(receipt_payload),
        "source_snapshot_sha256": receipt["source_snapshot_sha256"],
        "after_index_sha256": receipt["after_index_sha256"],
        "current_index_sha256": sha256_bytes(index_payload),
        "appendability": appendability,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect, plan, apply, validate, or recover a sealed .agent_log legacy migration.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect_parser = subparsers.add_parser("inspect", help="Read-only source/index/body inventory.")
    inspect_parser.add_argument("--root", required=True)
    inspect_parser.add_argument("--json", action="store_true", help="Emit JSON (the default output format).")

    plan_parser = subparsers.add_parser("plan", help="Write a deterministic zero-canonical-mutation plan.")
    plan_parser.add_argument("--root", required=True)
    plan_parser.add_argument("--expected-index-sha256", required=True)
    plan_parser.add_argument("--status-map", required=True)
    plan_parser.add_argument("--output", required=True)

    apply_parser = subparsers.add_parser("apply", help="Apply one expected-hash-bound locked transaction.")
    apply_parser.add_argument("--root", required=True)
    apply_parser.add_argument("--plan", required=True)
    apply_parser.add_argument("--expected-plan-sha256", required=True)
    apply_parser.add_argument("--expected-index-sha256", required=True)
    apply_parser.add_argument("--expected-inventory-sha256", required=True)
    apply_parser.add_argument("--dry-run", action="store_true")

    validate_parser = subparsers.add_parser("validate", help="Validate receipt, sidecars, prefix, store, and appendability.")
    validate_parser.add_argument("--root", required=True)
    validate_parser.add_argument("--receipt", required=True)
    validate_parser.add_argument("--require-appendable", action="store_true")

    recover_parser = subparsers.add_parser("recover", help="Recover a prepared or switched transaction without history rollback.")
    recover_parser.add_argument("--root", required=True)
    recover_parser.add_argument("--transaction-id", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "inspect":
            result = inspect_store(args.root)
        elif args.command == "plan":
            result = write_plan(
                args.root,
                expected_index_sha256=args.expected_index_sha256,
                status_map_raw=args.status_map,
                output_raw=args.output,
            )
        elif args.command == "apply":
            result = apply_plan(
                args.root,
                plan_raw=args.plan,
                expected_plan_sha256=args.expected_plan_sha256,
                expected_index_sha256=args.expected_index_sha256,
                expected_inventory_sha256=args.expected_inventory_sha256,
                dry_run=args.dry_run,
            )
        elif args.command == "validate":
            result = validate_receipt(args.root, args.receipt, require_appendable=args.require_appendable)
        else:
            result = recover(args.root, args.transaction_id)
    except (AgentLogIntegrityError, MigrationError, OSError, ValueError) as exc:
        print(json.dumps({"status": "blocked", "error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
