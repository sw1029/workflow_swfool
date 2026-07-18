from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
for package_root in (
    ROOT / "orchestrate-task-cycle" / "scripts",
    ROOT / "audit-cycle-loopback" / "scripts",
):
    if str(package_root) not in sys.path:
        sys.path.insert(0, str(package_root))

import audit_cycle_loopback as loopback_provider  # noqa: E402
from orchestrate_task_cycle import assemble_cycle_report  # noqa: E402
from orchestrate_task_cycle import cycle_ledger  # noqa: E402
from orchestrate_task_cycle import output_delta_contract  # noqa: E402
from orchestrate_task_cycle import profile_cycle_efficiency  # noqa: E402
from orchestrate_task_cycle import render_cycle_dashboard  # noqa: E402
from orchestrate_task_cycle.progress import (  # noqa: E402
    analysis_aggregation as progress_analysis_aggregation,
)
from orchestrate_task_cycle.progress import dispatch_gate as progress_dispatch_gate  # noqa: E402
from orchestrate_task_cycle.progress import (  # noqa: E402
    output_delta_gate as progress_output_delta_gate,
)
from orchestrate_task_cycle.result_contract import api as result_contract  # noqa: E402
from orchestrate_task_cycle.result_contract import finalization as finalization_contract  # noqa: E402
from orchestrate_task_cycle.result_contract import integrity as result_integrity  # noqa: E402
from orchestrate_task_cycle.result_contract import lifecycle as lifecycle_contract  # noqa: E402
from orchestrate_task_cycle.result_contract.legacy_revision_bridge import (  # noqa: E402
    legacy_revision_bridge_sha256,
)
from orchestrate_task_cycle.result_contract.scenario_receipts import (  # noqa: E402
    canonical_invocation_sha256,
)
from orchestrate_task_cycle.result_contract.scoped_progress import (  # noqa: E402
    assess_scoped_progress,
    canonical_goal_axis_map_sha256,
)
from orchestrate_task_cycle.result_contract.scoped_progress_evidence import (  # noqa: E402
    canonical_goal_axis_receipt_sha256,
    canonical_independent_observation_receipt_sha256,
    canonical_self_grounded_receipt_sha256,
)
from orchestrate_task_cycle.result_contract.consumer_receipt_contract import (  # noqa: E402
    VALIDATOR_SIGNATURE_SHA256,
)
from orchestrate_task_cycle.result_contract.retained_change import (  # noqa: E402
    canonical_file_change_receipt_sha256,
    canonical_role_change_receipt_sha256,
)
from orchestrate_task_cycle.cycle_efficiency.producer_receipts import (  # noqa: E402
    canonical_sha256 as producer_receipt_sha256,
)


def finding_codes(result: dict[str, Any]) -> set[str]:
    return {str(item.get("code")) for item in result.get("findings", [])}


def legacy_identity() -> dict[str, Any]:
    return {
        "artifact_id": "artifact_A",
        "artifact_class": "family_F",
        "artifact_sha256": "a" * 64,
        "production_lane_identity": "lane_L",
        "body_projection_fingerprint": "b" * 64,
        "verification_input_ids": ["cohort_C"],
        "discovery_basis": "explicit_artifact_ref",
        "scope_verified": True,
    }


def legacy_revision_bridge(
    identity: dict[str, Any] | None = None,
) -> dict[str, Any]:
    artifact = identity or legacy_identity()
    receipt: dict[str, Any] = {
        "bridge_contract_version": 1,
        "bridge_status": "revision_bound",
        "artifact_id": artifact["artifact_id"],
        "artifact_class": artifact["artifact_class"],
        "artifact_sha256": artifact["artifact_sha256"],
        "revision_id": "revision_R",
        "subject_digest": artifact["artifact_sha256"],
        "lineage_id": "lineage_L",
        "freshness_status": "current",
        "evidence_ref": "bridge-evidence-E",
        "evidence_sha256": "e" * 64,
    }
    receipt["receipt_sha256"] = legacy_revision_bridge_sha256(receipt)
    return receipt


def absent_no_change_evidence(attempt_identity: str) -> dict[str, Any]:
    target_ref = "registry_projection"
    state_digest = cycle_ledger.absent_target_state_digest(target_ref)
    observation = cycle_ledger.build_unchanged_target_observation(
        observation_id=f"{attempt_identity}-registry-observation",
        attempt_identity=attempt_identity,
        target_ref=target_ref,
        state_status="absent",
        before_revision_id="absent",
        current_revision_id="absent",
        before_state_digest=state_digest,
        current_state_digest=state_digest,
    )
    return cycle_ledger.build_no_change_evidence(
        evidence_id=f"{attempt_identity}-no-change-evidence",
        attempt_identity=attempt_identity,
        target_observations=[observation],
    )


def finalized_bundle(
    root: Path,
    *,
    cycle_id: str = "cycle-final",
    attempt_id: str = "attempt-A",
    axis_statuses: dict[str, str] | None = None,
) -> dict[str, Any]:
    cycle_ledger.init_cycle(root, cycle_id, "task-1", "test finalization")
    statuses = axis_statuses or {}
    candidate: dict[str, Any] = {
        "schema_version": 1,
        "kind": "cycle_final_candidate",
        "final_candidate": True,
        "cycle_id": cycle_id,
        "attempt_id": attempt_id,
        "expected_previous_revision": None,
        "expected_previous_attempt_id": None,
        "expected_previous_finalization_token": None,
        "verdict_contract_version": 1,
        "durable_state_candidate": cycle_ledger.build_no_durable_state_change_candidate(
            attempt_identity=attempt_id,
            reason_id="validation-has-no-durable-axis-change",
            evidence=absent_no_change_evidence(attempt_id),
        ),
    }
    for axis in (
        "task_acceptance_verdict",
        "artifact_truth_verdict",
        "artifact_semantic_verdict",
        "pack_transition_verdict",
        "historical_index_verdict",
        "goal_readiness_verdict",
    ):
        candidate[axis] = {
            "status": statuses.get(axis, "pass"),
            "evidence_ref": f"{axis}-evidence",
        }
    finalized = cycle_ledger.finalize_candidate(root, cycle_id, candidate)
    receipt = finalized["finalization_receipt"]
    projection = finalized["snapshot"]["authoritative_projection"]
    consumption = {
        field: receipt[field]
        for field in (
            "finalization_token",
            "attempt_id",
            "attempt_revision",
            "authoritative_projection_id",
            "authoritative_projection_digest",
            "receipt_hash",
        )
    }
    return {
        "receipt": receipt,
        "projection": projection,
        "consumption": consumption,
        "candidate": candidate,
        "output": finalized,
    }


def test_direct_finalizer_output_is_consumable_and_binding_mismatch_blocks(
    tmp_path: Path,
) -> None:
    finalized = finalized_bundle(tmp_path)
    producer_output = finalized["output"]
    assert (
        finalization_contract.extract_finalization_receipt(producer_output)
        == finalized["receipt"]
    )
    projection, receipt, errors = finalization_contract.verified_projection(
        producer_output,
        {"workspace_root": str(tmp_path)},
    )
    assert errors == []
    assert receipt == finalized["receipt"]
    assert projection == finalized["projection"]
    consumer = {
        "step": "derive",
        "derive_mode": "normal",
        "finalization_receipt": finalized["receipt"],
        "authoritative_projection": finalized["projection"],
        "finalization_consumption": finalized["consumption"],
        "next_task_id": "task-2",
        "selected_task_source": "task_backlog",
        "progress_kind": "goal_productive",
        "semantic_signature": "axis-G",
        "evidence_paths": ["derive.json"],
    }
    accepted = result_contract.validate(
        "derive",
        consumer,
        "block",
        {"workspace_root": str(tmp_path)},
    )
    assert not {
        code
        for code in finding_codes(accepted)
        if code.startswith("finalization_")
        or code.startswith("authoritative_projection_")
    }

    mismatched = {
        **consumer,
        "finalization_consumption": {**finalized["consumption"], "attempt_revision": 2},
    }
    rejected = result_contract.validate(
        "derive",
        mismatched,
        "block",
        {"workspace_root": str(tmp_path)},
    )
    assert "finalization_consumption_binding_mismatch" in finding_codes(rejected)


def test_cross_attempt_cas_is_not_same_attempt_supersession(tmp_path: Path) -> None:
    first = finalized_bundle(tmp_path)
    first_receipt = first["receipt"]
    second_candidate = {
        **first["candidate"],
        "attempt_id": "attempt-B",
        "expected_previous_revision": first_receipt["attempt_revision"],
        "expected_previous_attempt_id": first_receipt["attempt_id"],
        "expected_previous_finalization_token": first_receipt["finalization_token"],
        "durable_state_candidate": cycle_ledger.build_no_durable_state_change_candidate(
            attempt_identity="attempt-B",
            reason_id="validation-has-no-durable-axis-change",
            evidence=absent_no_change_evidence("attempt-B"),
        ),
    }
    second = cycle_ledger.finalize_candidate(tmp_path, "cycle-final", second_candidate)
    second_receipt = second["finalization_receipt"]

    assert second_receipt["attempt_revision"] == 1
    assert second_receipt["supersedes_revision"] is None
    assert second_receipt["supersedes_finalization_token"] is None
    assert finalization_contract.receipt_shape_errors(second_receipt) == []


def test_projection_preserves_task_acceptance_separately_from_goal_progress() -> None:
    projection = {
        "verdict_contract_version": 1,
        **{
            axis: {"status": "pass", "evidence_ref": "evidence-E"}
            for axis in finalization_contract.VERDICT_AXES
        },
        "authoritative_final": "failure",
    }
    projection["goal_readiness_verdict"] = {
        "status": "fail",
        "evidence_ref": "evidence-G",
    }

    assert finalization_contract.projection_conclusions(projection) == (
        "passed",
        "no_progress",
    )

    projection["goal_readiness_verdict"] = {"status": "not_applicable"}
    projection["authoritative_final"] = "success"
    assert finalization_contract.projection_conclusions(projection) == (
        "passed",
        "no_progress",
    )


def test_report_and_dashboard_share_task_pass_goal_fail_projection(
    tmp_path: Path,
) -> None:
    finalized = finalized_bundle(
        tmp_path,
        axis_statuses={"goal_readiness_verdict": "fail"},
    )
    validate_event = {
        "cycle_id": "cycle-final",
        "step": "validate",
        "status": "complete",
        "task_id": "task-1",
        "validation_verdict": "complete",
        "progress_verdict": "no_progress",
        "blockers": [],
        "finalization_applicability": "required",
        "finalization_receipt": finalized["receipt"],
        "authoritative_projection": finalized["projection"],
    }
    stage = {
        "task_id": "task-1",
        "next_task_id": "task-2",
        "blockers": [],
        "events": [
            validate_event,
            {
                "cycle_id": "cycle-final",
                "step": "issue",
                "status": "not_applicable",
                "task_id": "task-1",
            },
            {
                "cycle_id": "cycle-final",
                "step": "derive",
                "status": "complete",
                "task_id": "task-1",
            },
            {
                "cycle_id": "cycle-final",
                "step": "commit",
                "status": "complete",
                "task_id": "task-1",
            },
            {
                "cycle_id": "cycle-final",
                "step": "dashboard",
                "status": "complete",
                "task_id": "task-1",
            },
        ],
    }
    report = assemble_cycle_report.assemble(
        context={"workspace_root": str(tmp_path)},
        stage=stage,
        validation={
            **validate_event,
            "commands": [{"command": "pytest", "status": "passed"}],
            "evidence_paths": ["validation.json"],
        },
        progress={},
        commit={"task_id": "task-1", "commit_status": "committed"},
        closeout_commit={},
    )
    rows = [
        {
            "cycle_id": "cycle-final",
            "step": "context",
            "status": "complete",
            "task_id": "task-1",
        },
        validate_event,
    ]
    dashboard = render_cycle_dashboard.summarize(
        rows,
        {"event_count": len(rows)},
        "loaded",
        "cycle-final",
        tmp_path,
    )

    assert report["validation_verdict"] == "passed"
    assert report["progress_verdict"] == "no_progress"
    assert report["completion_status"] == "not_complete"
    assert report["authoritative_final"] == "failure"
    assert dashboard["validation_verdict"] == "passed"
    assert dashboard["progress_verdict"] == "no_progress"
    assert dashboard["authoritative_final"] == "failure"
    assert dashboard["dashboard_status"] == "rendered"
    assert (
        report["finalization_receipt"]["authoritative_projection_digest"]
        == dashboard["finalization_receipt"]["authoritative_projection_digest"]
    )


def test_dashboard_uses_current_pointer_when_ledger_receipt_echo_is_absent(
    tmp_path: Path,
) -> None:
    finalized = finalized_bundle(tmp_path)
    rows = [
        {
            "cycle_id": "cycle-final",
            "step": "context",
            "status": "complete",
            "task_id": "task-1",
        },
        {
            "cycle_id": "cycle-final",
            "step": "validate",
            "status": "complete",
            "task_id": "task-1",
            "validation_verdict": "complete",
            "progress_verdict": "advanced",
            "finalization_applicability": "required",
        },
    ]

    summary = render_cycle_dashboard.summarize(
        rows,
        {"event_count": len(rows)},
        "loaded",
        "cycle-final",
        tmp_path,
    )

    assert summary["dashboard_status"] == "rendered"
    assert summary["finalization_receipt"] == finalized["receipt"]
    assert summary["authoritative_projection"] == finalized["projection"]


def test_report_and_dashboard_reject_noncurrent_projection_echo(tmp_path: Path) -> None:
    finalized = finalized_bundle(tmp_path)
    tampered_projection = {
        **finalized["projection"],
        "goal_readiness_verdict": {"status": "fail", "evidence_ref": "other-E"},
        "authoritative_final": "failure",
    }
    validate_event = {
        "cycle_id": "cycle-final",
        "step": "validate",
        "status": "complete",
        "task_id": "task-1",
        "validation_verdict": "complete",
        "progress_verdict": "advanced",
        "finalization_applicability": "required",
        "finalization_receipt": finalized["receipt"],
        "authoritative_projection": tampered_projection,
    }
    report = assemble_cycle_report.assemble(
        context={"workspace_root": str(tmp_path)},
        stage={"task_id": "task-1", "events": [validate_event]},
        validation=validate_event,
        progress={},
        commit={},
        closeout_commit={},
    )
    dashboard = render_cycle_dashboard.summarize(
        [validate_event],
        {"event_count": 1},
        "loaded",
        "cycle-final",
        tmp_path,
    )

    assert "authoritative_projection_report_input_mismatch" in {
        row["code"] for row in report["report_findings"]
    }
    assert dashboard["dashboard_status"] == "block"
    assert "dashboard_event_projection_not_current" in {
        row["code"] for row in dashboard["findings"]
    }
    assert report["authoritative_projection"] == finalized["projection"]
    assert dashboard["authoritative_projection"] == finalized["projection"]


def test_report_blocks_missing_and_stale_finalization_receipts(tmp_path: Path) -> None:
    missing = assemble_cycle_report.assemble(
        context={"workspace_root": str(tmp_path)},
        stage={"task_id": "task-1", "blockers": []},
        validation={
            "task_id": "task-1",
            "validation_verdict": "complete",
            "progress_verdict": "advanced",
            "blockers": [],
        },
        progress={},
        commit={},
        closeout_commit={},
    )
    assert "finalization_receipt_missing" in {
        row["code"] for row in missing["report_findings"]
    }

    first = finalized_bundle(tmp_path)
    receipt = first["receipt"]
    correction = {
        **first["candidate"],
        "expected_previous_revision": receipt["attempt_revision"],
        "expected_previous_attempt_id": receipt["attempt_id"],
        "expected_previous_finalization_token": receipt["finalization_token"],
        "goal_readiness_verdict": {"status": "fail", "evidence_ref": "goal-E"},
    }
    cycle_ledger.finalize_candidate(tmp_path, "cycle-final", correction)
    stale = assemble_cycle_report.assemble(
        context={"workspace_root": str(tmp_path)},
        stage={"task_id": "task-1", "blockers": []},
        validation={
            "task_id": "task-1",
            "validation_verdict": "complete",
            "progress_verdict": "advanced",
            "blockers": [],
            "finalization_receipt": first["receipt"],
            "authoritative_projection": first["projection"],
        },
        progress={},
        commit={},
        closeout_commit={},
    )

    assert "finalization_receipt_current_verification_failed" in {
        row["code"] for row in stale["report_findings"]
    }


def test_receipt_rejects_unknown_authoritative_final_even_with_rehashed_body(
    tmp_path: Path,
) -> None:
    finalized = finalized_bundle(tmp_path)
    malformed = {**finalized["receipt"], "authoritative_final": "optimistic"}
    malformed["receipt_hash"] = finalization_contract.canonical_digest(
        {key: value for key, value in malformed.items() if key != "receipt_hash"}
    )

    assert "finalization_receipt_authoritative_final_invalid" in {
        row["code"] for row in finalization_contract.receipt_shape_errors(malformed)
    }


def test_governed_validate_requires_candidate_while_legacy_diagnostic_stays_readable() -> (
    None
):
    base = {
        "step": "validate",
        "task_id": "task-1",
        "validation_verdict": "partial",
        "progress_verdict": "no_progress",
        "blockers": [],
        "evidence_paths": ["validation.json"],
    }
    legacy = result_contract.validate("validate", base, "block")
    governed = result_contract.validate(
        "validate",
        {
            **base,
            "finalization_contract_version": 1,
            "finalization_applicability": "required",
        },
        "block",
    )

    assert "final_candidate_missing" not in finding_codes(legacy)
    assert "final_candidate_missing" in finding_codes(governed)


def test_ordinary_derive_requires_receipt_but_bootstrap_and_reasoned_repair_do_not() -> (
    None
):
    base = {
        "step": "derive",
        "next_task_id": "task-2",
        "selected_task_source": "task_backlog",
        "progress_kind": "goal_productive",
        "semantic_signature": "axis-G",
        "evidence_paths": ["derive.json"],
    }
    ordinary = result_contract.validate("derive", base, "block")
    bootstrap = result_contract.validate(
        "derive",
        {**base, "derive_mode": "initial_init"},
        "block",
    )
    repair = result_contract.validate(
        "derive",
        {
            **base,
            "finalization_applicability": "not_applicable",
            "finalization_not_applicable_reason": "no-predecessor-attempt",
            "prior_final_attempt_exists": False,
            "transition_kind": "unrelated_state_repair",
        },
        "block",
    )

    assert "finalization_receipt_missing" in finding_codes(ordinary)
    assert "finalization_receipt_missing" not in finding_codes(bootstrap)
    assert "finalization_receipt_missing" not in finding_codes(repair)


def test_option_inventory_completeness_is_typed_and_does_not_invent_classes() -> None:
    base = {
        "step": "validate",
        "task_id": "task-1",
        "validation_verdict": "partial",
        "progress_verdict": "no_progress",
        "blockers": [],
        "evidence_paths": ["validation.json"],
    }
    complete_absence = {
        "schema_version": 1,
        "inventory_status": "complete",
        "options": [
            {
                "option_id": "option-wait",
                "option_class": "terminal_or_wait",
                "applicability": "applicable",
                "evidence_ids": ["authority-E"],
            }
        ],
        "blocker_removing_option_present": False,
        "blocker_removing_absence_reason": "producer-map-empty",
        "blocker_removing_absence_evidence_ids": ["producer-map-E"],
        "options_incomplete": False,
    }
    accepted = result_contract.validate(
        "validate", {**base, "option_inventory": complete_absence}, "block"
    )
    incomplete_terminal = result_contract.validate(
        "validate",
        {
            **base,
            "terminal_state": True,
            "option_inventory": {
                **complete_absence,
                "inventory_status": "incomplete",
                "options_incomplete": True,
            },
        },
        "block",
    )
    omitted_removing = result_contract.validate(
        "validate",
        {
            **base,
            "option_inventory": {
                **complete_absence,
                "options": [
                    {
                        "option_id": "option-grant",
                        "option_class": "blocker_removing",
                        "applicability": "applicable",
                        "evidence_ids": ["producer-map-E"],
                    }
                ],
            },
        },
        "block",
    )

    assert not {
        code
        for code in finding_codes(accepted)
        if code.startswith("option_") or code.startswith("blocker_removing_")
    }
    assert "incomplete_options_control_terminal_or_authority" in finding_codes(
        incomplete_terminal
    )
    assert "blocker_removing_option_presence_mismatch" in finding_codes(
        omitted_removing
    )


def test_operation_matrix_separates_diagnostic_read_from_state_change() -> None:
    base = {
        "step": "validate",
        "task_id": "task-1",
        "validation_verdict": "partial",
        "progress_verdict": "no_progress",
        "blockers": [],
        "evidence_paths": ["validation.json"],
    }
    operations = {
        operation: {
            "status": "allowed" if operation == "read_diagnostic" else "blocked",
            "evidence_ids": [f"{operation}-E"],
        }
        for operation in lifecycle_contract.OPERATIONS
    }
    matrix = {
        "schema_version": 1,
        "matrix_status": "complete",
        "operations": operations,
    }
    read_without_matrix = result_contract.validate(
        "validate",
        {**base, "requested_operation": "read_diagnostic", "operation_consumed": True},
        "block",
    )
    read_without_authority = result_contract.validate(
        "validate",
        {
            **base,
            "gate_operation_applicability": matrix,
            "requested_operation": "read_diagnostic",
            "operation_consumed": True,
        },
        "block",
    )
    read_contract = {
        "authority_status": "verified",
        "safety_status": "verified",
        "privacy_status": "verified",
        "provenance_status": "verified",
        "receipt_ref": "receipt-R",
        "receipt_hash": "a" * 64,
    }
    read_allowed = result_contract.validate(
        "validate",
        {
            **base,
            "gate_operation_applicability": {**matrix, "read_contract": read_contract},
            "requested_operation": "read_diagnostic",
            "operation_consumed": True,
        },
        "block",
    )
    unknown_operations = {
        **operations,
        "promote_or_adopt": {"status": "unknown", "evidence_ids": []},
    }
    promotion_unknown = result_contract.validate(
        "validate",
        {
            **base,
            "gate_operation_applicability": {
                "schema_version": 1,
                "matrix_status": "complete",
                "operations": unknown_operations,
            },
            "requested_operation": "promote_or_adopt",
            "operation_consumed": True,
        },
        "block",
    )

    assert "gate_operation_applicability_missing" in finding_codes(read_without_matrix)
    assert "read_diagnostic_contract_unverified" in finding_codes(
        read_without_authority
    )
    assert "read_diagnostic_contract_unverified" not in finding_codes(read_allowed)
    assert "state_changing_operation_scope_unknown" in finding_codes(promotion_unknown)
    assert "gate_operation_not_allowed_for_consumption" in finding_codes(
        promotion_unknown
    )


def test_pending_advice_with_explicit_disposition_is_warn_only_and_non_authoritative() -> (
    None
):
    payload = {
        "step": "validate",
        "task_id": "task-1",
        "validation_verdict": "partial",
        "progress_verdict": "no_progress",
        "blockers": [],
        "evidence_paths": ["validation.json"],
        "active_advice_count": 1,
        "advice_deferred_reason": "pending-intake-review",
        "advice_consumption_states": [
            {
                "clause_id": "clause-Q",
                "state": "pending",
                "consumer_context_id": "consumer-C",
            }
        ],
    }
    result = result_contract.validate("validate", payload, "warn")

    assert "active_advice_unhandled" not in finding_codes(result)
    assert result["status"] != "block"
    assert payload["validation_verdict"] == "partial"
    assert "authoritative_final" not in payload


