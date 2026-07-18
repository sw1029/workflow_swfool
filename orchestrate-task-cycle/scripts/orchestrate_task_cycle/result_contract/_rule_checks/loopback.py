from __future__ import annotations

from ..base import RuleContext
from .loopback_acceptance import validate_acceptance_and_verification
from .loopback_envelope import validate_envelope_and_observability
from .loopback_progress import validate_progress_and_mutation
from .loopback_routing import validate_routing_and_provenance
from .loopback_scoped_progress import validate_scoped_progress_contract
from .loopback_state import LoopbackState


def run_loopback_audit_check(context: RuleContext) -> None:
    state = LoopbackState(context)
    validate_progress_and_mutation(state)
    validate_scoped_progress_contract(state)
    validate_acceptance_and_verification(state)
    validate_routing_and_provenance(state)
    validate_envelope_and_observability(state)
