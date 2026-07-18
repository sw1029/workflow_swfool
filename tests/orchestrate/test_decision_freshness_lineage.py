from __future__ import annotations

import copy
from typing import Any

from orchestrate_task_cycle.result_contract import api as result_contract
from orchestrate_task_cycle.result_contract.decision_freshness_lineage import (
    canonical_receipt_sha256,
)


def codes(packet: dict[str, Any], target: str = "validate") -> set[str]:
    result = result_contract.validate(target, packet, "block")
    return {str(row.get("code")) for row in result.get("findings", [])}


def identity(*, producer_run: bool = True) -> dict[str, Any]:
    return {
        "decision_subject_id": "subject-A",
        "subject_class_id": "class-A",
        "revision_id": "implementation-R2",
        "subject_digest": "a" * 64,
        "lineage_id": "lineage-A",
        "freshness_status": "current",
        "body_fingerprint": {"applicability": "applicable", "value": "c" * 64},
        "production_lane": {"applicability": "applicable", "value": "lane-A"},
        "cohort": {"applicability": "not_applicable", "value": None},
        "producer_run": {
            "applicability": "applicable" if producer_run else "not_applicable",
            "value": "run-R2" if producer_run else None,
        },
    }


def relation_receipt(
    relation_kind: str,
    *,
    implementation_revision_id: str | None = None,
    deliverable_revision_id: str,
    review_revision_id: str | None = None,
) -> dict[str, Any]:
    receipt: dict[str, Any] = {
        "contract_version": 1,
        "relation_kind": relation_kind,
        "decision_subject_id": "subject-A",
        "decision_subject_digest": "a" * 64,
        "evidence_digest": "e" * 64,
    }
    if implementation_revision_id is not None:
        receipt["implementation_revision_id"] = implementation_revision_id
    receipt["deliverable_revision_id"] = deliverable_revision_id
    if review_revision_id is not None:
        receipt["review_revision_id"] = review_revision_id
    receipt["receipt_sha256"] = canonical_receipt_sha256(receipt)
    return receipt


def lineage(status: str = "all_current") -> dict[str, Any]:
    revisions: dict[str, Any] = {
        "latest_implementation_revision_id": "implementation-R2",
        "latest_compatible_deliverable_revision_id": "deliverable-R2",
        "latest_semantically_reviewed_deliverable_revision_id": "deliverable-R2",
        "implementation_deliverable_relation_receipt": relation_receipt(
            "compatible_deliverable_for_implementation",
            implementation_revision_id="implementation-R2",
            deliverable_revision_id="deliverable-R2",
        ),
        "deliverable_review_relation_receipt": relation_receipt(
            "semantic_review_of_deliverable",
            deliverable_revision_id="deliverable-R2",
            review_revision_id="review-R2",
        ),
    }
    if status == "implementation_ahead_of_artifact":
        revisions.update(
            latest_compatible_deliverable_revision_id="deliverable-R1",
            latest_semantically_reviewed_deliverable_revision_id="deliverable-R1",
            implementation_deliverable_relation_receipt=relation_receipt(
                "compatible_deliverable_for_implementation",
                implementation_revision_id="implementation-R1",
                deliverable_revision_id="deliverable-R1",
            ),
            deliverable_review_relation_receipt=relation_receipt(
                "semantic_review_of_deliverable",
                deliverable_revision_id="deliverable-R1",
                review_revision_id="review-R1",
            ),
        )
    elif status == "artifact_ahead_of_review":
        revisions.update(
            latest_semantically_reviewed_deliverable_revision_id="deliverable-R1",
            deliverable_review_relation_receipt=relation_receipt(
                "semantic_review_of_deliverable",
                deliverable_revision_id="deliverable-R1",
                review_revision_id="review-R1",
            ),
        )
    elif status == "no_domain_artifact":
        revisions.update(
            latest_compatible_deliverable_revision_id=None,
            latest_semantically_reviewed_deliverable_revision_id=None,
            implementation_deliverable_relation_receipt=None,
            deliverable_review_relation_receipt=None,
        )
    return {
        "applicability": "applicable",
        "lineage_status": status,
        "decision_subject_id": "subject-A",
        "decision_subject_digest": "a" * 64,
        **revisions,
    }


def measurement_receipt() -> dict[str, Any]:
    receipt = {
        "decision_subject_id": "subject-A",
        "decision_subject_digest": "a" * 64,
        "input_revision_id": "implementation-R2",
        "run_id": "run-R2",
        "output_fingerprint": "c" * 64,
    }
    receipt["receipt_sha256"] = canonical_receipt_sha256(receipt)
    return receipt


def no_impact_receipt() -> dict[str, Any]:
    receipt = {
        "decision_subject_id": "subject-A",
        "decision_subject_digest": "a" * 64,
        "input_revision_id": "implementation-R2",
        "predicate_id": "predicate-A",
        "evaluation_status": "pass",
        "evidence_digest": "d" * 64,
    }
    receipt["receipt_sha256"] = canonical_receipt_sha256(receipt)
    return receipt


def validation_packet(lineage_row: dict[str, Any]) -> dict[str, Any]:
    return {
        "step": "validate",
        "validation_verdict": "complete",
        "progress_verdict": "advanced",
        "progress_kind": "goal_productive",
        "decision_artifact_ref": identity(),
        "decision_freshness_lineage": lineage_row,
        "evidence_paths": ["receipt-A.json"],
    }


def derive_packet(lineage_row: dict[str, Any], task_kind: str) -> dict[str, Any]:
    return {
        "step": "derive",
        "next_task_id": "task-next",
        "selected_task_source": "candidate",
        "selected_task_kind": task_kind,
        "progress_kind": "goal_productive",
        "decision_artifact_ref": identity(),
        "decision_freshness_lineage": lineage_row,
        "evidence_paths": ["derive-A.json"],
    }


