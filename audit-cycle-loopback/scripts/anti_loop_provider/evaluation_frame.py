from __future__ import annotations

from collections.abc import Mapping as _Mapping
from typing import Any


class _EvaluationFrame:
    """Explicit state carrier between ordered evaluator stages.

    The evaluator intentionally has a broad internal state surface.  Keeping
    that surface in one mapping makes stage dependencies inspectable without
    leaking evaluation locals into module globals.
    """

    def __init__(self, values: _Mapping[str, Any] | None = None) -> None:
        self._values = dict(values or {})

    def require(self, *names: str) -> Any:
        values = tuple(self._values[name] for name in names)
        return values[0] if len(values) == 1 else values

    def update(self, values: _Mapping[str, Any]) -> None:
        self._values.update(values)

    def snapshot(self) -> dict[str, Any]:
        return dict(self._values)

def _require_values(values: _Mapping[str, Any], names: tuple[str, ...]) -> tuple[Any, ...]:
    """Resolve a declared stage dependency set from a legacy mapping."""

    return tuple(values[name] for name in names)
