from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..base import RuleContext
from ..common import (
    add,
    boolish,
    first_present,
    has_value,
    list_values,
    non_empty,
    value_for,
)
from .qualitative_common import (
    finite_nonnegative_number,
    nonzero_scalar,
    scalar_counts_valid,
)
from .qualitative_surface import validate_surface_review


DENSITY_REQUIRED_PATHS = (
    "substance_density_required",
    "substance_density_gate.required_for_acceptance",
    "substance_density_gate.decision_contribution_allowed",
    "quality_review.substance_density_required",
    "quality_review.substance_density_gate.required_for_acceptance",
    "quality_review.substance_density_gate.decision_contribution_allowed",
    "qualitative_review.substance_density_required",
    "qualitative_review.substance_density_gate.required_for_acceptance",
    "qualitative_review.substance_density_gate.decision_contribution_allowed",
    "result.substance_density_required",
    "result.substance_density_gate.required_for_acceptance",
    "result.substance_density_gate.decision_contribution_allowed",
    "result.quality_review.substance_density_required",
    "result.quality_review.substance_density_gate.required_for_acceptance",
    "result.quality_review.substance_density_gate.decision_contribution_allowed",
)


@dataclass(frozen=True, slots=True)
class ReviewState:
    status: str
    verdict: str
    delegation_reason: Any

    @property
    def delegation_unavailable(self) -> bool:
        return self.delegation_reason is not None


def run_qualitative_review_check(context: RuleContext) -> None:
    state = _review_state(context.result)
    _validate_review_vocabulary(context, state)
    _validate_direct_read_scope(context, state)
    _validate_axis_completeness(context, state)
    _validate_delegation(context, state)
    validate_surface_review(context)
    _validate_density(context)


def _review_state(result: dict[str, Any]) -> ReviewState:
    return ReviewState(
        status=str(
            value_for(result, "review_status") or value_for(result, "status") or ""
        ).lower(),
        verdict=str(value_for(result, "quality_verdict") or "").lower(),
        delegation_reason=first_present(
            result,
            [
                "reviewer_delegation_unavailable_reason",
                "delegation_unavailable_reason",
                "review_delegation_unavailable_reason",
                "quality_review.reviewer_delegation_unavailable_reason",
                "qualitative_review.reviewer_delegation_unavailable_reason",
            ],
        ),
    )


def _validate_review_vocabulary(context: RuleContext, state: ReviewState) -> None:
    result = context.result
    count = value_for(result, "review_agent_count")
    try:
        count_value = int(str(count))
    except (TypeError, ValueError):
        count_value = None
    no_review_reason = first_present(
        result,
        [
            "reason",
            "review_skipped_reason",
            "qualitative_review_pending_reason",
            "reviewer_delegation_unavailable_reason",
            "blockers",
        ],
    )
    reasoned_no_review = state.status in {"blocked", "not_applicable"} and non_empty(
        no_review_reason
    )
    severity = "block" if context.mode == "block" else "warn"
    if count_value != 1 and not (count_value == 0 and reasoned_no_review):
        add(
            context.findings,
            severity,
            "qualitative_review_agent_count_invalid",
            "`qualitative_review` must report exactly one reviewer agent.",
            {"review_agent_count": count},
        )
    if state.status and state.status not in {
        "complete",
        "partial",
        "blocked",
        "not_applicable",
    }:
        add(
            context.findings,
            severity,
            "qualitative_review_status_invalid",
            "`qualitative_review` review_status should be complete, partial, blocked, or not_applicable.",
            {"review_status": state.status},
        )
    if state.verdict and state.verdict not in {
        "acceptable",
        "candidate_only",
        "quality_blocked",
        "unreviewable",
        "not_applicable",
    }:
        add(
            context.findings,
            severity,
            "qualitative_review_quality_verdict_invalid",
            "`qualitative_review` quality_verdict should use the owner skill vocabulary.",
            {"quality_verdict": state.verdict},
        )


