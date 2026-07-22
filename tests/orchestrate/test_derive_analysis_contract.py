from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from orchestrate_task_cycle.result_contract import api as result_contract
from orchestrate_task_cycle.result_contract import configuration
from orchestrate_task_cycle.prerequisite_chain_contract import receipt_sha256
from orchestrate_task_cycle.selection_decision_receipt import (
    render_preliminary_selection_decision,
    render_selection_decision_receipt,
)
from orchestrate_task_cycle.selection_tick import build_selection_tick
from orchestrate_task_cycle.selection_tick_premise import VERIFIED_PREMISE_CONTRACT
from orchestrate_task_cycle.selection_synthesis import render_selection_synthesis


def digest(value: object) -> str:
    body = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    return hashlib.sha256(body).hexdigest()


def canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def runtime_ref(filename: str) -> str:
    return f".task/cycle/cycle-A/agent_receipts/{filename}"


def write_runtime_artifact(root: Path, ref: str, value: object) -> None:
    path = root / ref
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_bytes(value))


def tick_packet_id(value: dict[str, Any]) -> str:
    body = (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    )
    return "selection-tick-" + hashlib.sha256(body.encode()).hexdigest()[:32]


def codes(value: dict[str, Any]) -> set[str]:
    return {str(row.get("code")) for row in value.get("findings", [])}


def candidate(*, issue_derived: bool = False) -> dict[str, Any]:
    return {
        "candidate_id": "candidate-A",
        "exact_subject_fingerprint": "subject-A",
        "first_failing_invariant": "invariant-A",
        "canonical_owner": "owner-A",
        "task_kind": "producer_repair",
        "expected_blocker_transition": "blocked-to-measured",
        "actionability": "actionable",
        "pack_disposition": "derive_standalone",
        "issue_derived": issue_derived,
        "evidence_ids": ["evidence-A"],
        "validation_ids": ["validation-A"],
    }


def lens(role: str, index: int, candidates: list[dict[str, Any]]) -> dict[str, Any]:
    output = {
        "candidates": candidates,
        "rejection_inventory": []
        if candidates
        else [
            {
                "option_id": f"option-{index}",
                "reason_code": "lower-value",
                "evidence_ids": [f"evidence-{index}"],
            }
        ],
        "advice_clause_set_sha256": "",
        "advice_clause_assessments": [],
    }
    return {
        "role_id": role,
        "agent_id": f"agent-{index}",
        "agent_receipt_id": f"agent-receipt-{index}",
        "read_only": True,
        "status": "complete",
        "input_evidence_manifest_sha256": "",
        "output_ref": f"lens-{index}.json",
        "output_sha256": digest(output),
        "output": output,
    }


def valid_packet() -> dict[str, Any]:
    identity = {
        "cycle_id": "cycle-A",
        "task_id": "task-old",
        "attempt_id": "attempt-A",
        "artifact_id": "artifact-A",
        "artifact_sha256": "a" * 64,
        "body_projection_fingerprint": "b" * 64,
        "production_lane_identity": "lane-A",
        "input_state_fingerprint": "c" * 64,
    }
    seal = {
        "schema_version": 1,
        "consumer_id": "derive-improvement-task",
        **identity,
        "adapter_revision_sha256": "e" * 64,
        "hook_results_sha256": "f" * 64,
        "value_consumed_by_decision": True,
        "decision_id": "derive-decision-A",
    }
    seal["receipt_sha256"] = digest(seal)
    adapter_packet = {
        "phase": "derive",
        "required_consumer_ids": ["derive-improvement-task"],
        "static_validation": {"status": "pass"},
        "load_preflight": {"status": "pass"},
        "candidate_projection": {"status": "eligible", "eligible": True},
        "adapter_revision": {"adapter_revision_sha256": "e" * 64},
        "hook_results_sha256": "f" * 64,
        "decision_identity": identity,
        "post_use_decision_receipt": {
            "status": "pass",
            "receipt_sha256": seal["receipt_sha256"],
        },
    }
    context = {
        "packet_ref": "adapter-context.json",
        "packet_sha256": digest(adapter_packet),
        "packet": adapter_packet,
    }
    evidence = {
        **identity,
        "issue_fit": {"status": "available", "evidence_ids": ["issue-fit-A"]},
        "adapter_applicability": "required",
        "adapter_decision_context": context,
        "adapter_post_use_seal": seal,
        "evidence_refs": [
            {"evidence_id": "source-A", "ref": "source.json", "sha256": "1" * 64}
        ],
    }
    active_advice = {
        "contract_version": 1,
        "applicability": "not_applicable",
        "advice_packet_digest": None,
        "actionable_clause_ids": [],
        "clause_source_digests": {},
        "not_applicable_reason_id": "no-active-advice",
        "evidence_ids": ["advice-scan-A"],
    }
    active_advice["clause_set_sha256"] = result_contract.advice_clause_set_sha256(
        active_advice
    )
    evidence["active_advice_clause_set"] = active_advice
    evidence_sha = digest(evidence)
    lenses = [
        lens("goal_value", 1, [candidate()]),
        lens("architecture_contract", 2, []),
        lens("miss_validation", 3, []),
    ]
    for row in lenses:
        row["input_evidence_manifest_sha256"] = evidence_sha
        row["output"]["advice_clause_set_sha256"] = active_advice["clause_set_sha256"]
        row["output_sha256"] = digest(row["output"])
    synthesis = {
        "synthesis_agent_id": "agent-synthesis",
        "synthesis_receipt_id": "synthesis-A",
        "input_evidence_manifest_sha256": evidence_sha,
        "consumed_agent_receipt_ids": [row["agent_receipt_id"] for row in lenses],
        "candidate_union_ids": ["candidate-A"],
        "candidate_union_sha256": digest(["candidate-A"]),
        "selected_candidate_id": "candidate-A",
        "selection_outcome": "selected",
        "pack_disposition": "derive_standalone",
        "advice_clause_set_sha256": active_advice["clause_set_sha256"],
        "advice_clause_reconciliation": [],
        "advice_reconciliation_sha256": result_contract.advice_reconciliation_set_sha256(
            []
        ),
        "synthesis_output_ref": "synthesis-A.json",
    }
    synthesis["synthesis_output_sha256"] = (
        result_contract.advice_synthesis_output_sha256(synthesis)
    )
    return {
        "step": "derive",
        "derive_contract_version": 2,
        "completed_task_id": "task-old",
        "next_task_id": "task-new",
        "selected_task_source": "standalone",
        "selected_candidate_id": "candidate-A",
        "selection_outcome": "selected",
        "pack_disposition": "derive_standalone",
        "loop_breaker_disposition": "continue",
        "progress_kind": "goal_productive",
        "semantic_signature": "producer-repair-A",
        "terminal_justified": False,
        "hard_stop_required": False,
        "evidence_paths": ["derive.json"],
        "improvement_analysis_manifest": {
            "schema_version": 1,
            "shared_evidence_manifest": evidence,
            "shared_evidence_manifest_sha256": evidence_sha,
            "lens_results": lenses,
            "synthesis": synthesis,
        },
    }


