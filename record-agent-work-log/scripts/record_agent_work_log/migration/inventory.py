"""Read-only source-index and Markdown inventory."""

from __future__ import annotations

from collections import Counter
import json
import os
from pathlib import Path
from typing import Any

from ..integrity import safe_log_file, sha256_bytes, workspace_root
from .contracts import MISSING_STATUS_KEY, PLAN_SCHEMA_VERSION, TOOL_VERSION, MigrationError
from .storage import _canonical_json_bytes, _read_index, _root_identity, _sha256_path


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