def _validate_direct_read_scope(context: RuleContext, state: ReviewState) -> None:
    result = context.result
    scope = {
        str(item).strip().lower()
        for item in list_values(
            first_present(
                result,
                [
                    "direct_read_scope",
                    "quality_review.direct_read_scope",
                    "qualitative_review.direct_read_scope",
                    "result.direct_read_scope",
                ],
            )
        )
        if str(item).strip()
    }
    task_change = "task_change" in scope
    artifact_body = "artifact_body" in scope
    semantic_positive = _semantic_positive(result)
    truth_basis = (
        str(
            first_present(
                result,
                [
                    "truth_basis",
                    "actual_body_truth_basis",
                    "actual_artifact_truth.truth_basis",
                    "quality_review.truth_basis",
                ],
            )
            or ""
        )
        .strip()
        .lower()
    )
    if state.status == "complete" and not (task_change or artifact_body):
        add(
            context.findings,
            "block"
            if context.mode == "block" or state.verdict == "acceptable"
            else "warn",
            "qualitative_review_scope_not_evaluated",
            "A complete qualitative review must declare task_change, artifact_body, or both in direct_read_scope.",
        )
    if semantic_positive and (
        not artifact_body or truth_basis in {"", "not_evaluated", "missing", "unknown"}
    ):
        add(
            context.findings,
            "block",
            "qualitative_review_artifact_body_not_evaluated",
            "Task-change or compatibility inspection cannot produce an artifact-body semantic pass; read the current body and preserve an evaluated truth basis.",
            {
                "task_change_observed": task_change,
                "artifact_body_observed": artifact_body,
                "truth_basis": truth_basis or "not_evaluated",
            },
        )


def _semantic_positive(result: dict[str, Any]) -> bool:
    def axis_pass(value: object) -> bool:
        raw = (
            value.get("status") or value.get("verdict")
            if isinstance(value, dict)
            else value
        )
        return str(raw or "").strip().lower() == "pass"

    semantic_ready = (
        str(
            first_present(result, ["semantic_ready", "quality_review.semantic_ready"])
            or ""
        )
        .strip()
        .lower()
    )
    progress_kind = (
        str(
            first_present(
                result,
                [
                    "effective_progress_kind",
                    "progress_kind",
                    "quality_review.effective_progress_kind",
                ],
            )
            or ""
        )
        .strip()
        .lower()
    )
    progress_cap = (
        str(
            first_present(result, ["progress_cap", "quality_review.progress_cap"]) or ""
        )
        .strip()
        .lower()
    )
    axes = [
        first_present(
            result,
            [
                "artifact_semantic_verdict",
                "verdict_axes.artifact_semantic_verdict",
                "result.artifact_semantic_verdict",
                "result.verdict_axes.artifact_semantic_verdict",
            ],
        ),
        first_present(
            result,
            [
                "goal_readiness_verdict",
                "verdict_axes.goal_readiness_verdict",
                "result.goal_readiness_verdict",
                "result.verdict_axes.goal_readiness_verdict",
            ],
        ),
    ]
    return bool(
        boolish(
            first_present(result, ["semantic_progress", "observed_semantic_progress"])
        )
        or semantic_ready == "true"
        or progress_kind == "goal_productive"
        or progress_cap == "goal_productive"
        or any(axis_pass(value) for value in axes)
    )


def _validate_axis_completeness(context: RuleContext, state: ReviewState) -> None:
    result = context.result
    pass_with_unobserved_axes = boolish(
        first_present(
            result,
            [
                "pass_with_unobserved_axes",
                "goal_axis_completeness_gate.pass_with_unobserved_axes",
                "quality_review.pass_with_unobserved_axes",
                "qualitative_review.pass_with_unobserved_axes",
                "result.goal_axis_completeness_gate.pass_with_unobserved_axes",
            ],
        )
    )
    unobserved_axes = first_present(
        result,
        [
            "unobserved_goal_axes",
            "goal_axis_completeness_gate.unobserved_goal_axes",
            "quality_review.unobserved_goal_axes",
            "qualitative_review.unobserved_goal_axes",
            "result.goal_axis_completeness_gate.unobserved_goal_axes",
        ],
    )
    if (
        pass_with_unobserved_axes or non_empty(unobserved_axes)
    ) and state.verdict == "acceptable":
        add(
            context.findings,
            "block" if context.mode == "block" else "warn",
            "qualitative_review_unobserved_axes_acceptable",
            "`qualitative_review` cannot report an acceptable pass for measurable goals with zero mapped observing axes; use pass_with_unobserved_axes and preserve axis-supply or residual work.",
            {"unobserved_goal_axes": unobserved_axes or None},
        )


