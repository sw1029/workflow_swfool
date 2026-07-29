"""Shared closed-contract helpers for session continuation."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import PurePosixPath
import re
from typing import Any


OPAQUE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@-]{0,255}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class ContinuationContractError(ValueError):
    """Raised when continuation state cannot be trusted or replayed safely."""


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def opaque(value: Any, label: str, *, nullable: bool = False) -> str | None:
    if value is None and nullable:
        return None
    normalized = str(value or "").strip()
    if not OPAQUE_RE.fullmatch(normalized):
        raise ContinuationContractError(
            f"{label} must be a bounded opaque identifier"
        )
    return normalized


def sha(value: Any, label: str) -> str:
    normalized = str(value or "").removeprefix("sha256:").lower()
    if not SHA256_RE.fullmatch(normalized):
        raise ContinuationContractError(
            f"{label} must be a lowercase SHA-256 digest"
        )
    return normalized


def timestamp(value: Any, label: str) -> str:
    normalized = str(value or "")
    try:
        parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ContinuationContractError(f"{label} must be RFC3339") from exc
    if parsed.tzinfo is None:
        raise ContinuationContractError(f"{label} must include a timezone")
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def binding(value: Any, label: str, *, nullable: bool = False) -> dict[str, Any] | None:
    if value is None and nullable:
        return None
    if not isinstance(value, dict) or set(value) != {"ref", "sha256"}:
        raise ContinuationContractError(
            f"{label} must be a closed ref/sha256 binding"
        )
    ref = str(value.get("ref") or "").strip()
    path = PurePosixPath(ref)
    if (
        not ref
        or len(ref) > 512
        or path.is_absolute()
        or ".." in path.parts
        or "\\" in ref
    ):
        raise ContinuationContractError(
            f"{label}.ref must be a safe repository-relative path"
        )
    return {"ref": path.as_posix(), "sha256": sha(value.get("sha256"), f"{label}.sha256")}


__all__ = (
    "ContinuationContractError",
    "binding",
    "canonical_bytes",
    "digest",
    "opaque",
    "sha",
    "timestamp",
)
