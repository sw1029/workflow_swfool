from __future__ import annotations

from typing import Any

from ..advice import validate_advice_consumption_and_forward_tests
from ..base import RuleContext, RuleRegistry
from ..common import (
    ADVICE_REQUIRED_TARGETS,
    AGENT_ROUTING_TARGETS,
    CANONICAL_LEDGER_STEPS,
    COMMON_FIELDS,
    MODEL_EFFORT_POLICY,
    MODEL_EFFORT_ROUTER,
    ROUTING_ENFORCEMENT_VALUES,
    SUPPORTED_AGENT_EFFORTS,
    SUPPORTED_AGENT_MODELS,
    active_advice_present,
    actual_report_body_divergences,
    add,
    advice_handling_rationale_present,
    boolish,
    first_present,
    has_value,
    list_values,
    non_empty,
    report_key_divergences,
    report_key_duplicate_matches,
    value_for,
)
from ..decision import validate_decision_identity_and_compatibility, validate_verification_axes
from ..expectations import validate_state_projection, validate_task_pack_expectation_comparison
from ..finalization import validate_finalization_contract
from ..lifecycle import validate_lifecycle_extensions
from ..metric_consumption import validate_metric_applicability_consumption
from ..policy import long_run_state_checked, pending_long_run_context, reasoned_na_allows_explicit_empty
from ..receipts import (
    _consumer_receipt_binding_sha256,
    _declared_values,
    _full_sha256,
    _positive_decision_claim,
)
from ..rules.session_audit import SessionAuditRule
from ..verdicts import validate_verdict_axes

SESSION_AUDIT_RULE = SessionAuditRule()

__all__ = (
    "ADVICE_REQUIRED_TARGETS",
    "AGENT_ROUTING_TARGETS",
    "Any",
    "CANONICAL_LEDGER_STEPS",
    "COMMON_FIELDS",
    "MODEL_EFFORT_POLICY",
    "MODEL_EFFORT_ROUTER",
    "ROUTING_ENFORCEMENT_VALUES",
    "RuleContext",
    "RuleRegistry",
    "SESSION_AUDIT_RULE",
    "SUPPORTED_AGENT_EFFORTS",
    "SUPPORTED_AGENT_MODELS",
    "SessionAuditRule",
    "_consumer_receipt_binding_sha256",
    "_declared_values",
    "_full_sha256",
    "_positive_decision_claim",
    "active_advice_present",
    "actual_report_body_divergences",
    "add",
    "advice_handling_rationale_present",
    "annotations",
    "boolish",
    "first_present",
    "has_value",
    "list_values",
    "long_run_state_checked",
    "non_empty",
    "pending_long_run_context",
    "reasoned_na_allows_explicit_empty",
    "report_key_divergences",
    "report_key_duplicate_matches",
    "validate_advice_consumption_and_forward_tests",
    "validate_decision_identity_and_compatibility",
    "validate_finalization_contract",
    "validate_lifecycle_extensions",
    "validate_metric_applicability_consumption",
    "validate_state_projection",
    "validate_task_pack_expectation_comparison",
    "validate_verdict_axes",
    "validate_verification_axes",
    "value_for",
)