def rehash(packet: dict[str, Any]) -> None:
    analysis = packet["improvement_analysis_manifest"]
    advice = analysis["shared_evidence_manifest"]["active_advice_clause_set"]
    advice["clause_set_sha256"] = result_contract.advice_clause_set_sha256(advice)
    shared_sha = digest(analysis["shared_evidence_manifest"])
    analysis["shared_evidence_manifest_sha256"] = shared_sha
    for row in analysis["lens_results"]:
        row["input_evidence_manifest_sha256"] = shared_sha
        row["output"]["advice_clause_set_sha256"] = advice["clause_set_sha256"]
        for assessment in row["output"].get("advice_clause_assessments", []):
            assessment["assessment_sha256"] = result_contract.advice_assessment_sha256(
                assessment
            )
        row["output_sha256"] = digest(row["output"])
    synthesis = analysis["synthesis"]
    synthesis["input_evidence_manifest_sha256"] = shared_sha
    ids = sorted(
        candidate_row["candidate_id"]
        for row in analysis["lens_results"]
        for candidate_row in row["output"]["candidates"]
    )
    synthesis["candidate_union_ids"] = ids
    synthesis["candidate_union_sha256"] = digest(ids)
    synthesis["advice_clause_set_sha256"] = advice["clause_set_sha256"]
    assessment_hashes = {
        clause_id: sorted(
            assessment["assessment_sha256"]
            for lens_row in analysis["lens_results"]
            for assessment in lens_row["output"].get("advice_clause_assessments", [])
            if assessment.get("clause_id") == clause_id
        )
        for clause_id in advice["actionable_clause_ids"]
    }
    for reconciliation in synthesis.get("advice_clause_reconciliation", []):
        reconciliation["consumed_lens_assessment_sha256s"] = assessment_hashes[
            reconciliation["clause_id"]
        ]
        reconciliation["reconciliation_sha256"] = (
            result_contract.advice_reconciliation_row_sha256(reconciliation)
        )
    synthesis["advice_reconciliation_sha256"] = (
        result_contract.advice_reconciliation_set_sha256(
            synthesis.get("advice_clause_reconciliation", [])
        )
    )
    synthesis["synthesis_output_sha256"] = (
        result_contract.advice_synthesis_output_sha256(synthesis)
    )


def write_advice_runtime_artifacts(packet: dict[str, Any], root: Path) -> None:
    analysis = packet["improvement_analysis_manifest"]
    for lens_row in analysis["lens_results"]:
        write_runtime_artifact(
            root,
            lens_row["output_ref"],
            result_contract.advice_lens_receipt_projection(lens_row),
        )
    synthesis = analysis["synthesis"]
    write_runtime_artifact(
        root,
        synthesis["synthesis_output_ref"],
        result_contract.advice_synthesis_output_projection(synthesis),
    )


def activate_advice(packet: dict[str, Any], root: Path) -> None:
    analysis = packet["improvement_analysis_manifest"]
    evidence = analysis["shared_evidence_manifest"]
    evidence["active_advice_clause_set"] = {
        "contract_version": 1,
        "applicability": "applicable",
        "advice_packet_digest": "7" * 64,
        "actionable_clause_ids": ["clause-Q"],
        "clause_source_digests": {"clause-Q": "8" * 64},
        "clause_set_sha256": "pending",
    }
    for index, lens_row in enumerate(analysis["lens_results"], start=1):
        lens_row["output_ref"] = runtime_ref(f"lens-{index}.json")
        candidate_ids = [
            row["candidate_id"] for row in lens_row["output"]["candidates"]
        ]
        lens_row["output"]["advice_clause_assessments"] = [
            {
                "contract_version": 1,
                "clause_id": "clause-Q",
                "lens_agent_id": lens_row["agent_id"],
                "lens_receipt_id": lens_row["agent_receipt_id"],
                "disposition": "incorporated" if index == 1 else "deferred",
                "evidence_ids": [f"advice-lens-{index}-E"],
                "candidate_ids": candidate_ids,
                "assessment_sha256": "pending",
            }
        ]
    analysis["synthesis"]["advice_clause_reconciliation"] = [
        {
            "contract_version": 1,
            "clause_id": "clause-Q",
            "final_disposition": "incorporated",
            "consumed_lens_assessment_sha256s": [],
            "evidence_ids": ["advice-synthesis-E"],
            "selected_candidate_ids": ["candidate-A"],
            "reconciliation_sha256": "pending",
        }
    ]
    analysis["synthesis"]["synthesis_output_ref"] = runtime_ref("synthesis-A.json")
    rehash(packet)
    write_advice_runtime_artifacts(packet, root)
    packet["advice_consumption_states"] = (
        result_contract.build_derive_advice_consumption_rows(
            packet, workspace_root=root
        )
    )


def forward_receipt(
    packet: dict[str, Any], row: dict[str, Any], path_kind: str, root: Path
) -> dict[str, Any]:
    happy = path_kind == "happy"
    expected_state = row[
        "happy_expected_decision_state" if happy else "expected_decision_state"
    ]
    fault = None if happy else row["injected_fault_class"]
    consumer_binding = packet["advice_consumption_states"][0]["derive_consumer_binding"]
    output = {
        "clause_id": row["clause_id"],
        "observed_decision_state": expected_state,
        "decision_path_consumed": True,
        "evidence_ids": [f"{path_kind}-decision-E"],
    }
    artifact = {
        "contract_version": 1,
        "producer_agent_id": f"{path_kind}-producer-agent",
        "producer_receipt_id": f"{path_kind}-producer-receipt",
        "producer_role": f"advice_forward_{path_kind}",
        "freshness_basis": "current_bound_inputs",
        "input_advice_clause_set_sha256": consumer_binding["advice_clause_set_sha256"],
        "input_synthesis_output_sha256": consumer_binding["synthesis_output_sha256"],
        "input_decision_identity_echo": result_contract.expected_advice_decision_identity_echo(
            packet
        ),
        "scenario_id": row["scenario_id"],
        "precondition_ids": row["precondition_ids"],
        "injected_fault_class": fault,
        "output_ref": runtime_ref(f"{path_kind}-agent-output.json"),
        "output": output,
        "output_sha256": result_contract.advice_forward_agent_output_sha256(output),
    }
    verification = {
        "contract_version": 1,
        "verifier_agent_id": f"{path_kind}-verifier-agent",
        "verifier_receipt_id": f"{path_kind}-verifier-receipt",
        "producer_agent_id": artifact["producer_agent_id"],
        "producer_receipt_id": artifact["producer_receipt_id"],
        "producer_output_sha256": artifact["output_sha256"],
        "invariant_owner_id": f"{path_kind}-invariant-owner",
        "expected_decision_state": expected_state,
        "observed_decision_state": expected_state,
        "invariant_ids": [f"{path_kind}-invariant"],
        "verification_input_ids": [f"{path_kind}-independent-input"],
        "evidence_ids": [f"{path_kind}-verification-E"],
        "status": "pass",
    }
    verification["receipt_sha256"] = (
        result_contract.advice_forward_verification_receipt_sha256(verification)
    )
    receipt = {
        "path_kind": path_kind,
        "clause_id": row["clause_id"],
        "scenario_id": row["scenario_id"],
        "precondition_ids": row["precondition_ids"],
        "injected_fault_class": fault,
        "expected_decision_state": expected_state,
        "observed_decision_state": expected_state,
        "decision_identity_echo": result_contract.expected_advice_decision_identity_echo(
            packet
        ),
        "producer_artifact": artifact,
        "independent_verification_receipt": verification,
        "receipt_ref": runtime_ref(f"{path_kind}-forward-receipt.json"),
    }
    receipt["receipt_sha256"] = (
        result_contract.advice_forward_path_receipt_binding_sha256(row, receipt)
    )
    write_runtime_artifact(root, artifact["output_ref"], output)
    write_runtime_artifact(root, receipt["receipt_ref"], receipt)
    return receipt


