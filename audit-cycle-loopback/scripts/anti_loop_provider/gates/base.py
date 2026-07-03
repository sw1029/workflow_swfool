from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class GateContext:
    values: dict[str, Any] = field(default_factory=dict)


@dataclass
class GateState:
    values: dict[str, Any] = field(default_factory=dict)


class BaseGate(ABC):
    name: str = 'base_gate'

    def evaluate(self, context: GateContext | dict[str, Any] | None = None, state: GateState | dict[str, Any] | None = None) -> dict[str, Any]:
        context_values = context.values if isinstance(context, GateContext) else (context or {})
        state_values = state.values if isinstance(state, GateState) else (state or {})
        return self.compute(context_values, state_values)

    @abstractmethod
    def compute(self, context: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError


class DispositionGate(BaseGate):
    safety_valves = {'terminal_blocked', 'user_escalation'}

    def normalize_result(self, result: dict[str, Any]) -> dict[str, Any]:
        if result.get('constrains_disposition') and 'allowed_dispositions' not in result:
            result = {**result, 'allowed_dispositions': sorted(self.safety_valves)}
        return result

    def evaluate(self, context: GateContext | dict[str, Any] | None = None, state: GateState | dict[str, Any] | None = None) -> dict[str, Any]:
        return self.normalize_result(super().evaluate(context, state))
