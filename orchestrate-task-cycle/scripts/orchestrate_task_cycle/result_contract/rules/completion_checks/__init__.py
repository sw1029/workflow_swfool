from __future__ import annotations

from ...base import RuleContext
from .acceptance_facts import check_acceptance_facts
from .artifact_facts import check_artifact_facts
from .change_evidence import check_change_evidence
from .closure import check_closure
from .decision_freshness import check_decision_freshness
from .cycle_reachability import check_cycle_reachability
from .evaluate import check_evaluate
from .operation_facts import check_operation_facts
from .preflight import check_preflight
from .scenarios import check_scenarios
from .scoped_progress import check_scoped_progress
from .state import CompletionFacts

ORDERED_CHECKS = (
    check_preflight,
    check_acceptance_facts,
    check_artifact_facts,
    check_cycle_reachability,
    check_decision_freshness,
    check_operation_facts,
    check_evaluate,
    check_scenarios,
    check_change_evidence,
    check_scoped_progress,
    check_closure,
)


def run_checks(context: RuleContext) -> None:
    facts = CompletionFacts(context)
    for check in ORDERED_CHECKS:
        check(facts)
