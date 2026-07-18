from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

from manage_agent_authority.artifact_store import register_grant
from manage_agent_authority.artifact_store import snapshot_file
from manage_agent_authority.authority_cli import command_verify
from manage_agent_authority.canonical import sha256_file
from manage_agent_authority.canonical import write_immutable_json
from manage_agent_authority.evaluator import evaluate
from manage_agent_authority.lifecycle import reserve
from orchestrate_task_cycle.authority_boundary import project_authority_packet
from orchestrate_task_cycle.authority_packet import build_authority_packet
from orchestrate_task_cycle.result_contract.api import validate


AT = "2026-07-18T00:00:00+00:00"
PRE_DISPATCH_AT = "2026-07-18T00:01:00+00:00"
EXPIRES_AT = "2026-07-18T01:00:00+00:00"


def _write(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def _write_json(path: Path, value: dict[str, object]) -> Path:
    return _write(path, json.dumps(value, indent=2, sort_keys=True) + "\n")


def _operation() -> dict[str, str]:
    return {
        "skill_id": "owner-packet-integration",
        "skill_version": "1.0.0",
        "operation_id": "apply_bounded_change",
        "operation_version": "1",
    }


def _request(subject: dict[str, str]) -> dict[str, object]:
    return {
        "schema_version": 2,
        "request_kind": "authority_operation",
        "request_id": "request-owner-packet-integration",
        **_operation(),
        "cycle_id": "cycle-owner-packet-integration",
        "task_id": "task-owner-packet-integration",
        "pack_id": None,
        "attempt_id": "attempt-owner-packet-integration",
        "actor_rank": "S0",
        "subject": subject,
        "required_capabilities": ["implementation.local.edit"],
        "effect_class": "edit_local",
        "data_class": "repository_code",
        "mutation_class": "local_mutation",
        "reversibility": "conditionally_reversible",
        "risk_tier": "R1",
        "decision_class": "D3",
        "intent_type": "grant_authority",
        "cardinality_requested": "single_use",
        "use_budget_requested": 1,
        "idempotency_key": "owner-packet-request-key",
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


def _setup_owner(root: Path) -> tuple[dict[str, object], dict[str, object], Path]:
    policy = _write(root / ".agent_goal/agent_authority.md", "# Authority\n")
    goal = _write(root / ".agent_goal/goal_architecture.md", "# Goal\n")
    task = _write(root / ".task/task.md", "# Exact task subject\n")
    subject = {
        "kind": "task",
        "ref": ".task/task.md",
        "digest": sha256_file(task),
        "revision": "revision-owner-packet-integration",
    }
    request = _request(subject)
    skills_root = root / "test-skills"
    _write_json(
        skills_root / "owner-packet-integration/authority.operations.json",
        {
            "schema_version": 2,
            "manifest_kind": "authority_operations",
            "skill_id": "owner-packet-integration",
            "skill_version": "1.0.0",
            "operations": [
                {
                    "operation_id": "apply_bounded_change",
                    "operation_version": "1",
                    "mutation_class": "local_mutation",
                    "required_capabilities": ["implementation.local.edit"],
                    "source_rank_floor": "S1",
                    "risk_floor": "R1",
                    "decision_class": "D3",
                    "effect_classes": ["edit_local"],
                    "data_classes": ["repository_code"],
                    "reversibility": "conditionally_reversible",
                    "subject_kinds": ["task"],
                    "authority_applicability": "required",
                    "authorization_mechanism": "grant",
                }
            ],
        },
    )
    policy_binding = snapshot_file(root, str(policy.relative_to(root)), "policy")
    approval = _write_json(
        root / ".task/authorization/root-source.json",
        {
            "schema_version": 2,
            "artifact_kind": "authority_source_approval",
            "approval_id": "approval-owner-packet-integration",
            "source_kind": "explicit_user_instruction",
            "source_rank": "S3",
            "decision_type": "grant_authority",
            "capabilities": [
                "authority.grant.issue",
                "implementation.local.edit",
            ],
            "subjects": [subject],
            "operations": [_operation()],
            "risk_ceiling": "R1",
            "decision_classes": ["D3"],
            "cardinalities": ["single_use"],
            "max_uses": 1,
            "grant_ids": ["grant-owner-packet-integration"],
            "request_digests": [],
            "lineage_ids": ["lineage-owner-packet-integration"],
            "delegation_binding": None,
            "not_before": AT,
            "expires_at": EXPIRES_AT,
            "evidence_id": "user-owner-packet-integration",
            "integrity_status": "verified",
        },
    )
    source_binding = snapshot_file(
        root, str(approval.relative_to(root)), "source_approval"
    )
    register_grant(
        root,
        {
            "schema_version": 2,
            "artifact_kind": "authority_grant",
            "grant_id": "grant-owner-packet-integration",
            "lineage_id": "lineage-owner-packet-integration",
            "parent_grant_id": None,
            "issuer_rank": "S3",
            "holder_rank": "S0",
            "capabilities": ["implementation.local.edit"],
            "subjects": [subject],
            "operations": [_operation()],
            "risk_ceiling": "R1",
            "decision_classes": ["D3"],
            "cardinality": "single_use",
            "max_uses": 1,
            "not_before": AT,
            "expires_at": EXPIRES_AT,
            "session_id": None,
            "task_id": "task-owner-packet-integration",
            "improvement_id": None,
            "source_approval": source_binding,
            "policy_snapshot": policy_binding,
            "created_at": AT,
            "idempotency_key": "owner-packet-grant-key",
        },
    )
    operation_key = ":".join(_operation().values())
    context = {
        "schema_version": 2,
        "context_kind": "authority_evaluation",
        "session_ceiling": {
            "capabilities": ["implementation.local.edit"],
            "risk_ceiling": "R1",
            "mutation_classes": ["local_mutation"],
            "evidence_id": "session-owner-packet-integration",
        },
        "goal_autonomy_envelope": {
            "envelope_id": "envelope-owner-packet-integration",
            "capabilities": ["implementation.local.edit"],
            "risk_ceiling": "R1",
            "decision_classes": ["D3"],
            "subjects": [subject["digest"]],
            "operations": [operation_key],
            "source_binding": {
                "ref": str(goal.relative_to(root)),
                "sha256": sha256_file(goal),
            },
        },
    }
    return request, context, skills_root


def test_real_owner_allowed_mutation_builds_verified_orchestrator_packet(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    request, context, skills_root = _setup_owner(tmp_path)
    decision = evaluate(
        tmp_path,
        request,
        context,
        evaluated_at=AT,
        skills_root=skills_root,
    )
    assert decision["decision"] == "allowed"
    decision_path = (
        tmp_path / ".task/authorization/decisions" / f"{decision['decision_id']}.json"
    )
    decision_sha = write_immutable_json(
        decision_path, decision, "owner integration decision"
    )
    reserved = reserve(
        tmp_path,
        str(decision_path.relative_to(tmp_path)),
        decision_sha,
        reserved_at=PRE_DISPATCH_AT,
        idempotency_key="owner-packet-reservation-key",
        skills_root=skills_root,
    )
    command_verify(
        argparse.Namespace(
            root=str(tmp_path),
            reservation_ref=reserved["reservation_ref"],
            reservation_sha256=reserved["reservation_sha256"],
            at=PRE_DISPATCH_AT,
            expected_version=0,
            skills_root=str(skills_root),
            stage="pre_dispatch",
        )
    )
    verify_output = json.loads(capsys.readouterr().out)

    packet = build_authority_packet(
        tmp_path,
        {
            "ref": str(decision_path.relative_to(tmp_path)),
            "sha256": decision_sha,
        },
        reservation_binding={
            "ref": reserved["reservation_ref"],
            "sha256": reserved["reservation_sha256"],
        },
        verification_binding={
            "ref": verify_output["verification_ref"],
            "sha256": verify_output["verification_sha256"],
        },
    )

    assert project_authority_packet(packet).valid
    assert packet["decision_binding"]["decision"] == "allowed"
    assert packet["reservation_binding"]["status"] == "reserved"
    assert packet["dispatch_preflight"]["stage"] == "pre_dispatch"
    assert (
        validate(
            "authority",
            packet,
            "block",
            {"workspace_root": str(tmp_path)},
        )["status"]
        == "ok"
    )
