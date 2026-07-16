from __future__ import annotations

# Legacy constants and helper aliases remain available from this rule module.
# ruff: noqa: F401

from .._rule_checks.session_audit import (
    CLOSE_TARGETS,
    SUCCESS_VALIDATION_VERDICTS,
    audit_inputs as _audit_inputs,
    current_binding as _current_binding,
    direct_packet_projection as _direct_packet_projection,
    positive_close_claim as _positive_close_claim,
    projection_packets as _projection_packets,
    run_session_audit_check,
)
from ..base import ContractRule, RuleContext


class SessionAuditRule(ContractRule):
    """Consume optional audit sidecars without promoting transcript observations."""

    def applies_to(self, context: RuleContext) -> bool:
        return bool(
            _audit_inputs(context.result, context.get("contract_context"))
        ) or bool(
            isinstance(context.get("contract_context"), dict)
            and context.get("contract_context", {}).get("session_audit_required")
            is True
        )

    def check(self, context: RuleContext) -> None:
        run_session_audit_check(context)
