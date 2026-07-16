from __future__ import annotations

from .shared import (
    add,
    boolish,
    first_present,
)
from .state import CompletionFacts


def check_closure(facts: CompletionFacts) -> None:
    result = facts.result
    mode = facts.mode
    findings = facts.findings
    progress_verdict = facts.progress_verdict
    if progress_verdict == "advanced":
        authoritative_progress_verdict = str(
            first_present(
                result,
                [
                    "authoritative_progress_verdict",
                    "validation.authoritative_progress_verdict",
                    "result.authoritative_progress_verdict",
                ],
            )
            or ""
        ).strip().lower()
        loopback_authoritative = first_present(
            result,
            [
                "authoritative_semantic_progress",
                "anti_loop_progress_gate.authoritative_semantic_progress",
                "loopback_audit.authoritative_semantic_progress",
                "result.anti_loop_progress_gate.authoritative_semantic_progress",
            ],
        )
        hard_stop = boolish(
            first_present(
                result,
                [
                    "hard_stop_required",
                    "anti_loop_progress_gate.hard_stop_required",
                    "loopback_audit.hard_stop_required",
                ],
            )
        )
        if authoritative_progress_verdict != "advanced":
            add(
                findings,
                "block" if mode == "block" else "warn",
                "validate_advanced_without_authoritative_progress_verdict",
                "Only completion validation may emit close-time advanced progress, and it must explicitly own `authoritative_progress_verdict: advanced`.",
            )
        if loopback_authoritative is not None and not boolish(loopback_authoritative):
            add(
                findings,
                "block" if mode == "block" else "warn",
                "validate_progress_monotonicity_violation",
                "Completion validation cannot upgrade loopback `authoritative_semantic_progress=false` to advanced.",
            )
        if hard_stop:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "validate_advanced_despite_hard_stop",
                "Completion validation cannot report advanced while an authoritative hard stop remains active.",
            )
    
        required_artifact_class = str(first_present(result, ["required_artifact_class", "acceptance.required_artifact_class"]) or "").strip()
        observed_artifact_class = str(first_present(result, ["observed_artifact_class", "artifact_class", "target_metric_delta.artifact_class"]) or "").strip()
        if required_artifact_class and observed_artifact_class and required_artifact_class != observed_artifact_class:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "validate_required_artifact_class_mismatch",
                "Observed artifact class does not satisfy the acceptance-required artifact class.",
                {"required_artifact_class": required_artifact_class, "observed_artifact_class": observed_artifact_class},
            )
    
        required_status_paths = (
            "actual_body_truth_status",
            "report_convergence_status",
            "artifact_class_status",
            "freshness_status",
            "current_lane_status",
            "consumer_context_status",
            "verifier_completeness_status",
        )
        unevaluated_axes = [
            field
            for field in required_status_paths
            if str(first_present(result, [field, f"progress_integrity.{field}"]) or "").strip().lower()
            in {"not_evaluated", "missing", "unknown"}
        ]
        if unevaluated_axes:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "validate_advanced_with_required_integrity_not_evaluated",
                "Advanced progress is invalid while a required integrity axis is not evaluated.",
                {"axes": unevaluated_axes},
            )
    
