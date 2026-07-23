"""Opaque capability held only by registered authority artifact producers."""

from __future__ import annotations

from typing import Any


_AUTHORITY_PRODUCER_CAPABILITY = object()


def _require_authority_producer_capability(value: Any) -> None:
    if value is not _AUTHORITY_PRODUCER_CAPABILITY:
        raise SystemExit(
            "Prospective authority publication requires a registered internal "
            "producer capability."
        )


__all__: tuple[str, ...] = ()
