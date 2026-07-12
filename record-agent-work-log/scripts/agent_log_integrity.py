"""Shared workspace-local integrity checks for ``.agent_log`` stores."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import stat
from typing import Any


LOG_FORMAT_VERSION = 3
LOG_SCHEMA_VERSION = 2
LOG_STATUSES = ("blocked", "completed", "failed", "informational", "partial")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
CONTENT_ID_RE = re.compile(r"^log-content-[0-9a-f]{32}$")
RECORD_ID_RE = re.compile(r"^log-record-[0-9a-f]{32}$")
MIGRATION_KIND = "agent_log_legacy_migration"


class AgentLogIntegrityError(ValueError):
    """Raised when an agent-log store cannot be safely consumed or extended."""


def canonical_record_bytes(record: dict[str, Any]) -> bytes:
    payload = {key: value for key, value in record.items() if key != "record_id"}
    return (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def expected_record_id(record: dict[str, Any]) -> str:
    return (
        "log-record-" + hashlib.sha256(canonical_record_bytes(record)).hexdigest()[:32]
    )


def content_id_for(body_sha256: str) -> str:
    return f"log-content-{body_sha256[:32]}"


def expected_content_id(record: dict[str, Any]) -> str:
    body_sha256 = record.get("body_sha256")
    if not isinstance(body_sha256, str):
        return ""
    if record.get("content_id_scheme") is not None:
        return ""
    return content_id_for(body_sha256)


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def workspace_root(raw: str | Path) -> Path:
    lexical = Path(raw).expanduser().absolute()
    if lexical.is_symlink():
        raise AgentLogIntegrityError("workspace root must not be a symlink")
    try:
        root = lexical.resolve(strict=True)
    except OSError as exc:
        raise AgentLogIntegrityError(f"workspace root is unavailable: {exc}") from exc
    if not root.is_dir():
        raise AgentLogIntegrityError("workspace root must be a directory")
    return root


def _safe_relative_path(value: Any) -> Path | None:
    if not isinstance(value, str) or not value or "\x00" in value:
        return None
    path = Path(value)
    if (
        path.is_absolute()
        or value != path.as_posix()
        or any(part in {"", ".", ".."} for part in path.parts)
        or len(path.parts) < 3
        or path.parts[0] != ".agent_log"
        or path.suffix.lower() != ".md"
    ):
        return None
    return path


def _directory_projection(root: Path, log_root: Path) -> dict[str, Any]:
    projection: dict[str, Any] = {
        "path": ".agent_log",
        "exists": log_root.exists() or log_root.is_symlink(),
        "is_file": False,
        "is_dir": False,
        "is_symlink": log_root.is_symlink(),
    }
    if not projection["exists"] or projection["is_symlink"]:
        return projection
    try:
        mode = log_root.lstat().st_mode
        projection["is_file"] = stat.S_ISREG(mode)
        projection["is_dir"] = stat.S_ISDIR(mode)
        projection["size_bytes"] = log_root.lstat().st_size
    except OSError:
        pass
    return projection


def ensure_log_root(root: Path, *, create: bool) -> Path:
    root = workspace_root(root)
    log_root = root / ".agent_log"
    if log_root.exists() or log_root.is_symlink():
        mode = log_root.lstat().st_mode
        if stat.S_ISLNK(mode):
            raise AgentLogIntegrityError(".agent_log must not be a symlink")
        if not stat.S_ISDIR(mode):
            raise AgentLogIntegrityError(
                ".agent_log must be a workspace-local directory"
            )
    elif create:
        try:
            log_root.mkdir(mode=0o700)
        except FileExistsError:
            mode = log_root.lstat().st_mode
            if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
                raise AgentLogIntegrityError(
                    ".agent_log must be a workspace-local non-symlink directory"
                )
    return log_root


def ensure_safe_directory(root: Path, relative: Path, *, create: bool) -> Path:
    root = workspace_root(root)
    if relative.is_absolute() or any(
        part in {"", ".", ".."} for part in relative.parts
    ):
        raise AgentLogIntegrityError(
            "agent-log directory path must stay inside the workspace"
        )
    current = root
    for part in relative.parts:
        current /= part
        if current.exists() or current.is_symlink():
            mode = current.lstat().st_mode
            if stat.S_ISLNK(mode):
                raise AgentLogIntegrityError(
                    f"agent-log path component is a symlink: {current}"
                )
            if not stat.S_ISDIR(mode):
                raise AgentLogIntegrityError(
                    f"agent-log path component is not a directory: {current}"
                )
        elif create:
            try:
                current.mkdir(mode=0o700)
            except FileExistsError:
                mode = current.lstat().st_mode
                if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
                    raise AgentLogIntegrityError(
                        f"agent-log path component is not a safe directory: {current}"
                    )
        else:
            break
    try:
        current.resolve(strict=False).relative_to(root)
    except ValueError as exc:
        raise AgentLogIntegrityError(
            "agent-log directory escapes the workspace"
        ) from exc
    return current


def safe_log_file(root: Path, value: Any, *, must_exist: bool) -> Path:
    root = workspace_root(root)
    relative = _safe_relative_path(value)
    if relative is None:
        raise AgentLogIntegrityError(f"unsafe agent-log Markdown path: {value!r}")
    candidate = root / relative
    current = root
    for part in relative.parts:
        current /= part
        if not (current.exists() or current.is_symlink()):
            if must_exist:
                raise AgentLogIntegrityError(
                    f"indexed agent-log Markdown is missing: {value}"
                )
            break
        mode = current.lstat().st_mode
        if stat.S_ISLNK(mode):
            raise AgentLogIntegrityError(
                f"agent-log path component is a symlink: {value}"
            )
    try:
        candidate.resolve(strict=must_exist).relative_to(root)
    except (OSError, ValueError) as exc:
        raise AgentLogIntegrityError(
            f"agent-log path escapes the workspace: {value}"
        ) from exc
    if must_exist and not stat.S_ISREG(candidate.lstat().st_mode):
        raise AgentLogIntegrityError(
            f"indexed agent-log path is not a regular file: {value}"
        )
    return candidate


def _parse_index(payload: bytes, path: Path) -> list[dict[str, Any]]:
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise AgentLogIntegrityError(
            f"Malformed agent-log index {path}: invalid UTF-8"
        ) from exc
    records: list[dict[str, Any]] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise AgentLogIntegrityError(
                f"Malformed agent-log index {path} line {line_no}: {exc}"
            ) from exc
        if not isinstance(record, dict):
            raise AgentLogIntegrityError(
                f"Malformed agent-log index {path} line {line_no}: expected a JSON object"
            )
        for field in ("timestamp", "status", "path"):
            if not isinstance(record.get(field), str) or not record[field].strip():
                raise AgentLogIntegrityError(
                    f"Malformed agent-log index {path} line {line_no}: missing non-empty {field}"
                )
        if record["status"] not in LOG_STATUSES:
            raise AgentLogIntegrityError(
                f"Malformed agent-log index {path} line {line_no}: unsupported status {record['status']!r}"
            )
        for field, current in (
            ("format_version", LOG_FORMAT_VERSION),
            ("schema_version", LOG_SCHEMA_VERSION),
        ):
            value = record.get(field, 1)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise AgentLogIntegrityError(
                    f"Malformed agent-log index {path} line {line_no}: invalid {field}"
                )
            if value > current:
                raise AgentLogIntegrityError(
                    f"Unsupported agent-log {field} {value} in {path} line {line_no}"
                )
        if _safe_relative_path(record["path"]) is None:
            raise AgentLogIntegrityError(
                f"Malformed agent-log index {path} line {line_no}: unsafe path"
            )
        records.append(record)
    return records


def parse_index(payload: bytes, path: Path) -> list[dict[str, Any]]:
    return _parse_index(payload, path)


def _walk_store(log_root: Path) -> tuple[list[Path], list[Path]]:
    markdown: list[Path] = []
    jsonl: list[Path] = []
    pending = [log_root]
    while pending:
        directory = pending.pop()
        with os.scandir(directory) as entries:
            for entry in entries:
                path = Path(entry.path)
                if entry.is_symlink():
                    raise AgentLogIntegrityError(
                        f"agent-log path component is a symlink: {path}"
                    )
                if entry.is_dir(follow_symlinks=False):
                    pending.append(path)
                    continue
                if not entry.is_file(follow_symlinks=False):
                    raise AgentLogIntegrityError(
                        f"agent-log entry is not a regular file: {path}"
                    )
                if path.suffix.lower() == ".md":
                    markdown.append(path)
                elif path.suffix.lower() == ".jsonl":
                    jsonl.append(path)
    return sorted(markdown), sorted(jsonl)


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
            raise AgentLogIntegrityError(f"migration sidecar path contains a symlink: {value}")
    candidate = root / relative
    if not stat.S_ISREG(candidate.lstat().st_mode):
        raise AgentLogIntegrityError(f"migration sidecar is not a regular file: {value}")
    try:
        candidate.resolve(strict=True).relative_to(root)
    except (OSError, ValueError) as exc:
        raise AgentLogIntegrityError(f"migration sidecar escapes the workspace: {value}") from exc
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


def _verify_committed_migration(
    root: Path, index_payload: bytes, records: list[dict[str, Any]]
) -> dict[str, Any] | None:
    marker_path = root / ".agent_log" / "migrations" / "active.json"
    has_migration_rows = any(
        isinstance(record.get("migration_id"), str)
        or record.get("content_id_scheme") is not None
        for record in records
    )
    marker_exists = marker_path.exists() or marker_path.is_symlink()
    if not marker_exists:
        if has_migration_rows:
            raise AgentLogIntegrityError(
                "migration-derived agent-log rows require a committed marker"
            )
        return None
    marker_relative = marker_path.relative_to(root).as_posix()
    marker_path = _safe_migration_sidecar(root, marker_relative)
    marker, _ = _read_json_object(marker_path, "agent-log migration marker")
    if (
        marker.get("kind") != "agent_log_migration_commit_marker"
        or marker.get("transaction_status") != "committed"
        or not isinstance(marker.get("migration_id"), str)
        or not marker["migration_id"]
    ):
        raise AgentLogIntegrityError("agent-log migration marker contract mismatch")
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
        raise AgentLogIntegrityError("agent-log migration commit-boundary hash mismatch")
    prefix_payload = index_payload[:prefix_size]
    if prefix_payload and not prefix_payload.endswith(b"\n"):
        raise AgentLogIntegrityError("agent-log migration commit boundary splits a JSONL row")
    prefix_records = _parse_index(prefix_payload, root / ".agent_log" / "index.jsonl")
    for record in prefix_records:
        migration_id = record.get("migration_id")
        if migration_id is not None and migration_id != marker["migration_id"]:
            raise AgentLogIntegrityError("migration-derived row identity mismatches the marker")
    tail_records = records[len(prefix_records) :]
    if any(
        record.get("migration_id") is not None
        or record.get("content_id_scheme") is not None
        for record in tail_records
    ):
        raise AgentLogIntegrityError("migration-derived rows appear after the sealed commit boundary")

    receipt_path = _safe_migration_sidecar(root, marker.get("receipt_ref"))
    receipt, receipt_payload = _read_json_object(receipt_path, "agent-log migration receipt")
    if sha256_bytes(receipt_payload) != marker.get("receipt_sha256"):
        raise AgentLogIntegrityError("agent-log migration receipt hash mismatch")
    if (
        receipt.get("kind") != MIGRATION_KIND
        or receipt.get("transaction_status") != "committed"
        or receipt.get("migration_id") != marker["migration_id"]
        or receipt.get("after_index_sha256") != prefix_sha
        or receipt.get("after_index_size") != prefix_size
        or receipt.get("plan_sha256") != marker.get("plan_sha256")
        or receipt.get("historical_claims_upgraded") is not False
    ):
        raise AgentLogIntegrityError("agent-log migration receipt binding mismatch")
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
        or journal.get("after_index_sha256") != prefix_sha
        or journal.get("after_index_size") != prefix_size
        or journal.get("receipt_ref") != marker.get("receipt_ref")
        or journal.get("receipt_sha256") != marker.get("receipt_sha256")
    ):
        raise AgentLogIntegrityError("agent-log migration committed journal binding mismatch")
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
            raise AgentLogIntegrityError(f"agent-log migration receipt lacks {sha_field}")
        if sha256_file(sidecar) != expected:
            raise AgentLogIntegrityError(f"agent-log migration sidecar hash mismatch: {ref_field}")
    manifest, _ = _read_json_object(
        sidecars["resolution_manifest_ref"], "agent-log migration resolution manifest"
    )
    if manifest.get("migration_id") != marker["migration_id"]:
        raise AgentLogIntegrityError("agent-log migration manifest identity mismatch")
    inventory = manifest.get("markdown_inventory")
    resolutions = manifest.get("markdown_resolutions")
    if not isinstance(inventory, list) or not isinstance(resolutions, list):
        raise AgentLogIntegrityError("agent-log migration manifest lacks Markdown accounting")
    inventory_by_path: dict[str, dict[str, Any]] = {}
    for entry in inventory:
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
            raise AgentLogIntegrityError("agent-log migration inventory entry is malformed")
        path_value = entry["path"]
        if path_value in inventory_by_path:
            raise AgentLogIntegrityError("agent-log migration inventory path is duplicated")
        body_path = safe_log_file(root, path_value, must_exist=True)
        if entry.get("body_sha256") != sha256_file(body_path):
            raise AgentLogIntegrityError("agent-log migration inventory body hash mismatch")
        inventory_by_path[path_value] = entry
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
            raise AgentLogIntegrityError("agent-log migration Markdown resolution is malformed")
        path_value = entry["path"]
        if path_value in resolution_by_path or path_value not in inventory_by_path:
            raise AgentLogIntegrityError("agent-log migration Markdown resolution accounting mismatch")
        if entry.get("body_sha256") != inventory_by_path[path_value].get("body_sha256"):
            raise AgentLogIntegrityError("agent-log migration Markdown resolution hash mismatch")
        resolution_by_path[path_value] = entry
    if set(resolution_by_path) != set(inventory_by_path):
        raise AgentLogIntegrityError("agent-log migration does not classify every source Markdown path")
    excluded = sorted(
        path
        for path, entry in resolution_by_path.items()
        if entry["disposition"] in {"retain_as_alias_evidence", "quarantine_nonlog_body"}
    )
    return {
        "migration_id": marker["migration_id"],
        "commit_boundary_size": prefix_size,
        "commit_boundary_sha256": prefix_sha,
        "receipt_path": receipt_path.relative_to(root).as_posix(),
        "sealed_nonconsumable_count": len(excluded),
        "_sealed_inventory_paths": sorted(inventory_by_path),
        "_sealed_nonconsumable_paths": excluded,
    }


def inspect_agent_log_store(
    root_raw: str | Path,
) -> tuple[dict[str, Any], list[Path], list[Path]]:
    try:
        root = workspace_root(root_raw)
    except AgentLogIntegrityError as exc:
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
                    {"code": "agent_log_workspace_unsafe", "detail": str(exc)}
                ],
            },
            [],
            [],
        )
    log_root = root / ".agent_log"
    directory = _directory_projection(root, log_root)
    base: dict[str, Any] = {
        "status": "absent",
        "directory": directory,
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
    if not directory["exists"]:
        return base, [], []
    try:
        log_root = ensure_log_root(root, create=False)
        markdown, jsonl = _walk_store(log_root)
    except (AgentLogIntegrityError, OSError) as exc:
        base["status"] = "unsafe"
        base["findings"].append({"code": "agent_log_store_unsafe", "detail": str(exc)})
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
        base["findings"].append({"code": "agent_log_index_invalid", "detail": str(exc)})
        return base, markdown, jsonl

    sealed_inventory_paths: set[str] = set()
    sealed_nonconsumable_paths: set[str] = set()
    if migration is not None:
        sealed_inventory_paths = set(migration.pop("_sealed_inventory_paths", []))
        sealed_nonconsumable_paths = set(
            migration.pop("_sealed_nonconsumable_paths", [])
        )
        base["migration"] = migration

    base["indexed_count"] = len(records)
    referenced: set[str] = set()
    seen_log_ids: set[str] = set()
    seen_paths: set[str] = set()
    seen_content_ids: set[str] = set()
    seen_record_ids: set[str] = set()
    for line_no, record in enumerate(records, start=1):
        path_value = str(record["path"])
        referenced.add(path_value)
        for field, seen in (
            ("log_id", seen_log_ids),
            ("path", seen_paths),
            ("content_id", seen_content_ids),
            ("record_id", seen_record_ids),
        ):
            value = record.get(field)
            if not isinstance(value, str) or not value:
                continue
            if value in seen:
                base["duplicate_count"] += 1
                base["findings"].append(
                    {
                        "code": f"agent_log_duplicate_{field}",
                        "path": path_value,
                        "line": line_no,
                    }
                )
            seen.add(value)

        format_version = record.get("format_version", 1)
        schema_version = record.get("schema_version", 1)
        integrity_bound = format_version >= 3 or schema_version >= 2
        if not integrity_bound:
            base["legacy_count"] += 1
            try:
                safe_log_file(root, path_value, must_exist=False)
            except AgentLogIntegrityError as exc:
                base["findings"].append(
                    {
                        "code": "agent_log_legacy_path_unsafe",
                        "path": path_value,
                        "detail": str(exc),
                    }
                )
            continue

        required = {"log_id", "body_sha256", "content_id", "record_id"}
        if any(
            not isinstance(record.get(field), str) or not record[field]
            for field in required
        ):
            base["tampered_count"] += 1
            base["findings"].append(
                {"code": "agent_log_integrity_field_missing", "path": path_value}
            )
            continue
        body_sha = record["body_sha256"]
        if (
            not SHA256_RE.fullmatch(body_sha)
            or not CONTENT_ID_RE.fullmatch(record["content_id"])
            or record["content_id"] != expected_content_id(record)
            or not RECORD_ID_RE.fullmatch(record["record_id"])
            or record["record_id"] != expected_record_id(record)
        ):
            base["tampered_count"] += 1
            base["findings"].append(
                {"code": "agent_log_record_identity_mismatch", "path": path_value}
            )
            continue
        try:
            body_path = safe_log_file(root, path_value, must_exist=True)
        except AgentLogIntegrityError as exc:
            base["missing_count"] += 1
            base["findings"].append(
                {
                    "code": "agent_log_body_missing_or_unsafe",
                    "path": path_value,
                    "detail": str(exc),
                }
            )
            continue
        if sha256_file(body_path) != body_sha:
            base["tampered_count"] += 1
            base["findings"].append(
                {"code": "agent_log_body_hash_mismatch", "path": path_value}
            )
            continue
        base["verified_count"] += 1

    markdown_rel = {path.relative_to(root).as_posix() for path in markdown}
    if not sealed_inventory_paths.issubset(markdown_rel):
        base["tampered_count"] += 1
        base["findings"].append(
            {"code": "agent_log_migration_inventory_path_missing"}
        )
    if not sealed_nonconsumable_paths.issubset(sealed_inventory_paths):
        base["tampered_count"] += 1
        base["findings"].append(
            {"code": "agent_log_migration_exclusion_unsealed"}
        )
    orphans = sorted(markdown_rel - referenced - sealed_nonconsumable_paths)
    base["orphan_count"] = len(orphans)
    base["orphan_paths"] = orphans[:100]
    for path_value in base["orphan_paths"]:
        base["findings"].append(
            {"code": "agent_log_orphan_markdown", "path": path_value}
        )

    if (
        base["duplicate_count"]
        or base["tampered_count"]
        or base["missing_count"]
        or base["orphan_count"]
    ):
        base["status"] = "invalid"
    elif base["legacy_count"]:
        base["status"] = "legacy_unverified"
    else:
        base["status"] = "valid"
    consumable_markdown = [
        path
        for path in markdown
        if path.relative_to(root).as_posix() not in sealed_nonconsumable_paths
    ]
    return base, consumable_markdown, jsonl


def validate_store_for_append(
    root: Path, payload: bytes, index_path: Path
) -> list[dict[str, Any]]:
    records = _parse_index(payload, index_path)
    inspection, _, _ = inspect_agent_log_store(root)
    if inspection["status"] in {"unsafe", "invalid"}:
        findings = inspection.get("findings", [])
        if any(item.get("code") == "agent_log_body_hash_mismatch" for item in findings):
            raise AgentLogIntegrityError("agent-log body SHA-256 mismatch")
        duplicate = next(
            (
                item
                for item in findings
                if str(item.get("code", "")).startswith("agent_log_duplicate_")
            ),
            None,
        )
        if duplicate:
            field = str(duplicate["code"]).removeprefix("agent_log_duplicate_")
            raise AgentLogIntegrityError(f"duplicate {field} in agent-log index")
        if inspection.get("orphan_count"):
            raise AgentLogIntegrityError("orphan agent-log Markdown is not indexed")
        detail = (
            findings[0].get("detail")
            if findings
            else "agent-log integrity validation failed"
        )
        raise AgentLogIntegrityError(str(detail))
    return records
