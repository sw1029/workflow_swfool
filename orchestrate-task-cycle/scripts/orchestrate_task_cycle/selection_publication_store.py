"""Bounded durable storage primitives for selection publication."""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile
from typing import Any, Iterator


try:
    import fcntl
except ImportError:  # pragma: no cover - POSIX is the production path.
    fcntl = None  # type: ignore[assignment]


TRANSACTION_ID = re.compile(r"^selection-[0-9a-f]{64}$")


def _canonical_json(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def _display_json(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str | None:
    if not path.is_file() or path.is_symlink():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _fsync_dir(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_value = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_value)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        _fsync_dir(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


def _write_once(path: Path, payload: bytes, label: str) -> str:
    digest = _sha256_bytes(payload)
    if path.exists() or path.is_symlink():
        if path.is_symlink() or not path.is_file() or _sha256_file(path) != digest:
            raise ValueError(f"{label} conflicts with immutable transaction evidence")
        return digest
    _atomic_write(path, payload)
    if _sha256_file(path) != digest:
        raise ValueError(f"{label} failed post-write verification")
    return digest


def _safe_directory(path: Path, label: str) -> None:
    if path.is_symlink():
        raise ValueError(f"{label} cannot be a symlink")
    if path.exists() and not path.is_dir():
        raise ValueError(f"{label} must be a directory")


def _safe_regular_file(path: Path, label: str) -> None:
    if path.is_symlink():
        raise ValueError(f"{label} cannot be a symlink")
    if path.exists() and not stat.S_ISREG(path.lstat().st_mode):
        raise ValueError(f"{label} must be a regular file or absent")


def _store_root(root: Path) -> Path:
    root = root.resolve(strict=True)
    task_root = root / ".task"
    store = task_root / "selection_publication"
    _safe_directory(task_root, "selection-publication .task root")
    _safe_directory(store, "selection-publication store root")
    try:
        store.resolve(strict=False).relative_to(root)
    except ValueError as exc:
        raise ValueError("selection-publication store escapes the workspace") from exc
    return store


def _safe_store_directory(root: Path, relative_parts: tuple[str, ...]) -> Path:
    current = _store_root(root)
    for part in relative_parts:
        current /= part
        _safe_directory(current, "selection-publication store component")
    return current


def _prepare_path(root: Path, transaction_id: str) -> Path:
    if not TRANSACTION_ID.fullmatch(transaction_id):
        raise ValueError("invalid selection-publication transaction id")
    directory = _safe_store_directory(root, ("transactions", transaction_id))
    path = directory / "prepare.json"
    _safe_regular_file(path, "selection-publication prepare journal")
    return path


def _transactions_root(root: Path) -> Path:
    return _safe_store_directory(root, ("transactions",))


def _receipt_path(root: Path, transaction_id: str) -> Path:
    if not TRANSACTION_ID.fullmatch(transaction_id):
        raise ValueError("invalid selection-publication transaction id")
    directory = _safe_store_directory(root, ("receipts",))
    path = directory / f"{transaction_id}.json"
    _safe_regular_file(path, "selection-publication receipt")
    return path


def _receipts_root(root: Path) -> Path:
    return _safe_store_directory(root, ("receipts",))


def _create_store_directories(root: Path) -> Path:
    store = _store_root(root)
    task_root = root / ".task"
    if not task_root.exists():
        task_root.mkdir()
    _safe_directory(task_root, "selection-publication .task root")
    if not store.exists():
        store.mkdir()
    _safe_directory(store, "selection-publication store root")
    return store


@contextlib.contextmanager
def _lock(root: Path) -> Iterator[None]:
    store = _create_store_directories(root)
    path = store / "publication.lock"
    _safe_regular_file(path, "selection-publication lock")
    with path.open("a+b") as handle:
        if fcntl is not None:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            if fcntl is not None:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


__all__ = (
    "TRANSACTION_ID",
    "_atomic_write",
    "_canonical_json",
    "_display_json",
    "_lock",
    "_prepare_path",
    "_receipts_root",
    "_receipt_path",
    "_sha256_bytes",
    "_sha256_file",
    "_store_root",
    "_transactions_root",
    "_write_once",
)