def attach_forward_test(packet: dict[str, Any], root: Path) -> None:
    packet["advice_consumption_states"] = (
        result_contract.build_derive_advice_consumption_rows(
            packet, state="verified", workspace_root=root
        )
    )
    row = {
        "clause_id": "clause-Q",
        "scenario_id": "advice-forward-scenario",
        "precondition_ids": ["current-derive-synthesis"],
        "injected_fault_class": "advice-clause-omitted",
        "contract_test_status": "pass",
        "consumer_test_status": "pass",
        "forward_scenario_status": "pass",
        "expected_decision_state": "blocked",
        "observed_decision_state": "blocked",
        "happy_expected_decision_state": "selected",
        "happy_observed_decision_state": "selected",
        "regression_status": "pass",
    }
    row["happy_path_receipt"] = forward_receipt(packet, row, "happy", root)
    row["negative_path_receipt"] = forward_receipt(packet, row, "negative", root)
    packet["skill_forward_test"] = [row]


def sync_forward_runtime_artifacts(packet: dict[str, Any], root: Path) -> None:
    row = packet["skill_forward_test"][0]
    for key in ("happy_path_receipt", "negative_path_receipt"):
        receipt = row[key]
        artifact = receipt["producer_artifact"]
        write_runtime_artifact(root, artifact["output_ref"], artifact["output"])
        write_runtime_artifact(root, receipt["receipt_ref"], receipt)


def set_outcome(packet: dict[str, Any], outcome: str) -> None:
    analysis = packet["improvement_analysis_manifest"]
    synthesis = analysis["synthesis"]
    packet["selection_outcome"] = outcome
    synthesis["selection_outcome"] = outcome
    if outcome == "selected":
        return
    packet.update(
        {
            "next_task_id": None,
            "selected_task_source": outcome,
            "selected_candidate_id": "",
            "pack_disposition": outcome,
            "terminal_disposition": outcome,
            "selected_disposition": outcome,
        }
    )
    synthesis.update({"selected_candidate_id": "", "pack_disposition": outcome})
    first_candidate = analysis["lens_results"][0]["output"]["candidates"][0]
    if outcome == "terminal_wait":
        first_candidate["actionability"] = "blocked_external"
        tick_baseline = {
            "format_version": 2,
            "artifact_kind": "selection_tick",
            "status": "baseline_recorded",
            "reason": "no_previous_manifest_and_no_exact_premise",
            "observed_input_manifest_sha256": hashlib.sha256(b"[]\n").hexdigest(),
            "previous_input_manifest_sha256": None,
            "watch_entries": [],
            "changed_watch_entries": [],
            "changed_evidence_classes": [],
            "material_changed_watch_entries": [],
            "wake_predicates": ["artifact-digest-changed"],
            "wake_evaluation_rule": "explicit-premise-or-bound-class-change-v1",
            "wake_predicate_ids_are_policy_labels": True,
            "watched_evidence_classes": ["exact_subject"],
            "minimum_material_delta": "new-exact-subject",
            "premise_input_contract": VERIFIED_PREMISE_CONTRACT,
            "satisfied_wake_predicates": [],
            "exact_premise_supplied": False,
            "fresh_exact_premise_detected": False,
            "carried_forward_watch_ids": [],
            "acknowledgement_requested_for_packet_id": None,
            "selection_acknowledgement_binding": None,
            "selection_acknowledgement_status": "not_requested",
            "acknowledged_selection_tick_id": None,
            "baseline_rebased": False,
            "authority_scope_ids": [],
            "selection_required": False,
            "agent_fanout_allowed": False,
            "full_cycle_allowed": False,
            "next_action": "preserve_terminal_wait",
            "pending_selection_publication_ids": [],
            "selection_publication_status": {
                "status": "clear",
                "pending_transaction_ids": [],
                "selection_journal_initialized": False,
                "selection_consumption_allowed": False,
                "selection_consumption_reason": "no_committed_selection",
                "current_head": {
                    "status": "not_initialized",
                    "head_transaction_id": None,
                    "head_count": 0,
                    "lineage_mode": "uninitialized",
                },
                "mutation_performed": False,
            },
            "mutation_performed": False,
            "not_goal_truth": True,
            "not_authority": True,
        }
        tick_baseline["packet_id"] = tick_packet_id(tick_baseline)
        packet.update(
            {
                "terminal_justified": False,
                "hard_stop_required": False,
                "terminal_wait": {
                    "selection_epoch": "epoch-A",
                    "analysis_evidence_manifest_sha256": "pending-rehash",
                    "observed_input_manifest_sha256": tick_baseline[
                        "observed_input_manifest_sha256"
                    ],
                    "selection_tick_baseline": tick_baseline,
                    "selection_tick_baseline_sha256": digest(tick_baseline),
                    "wake_predicates": ["artifact-digest-changed"],
                    "watched_evidence_classes": ["exact_subject"],
                    "minimum_material_delta": "new-exact-subject",
                    "last_selection_receipt": "selection-A",
                },
            }
        )
    elif outcome == "user_escalation":
        first_candidate["actionability"] = "blocked_authority"
        packet.update(
            {
                "terminal_justified": False,
                "hard_stop_required": False,
                "user_escalation": {
                    "reason_code": "authority-required",
                    "requested_input_or_authority": "approve-operation-A",
                    "evidence_ids": ["authority-E"],
                },
            }
        )
    else:
        for index, row in enumerate(analysis["lens_results"], start=1):
            row["output"]["candidates"] = []
            row["output"]["rejection_inventory"] = [
                {
                    "option_id": f"terminal-option-{index}",
                    "reason_code": "exhausted",
                    "evidence_ids": [f"terminal-E-{index}"],
                }
            ]
        packet.update(
            {
                "terminal_justified": True,
                "hard_stop_required": True,
                "terminal_blocker": {
                    "reason_code": "options-exhausted",
                    "evidence_ids": ["terminal-E"],
                },
            }
        )
    rehash(packet)
    if outcome == "terminal_wait":
        packet["terminal_wait"]["analysis_evidence_manifest_sha256"] = analysis[
            "shared_evidence_manifest_sha256"
        ]


def validate(packet: dict[str, Any], root: Path | None = None) -> set[str]:
    context = {"workspace_root": str(root)} if root is not None else None
    return codes(result_contract.validate("derive", packet, "block", context))


def test_valid_three_agent_manifest_passes_new_contract() -> None:
    observed = validate(valid_packet())
    assert (
        not {
            "derive_exact_three_lenses_required",
            "derive_lens_input_digest_mismatch",
            "derive_synthesis_lens_consumption_incomplete",
            "derive_synthesis_selected_outside_union",
            "derive_adapter_post_use_binding_mismatch",
            "derive_selection_outcome_missing_or_invalid",
        }
        & observed
    )


def test_active_advice_is_consumed_by_actual_three_lens_synthesis_receipt(
    tmp_path: Path,
) -> None:
    packet = valid_packet()
    activate_advice(packet, tmp_path)

    observed = validate(packet, tmp_path)

    assert (
        not {
            "derive_advice_clause_set_missing",
            "derive_advice_lens_clause_coverage_mismatch",
            "derive_advice_synthesis_reconciliation_invalid",
            "derive_advice_synthesis_output_receipt_invalid",
            "advice_clause_wired_without_consumer_receipt",
        }
        & observed
    )
    row = packet["advice_consumption_states"][0]
    assert row["derive_consumer_binding"]["synthesis_agent_id"] == "agent-synthesis"
    assert row["consumer_receipt_ref"] == runtime_ref("synthesis-A.json")
    assert row["evidence_provenance"] == "durable_runtime_artifact_bound"


