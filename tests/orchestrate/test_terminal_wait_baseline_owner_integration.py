from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from manage_agent_authority.artifact_store import register_grant, snapshot_file
from manage_agent_authority.authority_cli import command_consume, command_verify
from manage_agent_authority.canonical import sha256_file, write_immutable_json
from manage_agent_authority.evaluator import evaluate
from manage_agent_authority.lifecycle import reserve
from orchestrate_task_cycle.authority_packet import build_authority_packet
from orchestrate_task_cycle.result_contract import api as result_contract
from orchestrate_task_cycle.result_contract.legacy_revision_bridge import (
    legacy_revision_bridge_sha256,
)
from orchestrate_task_cycle.selection_decision_receipt import (
    render_preliminary_selection_decision,
    render_selection_decision_receipt,
)
from orchestrate_task_cycle.selection_synthesis import render_selection_synthesis
from orchestrate_task_cycle.selection_tick import build_selection_tick
from orchestrate_task_cycle.terminal_wait_baseline import (
    activate_terminal_wait_baseline,
    audit_terminal_wait_baseline,
    current_selection_tick_packet,
    materialize_terminal_wait_authority_subject,
    prepare_terminal_wait_baseline,
    resolve_terminal_wait_baseline,
)
from orchestrate_task_cycle.terminal_wait_baseline_contract import (
    validate_selection_packet,
)


SKILLS_ROOT = Path(__file__).resolve().parents[2]
AT = "2026-07-18T00:00:00+00:00"
PRE_DISPATCH_AT = "2026-07-18T00:01:00+00:00"
PRE_COMMIT_AT = "2026-07-18T00:02:00+00:00"
CONSUMED_AT = "2026-07-18T00:03:00+00:00"
EXPIRES_AT = "2026-07-18T01:00:00+00:00"
TASK_ID = "task-terminal-wait-owner-integration"
PREMISE_CONTRACT = "validated_exact_subject_premise_receipt_v2"