def test_validate_accepts_explicit_empty_blockers() -> None:
    result = result_contract.validate(
        "validate",
        {
            "step": "validate",
            "task_id": "task-1",
            "validation_verdict": "partial",
            "progress_verdict": "no_progress",
            "blockers": [],
            "evidence_paths": ["validation.json"],
            "agent_routing_applicability": "deterministic_only",
        },
        "block",
    )

    assert "missing_required_field" not in finding_codes(result)


def test_commit_role_mismatch_blocks_in_block_mode() -> None:
    result = result_contract.validate(
        "closeout_commit",
        {
            "step": "closeout_commit",
            "commit_role": "implementation",
            "commit_status": "skipped",
            "commit_skipped_reason": "no changes",
            "tracked_artifacts": [],
            "evidence_paths": ["commit.json"],
            "agent_routing_applicability": "deterministic_only",
        },
        "block",
    )

    assert result["status"] == "block"
    assert "commit_role_mismatch" in finding_codes(result)


def test_report_assembler_output_is_directly_contract_validatable() -> None:
    report = assemble_cycle_report.assemble(
        context={},
        stage={
            "task_id": "task-1",
            "blockers": [],
            "used_goal_truth": [],
            "used_advice": [],
        },
        validation={
            "task_id": "task-1",
            "validation_verdict": "partial",
            "progress_verdict": "no_progress",
            "blockers": [],
            "progress_axes": {},
        },
        progress={},
        commit={},
        closeout_commit={},
    )
    validated = result_contract.validate("report", report, "block")

    assert report["blockers"] == []
    assert report["used_advice"] == []
    assert validated["status"] != "block", validated


def test_report_assembler_recognizes_validator_complete_vocabulary(
    tmp_path: Path,
) -> None:
    finalized = finalized_bundle(tmp_path)
    report = assemble_cycle_report.assemble(
        context={"workspace_root": str(tmp_path)},
        stage={
            "task_id": "task-1",
            "next_task_id": "task-2",
            "blockers": [],
            "used_goal_truth": [],
            "used_advice": [],
            "events": [
                {"step": "issue", "status": "not_applicable", "task_id": "task-1"},
                {
                    "step": "derive",
                    "status": "complete",
                    "task_id": "task-1",
                    "next_task_id": "task-2",
                },
                {"step": "commit", "status": "complete", "task_id": "task-1"},
                {"step": "dashboard", "status": "complete", "task_id": "task-1"},
            ],
        },
        validation={
            "task_id": "task-1",
            "validation_verdict": "complete",
            "progress_verdict": "advanced",
            "blockers": [],
            "progress_axes": {"behavior": "advanced"},
            "validation_commands": [
                {"command": "python -m pytest -q", "status": "passed"}
            ],
            "evidence_paths": ["validation.json"],
            "finalization_receipt": finalized["receipt"],
            "authoritative_projection": finalized["projection"],
        },
        progress={},
        commit={
            "task_id": "task-1",
            "commit_status": "committed",
            "evidence_paths": ["commit.json"],
        },
        closeout_commit={},
    )

    assert report["completion_status"] == "complete_verified"
    assert report["validation_verdict"] == "passed"


def test_report_completion_rejects_cross_task_closure_and_failed_commit(
    tmp_path: Path,
) -> None:
    finalized = finalized_bundle(tmp_path)
    report = assemble_cycle_report.assemble(
        context={"workspace_root": str(tmp_path)},
        stage={
            "task_id": "task-a",
            "next_task_id": "task-b",
            "blockers": [],
            "events": [
                {"step": "issue", "status": "complete", "task_id": "task-other"},
                {
                    "step": "derive",
                    "status": "complete",
                    "task_id": "task-other",
                    "next_task_id": "task-b",
                },
                {"step": "dashboard", "status": "complete", "task_id": "task-other"},
            ],
        },
        validation={
            "task_id": "task-a",
            "validation_verdict": "complete",
            "progress_verdict": "advanced",
            "blockers": [],
            "progress_axes": {"behavior": "advanced"},
            "commands": [{"command": "pytest", "status": "failed"}],
            "evidence_paths": ["validation.json"],
            "finalization_receipt": finalized["receipt"],
            "authoritative_projection": finalized["projection"],
        },
        progress={},
        commit={
            "task_id": "task-other",
            "commit_status": "failed",
            "commit_skipped_reason": "tests failed",
        },
        closeout_commit={},
    )

    validated = result_contract.validate(
        "report", report, "block", {"workspace_root": str(tmp_path)}
    )

    assert report["completion_status"] == "not_complete"
    assert "report_completion_evidence_incomplete" in finding_codes(validated)
    assert validated["status"] == "block"


def test_report_assembler_blocks_placeholder_only_completion(tmp_path: Path) -> None:
    finalized = finalized_bundle(tmp_path)
    report = assemble_cycle_report.assemble(
        context={"workspace_root": str(tmp_path)},
        stage={},
        validation={
            "validation_verdict": "complete",
            "progress_verdict": "advanced",
            "blockers": [],
            "finalization_receipt": finalized["receipt"],
            "authoritative_projection": finalized["projection"],
        },
        progress={},
        commit={},
        closeout_commit={},
    )

    validated = result_contract.validate(
        "report", report, "block", {"workspace_root": str(tmp_path)}
    )

    assert report["completion_status"] == "not_complete"
    assert "report_completion_evidence_incomplete" in finding_codes(validated)
    assert validated["status"] == "block"


def test_report_assembler_does_not_discard_malformed_blockers() -> None:
    report = assemble_cycle_report.assemble(
        context={},
        stage={"task_id": "task-1", "next_task_id": "task-2"},
        validation={
            "task_id": "task-1",
            "validation_verdict": "complete",
            "progress_verdict": "advanced",
            "blockers": "UNRESOLVED",
        },
        progress={},
        commit={},
        closeout_commit={},
    )

    validated = result_contract.validate("report", report, "block")

    assert report["completion_status"] == "not_complete"
    assert "invalid_report_blockers_input" in finding_codes(validated)
    assert validated["status"] == "block"


def test_report_explicit_empty_usage_does_not_claim_context_inventory() -> None:
    report = assemble_cycle_report.assemble(
        context={
            "agent_goal": {"used_goal_truth": [".agent_goal/final_goal.md"]},
            "external_advice": {
                "active_files": [{"path": ".agent_advice/active/note.md"}]
            },
        },
        stage={
            "task_id": "task-1",
            "used_goal_truth": [],
            "used_advice": [],
            "blockers": [],
        },
        validation={
            "task_id": "task-1",
            "validation_verdict": "partial",
            "progress_verdict": "no_progress",
            "blockers": [],
        },
        progress={},
        commit={},
        closeout_commit={},
    )

    assert report["used_goal_truth"] == []
    assert report["used_advice"] == []


def test_report_contract_rejects_inconsistent_complete_verified() -> None:
    report = assemble_cycle_report.assemble(
        context={},
        stage={
            "task_id": "task-1",
            "next_task_id": "task-2",
            "blockers": [],
            "used_goal_truth": [],
            "used_advice": [],
        },
        validation={
            "task_id": "task-1",
            "validation_verdict": "partial",
            "progress_verdict": "advanced",
            "blockers": [],
        },
        progress={},
        commit={},
        closeout_commit={},
    )
    report["completion_status"] = "complete_verified"

    validated = result_contract.validate("report", report, "block")

    assert validated["status"] == "block"
    assert "report_complete_verified_inconsistent" in finding_codes(validated)


def current_validate_packet(**overrides: Any) -> dict[str, Any]:
    evidence_ref = "packet_K.json"
    identity = legacy_identity()
    packet: dict[str, Any] = {
        "step": "validate",
        "task_id": "item_I",
        "validation_verdict": "complete",
        "progress_verdict": "advanced",
        "blockers": [],
        "evidence_paths": [evidence_ref],
        "agent_routing_applicability": "deterministic_only",
        "decision_contract_version": 1,
        "decision_artifact_ref": identity,
        "legacy_revision_bridge_receipt": legacy_revision_bridge(identity),
        "verdict_contract_version": 1,
    }
    for axis in (
        "task_acceptance_verdict",
        "artifact_truth_verdict",
        "artifact_semantic_verdict",
        "pack_transition_verdict",
        "historical_index_verdict",
        "goal_readiness_verdict",
    ):
        packet[axis] = {"status": "pass", "evidence_ref": evidence_ref}
    packet.update(overrides)
    return packet


def acceptance_scenario(**overrides: Any) -> dict[str, Any]:
    scenario: dict[str, Any] = {
        "scenario_id": "scenario_A",
        "premise_predicate_id": "predicate_P",
        "expected_terminal_state": "blocked",
    }
    scenario.update(overrides)
    return scenario


def premise_receipt(**overrides: Any) -> dict[str, Any]:
    receipt: dict[str, Any] = {
        "scenario_id": "scenario_A",
        "premise_predicate_id": "predicate_P",
        "premise_evaluation_status": "pass",
        "premise_satisfying_item_count": 1,
        "invocation_kind": "api",
        "invocation_descriptor_id": "invocation_I",
        "invocation_component_ids": [
            "action:execute-scenario",
            "param:scenario-id",
            "ref:scenario-A",
        ],
        "input_revision_ids": ["input_revision_R"],
        "result_digest": "c" * 64,
        "expected_terminal_state": "blocked",
        "observed_terminal_state": "blocked",
        "run_id": "run_R",
        "evidence_ref": "evidence_E.json",
    }
    receipt.update(overrides)
    if "canonical_invocation_digest" not in overrides:
        receipt["canonical_invocation_digest"] = canonical_invocation_sha256(
            scenario_id=str(receipt.get("scenario_id") or ""),
            premise_predicate_id=str(receipt.get("premise_predicate_id") or ""),
            invocation_kind=str(receipt.get("invocation_kind") or ""),
            invocation_descriptor_id=str(receipt.get("invocation_descriptor_id") or ""),
            invocation_component_ids=receipt.get("invocation_component_ids", []),
            input_revision_ids=receipt.get("input_revision_ids", []),
        )
    return receipt


def scoped_progress_fields(
    *,
    effective_progress_class: str = "task_local",
    changed_files: list[str] | None = None,
    expected_scope: str = "global",
    expected_progress_cap: str = "semantic",
    global_applicability: str = "applicable",
) -> dict[str, Any]:
    retained_paths = changed_files or ["tests/test_bounded_fixture.py"]
    file_changes = []
    for index, path in enumerate(retained_paths, start=1):
        row = {
            "path": path,
            "change_kind": "modified",
            "subject_id": f"retained_subject_{index}",
            "before_sha256": f"{index % 10}" * 64,
            "after_sha256": f"{(index + 1) % 10}" * 64,
        }
        row["receipt_sha256"] = canonical_file_change_receipt_sha256(row)
        file_changes.append(row)
    return {
        "progress_scope_contract": {
            "task_family_id": "task_family_F",
            "root_family_id": "root_family_R",
            "global_scope_applicability": global_applicability,
            "global_goal_axis_id": "goal_axis_G"
            if global_applicability == "applicable"
            else None,
            "task_terminal_predicate_id": "task_predicate_T",
            "root_terminal_predicate_id": "root_predicate_R",
            "global_terminal_predicate_id": "goal_predicate_G"
            if global_applicability == "applicable"
            else None,
            "identity_basis_id": "basis_B",
        },
        "work_intent": {
            "selected_transition_kind": "bounded_transition",
            "expected_scope": expected_scope,
            "expected_progress_cap": expected_progress_cap,
        },
        "progress_observations": {
            "task_scope": {
                "terminal_outcome_changed": True,
                "progress_class": "task_local",
            },
            "root_scope": {
                "comparison_status": "comparable",
                "movement_status": "flat",
                "residual_relation_status": "unchanged",
                "independent_verification_status": "unverified",
                "progress_class": "none",
            },
            "global_scope": {
                "movement_status": "flat",
                "progress_class": "none",
            },
        },
        "closeout_projection": {
            "task_acceptance": "pass",
            "review_axis": "unavailable",
            "global_readiness": "blocked",
            "task_lifecycle": "completed_local",
            "successor_state": "terminal_wait",
        },
        "actual_changed_files": retained_paths,
        "retained_change_evidence": {"file_changes": file_changes},
        "retained_change_classification": {
            "producer_body_changed": False,
            "producer_source_changed": False,
            "semantic_logic_changed": False,
            "tests_only_changed": True,
            "schema_or_verifier_only_changed": False,
            "lifecycle_only_changed": False,
            "effective_progress_class": effective_progress_class,
        },
    }


def goal_axis_map_receipt(
    *, owner_id: str, revision_id: str, map_sha256: str, adapter_revision: str
) -> dict[str, Any]:
    receipt: dict[str, Any] = {
        "contract_version": 1,
        "receipt_id": "goal_axis_receipt_A",
        "hook_id": "goal_axis_map",
        "owner_id": owner_id,
        "map_revision_id": revision_id,
        "map_sha256": map_sha256,
        "adapter_revision_sha256": adapter_revision,
        "consumer_id": "loopback_consumer_A",
        "consumer_revision_sha256": "e" * 64,
        "validator_signature_sha256": VALIDATOR_SIGNATURE_SHA256,
        "hook_input_sha256": "f" * 64,
        "hook_output_sha256": map_sha256,
        "invocation_status": "completed",
        "return_contract_status": "pass",
        "decision_consumption_status": "consumed",
        "evidence_id": "axis_evidence_A",
        "evidence_sha256": "9" * 64,
    }
    receipt["receipt_sha256"] = canonical_goal_axis_receipt_sha256(receipt)
    return receipt


def independent_observation_receipt(
    subject_id: str, *, observed_relation: str = "improved"
) -> dict[str, Any]:
    receipt: dict[str, Any] = {
        "contract_version": 1,
        "receipt_id": f"independent_receipt_{subject_id}",
        "subject_id": subject_id,
        "observation_id": f"observation_{subject_id}",
        "producer_owner_id": f"producer_owner_{subject_id}",
        "verifier_owner_id": f"verifier_owner_{subject_id}",
        "producer_invariant_id": f"producer_invariant_{subject_id}",
        "verifier_invariant_id": f"verifier_invariant_{subject_id}",
        "producer_input_ids": [f"producer_input_{subject_id}"],
        "verification_input_ids": [f"verifier_input_{subject_id}"],
        "source_overlap_status": "disjoint",
        "invariant_separation_status": "independent",
        "before_revision_id": f"before_revision_{subject_id}",
        "before_sha256": "2" * 64,
        "after_revision_id": f"after_revision_{subject_id}",
        "after_sha256": "3" * 64,
        "comparison_basis_id": f"basis_{subject_id}",
        "comparison_input_sha256": "4" * 64,
        "observed_relation": observed_relation,
        "evidence_id": f"evidence_{subject_id}",
        "evidence_sha256": "5" * 64,
    }
    receipt["receipt_sha256"] = canonical_independent_observation_receipt_sha256(
        receipt
    )
    return receipt


def self_grounded_receipt_fields() -> dict[str, Any]:
    contract: dict[str, Any] = {
        "contract_version": 1,
        "owner_id": "owner_R",
        "contract_id": "contract_R",
        "predicate_id": "predicate_R",
        "invariant_class": "deterministic_self_grounded",
        "adapter_revision_sha256": "a" * 64,
        "evidence_id": "contract_evidence_R",
        "evidence_sha256": "b" * 64,
    }
    contract["receipt_sha256"] = canonical_self_grounded_receipt_sha256(contract)
    calculation: dict[str, Any] = {
        "contract_version": 1,
        "receipt_id": "calculation_receipt_R",
        "contract_id": "contract_R",
        "calculation_id": "calculation_R",
        "calculation_revision_id": "calculation_revision_R",
        "input_sha256": "c" * 64,
        "output_sha256": "d" * 64,
        "calculator_id": "calculator_R",
        "outcome": "pass",
        "evidence_id": "calculation_evidence_R",
        "evidence_sha256": "e" * 64,
    }
    calculation["receipt_sha256"] = canonical_self_grounded_receipt_sha256(calculation)
    replay: dict[str, Any] = {
        "contract_version": 1,
        "receipt_id": "replay_receipt_R",
        "contract_id": "contract_R",
        "predicate_id": "predicate_R",
        "input_revision_id": "input_revision_R",
        "input_sha256": "f" * 64,
        "replay_executor_id": "replay_executor_R",
        "outcome": "pass",
        "calculation_input_sha256": calculation["input_sha256"],
        "evidence_id": "replay_evidence_R",
        "evidence_sha256": "1" * 64,
    }
    replay["receipt_sha256"] = canonical_self_grounded_receipt_sha256(replay)
    return {
        "self_grounded_owner_id": "owner_R",
        "self_grounded_contract_id": "contract_R",
        "self_grounded_contract_receipt": contract,
        "self_grounded_contract_receipt_sha256": contract["receipt_sha256"],
        "premise_replay_receipt": replay,
        "premise_replay_receipt_sha256": replay["receipt_sha256"],
        "calculation_receipt": calculation,
        "calculation_receipt_sha256": calculation["receipt_sha256"],
    }


def test_scenario_premise_receipt_is_recomputed_instead_of_trusting_booleans() -> None:
    declared_only = current_validate_packet(
        acceptance_scenarios=[acceptance_scenario()],
        acceptance_scenario_gate={
            "scenario_uncovered": False,
            "acceptance_inversion": False,
            "scenario_coverage": [
                {
                    "scenario_id": "scenario_A",
                    "premise_satisfied": True,
                    "observed_terminal_state": "blocked",
                }
            ],
        },
    )

    result = result_contract.validate("validate", declared_only, "block")
    codes = finding_codes(result)

    assert "validate_scenario_receipt_malformed" in codes
    assert "validate_scenario_receipt_uncovered" in codes
    assert "validate_scenario_coverage_claim_mismatch" in codes
    assert "validate_complete_with_scenario_uncovered" in codes


def test_scenario_premise_receipt_requires_recomputed_body_free_invocation() -> None:
    digest_bound = current_validate_packet(
        acceptance_scenarios=[acceptance_scenario()],
        acceptance_scenario_gate={"premise_receipts": [premise_receipt()]},
    )
    digest_codes = finding_codes(
        result_contract.validate("validate", digest_bound, "block")
    )
    assert (
        not {
            "validate_scenario_receipt_malformed",
            "validate_scenario_receipt_uncovered",
            "validate_complete_with_scenario_uncovered",
            "validate_complete_with_acceptance_inversion",
        }
        & digest_codes
    )

    cli_receipt = premise_receipt(
        invocation_kind="cli",
        invocation_component_ids=[
            "cmd:scenario-tool",
            "flag:scenario-id",
            "ref:scenario-A",
        ],
        command_argv=[
            "cmd:scenario-tool",
            "flag:scenario-id",
            "ref:scenario-A",
        ],
    )
    argv_bound = current_validate_packet(
        acceptance_scenarios=[acceptance_scenario()],
        acceptance_scenario_gate={"premise_receipts": [cli_receipt]},
    )
    argv_codes = finding_codes(
        result_contract.validate("validate", argv_bound, "block")
    )
    assert "validate_scenario_receipt_malformed" not in argv_codes
    assert "validate_scenario_receipt_uncovered" not in argv_codes


def test_scenario_receipt_rejects_arbitrary_digest_and_raw_cli_values() -> None:
    arbitrary = premise_receipt(canonical_invocation_digest="b" * 64)
    arbitrary_codes = finding_codes(
        result_contract.validate(
            "validate",
            current_validate_packet(
                acceptance_scenarios=[acceptance_scenario()],
                acceptance_scenario_gate={"premise_receipts": [arbitrary]},
            ),
            "block",
        )
    )
    assert "validate_scenario_receipt_malformed" in arbitrary_codes

    raw_cli = premise_receipt(
        invocation_kind="cli",
        invocation_component_ids=[
            "cmd:scenario-tool",
            "flag:source-path",
            "/private/source/chapter.txt",
        ],
        command_argv=[
            "cmd:scenario-tool",
            "flag:source-path",
            "/private/source/chapter.txt",
        ],
    )
    raw_codes = finding_codes(
        result_contract.validate(
            "validate",
            current_validate_packet(
                acceptance_scenarios=[acceptance_scenario()],
                acceptance_scenario_gate={"premise_receipts": [raw_cli]},
            ),
            "block",
        )
    )
    assert "validate_scenario_receipt_malformed" in raw_codes


def test_scenario_receipt_binds_predicate_revisions_result_and_run_evidence() -> None:
    malformed = premise_receipt(
        premise_predicate_id="predicate_other",
        premise_satisfying_item_count=0,
        input_revision_ids=[],
        result_digest="short",
        run_id="",
        evidence_ref="",
    )
    packet = current_validate_packet(
        acceptance_scenarios=[acceptance_scenario()],
        acceptance_scenario_gate={
            "scenario_uncovered": False,
            "premise_receipts": [malformed],
        },
    )

    result = result_contract.validate("validate", packet, "block")
    receipt_findings = [
        finding
        for finding in result["findings"]
        if finding.get("code") == "validate_scenario_receipt_malformed"
    ]

    assert receipt_findings
    invalid_fields = set(receipt_findings[0]["evidence"]["invalid_fields"])
    assert {
        "premise_predicate_id_binding",
        "premise_evaluation_status",
        "premise_satisfying_item_count",
        "input_revision_ids",
        "result_digest",
        "run_id",
        "evidence_ref",
    } <= invalid_fields
    assert result["status"] == "block"


def test_scenario_receipt_recomputes_terminal_inversion() -> None:
    inverted = current_validate_packet(
        acceptance_scenarios=[acceptance_scenario()],
        acceptance_scenario_gate={
            "acceptance_inversion": False,
            "premise_receipts": [premise_receipt(observed_terminal_state="selected")],
        },
    )

    result = result_contract.validate("validate", inverted, "block")
    codes = finding_codes(result)

    assert "validate_scenario_coverage_claim_mismatch" in codes
    assert "validate_complete_with_acceptance_inversion" in codes
    assert "validate_complete_with_scenario_uncovered" in codes


def test_non_applicable_scenario_contract_preserves_existing_completion_path() -> None:
    packet = current_validate_packet(
        acceptance_scenarios=[{"applicability": "not_applicable"}],
        acceptance_scenario_gate={"evaluation_status": "not_applicable"},
    )

    codes = finding_codes(result_contract.validate("validate", packet, "block"))

    assert not {code for code in codes if "scenario_receipt" in code}
    assert "validate_complete_with_scenario_uncovered" not in codes


def test_run_result_rejects_malformed_declared_receipt_and_accepts_full_receipt() -> (
    None
):
    base_run = {
        "step": "run",
        "task_id": "task_T",
        "execution_status": "success",
        "command_argv": ["scenario-tool", "--run"],
        "blockers": [],
        "evidence_paths": ["evidence_E.json"],
        "premise_receipts": [premise_receipt()],
    }
    accepted = result_contract.validate("run", base_run, "block")
    assert "run_scenario_receipt_malformed" not in finding_codes(accepted)

    malformed = {
        **base_run,
        "premise_receipts": [
            premise_receipt(
                premise_evaluation_status="pass",
                premise_satisfying_item_count=0,
            )
        ],
    }
    rejected = result_contract.validate("run", malformed, "block")
    assert "run_scenario_receipt_malformed" in finding_codes(rejected)
    assert rejected["status"] == "block"


def test_task_local_closeout_preserves_global_intent_without_resetting_stalls() -> None:
    packet = current_validate_packet(
        validation_verdict="complete",
        progress_verdict="no_progress",
        artifact_semantic_verdict={
            "status": "not_evaluated",
            "evidence_ref": "review_unavailable_E.json",
        },
        goal_readiness_verdict={
            "status": "blocked",
            "evidence_ref": "goal_blocked_E.json",
        },
        **scoped_progress_fields(),
    )

    result = result_contract.validate(
        "validate",
        packet,
        "block",
        {"long_run_state_checked": True},
    )
    codes = finding_codes(result)

    assert (
        not {
            "retained_change_classification_mismatch",
            "validate_advanced_from_capped_scoped_progress",
            "completed_local_without_task_acceptance",
            "completed_local_successor_not_evaluated",
            "scoped_global_readiness_overclaimed",
        }
        & codes
    )
    assessment = assess_scoped_progress(packet)
    assert assessment.effective_progress_class == "task_local"
    assert assessment.root_reset_allowed is False
    assert assessment.global_reset_allowed is False


