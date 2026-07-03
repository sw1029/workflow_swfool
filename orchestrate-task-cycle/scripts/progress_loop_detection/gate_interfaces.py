from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class ProgressGate(ABC):
    """Base contract for loop-breaker gates."""

    name: str

    @abstractmethod
    def evaluate(self, context: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError


class FunctionProgressGate(ProgressGate):
    """Adapter for existing pure gate functions during the refactor."""

    def __init__(self, name: str, function: Any) -> None:
        self.name = name
        self._function = function

    def evaluate(self, context: dict[str, Any]) -> dict[str, Any]:
        return self._function(**context)
