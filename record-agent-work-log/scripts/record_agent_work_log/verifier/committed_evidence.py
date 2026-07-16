"""Independent committed-record and live-store verification."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .core import (
    CURRENT_STATUSES,
    _body_metadata,
    _canonical_json,
    _expected_record_id,
    _is_current_record,
    _records,
    _require,
    _sha256,
)


def _expected_committed_records(
    *,
    root: Path,
    migration_id: str,
    source_rows: list[dict[str, Any]],
    inventory_by_path: dict[str, dict[str, Any]],
    canonical_by_line: dict[int, dict[str, Any]],
    orphans: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    source_by_line = {row["source_line"]: row for row in source_rows}

    def build(
        path: str,
        normalized_status: str,
        mapping_reason: str,
        original_status: str | None,
        source: dict[str, Any] | None,
        orphan: bool,
    ) -> dict[str, Any]:
        body_sha = inventory_by_path[path]["body_sha256"]
        parsed = source["parsed"] if source is not None else None
        if isinstance(parsed, dict) and _is_current_record(parsed, body_sha):
            return dict(parsed)
        metadata = _body_metadata(root / path)
        log_id = parsed.get("log_id") if isinstance(parsed, dict) else None
        if not isinstance(log_id, str) or not log_id:
            log_id = metadata.get("log_id")
        if not isinstance(log_id, str) or not log_id:
            log_id = "log-legacy-" + _sha256((path + "\0" + body_sha).encode("utf-8"))[:32]
        timestamp = parsed.get("timestamp") if isinstance(parsed, dict) else None
        if not isinstance(timestamp, str) or not timestamp:
            timestamp = metadata.get("timestamp") or "1970-01-01T00:00:00Z"
        title = parsed.get("title") if isinstance(parsed, dict) else None
        if not isinstance(title, str) or not title:
            title = metadata.get("title") or Path(path).stem
        record: dict[str, Any] = {
            "format_version": 3,
            "schema_version": 2,
            "log_id": log_id,
            "body_sha256": body_sha,
            "content_id": "log-content-" + body_sha[:32],
            "timestamp": timestamp,
            "status": normalized_status,
            "title": title,
            "path": path,
            "migration_id": migration_id,
            "legacy_import": True,
            "structured_fields_status": (
                "not_evaluated" if orphan else "source_index_limited"
            ),
            "original_status": original_status,
            "status_mapping_reason": mapping_reason,
            "status_evidence": (
                "not_evaluated" if original_status is None else "legacy_source_only"
            ),
            "source_line": source["source_line"] if source is not None else None,
            "source_row_sha256": (
                source["source_row_sha256"] if source is not None else None
            ),
            "historical_claims_upgraded": False,
        }
        record["record_id"] = _expected_record_id(record)
        return record

    records: list[dict[str, Any]] = []
    for line, plan_row in sorted(canonical_by_line.items()):
        source = source_by_line[line]
        records.append(
            build(
                plan_row["source_path"],
                plan_row["normalized_status"],
                plan_row["status_mapping_reason"],
                plan_row["original_status"],
                source,
                False,
            )
        )
    for orphan in orphans:
        if orphan.get("disposition") == "bind_as_legacy_import":
            records.append(
                build(
                    orphan["path"],
                    "informational",
                    "orphan_body_structure_not_evaluated",
                    None,
                    None,
                    True,
                )
            )
    seen_log_ids: set[str] = set()
    for record in records:
        log_id = record["log_id"]
        if log_id in seen_log_ids:
            record["original_log_id"] = log_id
            record["log_id"] = "log-legacy-" + _sha256(
                (record["path"] + "\0" + record["body_sha256"]).encode("utf-8")
            )[:32]
            record["record_id"] = _expected_record_id(record)
        seen_log_ids.add(record["log_id"])
    return records

def _verify_committed_records(
    *,
    root: Path,
    migration_id: str,
    prefix: bytes,
    plan: dict[str, Any],
    source_rows: list[dict[str, Any]],
    inventory_by_path: dict[str, dict[str, Any]],
    canonical_by_line: dict[int, dict[str, Any]],
    orphans: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows = _records(prefix)
    expected_rows = _expected_committed_records(
        root=root,
        migration_id=migration_id,
        source_rows=source_rows,
        inventory_by_path=inventory_by_path,
        canonical_by_line=canonical_by_line,
        orphans=orphans,
    )
    _require(rows == expected_rows, "committed records differ from independent source reconstruction")
    _require(
        prefix == b"".join(_canonical_json(record) for record in expected_rows),
        "committed prefix bytes differ from independent source reconstruction",
    )
    expected_paths = {entry["source_path"] for entry in canonical_by_line.values()}
    expected_paths.update(entry["path"] for entry in orphans if entry.get("disposition") == "bind_as_legacy_import")
    by_path = {row.get("path"): row for row in rows}
    _require(len(by_path) == len(rows), "committed index contains duplicate or missing paths")
    _require(set(by_path) == expected_paths, "committed index paths differ from independently resolved paths")
    status_by_path = {entry["source_path"]: entry["normalized_status"] for entry in canonical_by_line.values()}
    for orphan in orphans:
        if orphan.get("disposition") == "bind_as_legacy_import":
            status_by_path[orphan["path"]] = "informational"
    for path, record in by_path.items():
        _require(record.get("body_sha256") == inventory_by_path[path].get("body_sha256"), f"committed body hash mismatch: {path}")
        _require(record.get("status") == status_by_path[path], f"committed status mismatch: {path}")
        _require(record.get("historical_claims_upgraded") is not True, f"committed record upgrades historical claims: {path}")
        content_id = record.get("content_id")
        if record.get("content_id_scheme") is None:
            _require(content_id == "log-content-" + record["body_sha256"][:32], f"committed content ID mismatch: {path}")
        _require(record.get("record_id") == _expected_record_id(record), f"committed record ID mismatch: {path}")
    _require(len(rows) == plan.get("expected_after_row_count"), "committed row count differs from plan")
    return rows

def _verify_current_store(
    payload: bytes,
    actual_markdown: dict[str, dict[str, Any]],
    *,
    committed_row_count: int,
    migration_id: str,
) -> list[dict[str, Any]]:
    rows = _records(payload)
    unique_fields = ("log_id", "path", "content_id", "record_id")
    seen = {field: set() for field in unique_fields}
    for position, record in enumerate(rows, start=1):
        for field in ("timestamp", "status", "path"):
            _require(
                isinstance(record.get(field), str) and record[field].strip(),
                f"current index row {position} missing non-empty {field}",
            )
        _require(record.get("format_version") == 3, f"current index row {position} format version mismatch")
        _require(record.get("schema_version") == 2, f"current index row {position} schema version mismatch")
        _require(record.get("status") in CURRENT_STATUSES, f"current index row {position} status mismatch")
        _require(record.get("content_id_scheme") is None, f"current index row {position} content ID scheme is unsupported")
        if position <= committed_row_count:
            _require(record.get("migration_id") in {None, migration_id}, f"committed prefix row {position} migration identity mismatch")
        else:
            _require(record.get("migration_id") is None, f"migration-derived row appears after the sealed boundary at row {position}")
        path = record.get("path")
        relative = Path(path)
        _require(
            not relative.is_absolute()
            and path == relative.as_posix()
            and len(relative.parts) >= 3
            and relative.parts[0] == ".agent_log"
            and relative.suffix.lower() == ".md"
            and all(part not in {"", ".", ".."} for part in relative.parts),
            f"current index row {position} path is unsafe",
        )
        _require(isinstance(path, str) and path in actual_markdown, f"current index row {position} body is missing")
        _require(record.get("body_sha256") == actual_markdown[path].get("body_sha256"), f"current index row {position} body hash mismatch")
        _require(record.get("content_id") == "log-content-" + record["body_sha256"][:32], f"current index row {position} content ID mismatch")
        _require(record.get("record_id") == _expected_record_id(record), f"current index row {position} record ID mismatch")
        for field in unique_fields:
            value = record.get(field)
            _require(isinstance(value, str) and value and value not in seen[field], f"current index row {position} duplicate or missing {field}")
            seen[field].add(value)
    return rows
