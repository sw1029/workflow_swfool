"""Journal, receipt, marker, and immutable sidecar publication."""

from __future__ import annotations

import json
import os
from pathlib import Path
import stat
from typing import Any

from ..integrity import sha256_bytes
from .contracts import (
    JOURNAL_SCHEMA_VERSION,
    MARKER_SCHEMA_VERSION,
    MIGRATION_KIND,
    RECEIPT_SCHEMA_VERSION,
    TOOL_VERSION,
    MigrationError,
)
from .storage import (
    _canonical_json_bytes,
    _safe_migration_path,
    _sha256_path,
    _strict_fsync_directory,
    _strict_publish_new,
    _utc_now,
)


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