def _write(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def _write_json(path: Path, value: dict[str, Any]) -> Path:
    return _write(
        path,
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )


def _write_canonical_json(path: Path, value: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    )
    return path


def _binding(root: Path, path: Path) -> dict[str, str]:
    return {
        "ref": path.relative_to(root).as_posix(),
        "sha256": sha256_file(path),
    }


def _operation() -> dict[str, str]:
    return {
        "skill_id": "orchestrate-task-cycle",
        "skill_version": "2.0.0",
        "operation_id": "publish_terminal_wait_baseline_binding",
        "operation_version": "1",
    }


def _capture_json(capsys: pytest.CaptureFixture[str]) -> dict[str, Any]:
    return json.loads(capsys.readouterr().out)


def _canonical_digest(value: object) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _derive_candidate() -> dict[str, Any]:
    return {
        "candidate_id": "candidate-terminal-wait",
        "exact_subject_fingerprint": "subject-terminal-wait",
        "first_failing_invariant": "no-fresh-executable-successor",
        "canonical_owner": "derive-improvement-task",
        "task_kind": "producer_repair",
        "expected_blocker_transition": "blocked-to-measured",
        "actionability": "blocked_external",
        "pack_disposition": "derive_standalone",
        "issue_derived": False,
        "evidence_ids": ["evidence-terminal-wait"],
        "validation_ids": ["validation-terminal-wait"],
    }


def _derive_lens(
    role: str,
    index: int,
    candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    output = {
        "candidates": candidates,
        "rejection_inventory": (
            []
            if candidates
            else [
                {
                    "option_id": f"terminal-option-{index}",
                    "reason_code": "lower-value",
                    "evidence_ids": [f"terminal-evidence-{index}"],
                }
            ]
        ),
        "advice_clause_set_sha256": "",
        "advice_clause_assessments": [],
    }
    return {
        "role_id": role,
        "agent_id": f"terminal-agent-{index}",
        "agent_receipt_id": f"terminal-agent-receipt-{index}",
        "read_only": True,
        "status": "complete",
        "input_evidence_manifest_sha256": "",
        "output_ref": (
            f".task/cycle/cycle-terminal-wait/agent_receipts/terminal-lens-{index}.json"
        ),
        "output_sha256": _canonical_digest(output),
        "output": output,
    }


def _derive_result_template() -> dict[str, Any]:
    identity = {
        "cycle_id": "cycle-terminal-wait",
        "task_id": TASK_ID,
        "attempt_id": "attempt-terminal-wait",
        "artifact_id": "artifact-terminal-wait",
        "artifact_sha256": "a" * 64,
        "body_projection_fingerprint": "b" * 64,
        "production_lane_identity": "lane-terminal-wait",
        "input_state_fingerprint": "c" * 64,
    }
    seal = {
        "schema_version": 1,
        "consumer_id": "derive-improvement-task",
        **identity,
        "adapter_revision_sha256": "d" * 64,
        "hook_results_sha256": "f" * 64,
        "value_consumed_by_decision": True,
        "decision_id": "derive-decision-terminal-wait",
    }
    seal["receipt_sha256"] = _canonical_digest(seal)
    adapter_packet = {
        "phase": "derive",
        "required_consumer_ids": ["derive-improvement-task"],
        "static_validation": {"status": "pass"},
        "load_preflight": {"status": "pass"},
        "candidate_projection": {"status": "eligible", "eligible": True},
        "adapter_revision": {"adapter_revision_sha256": "d" * 64},
        "hook_results_sha256": "f" * 64,
        "decision_identity": identity,
        "post_use_decision_receipt": {
            "status": "pass",
            "receipt_sha256": seal["receipt_sha256"],
        },
    }
    evidence = {
        **identity,
        "issue_fit": {
            "status": "available",
            "evidence_ids": ["issue-fit-terminal-wait"],
        },
        "adapter_applicability": "required",
        "adapter_decision_context": {
            "packet_ref": "adapter-context-terminal-wait.json",
            "packet_sha256": _canonical_digest(adapter_packet),
            "packet": adapter_packet,
        },
        "adapter_post_use_seal": seal,
        "evidence_refs": [
            {
                "evidence_id": "source-terminal-wait",
                "ref": "source-terminal-wait.json",
                "sha256": "1" * 64,
            }
        ],
    }
    active_advice = {
        "contract_version": 1,
        "applicability": "not_applicable",
        "advice_packet_digest": None,
        "actionable_clause_ids": [],
        "clause_source_digests": {},
        "not_applicable_reason_id": "no-active-advice",
        "evidence_ids": ["advice-scan-terminal-wait"],
    }
    active_advice["clause_set_sha256"] = result_contract.advice_clause_set_sha256(
        active_advice
    )
    evidence["active_advice_clause_set"] = active_advice
    evidence_sha = _canonical_digest(evidence)
    lenses = [
        _derive_lens("goal_value", 1, [_derive_candidate()]),
        _derive_lens("architecture_contract", 2, []),
        _derive_lens("miss_validation", 3, []),
    ]
    for row in lenses:
        row["input_evidence_manifest_sha256"] = evidence_sha
        row["output"]["advice_clause_set_sha256"] = active_advice["clause_set_sha256"]
        row["output_sha256"] = _canonical_digest(row["output"])
    synthesis = {
        "synthesis_agent_id": "terminal-agent-synthesis",
        "synthesis_receipt_id": "terminal-synthesis-receipt",
        "input_evidence_manifest_sha256": evidence_sha,
        "consumed_agent_receipt_ids": [row["agent_receipt_id"] for row in lenses],
        "candidate_union_ids": ["candidate-terminal-wait"],
        "candidate_union_sha256": _canonical_digest(["candidate-terminal-wait"]),
        "selected_candidate_id": "",
        "selection_outcome": "terminal_wait",
        "pack_disposition": "terminal_wait",
        "advice_clause_set_sha256": active_advice["clause_set_sha256"],
        "advice_clause_reconciliation": [],
        "advice_reconciliation_sha256": (
            result_contract.advice_reconciliation_set_sha256([])
        ),
        "synthesis_output_ref": (
            ".task/cycle/cycle-terminal-wait/agent_receipts/terminal-synthesis.json"
        ),
    }
    synthesis["synthesis_output_sha256"] = (
        result_contract.advice_synthesis_output_sha256(synthesis)
    )
    decision_identity = {
        "artifact_id": "artifact-terminal-wait-result",
        "artifact_class": "derive-result",
        "artifact_sha256": "9" * 64,
        "production_lane_identity": "terminal-wait-lane",
        "body_projection_fingerprint": "8" * 64,
        "verification_input_ids": ["terminal-wait-source-cohort"],
        "discovery_basis": "explicit_artifact_ref",
        "scope_verified": True,
    }
    legacy_bridge = {
        "bridge_contract_version": 1,
        "bridge_status": "revision_bound",
        "artifact_id": decision_identity["artifact_id"],
        "artifact_class": decision_identity["artifact_class"],
        "artifact_sha256": decision_identity["artifact_sha256"],
        "revision_id": "terminal-wait-revision-1",
        "subject_digest": decision_identity["artifact_sha256"],
        "lineage_id": "terminal-wait-lineage",
        "freshness_status": "current",
        "evidence_ref": "terminal-wait-bridge-evidence",
        "evidence_sha256": "7" * 64,
    }
    legacy_bridge["receipt_sha256"] = legacy_revision_bridge_sha256(legacy_bridge)
    return {
        "step": "derive",
        "derive_contract_version": 2,
        "cycle_id": "cycle-terminal-wait",
        "decision_contract_version": 0,
        "decision_input_identity": decision_identity,
        "legacy_revision_bridge_receipt": legacy_bridge,
        "verdict_contract_version": 0,
        "agent_routing_applicability": "deterministic_only",
        "finalization_applicability": "not_applicable",
        "finalization_not_applicable_reason": "no-predecessor-attempt",
        "prior_final_attempt_exists": False,
        "transition_kind": "unrelated_state_repair",
        "long_run_state_checked": True,
        "completed_task_id": TASK_ID,
        "next_task_id": None,
        "selected_task_source": "terminal_wait",
        "selected_candidate_id": "",
        "selection_outcome": "terminal_wait",
        "pack_disposition": "terminal_wait",
        "terminal_disposition": "terminal_wait",
        "selected_disposition": "terminal_wait",
        "loop_breaker_disposition": "continue",
        "progress_kind": "goal_productive",
        "semantic_signature": "terminal-wait-owner-integration",
        "terminal_justified": False,
        "hard_stop_required": False,
        "evidence_paths": ["derive-terminal-wait.json"],
        "improvement_analysis_manifest": {
            "schema_version": 1,
            "shared_evidence_manifest": evidence,
            "shared_evidence_manifest_sha256": evidence_sha,
            "lens_results": lenses,
            "synthesis": synthesis,
        },
    }


def _persist_derive_runtime_artifacts(
    root: Path,
    result: dict[str, Any],
) -> None:
    analysis = result["improvement_analysis_manifest"]
    for lens in analysis["lens_results"]:
        _write_canonical_json(
            root / lens["output_ref"],
            result_contract.advice_lens_receipt_projection(lens),
        )
    synthesis = analysis["synthesis"]
    _write_canonical_json(
        root / synthesis["synthesis_output_ref"],
        result_contract.advice_synthesis_output_projection(synthesis),
    )


def _finalize_terminal_derive(
    result: dict[str, Any],
    baseline: dict[str, Any],
    receipt_id: str,
) -> dict[str, Any]:
    analysis = result["improvement_analysis_manifest"]
    result["terminal_wait"] = {
        "selection_epoch": "epoch-terminal-wait",
        "analysis_evidence_manifest_sha256": analysis[
            "shared_evidence_manifest_sha256"
        ],
        "observed_input_manifest_sha256": baseline["observed_input_manifest_sha256"],
        "selection_tick_baseline": baseline,
        "selection_tick_baseline_sha256": _canonical_digest(baseline),
        "wake_predicates": baseline["wake_predicates"],
        "watched_evidence_classes": baseline["watched_evidence_classes"],
        "minimum_material_delta": baseline["minimum_material_delta"],
        "last_selection_receipt": receipt_id,
    }
    return result


def _reseal_tick(packet: dict[str, Any]) -> None:
    body = {key: value for key, value in packet.items() if key != "packet_id"}
    encoded = (
        json.dumps(
            body,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")
    packet["packet_id"] = "selection-tick-" + hashlib.sha256(encoded).hexdigest()[:32]


def _initial_selection_baseline(root: Path) -> tuple[Path, dict[str, Any]]:
    baseline = build_selection_tick(
        root,
        wake_predicates=["verified-exact-subject-or-effective-authority-changed"],
        watched_evidence_classes=["goal_truth", "exact_subject", "authority"],
        minimum_material_delta="one-bound-watched-class-change",
        premise_contract=PREMISE_CONTRACT,
    )
    assert baseline["format_version"] == 2
    assert baseline["status"] == "baseline_recorded"
    path = _write_json(
        root / ".task/cycle/cycle-terminal-wait/selection-tick-initial.json",
        baseline,
    )
    return path, baseline


def _validated_final_derive(
    root: Path,
    baseline: dict[str, Any],
    receipt_id: str,
    suffix: str,
) -> Path:
    result = _derive_result_template()
    _persist_derive_runtime_artifacts(root, result)
    result = _finalize_terminal_derive(result, baseline, receipt_id)
    validation = result_contract.validate(
        "derive",
        result,
        "block",
        {"workspace_root": str(root)},
    )
    assert validation["status"] != "block", validation["findings"]
    return _write_json(
        root / f".task/cycle/cycle-terminal-wait/derive-final-{suffix}.json",
        result,
    )


def _selection_rebase(
    root: Path,
    trigger: dict[str, Any],
    suffix: str,
    *,
    verify_forged_receipt: bool = False,
) -> dict[str, Any]:
    assert trigger["status"] == "selection_required"
    assert trigger["agent_fanout_allowed"] is True
    trigger_path = _write_json(
        root / f".task/cycle/cycle-terminal-wait/selection-trigger-{suffix}.json",
        trigger,
    )
    trigger_binding = _binding(root, trigger_path)

    derive_result = _derive_result_template()
    _persist_derive_runtime_artifacts(root, derive_result)
    selection_synthesis = render_selection_synthesis(root, derive_result)
    synthesis_path = _write_json(
        root / f".task/cycle/cycle-terminal-wait/selection-synthesis-{suffix}.json",
        selection_synthesis,
    )
    decision = render_preliminary_selection_decision(
        root,
        trigger,
        _binding(root, synthesis_path),
    )
    decision_path = _write_json(
        root / f".task/cycle/cycle-terminal-wait/selection-decision-{suffix}.json",
        decision,
    )
    decision_binding = _binding(root, decision_path)

    forged_binding: dict[str, str] | None = None
    if verify_forged_receipt:
        forged_path = _write_json(
            root
            / f".task/cycle/cycle-terminal-wait/forged-selection-receipt-{suffix}.json",
            {
                "receipt_id": "selection-decision-forged",
                "trigger_selection_tick_id": trigger["packet_id"],
                "trigger_selection_tick_sha256": "a" * 64,
            },
        )
        forged_binding = _binding(root, forged_path)
        with pytest.raises(ValueError, match="persisted decision receipt"):
            build_selection_tick(
                root,
                previous=trigger,
                acknowledge_selection_tick_id=trigger["packet_id"],
                selection_receipt_ref=forged_binding["ref"],
                selection_receipt_sha256=forged_binding["sha256"],
            )

    receipt = render_selection_decision_receipt(
        root,
        trigger,
        trigger_binding,
        decision_binding,
    )
    receipt_path = _write_json(
        root / f".task/cycle/cycle-terminal-wait/selection-receipt-{suffix}.json",
        receipt,
    )
    receipt_binding = _binding(root, receipt_path)
    rebased = build_selection_tick(
        root,
        previous=trigger,
        acknowledge_selection_tick_id=trigger["packet_id"],
        selection_receipt_ref=receipt_binding["ref"],
        selection_receipt_sha256=receipt_binding["sha256"],
    )
    assert rebased["status"] == "baseline_recorded"
    assert rebased["baseline_rebased"] is True
    assert rebased["selection_acknowledgement_status"] == "accepted"
    acknowledgement = rebased["selection_acknowledgement_binding"]
    assert acknowledgement["selection_receipt_id"] == receipt["receipt_id"]
    assert acknowledgement["selection_receipt_ref"] == receipt_binding["ref"]
    assert acknowledgement["selection_receipt_sha256"] == receipt_binding["sha256"]
    validate_selection_packet(rebased, root=root)

    if forged_binding is not None:
        forged_rebased = copy.deepcopy(rebased)
        forged_rebased["selection_acknowledgement_binding"]["selection_receipt_ref"] = (
            forged_binding["ref"]
        )
        forged_rebased["selection_acknowledgement_binding"][
            "selection_receipt_sha256"
        ] = forged_binding["sha256"]
        _reseal_tick(forged_rebased)
        with pytest.raises(ValueError, match="decision receipt is invalid"):
            validate_selection_packet(forged_rebased, root=root)

    baseline_path = _write_json(
        root / f".task/cycle/cycle-terminal-wait/selection-tick-baseline-{suffix}.json",
        rebased,
    )
    final_derive_path = _validated_final_derive(
        root,
        rebased,
        str(receipt["receipt_id"]),
        suffix,
    )
    return {
        "baseline_path": baseline_path,
        "derive_path": final_derive_path,
        "preliminary_decision_path": decision_path,
        "baseline": rebased,
        "receipt_binding": receipt_binding,
    }


def _authority_inputs(
    root: Path,
    subject: dict[str, str],
    policy: Path,
    goal: Path,
    suffix: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    grant_id = f"grant-terminal-wait-owner-{suffix}"
    lineage_id = f"lineage-terminal-wait-owner-{suffix}"
    operation = _operation()
    request: dict[str, Any] = {
        "schema_version": 2,
        "request_kind": "authority_operation",
        "request_id": f"request-terminal-wait-owner-{suffix}",
        **operation,
        "cycle_id": f"cycle-terminal-wait-owner-{suffix}",
        "task_id": TASK_ID,
        "pack_id": None,
        "attempt_id": f"attempt-terminal-wait-owner-{suffix}",
        "actor_rank": "S0",
        "subject": subject,
        "required_capabilities": ["cycle.terminal_wait_baseline.publish"],
        "effect_class": "publish_terminal_wait_baseline_binding",
        "data_class": "workflow_metadata",
        "mutation_class": "local_mutation",
        "reversibility": "conditionally_reversible",
        "risk_tier": "R1",
        "decision_class": "D3",
        "intent_type": "grant_authority",
        "cardinality_requested": "single_use",
        "use_budget_requested": 1,
        "idempotency_key": f"request-terminal-wait-owner-{suffix}-key",
        "context": {
            "external_input_status": "not_required",
            "goal_truth_status": "aligned",
            "risk_acceptance_status": "not_required",
            "design_selection_status": "not_required",
            "external_input_evidence": None,
            "risk_acceptance_evidence": None,
            "design_selection_evidence": None,
        },
        "composition_receipt": None,
    }
    context = {
        "schema_version": 2,
        "context_kind": "authority_evaluation",
        "session_ceiling": {
            "capabilities": ["cycle.terminal_wait_baseline.publish"],
            "risk_ceiling": "R1",
            "mutation_classes": ["local_mutation"],
            "evidence_id": f"session-terminal-wait-owner-{suffix}",
        },
        "goal_autonomy_envelope": {
            "envelope_id": f"envelope-terminal-wait-owner-{suffix}",
            "capabilities": ["cycle.terminal_wait_baseline.publish"],
            "risk_ceiling": "R1",
            "decision_classes": ["D3"],
            "subjects": [subject["digest"]],
            "operations": [":".join(operation.values())],
            "source_binding": _binding(root, goal),
        },
    }
    policy_binding = snapshot_file(root, policy.relative_to(root).as_posix(), "policy")
    approval_path = _write_json(
        root / f".task/authorization/source-terminal-wait-owner-{suffix}.json",
        {
            "schema_version": 2,
            "artifact_kind": "authority_source_approval",
            "approval_id": f"approval-terminal-wait-owner-{suffix}",
            "source_kind": "explicit_user_instruction",
            "source_rank": "S3",
            "decision_type": "grant_authority",
            "capabilities": [
                "authority.grant.issue",
                "cycle.terminal_wait_baseline.publish",
            ],
            "subjects": [subject],
            "operations": [operation],
            "risk_ceiling": "R1",
            "decision_classes": ["D3"],
            "cardinalities": ["single_use"],
            "max_uses": 1,
            "grant_ids": [grant_id],
            "request_digests": [],
            "lineage_ids": [lineage_id],
            "delegation_binding": None,
            "not_before": AT,
            "expires_at": EXPIRES_AT,
            "evidence_id": f"instruction-terminal-wait-owner-{suffix}",
            "integrity_status": "verified",
        },
    )
    source_binding = snapshot_file(
        root, approval_path.relative_to(root).as_posix(), "source_approval"
    )
    register_grant(
        root,
        {
            "schema_version": 2,
            "artifact_kind": "authority_grant",
            "grant_id": grant_id,
            "lineage_id": lineage_id,
            "parent_grant_id": None,
            "issuer_rank": "S3",
            "holder_rank": "S0",
            "capabilities": ["cycle.terminal_wait_baseline.publish"],
            "subjects": [subject],
            "operations": [operation],
            "risk_ceiling": "R1",
            "decision_classes": ["D3"],
            "cardinality": "single_use",
            "max_uses": 1,
            "not_before": AT,
            "expires_at": EXPIRES_AT,
            "session_id": None,
            "task_id": TASK_ID,
            "improvement_id": None,
            "source_approval": source_binding,
            "policy_snapshot": policy_binding,
            "created_at": AT,
            "idempotency_key": f"grant-terminal-wait-owner-{suffix}-key",
        },
    )
    return request, context


def _publish_terminal_baseline(
    root: Path,
    source_core: dict[str, Any],
    policy: Path,
    goal: Path,
    suffix: str,
    capsys: pytest.CaptureFixture[str],
) -> dict[str, Any]:
    materialized = materialize_terminal_wait_authority_subject(root, source_core)
    subject = materialized["authority_subject"]
    subject_binding = materialized["authority_subject_binding"]
    assert subject["digest"] == subject_binding["sha256"]
    assert subject["ref"] == subject_binding["ref"]
    assert materialized["prepare_only"] is True

    request, context = _authority_inputs(root, subject, policy, goal, suffix)
    decision = evaluate(
        root,
        request,
        context,
        evaluated_at=AT,
        skills_root=SKILLS_ROOT,
    )
    assert decision["decision"] == "allowed"
    decision_path = (
        root / ".task/authorization/decisions" / f"{decision['decision_id']}.json"
    )
    decision_sha = write_immutable_json(
        decision_path,
        decision,
        "terminal-wait owner integration decision",
    )
    decision_binding = _binding(root, decision_path)
    assert decision_binding["sha256"] == decision_sha

    reserved = reserve(
        root,
        decision_binding["ref"],
        decision_binding["sha256"],
        reserved_at=PRE_DISPATCH_AT,
        idempotency_key=f"reservation-terminal-wait-owner-{suffix}-key",
        skills_root=SKILLS_ROOT,
    )
    assert (
        command_verify(
            argparse.Namespace(
                root=str(root),
                reservation_ref=reserved["reservation_ref"],
                reservation_sha256=reserved["reservation_sha256"],
                at=PRE_DISPATCH_AT,
                expected_version=0,
                skills_root=str(SKILLS_ROOT),
                stage="pre_dispatch",
            )
        )
        == 0
    )
    pre_dispatch = _capture_json(capsys)
    authority_packet = build_authority_packet(
        root,
        decision_binding,
        reservation_binding={
            "ref": reserved["reservation_ref"],
            "sha256": reserved["reservation_sha256"],
        },
        verification_binding={
            "ref": pre_dispatch["verification_ref"],
            "sha256": pre_dispatch["verification_sha256"],
        },
    )
    assert authority_packet["subject"] == subject
    packet_path = _write_json(
        root / f".task/cycle/cycle-terminal-wait/authority-packet-{suffix}.json",
        authority_packet,
    )

    assert (
        command_verify(
            argparse.Namespace(
                root=str(root),
                reservation_ref=reserved["reservation_ref"],
                reservation_sha256=reserved["reservation_sha256"],
                at=PRE_COMMIT_AT,
                expected_version=0,
                skills_root=str(SKILLS_ROOT),
                stage="pre_commit",
            )
        )
        == 0
    )
    pre_commit = _capture_json(capsys)
    consume_key = f"terminal-wait-baseline:{TASK_ID}:{suffix}:consume"
    plan = {
        **source_core,
        "artifact_kind": "terminal_wait_baseline_plan",
        "authority_subject": subject_binding,
        "authority_packet": _binding(root, packet_path),
        "pre_commit_verification": {
            "ref": pre_commit["verification_ref"],
            "sha256": pre_commit["verification_sha256"],
        },
        "consume_idempotency_key": consume_key,
        "prepared_at": PRE_COMMIT_AT,
    }
    prepared = prepare_terminal_wait_baseline(root, plan)
    assert prepared["status"] == "pending_settlement"
    assert prepared["current_pointer_exposed"] is False
    assert (
        prepared["authority_consume"]["reservation_id"]
        == (reserved["reservation"]["reservation_id"])
    )
    assert (
        command_consume(
            argparse.Namespace(
                root=str(root),
                reservation_ref=reserved["reservation_ref"],
                reservation_sha256=reserved["reservation_sha256"],
                execution_result=json.dumps(prepared["execution_result"]),
                at=CONSUMED_AT,
                expected_version=0,
                idempotency_key=consume_key,
                skills_root=str(SKILLS_ROOT),
            )
        )
        == 0
    )
    consumed = _capture_json(capsys)
    assert consumed["status"] == "consumed"

    activated = activate_terminal_wait_baseline(
        root,
        prepared["execution_result"],
        {"ref": consumed["ref"], "sha256": consumed["sha256"]},
    )
    assert activated["status"] == "active"
    assert activated["current_pointer_exposed"] is True
    resolved = resolve_terminal_wait_baseline(root)
    assert resolved["binding_id"] == prepared["binding_id"]
    assert resolved["authority_subject"] == subject_binding
    return {
        "materialized": materialized,
        "prepared": prepared,
        "activated": activated,
        "resolved": resolved,
    }


def _source_core(
    root: Path,
    task: Path,
    baseline_path: Path,
    derive_path: Path,
    expected_current_snapshot_sha256: str | None,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "artifact_kind": "terminal_wait_baseline_authority_subject",
        "task": {"task_id": TASK_ID, **_binding(root, task)},
        "source_derive": _binding(root, derive_path),
        "transition_evidence": None,
        "selection_baseline": _binding(root, baseline_path),
        "expected_current_snapshot_sha256": expected_current_snapshot_sha256,
    }


def test_real_owner_terminal_wait_publication_settles_exact_authority_lifecycle(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    task = _write(
        tmp_path / "task.md",
        "# Task\n\n- Status: `completed`\n- Executable: `false`\n- Task Pack: `none`\n",
    )
    policy = _write(
        tmp_path / ".agent_goal/agent_authority.md",
        "# Authority\n\nBounded terminal-wait baseline publication.\n",
    )
    goal = _write(
        tmp_path / ".agent_goal/goal_architecture.md",
        "# Goal Architecture\n\n- concept_id: concept-terminal-wait-v1\n",
    )

    initial_baseline_path, initial_baseline = _initial_selection_baseline(tmp_path)
    initial_derive_path = _validated_final_derive(
        tmp_path,
        initial_baseline,
        "initial-terminal-wait-selection",
        "initial",
    )
    initial_core = _source_core(
        tmp_path,
        task,
        initial_baseline_path,
        initial_derive_path,
        None,
    )
    assert not (tmp_path / ".task/terminal_wait_baseline/current.json").exists()
    initial_publication = _publish_terminal_baseline(
        tmp_path,
        initial_core,
        policy,
        goal,
        "initial",
        capsys,
    )
    predecessor_snapshot_sha256 = initial_publication["prepared"]["snapshot"]["sha256"]
    assert (
        initial_publication["resolved"]["selection_baseline"]["packet_id"]
        == (initial_baseline["packet_id"])
    )

    _write(
        goal,
        "# Goal Architecture\n\n- concept_id: concept-terminal-wait-v2\n",
    )
    trigger = build_selection_tick(tmp_path, previous=initial_baseline)
    real = _selection_rebase(
        tmp_path,
        trigger,
        "real",
        verify_forged_receipt=True,
    )
    real_core = _source_core(
        tmp_path,
        task,
        real["baseline_path"],
        real["derive_path"],
        predecessor_snapshot_sha256,
    )

    preliminary_core = {
        **real_core,
        "source_derive": _binding(tmp_path, real["preliminary_decision_path"]),
    }
    with pytest.raises(ValueError, match="rebased source derive contract failed"):
        materialize_terminal_wait_authority_subject(tmp_path, preliminary_core)

    forged_trigger = copy.deepcopy(trigger)
    forged_trigger["previous_input_manifest_sha256"] = "0" * 64
    _reseal_tick(forged_trigger)
    forged_trigger_rebase = _selection_rebase(
        tmp_path,
        forged_trigger,
        "forged-trigger",
    )
    forged_trigger_core = _source_core(
        tmp_path,
        task,
        forged_trigger_rebase["baseline_path"],
        forged_trigger_rebase["derive_path"],
        predecessor_snapshot_sha256,
    )
    with pytest.raises(ValueError, match="does not descend from the predecessor"):
        materialize_terminal_wait_authority_subject(tmp_path, forged_trigger_core)

    forged_rebased = copy.deepcopy(real["baseline"])
    forged_rebased["previous_input_manifest_sha256"] = initial_baseline[
        "observed_input_manifest_sha256"
    ]
    _reseal_tick(forged_rebased)
    forged_rebased_path = _write_json(
        tmp_path
        / ".task/cycle/cycle-terminal-wait/selection-tick-baseline-forged-c.json",
        forged_rebased,
    )
    receipt_id = forged_rebased["selection_acknowledgement_binding"][
        "selection_receipt_id"
    ]
    forged_rebased_derive_path = _validated_final_derive(
        tmp_path,
        forged_rebased,
        receipt_id,
        "forged-c",
    )
    forged_rebased_core = _source_core(
        tmp_path,
        task,
        forged_rebased_path,
        forged_rebased_derive_path,
        predecessor_snapshot_sha256,
    )
    with pytest.raises(ValueError, match="does not descend from its trigger"):
        materialize_terminal_wait_authority_subject(tmp_path, forged_rebased_core)

    final_publication = _publish_terminal_baseline(
        tmp_path,
        real_core,
        policy,
        goal,
        "rebased",
        capsys,
    )
    resolved = final_publication["resolved"]
    assert resolved["selection_baseline"]["packet_id"] == real["baseline"]["packet_id"]
    assert resolved["predecessor_snapshot_sha256"] == predecessor_snapshot_sha256
    current_tick = current_selection_tick_packet(tmp_path)
    assert current_tick is not None
    assert (
        current_tick["selection_acknowledgement_binding"]["selection_receipt_ref"]
        == real["receipt_binding"]["ref"]
    )

    audit = audit_terminal_wait_baseline(tmp_path)
    assert audit["status"] == "ok"
    assert audit["findings"] == []
    assert audit["artifact_counts"] == {
        "subjects": 2,
        "prepares": 2,
        "snapshots": 2,
        "completions": 2,
        "activations": 2,
    }
