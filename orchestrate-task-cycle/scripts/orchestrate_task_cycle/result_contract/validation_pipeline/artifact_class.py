from __future__ import annotations

from .shared import (
    add,
    first_present,
    value_for,
)
from .state import ValidationState


def check_artifact_class(state: ValidationState) -> None:
    target = state.target
    result = state.result
    mode = state.mode
    findings = state.findings
    if target == "validate":
        validation_verdict_early = str(value_for(result, "validation_verdict") or "").strip().lower()
        required_artifact_class_early = str(first_present(result, ["required_artifact_class", "acceptance.required_artifact_class"]) or "").strip()
        observed_artifact_class_early = str(first_present(result, ["observed_artifact_class", "artifact_class", "target_metric_delta.artifact_class"]) or "").strip()
        if (
            validation_verdict_early in {"complete", "passed", "pass", "success"}
            and required_artifact_class_early
            and observed_artifact_class_early
            and required_artifact_class_early != observed_artifact_class_early
        ):
            add(
                findings,
                "block" if mode == "block" else "warn",
                "validate_complete_required_artifact_class_mismatch",
                "Completion is invalid when the observed artifact class differs from the acceptance-required artifact class, regardless of progress verdict.",
                {"required_artifact_class": required_artifact_class_early, "observed_artifact_class": observed_artifact_class_early},
            )
    
