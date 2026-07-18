"""Opaque, bounded metadata for external advice sources."""

from __future__ import annotations

import re
import unicodedata


MAX_TITLE_LENGTH = 80
_PATH_OR_LOCATOR = re.compile(
    r"(?:[A-Za-z][A-Za-z0-9+.-]*://|[A-Za-z]:[\\/]|[/\\]|(?:^|\s)~(?:[/\\]|$)|\.\.)"
)
_TITLE_CHARACTERS = re.compile(r"[^0-9A-Za-z가-힣 ._-]+")


def opaque_source_id(raw_sha256: str) -> str:
    normalized = str(raw_sha256 or "").strip().lower()
    if len(normalized) != 64 or any(
        character not in "0123456789abcdef" for character in normalized
    ):
        raise ValueError("opaque source IDs require a full lowercase SHA-256")
    return f"src-sha256-{normalized}"


def safe_title(value: str | None, raw_sha256: str) -> tuple[str, str]:
    """Return a bounded caller label, or a digest-derived opaque fallback."""

    fallback = f"external-advice-{raw_sha256[:12]}"
    if value is None:
        return fallback, "opaque_fallback"
    normalized = unicodedata.normalize("NFKC", str(value))
    normalized = " ".join(normalized.split())
    if not normalized or _PATH_OR_LOCATOR.search(normalized):
        return fallback, "opaque_fallback"
    sanitized = _TITLE_CHARACTERS.sub(" ", normalized)
    sanitized = " ".join(sanitized.split()).strip(" ._-")[:MAX_TITLE_LENGTH].rstrip()
    if not sanitized:
        return fallback, "opaque_fallback"
    return sanitized, "caller_sanitized"


__all__ = ("MAX_TITLE_LENGTH", "opaque_source_id", "safe_title")