def _validate_delegation(context: RuleContext, state: ReviewState) -> None:
    result = context.result
    identity = str(
        first_present(
            result,
            [
                "reviewer_agent",
                "reviewer_id",
                "reviewer_identity",
                "reviewer",
                "quality_review.reviewer_agent",
                "quality_review.reviewer_id",
                "quality_review.reviewer_identity",
                "qualitative_review.reviewer_agent",
                "qualitative_review.reviewer_id",
                "qualitative_review.reviewer_identity",
            ],
        )
        or ""
    ).lower()
    markers = (
        "main_orchestrator",
        "main_coordinator",
        "main coordinator",
        "orchestrator",
        "coordinator",
    )
    if identity and any(marker in identity for marker in markers):
        add(
            context.findings,
            "block",
            "qualitative_review_main_coordinator_substitution",
            "`qualitative_review` may not satisfy the reviewer-agent contract by naming the main coordinator as the reviewer.",
            {"reviewer_identity": identity},
        )
    severity = "block" if context.mode == "block" else "warn"
    if state.delegation_unavailable and state.status == "complete":
        add(
            context.findings,
            severity,
            "qualitative_review_delegation_unavailable_marked_complete",
            "Reviewer delegation unavailability must be reported as blocked, partial, or not_applicable, not complete.",
            {"reviewer_delegation_unavailable_reason": state.delegation_reason},
        )
    if state.status in {"blocked", "not_applicable"} and not (
        state.delegation_unavailable
        or non_empty(result.get("reason"))
        or has_value(result, "review_skipped_reason")
        or has_value(result, "qualitative_review_pending_reason")
        or has_value(result, "blockers")
    ):
        add(
            context.findings,
            severity,
            "qualitative_review_blocked_reason_missing",
            "Blocked/not_applicable qualitative review requires a concrete blocker, skipped reason, or delegation unavailable reason.",
        )


def _validate_density(context: RuleContext) -> None:
    result = context.result
    status_value = first_present(
        result,
        [
            "substance_density_evaluation_status",
            "substance_density_gate.evaluation_status",
            "quality_review.substance_density_evaluation_status",
            "quality_review.substance_density_gate.evaluation_status",
            "qualitative_review.substance_density_evaluation_status",
            "qualitative_review.substance_density_gate.evaluation_status",
            "result.substance_density_evaluation_status",
            "result.substance_density_gate.evaluation_status",
            "result.quality_review.substance_density_evaluation_status",
            "result.quality_review.substance_density_gate.evaluation_status",
        ],
    )
    required = any(
        boolish(first_present(result, [path])) for path in DENSITY_REQUIRED_PATHS
    )
    severity = "block" if context.mode == "block" else "warn"
    if required and status_value is None:
        add(
            context.findings,
            severity,
            "qualitative_review_substance_density_required_missing",
            "A required referential-substance projection must be present before an acceptance decision.",
        )
    if status_value is not None:
        _validate_density_projection(context, status_value, required)


def _validate_density_projection(
    context: RuleContext, status_value: object, required: bool
) -> None:
    allowed = {
        "meaningful",
        "not_meaningful",
        "not_applicable",
        "insufficient_evidence",
        "invalid_contract",
    }
    candidate = (
        status_value.strip().lower()
        if isinstance(status_value, str)
        else "invalid_contract"
    )
    status = candidate if candidate in allowed else "invalid_contract"
    counts = first_present(
        context.result,
        [
            "referential_substance_counts",
            "quality_review.referential_substance_counts",
            "qualitative_review.referential_substance_counts",
            "result.referential_substance_counts",
            "result.quality_review.referential_substance_counts",
        ],
    )
    claim_relevant = required or status in {"meaningful", "not_meaningful"}
    unresolved = status not in allowed or status in {
        "not_meaningful",
        "insufficient_evidence",
        "invalid_contract",
    }
    not_applicable = status == "not_applicable"
    counts_invalid = (
        not not_applicable and counts is not None and not scalar_counts_valid(counts)
    )
    meaningful_count = counts.get("meaningful") if isinstance(counts, dict) else None
    meaningful_without_evidence = bool(
        status == "meaningful"
        and (not finite_nonnegative_number(meaningful_count) or meaningful_count == 0)
    )
    defects = (
        not not_applicable
        and isinstance(counts, dict)
        and nonzero_scalar(
            {
                key: counts.get(key)
                for key in ("opaque", "incompatible_collision", "possible_false_split")
            }
        )
    )
    if not not_applicable and (
        unresolved or counts_invalid or defects or meaningful_without_evidence
    ):
        add(
            context.findings,
            ("block" if context.mode == "block" else "warn")
            if claim_relevant
            else "warn",
            "qualitative_review_referential_substance_bypass",
            "A required or consumed density projection cannot support review while referential substance is unresolved or defective.",
            {
                "evaluation_status": status,
                "scalar_counts_invalid": counts_invalid,
                "scalar_defects_present": bool(defects),
                "meaningful_evidence_present": not meaningful_without_evidence,
            },
        )
