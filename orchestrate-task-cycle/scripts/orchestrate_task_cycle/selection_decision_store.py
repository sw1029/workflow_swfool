"""Safe bounded storage helpers for durable selection decisions."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
from typing import Any


BINDING_KEYS = {"ref", "sha256"}
SHA256 = re.compile(r"[0-9a-f]{64}")
MAX_ARTIFACT_BYTES = 64 * 1024 * 1024


def _file_signature(value: os.stat_result) -> tuple[int, int, int, int, int, int]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


def canonical_bytes(value: object) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def closed_object(value: Any, keys: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise ValueError(f"{label} requires exact fields {sorted(keys)}")
    return value


def normalize_binding(value: Any, label: str) -> dict[str, str]:
    row = closed_object(value, BINDING_KEYS, label)
    ref = row.get("ref")
    digest = row.get("sha256")
    if (
        not isinstance(ref, str)
        or not isinstance(digest, str)
        or not ref
        or len(ref) > 512
        or "\\" in ref
        or "\x00" in ref
        or not SHA256.fullmatch(digest)
    ):
        raise ValueError(f"{label} requires a safe ref and lowercase SHA-256")
    pure = PurePosixPath(ref)
    if (
        pure.is_absolute()
        or pure.as_posix() != ref
        or any(part in {"", ".", ".."} for part in pure.parts)
    ):
        raise ValueError(f"{label} ref is unsafe")
    return {"ref": ref, "sha256": digest}


def read_bound_bytes(
    root: Path,
    binding: dict[str, str],
    label: str,
    *,
    max_bytes: int = MAX_ARTIFACT_BYTES,
) -> tuple[Path, bytes]:
    root = root.expanduser().resolve(strict=True)
    normalized = normalize_binding(binding, label)
    parts = PurePosixPath(normalized["ref"]).parts
    path = root.joinpath(*parts)
    current = root
    for part in parts:
        current /= part
        if current.is_symlink():
            raise ValueError(f"{label} cannot traverse a symlink")
    try:
        before = path.lstat()
    except OSError as exc:
        raise ValueError(f"{label} does not exist") from exc
    if not stat.S_ISREG(before.st_mode) or path.resolve(strict=True) != path:
        raise ValueError(f"{label} must be a workspace-local regular file")
    if max_bytes < 1 or max_bytes > MAX_ARTIFACT_BYTES:
        raise ValueError(f"{label} byte limit is invalid")
    if before.st_size > max_bytes:
        raise ValueError(f"{label} exceeds the artifact size limit")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise ValueError(f"{label} changed during acquisition") from exc
    try:
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or _file_signature(opened) != _file_signature(before)
            or opened.st_size > max_bytes
        ):
            raise ValueError(f"{label} changed during acquisition")
        chunks: list[bytes] = []
        total = 0
        while total <= max_bytes:
            chunk = os.read(descriptor, min(1024 * 1024, max_bytes + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
        if total > max_bytes:
            raise ValueError(f"{label} exceeds the artifact size limit")
        after = os.fstat(descriptor)
        try:
            current = path.lstat()
        except OSError as exc:
            raise ValueError(f"{label} changed during acquisition") from exc
        if (
            _file_signature(opened) != _file_signature(after)
            or _file_signature(after) != _file_signature(current)
        ):
            raise ValueError(f"{label} changed during acquisition")
        body = b"".join(chunks)
    finally:
        os.close(descriptor)
    if hashlib.sha256(body).hexdigest() != normalized["sha256"]:
        raise ValueError(f"{label} raw SHA-256 does not match persisted bytes")
    return path, body


def read_bound_json(
    root: Path, binding: dict[str, str], label: str
) -> tuple[Path, dict[str, Any]]:
    path, body = read_bound_bytes(root, binding, label)
    try:
        value = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} must contain one JSON object") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must contain one JSON object")
    return path, value


__all__ = (
    "BINDING_KEYS",
    "MAX_ARTIFACT_BYTES",
    "SHA256",
    "canonical_bytes",
    "canonical_sha256",
    "closed_object",
    "normalize_binding",
    "read_bound_bytes",
    "read_bound_json",
)
