"""Consume only bound harvest/recalculation evidence for scale completion."""

from __future__ import annotations

from ...cycle_reachability import assess_harvest_completion, first_declared
from .shared import add
from .state import CompletionFacts


def check_cycle_reachability(facts: CompletionFacts) -> None:
    assessment = assess_harvest_completion(facts.result)
    if not assessment.applicable:
        return
    facts.harvest_validated = assessment.complete
    evidence_declared = (
        first_declared(
            facts.result,
            (
                "harvest_validation_receipt",
                "recomputed_cycle_reachability_gate",
                "long_run_harvest_validated",
                "harvest_validation_complete",
                "throughput_improved",
                "result.harvest_validation_receipt",
                "result.recomputed_cycle_reachability_gate",
            ),
        )
        is not None
    )
    consuming = (
        facts.validation_verdict in {"complete", "passed", "pass"}
        or facts.progress_verdict == "advanced"
    )
    if assessment.issues and (evidence_declared or consuming):
        add(
            facts.findings,
            "block" if facts.mode == "block" else "warn",
            "validate_cycle_reachability_evidence_invalid",
            "Cycle-unreachable acceptance can be consumed only by a content-bound matching harvest receipt or a matching fresh reachable recalculation.",
            {"contract_issues": assessment.issues},
        )


__all__ = ["check_cycle_reachability"]
