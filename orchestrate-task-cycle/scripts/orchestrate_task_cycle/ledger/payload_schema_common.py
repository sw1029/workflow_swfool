from __future__ import annotations

from typing import Any

from .constants import SHA256_PATTERN
from .support import validate_event_id


def exact_object(
    value: object,
    *,
    allowed: frozenset[str],
    required: frozenset[str],
    label: str,
) -> dict[str, Any]:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise ValueError(f"{label} payload must be an object with string fields")
    missing = sorted(required.difference(value))
    if missing:
        raise ValueError(
            f"{label} payload is missing required schema fields: {missing}"
        )
    unknown = sorted(set(value).difference(allowed))
    if unknown:
        raise ValueError(
            f"{label} payload contains unregistered schema fields: {unknown}"
        )
    return value


def exact_rows_payload(value: object, *, label: str) -> list[object]:
    payload = exact_object(
        value,
        allowed=frozenset({"rows"}),
        required=frozenset({"rows"}),
        label=label,
    )
    rows = payload["rows"]
    if not isinstance(rows, list):
        raise ValueError(f"{label} payload rows must be a list")
    return rows


def require_opaque_id(value: object, *, label: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be an exact opaque string ID")
    normalized = validate_event_id(value)
    if normalized != value:
        raise ValueError(f"{label} must not require normalization")
    return normalized


def require_digest(value: object, *, label: str) -> str:
    if not isinstance(value, str) or not SHA256_PATTERN.fullmatch(value):
        raise ValueError(f"{label} must be a full lowercase SHA-256 digest")
    return value


def require_non_negative_int(value: object, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a non-negative integer")
    return value


def require_bool(value: object, *, label: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{label} must be boolean")
    return value


def require_unique_opaque_ids(value: object, *, label: str) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be a unique opaque ID list")
    normalized = [require_opaque_id(item, label=label) for item in value]
    if len(normalized) != len(set(normalized)):
        raise ValueError(f"{label} must be a unique opaque ID list")
    return normalized


__all__ = [
    "exact_object",
    "exact_rows_payload",
    "require_bool",
    "require_digest",
    "require_non_negative_int",
    "require_opaque_id",
    "require_unique_opaque_ids",
]
