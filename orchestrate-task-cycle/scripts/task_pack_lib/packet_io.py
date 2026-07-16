"""Packet loading, evidence verification, and atomic persistence."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

from .contracts import SHA256_PATTERN, VERDICT_AXES, _CONTENT_ADDRESSED_WRITE_STATE
from .storage import (
    ContentAddressedWriteTransaction,
    bounded_workspace_file,
    now_iso,
    rel_path,
    sha256_bytes,
    sha256_file,
)

def require_file_digest(path: Path, expected: Any, label: str) -> str:
    match = SHA256_PATTERN.fullmatch(str(expected or "").strip().lower())
    if not match:
        raise SystemExit(f"{label} requires a full lowercase SHA-256 digest.")
    expected_digest = match.group(1)
    observed = sha256_file(path)
    if observed != expected_digest:
        raise SystemExit(f"{label} SHA-256 does not match the referenced file.")
    return observed


def packet_field(packet: dict[str, Any], key: str) -> Any:
    payload = packet.get("result")
    if isinstance(payload, dict) and key in payload:
        return payload.get(key)
    return packet.get(key)


def normalized_string_list(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise SystemExit(f"{label} must be a non-empty JSON list of workspace-relative files.")
    result: list[str] = []
    for item in value:
        normalized = str(item or "").strip()
        if not normalized:
            raise SystemExit(f"{label} cannot contain empty values.")
        result.append(normalized)
    return result


def verify_evidence_files(root: Path, values: Any, label: str) -> list[str]:
    normalized = normalized_string_list(values, label)
    verified: list[str] = []
    for value in normalized:
        verified.append(rel_path(root, bounded_workspace_file(root, value, label)))
    return verified


def load_bound_packet(root: Path, value: Any, digest: Any, label: str) -> tuple[Path, dict[str, Any], str]:
    path = bounded_workspace_file(root, value, label)
    observed_digest = require_file_digest(path, digest, label)
    try:
        packet = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SystemExit(f"{label} is not readable JSON: {exc}") from exc
    if not isinstance(packet, dict):
        raise SystemExit(f"{label} must contain a JSON object.")
    return path, packet, observed_digest


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Cannot load task pack {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise SystemExit(f"Task pack must be a JSON object: {path}")
    return value


def load_plan(value: str | None) -> dict[str, Any]:
    if not value or value == "-":
        raw = sys.stdin.read()
        plan = json.loads(raw) if raw.strip() else {}
    else:
        stripped = value.strip()
        if stripped.startswith("{"):
            plan = json.loads(stripped)
        else:
            path = Path(stripped)
            plan = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(plan, dict):
        raise SystemExit("Mutation plan must be a JSON object.")
    return plan


def truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "passed", "pass", "met", "ok"}
    return bool(value)


def non_empty(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def verdict_axis_status(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("status") or value.get("verdict") or "").strip().lower()
    return str(value or "").strip().lower()


def preserve_verdict_axes(
    target: dict[str, Any],
    source: dict[str, Any],
    *,
    require_current: bool,
) -> None:
    raw_version = source.get("verdict_contract_version")
    try:
        version = int(raw_version) if raw_version is not None else None
    except (TypeError, ValueError):
        version = None
    supplied = {axis: source.get(axis) for axis in VERDICT_AXES}
    if require_current and version != 1:
        raise SystemExit("Current pack consumption requires verdict_contract_version=1 and all six verdict axes.")
    if version not in {None, 0, 1}:
        raise SystemExit("Verdict contract version must be 1, or explicit legacy version 0.")
    if any(value is not None for value in supplied.values()) and version is None:
        raise SystemExit("Verdict axes require an explicit verdict contract version.")
    if version == 1:
        missing = [axis for axis, value in supplied.items() if value is None]
        if missing:
            raise SystemExit(f"Current verdict contract is missing: {', '.join(missing)}")
        target["verdict_contract_version"] = 1
        target.update(supplied)
    elif version == 0:
        target["verdict_contract_version"] = 0


def scope_fidelity_records(item: dict[str, Any]) -> tuple[list[dict[str, Any]], bool]:
    value = item.get("scope_fidelity", item.get("scope_fidelity_records"))
    if value is None:
        return [], True
    if isinstance(value, dict):
        return [value], True
    if isinstance(value, list) and all(isinstance(record, dict) for record in value):
        return value, True
    return [], False


def write_json(path: Path, data: dict[str, Any]) -> None:
    data["updated_at"] = now_iso()
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_value = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_value)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        directory_descriptor = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    finally:
        if temporary.exists():
            temporary.unlink()


def write_bytes_atomic(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_value = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_value)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        directory_descriptor = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    finally:
        if temporary.exists():
            temporary.unlink()


def write_content_addressed_file(path: Path, payload: bytes, label: str) -> str:
    """Write immutable content once or verify the existing bytes."""

    digest = sha256_bytes(payload)
    if path.exists():
        if not path.is_file() or sha256_file(path) != digest:
            raise SystemExit(f"{label} conflicts with existing content-addressed evidence.")
        return digest
    created_directories: list[Path] = []
    parent = path.parent
    while not parent.exists():
        created_directories.append(parent)
        parent = parent.parent
    write_bytes_atomic(path, payload)
    transaction = getattr(_CONTENT_ADDRESSED_WRITE_STATE, "current", None)
    if isinstance(transaction, ContentAddressedWriteTransaction):
        transaction.register_created(path, created_directories)
    if sha256_file(path) != digest:
        raise SystemExit(f"{label} failed post-write SHA-256 verification.")
    return digest