def test_tests_only_retained_change_caps_semantic_and_stall_reset_claims() -> None:
    fields = scoped_progress_fields(effective_progress_class="semantic")
    fields["retained_change_classification"]["tests_only_changed"] = False
    packet = current_validate_packet(
        root_stall_reset=True,
        global_stall_reset=True,
        **fields,
    )

    codes = finding_codes(result_contract.validate("validate", packet, "block"))

    assert "retained_change_classification_mismatch" in codes
    assert "task_local_progress_reset_root_stall" in codes
    assert "nonglobal_progress_reset_global_stall" in codes
    assert "validate_advanced_from_capped_scoped_progress" in codes


def test_retained_change_rejects_path_labels_without_content_bound_receipts() -> None:
    fields = scoped_progress_fields()
    fields.pop("retained_change_evidence")
    labels_only = current_validate_packet(**fields)
    label_codes = finding_codes(
        result_contract.validate("validate", labels_only, "block")
    )
    assert "retained_change_evidence_malformed" in label_codes
    assert "retained_change_evidence_missing" in label_codes

    tampered_fields = scoped_progress_fields()
    tampered_fields["retained_change_evidence"]["file_changes"][0]["after_sha256"] = (
        "f" * 64
    )
    tampered = current_validate_packet(**tampered_fields)
    tampered_codes = finding_codes(
        result_contract.validate("validate", tampered, "block")
    )
    assert "retained_change_evidence_malformed" in tampered_codes
    assert "retained_change_classification_mismatch" in tampered_codes


def test_root_reduction_resets_only_stable_root_with_self_grounded_evidence() -> None:
    fields = scoped_progress_fields(
        effective_progress_class="root_reduction",
        changed_files=["src/producer_engine.py", "tests/test_producer_engine.py"],
        expected_scope="root",
        expected_progress_cap="root_reduction",
    )
    fields["progress_observations"]["root_scope"] = {
        "comparison_status": "comparable",
        "movement_status": "improved",
        "residual_relation_status": "reduced",
        "independent_verification_status": "explicit_self_grounded",
        "self_grounded_contract_status": "verified",
        "premise_replay_status": "pass",
        "observation_binding_status": "exact_bound",
        **self_grounded_receipt_fields(),
        "progress_class": "root_reduction",
    }
    fields["retained_change_classification"].update(
        producer_source_changed=True,
        tests_only_changed=False,
    )
    packet = current_validate_packet(
        progress_verdict="no_progress",
        root_stall_reset=True,
        global_stall_reset=False,
        **fields,
    )

    result = result_contract.validate("validate", packet, "block")
    codes = finding_codes(result)

    assert "root_progress_without_verified_residual_reduction" not in codes
    assert "task_local_progress_reset_root_stall" not in codes
    assert assess_scoped_progress(packet).effective_progress_class == "root_reduction"
    assert assess_scoped_progress(packet).global_reset_allowed is False

    unreplayed_root = {
        key: value
        for key, value in fields["progress_observations"]["root_scope"].items()
        if key != "premise_replay_status"
    }
    unreplayed = {
        **packet,
        "progress_observations": {
            **packet["progress_observations"],
            "root_scope": unreplayed_root,
        },
    }
    unreplayed_codes = finding_codes(
        result_contract.validate("validate", unreplayed, "block")
    )
    assert "root_progress_without_verified_residual_reduction" in unreplayed_codes
    assert "task_local_progress_reset_root_stall" in unreplayed_codes


def test_bare_verified_alias_cannot_reset_stable_root() -> None:
    packet = {
        "progress_observations": {
            "root_scope": {
                "progress_class": "root_reduction",
                "comparison_status": "comparable",
                "movement_status": "improved",
                "residual_relation_status": "reduced",
                "independent_verification_status": "verified",
                "observation_binding_status": "exact_bound",
            }
        }
    }

    assessment = assess_scoped_progress(packet)

    assert assessment.root_reset_allowed is False
    assert assessment.effective_progress_class != "root_reduction"


def test_independent_root_reduction_requires_content_bound_separation_receipt() -> None:
    fields = scoped_progress_fields(
        effective_progress_class="root_reduction",
        changed_files=["src/producer_engine.py"],
        expected_scope="root",
        expected_progress_cap="root_reduction",
    )
    root_scope = {
        "observation_subject_id": "root_family_R",
        "comparison_status": "comparable",
        "movement_status": "improved",
        "residual_relation_status": "reduced",
        "independent_verification_status": "independently_verified",
        "observation_binding_status": "exact_bound",
        "progress_class": "root_reduction",
    }
    fields["progress_observations"]["root_scope"] = root_scope
    fields["retained_change_classification"].update(
        producer_source_changed=True,
        tests_only_changed=False,
    )
    unbound = current_validate_packet(root_stall_reset=True, **fields)
    assert assess_scoped_progress(unbound).root_reset_allowed is False

    root_scope["independent_observation_receipt"] = independent_observation_receipt(
        "root_family_R", observed_relation="reduced"
    )
    bound = current_validate_packet(root_stall_reset=True, **fields)
    bound_codes = finding_codes(result_contract.validate("validate", bound, "block"))

    assert assess_scoped_progress(bound).root_reset_allowed is True
    assert "root_progress_without_verified_residual_reduction" not in bound_codes


def test_global_progress_requires_every_exact_independent_axis() -> None:
    fields = scoped_progress_fields(
        effective_progress_class="semantic",
        changed_files=["src/producer_engine.py"],
    )
    semantic_logic = {
        "subject_id": "producer_logic_L",
        "before_sha256": "a" * 64,
        "after_sha256": "b" * 64,
    }
    semantic_logic["receipt_sha256"] = canonical_role_change_receipt_sha256(
        "semantic_logic", semantic_logic
    )
    fields["retained_change_evidence"]["semantic_logic"] = semantic_logic
    fields["retained_change_classification"].update(
        producer_source_changed=True,
        semantic_logic_changed=True,
        tests_only_changed=False,
    )
    fields["closeout_projection"].update(
        review_axis="pass",
        global_readiness="ready",
        successor_state="derived",
    )
    active_goals = ["goal_A", "goal_B"]
    goal_axis_map = {"goal_A": ["axis_A"], "goal_B": ["axis_B"]}
    fields["goal_axis_completeness_gate"] = {
        "evaluation_status": "pass",
        "active_measurable_goals": active_goals,
        "goal_axis_map": goal_axis_map,
        "goal_axis_map_owner_id": "adapter_A",
        "goal_axis_map_revision_id": "revision_R",
        "goal_axis_map_sha256": canonical_goal_axis_map_sha256(
            active_goals, goal_axis_map
        ),
        "adapter_revision_sha256": "a" * 64,
        "unobserved_goal_axes": [],
    }
    fields["goal_axis_completeness_gate"]["goal_axis_map_receipt"] = (
        goal_axis_map_receipt(
            owner_id="adapter_A",
            revision_id="revision_R",
            map_sha256=fields["goal_axis_completeness_gate"]["goal_axis_map_sha256"],
            adapter_revision="a" * 64,
        )
    )
    fields["progress_observations"]["global_scope"] = {
        "movement_status": "improved",
        "high_water_moved": True,
        "independent_verification_status": "independently_verified",
        "observation_binding_status": "exact_bound",
        "progress_class": "semantic",
        "axis_observations": [
            {
                "axis_id": "axis_A",
                "status": "pass",
                "provenance": "independently_verified",
                "binding_status": "exact_bound",
                "premise_satisfying_item_count": 1,
                "independent_observation_receipt": independent_observation_receipt(
                    "axis_A"
                ),
            },
            {
                "axis_id": "axis_B",
                "status": "pass",
                "provenance": "independently_verified",
                "binding_status": "exact_bound",
                "premise_satisfying_item_count": 1,
                "independent_observation_receipt": independent_observation_receipt(
                    "axis_B"
                ),
            },
        ],
    }
    packet = current_validate_packet(global_stall_reset=True, **fields)

    accepted_codes = finding_codes(
        result_contract.validate("validate", packet, "block")
    )
    assert (
        "global_progress_without_exact_axis_complete_high_water" not in accepted_codes
    )
    assert "nonglobal_progress_reset_global_stall" not in accepted_codes

    unbound = copy.deepcopy(packet)
    for row in unbound["progress_observations"]["global_scope"]["axis_observations"]:
        row.pop("independent_observation_receipt")
    unbound_assessment = assess_scoped_progress(unbound)
    unbound_codes = finding_codes(
        result_contract.validate("validate", unbound, "block")
    )
    assert unbound_assessment.global_reset_allowed is False
    assert "global_progress_without_exact_axis_complete_high_water" in unbound_codes

    conflicted = {
        **packet,
        "progress_observations": {
            **packet["progress_observations"],
            "global_scope": {
                **packet["progress_observations"]["global_scope"],
                "axis_observations": [
                    packet["progress_observations"]["global_scope"][
                        "axis_observations"
                    ][0],
                    {
                        "axis_id": "axis_B",
                        "status": "not_evaluated",
                        "provenance": "independently_verified",
                        "binding_status": "exact_bound",
                        "premise_satisfying_item_count": 1,
                    },
                ],
            },
        },
    }
    conflicted_codes = finding_codes(
        result_contract.validate("validate", conflicted, "block")
    )
    assert "global_progress_without_exact_axis_complete_high_water" in conflicted_codes
    assert "scoped_global_readiness_overclaimed" in conflicted_codes


def test_scalar_axis_completeness_cannot_self_attest_global_progress() -> None:
    fields = scoped_progress_fields(
        effective_progress_class="semantic",
        changed_files=["src/producer_engine.py"],
    )
    semantic_logic = {
        "subject_id": "producer_logic_L",
        "before_sha256": "a" * 64,
        "after_sha256": "b" * 64,
    }
    semantic_logic["receipt_sha256"] = canonical_role_change_receipt_sha256(
        "semantic_logic", semantic_logic
    )
    fields["retained_change_evidence"]["semantic_logic"] = semantic_logic
    fields["retained_change_classification"].update(
        producer_source_changed=True,
        semantic_logic_changed=True,
        tests_only_changed=False,
    )
    fields["closeout_projection"].update(
        review_axis="pass",
        global_readiness="ready",
        successor_state="derived",
    )
    fields["progress_observations"]["global_scope"] = {
        "movement_status": "improved",
        "high_water_moved": True,
        "independent_verification_status": "independently_verified",
        "observation_binding_status": "exact_bound",
        "progress_class": "semantic",
        "axis_completeness_status": "complete",
    }
    packet = current_validate_packet(global_stall_reset=True, **fields)

    assessment = assess_scoped_progress(packet)
    codes = finding_codes(result_contract.validate("validate", packet, "block"))

    assert assessment.global_axes_complete is False
    assert assessment.global_reset_allowed is False
    assert assessment.effective_progress_class != "semantic"
    assert "global_progress_without_exact_axis_complete_high_water" in codes
    assert "scoped_global_readiness_overclaimed" in codes
    assert "nonglobal_progress_reset_global_stall" in codes


def test_self_grounded_root_reset_requires_owner_and_replay_receipts() -> None:
    fields = scoped_progress_fields(
        effective_progress_class="root_reduction",
        changed_files=["src/producer_engine.py"],
        expected_scope="root",
        expected_progress_cap="root_reduction",
    )
    fields["progress_observations"]["root_scope"] = {
        "comparison_status": "comparable",
        "movement_status": "improved",
        "residual_relation_status": "reduced",
        "independent_verification_status": "explicit_self_grounded",
        "self_grounded_contract_status": "verified",
        "premise_replay_status": "pass",
        "observation_binding_status": "exact_bound",
        "progress_class": "root_reduction",
    }
    fields["retained_change_classification"].update(
        producer_source_changed=True,
        tests_only_changed=False,
    )
    packet = current_validate_packet(root_stall_reset=True, **fields)

    assessment = assess_scoped_progress(packet)
    codes = finding_codes(result_contract.validate("validate", packet, "block"))

    assert assessment.root_reset_allowed is False
    assert "root_progress_without_verified_residual_reduction" in codes
    assert "task_local_progress_reset_root_stall" in codes


def test_terminal_outcome_change_is_disposition_evidence_not_task_progress() -> None:
    fields = scoped_progress_fields()
    fields["progress_observations"]["task_scope"] = {
        "terminal_outcome_changed": True,
        "progress_class": "none",
    }
    fields["closeout_projection"]["task_acceptance"] = "fail"
    packet = current_validate_packet(**fields)

    assessment = assess_scoped_progress(packet)

    assert assessment.task_progress_qualified is False
    assert assessment.effective_progress_class == "none"


def test_loopback_and_derive_share_retrospective_cap_but_keep_future_intent() -> None:
    fields = scoped_progress_fields()
    loopback_packet = {
        "task_id": "task_T",
        "cycle_id": "cycle_C",
        "family_key": "family_F",
        "changed_vs_previous": True,
        "semantic_progress": True,
        "same_family_micro_hardening_count": 0,
        "recommended_disposition": "goal_productive",
        "hard_stop_required": False,
        "evidence_class": "direct",
        "evidence_paths": ["loopback_E.json"],
        **fields,
    }
    loopback_codes = finding_codes(
        result_contract.validate("loopback_audit", loopback_packet, "block")
    )
    assert "loopback_semantic_progress_exceeds_scoped_evidence" in loopback_codes

    derive_packet = {
        "step": "derive",
        "derive_mode": "initial_init",
        "next_task_id": "task_next",
        "selected_task_source": "standalone",
        "progress_kind": "goal_productive",
        "semantic_signature": "semantic_S",
        "evidence_paths": ["derive_E.json"],
        **fields,
    }
    prospective_codes = finding_codes(
        result_contract.validate("derive", derive_packet, "block")
    )
    assert (
        "derive_retrospective_progress_exceeds_scoped_evidence" not in prospective_codes
    )

    retrospective_codes = finding_codes(
        result_contract.validate(
            "derive",
            {**derive_packet, "effective_progress_kind": "goal_productive"},
            "block",
        )
    )
    assert (
        "derive_retrospective_progress_exceeds_scoped_evidence" in retrospective_codes
    )


def test_lifecycle_only_change_is_governance_and_completed_task_cannot_reactivate() -> (
    None
):
    fields = scoped_progress_fields(
        effective_progress_class="governance",
        changed_files=[".task/index.json"],
        expected_scope="task",
        expected_progress_cap="governance",
    )
    fields["progress_observations"]["task_scope"]["progress_class"] = "governance"
    fields["retained_change_classification"].update(
        tests_only_changed=False,
        lifecycle_only_changed=True,
    )
    packet = current_validate_packet(
        validation_verdict="complete",
        progress_verdict="no_progress",
        current_task_executable=True,
        **fields,
    )

    result = result_contract.validate("validate", packet, "block")
    codes = finding_codes(result)

    assert assess_scoped_progress(packet).effective_progress_class == "governance"
    assert "retained_change_classification_mismatch" not in codes
    assert "completed_local_reactivated_as_executable" in codes


def test_schema_and_verifier_only_changes_keep_bounded_progress_classes() -> None:
    cases = (
        ("schemas/output.jsonschema", "governance"),
        ("verifiers/current_verifier.py", "safety"),
    )
    for changed_file, expected_class in cases:
        fields = scoped_progress_fields(
            effective_progress_class=expected_class,
            changed_files=[changed_file],
            expected_scope="task",
            expected_progress_cap=expected_class,
        )
        fields["progress_observations"]["task_scope"]["progress_class"] = expected_class
        fields["retained_change_classification"].update(
            tests_only_changed=False,
            schema_or_verifier_only_changed=True,
        )
        packet = current_validate_packet(
            validation_verdict="complete",
            progress_verdict="no_progress",
            **fields,
        )

        codes = finding_codes(result_contract.validate("validate", packet, "block"))

        assert assess_scoped_progress(packet).effective_progress_class == expected_class
        assert "retained_change_classification_mismatch" not in codes


def test_consumer_does_not_upgrade_root_facts_when_upstream_class_is_none() -> None:
    fields = scoped_progress_fields(
        effective_progress_class="task_local",
        changed_files=["src/producer_engine.py"],
        expected_scope="root",
        expected_progress_cap="root_reduction",
    )
    fields["progress_observations"]["root_scope"] = {
        "comparison_status": "comparable",
        "movement_status": "improved",
        "residual_relation_status": "reduced",
        "independent_verification_status": "explicit_self_grounded",
        "self_grounded_contract_status": "verified",
        "premise_replay_status": "pass",
        "progress_class": "none",
    }
    fields["retained_change_classification"].update(
        producer_source_changed=True,
        tests_only_changed=False,
    )
    packet = current_validate_packet(
        progress_verdict="no_progress",
        root_stall_reset=True,
        **fields,
    )

    result = result_contract.validate("validate", packet, "block")

    assert assess_scoped_progress(packet).effective_progress_class == "task_local"
    assert "task_local_progress_reset_root_stall" in finding_codes(result)


def test_declared_empty_or_untyped_scoped_surfaces_fail_closed() -> None:
    empty_contract = current_validate_packet(progress_scope_contract={})
    empty_codes = finding_codes(
        result_contract.validate("validate", empty_contract, "block")
    )
    assert "scoped_progress_contract_malformed" in empty_codes

    fields = scoped_progress_fields()
    fields["actual_changed_files"] = "tests/test_bounded_fixture.py"
    malformed_evidence = current_validate_packet(**fields)
    malformed_codes = finding_codes(
        result_contract.validate("validate", malformed_evidence, "block")
    )
    assert "retained_change_evidence_malformed" in malformed_codes


def test_acceptance_and_transition_verdicts_remain_separate() -> None:
    transition_blocked = current_validate_packet(
        pack_transition_verdict={"status": "blocked", "evidence_ref": "pack_P.json"},
    )
    transition_result = result_contract.validate(
        "validate", transition_blocked, "block"
    )
    transition_codes = finding_codes(transition_result)
    assert "failed_axis_counted_as_goal_ready" in transition_codes
    assert "implementation_axis_failure_counted_as_progress" not in transition_codes

    semantic_failed = current_validate_packet(
        artifact_semantic_verdict={"status": "fail", "evidence_ref": "verdict_V.json"},
        goal_readiness_verdict={"status": "blocked", "evidence_ref": "verdict_V.json"},
    )
    semantic_result = result_contract.validate("validate", semantic_failed, "block")
    semantic_codes = finding_codes(semantic_result)
    assert "implementation_axis_failure_counted_as_progress" in semantic_codes
    assert semantic_failed["pack_transition_verdict"]["status"] == "pass"


def test_positive_current_decision_requires_identity_and_all_verdict_axes() -> None:
    missing_identity = current_validate_packet()
    del missing_identity["decision_artifact_ref"]
    identity_result = result_contract.validate("validate", missing_identity, "block")
    assert "decision_artifact_identity_missing" in finding_codes(identity_result)

    missing_axis = current_validate_packet()
    del missing_axis["historical_index_verdict"]
    axis_result = result_contract.validate("validate", missing_axis, "block")
    assert "verdict_axis_missing" in finding_codes(axis_result)

    missing_versions = current_validate_packet()
    del missing_versions["decision_contract_version"]
    del missing_versions["verdict_contract_version"]
    version_result = result_contract.validate("validate", missing_versions, "block")
    codes = finding_codes(version_result)
    assert "decision_contract_version_missing" in codes
    assert "verdict_contract_version_missing" in codes


def test_legacy_positive_decisions_require_revision_bound_bridge_receipt() -> None:
    identity = legacy_identity()
    claim_rows = (
        {"progress_verdict": "advanced"},
        {"semantic_progress": True},
        {"completion_status": "complete"},
        {"terminal_state": "conservative_hold"},
    )
    for version in (0, 1):
        for claim in claim_rows:
            packet = {
                "decision_contract_version": version,
                "decision_artifact_ref": identity,
                **claim,
            }
            missing = result_contract.validate("derive", packet, "warn")
            assert "legacy_positive_decision_revision_bridge_missing" in finding_codes(
                missing
            )

            bridged = result_contract.validate(
                "derive",
                {
                    **packet,
                    "legacy_revision_bridge_receipt": legacy_revision_bridge(identity),
                },
                "warn",
            )
            assert not {
                "legacy_positive_decision_revision_bridge_missing",
                "legacy_positive_decision_revision_bridge_invalid",
            } & finding_codes(bridged)


def test_legacy_bridge_tamper_blocks_but_nonpositive_init_remains_compatible() -> None:
    identity = legacy_identity()
    tampered = legacy_revision_bridge(identity)
    tampered["revision_id"] = "revision-tampered"
    invalid = result_contract.validate(
        "derive",
        {
            "decision_contract_version": 1,
            "decision_artifact_ref": identity,
            "progress_verdict": "advanced",
            "legacy_revision_bridge_receipt": tampered,
        },
        "warn",
    )
    assert invalid["status"] == "block"
    assert "legacy_positive_decision_revision_bridge_invalid" in finding_codes(invalid)

    malformed_v0 = result_contract.validate(
        "derive",
        {
            "decision_contract_version": 0,
            "decision_artifact_ref": {
                **identity,
                "body_fingerprint": {
                    "applicability": "not_applicable",
                    "value": None,
                },
            },
            "semantic_progress": True,
        },
        "warn",
    )
    assert "legacy_positive_decision_revision_bridge_missing" in finding_codes(
        malformed_v0
    )

    initial = result_contract.validate(
        "derive",
        {
            "derive_mode": "initial_init",
            "decision_contract_version": 0,
            "progress_verdict": "stalled",
        },
        "warn",
    )
    assert not {
        "legacy_positive_decision_revision_bridge_missing",
        "legacy_positive_decision_revision_bridge_invalid",
    } & finding_codes(initial)


def explicit_decision_identity(**overrides: Any) -> dict[str, Any]:
    identity: dict[str, Any] = {
        "decision_subject_id": "subject_A",
        "subject_class_id": "subject_class_A",
        "revision_id": "revision_A",
        "subject_digest": "a" * 64,
        "lineage_id": "lineage_A",
        "body_fingerprint": {"applicability": "not_applicable", "value": None},
        "production_lane": {"applicability": "not_applicable", "value": None},
        "cohort": {"applicability": "not_applicable", "value": None},
        "producer_run": {"applicability": "not_applicable", "value": None},
        "freshness_status": "current",
    }
    identity.update(overrides)
    return identity


def explicit_identity_echo(identity: dict[str, Any]) -> dict[str, Any]:
    dimensions = {
        name: identity[name]["value"]
        for name in ("body_fingerprint", "production_lane", "cohort", "producer_run")
        if identity[name]["applicability"] == "applicable"
    }
    return {
        **{
            field: identity[field]
            for field in (
                "decision_subject_id",
                "subject_class_id",
                "revision_id",
                "subject_digest",
                "lineage_id",
            )
        },
        "freshness_status": identity["freshness_status"],
        "dimension_values": dimensions,
    }