def test_wired_advice_rejects_missing_or_tampered_runtime_artifacts(
    tmp_path: Path,
) -> None:
    missing = valid_packet()
    activate_advice(missing, tmp_path)
    (tmp_path / runtime_ref("lens-2.json")).unlink()
    assert "advice_clause_wired_without_consumer_receipt" in validate(missing, tmp_path)
    assert not result_contract.build_derive_advice_consumption_rows(
        missing, workspace_root=tmp_path
    )

    tampered = valid_packet()
    activate_advice(tampered, tmp_path)
    synthesis = tampered["improvement_analysis_manifest"]["synthesis"]
    noncanonical = json.dumps(
        result_contract.advice_synthesis_output_projection(synthesis),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ).encode("utf-8")
    (tmp_path / runtime_ref("synthesis-A.json")).write_bytes(noncanonical)
    assert "advice_clause_wired_without_consumer_receipt" in validate(
        tampered, tmp_path
    )


def test_wired_advice_rejects_path_escape_and_symbolic_link(
    tmp_path: Path,
) -> None:
    escaped = valid_packet()
    activate_advice(escaped, tmp_path)
    escaped["improvement_analysis_manifest"]["lens_results"][0]["output_ref"] = (
        "../outside.json"
    )
    assert not result_contract.build_derive_advice_consumption_rows(
        escaped, workspace_root=tmp_path
    )
    assert "advice_clause_wired_without_consumer_receipt" in validate(escaped, tmp_path)

    linked = valid_packet()
    activate_advice(linked, tmp_path)
    lens_path = tmp_path / runtime_ref("lens-3.json")
    lens_row = linked["improvement_analysis_manifest"]["lens_results"][2]
    lens_value = result_contract.advice_lens_receipt_projection(lens_row)
    target = tmp_path / "symlink-target.json"
    target.write_bytes(canonical_bytes(lens_value))
    lens_path.unlink()
    lens_path.symlink_to(target)
    assert "advice_clause_wired_without_consumer_receipt" in validate(linked, tmp_path)


def test_lens_file_binds_declared_agent_and_receipt_metadata(tmp_path: Path) -> None:
    packet = valid_packet()
    activate_advice(packet, tmp_path)
    analysis = packet["improvement_analysis_manifest"]
    lens_row = analysis["lens_results"][0]
    lens_row["agent_id"] = "agent-rebound"
    lens_row["output"]["advice_clause_assessments"][0]["lens_agent_id"] = (
        "agent-rebound"
    )
    rehash(packet)
    synthesis = analysis["synthesis"]
    write_runtime_artifact(
        tmp_path,
        synthesis["synthesis_output_ref"],
        result_contract.advice_synthesis_output_projection(synthesis),
    )

    assert not result_contract.build_derive_advice_consumption_rows(
        packet, workspace_root=tmp_path
    )


def test_result_authored_workspace_root_cannot_redirect_validation(
    tmp_path: Path,
) -> None:
    trusted_root = tmp_path / "trusted"
    redirected_root = tmp_path / "redirected"
    packet = valid_packet()
    activate_advice(packet, trusted_root)
    write_advice_runtime_artifacts(packet, redirected_root)
    packet["workspace_root"] = str(redirected_root)
    (trusted_root / runtime_ref("lens-1.json")).unlink()

    assert "advice_clause_wired_without_consumer_receipt" in validate(
        packet, trusted_root
    )


def test_verified_advice_rejects_missing_or_tampered_forward_artifacts(
    tmp_path: Path,
) -> None:
    missing = valid_packet()
    activate_advice(missing, tmp_path)
    attach_forward_test(missing, tmp_path)
    (tmp_path / runtime_ref("happy-agent-output.json")).unlink()
    assert "skill_forward_test_verified_without_full_receipt" in validate(
        missing, tmp_path
    )

    tampered = valid_packet()
    activate_advice(tampered, tmp_path)
    attach_forward_test(tampered, tmp_path)
    (tmp_path / runtime_ref("negative-forward-receipt.json")).write_bytes(b"{}")
    assert "skill_forward_test_verified_without_full_receipt" in validate(
        tampered, tmp_path
    )


def test_verified_negative_path_must_cross_a_decision_boundary(
    tmp_path: Path,
) -> None:
    packet = valid_packet()
    activate_advice(packet, tmp_path)
    attach_forward_test(packet, tmp_path)
    row = packet["skill_forward_test"][0]
    row["expected_decision_state"] = row["happy_expected_decision_state"]
    row["observed_decision_state"] = row["happy_observed_decision_state"]
    row["negative_path_receipt"] = forward_receipt(packet, row, "negative", tmp_path)

    assert "skill_forward_test_verified_without_full_receipt" in validate(
        packet, tmp_path
    )


def test_fabricated_consumer_binding_cannot_claim_wired_state(tmp_path: Path) -> None:
    packet = valid_packet()
    activate_advice(packet, tmp_path)
    row = packet["advice_consumption_states"][0]
    row["derive_consumer_binding"]["synthesis_receipt_id"] = "fabricated-receipt"
    row["consumer_receipt_sha256"] = (
        result_contract.advice_consumer_receipt_binding_sha256(row)
    )

    assert "advice_clause_wired_without_consumer_receipt" in validate(packet, tmp_path)


def test_each_lens_must_bind_exact_active_advice_clause_set(tmp_path: Path) -> None:
    packet = valid_packet()
    activate_advice(packet, tmp_path)
    output = packet["improvement_analysis_manifest"]["lens_results"][1]["output"]
    output["advice_clause_assessments"] = []
    rehash(packet)

    observed = validate(packet, tmp_path)

    assert "derive_advice_lens_clause_coverage_mismatch" in observed
    assert "advice_clause_wired_without_consumer_receipt" in observed


def test_verified_advice_requires_fresh_agents_and_independent_verifiers(
    tmp_path: Path,
) -> None:
    packet = valid_packet()
    activate_advice(packet, tmp_path)
    attach_forward_test(packet, tmp_path)
    observed = validate(packet, tmp_path)
    assert (
        not {
            "advice_clause_wired_without_consumer_receipt",
            "advice_clause_verified_without_forward_test",
            "skill_forward_test_verified_without_full_receipt",
        }
        & observed
    )

    fabricated = copy.deepcopy(packet)
    forward = fabricated["skill_forward_test"][0]["happy_path_receipt"]
    artifact = forward["producer_artifact"]
    verification = forward["independent_verification_receipt"]
    verification["verifier_agent_id"] = artifact["producer_agent_id"]
    verification["receipt_sha256"] = (
        result_contract.advice_forward_verification_receipt_sha256(verification)
    )
    forward["receipt_sha256"] = (
        result_contract.advice_forward_path_receipt_binding_sha256(
            fabricated["skill_forward_test"][0], forward
        )
    )
    sync_forward_runtime_artifacts(fabricated, tmp_path)
    assert "skill_forward_test_verified_without_full_receipt" in validate(
        fabricated, tmp_path
    )

    coupled = copy.deepcopy(packet)
    coupled_forward = coupled["skill_forward_test"][0]["negative_path_receipt"]
    coupled_verification = coupled_forward["independent_verification_receipt"]
    coupled_verification["verification_input_ids"] = coupled_forward[
        "producer_artifact"
    ]["precondition_ids"]
    coupled_verification["receipt_sha256"] = (
        result_contract.advice_forward_verification_receipt_sha256(coupled_verification)
    )
    coupled_forward["receipt_sha256"] = (
        result_contract.advice_forward_path_receipt_binding_sha256(
            coupled["skill_forward_test"][0], coupled_forward
        )
    )
    sync_forward_runtime_artifacts(coupled, tmp_path)
    assert "skill_forward_test_verified_without_full_receipt" in validate(
        coupled, tmp_path
    )

    reused_owner = copy.deepcopy(packet)
    forward_row = reused_owner["skill_forward_test"][0]
    happy_owner = forward_row["happy_path_receipt"]["independent_verification_receipt"][
        "invariant_owner_id"
    ]
    negative = forward_row["negative_path_receipt"]
    negative_verification = negative["independent_verification_receipt"]
    negative_verification["invariant_owner_id"] = happy_owner
    negative_verification["receipt_sha256"] = (
        result_contract.advice_forward_verification_receipt_sha256(
            negative_verification
        )
    )
    negative["receipt_sha256"] = (
        result_contract.advice_forward_path_receipt_binding_sha256(
            forward_row, negative
        )
    )
    sync_forward_runtime_artifacts(reused_owner, tmp_path)
    assert "skill_forward_test_verified_without_full_receipt" in validate(
        reused_owner, tmp_path
    )


