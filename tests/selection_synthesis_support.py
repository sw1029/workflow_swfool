"""Shared durable three-lens synthesis fixtures for selection receipt tests."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from orchestrate_task_cycle.result_contract import api as result_contract
from orchestrate_task_cycle.result_contract.derive_advice_artifacts import (
    advice_lens_receipt_projection,
    advice_synthesis_output_projection,
)
from orchestrate_task_cycle.result_contract.advice_runtime_artifacts import (
    canonical_json_bytes,
)
from orchestrate_task_cycle.selection_synthesis import render_selection_synthesis
from orchestrate_task_cycle.selection_tick_premise import (
    VERIFIED_PREMISE_CONTRACT,
)


def _digest(value: object) -> str:
    body = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(body).hexdigest()


def _tick_packet_id(value: dict[str, Any]) -> str:
    body = (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    )
    return "selection-tick-" + hashlib.sha256(body.encode()).hexdigest()[:32]


def _candidate() -> dict[str, Any]:
    return {
        "candidate_id": "candidate-A",
        "exact_subject_fingerprint": "subject-A",
        "first_failing_invariant": "invariant-A",
        "canonical_owner": "owner-A",
        "task_kind": "producer_repair",
        "expected_blocker_transition": "blocked-to-measured",
        "actionability": "actionable",
        "pack_disposition": "derive_standalone",
        "issue_derived": False,
        "evidence_ids": ["evidence-A"],
        "validation_ids": ["validation-A"],
    }


def _lens(
    role: str,
    index: int,
    candidates: list[dict[str, Any]],
) -> dict[str, Any]:
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
        "output_sha256": _digest(output),
        "output": output,
    }


def _valid_packet() -> dict[str, Any]:
    """Build a valid derive-analysis packet without importing a test module."""

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
    seal["receipt_sha256"] = _digest(seal)
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
        "packet_sha256": _digest(adapter_packet),
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
    evidence_sha = _digest(evidence)
    lenses = [
        _lens("goal_value", 1, [_candidate()]),
        _lens("architecture_contract", 2, []),
        _lens("miss_validation", 3, []),
    ]
    for row in lenses:
        row["input_evidence_manifest_sha256"] = evidence_sha
        row["output"]["advice_clause_set_sha256"] = active_advice["clause_set_sha256"]
        row["output_sha256"] = _digest(row["output"])
    synthesis = {
        "synthesis_agent_id": "agent-synthesis",
        "synthesis_receipt_id": "synthesis-A",
        "input_evidence_manifest_sha256": evidence_sha,
        "consumed_agent_receipt_ids": [row["agent_receipt_id"] for row in lenses],
        "candidate_union_ids": ["candidate-A"],
        "candidate_union_sha256": _digest(["candidate-A"]),
        "selected_candidate_id": "candidate-A",
        "selection_outcome": "selected",
        "pack_disposition": "derive_standalone",
        "advice_clause_set_sha256": active_advice["clause_set_sha256"],
        "advice_clause_reconciliation": [],
        "advice_reconciliation_sha256": (
            result_contract.advice_reconciliation_set_sha256([])
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


def _rehash(packet: dict[str, Any]) -> None:
    analysis = packet["improvement_analysis_manifest"]
    advice = analysis["shared_evidence_manifest"]["active_advice_clause_set"]
    advice["clause_set_sha256"] = result_contract.advice_clause_set_sha256(advice)
    shared_sha = _digest(analysis["shared_evidence_manifest"])
    analysis["shared_evidence_manifest_sha256"] = shared_sha
    for row in analysis["lens_results"]:
        row["input_evidence_manifest_sha256"] = shared_sha
        row["output"]["advice_clause_set_sha256"] = advice["clause_set_sha256"]
        for assessment in row["output"].get("advice_clause_assessments", []):
            assessment["assessment_sha256"] = result_contract.advice_assessment_sha256(
                assessment
            )
        row["output_sha256"] = _digest(row["output"])
    synthesis = analysis["synthesis"]
    synthesis["input_evidence_manifest_sha256"] = shared_sha
    candidate_ids = sorted(
        candidate_row["candidate_id"]
        for row in analysis["lens_results"]
        for candidate_row in row["output"]["candidates"]
    )
    synthesis["candidate_union_ids"] = candidate_ids
    synthesis["candidate_union_sha256"] = _digest(candidate_ids)
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


def _set_outcome(packet: dict[str, Any], outcome: str) -> None:
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
        tick_baseline["packet_id"] = _tick_packet_id(tick_baseline)
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
                    "selection_tick_baseline_sha256": _digest(tick_baseline),
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
    _rehash(packet)
    if outcome == "terminal_wait":
        packet["terminal_wait"]["analysis_evidence_manifest_sha256"] = analysis[
            "shared_evidence_manifest_sha256"
        ]


def _write_json(path: Path, value: object, *, canonical: bool = False) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = (
        canonical_json_bytes(value)
        if canonical
        else (
            json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8")
    )
    path.write_bytes(body)
    return path


def binding(root: Path, path: Path) -> dict[str, str]:
    return {
        "ref": path.relative_to(root).as_posix(),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def persisted_selection_synthesis(
    root: Path,
    *,
    outcome: str = "selected",
    suffix: str = "A",
    selected_task_id: str = "task-next",
) -> tuple[dict[str, Any], dict[str, str], dict[str, Any]]:
    """Persist 3 lens outputs, one synthesis output, and their sealed projection."""

    result = _valid_packet()
    if outcome != "selected":
        _set_outcome(result, outcome)
    else:
        result["next_task_id"] = selected_task_id
    cycle_id = str(
        result["improvement_analysis_manifest"]["shared_evidence_manifest"]["cycle_id"]
    )
    result["cycle_id"] = cycle_id
    analysis = result["improvement_analysis_manifest"]
    receipt_root = root / ".task" / "cycle" / cycle_id / "agent_receipts"
    for index, row in enumerate(analysis["lens_results"], start=1):
        row["output_ref"] = (
            (receipt_root / f"lens-{suffix}-{index}.json").relative_to(root).as_posix()
        )
    analysis["synthesis"]["synthesis_output_ref"] = (
        (receipt_root / f"synthesis-{suffix}.json").relative_to(root).as_posix()
    )
    _rehash(result)
    for row in analysis["lens_results"]:
        _write_json(
            root / row["output_ref"],
            advice_lens_receipt_projection(row),
            canonical=True,
        )
    synthesis = analysis["synthesis"]
    _write_json(
        root / synthesis["synthesis_output_ref"],
        advice_synthesis_output_projection(synthesis),
        canonical=True,
    )
    projection = render_selection_synthesis(root, result)
    projection_path = _write_json(
        root / ".task" / "cycle" / cycle_id / f"selection-synthesis-{suffix}.json",
        projection,
    )
    return result, binding(root, projection_path), projection


__all__ = ("binding", "persisted_selection_synthesis")