def test_explicit_identity_requires_only_applicable_dimensions() -> None:
    all_not_applicable = current_validate_packet(
        decision_artifact_ref=explicit_decision_identity(),
    )
    all_na_codes = finding_codes(
        result_contract.validate("validate", all_not_applicable, "block")
    )
    assert "decision_identity_applicability_invalid" not in all_na_codes
    assert "decision_semantic_binding_incomplete" not in all_na_codes

    missing_body = explicit_decision_identity(
        body_fingerprint={"applicability": "applicable", "value": None},
    )
    assert "decision_identity_applicability_invalid" in finding_codes(
        result_contract.validate(
            "validate",
            current_validate_packet(decision_artifact_ref=missing_body),
            "block",
        )
    )

    current_body = explicit_decision_identity(
        body_fingerprint={"applicability": "applicable", "value": "b" * 64},
    )
    mismatch = current_validate_packet(
        decision_artifact_ref=current_body,
        body_projection_fingerprint="c" * 64,
    )
    assert "decision_applicable_dimension_mismatch" in finding_codes(
        result_contract.validate("validate", mismatch, "block")
    )

    nonapplicable_echo = current_validate_packet(
        decision_artifact_ref=explicit_decision_identity(),
        production_lane_identity="stale_lane",
    )
    assert "decision_nonapplicable_dimension_echoed" in finding_codes(
        result_contract.validate("validate", nonapplicable_echo, "block")
    )


def test_explicit_identity_consumer_echo_binds_subject_and_only_applicable_dimensions() -> (
    None
):
    identity = explicit_decision_identity(
        body_fingerprint={"applicability": "applicable", "value": "b" * 64},
        cohort={"applicability": "applicable", "value": ["cohort_A"]},
    )
    echo = explicit_identity_echo(identity)
    row = {
        "consumer_context_id": "consumer_A",
        "cycle_id": "cycle_A",
        "input_state_fingerprint": "c" * 64,
        "attempt_identity": "attempt_A",
        "decision_identity_echo": echo,
        "adapter_loaded": True,
        "hook_resolved": True,
        "required_hook_callable": True,
        "hook_signature_compatible": True,
        "invocation_completed": True,
        "return_contract_valid": True,
        "artifact_identity_echo_valid": True,
        "value_consumed_by_decision": True,
        "evidence_provenance": "independently_verified",
        "probe_evidence_ref": "probe_A",
    }
    row["probe_evidence_sha256"] = result_contract._consumer_receipt_binding_sha256(row)
    packet = current_validate_packet(
        decision_artifact_ref=identity,
        cycle_id="cycle_A",
        input_state_fingerprint="c" * 64,
        attempt_identity="attempt_A",
        required_consumer_ids=["consumer_A"],
        consumer_context_conformance={"rows": [row]},
    )
    happy_codes = finding_codes(result_contract.validate("validate", packet, "block"))
    assert "required_consumer_context_not_evaluated" not in happy_codes

    stale_echo = copy.deepcopy(packet)
    stale_row = stale_echo["consumer_context_conformance"]["rows"][0]
    stale_row["decision_identity_echo"]["dimension_values"]["production_lane"] = (
        "stale_lane"
    )
    stale_row["probe_evidence_sha256"] = (
        result_contract._consumer_receipt_binding_sha256(stale_row)
    )
    assert "required_consumer_context_not_evaluated" in finding_codes(
        result_contract.validate("validate", stale_echo, "block")
    )


def test_incomplete_current_index_projection_cannot_be_consumed_as_pass() -> None:
    packet = current_validate_packet(
        index_status="passed",
        current_projection_status="not_evaluated",
        projection_completeness="incomplete",
    )
    result = result_contract.validate("validate", packet, "block")
    assert "historical_index_projection_not_evaluated" in finding_codes(result)


def applicability_policy(status: str, *, missing_body: bool = False) -> dict[str, Any]:
    return {
        "keys": ["metric_M"],
        "applicability": {
            "metric_M": {
                "evaluation_status": status,
                "missing_body_class_ids": ["axis_X"] if missing_body else [],
            }
        },
    }


def test_metric_applicability_precedes_values_and_excludes_nonapplicable_metrics() -> (
    None
):
    policy = applicability_policy("not_applicable")
    output_gate = output_delta_contract.quality_delta_gate(
        {"metric_M": 999},
        {"metric_M": 1},
        quality_delta_policy=policy,
    )
    audit_gate = loopback_provider.coverage_quality_delta_gate(
        {"metric_M": 999},
        {"metric_M": 1},
        0,
        1e-9,
        policy,
    )
    supplied_gate = progress_output_delta_gate.coverage_quality_delta_gate(
        {
            "coverage_quality_delta_gate": {
                "quality_delta_pass": True,
                "improved_fields": ["metric_M"],
                "current_quality_vector": {"metric_M": 999},
                "previous_quality_vector": {"metric_M": 1},
                "quality_delta_policy": policy,
            }
        }
    )

    for gate in (output_gate, audit_gate, supplied_gate):
        assert gate["evaluation_status"] == "not_applicable"
        assert gate["quality_delta_pass"] is False
        assert gate["improved_fields"] == []
        assert gate["current_quality_vector"] == {}
    dispatch = progress_dispatch_gate.provider_scale_dispatch_gate({}, supplied_gate)
    assert dispatch["dispatch_required"] is False
    assert dispatch["high_water_all_zero"] is False


def test_metric_applicability_insufficient_invalid_and_happy_paths() -> None:
    insufficient = output_delta_contract.quality_delta_gate(
        {"metric_M": 2},
        {"metric_M": 1},
        quality_delta_policy=applicability_policy("applicable", missing_body=True),
    )
    assert insufficient["evaluation_status"] == "insufficient_evidence"
    assert insufficient["quality_delta_pass"] is False

    conflicted = output_delta_contract.explicit_quality_delta_policy(
        {"quality_delta_policy": applicability_policy("applicable")},
        {"quality_delta_policy": applicability_policy("not_applicable")},
    )
    assert conflicted["invalid_contract_fields"] == ["metric_M"]

    happy = output_delta_contract.quality_delta_gate(
        {"metric_M": 2},
        {"metric_M": 1},
        quality_delta_policy=applicability_policy("applicable"),
    )
    assert happy["evaluation_status"] == "evaluated"
    assert happy["quality_delta_pass"] is True
    assert happy["improved_fields"] == ["metric_M"]

    evaluator_source = (
        ROOT
        / "audit-cycle-loopback"
        / "scripts"
        / "audit_cycle_loopback"
        / "evaluation_stages"
        / "setup_quality.py"
    ).read_text(encoding="utf-8")
    assert evaluator_source.index(
        "applicability_preflight=True"
    ) < evaluator_source.index("else compute_quality")
    coverage_mapping = evaluator_source[
        evaluator_source.index("coverage_compatibility = {") : evaluator_source.index(
            "quality_delta_policy = apply_quality_policy_compatibility"
        )
    ]
    assert '"quality_delta_policy"' in coverage_mapping
    assert "gate_artifact_compatibility_result(" not in coverage_mapping


def test_metric_applicability_rejects_partial_rows_and_nonopaque_evidence() -> None:
    partial_policy = {
        "keys": ["metric_M", "metric_N"],
        "applicability": {
            "metric_M": {"evaluation_status": "not_applicable"},
        },
    }
    for normalized in (
        loopback_provider.normalize_quality_delta_policy(partial_policy),
        output_delta_contract.normalize_quality_delta_policy(partial_policy),
    ):
        assert normalized["invalid_contract_fields"] == ["metric_N"]
        assert normalized["keys"] == []

    malformed_policy = {
        "keys": ["metric_M"],
        "applicability": {
            "metric_M": {
                "evaluation_status": "applicable",
                "evidence_ids": [{"raw": "body"}],
            }
        },
    }
    for normalized in (
        loopback_provider.normalize_quality_delta_policy(malformed_policy),
        output_delta_contract.normalize_quality_delta_policy(malformed_policy),
    ):
        assert normalized["invalid_contract_fields"] == ["metric_M"]
        assert normalized["applicability"]["metric_M"]["evidence_ids"] == []
        assert (
            normalized["applicability"]["metric_M"]["reason_code"]
            == "applicability_opaque_id_malformed"
        )
        assert "'raw': 'body'" not in str(normalized)


def test_metric_policy_rejects_malformed_declared_ids_and_aliases_without_repr() -> (
    None
):
    cases = (
        {
            "keys": ["metric_M", {"raw": "source_span_X"}],
            "applicability": {"metric_M": {"evaluation_status": "applicable"}},
        },
        {"keys": [{"raw": "source_span_X"}]},
        {
            "keys": ["metric_M"],
            "aliases": {"metric_M": ["metric_M", {"raw": "source_span_X"}]},
        },
    )
    for policy in cases:
        for normalizer in (
            loopback_provider.normalize_quality_delta_policy,
            output_delta_contract.normalize_quality_delta_policy,
        ):
            normalized = normalizer(policy)
            assert normalized["policy_contract_invalid"] is True
            assert normalized["keys"] == []
            assert "source_span_X" not in repr(normalized)
            assert "'raw'" not in repr(normalized)
            assert normalizer(normalized)["policy_contract_invalid"] is True
        for gate in (
            loopback_provider.coverage_quality_delta_gate(
                {"metric_M": 2}, {"metric_M": 1}, 0, 1e-9, policy
            ),
            output_delta_contract.quality_delta_gate(
                {"metric_M": 2}, {"metric_M": 1}, quality_delta_policy=policy
            ),
        ):
            assert gate["evaluation_status"] == "invalid_contract"
            assert gate["quality_delta_pass"] is False

    forged = progress_output_delta_gate.coverage_quality_delta_gate(
        {
            "coverage_quality_delta_gate": {
                "evaluation_status": "evaluated",
                "quality_delta_pass": True,
                "improved_fields": ["metric_M"],
                "current_quality_vector": {"metric_M": 2},
                "previous_quality_vector": {"metric_M": 1},
                "quality_delta_policy": {"keys": [{"raw": "source_span_X"}]},
            }
        }
    )
    assert forged["evaluation_status"] == "invalid_contract"
    assert forged["quality_delta_pass"] is False
    assert "source_span_X" not in repr(forged)

    bounded_failures = (
        "metric_M\nsource_span_X",
        "metric_M" * 40,
    )
    for malformed_id in bounded_failures:
        for normalizer in (
            loopback_provider.normalize_quality_delta_policy,
            output_delta_contract.normalize_quality_delta_policy,
        ):
            normalized = normalizer({"keys": [malformed_id]})
            assert normalized["policy_contract_invalid"] is True
            assert normalized["keys"] == []
    for normalizer in (
        loopback_provider.normalize_quality_delta_policy,
        output_delta_contract.normalize_quality_delta_policy,
    ):
        normalized = normalizer(
            {
                "keys": ["metric_M"],
                "applicability": {
                    "metric_M": {
                        "evaluation_status": "applicable",
                        "reason_code": {"raw": "source_span_X"},
                    }
                },
            }
        )
        assert (
            normalized["applicability"]["metric_M"]["reason_code"]
            == "applicability_reason_code_malformed"
        )
        assert "source_span_X" not in repr(normalized)
        assert "'raw'" not in repr(normalized)

    for normalizer in (
        loopback_provider.normalize_quality_delta_policy,
        output_delta_contract.normalize_quality_delta_policy,
    ):
        prose_reason = normalizer(
            {
                "keys": ["metric_M"],
                "applicability": {
                    "metric_M": {
                        "evaluation_status": "applicable",
                        "reason_code": "source_span_X source_S",
                    }
                },
            }
        )
        assert (
            prose_reason["applicability"]["metric_M"]["reason_code"]
            == "applicability_reason_code_malformed"
        )
        assert "source_span_X source_S" not in repr(prose_reason)

        suppressed = normalizer(
            {
                "keys": ["metric_M"],
                "applicability_supplied": False,
                "applicability": {
                    "metric_M": {"evaluation_status": "not_applicable"},
                },
            }
        )
        assert suppressed["policy_contract_invalid"] is True
        assert suppressed["keys"] == []


def test_metric_gates_reject_nonfinite_observations_without_pass_or_stall() -> None:
    policy = {"keys": ["metric_M"]}
    invalid_values = (
        float("nan"),
        float("inf"),
        float("-inf"),
        "NaN",
        "Infinity",
        10**10000,
    )
    for invalid in invalid_values:
        gates = (
            loopback_provider.coverage_quality_delta_gate(
                {"metric_M": invalid}, {"metric_M": 1}, 0, 1e-9, policy
            ),
            output_delta_contract.quality_delta_gate(
                {"metric_M": invalid}, {"metric_M": 1}, quality_delta_policy=policy
            ),
            progress_output_delta_gate.coverage_quality_delta_gate(
                {
                    "quality_vector": {"metric_M": invalid},
                    "previous_quality_vector": {"metric_M": 1},
                    "quality_delta_policy": policy,
                }
            ),
        )
        for gate in gates:
            assert gate["evaluation_status"] == "insufficient_evidence"
            assert gate["quality_delta_pass"] is False
            assert gate["improved_fields"] == []
            dispatch = progress_dispatch_gate.provider_scale_dispatch_gate({}, gate)
            assert dispatch["dispatch_required"] is False
            assert dispatch["high_water_all_zero"] is False

        previous_invalid = output_delta_contract.quality_delta_gate(
            {"metric_M": 2}, {"metric_M": invalid}, quality_delta_policy=policy
        )
        assert previous_invalid["evaluation_status"] == "insufficient_evidence"
        assert previous_invalid["quality_delta_pass"] is False

    finite = output_delta_contract.quality_delta_gate(
        {"metric_M": 2}, {"metric_M": 1}, quality_delta_policy=policy
    )
    assert finite["evaluation_status"] == "evaluated"
    assert finite["quality_delta_pass"] is True

    for invalid_epsilon in (float("nan"), float("inf"), float("-inf"), 10**10000):
        epsilon_gates = (
            loopback_provider.coverage_quality_delta_gate(
                {"metric_M": 2}, {"metric_M": 1}, 0, invalid_epsilon, policy
            ),
            output_delta_contract.quality_delta_gate(
                {"metric_M": 2},
                {"metric_M": 1},
                epsilon=invalid_epsilon,
                quality_delta_policy=policy,
            ),
        )
        assert all(
            gate["evaluation_status"] == "invalid_contract" for gate in epsilon_gates
        )
        assert all(gate["quality_delta_pass"] is False for gate in epsilon_gates)


def test_metric_consumer_reconciles_policy_rows_and_fails_only_claim_local() -> None:
    forged_gate = {
        "gate": "G-COV",
        "evaluation_status": "evaluated",
        "quality_delta_pass": True,
        "improved_fields": ["metric_M"],
        "current_quality_vector": {"metric_M": 2},
        "previous_quality_vector": {"metric_M": 1},
        "not_applicable_fields": [],
        "insufficient_evidence_fields": [],
        "invalid_contract_fields": [],
        "quality_delta_policy": {
            "keys": ["metric_M"],
            "applicability": {"metric_M": {"evaluation_status": "not_applicable"}},
        },
    }
    forged = result_contract.validate(
        "validate",
        current_validate_packet(coverage_quality_delta_gate=forged_gate),
        "block",
    )
    forged_codes = finding_codes(forged)
    assert "metric_applicability_summary_divergence" in forged_codes
    assert "nonapplicable_metric_consumed" in forged_codes

    consistent_gate = {
        **forged_gate,
        "quality_delta_policy": {
            "keys": ["metric_M"],
            "applicability": {"metric_M": {"evaluation_status": "applicable"}},
        },
    }
    consistent_codes = finding_codes(
        result_contract.validate(
            "validate",
            current_validate_packet(coverage_quality_delta_gate=consistent_gate),
            "block",
        )
    )
    assert "metric_applicability_summary_divergence" not in consistent_codes
    assert "nonapplicable_metric_consumed" not in consistent_codes
    assert "metric_vector_contract_invalid" not in consistent_codes

    contradictory_nested_gate = current_validate_packet(
        coverage_quality_delta_gate=consistent_gate,
        result={"coverage_quality_delta_gate": forged_gate},
    )
    assert "metric_applicability_gate_conflict" in finding_codes(
        result_contract.validate("validate", contradictory_nested_gate, "block")
    )
    converged_duplicate_gate = current_validate_packet(
        coverage_quality_delta_gate=consistent_gate,
        result={"coverage_quality_delta_gate": dict(consistent_gate)},
    )
    assert "metric_applicability_gate_conflict" not in finding_codes(
        result_contract.validate("validate", converged_duplicate_gate, "block")
    )
    vector_only_conflict = dict(consistent_gate)
    vector_only_conflict["current_quality_vector"] = {"metric_M": 9}
    assert "metric_applicability_gate_conflict" in finding_codes(
        result_contract.validate(
            "validate",
            current_validate_packet(
                coverage_quality_delta_gate=consistent_gate,
                result={"coverage_quality_delta_gate": vector_only_conflict},
            ),
            "block",
        )
    )

    optional_gate = {
        "gate": "G-COV",
        "evaluation_status": "invalid_contract",
        "quality_delta_pass": False,
        "improved_fields": [],
        "invalid_contract_fields": ["metric_M"],
    }
    optional = result_contract.validate(
        "validate",
        current_validate_packet(coverage_quality_delta_gate=optional_gate),
        "block",
    )
    optional_findings = [
        row
        for row in optional["findings"]
        if row.get("code") == "metric_applicability_invalid_contract"
    ]
    assert optional_findings and optional_findings[0]["severity"] == "warn"

    required = result_contract.validate(
        "validate",
        current_validate_packet(
            coverage_quality_delta_gate=optional_gate,
            required_gate_ids=["G-COV"],
        ),
        "block",
    )
    required_findings = [
        row
        for row in required["findings"]
        if row.get("code") == "metric_applicability_invalid_contract"
    ]
    assert required_findings and required_findings[0]["severity"] == "block"

    no_policy = dict(consistent_gate)
    no_policy.pop("quality_delta_policy")
    no_policy_codes = finding_codes(
        result_contract.validate(
            "validate",
            current_validate_packet(coverage_quality_delta_gate=no_policy),
            "block",
        )
    )
    assert "metric_applicability_proof_missing" in no_policy_codes

    undeclared_mapping = {
        **consistent_gate,
        "quality_delta_policy": {
            "keys": [],
            "applicability": {"metric_M": {"evaluation_status": "applicable"}},
        },
    }
    assert "metric_applicability_summary_divergence" in finding_codes(
        result_contract.validate(
            "validate",
            current_validate_packet(coverage_quality_delta_gate=undeclared_mapping),
            "block",
        )
    )

    reverse_contradiction = {
        **consistent_gate,
        "not_applicable_fields": ["metric_M"],
    }
    reverse_codes = finding_codes(
        result_contract.validate(
            "validate",
            current_validate_packet(coverage_quality_delta_gate=reverse_contradiction),
            "block",
        )
    )
    assert "metric_applicability_summary_divergence" in reverse_codes
    assert "nonapplicable_metric_consumed" in reverse_codes

    nonfinite = {
        **consistent_gate,
        "current_quality_vector": {"metric_M": float("nan")},
    }
    assert "metric_vector_contract_invalid" in finding_codes(
        result_contract.validate(
            "validate",
            current_validate_packet(coverage_quality_delta_gate=nonfinite),
            "block",
        )
    )

    mixed_applicability = {
        "gate": "G-COV",
        "evaluation_status": "evaluated",
        "quality_delta_pass": True,
        "improved_fields": ["metric_M"],
        "current_quality_vector": {"metric_M": 2},
        "previous_quality_vector": {"metric_M": 1},
        "not_applicable_fields": ["metric_N"],
        "insufficient_evidence_fields": [],
        "invalid_contract_fields": [],
        "quality_delta_policy": {
            "keys": ["metric_M", "metric_N"],
            "applicability": {
                "metric_M": {"evaluation_status": "applicable"},
                "metric_N": {"evaluation_status": "not_applicable"},
            },
        },
    }
    mixed_codes = finding_codes(
        result_contract.validate(
            "validate",
            current_validate_packet(coverage_quality_delta_gate=mixed_applicability),
            "block",
        )
    )
    assert "metric_applicability_summary_divergence" not in mixed_codes
    assert "nonapplicable_metric_consumed" not in mixed_codes

    malformed_evaluation = {
        **consistent_gate,
        "evaluation_status": {"raw": "source_span_X"},
    }
    malformed_evaluation_result = result_contract.validate(
        "validate",
        current_validate_packet(coverage_quality_delta_gate=malformed_evaluation),
        "block",
    )
    assert "metric_applicability_summary_divergence" in finding_codes(
        malformed_evaluation_result
    )
    assert "source_span_X" not in repr(malformed_evaluation_result)

    pass_without_improved = {**consistent_gate, "improved_fields": []}
    assert "metric_delta_claim_inconsistent" in finding_codes(
        result_contract.validate(
            "validate",
            current_validate_packet(coverage_quality_delta_gate=pass_without_improved),
            "block",
        )
    )

    undeclared_improved = {
        **consistent_gate,
        "improved_fields": ["metric_N"],
        "current_quality_vector": {"metric_N": 2},
        "previous_quality_vector": {"metric_N": 1},
    }
    assert "metric_delta_claim_inconsistent" in finding_codes(
        result_contract.validate(
            "validate",
            current_validate_packet(coverage_quality_delta_gate=undeclared_improved),
            "block",
        )
    )

    malformed_improved = {
        **consistent_gate,
        "improved_fields": [{"raw": "source_span_X"}],
    }
    malformed_improved_result = result_contract.validate(
        "validate",
        current_validate_packet(coverage_quality_delta_gate=malformed_improved),
        "block",
    )
    assert "metric_applicability_consumed_ids_invalid" in finding_codes(
        malformed_improved_result
    )
    assert "source_span_X" not in repr(malformed_improved_result)

    required_not_evaluated = {
        **consistent_gate,
        "evaluation_status": "not_evaluated",
        "quality_delta_pass": False,
        "improved_fields": [],
    }
    assert "metric_applicability_insufficient_evidence" in finding_codes(
        result_contract.validate(
            "validate",
            current_validate_packet(
                coverage_quality_delta_gate=required_not_evaluated,
                required_gate_ids=["G-COV"],
            ),
            "block",
        )
    )

    all_not_applicable_evaluated = {
        "gate": "G-COV",
        "evaluation_status": "evaluated",
        "quality_delta_pass": False,
        "improved_fields": [],
        "current_quality_vector": {},
        "previous_quality_vector": {},
        "not_applicable_fields": ["metric_M"],
        "insufficient_evidence_fields": [],
        "invalid_contract_fields": [],
        "quality_delta_policy": {
            "keys": ["metric_M"],
            "applicability": {
                "metric_M": {"evaluation_status": "not_applicable"},
            },
        },
    }
    assert "metric_applicability_summary_divergence" in finding_codes(
        result_contract.validate(
            "validate",
            current_validate_packet(
                coverage_quality_delta_gate=all_not_applicable_evaluated,
                required_gate_ids=["G-COV"],
            ),
            "block",
        )
    )


