"""Process-local capability for the guarded selected-successor executor."""
from __future__ import annotations

from typing import Any


_SELECTED_SUCCESSOR_EXECUTION_TOKEN = object()


def require_selected_successor_execution(value: Any) -> None:
    """Reject schema-v3 owner effects outside the all-three-gate executor."""

    if value is not _SELECTED_SUCCESSOR_EXECUTION_TOKEN:
        raise ValueError(
            "Selected-successor owner effect requires the guarded all-three authority gate"
        )


__all__ = ()