def test_non_derive_self_hashed_booleans_remain_unwired() -> None:
    legacy = {
        "clause_id": "clause-Q",
        "state": "wired",
        "consumer_context_id": "derive-improvement-task",
        "consumer_contract_kind": "derive_three_lens_synthesis",
        "derive_consumer_binding": {"synthesis_receipt_id": "caller-authored"},
        "invocation_completed": True,
        "return_contract_valid": True,
        "decision_path_consumed": True,
        "decision_identity_echo": {"artifact_id": "artifact-A"},
        "evidence_provenance": "independently_verified",
        "consumer_receipt_ref": "caller-authored-ref",
    }
    legacy["consumer_receipt_sha256"] = (
        result_contract.advice_consumer_receipt_binding_sha256(legacy)
    )
    packet = {
        "step": "validate",
        "decision_artifact_ref": {"artifact_id": "artifact-A"},
        "advice_consumption_states": [legacy],
    }

    observed = result_contract.validate("validate", packet, "block")

    assert "advice_clause_wired_without_consumer_receipt" in codes(observed)


def test_prompt_and_validator_share_canonical_selection_resource() -> None:
    contract = json.loads(
        configuration.DERIVE_SELECTION_CONTRACT_PATH.read_text(encoding="utf-8")
    )
    assert configuration.DERIVE_SELECTION_CONTRACT == contract
    assert configuration.CANONICAL_PACK_DISPOSITIONS == frozenset(
        contract["pack_dispositions"]
    )
    assert configuration.DERIVE_SELECTION_OUTCOMES == frozenset(
        contract["selection_outcomes"]
    )


def test_lens_removal_and_required_field_mutation_fail_closed() -> None:
    missing_manifest = valid_packet()
    missing_manifest.pop("improvement_analysis_manifest")
    assert "derive_improvement_analysis_manifest_missing" in validate(missing_manifest)

    missing_lens = valid_packet()
    missing_lens["improvement_analysis_manifest"]["lens_results"].pop()
    assert "derive_exact_three_lenses_required" in validate(missing_lens)

    missing_output = valid_packet()
    missing_output["improvement_analysis_manifest"]["lens_results"][0].pop("output")
    assert "derive_lens_output_missing" in validate(missing_output)

    missing_owner = valid_packet()
    missing_owner["improvement_analysis_manifest"]["lens_results"][0]["output"][
        "candidates"
    ][0].pop("canonical_owner")
    rehash(missing_owner)
    assert "derive_lens_candidate_incomplete" in validate(missing_owner)


def test_agent_receipts_and_shared_input_must_be_unique_and_identical() -> None:
    duplicate = valid_packet()
    lenses = duplicate["improvement_analysis_manifest"]["lens_results"]
    lenses[1]["agent_receipt_id"] = lenses[0]["agent_receipt_id"]
    assert "derive_agent_receipts_not_unique" in validate(duplicate)

    duplicate_agent = valid_packet()
    lenses = duplicate_agent["improvement_analysis_manifest"]["lens_results"]
    lenses[1]["agent_id"] = lenses[0]["agent_id"]
    assert "derive_agent_ids_not_unique" in validate(duplicate_agent)

    reused_synthesis_agent = valid_packet()
    analysis = reused_synthesis_agent["improvement_analysis_manifest"]
    analysis["synthesis"]["synthesis_agent_id"] = analysis["lens_results"][0][
        "agent_id"
    ]
    assert "derive_synthesis_agent_id_invalid" in validate(reused_synthesis_agent)

    mismatch = valid_packet()
    mismatch["improvement_analysis_manifest"]["lens_results"][1][
        "input_evidence_manifest_sha256"
    ] = "0" * 64
    assert "derive_lens_input_digest_mismatch" in validate(mismatch)


def test_synthesis_must_consume_all_lenses_and_select_inside_union() -> None:
    omitted = valid_packet()
    omitted["improvement_analysis_manifest"]["synthesis"][
        "consumed_agent_receipt_ids"
    ].pop()
    assert "derive_synthesis_lens_consumption_incomplete" in validate(omitted)

    outside = valid_packet()
    outside["improvement_analysis_manifest"]["synthesis"]["selected_candidate_id"] = (
        "candidate-outside"
    )
    outside["selected_candidate_id"] = "candidate-outside"
    assert "derive_synthesis_selected_outside_union" in validate(outside)


def test_equivalent_lens_candidates_require_one_normalized_union_id() -> None:
    packet = valid_packet()
    duplicate = copy.deepcopy(candidate())
    duplicate["candidate_id"] = "candidate-alias"
    packet["improvement_analysis_manifest"]["lens_results"][1]["output"][
        "candidates"
    ] = [duplicate]
    packet["improvement_analysis_manifest"]["lens_results"][1]["output"][
        "rejection_inventory"
    ] = []
    rehash(packet)
    assert "derive_candidate_union_not_normalized" in validate(packet)


def test_zero_candidate_lens_requires_rejection_inventory() -> None:
    packet = valid_packet()
    packet["improvement_analysis_manifest"]["lens_results"][1]["output"][
        "rejection_inventory"
    ] = []
    rehash(packet)
    assert "derive_zero_candidate_rejection_inventory_missing" in validate(packet)


def test_issue_fit_unavailability_only_degrades_issue_derived_candidates() -> None:
    non_issue = valid_packet()
    issue_fit = non_issue["improvement_analysis_manifest"]["shared_evidence_manifest"][
        "issue_fit"
    ]
    issue_fit.update(
        {
            "status": "unavailable",
            "unavailable_reason": "issue-agent-timeout",
            "evidence_ids": ["timeout-A"],
        }
    )
    rehash(non_issue)
    assert "derive_issue_candidate_selected_without_fit" not in validate(non_issue)

    issue_candidate = copy.deepcopy(non_issue)
    issue_candidate["improvement_analysis_manifest"]["lens_results"][0]["output"][
        "candidates"
    ][0]["issue_derived"] = True
    rehash(issue_candidate)
    assert "derive_issue_candidate_selected_without_fit" in validate(issue_candidate)


def test_adapter_context_and_post_use_seal_are_required_and_bound() -> None:
    missing = valid_packet()
    missing["improvement_analysis_manifest"]["shared_evidence_manifest"].pop(
        "adapter_post_use_seal"
    )
    rehash(missing)
    assert "derive_adapter_post_use_seal_missing" in validate(missing)

    mismatched = valid_packet()
    seal = mismatched["improvement_analysis_manifest"]["shared_evidence_manifest"][
        "adapter_post_use_seal"
    ]
    seal["artifact_id"] = "artifact-other"
    seal["receipt_sha256"] = digest(
        {key: value for key, value in seal.items() if key != "receipt_sha256"}
    )
    rehash(mismatched)
    assert "derive_adapter_post_use_binding_mismatch" in validate(mismatched)

    unloaded = valid_packet()
    adapter_packet = unloaded["improvement_analysis_manifest"][
        "shared_evidence_manifest"
    ]["adapter_decision_context"]["packet"]
    adapter_packet["load_preflight"]["status"] = "not_evaluated"
    context = unloaded["improvement_analysis_manifest"]["shared_evidence_manifest"][
        "adapter_decision_context"
    ]
    context["packet_sha256"] = digest(adapter_packet)
    rehash(unloaded)
    assert "derive_adapter_decision_context_not_pass" in validate(unloaded)


