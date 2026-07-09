from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable


Finding = dict[str, Any]
ContextRequirement = Callable[[str, str, str], None]


@dataclass(slots=True)
class RuleContext:
    """Mutable validation state shared by independent target rules."""

    target: str
    result: dict[str, Any]
    mode: str
    findings: list[Finding]
    missing: list[str]
    require_context_field: ContextRequirement
    metadata: dict[str, Any] = field(default_factory=dict)

    def get(self, key: str, default: Any = None) -> Any:
        return self.metadata.get(key, default)


class ContractRule(ABC):
    """Base contract for an independently reusable validation rule."""

    @abstractmethod
    def applies_to(self, context: RuleContext) -> bool:
        """Return whether this rule owns the supplied result target."""

    @abstractmethod
    def check(self, context: RuleContext) -> None:
        """Append findings to the shared context without replacing prior facts."""

    def validate(self, context: RuleContext) -> None:
        if self.applies_to(context):
            self.check(context)


class TargetContractRule(ContractRule):
    """Contract rule selected by one or more canonical target names."""

    targets: frozenset[str] = frozenset()

    def applies_to(self, context: RuleContext) -> bool:
        return context.target in self.targets


class RuleRegistry:
    """Ordered composite for contract rules.

    Ordering is explicit because several legacy checks intentionally add context
    that a later check consumes. Rules remain independently instantiable for
    focused tests and downstream reuse.
    """

    def __init__(self, rules: Iterable[ContractRule]) -> None:
        self._rules = tuple(rules)

    @property
    def rules(self) -> tuple[ContractRule, ...]:
        return self._rules

    def validate(self, context: RuleContext) -> None:
        for rule in self._rules:
            rule.validate(context)
