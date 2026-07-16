from __future__ import annotations

from .shared import (
    _positive_decision_claim,
    actual_report_body_divergences,
    add,
    boolish,
    first_present,
)
from .state import ValidationState


def check_reports(state: ValidationState) -> None:
    target = state.target
    result = state.result
    mode = state.mode
    findings = state.findings
    auto_report_body_divergences = actual_report_body_divergences(result)
    report_body_divergence = boolish(
        first_present(
            result,
            [
                "report_body_divergence",
                "actual_artifact_truth.report_body_divergence",
                "validation.actual_artifact_truth.report_body_divergence",
                "result.report_body_divergence",
            ],
        )
    ) or bool(auto_report_body_divergences)
    actual_truth_required = boolish(
        first_present(
            result,
            [
                "actual_body_truth_required",
                "acceptance_required_actual_body_truth",
                "target_metric_delta.actual_body_truth_required",
                "acceptance.actual_body_truth_required",
            ],
        )
    )
    truth_basis = str(
        first_present(
            result,
            [
                "truth_basis",
                "actual_body_truth_basis",
                "actual_artifact_truth.truth_basis",
                "target_metric_delta.truth_basis",
            ],
        )
        or ""
    ).strip().lower()
    if report_body_divergence:
        add(
            findings,
            (
                "block"
                if mode == "block"
                or target in {"validate", "report"}
                or _positive_decision_claim(target, result)
                else "warn"
            ),
            "report_body_divergence",
            "The canonical actual-artifact body projection disagrees with the consumed report; this is distinct from duplicate report-key divergence.",
            {"auto_detected": auto_report_body_divergences[:20]},
        )
    if actual_truth_required and truth_basis in {"", "not_evaluated", "missing", "unknown"}:
        add(
            findings,
            "block" if mode == "block" or target == "validate" else "warn",
            "actual_body_truth_not_evaluated",
            "Acceptance-required actual-artifact body truth was not independently evaluated.",
        )
    