def test_current_producer_lineage_requires_content_bound_measurement() -> None:
    missing = validation_packet(lineage())
    assert "decision_current_execution_receipt_missing" in codes(missing)

    valid = validation_packet(
        {**lineage(), "fresh_measurement_receipt": measurement_receipt()}
    )
    assert "decision_current_execution_receipt_missing" not in codes(valid)

    tampered = copy.deepcopy(valid)
    tampered["decision_freshness_lineage"]["fresh_measurement_receipt"]["run_id"] = (
        "run-other"
    )
    assert "decision_current_execution_receipt_missing" in codes(tampered)


def test_current_lineage_accepts_distinct_revision_namespaces_via_relations() -> None:
    row = lineage()
    assert (
        row["latest_implementation_revision_id"]
        != row["latest_compatible_deliverable_revision_id"]
    )
    packet = validation_packet(
        {**row, "fresh_measurement_receipt": measurement_receipt()}
    )
    assert "decision_freshness_lineage_invalid" not in codes(packet)


def test_lineage_relation_receipts_are_content_and_endpoint_bound() -> None:
    packet = validation_packet(
        {**lineage(), "fresh_measurement_receipt": measurement_receipt()}
    )
    tampered_endpoint = copy.deepcopy(packet)
    tampered_endpoint["decision_freshness_lineage"][
        "implementation_deliverable_relation_receipt"
    ]["deliverable_revision_id"] = "deliverable-other"
    assert "decision_freshness_lineage_invalid" in codes(tampered_endpoint)

    tampered_digest = copy.deepcopy(packet)
    tampered_digest["decision_freshness_lineage"][
        "deliverable_review_relation_receipt"
    ]["receipt_sha256"] = "f" * 64
    assert "decision_freshness_lineage_invalid" in codes(tampered_digest)


def test_producer_run_applicability_cannot_use_no_impact_receipt() -> None:
    packet = validation_packet({**lineage(), "no_impact_receipt": no_impact_receipt()})
    assert "decision_current_execution_receipt_missing" in codes(packet)


def test_body_only_applicability_can_use_bound_no_impact_receipt() -> None:
    packet = validation_packet({**lineage(), "no_impact_receipt": no_impact_receipt()})
    packet["decision_artifact_ref"] = identity(producer_run=False)
    assert "decision_current_execution_receipt_missing" not in codes(packet)


def test_implementation_ahead_routes_to_refresh_and_blocks_completion() -> None:
    stale = validation_packet(lineage("implementation_ahead_of_artifact"))
    assert "validate_decision_metadata_revision_complete" in codes(stale)

    wrong_route = derive_packet(
        lineage("implementation_ahead_of_artifact"), "metadata_cleanup"
    )
    assert "derive_decision_metadata_revision_unhandled" in codes(wrong_route, "derive")
    refresh = derive_packet(
        lineage("implementation_ahead_of_artifact"), "producer_refresh"
    )
    assert "derive_decision_metadata_revision_unhandled" not in codes(refresh, "derive")


def test_artifact_ahead_only_restricts_review_backed_claims() -> None:
    ordinary = validation_packet(lineage("artifact_ahead_of_review"))
    ordinary["progress_verdict"] = "unchanged"
    ordinary["progress_kind"] = "task_local"
    ordinary["validation_verdict"] = "partial"
    assert "decision_review_revision_stale" not in codes(ordinary)

    review_backed = {**ordinary, "review_backed_readiness": True}
    assert "decision_review_revision_stale" in codes(review_backed)

    wrong_route = derive_packet(lineage("artifact_ahead_of_review"), "metadata_cleanup")
    assert "derive_artifact_review_revision_stale" in codes(wrong_route, "derive")
    review_route = derive_packet(
        lineage("artifact_ahead_of_review"), "semantic_review_refresh"
    )
    assert "derive_artifact_review_revision_stale" not in codes(review_route, "derive")


def test_no_domain_artifact_does_not_support_semantic_claim_or_review() -> None:
    packet = validation_packet(lineage("no_domain_artifact"))
    assert "decision_domain_artifact_absent" in codes(packet)
    derive = derive_packet(lineage("no_domain_artifact"), "semantic_review")
    assert "derive_review_without_domain_artifact" in codes(derive, "derive")


def test_not_applicable_lineage_is_an_explicit_bypass() -> None:
    packet = validation_packet(
        {
            "applicability": "not_applicable",
            "lineage_status": "not_applicable",
            "latest_implementation_revision_id": None,
            "latest_compatible_deliverable_revision_id": None,
            "latest_semantically_reviewed_deliverable_revision_id": None,
            "implementation_deliverable_relation_receipt": None,
            "deliverable_review_relation_receipt": None,
        }
    )
    packet["decision_artifact_ref"] = {
        **identity(producer_run=False),
        "body_fingerprint": {"applicability": "not_applicable", "value": None},
        "production_lane": {"applicability": "not_applicable", "value": None},
    }
    assert "decision_freshness_lineage_invalid" not in codes(packet)
    assert "decision_current_execution_receipt_missing" not in codes(packet)


def test_subject_mismatch_and_truthy_legacy_no_impact_fail_closed() -> None:
    mismatched = lineage()
    mismatched["decision_subject_id"] = "subject-other"
    assert "decision_freshness_lineage_invalid" in codes(validation_packet(mismatched))

    legacy = validation_packet(lineage())
    legacy.pop("decision_freshness_lineage")
    legacy["decision_metadata_revision"] = True
    legacy["no_impact_proof"] = True
    assert "decision_no_impact_receipt_required" in codes(legacy)
