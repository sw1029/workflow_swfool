from __future__ import annotations

from ...base import RuleContext
from .analysis_contract import check_analysis_contract
from .anti_loop import check_anti_loop
from .authority_terminal import check_authority_terminal
from .decision_freshness import check_decision_freshness
from .cycle_reachability import check_cycle_reachability
from .execution_scope import check_execution_scope
from .finalization_recovery import check_finalization_recovery
from .progress_evidence import check_progress_evidence
from .progress_policy import check_progress_policy
from .prerequisite_chain import check_prerequisite_chain
from .provider_outcomes import check_provider_outcomes
from .provider_setup import check_provider_setup
from .routing_contracts import check_routing_contracts
from .routing_outcomes import check_routing_outcomes
from .routing_safety import check_routing_safety
from .scoped_progress import check_scoped_progress
from .state import DeriveFacts
from .task_pack import check_task_pack
from .terminal_contract import check_terminal_contract

ORDERED_CHECKS = (
    check_analysis_contract,
    check_terminal_contract,
    check_authority_terminal,
    check_finalization_recovery,
    check_anti_loop,
    check_prerequisite_chain,
    check_task_pack,
    check_execution_scope,
    check_routing_contracts,
    check_decision_freshness,
    check_routing_safety,
    check_cycle_reachability,
    check_routing_outcomes,
    check_progress_evidence,
    check_progress_policy,
    check_scoped_progress,
    check_provider_setup,
    check_provider_outcomes,
)


def run_checks(context: RuleContext) -> None:
    facts = DeriveFacts(context)
    for check in ORDERED_CHECKS:
        check(facts)
