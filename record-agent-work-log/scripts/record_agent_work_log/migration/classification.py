"""Exact status mapping, duplicate classification, and canonical records."""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import re
from typing import Any

from ..integrity import (
    AgentLogIntegrityError,
    LOG_FORMAT_VERSION,
    LOG_SCHEMA_VERSION,
    LOG_STATUSES,
    content_id_for,
    expected_record_id,
    safe_log_file,
    sha256_bytes,
)
from .contracts import STATUS_MAP_SCHEMA_VERSION, MigrationError


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
