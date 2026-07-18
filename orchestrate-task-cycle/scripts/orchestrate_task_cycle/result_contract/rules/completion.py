from __future__ import annotations

from ..base import RuleContext, TargetContractRule
from .completion_checks.shared import (  # noqa: F401 - legacy compatibility surface
    add,
    annotations,
    boolish,
    first_present,
    json,
    list_values,
    non_empty,
    nonzero_scalar,
    value_for,
)
from .completion_checks.shared import __all__ as __shared_exports


__all__ = (*__shared_exports, "CompletionValidationRule")


class CompletionValidationRule(TargetContractRule):
    """Enforce completion, progress, evidence, and close-time integrity rules."""

    targets = frozenset({"validate"})

    def check(self, context: RuleContext) -> None:
        from .completion_checks import run_checks
        from .acceptance_satisfiability import validate_acceptance_satisfiability

        validate_acceptance_satisfiability(context)
        run_checks(context)
