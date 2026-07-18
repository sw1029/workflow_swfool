from __future__ import annotations

from ...decision_freshness_lineage import assess_decision_freshness_lineage
from .shared import add, boolish, first_present
from .state import DeriveFacts


REVIEW_REFRESH_TASK_KINDS = frozenset(
    {
        "semantic_review",
        "semantic_review_refresh",
        "artifact_body_review",
        "qualitative_review",
        "review_refresh",
        "residual_descope",
        "descope_with_residual",
        "user_escalation",
        "terminal_blocked",
        "terminal_blocker",
    }
)
NONEXISTENT_ARTIFACT_REVIEW_KINDS = frozenset(
    {
        "semantic_review",
        "semantic_review_refresh",
        "artifact_body_review",
        "qualitative_review",
        "review_refresh",
    }
)


def _legacy_no_impact_declared(result: dict[str, object]) -> bool:
    value = first_present(
        result,
        [
            "no_impact_proof",
            "upstream_contract_no_impact_proof",
            "decision_freshness_gate.no_impact_proof",
            "result.decision_freshness_gate.no_impact_proof",
        ],
    )
    return value not in (None, "", [], {})


def check_decision_freshness(facts: DeriveFacts) -> None:
    assessment = assess_decision_freshness_lineage(facts.result)
    if not assessment.declared:
        legacy_revision = first_present(
            facts.result,
            [
                "decision_metadata_revision",
                "stale_measurement_artifact",
                "decision_freshness_gate.decision_metadata_revision",
                "decision_freshness_gate.stale_measurement_artifact",
            ],
        )
        if boolish(legacy_revision) and _legacy_no_impact_declared(facts.result):
            add(
                facts.findings,
                "block" if facts.mode == "block" else "warn",
                "derive_decision_no_impact_receipt_required",
                "A no-impact task or flag cannot satisfy decision freshness without an exact-subject, content-bound receipt.",
            )
        return

    facts.decision_lineage_declared = True
    facts.decision_lineage_status = assessment.status
    if assessment.issues:
        facts.decision_metadata_revision = True
        add(
            facts.findings,
            "block" if facts.mode == "block" else "warn",
            "derive_decision_freshness_lineage_invalid",
            "Derive cannot consume malformed or subject-mismatched implementation/deliverable/review lineage.",
            {"invalid_fields": list(assessment.issues)},
        )
        return

    if assessment.status == "implementation_ahead_of_artifact":
        facts.decision_metadata_revision = True
    elif assessment.status == "artifact_ahead_of_review":
        if (
            not facts.terminal_selected
            and facts.selected_kind not in REVIEW_REFRESH_TASK_KINDS
        ):
            add(
                facts.findings,
                "block" if facts.mode == "block" else "warn",
                "derive_artifact_review_revision_stale",
                "When the deliverable is ahead of semantic review, derive must route only the review-backed residual to review refresh, explicit descope, terminal handling, or escalation.",
                {"selected_task_kind": facts.selected_kind or None},
            )
    elif (
        assessment.status == "no_domain_artifact"
        and facts.selected_kind in NONEXISTENT_ARTIFACT_REVIEW_KINDS
    ):
        add(
            facts.findings,
            "block" if facts.mode == "block" else "warn",
            "derive_review_without_domain_artifact",
            "A no-domain-artifact lineage cannot be routed directly to semantic artifact review.",
            {"selected_task_kind": facts.selected_kind},
        )
    elif (
        assessment.status == "all_current"
        and assessment.evidence_required != "none"
        and not assessment.evidence_valid
    ):
        facts.decision_metadata_revision = True


__all__ = ("check_decision_freshness",)
