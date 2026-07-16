from __future__ import annotations

from typing import Any

from .shared import (
    RuleContext,
    SESSION_AUDIT_RULE,
    long_run_state_checked,
    pending_long_run_context,
    value_for,
)
from .state import ValidationState


def check_finalize(state: ValidationState) -> dict[str, Any]:
    target = state.target
    result = state.result
    mode = state.mode
    rule_registry = state.rule_registry
    contract_context = state.contract_context
    findings = state.findings
    missing = state.missing
    require_context_field = state.require_context_field
    explicit_report_key_divergence = state.explicit_report_key_divergence
    auto_report_key_divergences = state.auto_report_key_divergences
    execution_status = str(value_for(result, "execution_status") or "").lower()
    pending_long_runs = pending_long_run_context(contract_context)
    checked_long_run_state = long_run_state_checked(contract_context, result)
    context = RuleContext(
        target=target,
        result=result,
        mode=mode,
        findings=findings,
        missing=missing,
        require_context_field=require_context_field,
        metadata={
            "contract_context": contract_context,
            "execution_status": execution_status,
            "explicit_report_key_divergence": explicit_report_key_divergence,
            "auto_report_key_divergences": auto_report_key_divergences,
            "pending_long_runs": pending_long_runs,
            "long_run_state_checked": checked_long_run_state,
        },
    )
    SESSION_AUDIT_RULE.validate(context)
    rule_registry.validate(context)
    
    status = "ok"
    if any(item["severity"] == "block" for item in findings):
        status = "block"
    elif findings:
        status = "warn"
    return {"status": status, "target": target, "mode": mode, "findings": findings, "missing_fields": missing}
    
