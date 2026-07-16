"""Whole-store integrity projection."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .contracts import CONTENT_ID_RE, RECORD_ID_RE, SHA256_RE, AgentLogIntegrityError
from .core import (
    _directory_projection,
    ensure_log_root,
    expected_content_id,
    expected_record_id,
    safe_log_file,
    sha256_file,
    workspace_root,
)
from .index import _parse_index, _walk_store
from .migration import _verify_committed_migration


@dataclass
class InspectionState:
    root: Path
    base: dict[str, Any]
    markdown: list[Path]
    jsonl: list[Path]
    referenced: set[str] = field(default_factory=set)
    sealed_inventory_paths: set[str] = field(default_factory=set)
    sealed_nonconsumable_paths: set[str] = field(default_factory=set)
    seen_by_field: dict[str, set[str]] = field(
        default_factory=lambda: {
            "log_id": set(),
            "path": set(),
            "content_id": set(),
            "record_id": set(),
        }
    )


def _unsafe_workspace_result(detail: str) -> tuple[dict[str, Any], list[Path], list[Path]]:
    return (
        {
            "status": "unsafe",
            "directory": {"path": ".agent_log", "exists": False},
            "indexed_count": 0,
            "verified_count": 0,
            "legacy_count": 0,
            "tampered_count": 0,
            "missing_count": 0,
            "duplicate_count": 0,
            "orphan_count": 0,
            "orphan_paths": [],
            "findings": [
                {"code": "agent_log_workspace_unsafe", "detail": detail}
            ],
        },
        [],
        [],
    )


def _base_projection(root: Path, log_root: Path) -> dict[str, Any]:
    return {
        "status": "absent",
        "directory": _directory_projection(root, log_root),
        "indexed_count": 0,
        "verified_count": 0,
        "legacy_count": 0,
        "tampered_count": 0,
        "missing_count": 0,
        "duplicate_count": 0,
        "orphan_count": 0,
        "orphan_paths": [],
        "findings": [],
    }


def _apply_migration_projection(
    state: InspectionState, migration: dict[str, Any] | None
) -> None:
    if migration is None:
        return
    state.sealed_inventory_paths = set(
        migration.pop("_sealed_inventory_paths", [])
    )
    state.sealed_nonconsumable_paths = set(
        migration.pop("_sealed_nonconsumable_paths", [])
    )
    state.base["migration"] = migration


def _record_duplicates(
    state: InspectionState,
    record: dict[str, Any],
    path_value: str,
    line_no: int,
) -> None:
    for field_name, seen in state.seen_by_field.items():
        value = record.get(field_name)
        if not isinstance(value, str) or not value:
            continue
        if value in seen:
            state.base["duplicate_count"] += 1
            state.base["findings"].append(
                {
                    "code": f"agent_log_duplicate_{field_name}",
                    "path": path_value,
                    "line": line_no,
                }
            )
        seen.add(value)


def _inspect_integrity_bound_record(
    state: InspectionState, record: dict[str, Any], path_value: str
) -> None:
    required = {"log_id", "body_sha256", "content_id", "record_id"}
    if any(
        not isinstance(record.get(field_name), str) or not record[field_name]
        for field_name in required
    ):
        state.base["tampered_count"] += 1
        state.base["findings"].append(
            {"code": "agent_log_integrity_field_missing", "path": path_value}
        )
        return
    body_sha = record["body_sha256"]
    if (
        not SHA256_RE.fullmatch(body_sha)
        or not CONTENT_ID_RE.fullmatch(record["content_id"])
        or record["content_id"] != expected_content_id(record)
        or not RECORD_ID_RE.fullmatch(record["record_id"])
        or record["record_id"] != expected_record_id(record)
    ):
        state.base["tampered_count"] += 1
        state.base["findings"].append(
            {"code": "agent_log_record_identity_mismatch", "path": path_value}
        )
        return
    try:
        body_path = safe_log_file(state.root, path_value, must_exist=True)
    except AgentLogIntegrityError as exc:
        state.base["missing_count"] += 1
        state.base["findings"].append(
            {
                "code": "agent_log_body_missing_or_unsafe",
                "path": path_value,
                "detail": str(exc),
            }
        )
        return
    if sha256_file(body_path) != body_sha:
        state.base["tampered_count"] += 1
        state.base["findings"].append(
            {"code": "agent_log_body_hash_mismatch", "path": path_value}
        )
        return
    state.base["verified_count"] += 1


def _inspect_record(
    state: InspectionState, record: dict[str, Any], line_no: int
) -> None:
    path_value = str(record["path"])
    state.referenced.add(path_value)
    _record_duplicates(state, record, path_value, line_no)
    format_version = record.get("format_version", 1)
    schema_version = record.get("schema_version", 1)
    if format_version < 3 and schema_version < 2:
        state.base["legacy_count"] += 1
        try:
            safe_log_file(state.root, path_value, must_exist=False)
        except AgentLogIntegrityError as exc:
            state.base["findings"].append(
                {
                    "code": "agent_log_legacy_path_unsafe",
                    "path": path_value,
                    "detail": str(exc),
                }
            )
        return
    _inspect_integrity_bound_record(state, record, path_value)


def _inspect_records(
    state: InspectionState, records: list[dict[str, Any]]
) -> None:
    state.base["indexed_count"] = len(records)
    for line_no, record in enumerate(records, start=1):
        _inspect_record(state, record, line_no)


def _finalize_projection(state: InspectionState) -> list[Path]:
    markdown_rel = {
        path.relative_to(state.root).as_posix() for path in state.markdown
    }
    if not state.sealed_inventory_paths.issubset(markdown_rel):
        state.base["tampered_count"] += 1
        state.base["findings"].append(
            {"code": "agent_log_migration_inventory_path_missing"}
        )
    if not state.sealed_nonconsumable_paths.issubset(
        state.sealed_inventory_paths
    ):
        state.base["tampered_count"] += 1
        state.base["findings"].append(
            {"code": "agent_log_migration_exclusion_unsealed"}
        )
    orphans = sorted(
        markdown_rel - state.referenced - state.sealed_nonconsumable_paths
    )
    state.base["orphan_count"] = len(orphans)
    state.base["orphan_paths"] = orphans[:100]
    for path_value in state.base["orphan_paths"]:
        state.base["findings"].append(
            {"code": "agent_log_orphan_markdown", "path": path_value}
        )
    if (
        state.base["duplicate_count"]
        or state.base["tampered_count"]
        or state.base["missing_count"]
        or state.base["orphan_count"]
    ):
        state.base["status"] = "invalid"
    elif state.base["legacy_count"]:
        state.base["status"] = "legacy_unverified"
    else:
        state.base["status"] = "valid"
    return [
        path
        for path in state.markdown
        if path.relative_to(state.root).as_posix()
        not in state.sealed_nonconsumable_paths
    ]


def inspect_agent_log_store(
    root_raw: str | Path,
) -> tuple[dict[str, Any], list[Path], list[Path]]:
    try:
        root = workspace_root(root_raw)
    except AgentLogIntegrityError as exc:
        return _unsafe_workspace_result(str(exc))
    log_root = root / ".agent_log"
    base = _base_projection(root, log_root)
    if not base["directory"]["exists"]:
        return base, [], []
    try:
        log_root = ensure_log_root(root, create=False)
        markdown, jsonl = _walk_store(log_root)
    except (AgentLogIntegrityError, OSError) as exc:
        base["status"] = "unsafe"
        base["findings"].append(
            {"code": "agent_log_store_unsafe", "detail": str(exc)}
        )
        return base, [], []
    index_path = log_root / "index.jsonl"
    if index_path.is_symlink():
        base["status"] = "unsafe"
        base["findings"].append(
            {"code": "agent_log_index_unsafe", "path": ".agent_log/index.jsonl"}
        )
        return base, [], []
    try:
        payload = index_path.read_bytes() if index_path.is_file() else b""
        records = _parse_index(payload, index_path)
        migration = _verify_committed_migration(root, payload, records)
    except (AgentLogIntegrityError, OSError) as exc:
        base["status"] = "invalid"
        base["findings"].append(
            {"code": "agent_log_index_invalid", "detail": str(exc)}
        )
        return base, markdown, jsonl
    state = InspectionState(root=root, base=base, markdown=markdown, jsonl=jsonl)
    _apply_migration_projection(state, migration)
    _inspect_records(state, records)
    consumable_markdown = _finalize_projection(state)
    return state.base, consumable_markdown, state.jsonl
