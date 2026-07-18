"""Conditional run checks for cycle-unreachable long-run handoffs."""

from __future__ import annotations

from ..base import RuleContext
from ..cycle_reachability import assess_launch_contract
from ..scope import add


def check_cycle_reachability_run(context: RuleContext) -> None:
    assessment = assess_launch_contract(context.result)
    if not assessment.applicable:
        return
    for issue in assessment.issues:
        add(
            context.findings,
            "block" if context.mode == "block" else "warn",
            f"run_{issue}",
            "A cycle-unreachable run must preserve its exact scale, throughput, cycle-cap, residual-acceptance, and harvest-plan bindings.",
            {"contract_issue": issue},
        )


__all__ = ["check_cycle_reachability_run"]
