"""Forward recovery and independent receipt consumption checks."""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any

from ..integrity import inspect_agent_log_store, sha256_bytes, validate_store_for_append, workspace_root
from ..write import log_lock
from .contracts import MIGRATION_KIND, RECEIPT_SCHEMA_VERSION, MigrationError
from .publication import _active_marker, _current_prefix_matches, _marker_for, _receipt_from_journal
from .storage import (
    _canonical_json_bytes,
    _index_path,
    _read_index,
    _root_identity,
    _safe_migration_path,
    _sha256_path,
    _strict_atomic_replace,
    _utc_now,
)


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
