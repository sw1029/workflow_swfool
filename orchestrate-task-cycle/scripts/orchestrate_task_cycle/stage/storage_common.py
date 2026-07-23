"""Shared exact-file and immutable-CAS storage primitives."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any


SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")


def cas_write_receipt(
    size_bytes: int, mutation_performed: bool, *, attempted: bool = True
) -> dict[str, Any]:
    """Describe actual immutable-CAS mutation without a racy existence guess."""

    return {
        "write_attempted": attempted,
        "mutation_performed": mutation_performed,
        "cas_newly_written_bytes": (
            size_bytes if attempted and mutation_performed else 0
        ),
        "cas_reused_bytes": size_bytes if attempted and not mutation_performed else 0,
        "files_written_count": 1 if attempted and mutation_performed else 0,
    }


def resolved_ref(root: Path, ref: str) -> Path:
    """Resolve one workspace-relative file ref without following symlinks."""

    relative = Path(str(ref))
    if relative.is_absolute() or not relative.parts or ".." in relative.parts:
        raise ValueError("artifact ref must be a workspace-relative path")
    candidate = root
    for part in relative.parts:
        candidate = candidate / part
        if candidate.is_symlink():
            raise ValueError("artifact ref must not traverse a symlink")
    try:
        path = candidate.resolve(strict=True)
    except FileNotFoundError as exc:
        raise ValueError("artifact ref does not exist") from exc
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ValueError("artifact ref escapes the workspace") from exc
    if not path.is_file():
        raise ValueError("artifact ref must identify a regular file")
    return path


def read_exact_json(
    root: Path, ref: str, sha256: str, maximum: int
) -> tuple[dict[str, Any], bytes, Path]:
    """Read one digest-bound JSON object subject to a strict byte budget."""

    if not SHA256_PATTERN.fullmatch(str(sha256)):
        raise ValueError("artifact sha256 must be a lowercase SHA-256 value")
    path = resolved_ref(root, ref)
    if path.stat().st_size > maximum:
        raise ValueError("stage artifact byte budget exceeded")
    payload = path.read_bytes()
    if hashlib.sha256(payload).hexdigest() != sha256:
        raise ValueError("stage artifact file digest does not match exact input")
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("stage artifact is not valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise ValueError("stage artifact JSON must be an object")
    return value, payload, path


# Compatibility aliases for callers that previously imported private helpers.
_resolved_ref = resolved_ref
_read_exact_json = read_exact_json


__all__ = [
    "SHA256_PATTERN",
    "_read_exact_json",
    "_resolved_ref",
    "cas_write_receipt",
    "read_exact_json",
    "resolved_ref",
]