def explicit_decision_ref() -> dict[str, Any]:
    return {
        "decision_subject_id": "subject-A",
        "subject_class_id": "class-A",
        "revision_id": "revision-A",
        "subject_digest": "a" * 64,
        "body_fingerprint": {"applicability": "applicable", "value": "b" * 64},
        "production_lane": {"applicability": "not_applicable", "value": None},
        "cohort": {"applicability": "applicable", "value": ["cohort-A"]},
        "lineage_id": "lineage-A",
        "producer_run": {"applicability": "not_applicable", "value": None},
        "freshness_status": "current",
    }


def bind_explicit_decision_ref(packet: dict[str, Any]) -> None:
    evidence = packet["improvement_analysis_manifest"]["shared_evidence_manifest"]
    decision_ref = explicit_decision_ref()
    evidence["decision_artifact_ref"] = decision_ref
    context = evidence["adapter_decision_context"]
    adapter_packet = context["packet"]
    adapter_packet["decision_identity"] = decision_ref
    seal = evidence["adapter_post_use_seal"]
    for field in (
        "artifact_id",
        "artifact_sha256",
        "body_projection_fingerprint",
        "production_lane_identity",
    ):
        seal.pop(field, None)
    seal["decision_identity_echo"] = {
        "decision_subject_id": "subject-A",
        "subject_class_id": "class-A",
        "revision_id": "revision-A",
        "subject_digest": "a" * 64,
        "lineage_id": "lineage-A",
        "freshness_status": "current",
        "dimension_values": {
            "body_fingerprint": "b" * 64,
            "cohort": ["cohort-A"],
        },
    }
    seal["receipt_sha256"] = digest(
        {key: value for key, value in seal.items() if key != "receipt_sha256"}
    )
    adapter_packet["post_use_decision_receipt"]["receipt_sha256"] = seal[
        "receipt_sha256"
    ]
    context["packet_sha256"] = digest(adapter_packet)
    rehash(packet)


def test_derive_explicit_identity_binds_revision_and_only_applicable_dimensions() -> (
    None
):
    packet = valid_packet()
    bind_explicit_decision_ref(packet)
    observed = validate(packet)
    assert (
        not {
            "derive_shared_evidence_identity_incomplete",
            "derive_adapter_post_use_binding_mismatch",
            "derive_adapter_post_use_receipt_invalid",
        }
        & observed
    )

    mismatched = copy.deepcopy(packet)
    seal = mismatched["improvement_analysis_manifest"]["shared_evidence_manifest"][
        "adapter_post_use_seal"
    ]
    seal["decision_identity_echo"]["dimension_values"]["production_lane"] = "lane-stale"
    seal["receipt_sha256"] = digest(
        {key: value for key, value in seal.items() if key != "receipt_sha256"}
    )
    context = mismatched["improvement_analysis_manifest"]["shared_evidence_manifest"][
        "adapter_decision_context"
    ]
    context["packet"]["post_use_decision_receipt"]["receipt_sha256"] = seal[
        "receipt_sha256"
    ]
    context["packet_sha256"] = digest(context["packet"])
    rehash(mismatched)
    assert "derive_adapter_post_use_binding_mismatch" in validate(mismatched)


def test_derive_consumer_rejects_goal_progress_from_coupled_invariant_owner() -> None:
    packet = valid_packet()
    packet["independent_source_separation_status"] = "pass"
    packet["independent_invariant_separation_status"] = "coupled"
    assert "derive_goal_productive_from_coupled_invariant_verification" in validate(
        packet
    )

    separated = valid_packet()
    separated["independent_source_separation_status"] = "pass"
    separated["independent_invariant_separation_status"] = "pass"
    assert "derive_goal_productive_from_coupled_invariant_verification" not in validate(
        separated
    )


def test_derive_explicit_identity_requires_current_subject_revision() -> None:
    packet = valid_packet()
    bind_explicit_decision_ref(packet)
    evidence = packet["improvement_analysis_manifest"]["shared_evidence_manifest"]
    evidence["decision_artifact_ref"]["freshness_status"] = "stale"
    context = evidence["adapter_decision_context"]
    context["packet"]["decision_identity"]["freshness_status"] = "stale"
    seal = evidence["adapter_post_use_seal"]
    seal["decision_identity_echo"]["freshness_status"] = "stale"
    seal["receipt_sha256"] = digest(
        {key: value for key, value in seal.items() if key != "receipt_sha256"}
    )
    context["packet"]["post_use_decision_receipt"]["receipt_sha256"] = seal[
        "receipt_sha256"
    ]
    context["packet_sha256"] = digest(context["packet"])
    rehash(packet)
    assert "derive_shared_evidence_identity_not_current" in validate(packet)


def test_evidenced_empty_adapter_registry_is_general_not_applicable_path() -> None:
    packet = valid_packet()
    evidence = packet["improvement_analysis_manifest"]["shared_evidence_manifest"]
    evidence.pop("adapter_decision_context")
    evidence.pop("adapter_post_use_seal")
    evidence.update(
        {
            "adapter_applicability": "not_applicable",
            "adapter_registry_status": "no_registered_adapter",
            "adapter_not_applicable_reason": "adapter-registry-empty",
            "adapter_registry_evidence_ids": ["adapter-scan-E"],
        }
    )
    rehash(packet)
    observed = validate(packet)
    assert (
        not {
            "derive_adapter_not_applicable_unproven",
            "derive_adapter_decision_context_missing",
            "derive_adapter_post_use_seal_missing",
        }
        & observed
    )


@pytest.mark.parametrize(
    "outcome", ("selected", "terminal_wait", "terminal_blocked", "user_escalation")
)
def test_four_selection_outcomes_are_structurally_disjoint(outcome: str) -> None:
    packet = valid_packet()
    set_outcome(packet, outcome)
    observed = validate(packet)
    assert (
        not {
            "derive_terminal_disposition_mismatch",
            "derive_terminal_wait_hard_stop_contradiction",
            "derive_terminal_blocked_not_justified",
            "derive_user_escalation_terminal_contradiction",
            "derive_selected_terminal_fields_present",
        }
        & observed
    )


def test_terminal_wait_requires_selection_tick_baseline_not_analysis_digest_alias() -> (
    None
):
    packet = valid_packet()
    set_outcome(packet, "terminal_wait")
    wait = packet["terminal_wait"]
    wait["observed_input_manifest_sha256"] = wait["analysis_evidence_manifest_sha256"]

    assert "derive_terminal_wait_tick_baseline_invalid" in validate(packet)


def test_terminal_wait_rejects_fanout_enabling_tick_receipt() -> None:
    packet = valid_packet()
    set_outcome(packet, "terminal_wait")
    baseline = packet["terminal_wait"]["selection_tick_baseline"]
    baseline["agent_fanout_allowed"] = True
    packet["terminal_wait"]["selection_tick_baseline_sha256"] = digest(baseline)

    assert "derive_terminal_wait_tick_baseline_invalid" in validate(packet)


