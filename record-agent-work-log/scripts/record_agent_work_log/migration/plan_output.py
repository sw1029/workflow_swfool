"""Canonical record materialization and final plan document assembly."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from ..integrity import expected_record_id, sha256_bytes
from .classification import _canonical_record
from .contracts import PLAN_SCHEMA_VERSION, TOOL_VERSION
from .storage import _canonical_json_bytes, _relative_or_absolute, _root_identity


def build_canonical_records(
    root: Path,
    migration_id: str,
    canonical_sources: list[dict[str, Any]],
    row_plans: dict[int, dict[str, Any]],
    markdown_by_path: dict[str, dict[str, Any]],
    orphan_entries: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for source in sorted(canonical_sources, key=lambda item: item["source_line"]):
        entry = row_plans[source["source_line"]]
        path = entry["source_path"]
        assert isinstance(path, str)
        records.append(
            _canonical_record(
                root=root,
                migration_id=migration_id,
                source=source,
                path=path,
                body_sha=markdown_by_path[path]["body_sha256"],
                normalized_status=entry["normalized_status"],
                mapping_reason=entry["status_mapping_reason"],
                original_status=entry["original_status"],
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
    return records


def finalize_record_identifiers(
    records: list[dict[str, Any]],
    unresolved_count: int,
    counts: Counter[str],
) -> tuple[bytes, int]:
    """Repair duplicate legacy log IDs and reject all remaining collisions."""

    duplicate_fields: dict[str, int] = {}
    for field in ("log_id", "path", "content_id", "record_id"):
        values = [record.get(field) for record in records]
        duplicate_fields[field] = len(values) - len(set(values))
    if unresolved_count == 0 and any(duplicate_fields.values()):
        seen_log_ids: set[str] = set()
        for record in records:
            value = record["log_id"]
            if value in seen_log_ids:
                record["original_log_id"] = value
                record["log_id"] = "log-legacy-" + sha256_bytes(
                    (record["path"] + "\0" + record["body_sha256"]).encode("utf-8")
                )[:32]
                record["record_id"] = expected_record_id(record)
            seen_log_ids.add(record["log_id"])
        for field in ("log_id", "path", "content_id", "record_id"):
            values = [record.get(field) for record in records]
            duplicate_fields[field] = len(values) - len(set(values))
        if any(duplicate_fields.values()):
            unresolved_count += 1
            counts["unresolved"] += 1
    return b"".join(_canonical_json_bytes(record) for record in records), unresolved_count


def build_plan_document(
    *,
    root: Path,
    migration_id: str,
    inventory: dict[str, Any],
    status_map_path: Path,
    status_document: dict[str, Any],
    status_payload: bytes,
    rows: list[dict[str, Any]],
    orphan_entries: list[dict[str, Any]],
    body_resolutions: list[dict[str, Any]],
    counts: Counter[str],
    unresolved_count: int,
    after_payload: bytes,
    record_count: int,
) -> dict[str, Any]:
    return {
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
        "expected_after_index_sha256": (
            sha256_bytes(after_payload) if unresolved_count == 0 else None
        ),
        "expected_after_index_size": len(after_payload) if unresolved_count == 0 else None,
        "expected_after_row_count": record_count if unresolved_count == 0 else None,
        "body_mutation_count": 0,
        "historical_claims_upgraded": False,
    }
