from __future__ import annotations

from ..base import RuleContext, TargetContractRule
from ..common import add, boolish, first_present, has_value, non_empty, value_for


class QualitativeReviewRule(TargetContractRule):
    """Validate independent qualitative-review evidence and routing."""

    targets = frozenset({'qualitative_review'})

    def check(self, context: RuleContext) -> None:
        result = context.result
        mode = context.mode
        findings = context.findings
        review_agent_count = value_for(result, "review_agent_count")
        try:
            reviewer_count_value = int(str(review_agent_count))
        except (TypeError, ValueError):
            reviewer_count_value = None
        review_status = str(value_for(result, "review_status") or value_for(result, "status") or "").lower()
        quality_verdict = str(value_for(result, "quality_verdict") or "").lower()
        delegation_unavailable_reason = first_present(
            result,
            [
                "reviewer_delegation_unavailable_reason",
                "delegation_unavailable_reason",
                "review_delegation_unavailable_reason",
                "quality_review.reviewer_delegation_unavailable_reason",
                "qualitative_review.reviewer_delegation_unavailable_reason",
            ],
        )
        delegation_unavailable = delegation_unavailable_reason is not None
        review_na_reason = first_present(
            result,
            [
                "reason",
                "review_skipped_reason",
                "qualitative_review_pending_reason",
                "reviewer_delegation_unavailable_reason",
                "blockers",
            ],
        )
        reasoned_no_review = review_status in {"blocked", "not_applicable"} and non_empty(review_na_reason)
        if reviewer_count_value != 1 and not (reviewer_count_value == 0 and reasoned_no_review):
            add(
                findings,
                "block" if mode == "block" else "warn",
                "qualitative_review_agent_count_invalid",
                "`qualitative_review` must report exactly one reviewer agent.",
                {"review_agent_count": review_agent_count},
            )
        if review_status and review_status not in {"complete", "partial", "blocked", "not_applicable"}:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "qualitative_review_status_invalid",
                "`qualitative_review` review_status should be complete, partial, blocked, or not_applicable.",
                {"review_status": review_status},
            )
        if quality_verdict and quality_verdict not in {"acceptable", "candidate_only", "quality_blocked", "unreviewable", "not_applicable"}:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "qualitative_review_quality_verdict_invalid",
                "`qualitative_review` quality_verdict should use the owner skill vocabulary.",
                {"quality_verdict": quality_verdict},
            )
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
        unobserved_goal_axes = first_present(
            result,
            [
                "unobserved_goal_axes",
                "goal_axis_completeness_gate.unobserved_goal_axes",
                "quality_review.unobserved_goal_axes",
                "qualitative_review.unobserved_goal_axes",
                "result.goal_axis_completeness_gate.unobserved_goal_axes",
            ],
        )
        if (pass_with_unobserved_axes or non_empty(unobserved_goal_axes)) and quality_verdict == "acceptable":
            add(
                findings,
                "block" if mode == "block" else "warn",
                "qualitative_review_unobserved_axes_acceptable",
                "`qualitative_review` cannot report an acceptable pass for measurable goals with zero mapped observing axes; use pass_with_unobserved_axes and preserve axis-supply or residual work.",
                {"unobserved_goal_axes": unobserved_goal_axes or None},
            )
        reviewer_identity = str(
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
        main_reviewer_markers = ("main_orchestrator", "main_coordinator", "main coordinator", "orchestrator", "coordinator")
        if reviewer_identity and any(marker in reviewer_identity for marker in main_reviewer_markers):
            add(
                findings,
                "block",
                "qualitative_review_main_coordinator_substitution",
                "`qualitative_review` may not satisfy the reviewer-agent contract by naming the main coordinator as the reviewer.",
                {"reviewer_identity": reviewer_identity},
            )
        if delegation_unavailable and review_status == "complete":
            add(
                findings,
                "block" if mode == "block" else "warn",
                "qualitative_review_delegation_unavailable_marked_complete",
                "Reviewer delegation unavailability must be reported as blocked, partial, or not_applicable, not complete.",
                {"reviewer_delegation_unavailable_reason": delegation_unavailable_reason},
            )
        if review_status in {"blocked", "not_applicable"} and not (
            delegation_unavailable
            or non_empty(result.get("reason"))
            or has_value(result, "review_skipped_reason")
            or has_value(result, "qualitative_review_pending_reason")
            or has_value(result, "blockers")
        ):
            add(
                findings,
                "block" if mode == "block" else "warn",
                "qualitative_review_blocked_reason_missing",
                "Blocked/not_applicable qualitative review requires a concrete blocker, skipped reason, or delegation unavailable reason.",
            )