def test_terminal_wait_binds_rebased_tick_to_last_selection_receipt(
    tmp_path: Path,
) -> None:
    packet = valid_packet()
    set_outcome(packet, "terminal_wait")
    wait = packet["terminal_wait"]
    task = tmp_path / "task.md"
    task.write_text("# Task A\n", encoding="utf-8")
    goal = tmp_path / ".agent_goal/final_goal.md"
    goal.parent.mkdir(parents=True, exist_ok=True)
    goal.write_text("# Goal A\n", encoding="utf-8")
    initial = build_selection_tick(
        tmp_path,
        premise_contract=VERIFIED_PREMISE_CONTRACT,
    )
    goal.write_text("# Goal B\n", encoding="utf-8")
    trigger = build_selection_tick(tmp_path, previous=initial)
    trigger_path = tmp_path / ".task/cycle/cycle-A/selection-trigger.json"
    trigger_path.parent.mkdir(parents=True, exist_ok=True)
    trigger_path.write_text(
        json.dumps(trigger, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    trigger_binding = {
        "ref": trigger_path.relative_to(tmp_path).as_posix(),
        "sha256": hashlib.sha256(trigger_path.read_bytes()).hexdigest(),
    }
    synthesis_source = valid_packet()
    set_outcome(synthesis_source, "terminal_wait")
    synthesis_source["cycle_id"] = "cycle-A"
    synthesis_analysis = synthesis_source["improvement_analysis_manifest"]
    for index, row in enumerate(synthesis_analysis["lens_results"], start=1):
        row["output_ref"] = runtime_ref(f"selection-lens-{index}.json")
    synthesis_analysis["synthesis"]["synthesis_output_ref"] = runtime_ref(
        "selection-synthesis-output.json"
    )
    rehash(synthesis_source)
    write_advice_runtime_artifacts(synthesis_source, tmp_path)
    synthesis = render_selection_synthesis(tmp_path, synthesis_source)
    synthesis_path = tmp_path / ".task/cycle/cycle-A/selection-synthesis.json"
    synthesis_path.write_text(
        json.dumps(synthesis, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    synthesis_binding = {
        "ref": synthesis_path.relative_to(tmp_path).as_posix(),
        "sha256": hashlib.sha256(synthesis_path.read_bytes()).hexdigest(),
    }
    decision = render_preliminary_selection_decision(
        tmp_path,
        trigger,
        synthesis_binding,
    )
    decision_path = tmp_path / ".task/cycle/cycle-A/preliminary-decision.json"
    decision_path.write_text(
        json.dumps(decision, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    decision_binding = {
        "ref": decision_path.relative_to(tmp_path).as_posix(),
        "sha256": hashlib.sha256(decision_path.read_bytes()).hexdigest(),
    }
    receipt = render_selection_decision_receipt(
        tmp_path,
        trigger,
        trigger_binding,
        decision_binding,
    )
    receipt_path = tmp_path / ".task/cycle/cycle-A/selection-receipt.json"
    receipt_path.write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    receipt_binding = {
        "ref": receipt_path.relative_to(tmp_path).as_posix(),
        "sha256": hashlib.sha256(receipt_path.read_bytes()).hexdigest(),
    }
    baseline = build_selection_tick(
        tmp_path,
        previous=trigger,
        acknowledge_selection_tick_id=trigger["packet_id"],
        selection_receipt_ref=receipt_binding["ref"],
        selection_receipt_sha256=receipt_binding["sha256"],
    )
    wait.update(
        {
            "observed_input_manifest_sha256": baseline[
                "observed_input_manifest_sha256"
            ],
            "selection_tick_baseline": baseline,
            "selection_tick_baseline_sha256": digest(baseline),
            "wake_predicates": baseline["wake_predicates"],
            "watched_evidence_classes": baseline["watched_evidence_classes"],
            "minimum_material_delta": baseline["minimum_material_delta"],
            "last_selection_receipt": receipt["receipt_id"],
        }
    )

    assert "derive_terminal_wait_tick_baseline_invalid" not in validate(
        packet, tmp_path
    )

    wait["last_selection_receipt"] = "selection-B"
    assert "derive_terminal_wait_tick_baseline_invalid" in validate(packet, tmp_path)


def test_initial_init_terminal_wait_does_not_require_or_allow_next_task_id() -> None:
    packet = valid_packet()
    set_outcome(packet, "terminal_wait")
    packet["derive_mode"] = "initial_init"
    packet.pop("completed_task_id")

    observed = validate(packet)

    assert "missing_required_field" not in observed
    assert "derive_terminal_wait_has_next_task" not in observed
    assert "derive_governance_only_selected" not in observed


@pytest.mark.parametrize(
    ("outcome", "mutations", "expected_code"),
    (
        (
            "selected",
            {"terminal_blocker": {"reason_code": "x", "evidence_ids": ["E"]}},
            "derive_selected_terminal_fields_present",
        ),
        (
            "selected",
            {"terminal_disposition": "terminal_wait"},
            "derive_selected_terminal_fields_present",
        ),
        (
            "selected",
            {"selected_disposition": "user_escalation"},
            "derive_selected_terminal_fields_present",
        ),
        (
            "terminal_wait",
            {"hard_stop_required": True},
            "derive_terminal_wait_hard_stop_contradiction",
        ),
        (
            "terminal_wait",
            {"user_escalation": {"reason_code": "x"}},
            "derive_terminal_wait_outcome_contradiction",
        ),
        (
            "terminal_wait",
            {"selected_candidate_id": "candidate-A"},
            "derive_terminal_candidate_selected",
        ),
        (
            "terminal_blocked",
            {"terminal_justified": False},
            "derive_terminal_blocked_not_justified",
        ),
        (
            "user_escalation",
            {"terminal_justified": True},
            "derive_user_escalation_terminal_contradiction",
        ),
    ),
)
def test_terminal_outcome_contradictions_fail_closed(
    outcome: str,
    mutations: dict[str, Any],
    expected_code: str,
) -> None:
    packet = valid_packet()
    set_outcome(packet, outcome)
    packet.update(mutations)
    assert expected_code in validate(packet)


def prerequisite_chain(**updates: object) -> dict[str, object]:
    value: dict[str, object] = {
        "applicability": "applicable",
        "stable_root_id": "root-A",
        "item_owner_id": "owner-A",
        "prerequisite_relation_id": "relation-A",
        "strict_local_reduction": True,
        "semantic_high_water_moved": False,
        "chain_budget_status": "within",
        "mandatory_successor_kind": "producer",
        "selected_successor_kind": "prerequisite",
        "chain_position": 1,
        "chain_cap": 2,
        "residual_before": 3,
        "residual_after": 2,
    }
    value.update(updates)
    if (
        value.get("strict_local_reduction") is True
        and "reduction_observation_receipt" not in value
    ):
        receipt: dict[str, object] = {
            "contract_version": "prerequisite-reduction-observation-v1",
            "receipt_id": "receipt-A",
            "stable_root_id": value["stable_root_id"],
            "prerequisite_relation_id": value["prerequisite_relation_id"],
            "residual_basis_id": "basis-A",
            "observation_kind": "residual",
            "before_observation": {
                "observation_id": "observation-before-A",
                "revision_id": "revision-before-A",
                "value": value.get("residual_before"),
                "evidence_ref_id": "evidence-before-A",
                "evidence_sha256": "a" * 64,
            },
            "after_observation": {
                "observation_id": "observation-after-A",
                "revision_id": "revision-after-A",
                "value": value.get("residual_after"),
                "evidence_ref_id": "evidence-after-A",
                "evidence_sha256": "b" * 64,
            },
            "source_kind": "task_pack_projection",
            "source_revision_sha256": "c" * 64,
            "source_snapshot_sha256": "d" * 64,
            "observer_id": "observer-A",
            "invariant_owner_id": "owner-invariant-A",
            "provenance_status": "independently_observed",
        }
        receipt["receipt_sha256"] = receipt_sha256(receipt)
        value["reduction_observation_receipt"] = receipt
    return value


def test_reducing_prerequisite_chain_can_continue_inside_budget() -> None:
    packet = valid_packet()
    packet["bounded_prerequisite_chain"] = prerequisite_chain()

    observed = validate(packet)

    assert (
        not {
            "derive_nonconvergent_prerequisite_chain_recurred",
            "derive_exhausted_prerequisite_chain_recurred",
            "derive_prerequisite_chain_reduction_unsubstantiated",
        }
        & observed
    )


def test_nonreducing_prerequisite_chain_cannot_recur() -> None:
    packet = valid_packet()
    packet["bounded_prerequisite_chain"] = prerequisite_chain(
        strict_local_reduction=False,
        residual_after=3,
    )

    assert "derive_nonconvergent_prerequisite_chain_recurred" in validate(packet)


def test_decreasing_prerequisite_scalars_without_receipt_do_not_authorize_recurrence() -> (
    None
):
    packet = valid_packet()
    chain = prerequisite_chain()
    chain.pop("reduction_observation_receipt")
    packet["bounded_prerequisite_chain"] = chain

    assert "derive_prerequisite_chain_reduction_unsubstantiated" in validate(packet)


def test_exhausted_prerequisite_chain_enforces_direct_successor() -> None:
    packet = valid_packet()
    packet["bounded_prerequisite_chain"] = prerequisite_chain(
        chain_budget_status="exhausted",
        chain_position=2,
        selected_successor_kind="prerequisite",
    )

    observed = validate(packet)

    assert "derive_exhausted_prerequisite_chain_recurred" in observed
    assert "derive_prerequisite_chain_successor_not_enforced" in observed


def test_exhausted_prerequisite_chain_accepts_mandatory_direct_successor() -> None:
    packet = valid_packet()
    packet["selected_task_kind"] = "producer_repair"
    packet["bounded_prerequisite_chain"] = prerequisite_chain(
        chain_budget_status="exhausted",
        chain_position=2,
        selected_successor_kind="producer",
    )

    observed = validate(packet)

    assert (
        not {
            "derive_exhausted_prerequisite_chain_recurred",
            "derive_prerequisite_chain_successor_not_enforced",
            "derive_prerequisite_chain_selected_task_kind_missing",
        }
        & observed
    )


def test_exhausted_prerequisite_chain_rejects_unrelated_concrete_task_kind() -> None:
    packet = valid_packet()
    packet["selected_task_kind"] = "report_repair"
    packet["bounded_prerequisite_chain"] = prerequisite_chain(
        chain_budget_status="exhausted",
        chain_position=2,
        selected_successor_kind="producer",
    )

    assert "derive_prerequisite_chain_selected_task_kind_mismatch" in validate(packet)


def test_prerequisite_not_applicable_requires_reason_receipt() -> None:
    packet = valid_packet()
    packet["bounded_prerequisite_chain"] = {"applicability": "not_applicable"}

    assert "derive_prerequisite_chain_not_applicable_unsubstantiated" in validate(
        packet
    )

    evidence: dict[str, object] = {
        "contract_version": "prerequisite-not-applicable-v1",
        "reason_id": "reason-no-chain-A",
        "subject_id": "subject-A",
        "evidence_ref_id": "evidence-no-chain-A",
        "evidence_sha256": "e" * 64,
    }
    evidence["receipt_sha256"] = receipt_sha256(evidence)
    packet["bounded_prerequisite_chain"] = {
        "applicability": "not_applicable",
        "not_applicable_evidence": evidence,
    }

    assert "derive_prerequisite_chain_not_applicable_unsubstantiated" not in validate(
        packet
    )


def test_pending_finalization_conflict_blocks_normal_successor() -> None:
    packet = valid_packet()
    packet["pending_finalization_conflicts"] = [
        {
            "pending_conflict_id": "pending-A",
            "state_commit_status": "recovery_required",
            "attempt_memory_disposition": "pending_conflict",
        }
    ]

    assert "derive_pending_finalization_conflict_bypassed" in validate(packet)


def test_pending_finalization_conflict_allows_recovery_task_only() -> None:
    packet = valid_packet()
    packet["pending_finalization_conflicts"] = [
        {
            "pending_conflict_id": "pending-A",
            "state_commit_status": "recovery_required",
            "attempt_memory_disposition": "pending_conflict",
        }
    ]
    packet["selected_task_kind"] = "finalization_conflict_recovery"

    assert "derive_pending_finalization_conflict_bypassed" not in validate(packet)


def authority_row(**updates: object) -> dict[str, object]:
    value: dict[str, object] = {
        "item_id": "residual-A",
        "authority_status": "already_granted",
        "local_resolution_status": "unavailable",
        "external_dependency": "none",
        "risk_or_cost_confirmation": "not_required",
        "resolution_kind_id": "resolution-A",
        "authority_evidence_ids": ["authority-evidence-A"],
        "local_capability_evidence_ids": ["local-evidence-A"],
        "classification_valid": True,
    }
    value.update(updates)
    return value


def test_legacy_local_resolution_axes_are_diagnostic_only() -> None:
    packet = valid_packet()
    set_outcome(packet, "terminal_blocked")
    packet["goal_terminal_prohibited"] = True
    packet["authority_classification"] = [
        authority_row(local_resolution_status="available")
    ]

    assert "derive_terminal_authority_axes_unverified" in validate(packet)


def test_legacy_new_authority_axis_cannot_authorize_user_escalation() -> None:
    packet = valid_packet()
    set_outcome(packet, "user_escalation")
    packet["goal_terminal_prohibited"] = True
    packet["authority_classification"] = [
        authority_row(authority_status="new_authority_required")
    ]

    observed = validate(packet)

    assert "derive_terminal_authority_axes_unverified" in observed


def test_legacy_waiting_state_requires_classification_repair() -> None:
    packet = valid_packet()
    set_outcome(packet, "terminal_wait")
    packet["goal_terminal_prohibited"] = True
    packet["authority_classification"] = [
        authority_row(external_dependency="waiting_state")
    ]

    assert "derive_terminal_authority_axes_unverified" in validate(packet)

    selected = valid_packet()
    selected["selected_task_kind"] = "producer_repair"
    selected["authority_classification"] = [
        authority_row(external_dependency="waiting_state")
    ]
    assert "derive_authority_axes_unverified_unrecovered" in validate(selected)

    selected["selected_task_kind"] = "monitor_running_execution"
    assert "derive_authority_axes_unverified_unrecovered" in validate(selected)


def test_unverified_authority_axes_cannot_support_terminal() -> None:
    packet = valid_packet()
    set_outcome(packet, "terminal_blocked")
    packet["offline_scope_unverified"] = True

    assert "derive_terminal_authority_axes_unverified" in validate(packet)


def test_self_declared_favorable_authority_axes_without_evidence_cannot_route_terminal() -> (
    None
):
    packet = valid_packet()
    set_outcome(packet, "terminal_wait")
    row = authority_row(external_dependency="waiting_state")
    row.pop("classification_valid")
    row.pop("authority_evidence_ids")
    row.pop("local_capability_evidence_ids")
    packet["authority_classification"] = [row]

    observed = validate(packet)

    assert "derive_terminal_authority_axes_unverified" in observed