def test_metric_baseline_absence_is_insufficient_and_mixed_statuses_do_not_pass() -> (
    None
):
    policy = applicability_policy("applicable")
    missing_baseline_gates = [
        output_delta_contract.quality_delta_gate(
            {"metric_M": 2}, {}, quality_delta_policy=policy
        ),
        loopback_provider.coverage_quality_delta_gate(
            {"metric_M": 2}, {}, 0, 1e-9, policy
        ),
        progress_output_delta_gate.coverage_quality_delta_gate(
            {
                "quality_vector": {"metric_M": 2},
                "previous_quality_vector": {},
                "quality_delta_policy": policy,
            }
        ),
    ]
    assert all(
        gate["evaluation_status"] == "insufficient_evidence"
        for gate in missing_baseline_gates
    )
    assert all(gate["quality_delta_pass"] is False for gate in missing_baseline_gates)
    assert all(
        not (
            gate.get("previous_quality_vector")
            or gate.get("previous_high_water_vector")
        )
        for gate in missing_baseline_gates
    )

    gates = [
        output_delta_contract.quality_delta_gate(
            {"metric_M": 2}, {"metric_M": True}, quality_delta_policy=policy
        ),
        loopback_provider.coverage_quality_delta_gate(
            {"metric_M": 2}, {"metric_M": True}, 0, 1e-9, policy
        ),
        progress_output_delta_gate.coverage_quality_delta_gate(
            {
                "quality_vector": {"metric_M": 2},
                "previous_quality_vector": {"metric_M": True},
                "quality_delta_policy": policy,
            }
        ),
    ]
    assert all(gate["evaluation_status"] == "insufficient_evidence" for gate in gates)
    assert all(gate["quality_delta_pass"] is False for gate in gates)

    aggregate = (
        progress_analysis_aggregation.ProgressAggregationMixin._coverage_gate_result(
            None,
            [
                {
                    "evaluation_status": "evaluated",
                    "quality_delta_pass": True,
                    "improved_fields": ["metric_M"],
                },
                {"evaluation_status": "invalid_contract", "quality_delta_pass": False},
            ],
        )
    )
    assert aggregate["evaluation_status"] == "invalid_contract"
    assert aggregate["quality_delta_pass"] is False
    assert aggregate["improved_fields"] == []

    semantically_equal = output_delta_contract.explicit_quality_delta_policy(
        {"quality_delta_policy": {"keys": ["metric_M"]}},
        {"quality_delta_policy": applicability_policy("applicable")},
    )
    assert semantically_equal["invalid_contract_fields"] == []
    assert (
        loopback_provider.metric_stall_observation_allowed(
            "not_applicable", policy_supplied=True, producer_absence_reason="missing"
        )
        is False
    )
    assert (
        loopback_provider.metric_stall_observation_allowed(
            "insufficient_evidence",
            policy_supplied=True,
            producer_absence_reason="missing",
        )
        is False
    )
    assert (
        loopback_provider.metric_stall_observation_allowed(
            "evaluated", policy_supplied=True
        )
        is True
    )


def test_nonapplicable_metric_consumption_is_rejected_by_result_contract() -> None:
    packet = current_validate_packet(
        coverage_quality_delta_gate={
            "evaluation_status": "not_applicable",
            "quality_delta_pass": True,
            "improved_fields": ["metric_M"],
            "not_applicable_fields": ["metric_M"],
            "current_quality_vector": {"metric_M": 9},
        }
    )
    result = result_contract.validate("validate", packet, "block")
    assert "nonapplicable_metric_consumed" in finding_codes(result)

    insufficient = current_validate_packet(
        coverage_quality_delta_gate={
            "evaluation_status": "insufficient_evidence",
            "quality_delta_pass": False,
            "improved_fields": [],
            "insufficient_evidence_fields": ["metric_M"],
        }
    )
    assert "metric_applicability_insufficient_evidence" in finding_codes(
        result_contract.validate("validate", insufficient, "block")
    )


def test_report_projection_divergence_converges_across_report_roots() -> None:
    packet = current_validate_packet(
        body_projection_fingerprint="b" * 64,
        recomputed_fields=["metric_M"],
        actual_artifact={"axis": {"metric_M": 1}},
        validation_report={
            "body_projection_fingerprint": "b" * 64,
            "summary": {"metric_M": 1},
        },
        result_report={
            "body_projection_fingerprint": "b" * 64,
            "summary": {"metric_M": 2},
        },
    )
    result = result_contract.validate("validate", packet, "block")
    codes = finding_codes(result)
    assert "report_key_divergence" in codes
    assert "report_body_divergence" in codes

    matching = current_validate_packet(
        body_projection_fingerprint="b" * 64,
        recomputed_fields=["metric_M"],
        actual_artifact={"axis": {"metric_M": 1}},
        validation_report={
            "body_projection_fingerprint": "b" * 64,
            "summary": {"metric_M": 1},
        },
        result_report={
            "body_projection_fingerprint": "b" * 64,
            "summary": {"metric_M": 1},
        },
    )
    matching_result = result_contract.validate("validate", matching, "block")
    assert "report_key_divergence" not in finding_codes(matching_result)
    assert "report_body_divergence" not in finding_codes(matching_result)

    nested = current_validate_packet(
        body_projection_fingerprint="b" * 64,
        recomputed_fields=["metric_M"],
        actual_artifact={"axis": {"metric_M": 1}},
        result={
            "validation_report": {
                "body_projection_fingerprint": "b" * 64,
                "summary": {"metric_M": 1},
            },
            "result_report": {
                "body_projection_fingerprint": "b" * 64,
                "summary": {"metric_M": 2},
            },
        },
    )
    nested_validated = result_contract.validate("validate", nested, "block")
    assert nested_validated["status"] == "block"
    assert "report_key_divergence" in finding_codes(nested_validated)

    unrelated = current_validate_packet(
        body_projection_fingerprint="a" * 64,
        recomputed_fields=["metric_M"],
        actual_artifact={
            "artifact_id": "artifact_A",
            "body_projection_fingerprint": "a" * 64,
            "metric_M": 1,
        },
        validation_report={
            "artifact_id": "artifact_B",
            "body_projection_fingerprint": "b" * 64,
            "metric_M": 2,
        },
    )
    unrelated_codes = finding_codes(
        result_contract.validate("validate", unrelated, "block")
    )
    assert "report_body_divergence" not in unrelated_codes
    assert "report_key_divergence" not in unrelated_codes

    identityless = current_validate_packet(
        recomputed_fields=["metric_M"],
        actual_artifact={"metric_M": 1},
        validation_report={"metric_M": 2},
    )
    identityless_codes = finding_codes(
        result_contract.validate("validate", identityless, "block")
    )
    assert "report_body_divergence" not in identityless_codes
    assert "report_key_divergence" not in identityless_codes

    same_artifact_different_fingerprints = current_validate_packet(
        recomputed_fields=["metric_M"],
        validation_report={
            "artifact_id": "artifact_A",
            "body_projection_fingerprint": "a" * 64,
            "metric_M": 1,
        },
        result_report={
            "artifact_id": "artifact_A",
            "body_projection_fingerprint": "b" * 64,
            "metric_M": 1,
        },
    )
    assert "report_key_divergence" in finding_codes(
        result_contract.validate(
            "validate", same_artifact_different_fingerprints, "block"
        )
    )

    unanimous_fingerprint = current_validate_packet(
        recomputed_fields=["metric_M"],
        validation_report={"body_projection_fingerprint": "b" * 64, "metric_M": 1},
        result_report={"body_projection_fingerprint": "b" * 64, "metric_M": 2},
    )
    assert "report_key_divergence" in finding_codes(
        result_contract.validate("validate", unanimous_fingerprint, "block")
    )
    unanimous_fingerprint = current_validate_packet(
        recomputed_fields=["metric_M"],
        validation_report={"body_projection_fingerprint": "b" * 64, "metric_M": 1},
        result_report={"body_projection_fingerprint": "b" * 64, "metric_M": 1},
    )
    assert "report_key_divergence" not in finding_codes(
        result_contract.validate("validate", unanimous_fingerprint, "block")
    )

    opaque = result_integrity.report_key_divergences(nested)
    assert opaque
    serialized = repr(opaque)
    assert "metric_M" not in serialized
    assert "validation_report" not in serialized

    no_top_identity = {
        "recomputed_fields": ["metric_M"],
        "actual_artifact": {"metric_M": 1},
        "validation_report": {"metric_M": 2},
    }
    assert result_integrity.actual_report_body_divergences(no_top_identity) == []
    assert result_integrity.report_key_divergences(no_top_identity) == []

    canonical_actual_conflict = {
        "body_projection_fingerprint": "a" * 64,
        "recomputed_fields": ["metric_M"],
        "actual_artifact": {
            "artifact_id": "artifact_A",
            "body_projection_fingerprint": "b" * 64,
            "metric_M": 1,
        },
        "validation_report": {
            "artifact_id": "artifact_A",
            "body_projection_fingerprint": "a" * 64,
            "metric_M": 1,
        },
    }
    assert result_integrity.actual_report_body_divergences(canonical_actual_conflict)

    metadata_only_difference = {
        "decision_artifact_ref": {"artifact_id": "artifact_A"},
        "recomputed_fields": ["metric_M"],
        "actual_artifact": {
            "artifact_id": "artifact_A",
            "status": "draft",
            "metric_M": 1,
        },
        "validation_report": {
            "artifact_id": "artifact_A",
            "status": "pass",
            "metric_M": 1,
        },
    }
    assert (
        result_integrity.actual_report_body_divergences(metadata_only_difference) == []
    )
    metadata_only_difference["validation_report"]["metric_M"] = 2
    assert result_integrity.actual_report_body_divergences(metadata_only_difference)

    malformed_identity = {
        "decision_artifact_ref": {"artifact_id": {"raw": "source_span_X"}},
        "recomputed_fields": [{"raw": "source_span_X"}],
        "actual_artifact": {"artifact_id": {"raw": "source_span_X"}, "metric_M": 1},
        "validation_report": {"artifact_id": {"raw": "source_span_X"}, "metric_M": 2},
    }
    malformed_divergences = result_integrity.actual_report_body_divergences(
        malformed_identity
    )
    assert "source_span_X" not in repr(malformed_divergences)
    assert "'raw'" not in repr(malformed_divergences)

    missing_projected_field = {
        "decision_artifact_ref": {"artifact_id": "artifact_A"},
        "recomputed_fields": ["metric_M"],
        "actual_artifact": {"artifact_id": "artifact_A", "metric_M": 1},
        "validation_report": {"artifact_id": "artifact_A"},
    }
    assert result_integrity.actual_report_body_divergences(missing_projected_field)

    both_missing_projected_field = {
        "decision_artifact_ref": {"artifact_id": "artifact_A"},
        "recomputed_fields": ["metric_M"],
        "actual_artifact": {"artifact_id": "artifact_A"},
        "validation_report": {"artifact_id": "artifact_A"},
    }
    assert result_integrity.actual_report_body_divergences(both_missing_projected_field)

    suffix_reports = {
        "recomputed_fields": ["metric_M"],
        "alpha_report": {"body_projection_fingerprint": "a" * 64, "metric_M": 1},
        "beta_report": {"body_projection_fingerprint": "a" * 64, "metric_M": 2},
    }
    assert result_integrity.report_key_divergences(suffix_reports)

    unrelated_internal_duplicate = {
        "decision_artifact_ref": {
            "artifact_id": "artifact_A",
            "body_projection_fingerprint": "a" * 64,
        },
        "recomputed_fields": ["metric_M"],
        "validation_report": {
            "artifact_id": "artifact_B",
            "body_projection_fingerprint": "b" * 64,
            "left": {"metric_M": 1},
            "right": {"metric_M": 2},
            "actual_artifact": {"artifact_id": "artifact_B", "metric_M": 3},
        },
    }
    assert result_integrity.report_key_divergences(unrelated_internal_duplicate) == []
    assert (
        result_integrity.actual_report_body_divergences(unrelated_internal_duplicate)
        == []
    )

    required_mask = {
        "report_key_integrity_required": False,
        "report_key_integrity_gate": {"required": True},
        "left": {"metric_M": 1},
        "right": {"metric_M": 2},
    }
    assert result_integrity.report_integrity_required(required_mask) is True
    assert result_integrity.report_key_divergences(required_mask)

    identityless_required_report = {
        "decision_artifact_ref": {"artifact_id": "artifact_A"},
        "report_key_integrity_required": True,
        "validation_report": {
            "left": {"metric_M": 1},
            "right": {"metric_M": 2},
        },
    }
    assert result_integrity.report_key_divergences(identityless_required_report)

    identityless_optional_report = dict(identityless_required_report)
    identityless_optional_report["report_key_integrity_required"] = False
    assert result_integrity.report_key_divergences(identityless_optional_report) == []

    required_identity_conflict = {
        "decision_artifact_ref": {"artifact_id": "artifact_A"},
        "report_key_integrity_required": True,
        "recomputed_fields": ["metric_M"],
        "actual_artifact": {"artifact_id": "artifact_A", "metric_M": 1},
        "validation_report": {"artifact_id": "artifact_B", "metric_M": 2},
    }
    assert result_integrity.report_key_divergences(required_identity_conflict)
    assert result_integrity.actual_report_body_divergences(required_identity_conflict)

    optional_identity_conflict = dict(required_identity_conflict)
    optional_identity_conflict["report_key_integrity_required"] = False
    assert result_integrity.report_key_divergences(optional_identity_conflict) == []
    assert (
        result_integrity.actual_report_body_divergences(optional_identity_conflict)
        == []
    )

    required_identity_match = {
        **required_identity_conflict,
        "validation_report": {"artifact_id": "artifact_A", "metric_M": 1},
    }
    assert result_integrity.report_key_divergences(required_identity_match) == []
    assert (
        result_integrity.actual_report_body_divergences(required_identity_match) == []
    )

    required_incomparable_identity = {
        "decision_artifact_ref": {"artifact_id": "artifact_A"},
        "report_key_integrity_required": True,
        "recomputed_fields": ["metric_M"],
        "actual_artifact": {"artifact_id": "artifact_A", "metric_M": 1},
        "validation_report": {
            "body_projection_fingerprint": "a" * 64,
            "metric_M": 1,
        },
    }
    assert result_integrity.report_key_divergences(required_incomparable_identity)
    assert result_integrity.actual_report_body_divergences(
        required_incomparable_identity
    )
    optional_incomparable_identity = dict(required_incomparable_identity)
    optional_incomparable_identity["report_key_integrity_required"] = False
    assert result_integrity.report_key_divergences(optional_incomparable_identity) == []
    assert (
        result_integrity.actual_report_body_divergences(optional_incomparable_identity)
        == []
    )

    required_incomparable_identity_reverse = {
        "body_projection_fingerprint": "a" * 64,
        "report_key_integrity_required": True,
        "recomputed_fields": ["metric_M"],
        "actual_artifact": {
            "body_projection_fingerprint": "a" * 64,
            "metric_M": 1,
        },
        "validation_report": {"artifact_id": "artifact_A", "metric_M": 1},
    }
    assert result_integrity.report_key_divergences(
        required_incomparable_identity_reverse
    )
    assert result_integrity.actual_report_body_divergences(
        required_incomparable_identity_reverse
    )

    required_without_top_identity_conflict = {
        "report_key_integrity_required": True,
        "recomputed_fields": ["metric_M"],
        "actual_artifact": {"artifact_id": "artifact_A", "metric_M": 1},
        "validation_report": {"artifact_id": "artifact_B", "metric_M": 1},
    }
    assert result_integrity.actual_report_body_divergences(
        required_without_top_identity_conflict
    )
    optional_without_top_identity_conflict = dict(
        required_without_top_identity_conflict
    )
    optional_without_top_identity_conflict["report_key_integrity_required"] = False
    assert (
        result_integrity.actual_report_body_divergences(
            optional_without_top_identity_conflict
        )
        == []
    )

    required_without_top_identityless_report = {
        **required_without_top_identity_conflict,
        "validation_report": {"metric_M": 1},
    }
    assert result_integrity.actual_report_body_divergences(
        required_without_top_identityless_report
    )
    required_without_top_identity_match = {
        **required_without_top_identity_conflict,
        "validation_report": {"artifact_id": "artifact_A", "metric_M": 1},
    }
    assert (
        result_integrity.actual_report_body_divergences(
            required_without_top_identity_match
        )
        == []
    )


def profile_event(cycle_id: str, family_id: str, **overrides: Any) -> dict[str, Any]:
    event: dict[str, Any] = {
        "cycle_id": cycle_id,
        "event_id": f"{cycle_id}-{family_id}",
        "task_id": "task_T",
        "goal_axis": "goal_axis_G",
        "root_family_key": family_id,
        "producer_lineage": "family_F",
        "artifact_class": "artifact_A",
        "current_decision_lane": "lane_L",
        "input_cohort": "source_S",
        "execution_starvation_window": 2,
        "progress_verdict": "safety_only",
        "progress_kind": "governance_only",
    }
    event.update(overrides)
    return event


def bound_profile_event(
    cycle_id: str,
    family_id: str,
    *,
    required_revision_id: str = "input_revision_current",
    receipt_revision_id: str | None = None,
    include_receipt: bool = True,
) -> dict[str, Any]:
    input_digest = "a" * 64
    event = profile_event(
        cycle_id,
        family_id,
        execution_scope_applicability="applicable",
        required_input_binding={
            "revision_id": required_revision_id,
            "content_digest": input_digest,
        },
    )
    if not include_receipt:
        return event
    material = {
        "schema_version": 1,
        "run_id": f"run_{cycle_id}",
        "input_revision_id": receipt_revision_id or required_revision_id,
        "input_digest": input_digest,
        "output_digest": "b" * 64,
    }
    event["run_id"] = material["run_id"]
    event["producer_run_receipt"] = {
        **material,
        "receipt_sha256": producer_receipt_sha256(material),
    }
    return event


def test_goal_axis_stagnation_survives_family_change_and_semantic_run_resets_it(
    tmp_path: Path,
) -> None:
    events = [
        profile_event("cycle_A", "family_A"),
        profile_event("cycle_B", "family_B"),
    ]
    profile = profile_cycle_efficiency.analyze(tmp_path, events, [])
    projection = profile["goal_axis_stagnation_projection"]
    assert profile["family_scoped_event_count"] == 1
    assert projection["family_ids"] == ["family-a", "family-b"]
    assert projection["no_semantic_movement_streak"] == 2
    assert projection["family_change_resets_streak"] is False

    events.append(
        profile_event(
            "cycle_C",
            "family_C",
            run_id="run_C",
            produced_domain_delta=True,
            changed_vs_previous=True,
            semantic_progress=True,
            progress_verdict="advanced",
            progress_kind="goal_productive",
            semantic_movement_evidence_class="independently_verified",
        )
    )
    reset_profile = profile_cycle_efficiency.analyze(tmp_path, events, [])
    assert (
        reset_profile["goal_axis_stagnation_projection"]["no_semantic_movement_streak"]
        == 0
    )

    unsupported_reset = profile_cycle_efficiency.analyze(
        tmp_path,
        [
            profile_event("cycle_A", "family_A"),
            profile_event("cycle_B", "family_B", authoritative_semantic_progress=True),
        ],
        [],
    )["goal_axis_stagnation_projection"]
    assert unsupported_reset["producer_run_cycle_count"] == 0
    assert unsupported_reset["semantic_movement_cycle_count"] == 0
    assert unsupported_reset["no_semantic_movement_streak"] == 2

    unrelated_axis = profile_cycle_efficiency.analyze(
        tmp_path,
        [
            profile_event("cycle_A", "family_A"),
            profile_event(
                "cycle_B",
                "family_B",
                run_id="input_D",
                produced_domain_delta=True,
                changed_vs_previous=True,
                semantic_progress=True,
                progress_verdict="advanced",
                progress_kind="goal_productive",
                evidence_provenance={"axis_X": "independently_verified"},
            ),
        ],
        [],
    )["goal_axis_stagnation_projection"]
    assert unrelated_axis["semantic_movement_cycle_count"] == 0
    assert unrelated_axis["no_semantic_movement_streak"] == 2

    matching_axis = profile_cycle_efficiency.analyze(
        tmp_path,
        [
            profile_event("cycle_A", "family_A"),
            profile_event(
                "cycle_B",
                "family_B",
                run_id="input_D",
                produced_domain_delta=True,
                changed_vs_previous=True,
                semantic_progress=True,
                progress_verdict="advanced",
                progress_kind="goal_productive",
                evidence_provenance={"goal_axis_G": "independently_verified"},
            ),
        ],
        [],
    )["goal_axis_stagnation_projection"]
    assert matching_axis["semantic_movement_cycle_count"] == 1
    assert matching_axis["no_semantic_movement_streak"] == 0


def test_execution_scope_unknown_recovers_before_continue_and_known_scope_preserves_paths(
    tmp_path: Path,
) -> None:
    unknown = profile_cycle_efficiency.analyze(
        tmp_path,
        [{"cycle_id": "cycle_A", "task_id": "task_T", "goal_axis": "goal_axis_G"}],
        [],
    )
    assert unknown["execution_starvation_status"] == "scope_unknown"
    assert unknown["execution_starvation"] is None
    assert unknown["recommendation"] == "supply_evidence_path"

    starved = profile_cycle_efficiency.analyze(
        tmp_path, [profile_event("cycle_A", "family_A")], []
    )
    assert starved["execution_starvation_status"] == "present"
    assert starved["execution_candidate_priority_boost"] is True

    exercised = profile_cycle_efficiency.analyze(
        tmp_path,
        [profile_event("cycle_A", "family_A", run_id="run_A")],
        [],
    )
    assert exercised["execution_starvation_status"] == "absent"
    assert exercised["execution_starvation"] is False

    old_matching_run = profile_cycle_efficiency.analyze(
        tmp_path,
        [
            profile_event("cycle_A", "family_A", run_id="run_A"),
            profile_event("cycle_B", "family_B", goal_axis="axis_X"),
            profile_event("cycle_C", "family_C"),
        ],
        [],
    )
    assert old_matching_run["execution_starvation_status"] == "present"
    assert old_matching_run["recent_cycle_run_id_count"] == 0

    unknown_validation = result_contract.validate(
        "cycle_efficiency_profile", unknown, "block"
    )
    assert "cycle_efficiency_scope_unknown_auto_continue" not in finding_codes(
        unknown_validation
    )
    invalid_unknown = {
        **unknown,
        "recommendation": "stop_with_blocker",
        "recommendations": ["stop_with_blocker"],
    }
    assert "cycle_efficiency_scope_unknown_auto_continue" in finding_codes(
        result_contract.validate("cycle_efficiency_profile", invalid_unknown, "block")
    )

    legacy = dict(starved)
    for field in (
        "execution_starvation_status",
        "execution_starvation",
        "execution_scope_status",
        "scope_evidence_required",
        "goal_axis_stagnation_projection",
    ):
        legacy.pop(field, None)
    legacy_codes = finding_codes(
        result_contract.validate("cycle_efficiency_profile", legacy, "block")
    )
    assert "cycle_efficiency_execution_starvation_status_invalid" not in legacy_codes
    assert "cycle_efficiency_goal_axis_projection_invalid" not in legacy_codes

    malformed_scope = profile_event("cycle_C", "family_F")
    malformed_scope["producer_lineage"] = {"raw": "source_span_X"}
    malformed_profile = profile_cycle_efficiency.analyze(
        tmp_path, [malformed_scope], []
    )
    assert malformed_profile["execution_scope_status"] == "scope_unknown"
    assert malformed_profile["execution_starvation_status"] == "scope_unknown"
    assert "source_span_X" not in repr(malformed_profile)
    assert "'raw'" not in repr(malformed_profile)

    for malformed_run in ({"raw": "source_span_X"}, "x" * 129, "input_D\nraw"):
        profile = profile_cycle_efficiency.analyze(
            tmp_path,
            [profile_event("cycle_C", "family_F", run_id=malformed_run)],
            [],
        )
        assert profile["recent_cycle_run_ids"] == []
        assert profile["recent_cycle_run_id_count"] == 0
        assert profile["execution_starvation_status"] == "present"
        assert "source_span_X" not in repr(profile)

    valid_run = profile_cycle_efficiency.analyze(
        tmp_path,
        [profile_event("cycle_C", "family_F", run_id="input_D")],
        [],
    )
    assert valid_run["recent_cycle_run_ids"] == ["input_D"]
    assert valid_run["execution_starvation_status"] == "absent"

    inconsistent_unknown = {
        **unknown,
        "recent_cycle_run_ids": ["input_D"],
        "recent_cycle_run_id_count": 1,
    }
    assert "cycle_efficiency_scope_unknown_contract_invalid" in finding_codes(
        result_contract.validate(
            "cycle_efficiency_profile", inconsistent_unknown, "block"
        )
    )

    conflicting_scope = {**starved, "execution_scope_status": "scope_unknown"}
    assert "cycle_efficiency_scope_starvation_status_conflict" in finding_codes(
        result_contract.validate("cycle_efficiency_profile", conflicting_scope, "block")
    )

    malformed_contract = {
        **unknown,
        "task_id": {"raw": "source_span_X"},
        "scope_evidence_required": [{"raw": "source_span_X"}],
        "recent_cycle_run_ids": [{"raw": "source_span_X"}],
    }
    malformed_contract_result = result_contract.validate(
        "cycle_efficiency_profile", malformed_contract, "block"
    )
    malformed_contract_codes = finding_codes(malformed_contract_result)
    assert "cycle_efficiency_task_id_invalid" in malformed_contract_codes
    assert "cycle_efficiency_scope_evidence_ids_invalid" in malformed_contract_codes
    assert "cycle_efficiency_recent_run_ids_invalid" in malformed_contract_codes
    assert "source_span_X" not in repr(malformed_contract_result)
    assert "'raw'" not in repr(malformed_contract_result)

    for valid_profile in (unknown, starved, exercised):
        valid_codes = finding_codes(
            result_contract.validate("cycle_efficiency_profile", valid_profile, "block")
        )
        assert "cycle_efficiency_scope_starvation_status_conflict" not in valid_codes
        assert "cycle_efficiency_recent_run_count_mismatch" not in valid_codes

    evaluated_missing_scope = {
        **starved,
        "execution_scope": {**starved["execution_scope"], "goal_axis": ""},
    }
    assert "cycle_efficiency_scope_evidence_mismatch" in finding_codes(
        result_contract.validate(
            "cycle_efficiency_profile", evaluated_missing_scope, "block"
        )
    )


