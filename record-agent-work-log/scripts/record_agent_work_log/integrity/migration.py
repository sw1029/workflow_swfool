"""Committed migration-boundary integrity verification."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import stat
from typing import Any

from .contracts import MIGRATION_KIND, SHA256_RE, AgentLogIntegrityError
from .core import safe_log_file, sha256_bytes, sha256_file
from .index import _parse_index


@dataclass(frozen=True)
class MigrationBoundary:
    marker: dict[str, Any]
    prefix_size: int
    prefix_sha: str


def _safe_migration_sidecar(root: Path, value: Any) -> Path:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise AgentLogIntegrityError("migration sidecar path is missing")
    relative = Path(value)
    if (
        relative.is_absolute()
        or value != relative.as_posix()
        or any(part in {"", ".", ".."} for part in relative.parts)
        or len(relative.parts) < 3
        or relative.parts[:2] != (".agent_log", "migrations")
    ):
        raise AgentLogIntegrityError(f"unsafe migration sidecar path: {value!r}")
    current = root
    for part in relative.parts:
        current /= part
        if not (current.exists() or current.is_symlink()):
            raise AgentLogIntegrityError(f"migration sidecar is missing: {value}")
        mode = current.lstat().st_mode
        if stat.S_ISLNK(mode):
            raise AgentLogIntegrityError(
                f"migration sidecar path contains a symlink: {value}"
            )
    candidate = root / relative
    if not stat.S_ISREG(candidate.lstat().st_mode):
        raise AgentLogIntegrityError(
            f"migration sidecar is not a regular file: {value}"
        )
    try:
        candidate.resolve(strict=True).relative_to(root)
    except (OSError, ValueError) as exc:
        raise AgentLogIntegrityError(
            f"migration sidecar escapes the workspace: {value}"
        ) from exc
    return candidate


def _read_json_object(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    payload = path.read_bytes()
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AgentLogIntegrityError(f"{label} is invalid: {exc}") from exc
    if not isinstance(value, dict):
        raise AgentLogIntegrityError(f"{label} must be a JSON object")
    return value, payload


def _load_marker(
    root: Path, records: list[dict[str, Any]]
) -> dict[str, Any] | None:
    marker_path = root / ".agent_log" / "migrations" / "active.json"
    has_migration_rows = any(
        isinstance(record.get("migration_id"), str)
        or record.get("content_id_scheme") is not None
        for record in records
    )
    if not (marker_path.exists() or marker_path.is_symlink()):
        if has_migration_rows:
            raise AgentLogIntegrityError(
                "migration-derived agent-log rows require a committed marker"
            )
        return None
    marker_relative = marker_path.relative_to(root).as_posix()
    safe_marker_path = _safe_migration_sidecar(root, marker_relative)
    marker, _ = _read_json_object(
        safe_marker_path, "agent-log migration marker"
    )
    if (
        marker.get("kind") != "agent_log_migration_commit_marker"
        or marker.get("transaction_status") != "committed"
        or not isinstance(marker.get("migration_id"), str)
        or not marker["migration_id"]
    ):
        raise AgentLogIntegrityError(
            "agent-log migration marker contract mismatch"
        )
    return marker


def _verify_commit_boundary(
    root: Path,
    index_payload: bytes,
    records: list[dict[str, Any]],
    marker: dict[str, Any],
) -> MigrationBoundary:
    prefix_size = marker.get("after_index_size")
    prefix_sha = marker.get("after_index_sha256")
    if (
        isinstance(prefix_size, bool)
        or not isinstance(prefix_size, int)
        or prefix_size < 0
        or prefix_size > len(index_payload)
        or not isinstance(prefix_sha, str)
        or not SHA256_RE.fullmatch(prefix_sha)
        or sha256_bytes(index_payload[:prefix_size]) != prefix_sha
    ):
        raise AgentLogIntegrityError(
            "agent-log migration commit-boundary hash mismatch"
        )
    prefix_payload = index_payload[:prefix_size]
    if prefix_payload and not prefix_payload.endswith(b"\n"):
        raise AgentLogIntegrityError(
            "agent-log migration commit boundary splits a JSONL row"
        )
    prefix_records = _parse_index(
        prefix_payload, root / ".agent_log" / "index.jsonl"
    )
    for record in prefix_records:
        migration_id = record.get("migration_id")
        if migration_id is not None and migration_id != marker["migration_id"]:
            raise AgentLogIntegrityError(
                "migration-derived row identity mismatches the marker"
            )
    tail_records = records[len(prefix_records) :]
    if any(
        record.get("migration_id") is not None
        or record.get("content_id_scheme") is not None
        for record in tail_records
    ):
        raise AgentLogIntegrityError(
            "migration-derived rows appear after the sealed commit boundary"
        )
    return MigrationBoundary(marker, prefix_size, prefix_sha)


def _verify_receipt(
    root: Path, boundary: MigrationBoundary
) -> tuple[Path, dict[str, Any]]:
    marker = boundary.marker
    receipt_path = _safe_migration_sidecar(root, marker.get("receipt_ref"))
    receipt, receipt_payload = _read_json_object(
        receipt_path, "agent-log migration receipt"
    )
    if sha256_bytes(receipt_payload) != marker.get("receipt_sha256"):
        raise AgentLogIntegrityError("agent-log migration receipt hash mismatch")
    if (
        receipt.get("kind") != MIGRATION_KIND
        or receipt.get("transaction_status") != "committed"
        or receipt.get("migration_id") != marker["migration_id"]
        or receipt.get("after_index_sha256") != boundary.prefix_sha
        or receipt.get("after_index_size") != boundary.prefix_size
        or receipt.get("plan_sha256") != marker.get("plan_sha256")
        or receipt.get("historical_claims_upgraded") is not False
    ):
        raise AgentLogIntegrityError(
            "agent-log migration receipt binding mismatch"
        )
    return receipt_path, receipt


def _verify_journal(root: Path, boundary: MigrationBoundary) -> None:
    marker = boundary.marker
    journal_path = _safe_migration_sidecar(root, marker.get("journal_ref"))
    journal, journal_payload = _read_json_object(
        journal_path, "agent-log migration journal"
    )
    if sha256_bytes(journal_payload) != marker.get("journal_sha256"):
        raise AgentLogIntegrityError("agent-log migration journal hash mismatch")
    if (
        journal.get("kind") != "agent_log_migration_journal"
        or journal.get("phase") != "committed"
        or journal.get("migration_id") != marker["migration_id"]
        or journal.get("plan_sha256") != marker.get("plan_sha256")
        or journal.get("after_index_sha256") != boundary.prefix_sha
        or journal.get("after_index_size") != boundary.prefix_size
        or journal.get("receipt_ref") != marker.get("receipt_ref")
        or journal.get("receipt_sha256") != marker.get("receipt_sha256")
    ):
        raise AgentLogIntegrityError(
            "agent-log migration committed journal binding mismatch"
        )


def _verify_receipt_sidecars(
    root: Path, receipt: dict[str, Any]
) -> dict[str, Path]:
    sidecars: dict[str, Path] = {}
    for ref_field, sha_field in (
        ("source_snapshot_ref", "source_snapshot_sha256"),
        ("plan_ref", "plan_sha256"),
        ("status_map_ref", "status_map_sha256"),
        ("resolution_manifest_ref", "resolution_manifest_sha256"),
    ):
        sidecar = _safe_migration_sidecar(root, receipt.get(ref_field))
        sidecars[ref_field] = sidecar
        expected = receipt.get(sha_field)
        if not isinstance(expected, str) or not SHA256_RE.fullmatch(expected):
            raise AgentLogIntegrityError(
                f"agent-log migration receipt lacks {sha_field}"
            )
        if sha256_file(sidecar) != expected:
            raise AgentLogIntegrityError(
                f"agent-log migration sidecar hash mismatch: {ref_field}"
            )
    return sidecars


def _verify_inventory(
    root: Path, inventory: list[Any]
) -> dict[str, dict[str, Any]]:
    inventory_by_path: dict[str, dict[str, Any]] = {}
    for entry in inventory:
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
            raise AgentLogIntegrityError(
                "agent-log migration inventory entry is malformed"
            )
        path_value = entry["path"]
        if path_value in inventory_by_path:
            raise AgentLogIntegrityError(
                "agent-log migration inventory path is duplicated"
            )
        body_path = safe_log_file(root, path_value, must_exist=True)
        if entry.get("body_sha256") != sha256_file(body_path):
            raise AgentLogIntegrityError(
                "agent-log migration inventory body hash mismatch"
            )
        inventory_by_path[path_value] = entry
    return inventory_by_path


def _verify_resolutions(
    resolutions: list[Any], inventory_by_path: dict[str, dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    resolution_by_path: dict[str, dict[str, Any]] = {}
    allowed_dispositions = {
        "bind_existing_body",
        "bind_as_legacy_import",
        "retain_as_alias_evidence",
        "quarantine_nonlog_body",
    }
    for entry in resolutions:
        if (
            not isinstance(entry, dict)
            or not isinstance(entry.get("path"), str)
            or entry.get("disposition") not in allowed_dispositions
        ):
            raise AgentLogIntegrityError(
                "agent-log migration Markdown resolution is malformed"
            )
        path_value = entry["path"]
        if path_value in resolution_by_path or path_value not in inventory_by_path:
            raise AgentLogIntegrityError(
                "agent-log migration Markdown resolution accounting mismatch"
            )
        if entry.get("body_sha256") != inventory_by_path[path_value].get(
            "body_sha256"
        ):
            raise AgentLogIntegrityError(
                "agent-log migration Markdown resolution hash mismatch"
            )
        resolution_by_path[path_value] = entry
    if set(resolution_by_path) != set(inventory_by_path):
        raise AgentLogIntegrityError(
            "agent-log migration does not classify every source Markdown path"
        )
    return resolution_by_path


def _verify_manifest(
    root: Path,
    marker: dict[str, Any],
    manifest_path: Path,
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    manifest, _ = _read_json_object(
        manifest_path, "agent-log migration resolution manifest"
    )
    if manifest.get("migration_id") != marker["migration_id"]:
        raise AgentLogIntegrityError(
            "agent-log migration manifest identity mismatch"
        )
    inventory = manifest.get("markdown_inventory")
    resolutions = manifest.get("markdown_resolutions")
    if not isinstance(inventory, list) or not isinstance(resolutions, list):
        raise AgentLogIntegrityError(
            "agent-log migration manifest lacks Markdown accounting"
        )
    inventory_by_path = _verify_inventory(root, inventory)
    resolution_by_path = _verify_resolutions(resolutions, inventory_by_path)
    return inventory_by_path, resolution_by_path


def _verify_committed_migration(
    root: Path, index_payload: bytes, records: list[dict[str, Any]]
) -> dict[str, Any] | None:
    marker = _load_marker(root, records)
    if marker is None:
        return None
    boundary = _verify_commit_boundary(root, index_payload, records, marker)
    receipt_path, receipt = _verify_receipt(root, boundary)
    _verify_journal(root, boundary)
    sidecars = _verify_receipt_sidecars(root, receipt)
    inventory_by_path, resolution_by_path = _verify_manifest(
        root, marker, sidecars["resolution_manifest_ref"]
    )
    excluded = sorted(
        path
        for path, entry in resolution_by_path.items()
        if entry["disposition"]
        in {"retain_as_alias_evidence", "quarantine_nonlog_body"}
    )
    return {
        "migration_id": marker["migration_id"],
        "commit_boundary_size": boundary.prefix_size,
        "commit_boundary_sha256": boundary.prefix_sha,
        "receipt_path": receipt_path.relative_to(root).as_posix(),
        "sealed_nonconsumable_count": len(excluded),
        "_sealed_inventory_paths": sorted(inventory_by_path),
        "_sealed_nonconsumable_paths": excluded,
    }
