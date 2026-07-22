"""Shared closed-schema and canonicalization helpers for adapter audits."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import stat
from typing import Any


ANALYZER_REVISION = "adapter-architecture-facts-v2"
ADJUDICATOR_REVISION = "adapter-architecture-adjudicator-v1"
SEMANTIC_SCHEMA_REVISION = "adapter-architecture-semantic-v2"
CACHE_SCHEMA_REVISION = "adapter-architecture-cache-v1"
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
FORBIDDEN_SEMANTIC_KEYS = frozenset(
    {
        "audit_status",
        "block",
        "blocked",
        "body",
        "final_severity",
        "final_status",
        "prompt",
        "raw_body",
        "raw_source",
        "response",
        "severity",
        "source_body",
        "status",
    }
)


def canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def object_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_regular_file(root: Path, raw: str) -> tuple[Path, str]:
    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = root / candidate
    lexical = candidate.absolute()
    try:
        relative = lexical.relative_to(root)
    except ValueError as exc:
        raise ValueError("path escapes repository root") from exc
    current = root
    for part in relative.parts:
        current /= part
        if current.is_symlink():
            raise ValueError("path crosses a symlink")
    resolved = lexical.resolve(strict=True)
    if not stat.S_ISREG(resolved.lstat().st_mode):
        raise ValueError("path is not a regular file")
    return resolved, resolved.relative_to(root).as_posix()


def require_sha256(value: Any, label: str) -> str:
    if not isinstance(value, str) or SHA256_PATTERN.fullmatch(value) is None:
        raise ValueError(f"{label} must be a lowercase sha256")
    return value


def require_closed_fields(
    value: dict[str, Any],
    *,
    required: set[str],
    optional: set[str] = frozenset(),
    label: str,
) -> None:
    missing = required - set(value)
    unknown = set(value) - required - set(optional)
    if missing:
        raise ValueError(f"{label} missing fields: {', '.join(sorted(missing))}")
    if unknown:
        raise ValueError(f"{label} has unsupported fields: {', '.join(sorted(unknown))}")


def contains_forbidden_semantic_key(value: Any) -> str | None:
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = str(key).strip().lower()
            if normalized in FORBIDDEN_SEMANTIC_KEYS:
                return normalized
            found = contains_forbidden_semantic_key(child)
            if found:
                return found
    elif isinstance(value, list):
        for child in value:
            found = contains_forbidden_semantic_key(child)
            if found:
                return found
    return None


def load_bound_json(root: Path, path_value: Any, sha256: Any, label: str) -> Any:
    if not isinstance(path_value, str) or not path_value.strip():
        raise ValueError(f"{label} path is missing")
    path, relative = safe_regular_file(root, path_value)
    expected = require_sha256(sha256, f"{label} sha256")
    if file_sha256(path) != expected:
        raise ValueError(f"{label} digest mismatch")
    value = json.loads(path.read_text(encoding="utf-8"))
    return value, relative


__all__ = (
    "ADJUDICATOR_REVISION",
    "ANALYZER_REVISION",
    "CACHE_SCHEMA_REVISION",
    "SEMANTIC_SCHEMA_REVISION",
    "canonical_bytes",
    "contains_forbidden_semantic_key",
    "file_sha256",
    "load_bound_json",
    "object_sha256",
    "require_closed_fields",
    "require_sha256",
    "safe_regular_file",
)
