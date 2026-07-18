"""Filesystem boundaries, canonical hashes, and atomic write transactions."""
from __future__ import annotations

import datetime as dt
import fcntl
import hashlib
import json
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from .contracts import _CONTENT_ADDRESSED_WRITE_STATE, _PACK_MUTATION_THREAD_LOCK
from .ordering import sorted_items

class ContentAddressedWriteTransaction:
    """Roll back newly-created evidence unless a canonical consumer was published."""

    def __init__(self) -> None:
        self.created_paths: list[Path] = []
        self.created_directories: list[Path] = []
        self.canonical_consumers: list[tuple[Path, str]] = []
        self.committed = False

    def register_created(self, path: Path, created_directories: list[Path] | None = None) -> None:
        self.created_paths.append(path)
        self.created_directories.extend(created_directories or [])

    def guard_canonical_consumer(self, path: Path, expected_canonical_sha256: str) -> None:
        self.canonical_consumers.append((path, expected_canonical_sha256))

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        if self.committed:
            return
        for path, expected_digest in self.canonical_consumers:
            if not path.is_file():
                continue
            try:
                body = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(body, dict) and canonical_pack_sha256(body) == expected_digest:
                return
        for path in reversed(self.created_paths):
            if path.is_file():
                path.unlink()
        for directory in sorted(set(self.created_directories), key=lambda value: len(value.parts), reverse=True):
            try:
                directory.rmdir()
            except OSError:
                pass


@contextmanager
def content_addressed_write_transaction():
    previous = getattr(_CONTENT_ADDRESSED_WRITE_STATE, "current", None)
    transaction = ContentAddressedWriteTransaction()
    _CONTENT_ADDRESSED_WRITE_STATE.current = transaction
    try:
        yield transaction
    finally:
        try:
            transaction.rollback()
        finally:
            _CONTENT_ADDRESSED_WRITE_STATE.current = previous


def guard_content_addressed_consumer(path: Path, expected_canonical_sha256: str) -> None:
    transaction = getattr(_CONTENT_ADDRESSED_WRITE_STATE, "current", None)
    if isinstance(transaction, ContentAddressedWriteTransaction):
        transaction.guard_canonical_consumer(path, expected_canonical_sha256)


def preserve_content_addressed_evidence() -> None:
    """Retain helper evidence once a durable forward-recovery journal exists."""

    transaction = getattr(_CONTENT_ADDRESSED_WRITE_STATE, "current", None)
    if isinstance(transaction, ContentAddressedWriteTransaction):
        transaction.commit()


def now_iso() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def rel_path(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def pack_dir(root: Path) -> Path:
    return root / ".task" / "task_pack"


def creation_snapshot_dir(root: Path) -> Path:
    return pack_dir(root) / "creation_snapshots"


def creation_receipt_dir(root: Path) -> Path:
    return pack_dir(root) / "creation_receipts"


@contextmanager
def pack_mutation_lock(root: Path, *, create: bool = True):
    """Serialize through the stable workspace-root inode without lock residue."""

    root = root.resolve()
    if not root.is_dir():
        raise SystemExit("Task-pack workspace root must be an existing directory.")
    directory = _require_within(pack_dir(root), root, "Task pack directory")
    with _PACK_MUTATION_THREAD_LOCK:
        descriptor = os.open(root, os.O_RDONLY)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            if create and not directory.is_dir():
                directory.mkdir(parents=True, exist_ok=True)
            yield
        finally:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)


def _require_within(path: Path, boundary: Path, label: str) -> Path:
    resolved = path.resolve(strict=False)
    resolved_boundary = boundary.resolve(strict=False)
    try:
        resolved.relative_to(resolved_boundary)
    except ValueError as exc:
        raise SystemExit(f"{label} must stay inside {resolved_boundary}, including through symlinks.") from exc
    return resolved


def resolve_pack_path(root: Path, value: str, *, must_exist: bool = True) -> Path:
    raw = Path(str(value).strip())
    if not str(value).strip() or raw.is_absolute():
        raise SystemExit("Task pack path must be a non-empty workspace-relative path.")
    directory = _require_within(pack_dir(root), root, "Task pack directory")
    path = _require_within(root / raw, directory, "Task pack path")
    if path.suffix != ".json":
        raise SystemExit("Task pack path must identify a .json file under .task/task_pack.")
    if must_exist and not path.is_file():
        raise SystemExit(f"Task pack does not exist: {rel_path(root, path)}")
    return path


def bounded_workspace_path(root: Path, value: Any, label: str) -> Path:
    raw_value = str(value or "").strip()
    raw = Path(raw_value)
    if not raw_value or raw.is_absolute():
        raise SystemExit(f"{label} must be a non-empty workspace-relative path.")
    return _require_within(root / raw, root, label)


def bounded_workspace_file(root: Path, value: Any, label: str) -> Path:
    path = bounded_workspace_path(root, value, label)
    if not path.is_file():
        raise SystemExit(f"{label} does not identify an existing file: {value}")
    return path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_optional_file(path: Path) -> str | None:
    if not path.exists():
        return None
    if not path.is_file():
        raise SystemExit(f"Expected a regular file for hashing: {path}")
    return sha256_file(path)


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def json_bytes(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def parse_rfc3339(value: Any, label: str) -> dt.datetime:
    raw = str(value or "").strip()
    if not raw:
        raise SystemExit(f"{label} is required.")
    try:
        parsed = dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SystemExit(f"{label} must be RFC3339-compatible.") from exc
    if parsed.tzinfo is None:
        raise SystemExit(f"{label} must include a timezone.")
    return parsed


def _without_volatile_pack_fields(value: Any) -> Any:
    """Return the deterministic lifecycle state used for pack preconditions."""

    if isinstance(value, list):
        return [_without_volatile_pack_fields(item) for item in value]
    if not isinstance(value, dict):
        return value
    ignored = {
        "created_at",
        "updated_at",
        "timestamp",
        "promoted_at",
        "completed_at",
    }
    return {
        str(key): _without_volatile_pack_fields(item)
        for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        if key not in ignored and key != "mutation_log"
    }


def canonical_pack_sha256(data: dict[str, Any]) -> str:
    """Hash canonical pack state without timestamps or append-only mutation history."""

    payload = json.dumps(
        _without_volatile_pack_fields(data),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def pack_snapshot(root: Path, path: Path, data: dict[str, Any]) -> dict[str, Any]:
    ordered = sorted_items(data)
    item_ids = [str(item.get("item_id")) for item in ordered if item.get("item_id")]
    return {
        "canonical_pack_ref": rel_path(root, path),
        "canonical_pack_sha256": canonical_pack_sha256(data),
        "pack_file_sha256": sha256_file(path) if path.is_file() else None,
        "item_ids": item_ids,
        "item_order": item_ids,
        "current_item": data.get("current_item_id"),
    }