def test_execution_starvation_requires_exact_content_bound_input_receipt(
    tmp_path: Path,
) -> None:
    stale = profile_cycle_efficiency.analyze(
        tmp_path,
        [
            bound_profile_event(
                "cycle_A",
                "family_A",
                receipt_revision_id="input_revision_stale",
            )
        ],
        [],
    )
    assert stale["execution_starvation_status"] == "present"
    assert stale["recent_cycle_run_ids"] == []
    assert stale["recent_cycle_run_receipts"] == []

    exact = profile_cycle_efficiency.analyze(
        tmp_path,
        [bound_profile_event("cycle_A", "family_A")],
        [],
    )
    assert exact["execution_starvation_status"] == "absent"
    assert exact["recent_cycle_run_ids"] == ["run_cycle_A"]
    exact_codes = finding_codes(
        result_contract.validate("cycle_efficiency_profile", exact, "block")
    )
    assert "cycle_efficiency_starvation_absent_inconsistent" not in exact_codes
    assert "cycle_efficiency_recent_run_receipts_invalid" not in exact_codes

    stale_material = {
        **exact["recent_cycle_run_receipts"][0],
        "input_revision_id": "input_revision_stale",
    }
    stale_material["receipt_sha256"] = producer_receipt_sha256(
        {key: value for key, value in stale_material.items() if key != "receipt_sha256"}
    )
    forged_absence = {**exact, "recent_cycle_run_receipts": [stale_material]}
    assert "cycle_efficiency_starvation_absent_inconsistent" in finding_codes(
        result_contract.validate("cycle_efficiency_profile", forged_absence, "block")
    )

    tampered = copy.deepcopy(exact)
    tampered["recent_cycle_run_receipts"][0]["receipt_sha256"] = "c" * 64
    tampered_codes = finding_codes(
        result_contract.validate("cycle_efficiency_profile", tampered, "block")
    )
    assert "cycle_efficiency_recent_run_receipts_invalid" in tampered_codes
    assert "cycle_efficiency_starvation_absent_inconsistent" in tampered_codes


def test_execution_scope_applicability_distinguishes_exclusion_from_absence(
    tmp_path: Path,
) -> None:
    declared_binding_without_receipt = profile_cycle_efficiency.analyze(
        tmp_path,
        [
            profile_event(
                "cycle_A",
                "family_A",
                run_id="legacy_run",
                required_input_binding={
                    "revision_id": "input_revision_current",
                    "content_digest": "a" * 64,
                },
            )
        ],
        [],
    )
    assert declared_binding_without_receipt["execution_starvation_status"] == "present"

    excluded_event = profile_event(
        "cycle_A",
        "family_A",
        execution_scope_applicability="excluded_by_task",
        execution_scope_exclusion_reason_id="task_has_no_execution_surface",
    )
    excluded = profile_cycle_efficiency.analyze(tmp_path, [excluded_event], [])
    assert excluded["execution_scope_status"] == "excluded_by_task"
    assert excluded["execution_starvation_status"] == "present"
    assert excluded["execution_starvation"] is True
    assert excluded["execution_candidate_priority_boost"] is True
    assert excluded["recommendation"] == "resume_primary_output"
    excluded_codes = finding_codes(
        result_contract.validate("cycle_efficiency_profile", excluded, "block")
    )
    assert "cycle_efficiency_execution_scope_exclusion_invalid" not in excluded_codes
    assert "cycle_efficiency_scope_starvation_status_conflict" not in excluded_codes

    intrinsically_not_applicable = profile_cycle_efficiency.analyze(
        tmp_path,
        [
            profile_event(
                "cycle_A",
                "family_A",
                execution_scope_applicability="not_applicable",
                execution_scope_exclusion_reason_id="governance_has_no_producer",
            )
        ],
        [],
    )
    assert intrinsically_not_applicable["execution_scope_status"] == "not_applicable"
    assert (
        intrinsically_not_applicable["execution_starvation_status"] == "not_applicable"
    )
    assert intrinsically_not_applicable["execution_starvation"] is None
    assert intrinsically_not_applicable["recommendation"] == "continue"
    not_applicable_codes = finding_codes(
        result_contract.validate(
            "cycle_efficiency_profile", intrinsically_not_applicable, "block"
        )
    )
    assert (
        "cycle_efficiency_execution_scope_not_applicable_invalid"
        not in not_applicable_codes
    )
    assert (
        "cycle_efficiency_scope_starvation_status_conflict" not in not_applicable_codes
    )

    missing_reason = {**excluded, "execution_scope_exclusion_reason_id": None}
    assert "cycle_efficiency_execution_scope_exclusion_invalid" in finding_codes(
        result_contract.validate("cycle_efficiency_profile", missing_reason, "block")
    )

    contradictory_exclusion = profile_cycle_efficiency.analyze(
        tmp_path,
        [
            {
                **excluded_event,
                "run_id": "unexpected_run",
            }
        ],
        [],
    )
    assert contradictory_exclusion["execution_scope_status"] == "scope_unknown"
    assert contradictory_exclusion["execution_starvation_status"] == "scope_unknown"
    assert (
        "execution_scope_applicability"
        in contradictory_exclusion["scope_evidence_required"]
    )

    applicable_without_binding = profile_cycle_efficiency.analyze(
        tmp_path,
        [
            profile_event(
                "cycle_A",
                "family_A",
                execution_scope_applicability="applicable",
            )
        ],
        [],
    )
    assert applicable_without_binding["execution_starvation_status"] == "scope_unknown"
    assert (
        "required_input_binding"
        in applicable_without_binding["scope_evidence_required"]
    )

    unknown = profile_cycle_efficiency.analyze(
        tmp_path,
        [{"cycle_id": "cycle_A", "task_id": "task_T", "goal_axis": "goal_axis_G"}],
        [],
    )
    unknown_with_filled_scope = {
        **unknown,
        "execution_scope": {
            "goal_axis": "goal_axis_G",
            "producer_lineage": "family_F",
            "artifact_class": "artifact_A",
            "decision_lane": "lane_L",
        },
    }
    assert "cycle_efficiency_scope_evidence_mismatch" in finding_codes(
        result_contract.validate(
            "cycle_efficiency_profile", unknown_with_filled_scope, "block"
        )
    )


def test_task_pack_expectation_miss_requires_review_and_preserves_match_path() -> None:
    miss = current_validate_packet(
        progress_kind_expected="goal_productive",
        progress_kind="governance_only",
        metadata_only=True,
        expectation_miss_streak=2,
        repeated_expectation_miss=True,
        expectation_comparison={
            "status": "miss",
            "mismatched_axes": ["progress_kind"],
            "remaining_pack_review": "continue",
        },
    )
    miss_result = result_contract.validate("validate", miss, "block")
    assert "task_pack_repeated_metadata_miss_auto_continue" in finding_codes(
        miss_result
    )

    happy = current_validate_packet(
        progress_kind_expected="goal_productive",
        progress_kind="goal_productive",
        expectation_comparison={
            "status": "match",
            "mismatched_axes": [],
            "remaining_pack_review": "continue",
        },
    )
    happy_result = result_contract.validate("validate", happy, "block")
    assert not (
        {"task_pack_expectation_false_match", "task_pack_expectation_miss_unreviewed"}
        & finding_codes(happy_result)
    )

    missing_comparison = current_validate_packet(
        progress_kind_expected="goal_productive",
        progress_kind="governance_only",
        pack_transition_applied=True,
    )
    assert "task_pack_expectation_comparison_missing" in finding_codes(
        result_contract.validate("validate", missing_comparison, "block")
    )

    missing_actual = current_validate_packet(
        semantic_signature_expected="axis_X",
        required_output_classes=["artifact_A"],
        observed_output_classes=[],
        expectation_comparison={
            "status": "match",
            "mismatched_axes": [],
            "remaining_pack_review": "continue",
        },
    )
    assert "task_pack_expectation_false_match" in finding_codes(
        result_contract.validate("validate", missing_actual, "block")
    )

    missing_actual_miss = current_validate_packet(
        semantic_signature_expected="axis_X",
        expectation_comparison={
            "status": "miss",
            "mismatched_axes": ["semantic_signature"],
            "remaining_pack_review": "reorder",
        },
    )
    assert "task_pack_expectation_actual_missing_status" in finding_codes(
        result_contract.validate("validate", missing_actual_miss, "block")
    )

    single_miss = current_validate_packet(
        progress_kind_expected="goal_productive",
        progress_kind="governance_only",
        metadata_only=True,
        expectation_miss_streak=1,
        expectation_comparison={
            "status": "miss",
            "mismatched_axes": ["progress_kind"],
            "remaining_pack_review": "continue",
        },
    )
    assert "task_pack_repeated_metadata_miss_auto_continue" not in finding_codes(
        result_contract.validate("validate", single_miss, "block")
    )

    nested_output_expectation = current_validate_packet(
        task_pack_item={
            "adoption_axis_contract": {"required_output_classes": ["artifact_A"]},
        },
        pack_transition_applied=True,
    )
    assert "task_pack_expectation_comparison_missing" in finding_codes(
        result_contract.validate("validate", nested_output_expectation, "block")
    )

    nested_output_match = current_validate_packet(
        task_pack_item={
            "adoption_axis_contract": {"required_output_classes": ["artifact_A"]},
            "result": {
                "observed_output_classes": ["artifact_A"],
                "expectation_comparison": {
                    "status": "match",
                    "mismatched_axes": [],
                    "remaining_pack_review": "continue",
                },
            },
        },
    )
    nested_match_codes = finding_codes(
        result_contract.validate("validate", nested_output_match, "block")
    )
    assert "task_pack_expectation_comparison_missing" not in nested_match_codes
    assert "task_pack_expectation_false_match" not in nested_match_codes

    malformed = current_validate_packet(
        progress_kind_expected={"raw": "source_span_X"},
        progress_kind={"raw": "source_span_X"},
        required_output_classes=[{"raw": "source_span_X"}],
        observed_output_classes=[{"raw": "source_span_X"}],
        expectation_comparison={
            "status": "match",
            "mismatched_axes": [{"raw": "source_span_X"}],
            "remaining_pack_review": "continue",
        },
    )
    malformed_result = result_contract.validate("validate", malformed, "block")
    assert "task_pack_expectation_contract_invalid" in finding_codes(malformed_result)
    assert "source_span_X" not in repr(malformed_result)
    assert "'raw'" not in repr(malformed_result)

    nested_transition = current_validate_packet(
        task_pack_item={
            "progress_kind_expected": "goal_productive",
            "result": {
                "progress_kind": "governance_only",
                "pack_transition_applied": True,
                "expectation_comparison": {
                    "status": "miss",
                    "mismatched_axes": ["progress_kind"],
                    "remaining_pack_review": "reorder",
                },
            },
        },
    )
    assert "task_pack_expectation_unresolved_transition" in finding_codes(
        result_contract.validate("validate", nested_transition, "block")
    )

    not_applicable_bypass = current_validate_packet(
        progress_kind_expected="goal_productive",
        progress_kind="governance_only",
        pack_transition_applied=True,
        expectation_comparison={
            "status": "not_applicable",
            "mismatched_axes": [],
            "remaining_pack_review": "continue",
        },
    )
    not_applicable_codes = finding_codes(
        result_contract.validate("validate", not_applicable_bypass, "block")
    )
    assert "task_pack_expectation_status_mismatch" in not_applicable_codes
    assert "task_pack_expectation_unresolved_transition" in not_applicable_codes

    contradictory_nested_expectation = current_validate_packet(
        progress_kind_expected="goal_productive",
        progress_kind="goal_productive",
        expectation_comparison={
            "status": "match",
            "mismatched_axes": [],
            "remaining_pack_review": "continue",
        },
        task_pack_item={
            "progress_kind_expected": "goal_productive",
            "result": {
                "progress_kind": "governance_only",
                "pack_transition_applied": True,
                "expectation_comparison": {
                    "status": "miss",
                    "mismatched_axes": ["progress_kind"],
                    "remaining_pack_review": "reorder",
                },
            },
        },
    )
    assert "task_pack_expectation_surface_conflict" in finding_codes(
        result_contract.validate("validate", contradictory_nested_expectation, "block")
    )

    converged_duplicate_expectation = current_validate_packet(
        progress_kind_expected="goal_productive",
        progress_kind="goal_productive",
        expectation_comparison={
            "status": "match",
            "mismatched_axes": [],
            "remaining_pack_review": "continue",
        },
        task_pack_item={
            "progress_kind_expected": "goal_productive",
            "result": {
                "progress_kind": "goal_productive",
                "expectation_comparison": {
                    "status": "match",
                    "mismatched_axes": [],
                    "remaining_pack_review": "continue",
                },
            },
        },
    )
    assert "task_pack_expectation_surface_conflict" not in finding_codes(
        result_contract.validate("validate", converged_duplicate_expectation, "block")
    )


def qualitative_surface_packet(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "step": "qualitative_review",
        "task_id": "task_T",
        "review_agent_count": 1,
        "review_status": "complete",
        "quality_verdict": "acceptable",
        "agent_routing_applicability": "deterministic_only",
        "blockers": [],
        "evidence_paths": ["packet_K.json"],
        "surface_field_review_gate": {
            "surface_field_review_status": "pass",
            "surface_field_classes": ["axis_X", "axis_Y"],
            "field_class_results": rows,
        },
    }


def field_row(field_class_id: str, **overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "field_class_id": field_class_id,
        "applicability_status": "applicable",
        "review_status": "pass",
        "observed_count": 1,
        "locator_status": "present",
        "referential_substance_status": "meaningful",
        "defect_counts": {},
    }
    row.update(overrides)
    return row


def test_surface_review_requires_every_active_class_and_referential_substance() -> None:
    representative_only = result_contract.validate(
        "qualitative_review",
        qualitative_surface_packet([field_row("axis_X")]),
        "block",
    )
    assert "qualitative_review_surface_class_bypass" in finding_codes(
        representative_only
    )

    locator_only = result_contract.validate(
        "qualitative_review",
        qualitative_surface_packet(
            [
                field_row("axis_X"),
                field_row(
                    "axis_Y", referential_substance_status="insufficient_evidence"
                ),
            ]
        ),
        "block",
    )
    assert "qualitative_review_surface_class_bypass" in finding_codes(locator_only)

    locator_missing = result_contract.validate(
        "qualitative_review",
        qualitative_surface_packet(
            [
                field_row("axis_X"),
                field_row(
                    "axis_Y", locator_status="missing", referential_substance_status=""
                ),
            ]
        ),
        "block",
    )
    assert "qualitative_review_surface_class_bypass" in finding_codes(locator_missing)

    missing_map_packet = qualitative_surface_packet([])
    missing_map_packet["surface_field_review_gate"].update(
        {"surface_field_classes": [], "field_class_map_missing": True}
    )
    assert "qualitative_review_surface_class_bypass" in finding_codes(
        result_contract.validate("qualitative_review", missing_map_packet, "block")
    )

    duplicate_rows = qualitative_surface_packet(
        [field_row("axis_X"), field_row("axis_X"), field_row("axis_Y")]
    )
    assert "qualitative_review_surface_class_bypass" in finding_codes(
        result_contract.validate("qualitative_review", duplicate_rows, "block")
    )

    happy = result_contract.validate(
        "qualitative_review",
        qualitative_surface_packet([field_row("axis_X"), field_row("axis_Y")]),
        "block",
    )
    assert "qualitative_review_surface_class_bypass" not in finding_codes(happy)

    not_applicable = result_contract.validate(
        "qualitative_review",
        qualitative_surface_packet(
            [
                field_row("axis_X"),
                field_row("axis_Y", applicability_status="not_applicable"),
            ]
        ),
        "block",
    )
    assert "qualitative_review_surface_class_bypass" not in finding_codes(
        not_applicable
    )

    referential_not_applicable = result_contract.validate(
        "qualitative_review",
        qualitative_surface_packet(
            [
                field_row("axis_X"),
                field_row(
                    "axis_Y",
                    locator_status="not_applicable",
                    referential_substance_status="not_applicable",
                ),
            ]
        ),
        "block",
    )
    assert "qualitative_review_surface_class_bypass" not in finding_codes(
        referential_not_applicable
    )

    for malformed_row in (
        field_row("axis_Y", observed_count=True),
        field_row("axis_Y", defect_counts={"opaque": "1"}),
    ):
        malformed_counts = result_contract.validate(
            "qualitative_review",
            qualitative_surface_packet([field_row("axis_X"), malformed_row]),
            "block",
        )
        assert "qualitative_review_surface_class_bypass" in finding_codes(
            malformed_counts
        )

    malformed_ids_packet = qualitative_surface_packet([field_row("axis_X")])
    malformed_ids_packet["surface_field_review_gate"].update(
        {
            "surface_field_classes": ["axis_X", {"raw": "source_span_X"}],
            "field_class_results": [
                field_row("axis_X"),
                {**field_row("axis_Y"), "field_class_id": {"raw": "source_span_X"}},
            ],
        }
    )
    malformed_ids_result = result_contract.validate(
        "qualitative_review", malformed_ids_packet, "block"
    )
    assert "qualitative_review_surface_class_bypass" in finding_codes(
        malformed_ids_result
    )
    assert "source_span_X" not in repr(malformed_ids_result)
    assert "'raw'" not in repr(malformed_ids_result)

    matrix_conflict_packet = qualitative_surface_packet(
        [field_row("axis_X"), field_row("axis_Y")]
    )
    matrix_conflict_packet["surface_field_review_gate"][
        "surface_field_defect_matrix"
    ] = {
        "axis_X": {"opaque": 1},
        "axis_Y": {},
    }
    assert "qualitative_review_surface_class_bypass" in finding_codes(
        result_contract.validate("qualitative_review", matrix_conflict_packet, "block")
    )

    matrix_happy_packet = qualitative_surface_packet(
        [field_row("axis_X"), field_row("axis_Y")]
    )
    matrix_happy_packet["surface_field_review_gate"]["surface_field_defect_matrix"] = {
        "axis_X": {},
        "axis_Y": {},
    }
    assert "qualitative_review_surface_class_bypass" not in finding_codes(
        result_contract.validate("qualitative_review", matrix_happy_packet, "block")
    )

    empty_pass = qualitative_surface_packet([])
    empty_pass["surface_field_review_gate"]["surface_field_classes"] = []
    assert "qualitative_review_surface_class_bypass" in finding_codes(
        result_contract.validate("qualitative_review", empty_pass, "block")
    )

    explicit_na = qualitative_surface_packet([])
    explicit_na["surface_field_review_gate"].update(
        {
            "surface_field_review_status": "not_applicable",
            "surface_field_inventory_status": "not_applicable",
            "surface_field_classes": [],
        }
    )
    assert "qualitative_review_surface_class_bypass" not in finding_codes(
        result_contract.validate("qualitative_review", explicit_na, "block")
    )

    optional_missing = qualitative_surface_packet([])
    optional_missing["surface_field_review_gate"].update(
        {
            "surface_field_review_status": "not_evaluated",
            "surface_field_classes": [],
            "field_class_map_missing": True,
        }
    )
    optional_missing_result = result_contract.validate(
        "qualitative_review", optional_missing, "block"
    )
    optional_findings = [
        row
        for row in optional_missing_result["findings"]
        if row.get("code") == "qualitative_review_surface_class_bypass"
    ]
    assert optional_findings and optional_findings[0]["severity"] == "warn"

    required_missing = {**optional_missing, "surface_field_review_required": True}
    required_missing_result = result_contract.validate(
        "qualitative_review", required_missing, "block"
    )
    required_findings = [
        row
        for row in required_missing_result["findings"]
        if row.get("code") == "qualitative_review_surface_class_bypass"
    ]
    assert required_findings and required_findings[0]["severity"] == "block"

    required_gate_absent = qualitative_surface_packet(
        [field_row("axis_X"), field_row("axis_Y")]
    )
    required_gate_absent.pop("surface_field_review_gate")
    required_gate_absent["surface_field_review_required"] = True
    assert "qualitative_review_surface_required_missing" in finding_codes(
        result_contract.validate("qualitative_review", required_gate_absent, "block")
    )

    optional_gate_absent = dict(required_gate_absent)
    optional_gate_absent.pop("surface_field_review_required")
    assert "qualitative_review_surface_required_missing" not in finding_codes(
        result_contract.validate("qualitative_review", optional_gate_absent, "block")
    )

    nested_required = qualitative_surface_packet(
        [field_row("axis_X"), field_row("axis_Y")]
    )
    nested_required["surface_field_review_required"] = False
    nested_required["quality_review"] = {
        "surface_field_review_gate": {"required_for_acceptance": True},
    }
    nested_required["surface_field_review_gate"]["surface_field_review_status"] = (
        "not_evaluated"
    )
    assert "qualitative_review_surface_required_not_passed" in finding_codes(
        result_contract.validate("qualitative_review", nested_required, "block")
    )

    result_required_missing = qualitative_surface_packet(
        [field_row("axis_X"), field_row("axis_Y")]
    )
    result_required_missing.pop("surface_field_review_gate")
    result_required_missing["result"] = {"surface_field_review_required": True}
    assert "qualitative_review_surface_required_missing" in finding_codes(
        result_contract.validate("qualitative_review", result_required_missing, "block")
    )

    printable_raw_id = qualitative_surface_packet([field_row("axis_X")])
    printable_raw_id["surface_field_review_gate"].update(
        {
            "surface_field_classes": ["axis_X", "source_span_X source_S"],
            "field_class_results": [field_row("axis_X")],
        }
    )
    printable_raw_result = result_contract.validate(
        "qualitative_review", printable_raw_id, "block"
    )
    assert "qualitative_review_surface_class_bypass" in finding_codes(
        printable_raw_result
    )
    assert "source_span_X source_S" not in repr(printable_raw_result)

    nested_decision_required = qualitative_surface_packet([])
    nested_decision_required.pop("surface_field_review_gate")
    nested_decision_required["qualitative_review"] = {
        "surface_field_review_gate": {
            "decision_contribution_allowed": True,
            "surface_field_review_status": "not_evaluated",
            "surface_field_classes": [],
            "field_class_results": [],
        }
    }
    nested_decision_result = result_contract.validate(
        "qualitative_review", nested_decision_required, "block"
    )
    nested_decision_findings = [
        row
        for row in nested_decision_result["findings"]
        if row.get("code") == "qualitative_review_surface_required_not_passed"
    ]
    assert nested_decision_findings
    assert nested_decision_findings[0]["severity"] == "block"

    result_quality_surface = qualitative_surface_packet(
        [field_row("axis_X"), field_row("axis_Y")]
    )
    result_quality_gate = result_quality_surface.pop("surface_field_review_gate")
    result_quality_surface["result"] = {
        "quality_review": {
            "surface_field_review_required": True,
            "surface_field_review_gate": result_quality_gate,
        }
    }
    result_quality_surface_codes = finding_codes(
        result_contract.validate("qualitative_review", result_quality_surface, "block")
    )
    assert (
        "qualitative_review_surface_required_missing"
        not in result_quality_surface_codes
    )
    assert "qualitative_review_surface_class_bypass" not in result_quality_surface_codes

    private_surface_status = qualitative_surface_packet(
        [field_row("axis_X"), field_row("axis_Y")]
    )
    private_surface_status["surface_field_review_required"] = True
    private_surface_status["surface_field_review_gate"][
        "surface_field_review_status"
    ] = "source_span_X source_S"
    private_surface_result = result_contract.validate(
        "qualitative_review", private_surface_status, "block"
    )
    assert "qualitative_review_surface_required_not_passed" in finding_codes(
        private_surface_result
    )
    assert "source_span_X source_S" not in repr(private_surface_result)


