"""Reader policy for session-bound and historical authority children."""

from __future__ import annotations

from typing import Any


def grant_reuse_disposition(grant: dict[str, Any], session_id: str) -> str:
    """Classify legacy grants without mutating or upgrading historical evidence."""

    actual = grant.get("session_id")
    if actual is None:
        return "legacy_reader_only"
    if actual != session_id:
        return "session_mismatch"
    return "session_bound"


__all__ = ("grant_reuse_disposition",)
