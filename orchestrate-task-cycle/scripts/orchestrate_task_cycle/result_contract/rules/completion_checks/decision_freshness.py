from __future__ import annotations

from ...decision_freshness_lineage import assess_decision_freshness_lineage
from .shared import add, first_present
from .state import CompletionFacts


POSITIVE_VALIDATION = frozenset({"complete", "pass", "passed", "success"})
POSITIVE_READINESS = frozenset({"ready", "acceptable", "complete", "pass", "passed"})


def _positive_semantic_claim(facts: CompletionFacts) -> bool:
    result = facts.result
    return bool(
        facts.validation_verdict in POSITIVE_VALIDATION
        or facts.progress_verdict == "advanced"
        or str(result.get("progress_kind") or "").strip().lower() == "goal_productive"
        or result.get("semantic_progress") is True
        or result.get("completion_eligible") is True
    )


def _review_backed_claim(facts: CompletionFacts) -> bool:
    result = facts.result
    return bool(
        result.get("review_backed_readiness") is True
        or result.get("semantic_review_required") is True
        or str(result.get("readiness_status") or "").strip().lower()
        in POSITIVE_READINESS
        or str(result.get("quality_verdict") or "").strip().lower()
        in {"acceptable", "pass", "passed"}
        or str(result.get("global_readiness") or "").strip().lower() == "ready"
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


def check_decision_freshness(facts: CompletionFacts) -> None:
    assessment = assess_decision_freshness_lineage(facts.result)
    if not assessment.declared:
        if facts.decision_metadata_revision and _legacy_no_impact_declared(
            facts.result
        ):
            facts.fresh_measurement_present = False
            add(
                facts.findings,
                "block" if facts.mode == "block" else "warn",
                "decision_no_impact_receipt_required",
                "A truthy no-impact flag is not freshness evidence; supply a content-bound no_impact_receipt for the exact decision subject and implementation revision.",
            )
        return

    facts.decision_lineage_declared = True
    facts.decision_lineage_status = assessment.status
    facts.fresh_measurement_present = assessment.evidence_valid
    if assessment.issues:
        facts.decision_metadata_revision = True
        facts.fresh_measurement_present = False
        add(
            facts.findings,
            "block" if facts.mode == "block" else "warn",
            "decision_freshness_lineage_invalid",
            "Decision freshness lineage must bind the exact subject and preserve a coherent implementation/deliverable/review revision relation.",
            {"invalid_fields": list(assessment.issues)},
        )
        return

    if assessment.status == "implementation_ahead_of_artifact":
        facts.decision_metadata_revision = True
        facts.fresh_measurement_present = False
        return
    if assessment.status == "artifact_ahead_of_review" and _review_backed_claim(facts):
        add(
            facts.findings,
            "block" if facts.mode == "block" else "warn",
            "decision_review_revision_stale",
            "Artifact production remains valid, but review-backed readiness cannot advance while the latest compatible deliverable is ahead of semantic review.",
        )
    if assessment.status == "no_domain_artifact" and _positive_semantic_claim(facts):
        add(
            facts.findings,
            "block" if facts.mode == "block" else "warn",
            "decision_domain_artifact_absent",
            "A no-domain-artifact lineage cannot support semantic artifact movement or readiness claims.",
        )
    if (
        assessment.status == "all_current"
        and assessment.evidence_required != "none"
        and not assessment.evidence_valid
        and _positive_semantic_claim(facts)
    ):
        add(
            facts.findings,
            "block" if facts.mode == "block" else "warn",
            "decision_current_execution_receipt_missing",
            "Applicable body/lane/run freshness requires an exact-subject current measurement receipt; producer-run applicability cannot be bypassed by no-impact assertion.",
            {"evidence_requirement": assessment.evidence_required},
        )


__all__ = ("check_decision_freshness",)