def test_referential_substance_projection_is_separate_from_structural_presence() -> (
    None
):
    unresolved = qualitative_surface_packet([field_row("axis_X"), field_row("axis_Y")])
    unresolved.update(
        {
            "substance_density_evaluation_status": "insufficient_evidence",
            "referential_substance_counts": {"meaningful": 1, "opaque": 0},
        }
    )
    assert "qualitative_review_referential_substance_bypass" in finding_codes(
        result_contract.validate("qualitative_review", unresolved, "block")
    )

    meaningful = qualitative_surface_packet([field_row("axis_X"), field_row("axis_Y")])
    meaningful.update(
        {
            "substance_density_evaluation_status": "meaningful",
            "referential_substance_counts": {
                "meaningful": 2,
                "opaque": 0,
                "incompatible_collision": 0,
                "possible_false_split": 0,
            },
        }
    )
    assert "qualitative_review_referential_substance_bypass" not in finding_codes(
        result_contract.validate("qualitative_review", meaningful, "block")
    )

    collision = {
        **meaningful,
        "referential_substance_counts": {
            "meaningful": 2,
            "opaque": 0,
            "incompatible_collision": 1,
            "possible_false_split": 0,
        },
    }
    assert "qualitative_review_referential_substance_bypass" in finding_codes(
        result_contract.validate("qualitative_review", collision, "block")
    )

    density_na_with_stale_counts = {
        **meaningful,
        "substance_density_evaluation_status": "not_applicable",
        "referential_substance_counts": {
            "meaningful": 0,
            "opaque": 3,
            "incompatible_collision": 1,
            "possible_false_split": 1,
        },
    }
    assert "qualitative_review_referential_substance_bypass" not in finding_codes(
        result_contract.validate(
            "qualitative_review", density_na_with_stale_counts, "block"
        )
    )

    optional_unobserved = {
        **meaningful,
        "substance_density_evaluation_status": "insufficient_evidence",
    }
    optional_unobserved_result = result_contract.validate(
        "qualitative_review", optional_unobserved, "block"
    )
    optional_density_findings = [
        row
        for row in optional_unobserved_result["findings"]
        if row.get("code") == "qualitative_review_referential_substance_bypass"
    ]
    assert (
        optional_density_findings and optional_density_findings[0]["severity"] == "warn"
    )

    required_unobserved = {**optional_unobserved, "substance_density_required": True}
    required_unobserved_result = result_contract.validate(
        "qualitative_review", required_unobserved, "block"
    )
    required_density_findings = [
        row
        for row in required_unobserved_result["findings"]
        if row.get("code") == "qualitative_review_referential_substance_bypass"
    ]
    assert (
        required_density_findings
        and required_density_findings[0]["severity"] == "block"
    )

    required_density_absent = qualitative_surface_packet(
        [field_row("axis_X"), field_row("axis_Y")]
    )
    required_density_absent["substance_density_required"] = True
    assert "qualitative_review_substance_density_required_missing" in finding_codes(
        result_contract.validate("qualitative_review", required_density_absent, "block")
    )
    assert "qualitative_review_substance_density_required_missing" not in finding_codes(
        result_contract.validate(
            "qualitative_review",
            qualitative_surface_packet([field_row("axis_X"), field_row("axis_Y")]),
            "block",
        )
    )

    zero_meaning = {
        **meaningful,
        "substance_density_required": True,
        "referential_substance_counts": {
            "meaningful": 0,
            "opaque": 0,
            "incompatible_collision": 0,
            "possible_false_split": 0,
        },
    }
    assert "qualitative_review_referential_substance_bypass" in finding_codes(
        result_contract.validate("qualitative_review", zero_meaning, "block")
    )

    raw_density_status = {
        **meaningful,
        "substance_density_evaluation_status": "source_span_X source_S",
    }
    raw_density_result = result_contract.validate(
        "qualitative_review", raw_density_status, "block"
    )
    assert "qualitative_review_referential_substance_bypass" in finding_codes(
        raw_density_result
    )
    assert "source_span_X source_S" not in repr(raw_density_result)

    nested_density_required = dict(meaningful)
    nested_density_required["substance_density_required"] = False
    nested_density_required["quality_review"] = {
        "substance_density_gate": {"required_for_acceptance": True},
    }
    nested_density_required.pop("substance_density_evaluation_status")
    assert "qualitative_review_substance_density_required_missing" in finding_codes(
        result_contract.validate("qualitative_review", nested_density_required, "block")
    )

    nested_density_decision = qualitative_surface_packet(
        [field_row("axis_X"), field_row("axis_Y")]
    )
    nested_density_decision["qualitative_review"] = {
        "substance_density_gate": {
            "decision_contribution_allowed": True,
            "evaluation_status": "insufficient_evidence",
        }
    }
    nested_density_decision_result = result_contract.validate(
        "qualitative_review", nested_density_decision, "block"
    )
    nested_density_decision_findings = [
        row
        for row in nested_density_decision_result["findings"]
        if row.get("code") == "qualitative_review_referential_substance_bypass"
    ]
    assert nested_density_decision_findings
    assert nested_density_decision_findings[0]["severity"] == "block"

    result_quality_density = qualitative_surface_packet(
        [field_row("axis_X"), field_row("axis_Y")]
    )
    result_quality_density["result"] = {
        "quality_review": {
            "substance_density_required": True,
            "substance_density_evaluation_status": "meaningful",
            "referential_substance_counts": {
                "meaningful": 2,
                "opaque": 0,
                "incompatible_collision": 0,
                "possible_false_split": 0,
            },
        }
    }
    result_quality_density_codes = finding_codes(
        result_contract.validate("qualitative_review", result_quality_density, "block")
    )
    assert (
        "qualitative_review_substance_density_required_missing"
        not in result_quality_density_codes
    )
    assert (
        "qualitative_review_referential_substance_bypass"
        not in result_quality_density_codes
    )

    nested_quality_density = qualitative_surface_packet(
        [field_row("axis_X"), field_row("axis_Y")]
    )
    nested_quality_density["qualitative_review"] = {
        "substance_density_required": True,
        "substance_density_evaluation_status": "meaningful",
        "referential_substance_counts": {
            "meaningful": 2,
            "opaque": 0,
            "incompatible_collision": 0,
            "possible_false_split": 0,
        },
    }
    nested_quality_density_codes = finding_codes(
        result_contract.validate("qualitative_review", nested_quality_density, "block")
    )
    assert (
        "qualitative_review_substance_density_required_missing"
        not in nested_quality_density_codes
    )
    assert (
        "qualitative_review_referential_substance_bypass"
        not in nested_quality_density_codes
    )


def test_verification_provenance_requires_disjoint_inputs_and_preserves_happy_path() -> (
    None
):
    coupled = current_validate_packet(
        verification_axes=[
            {
                "axis_id": "axis_X",
                "coupling_status": "same_artifact",
                "evidence_provenance": "independently_verified",
            }
        ]
    )
    assert "verification_axis_independent_without_disjoint_inputs" in finding_codes(
        result_contract.validate("validate", coupled, "block")
    )

    same_function = current_validate_packet(
        verification_axes=[
            {
                "axis_id": "axis_X",
                "coupling_status": "disjoint",
                "evidence_provenance": "independently_verified",
                "producer_function_id": "producer_F",
                "verifier_function_id": "producer_F",
                "producer_input_fingerprint": "a" * 64,
                "verifier_input_fingerprint": "a" * 64,
            }
        ]
    )
    assert "verification_axis_independent_with_coupled_lineage" in finding_codes(
        result_contract.validate("validate", same_function, "block")
    )

    disjoint = current_validate_packet(
        verification_axes=[
            {
                "axis_id": "axis_X",
                "coupling_status": "disjoint",
                "evidence_provenance": "independently_verified",
                "producer_function_id": "producer_F",
                "verifier_function_id": "verifier_F",
                "producer_invariant_owner_id": "producer_owner_A",
                "verifier_invariant_owner_id": "verifier_owner_B",
                "invariant_separation_status": "independent",
                "producer_input_fingerprint": "a" * 64,
                "verifier_input_fingerprint": "b" * 64,
            }
        ]
    )
    assert "verification_axis_independent_without_disjoint_inputs" not in finding_codes(
        result_contract.validate("validate", disjoint, "block")
    )
    assert "verification_axis_independent_with_coupled_lineage" not in finding_codes(
        result_contract.validate("validate", disjoint, "block")
    )
    assert (
        "verification_axis_independent_without_invariant_separation"
        not in finding_codes(result_contract.validate("validate", disjoint, "block"))
    )

    different_file_same_owner = current_validate_packet(
        verification_axes=[
            {
                "axis_id": "axis_X",
                "coupling_status": "disjoint",
                "evidence_provenance": "independently_verified",
                "producer_function_id": "producer_F",
                "verifier_function_id": "verifier_F",
                "producer_input_fingerprint": "a" * 64,
                "verifier_input_fingerprint": "b" * 64,
                "producer_invariant_owner_id": "shared_owner",
                "verifier_invariant_owner_id": "shared_owner",
                "invariant_separation_status": "independent",
            }
        ]
    )
    same_owner_codes = finding_codes(
        result_contract.validate("validate", different_file_same_owner, "block")
    )
    assert (
        "verification_axis_independent_without_invariant_separation" in same_owner_codes
    )
    assert "verification_axis_false_invariant_separation" in same_owner_codes

    missing_owner = current_validate_packet(
        verification_axes=[
            {
                "axis_id": "axis_X",
                "coupling_status": "disjoint",
                "evidence_provenance": "independently_verified",
                "producer_function_id": "producer_F",
                "verifier_function_id": "verifier_F",
                "producer_input_fingerprint": "a" * 64,
                "verifier_input_fingerprint": "b" * 64,
            }
        ]
    )
    assert (
        "verification_axis_independent_without_invariant_separation"
        in finding_codes(result_contract.validate("validate", missing_owner, "block"))
    )

    self_grounded_global = current_validate_packet(
        verification_axes=[
            {
                "axis_id": "axis_X",
                "axis_scope": "global",
                "axis_kind": "semantic",
                "coupling_status": "same_artifact",
                "evidence_provenance": "self_grounded",
            }
        ]
    )
    global_codes = finding_codes(
        result_contract.validate("validate", self_grounded_global, "block")
    )
    assert "self_grounded_semantic_axis_overclaim" in global_codes
    assert "self_grounded_scope_invalid" in global_codes

    self_grounded_root = current_validate_packet(
        verification_axes=[
            {
                "axis_id": "axis_X",
                "axis_scope": "root_local",
                "axis_kind": "structural",
                "coupling_status": "same_artifact",
                "evidence_provenance": "self_grounded",
            }
        ]
    )
    root_codes = finding_codes(
        result_contract.validate("validate", self_grounded_root, "block")
    )
    assert "self_grounded_semantic_axis_overclaim" not in root_codes
    assert "self_grounded_scope_invalid" not in root_codes

    malformed_lineage = current_validate_packet(
        verification_axes=[
            {
                "axis_id": "axis_X",
                "coupling_status": "disjoint",
                "evidence_provenance": "independently_verified",
                "producer_function_id": {"raw": "source_span_X"},
                "verifier_function_id": {"raw": "source_span_X"},
                "producer_input_ids": [{"raw": "source_span_X"}],
                "verifier_input_ids": [{"raw": "source_span_X"}],
            }
        ]
    )
    malformed_lineage_result = result_contract.validate(
        "validate", malformed_lineage, "block"
    )
    malformed_codes = finding_codes(malformed_lineage_result)
    assert "verification_axis_lineage_invalid" in malformed_codes
    assert "verification_axis_independent_with_coupled_lineage" in malformed_codes
    assert "source_span_X" not in repr(malformed_lineage_result)
    assert "'raw'" not in repr(malformed_lineage_result)

    malformed_axis = current_validate_packet(
        verification_axes=[
            {
                "axis_id": {"raw": "source_span_X"},
                "coupling_status": "disjoint",
                "evidence_provenance": "independently_verified",
            }
        ]
    )
    malformed_axis_result = result_contract.validate(
        "validate", malformed_axis, "block"
    )
    assert "verification_axis_identity_missing" in finding_codes(malformed_axis_result)
    assert "source_span_X" not in repr(malformed_axis_result)

    no_lineage = current_validate_packet(
        verification_axes=[
            {
                "axis_id": "axis_X",
                "coupling_status": "disjoint",
                "evidence_provenance": "independently_verified",
            }
        ]
    )
    assert "verification_axis_independent_without_lineage_basis" in finding_codes(
        result_contract.validate("validate", no_lineage, "block")
    )

    malformed_required = current_validate_packet(
        required_verification_axis_ids=[{"raw": "source_span_X"}],
    )
    malformed_required_result = result_contract.validate(
        "validate", malformed_required, "block"
    )
    malformed_required_findings = [
        finding
        for finding in malformed_required_result["findings"]
        if finding.get("code") == "verification_axis_required_ids_invalid"
    ]
    assert malformed_required_findings
    assert malformed_required_findings[0]["severity"] == "block"
    assert "source_span_X" not in repr(malformed_required_result)

    empty_required_contract = current_validate_packet(
        verification_axes_required=True,
        required_verification_axis_ids=[],
        verification_axes=[],
    )
    assert "verification_axis_contract_missing" in finding_codes(
        result_contract.validate("validate", empty_required_contract, "block")
    )

    malformed_axes_contract = current_validate_packet(
        verification_axes_required=True,
        required_verification_axis_ids=["axis_X"],
        verification_axes={"raw": "source_span_X"},
    )
    malformed_axes_result = result_contract.validate(
        "validate", malformed_axes_contract, "block"
    )
    assert "verification_axis_contract_missing" in finding_codes(malformed_axes_result)
    assert "source_span_X" not in repr(malformed_axes_result)

    malformed_provenance = current_validate_packet(
        required_verification_axis_ids=["axis_X"],
        verification_axes=[
            {
                "axis_id": "axis_X",
                "coupling_status": "disjoint",
                "evidence_provenance": {"raw": "source_span_X"},
            }
        ],
    )
    malformed_provenance_result = result_contract.validate(
        "validate", malformed_provenance, "block"
    )
    assert "required_verification_axis_not_evaluated" in finding_codes(
        malformed_provenance_result
    )
    assert "source_span_X" not in repr(malformed_provenance_result)

    for partial_lineage in (
        {
            "producer_function_id": "producer_F",
            "verifier_function_id": "verifier_F",
        },
        {
            "producer_input_ids": ["input_D"],
            "verifier_input_ids": ["source_S"],
        },
    ):
        partial = current_validate_packet(
            verification_axes=[
                {
                    "axis_id": "axis_X",
                    "coupling_status": "disjoint",
                    "evidence_provenance": "independently_verified",
                    **partial_lineage,
                }
            ]
        )
        assert "verification_axis_independent_without_lineage_basis" in finding_codes(
            result_contract.validate("validate", partial, "block")
        )


def test_completion_consumer_blocks_coupled_invariant_summary() -> None:
    coupled = current_validate_packet(
        independently_verified_fields=["axis_X"],
        independent_source_separation_status="pass",
        independent_invariant_separation_status="coupled",
    )
    codes = finding_codes(result_contract.validate("validate", coupled, "block"))
    assert "validate_independent_verification_invariant_not_separated" in codes

    separated = current_validate_packet(
        independently_verified_fields=["axis_X"],
        independent_source_separation_status="pass",
        independent_invariant_separation_status="pass",
    )
    separated_codes = finding_codes(
        result_contract.validate("validate", separated, "block")
    )
    assert (
        "validate_independent_verification_invariant_not_separated"
        not in separated_codes
    )


def current_state_projection(status: str = "current") -> dict[str, Any]:
    return {
        "projection_epoch": "cycle_C",
        "source_decision_id": "packet_K",
        "surface_epochs": {
            "authority": "cycle_C",
            "task": "cycle_C",
            "index": "cycle_C",
        },
        "authority_digest": "a" * 64,
        "task_digest": "b" * 64,
        "index_digest": "c" * 64,
        "projection_status": status,
    }


def test_state_projection_stale_routes_repair_before_user_reask_and_current_is_happy() -> (
    None
):
    stale_projection = current_state_projection("stale_projection")
    stale_projection["surface_epochs"]["task"] = "cycle_B"
    stale = current_validate_packet(
        state_projection=stale_projection,
        state_projection_required=True,
        user_input_required=True,
    )
    stale_codes = finding_codes(result_contract.validate("validate", stale, "block"))
    assert "state_projection_not_current" in stale_codes
    assert "state_projection_repair_precedes_user_reask" in stale_codes

    current = current_validate_packet(state_projection=current_state_projection())
    current_codes = finding_codes(
        result_contract.validate("validate", current, "block")
    )
    assert "state_projection_false_current" not in current_codes
    assert "state_projection_not_current" not in current_codes

    false_current = current_state_projection()
    false_current["surface_epochs"]["index"] = "cycle_B"
    false_current_codes = finding_codes(
        result_contract.validate(
            "validate",
            current_validate_packet(
                state_projection=false_current,
                state_projection_required=True,
                user_input_required=True,
            ),
            "block",
        )
    )
    assert "state_projection_false_current" in false_current_codes
    assert "state_projection_not_current" in false_current_codes
    assert "state_projection_repair_precedes_user_reask" in false_current_codes

    missing_required = result_contract.validate(
        "validate",
        current_validate_packet(
            state_projection_required=True, lifecycle_transition_applied=True
        ),
        "block",
    )
    assert "state_projection_missing" in finding_codes(missing_required)

    malformed_identity = current_state_projection()
    malformed_identity["projection_epoch"] = {"raw": "cycle_C"}
    malformed_identity["source_decision_id"] = {"raw": "packet_K"}
    malformed_codes = finding_codes(
        result_contract.validate(
            "validate",
            current_validate_packet(
                state_projection=malformed_identity,
                state_projection_required=True,
            ),
            "block",
        )
    )
    assert "state_projection_false_current" in malformed_codes

    advisory_stale = result_contract.validate(
        "validate",
        current_validate_packet(state_projection=stale_projection),
        "block",
    )
    advisory_findings = [
        row
        for row in advisory_stale["findings"]
        if row.get("code") == "state_projection_not_current"
    ]
    assert advisory_findings == []

    task_only_trigger = result_contract.validate(
        "validate",
        current_validate_packet(task_projection_applied=True),
        "block",
    )
    assert "state_projection_missing" in finding_codes(task_only_trigger)

    nested_trigger = result_contract.validate(
        "validate",
        current_validate_packet(
            lifecycle_transition_result={"task_projection_applied": True},
        ),
        "block",
    )
    assert "state_projection_missing" in finding_codes(nested_trigger)


def advice_decision_echo() -> dict[str, Any]:
    return {
        "artifact_id": "artifact_A",
        "artifact_class": "family_F",
        "artifact_sha256": "a" * 64,
        "production_lane_identity": "lane_L",
        "body_projection_fingerprint": "b" * 64,
        "verification_input_ids": ["cohort_C"],
        "discovery_basis": "explicit_artifact_ref",
        "scope_verified": True,
    }


def _forward_path_receipt(row: dict[str, Any], path_kind: str) -> dict[str, Any]:
    happy = path_kind == "happy"
    receipt: dict[str, Any] = {
        "path_kind": path_kind,
        "clause_id": row["clause_id"],
        "scenario_id": row["scenario_id"],
        "precondition_ids": row["precondition_ids"],
        "injected_fault_class": None if happy else row["injected_fault_class"],
        "expected_decision_state": row[
            "happy_expected_decision_state" if happy else "expected_decision_state"
        ],
        "observed_decision_state": row[
            "happy_observed_decision_state" if happy else "observed_decision_state"
        ],
        "decision_identity_echo": advice_decision_echo(),
        "invocation_completed": True,
        "return_contract_valid": True,
        "decision_path_consumed": True,
        "evidence_provenance": "independently_verified",
        "receipt_ref": f"{path_kind}-packet.json",
    }
    receipt["receipt_sha256"] = (
        result_contract.advice_forward_path_receipt_binding_sha256(row, receipt)
    )
    return receipt


def forward_row(**overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "clause_id": "clause_Q",
        "scenario_id": "input_D",
        "precondition_ids": ["artifact_A"],
        "injected_fault_class": "gate_G",
        "contract_test_status": "pass",
        "consumer_test_status": "pass",
        "forward_scenario_status": "pass",
        "expected_decision_state": "blocked",
        "observed_decision_state": "blocked",
        "happy_expected_decision_state": "allowed",
        "happy_observed_decision_state": "allowed",
        "regression_status": "pass",
    }
    row.update(overrides)
    if "happy_path_receipt" not in overrides:
        row["happy_path_receipt"] = _forward_path_receipt(row, "happy")
    if "negative_path_receipt" not in overrides:
        row["negative_path_receipt"] = _forward_path_receipt(row, "negative")
    return row


def consumption_row(state: str) -> dict[str, Any]:
    row: dict[str, Any] = {
        "clause_id": "clause_Q",
        "state": state,
        "consumer_context_id": "consumer_C",
        "invocation_completed": True,
        "return_contract_valid": True,
        "decision_path_consumed": True,
        "decision_identity_echo": advice_decision_echo(),
        "evidence_provenance": "independently_verified",
        "consumer_receipt_ref": "packet_K",
    }
    row["consumer_receipt_sha256"] = (
        result_contract.advice_consumer_receipt_binding_sha256(row)
    )
    return row


def expected_advice_packet(
    clause_ids: list[str],
    *,
    applicability: str = "applicable",
    packet_digest: str = "b" * 64,
    source_digest: str = "c" * 64,
) -> dict[str, Any]:
    return {
        "applicability": applicability,
        "canonical_actionable_clause_ids": clause_ids,
        "advice_packet_digest": packet_digest,
        "clause_source_digests": {clause_id: source_digest for clause_id in clause_ids},
    }


