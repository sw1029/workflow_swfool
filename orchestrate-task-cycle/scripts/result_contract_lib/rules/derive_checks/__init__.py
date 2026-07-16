from __future__ import annotations

from ...base import RuleContext
from .anti_loop import check_anti_loop
from .execution_scope import check_execution_scope
from .progress_evidence import check_progress_evidence
from .progress_policy import check_progress_policy
from .provider_outcomes import check_provider_outcomes
from .provider_setup import check_provider_setup
from .routing_contracts import check_routing_contracts
from .routing_outcomes import check_routing_outcomes
from .routing_safety import check_routing_safety
from .state import DeriveFacts
from .task_pack import check_task_pack

ORDERED_CHECKS = (
    check_anti_loop,
    check_task_pack,
    check_execution_scope,
    check_routing_contracts,
    check_routing_safety,
    check_routing_outcomes,
    check_progress_evidence,
    check_progress_policy,
    check_provider_setup,
    check_provider_outcomes,
)


def run_checks(context: RuleContext) -> None:
    facts = DeriveFacts(context)
    for check in ORDERED_CHECKS:
        check(facts)
