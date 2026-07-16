from __future__ import annotations

# Legacy constants and helper aliases remain available from this rule module.
# ruff: noqa: F401

from .._rule_checks.cycle_efficiency import run_cycle_efficiency_profile_check
from .._rule_checks.cycle_efficiency_common import (
    BASIS_LIST_FIELDS,
    EXECUTION_SCOPE_EVIDENCE_FIELDS,
    EXECUTION_SCOPE_FIELDS,
    ID_PATTERN,
    OPAQUE_ID_MAX_LENGTH,
    PROFILE_SCOPE_FIELDS,
    RECOMMENDATIONS,
    STATUSES,
    bounded_id_list as _bounded_id_list,
    bounded_opaque_id as _bounded_opaque_id,
    nonnegative_int as _nonnegative_int,
)
from ..base import RuleContext, TargetContractRule


class CycleEfficiencyProfileRule(TargetContractRule):
    """Reject fabricated or structurally empty efficiency-profile envelopes."""

    targets = frozenset({"cycle_efficiency_profile"})

    def check(self, context: RuleContext) -> None:
        run_cycle_efficiency_profile_check(context)
