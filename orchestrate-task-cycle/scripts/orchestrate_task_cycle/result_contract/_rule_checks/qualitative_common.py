from __future__ import annotations

import math


def nonzero_scalar(value: object) -> bool:
    if isinstance(value, dict):
        return any(nonzero_scalar(child) for child in value.values())
    if isinstance(value, list):
        return any(nonzero_scalar(child) for child in value)
    return (
        isinstance(value, (int, float)) and not isinstance(value, bool) and value != 0
    )


def finite_nonnegative_number(value: object) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(float(value)) and value >= 0
    except (OverflowError, TypeError, ValueError):
        return False


def scalar_counts_valid(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    for child in value.values():
        if isinstance(child, dict):
            if not scalar_counts_valid(child):
                return False
        elif not finite_nonnegative_number(child):
            return False
    return True


def opaque_id(value: object, *, max_length: int = 256) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    if not normalized or len(normalized) > max_length:
        return None
    if any(ord(character) < 32 or ord(character) == 127 for character in normalized):
        return None
    if (
        not normalized[0].isascii()
        or not normalized[0].isalnum()
        or any(
            not character.isascii() or not (character.isalnum() or character in "._-")
            for character in normalized
        )
    ):
        return None
    return normalized
