from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..base import RuleContext
from ..common import add, boolish, deep_get, list_values, number_value, value_for


@dataclass(frozen=True, slots=True)
class LoopbackState:
    context: RuleContext

    @property
    def result(self) -> dict[str, Any]:
        return self.context.result

    @property
    def disposition(self) -> str:
        return self.text("recommended_disposition")

    @property
    def semantic_progress(self) -> bool:
        return self.flag("semantic_progress")

    @property
    def hard_stop(self) -> bool:
        return self.flag("hard_stop_required")

    @property
    def measurement_progress_allowed(self) -> bool:
        return self.flag("measurement_progress_allowed")

    @property
    def primary_metric_high_water_moved(self) -> bool:
        return self.flag(
            "primary_metric_high_water_moved",
            "primary_metric_gate.primary_metric_high_water_moved",
        )

    def value(self, key: str) -> Any:
        return value_for(self.result, key)

    def nested(self, path: str) -> Any:
        return deep_get(self.result, path)

    def first(self, key: str, *paths: str) -> Any:
        value = self.value(key)
        if value:
            return value
        for path in paths:
            value = self.nested(path)
            if value:
                return value
        return value

    def flag(self, key: str, *paths: str) -> bool:
        return boolish(self.value(key)) or any(
            boolish(self.nested(path)) for path in paths
        )

    def nested_flag(self, path: str) -> bool:
        return boolish(self.nested(path))

    def text(self, key: str, *paths: str) -> str:
        return str(self.first(key, *paths) or "").lower()

    def items(self, key: str, *paths: str) -> list[Any]:
        return list_values(self.first(key, *paths))

    def number(self, key: str, *paths: str) -> int | float:
        value = number_value(self.value(key))
        if value is not None:
            return value
        for path in paths:
            value = number_value(self.nested(path))
            if value is not None:
                return value
        return 0

    def emit(
        self,
        code: str,
        message: str,
        evidence: dict[str, Any] | None = None,
    ) -> None:
        add(
            self.context.findings,
            "block" if self.context.mode == "block" else "warn",
            code,
            message,
            evidence,
        )
