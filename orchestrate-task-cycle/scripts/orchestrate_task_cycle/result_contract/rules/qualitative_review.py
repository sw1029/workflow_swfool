from __future__ import annotations

# Private helper aliases are retained for compatibility with the legacy module.
# ruff: noqa: F401

from .._rule_checks.qualitative_common import (
    finite_nonnegative_number as _finite_nonnegative_number,
    nonzero_scalar as _nonzero_scalar,
    opaque_id as _opaque_id,
    scalar_counts_valid as _scalar_counts_valid,
)
from .._rule_checks.qualitative_review import run_qualitative_review_check
from ..base import RuleContext, TargetContractRule


class QualitativeReviewRule(TargetContractRule):
    """Validate independent qualitative-review evidence and routing."""

    targets = frozenset({"qualitative_review"})

    def check(self, context: RuleContext) -> None:
        run_qualitative_review_check(context)
