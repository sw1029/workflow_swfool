from __future__ import annotations

from typing import Any

from .shared import (
    COMMON_FIELDS,
    add,
    first_present,
    has_value,
    reasoned_na_allows_explicit_empty,
    validate_advice_consumption_and_forward_tests,
    validate_decision_identity_and_compatibility,
    validate_finalization_contract,
    validate_lifecycle_extensions,
    validate_metric_applicability_consumption,
    validate_state_projection,
    validate_task_pack_expectation_comparison,
    validate_verdict_axes,
    validate_verification_axes,
)
from .state import ValidationState


def check_common(state: ValidationState) -> None:
    target = state.target
    result = state.result
    mode = state.mode
    contract_context = state.contract_context
    findings = state.findings
    missing = state.missing
    findings: list[dict[str, Any]] = []
    derive_mode = (
        str(
            first_present(
                result, ["derive_mode", "mode", "derive.mode", "result.derive_mode"]
            )
            or ""
        )
        .strip()
        .lower()
    )
    if target == "derive" and derive_mode == "initial_init":
        required_fields = [
            field for field in COMMON_FIELDS[target] if field != "completed_task_id"
        ]
    else:
        required_fields = COMMON_FIELDS[target]
    missing = [
        field
        for field in required_fields
        if not has_value(result, field)
        and not reasoned_na_allows_explicit_empty(target, field, result)
    ]
    severity = "block" if mode == "block" or target == "report" else "warn"
    for field in missing:
        add(
            findings,
            severity,
            "missing_required_field",
            f"`{target}` result is missing `{field}`.",
            {"field": field},
        )

    validate_decision_identity_and_compatibility(target, result, mode, findings)
    validate_metric_applicability_consumption(target, result, mode, findings)
    validate_verification_axes(target, result, mode, findings)
    validate_task_pack_expectation_comparison(target, result, mode, findings)
    validate_state_projection(target, result, mode, findings)
    validate_advice_consumption_and_forward_tests(
        target, result, mode, findings, contract_context
    )
    validate_verdict_axes(target, result, mode, findings)
    for item in validate_finalization_contract(target, result, contract_context):
        add(
            findings,
            "block",
            str(item["code"]),
            str(item["message"]),
            item.get("evidence"),
        )
    for item in validate_lifecycle_extensions(target, result):
        add(
            findings,
            str(item.get("severity") or "block"),
            str(item["code"]),
            str(item["message"]),
            item.get("evidence"),
        )

    state.findings = findings
    state.missing = missing
    state.severity = severity
