"""Bounded root-local file access for selection-tick discovery and hashing."""

from __future__ import annotations

import hashlib
from itertools import islice
import json
import stat
from collections.abc import Iterable
from pathlib import Path
from typing import Any


MAX_FILE_BYTES = 64 * 1024 * 1024


def safe_path(root: Path, raw: str, *, explicit: bool) -> tuple[Path, str]:
    """Resolve one regular root-local path without traversing a symlink."""

    candidate = Path(raw).expanduser()
    if ".." in candidate.parts:
        raise ValueError(f"parent traversal is not allowed in watch path: {raw}")
    if not candidate.is_absolute():
        candidate = root / candidate
    lexical = candidate.absolute()
    try:
        relative = lexical.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"watch path is outside repository root: {raw}") from exc
    current = root
    for part in relative.parts:
        current /= part
        if current.is_symlink():
            raise ValueError(f"symlink watch path is not allowed: {raw}")
    if not lexical.exists():
        if explicit:
            raise ValueError(f"explicit premise/watch path does not exist: {raw}")
        return lexical, relative.as_posix()
    resolved = lexical.resolve(strict=True)
    try:
        normalized = resolved.relative_to(root).as_posix()
    except ValueError as exc:
        raise ValueError(f"watch path resolves outside repository root: {raw}") from exc
    if not stat.S_ISREG(resolved.lstat().st_mode):
        raise ValueError(f"watch path must be a regular file: {raw}")
    if resolved.stat().st_size > MAX_FILE_BYTES:
        raise ValueError(f"watch path exceeds {MAX_FILE_BYTES} bytes: {raw}")
    return resolved, normalized


def sha256_and_size(path: Path) -> tuple[str, int]:
    """Hash and count the same bounded byte stream."""

    digest = hashlib.sha256()
    size_bytes = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            size_bytes += len(chunk)
            if size_bytes > MAX_FILE_BYTES:
                raise ValueError(f"watch file exceeds {MAX_FILE_BYTES} bytes")
            digest.update(chunk)
    return digest.hexdigest(), size_bytes


def sha256_file(path: Path) -> str:
    """Hash at most MAX_FILE_BYTES, including protection against concurrent growth."""

    return sha256_and_size(path)[0]


def bounded_paths(paths: Iterable[Path], limit: int, label: str) -> list[Path]:
    """Materialize and sort at most ``limit`` discovered paths."""

    result = list(islice(paths, limit + 1))
    if len(result) > limit:
        raise ValueError(f"{label} count exceeds {limit}")
    return sorted(result)


def safe_json_object(root: Path, raw: str, label: str) -> tuple[dict[str, Any], str]:
    """Read one bounded safe path as a UTF-8 JSON object."""

    path, normalized = safe_path(root, raw, explicit=True)
    try:
        with path.open("rb") as handle:
            body = handle.read(MAX_FILE_BYTES + 1)
        if len(body) > MAX_FILE_BYTES:
            raise ValueError(f"{label} exceeds {MAX_FILE_BYTES} bytes")
        value = json.loads(body.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is malformed: {normalized}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object: {normalized}")
    return value, normalized


__all__ = (
    "MAX_FILE_BYTES",
    "bounded_paths",
    "safe_json_object",
    "safe_path",
    "sha256_and_size",
    "sha256_file",
)
