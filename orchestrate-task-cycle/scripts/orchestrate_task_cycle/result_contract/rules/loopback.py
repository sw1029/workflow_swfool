from __future__ import annotations

from .._rule_checks.loopback import run_loopback_audit_check
from ..base import RuleContext, TargetContractRule


class LoopbackAuditRule(TargetContractRule):
    """Validate authoritative pre-derive progress and anti-loop disposition."""

    targets = frozenset({"loopback_audit"})

    def check(self, context: RuleContext) -> None:
        run_loopback_audit_check(context)