def content_bound_expected_advice_packet(clause_ids: list[str]) -> dict[str, Any]:
    source_digest = "c" * 64
    binding = {
        "advice_packet_schema_version": 1,
        "applicability": "applicable",
        "active_items": [
            {
                "advice_id": "adv-A",
                "source_digest": source_digest,
                "normalized_content_digest": "d" * 64,
                "canonical_clause_ids": clause_ids,
                "actionable_clause_ids": clause_ids,
            }
        ],
    }
    encoded = json.dumps(
        binding, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    packet = expected_advice_packet(clause_ids)
    packet.update(
        {
            "source_digests": {"adv-A": source_digest},
            "duplicate_actionable_clause_ids": [],
            "advice_packet_digest_basis": binding,
            "advice_packet_digest": hashlib.sha256(encoded.encode("utf-8")).hexdigest(),
        }
    )
    return packet


def packet_bound_consumption_row(
    clause_id: str,
    state: str = "wired",
    *,
    packet_digest: str = "b" * 64,
    source_digest: str = "c" * 64,
) -> dict[str, Any]:
    row = consumption_row(state)
    row["clause_id"] = clause_id
    row["advice_packet_digest"] = packet_digest
    row["advice_source_digest"] = source_digest
    row["consumer_receipt_sha256"] = (
        result_contract.advice_consumer_receipt_binding_sha256(row)
    )
    return row


def test_advice_consumption_and_forward_receipt_prevent_wired_verified_overclaim() -> (
    None
):
    declared_only = current_validate_packet(
        advice_consumption_states=[
            {**consumption_row("wired"), "hook_declared_only": True}
        ]
    )
    assert "advice_clause_wired_without_consumer_receipt" in finding_codes(
        result_contract.validate("validate", declared_only, "block")
    )

    self_attested = consumption_row("wired")
    self_attested.pop("invocation_completed")
    self_attested.pop("decision_identity_echo")
    assert "advice_clause_wired_without_consumer_receipt" in finding_codes(
        result_contract.validate(
            "validate",
            current_validate_packet(advice_consumption_states=[self_attested]),
            "block",
        )
    )

    deferred = current_validate_packet(
        advice_consumption_states=[consumption_row("verified")],
        skill_forward_test=[
            forward_row(
                runtime_forward_verification="deferred_by_explicit_single_skill_constraint"
            )
        ],
    )
    assert "skill_forward_test_verified_without_full_receipt" in finding_codes(
        result_contract.validate("validate", deferred, "block")
    )

    happy = current_validate_packet(
        advice_consumption_states=[consumption_row("verified")],
        skill_forward_test=[forward_row()],
    )
    happy_codes = finding_codes(result_contract.validate("validate", happy, "block"))
    assert "advice_clause_wired_without_consumer_receipt" in happy_codes
    assert "advice_clause_verified_without_forward_test" not in happy_codes
    assert "skill_forward_test_verified_without_full_receipt" in happy_codes

    incomplete = current_validate_packet(
        advice_consumption_states=[consumption_row("verified")],
        skill_forward_test=[
            forward_row(
                precondition_ids=[],
                injected_fault_class="",
                expected_decision_state=None,
                observed_decision_state=None,
            )
        ],
    )
    incomplete_result = result_contract.validate("validate", incomplete, "block")
    assert "skill_forward_test_malformed" in finding_codes(incomplete_result)
    assert incomplete_result["status"] == "block"

    unrelated_malformed = current_validate_packet(
        advice_consumption_states=[consumption_row("pending")],
        skill_forward_test=[forward_row(clause_id="clause_X", precondition_ids=[])],
    )
    unrelated_result = result_contract.validate(
        "validate", unrelated_malformed, "block"
    )
    malformed_rows = [
        finding
        for finding in unrelated_result["findings"]
        if finding.get("code") == "skill_forward_test_malformed"
    ]
    assert malformed_rows and malformed_rows[0]["severity"] == "warn"

    malformed_consumption = consumption_row("wired")
    malformed_consumption["consumer_context_id"] = {"raw": "consumer_C"}
    malformed_consumption["consumer_receipt_ref"] = {"raw": "packet_K"}
    assert "advice_clause_wired_without_consumer_receipt" in finding_codes(
        result_contract.validate(
            "validate",
            current_validate_packet(advice_consumption_states=[malformed_consumption]),
            "block",
        )
    )

    malformed_forward = forward_row(
        precondition_ids=[{"raw": "artifact_A"}],
        injected_fault_class={"raw": "gate_G"},
        expected_decision_state={"raw": "blocked"},
        observed_decision_state={"raw": "blocked"},
    )
    assert "skill_forward_test_malformed" in finding_codes(
        result_contract.validate(
            "validate",
            current_validate_packet(skill_forward_test=[malformed_forward]),
            "block",
        )
    )

    for malformed_positive in ("verified", ["wired"]):
        malformed_positive_result = result_contract.validate(
            "validate",
            current_validate_packet(advice_consumption_states=malformed_positive),
            "block",
        )
        malformed_positive_findings = [
            row
            for row in malformed_positive_result["findings"]
            if row.get("code") == "advice_consumption_state_unverified"
        ]
        assert malformed_positive_findings
        assert malformed_positive_findings[0]["severity"] == "block"
        assert "verified" not in repr(malformed_positive_findings[0].get("evidence"))

    absent_state = result_contract.validate(
        "validate", current_validate_packet(), "block"
    )
    assert "advice_consumption_state_unverified" not in finding_codes(absent_state)
    assert "advice_consumption_rows_missing" not in finding_codes(absent_state)


def test_expected_advice_packet_requires_exact_packet_bound_consumption_rows() -> None:
    packet = expected_advice_packet(["clause_Q", "clause_R"])
    absent = result_contract.validate(
        "validate",
        current_validate_packet(),
        "block",
        {"active_advice_packet": packet},
    )
    assert "advice_consumption_rows_missing" in finding_codes(absent)
    assert "advice_consumption_clause_missing" in finding_codes(absent)
    assert absent["status"] == "block"

    malformed_rows = [
        packet_bound_consumption_row("clause_Q", "pending"),
        packet_bound_consumption_row("clause_Q", "pending"),
        packet_bound_consumption_row("clause_X", "pending", packet_digest="d" * 64),
    ]
    incomplete = result_contract.validate(
        "validate",
        current_validate_packet(advice_consumption_states=malformed_rows),
        "block",
        {"active_advice_packet": packet},
    )
    incomplete_codes = finding_codes(incomplete)
    assert "advice_consumption_clause_missing" in incomplete_codes
    assert "advice_consumption_clause_duplicate" in incomplete_codes
    assert "advice_consumption_external_clause" in incomplete_codes

    digest_mismatch = packet_bound_consumption_row(
        "clause_Q", "pending", packet_digest="d" * 64
    )
    digest_result = result_contract.validate(
        "validate",
        current_validate_packet(
            advice_consumption_states=[
                digest_mismatch,
                packet_bound_consumption_row("clause_R", "pending"),
            ]
        ),
        "block",
        {"active_advice_packet": packet},
    )
    assert "advice_consumption_packet_digest_mismatch" in finding_codes(digest_result)


def test_expected_advice_completeness_is_pending_debt_until_positive_use() -> None:
    packet = expected_advice_packet(["clause_Q"])
    base = {
        "step": "governance",
        "task_id": "task_T",
        "changed_files": [],
        "task_miss": False,
        "implementation_summary": "No advice-dependent implementation.",
        "validation_profile": "deterministic",
        "blockers": [],
        "agent_routing_applicability": "deterministic_only",
    }
    neutral = result_contract.validate(
        "governance",
        base,
        "warn",
        {"active_advice_packet": packet},
    )
    neutral_rows = [
        row
        for row in neutral["findings"]
        if row.get("code") == "advice_consumption_rows_missing"
    ]
    assert neutral_rows and neutral_rows[0]["severity"] == "warn"

    positive = result_contract.validate(
        "governance",
        {
            **base,
            "implementation_summary": "Advice-dependent implementation claimed.",
            "used_advice": ["adv-A"],
        },
        "warn",
        {"active_advice_packet": packet},
    )
    positive_rows = [
        row
        for row in positive["findings"]
        if row.get("code") == "advice_consumption_rows_missing"
    ]
    assert positive_rows and positive_rows[0]["severity"] == "block"
    assert positive["status"] == "block"


def test_expected_advice_packet_exact_rows_are_consumable_and_na_fails_quiet() -> None:
    packet = content_bound_expected_advice_packet(["clause_Q", "clause_R"])
    packet_digest = packet["advice_packet_digest"]
    happy = result_contract.validate(
        "validate",
        current_validate_packet(
            advice_consumption_states=[
                packet_bound_consumption_row(
                    "clause_Q", "pending", packet_digest=packet_digest
                ),
                packet_bound_consumption_row(
                    "clause_R", "pending", packet_digest=packet_digest
                ),
            ]
        ),
        "block",
        {"active_advice_packet": packet},
    )
    happy_codes = finding_codes(happy)
    assert "advice_consumption_rows_missing" not in happy_codes
    assert "advice_consumption_clause_missing" not in happy_codes
    assert "advice_consumption_clause_duplicate" not in happy_codes
    assert "advice_consumption_external_clause" not in happy_codes
    assert "advice_consumption_packet_digest_mismatch" not in happy_codes
    assert "advice_consumption_source_digest_mismatch" not in happy_codes
    assert "advice_clause_wired_without_consumer_receipt" not in happy_codes

    tampered_packet = copy.deepcopy(packet)
    tampered_packet["source_digests"]["adv-A"] = "e" * 64
    tampered = result_contract.validate(
        "validate",
        current_validate_packet(
            advice_consumption_states=[
                packet_bound_consumption_row(
                    "clause_Q", "pending", packet_digest=packet_digest
                ),
                packet_bound_consumption_row(
                    "clause_R", "pending", packet_digest=packet_digest
                ),
            ]
        ),
        "block",
        {"active_advice_packet": tampered_packet},
    )
    assert "active_advice_packet_source_digest_mismatch" in finding_codes(tampered)

    alias_conflict_packet = copy.deepcopy(packet)
    alias_conflict_packet["actionable_clause_ids"] = ["clause_Q"]
    alias_conflict = result_contract.validate(
        "validate",
        current_validate_packet(
            advice_consumption_states=[
                packet_bound_consumption_row(
                    "clause_Q", "pending", packet_digest=packet_digest
                ),
                packet_bound_consumption_row(
                    "clause_R", "pending", packet_digest=packet_digest
                ),
            ]
        ),
        "block",
        {"active_advice_packet": alias_conflict_packet},
    )
    assert "active_advice_packet_clause_set_alias_conflict" in finding_codes(
        alias_conflict
    )

    false_na_packet = copy.deepcopy(packet)
    false_na_packet["applicability"] = "not_applicable"
    false_na = result_contract.validate(
        "validate",
        current_validate_packet(),
        "block",
        {"active_advice_packet": false_na_packet},
    )
    assert "active_advice_packet_applicability_mismatch" in finding_codes(false_na)

    not_applicable = result_contract.validate(
        "validate",
        current_validate_packet(),
        "block",
        {
            "active_advice_packet": expected_advice_packet(
                ["clause_Q"], applicability="not_applicable"
            )
        },
    )
    assert "advice_consumption_rows_missing" not in finding_codes(not_applicable)


def test_advice_receipts_bind_content_identity_and_separate_happy_negative_paths() -> (
    None
):
    tampered = consumption_row("wired")
    tampered["decision_path_consumed"] = False
    tampered_codes = finding_codes(
        result_contract.validate(
            "validate",
            current_validate_packet(advice_consumption_states=[tampered]),
            "block",
        )
    )
    assert "advice_clause_wired_without_consumer_receipt" in tampered_codes

    wrong_identity = consumption_row("wired")
    wrong_identity["decision_identity_echo"] = {
        **advice_decision_echo(),
        "artifact_id": "artifact_B",
    }
    wrong_identity["consumer_receipt_sha256"] = (
        result_contract.advice_consumer_receipt_binding_sha256(wrong_identity)
    )
    wrong_codes = finding_codes(
        result_contract.validate(
            "validate",
            current_validate_packet(advice_consumption_states=[wrong_identity]),
            "block",
        )
    )
    assert "advice_clause_wired_without_consumer_receipt" in wrong_codes

    shared = forward_row()
    shared["negative_path_receipt"] = copy.deepcopy(shared["happy_path_receipt"])
    shared_codes = finding_codes(
        result_contract.validate(
            "validate",
            current_validate_packet(
                advice_consumption_states=[consumption_row("verified")],
                skill_forward_test=[shared],
            ),
            "block",
        )
    )
    assert "skill_forward_test_verified_without_full_receipt" in shared_codes


def test_unconsumed_advice_regression_requires_finalized_recurrence_clause_state() -> (
    None
):
    absent = result_contract.validate(
        "validate",
        current_validate_packet(
            advice_consumption_states=[consumption_row("pending")],
        ),
        "block",
    )
    assert "unconsumed_advice_regression" not in finding_codes(absent)

    finalized = result_contract.validate(
        "validate",
        current_validate_packet(
            advice_consumption_states=[consumption_row("pending")],
            finalized_advice_clause_states={
                "rows": [
                    {
                        "clause_id": "clause_Q",
                        "recurrence_id": "recurrence_R",
                        "finalized_clause_state": "wired",
                        "recurrence_observed": True,
                    }
                ]
            },
        ),
        "block",
    )
    regression_rows = [
        row
        for row in finalized["findings"]
        if row.get("code") == "unconsumed_advice_regression"
    ]
    assert regression_rows and regression_rows[0]["severity"] == "warn"

    verified = result_contract.validate(
        "validate",
        current_validate_packet(
            advice_consumption_states=[consumption_row("verified")],
            skill_forward_test=[forward_row()],
            finalized_advice_clause_states={
                "rows": [
                    {
                        "clause_id": "clause_Q",
                        "recurrence_id": "recurrence_R",
                        "finalized_clause_state": "wired",
                        "recurrence_observed": True,
                    }
                ]
            },
        ),
        "block",
    )
    verified_codes = finding_codes(verified)
    assert "advice_clause_wired_without_consumer_receipt" in verified_codes
    assert "unconsumed_advice_regression" in verified_codes


def test_producer_starved_gating_axis_routes_supply_before_another_verifier() -> None:
    base = {
        "step": "derive",
        "task_id": "task_T",
        "next_task_id": "item_I",
        "status": "complete",
        "axis_starved_by_missing_producer": True,
        "blockers": [],
        "evidence_paths": ["packet_K.json"],
        "agent_routing_applicability": "deterministic_only",
    }
    verifier = result_contract.validate(
        "derive",
        {**base, "selected_task_kind": "report_repair"},
        "block",
    )
    assert "derive_axis_starved_by_missing_producer_unhandled" in finding_codes(
        verifier
    )

    producer = result_contract.validate(
        "derive",
        {**base, "selected_task_kind": "producer_supply"},
        "block",
    )
    assert "derive_axis_starved_by_missing_producer_unhandled" not in finding_codes(
        producer
    )

    unknown_scope = result_contract.validate(
        "derive",
        {
            **base,
            "axis_starved_by_missing_producer": False,
            "execution_starvation_status": "scope_unknown",
            "scope_evidence_required": ["goal_axis"],
            "selected_task_kind": "report_repair",
        },
        "block",
    )
    assert "derive_execution_scope_unknown_unrecovered" in finding_codes(unknown_scope)

    scope_recovery = result_contract.validate(
        "derive",
        {
            **base,
            "axis_starved_by_missing_producer": False,
            "execution_starvation_status": "scope_unknown",
            "scope_evidence_required": ["goal_axis"],
            "selected_task_kind": "instrumentation_supply",
        },
        "block",
    )
    assert "derive_execution_scope_unknown_unrecovered" not in finding_codes(
        scope_recovery
    )

    starvation_report = result_contract.validate(
        "derive",
        {
            **base,
            "axis_starved_by_missing_producer": False,
            "selection_outcome": "selected",
            "selected_task_source": "standalone",
            "execution_starvation_status": "present",
            "execution_scope_status": "evaluated",
            "selected_task_kind": "report_repair",
        },
        "block",
    )
    assert "derive_execution_starvation_unhandled" in finding_codes(starvation_report)

    for allowed_kind in (
        "fresh_producer_execution",
        "instrumentation_exercise",
        "producer_input_reconciliation",
        "producer_authority_reconciliation",
        "producer_supply",
        "residual_descope",
    ):
        allowed = result_contract.validate(
            "derive",
            {
                **base,
                "axis_starved_by_missing_producer": False,
                "selection_outcome": "selected",
                "selected_task_source": "standalone",
                "execution_starvation_status": "present",
                "execution_scope_status": "evaluated",
                "selected_task_kind": allowed_kind,
            },
            "block",
        )
        assert "derive_execution_starvation_unhandled" not in finding_codes(allowed)

    terminal_wait_does_not_clear_starvation = result_contract.validate(
        "derive",
        {
            **base,
            "axis_starved_by_missing_producer": False,
            "selection_outcome": "terminal_wait",
            "selected_task_source": "terminal_wait",
            "execution_starvation_status": "present",
            "execution_scope_status": "evaluated",
        },
        "block",
    )
    assert "derive_execution_starvation_unhandled" in finding_codes(
        terminal_wait_does_not_clear_starvation
    )

    genuine_escalation = result_contract.validate(
        "derive",
        {
            **base,
            "next_task_id": None,
            "axis_starved_by_missing_producer": False,
            "selection_outcome": "user_escalation",
            "selected_task_source": "user_escalation",
            "pack_disposition": "user_escalation",
            "selected_disposition": "user_escalation",
            "terminal_justified": False,
            "hard_stop_required": False,
            "execution_starvation_status": "present",
            "execution_scope_status": "evaluated",
            "user_escalation": {
                "reason_code": "execution_authority_missing",
                "requested_input_or_authority": "grant_execution_authority",
                "evidence_ids": ["authority_evidence_A"],
            },
        },
        "block",
    )
    assert "derive_execution_starvation_unhandled" not in finding_codes(
        genuine_escalation
    )

    excluded_scope = result_contract.validate(
        "derive",
        {
            **base,
            "axis_starved_by_missing_producer": False,
            "selection_outcome": "selected",
            "selected_task_source": "standalone",
            "execution_scope_applicability": "excluded_by_task",
            "execution_scope_status": "excluded_by_task",
            "execution_scope_exclusion_reason_id": "task_excludes_required_producer",
            "execution_starvation_status": "present",
            "selected_task_kind": "producer_supply",
        },
        "block",
    )
    excluded_codes = finding_codes(excluded_scope)
    assert "derive_execution_scope_exclusion_conflict" not in excluded_codes
    assert "derive_execution_starvation_unhandled" not in excluded_codes

    excluded_report = result_contract.validate(
        "derive",
        {
            **base,
            "axis_starved_by_missing_producer": False,
            "selection_outcome": "selected",
            "selected_task_source": "standalone",
            "execution_scope_applicability": "excluded_by_task",
            "execution_scope_status": "excluded_by_task",
            "execution_scope_exclusion_reason_id": "task_excludes_required_producer",
            "execution_starvation_status": "present",
            "selected_task_kind": "report_repair",
        },
        "block",
    )
    assert "derive_execution_starvation_unhandled" in finding_codes(excluded_report)

    intrinsic_not_applicable = result_contract.validate(
        "derive",
        {
            **base,
            "axis_starved_by_missing_producer": False,
            "selection_outcome": "selected",
            "selected_task_source": "standalone",
            "execution_scope_applicability": "not_applicable",
            "execution_scope_status": "not_applicable",
            "execution_scope_exclusion_reason_id": "governance_has_no_producer",
            "execution_starvation_status": "not_applicable",
            "selected_task_kind": "report_repair",
        },
        "block",
    )
    intrinsic_codes = finding_codes(intrinsic_not_applicable)
    assert "derive_execution_scope_exclusion_conflict" not in intrinsic_codes
    assert "derive_execution_starvation_unhandled" not in intrinsic_codes

    malformed_scope_status = result_contract.validate(
        "derive",
        {
            **base,
            "axis_starved_by_missing_producer": False,
            "execution_starvation_status": {"raw": "source_span_X"},
            "selected_task_kind": "report_repair",
        },
        "block",
    )
    malformed_scope_codes = finding_codes(malformed_scope_status)
    assert "derive_execution_starvation_status_malformed" in malformed_scope_codes
    assert "derive_execution_scope_unknown_unrecovered" in malformed_scope_codes
    assert "source_span_X" not in repr(malformed_scope_status)

    terminal_scope_unknown = result_contract.validate(
        "derive",
        {
            **base,
            "axis_starved_by_missing_producer": False,
            "execution_starvation_status": "scope_unknown",
            "selected_task_kind": "instrumentation_supply",
            "selected_task_source": "terminal_blocked",
        },
        "block",
    )
    assert "derive_execution_scope_unknown_unrecovered" in finding_codes(
        terminal_scope_unknown
    )

    stagnant_projection = {
        "status": "evaluated",
        "goal_axis": "goal_axis_G",
        "family_ids": ["family_F", "family_G"],
        "cycle_count": 2,
        "semantic_movement_cycle_count": 0,
        "producer_run_cycle_count": 0,
        "no_semantic_movement_streak": 2,
        "family_change_resets_streak": False,
    }
    family_change_only = result_contract.validate(
        "derive",
        {
            **base,
            "axis_starved_by_missing_producer": False,
            "selected_task_kind": "producer_supply",
            "goal_axis_stagnation_projection": stagnant_projection,
        },
        "block",
    )
    assert "derive_goal_axis_stagnation_unjustified_reset" not in finding_codes(
        family_change_only
    )

    false_reset = result_contract.validate(
        "derive",
        {
            **base,
            "axis_starved_by_missing_producer": False,
            "selected_task_kind": "producer_supply",
            "goal_axis_stagnation_projection": stagnant_projection,
            "semantic_progress": True,
        },
        "block",
    )
    assert "derive_goal_axis_stagnation_unjustified_reset" in finding_codes(false_reset)

    verified_projection = {
        **stagnant_projection,
        "semantic_movement_cycle_count": 1,
        "producer_run_cycle_count": 1,
        "no_semantic_movement_streak": 0,
    }
    verified_movement = result_contract.validate(
        "derive",
        {
            **base,
            "axis_starved_by_missing_producer": False,
            "selected_task_kind": "producer_supply",
            "goal_axis_stagnation_projection": verified_projection,
            "semantic_progress": True,
        },
        "block",
    )
    assert "derive_goal_axis_stagnation_unjustified_reset" not in finding_codes(
        verified_movement
    )

    duplicate_scope_conflict = result_contract.validate(
        "derive",
        {
            **base,
            "axis_starved_by_missing_producer": False,
            "execution_starvation_status": "absent",
            "cycle_efficiency_profile": {
                "execution_starvation_status": "scope_unknown",
                "scope_evidence_required": ["goal_axis"],
            },
            "selected_task_kind": "report_repair",
        },
        "block",
    )
    assert "derive_execution_starvation_status_conflict" in finding_codes(
        duplicate_scope_conflict
    )
    assert "derive_execution_scope_unknown_unrecovered" in finding_codes(
        duplicate_scope_conflict
    )

    scope_status_only = result_contract.validate(
        "derive",
        {
            **base,
            "axis_starved_by_missing_producer": False,
            "execution_scope_status": "scope_unknown",
            "scope_evidence_required": ["goal_axis"],
            "selected_task_kind": "report_repair",
        },
        "block",
    )
    assert "derive_execution_scope_unknown_unrecovered" in finding_codes(
        scope_status_only
    )

    recovery_without_evidence = result_contract.validate(
        "derive",
        {
            **base,
            "axis_starved_by_missing_producer": False,
            "execution_starvation_status": "scope_unknown",
            "selected_task_kind": "instrumentation_supply",
        },
        "block",
    )
    assert "derive_execution_scope_evidence_missing" in finding_codes(
        recovery_without_evidence
    )

    duplicate_projection_conflict = result_contract.validate(
        "derive",
        {
            **base,
            "axis_starved_by_missing_producer": False,
            "selected_task_kind": "producer_supply",
            "semantic_progress": True,
            "goal_axis_stagnation_projection": verified_projection,
            "cycle_efficiency_profile": {
                "goal_axis_stagnation_projection": stagnant_projection,
            },
        },
        "block",
    )
    assert "derive_goal_axis_stagnation_projection_conflict" in finding_codes(
        duplicate_projection_conflict
    )
