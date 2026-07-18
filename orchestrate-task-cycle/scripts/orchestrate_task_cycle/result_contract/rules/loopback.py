from __future__ import annotations

from .._rule_checks.loopback import run_loopback_audit_check
from ..base import RuleContext, TargetContractRule
from .acceptance_satisfiability import validate_acceptance_satisfiability


class LoopbackAuditRule(TargetContractRule):
    """Validate authoritative pre-derive progress and anti-loop disposition."""

    targets = frozenset({"loopback_audit"})

    def check(self, context: RuleContext) -> None:
        validate_acceptance_satisfiability(context)
        run_loopback_audit_check(context)
