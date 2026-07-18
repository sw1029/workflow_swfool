"""Safe bounded storage helpers for durable selection decisions."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import stat
from typing import Any


BINDING_KEYS = {"ref", "sha256"}
SHA256 = re.compile(r"[0-9a-f]{64}")
MAX_ARTIFACT_BYTES = 64 * 1024 * 1024


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
    root: Path, binding: dict[str, str], label: str
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
        mode = path.lstat().st_mode
    except OSError as exc:
        raise ValueError(f"{label} does not exist") from exc
    if not stat.S_ISREG(mode) or path.resolve(strict=True) != path:
        raise ValueError(f"{label} must be a workspace-local regular file")
    if path.stat().st_size > MAX_ARTIFACT_BYTES:
        raise ValueError(f"{label} exceeds the artifact size limit")
    with path.open("rb") as handle:
        body = handle.read(MAX_ARTIFACT_BYTES + 1)
    if len(body) > MAX_ARTIFACT_BYTES:
        raise ValueError(f"{label} exceeds the artifact size limit")
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
