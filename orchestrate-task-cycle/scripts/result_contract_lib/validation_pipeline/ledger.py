from __future__ import annotations

from .shared import (
    ADVICE_REQUIRED_TARGETS,
    CANONICAL_LEDGER_STEPS,
    active_advice_present,
    add,
    advice_handling_rationale_present,
    boolish,
    first_present,
    has_value,
    report_key_divergences,
    report_key_duplicate_matches,
)
from .state import ValidationState


def check_ledger(state: ValidationState) -> None:
    target = state.target
    result = state.result
    mode = state.mode
    rule_registry = state.rule_registry
    contract_context = state.contract_context
    findings = state.findings
    missing = state.missing
    def require_context_field(field: str, code: str, message: str) -> None:
        if has_value(result, field):
            return
        if field not in missing:
            missing.append(field)
        add(findings, "block" if mode == "block" or target == "report" else "warn", code, message, {"field": field})
    
    raw_step = result.get("step")
    step = str(raw_step).strip() if raw_step is not None else ""
    if not step:
        if "step" not in missing:
            missing.append("step")
        add(
            findings,
            "block" if mode == "block" else "warn",
            "ledger_step_missing",
            f"`{target}` result lacks top-level canonical `step`; direct ledger append must pass `--step {target}` or use an event envelope.",
            {"expected_step": target},
        )
    elif step not in CANONICAL_LEDGER_STEPS:
        add(
            findings,
            "block" if mode == "block" else "warn",
            "ledger_step_noncanonical",
            f"`{target}` result has noncanonical ledger `step`.",
            {"step": step, "expected_step": target},
        )
    elif step != target:
        add(
            findings,
            "block" if mode == "block" else "warn",
            "ledger_step_mismatch",
            f"`{target}` result has `step: {step}`; expected `step: {target}` for direct ledger append.",
            {"step": step, "expected_step": target},
        )
    
    if target in ADVICE_REQUIRED_TARGETS and active_advice_present(result) and not has_value(result, "used_advice"):
        if not advice_handling_rationale_present(result):
            add(
                findings,
                "block",
                "active_advice_unhandled",
                f"`{target}` result has active external advice in scope but lacks `used_advice` or an explicit advice defer/reject/not-applicable rationale.",
                {"required": ["used_advice", "advice_deferred_reason|advice_rejected_reason|advice_not_applicable_reason|advice_handling_rationale"]},
            )
    
    explicit_report_key_divergence = boolish(
        first_present(
            result,
            [
                "report_key_divergence",
                "report_key_integrity_gate.report_key_divergence",
                "validation.report_key_integrity_gate.report_key_divergence",
                "result.report_key_integrity_gate.report_key_divergence",
            ],
        )
    )
    auto_report_key_divergences = report_key_divergences(result)
    auto_report_key_duplicate_matches = report_key_duplicate_matches(result)
    if explicit_report_key_divergence or auto_report_key_divergences:
        report_key_severity = "block" if mode == "block" or target in {"validate", "report"} else "warn"
        add(
            findings,
            report_key_severity,
            "report_key_divergence",
            "`report_key_divergence` means one canonical projection has divergent duplicate terminal keys across one or more report surfaces; pass/close/adoption/baseline/comparison consumption is invalid until the reports converge.",
            {"auto_detected": auto_report_key_divergences[:20], "explicit_report_key_divergence": explicit_report_key_divergence},
        )
    if auto_report_key_duplicate_matches:
        add(
            findings,
            "warn",
            "report_key_duplicate_schema_debt",
            "Matching duplicate terminal report keys are schema debt; consumption may continue, but the report should be normalized to one authoritative copy.",
            {"auto_detected": auto_report_key_duplicate_matches[:20]},
        )
    
    state.require_context_field = require_context_field
    state.explicit_report_key_divergence = explicit_report_key_divergence
    state.auto_report_key_divergences = auto_report_key_divergences
