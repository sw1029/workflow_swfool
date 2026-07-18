from __future__ import annotations

import argparse
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
from orchestrate_task_cycle.task_pack.legacy_retirement_commands import (
    command_activate_legacy_retirement,
    command_retire_legacy,
)
from orchestrate_task_cycle.task_pack.legacy_retirement_contract import (
    REASON_CODE,
)
from orchestrate_task_cycle.task_pack.legacy_retirement_validation import (
    validate_activation_binding,
)
from orchestrate_task_cycle.task_pack.presentation import (
    _command_status_locked,
    _command_validate_locked,
)
from orchestrate_task_cycle.task_pack.storage import canonical_pack_sha256
from orchestrate_task_cycle.task_pack.store import task_pack_store_findings
from orchestrate_task_cycle.task_pack.validation import validate_pack


SKILLS_ROOT = Path(__file__).resolve().parents[2]
AT = "2026-07-18T00:00:00+00:00"
PRE_DISPATCH_AT = "2026-07-18T00:01:00+00:00"
PRE_COMMIT_AT = "2026-07-18T00:02:00+00:00"
CONSUMED_AT = "2026-07-18T00:03:00+00:00"
EXPIRES_AT = "2026-07-18T01:00:00+00:00"
PACK_ID = "pack-owner-retirement-integration"
TASK_ID = "task-owner-retirement-integration"
GRANT_ID = "grant-owner-retirement-integration"
LINEAGE_ID = "lineage-owner-retirement-integration"
CONSUME_KEY = f"task-pack-retire:{PACK_ID}:authority-consume"


def _write(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def _write_json(path: Path, value: dict[str, Any]) -> Path:
    return _write(
        path,
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )


def _binding(root: Path, path: Path) -> dict[str, str]:
    return {
        "ref": path.relative_to(root).as_posix(),
        "sha256": sha256_file(path),
    }


def _operation() -> dict[str, str]:
    return {
        "skill_id": "orchestrate-task-cycle",
        "skill_version": "2.0.0",
        "operation_id": "mutate_task_topology",
        "operation_version": "1",
    }


def _legacy_pack() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "pack_id": PACK_ID,
        "status": "completed",
        "goal": "Historical topology contract.",
        "current_item_id": None,
        "items": [
            {
                "item_id": "item-owner-retirement-integration",
                "order": 1,
                "status": "consumed",
                "title": "Historical item",
                "objective": "Preserve the historical record without a new claim.",
                "acceptance": ["The original bytes remain immutable."],
                "validation_profile": "current_only",
                "progress_target": "advanced",
            }
        ],
        "mutation_log": [],
    }


def _setup_workspace(
    root: Path,
) -> tuple[Path, dict[str, Any], dict[str, Any], dict[str, Any]]:
    _write(
        root / "task.md",
        "# Task\n\n- Status: `completed`\n- Executable: `false`\n- Task Pack: `none`\n",
    )
    policy = _write(
        root / ".agent_goal/agent_authority.md",
        "# Authority\n\nBounded task-topology migration.\n",
    )
    goal = _write(
        root / ".agent_goal/goal_architecture.md",
        "# Goal Architecture\n\n- concept_id: concept-owner-retirement\n",
    )
    pack = _legacy_pack()
    pack_path = _write_json(root / f".task/task_pack/{PACK_ID}.json", pack)
    raw_findings = validate_pack(pack, pack_path)
    assert any(row.get("severity") == "block" for row in raw_findings)

    subject = {
        "kind": "task_pack",
        "ref": pack_path.relative_to(root).as_posix(),
        "digest": sha256_file(pack_path),
        "revision": PACK_ID,
    }
    request: dict[str, Any] = {
        "schema_version": 2,
        "request_kind": "authority_operation",
        "request_id": "request-owner-retirement-integration",
        **_operation(),
        "cycle_id": "cycle-owner-retirement-integration",
        "task_id": TASK_ID,
        "pack_id": PACK_ID,
        "attempt_id": "attempt-owner-retirement-integration",
        "actor_rank": "S0",
        "subject": subject,
        "required_capabilities": ["cycle.task_topology.mutate"],
        "effect_class": "insert_delete_reorder_task",
        "data_class": "task_topology",
        "mutation_class": "local_mutation",
        "reversibility": "conditionally_reversible",
        "risk_tier": "R2",
        "decision_class": "D2",
        "intent_type": "grant_authority",
        "cardinality_requested": "single_use",
        "use_budget_requested": 1,
        "idempotency_key": "request-owner-retirement-integration-key",
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
            "capabilities": ["cycle.task_topology.mutate"],
            "risk_ceiling": "R2",
            "mutation_classes": ["local_mutation"],
            "evidence_id": "session-owner-retirement-integration",
        },
        "goal_autonomy_envelope": {
            "envelope_id": "envelope-owner-retirement-integration",
            "capabilities": ["cycle.task_topology.mutate"],
            "risk_ceiling": "R2",
            "decision_classes": ["D2"],
            "subjects": [subject["digest"]],
            "operations": [":".join(_operation().values())],
            "source_binding": _binding(root, goal),
        },
    }
    policy_binding = snapshot_file(root, policy.relative_to(root).as_posix(), "policy")
    approval = _write_json(
        root / ".task/authorization/source-owner-retirement.json",
        {
            "schema_version": 2,
            "artifact_kind": "authority_source_approval",
            "approval_id": "approval-owner-retirement-integration",
            "source_kind": "explicit_user_instruction",
            "source_rank": "S3",
            "decision_type": "grant_authority",
            "capabilities": [
                "authority.grant.issue",
                "cycle.task_topology.mutate",
            ],
            "subjects": [subject],
            "operations": [_operation()],
            "risk_ceiling": "R2",
            "decision_classes": ["D2"],
            "cardinalities": ["single_use"],
            "max_uses": 1,
            "grant_ids": [GRANT_ID],
            "request_digests": [],
            "lineage_ids": [LINEAGE_ID],
            "delegation_binding": None,
            "not_before": AT,
            "expires_at": EXPIRES_AT,
            "evidence_id": "instruction-owner-retirement-integration",
            "integrity_status": "verified",
        },
    )
    source_binding = snapshot_file(
        root, approval.relative_to(root).as_posix(), "source_approval"
    )
    register_grant(
        root,
        {
            "schema_version": 2,
            "artifact_kind": "authority_grant",
            "grant_id": GRANT_ID,
            "lineage_id": LINEAGE_ID,
            "parent_grant_id": None,
            "issuer_rank": "S3",
            "holder_rank": "S0",
            "capabilities": ["cycle.task_topology.mutate"],
            "subjects": [subject],
            "operations": [_operation()],
            "risk_ceiling": "R2",
            "decision_classes": ["D2"],
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
            "idempotency_key": "grant-owner-retirement-integration-key",
        },
    )
    return pack_path, pack, request, context


def _capture_json(capsys: pytest.CaptureFixture[str]) -> dict[str, Any]:
    return json.loads(capsys.readouterr().out)


def test_real_owner_legacy_retirement_settles_and_preserves_history(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    pack_path, pack, request, context = _setup_workspace(tmp_path)
    original_pack_bytes = pack_path.read_bytes()

    decision = evaluate(
        tmp_path,
        request,
        context,
        evaluated_at=AT,
        skills_root=SKILLS_ROOT,
    )
    assert decision["decision"] == "allowed"
    assert (decision["operation_manifest"] or {})["ref"] == (
        "orchestrate-task-cycle/authority.operations.json"
    )
    decision_path = (
        tmp_path / ".task/authorization/decisions" / f"{decision['decision_id']}.json"
    )
    decision_sha = write_immutable_json(
        decision_path, decision, "legacy retirement owner integration decision"
    )
    decision_binding = _binding(tmp_path, decision_path)
    assert decision_binding["sha256"] == decision_sha

    reserved = reserve(
        tmp_path,
        decision_binding["ref"],
        decision_binding["sha256"],
        reserved_at=PRE_DISPATCH_AT,
        idempotency_key="reservation-owner-retirement-integration-key",
        skills_root=SKILLS_ROOT,
    )
    assert (
        command_verify(
            argparse.Namespace(
                root=str(tmp_path),
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
    packet = build_authority_packet(
        tmp_path,
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
    packet_path = _write_json(
        tmp_path / ".task/cycle/authority-owner-retirement.json", packet
    )
    packet_binding = _binding(tmp_path, packet_path)

    assert (
        command_verify(
            argparse.Namespace(
                root=str(tmp_path),
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
    plan = {
        "schema_version": 1,
        "artifact_kind": "legacy_task_pack_retirement_plan",
        "source_pack": {
            "ref": pack_path.relative_to(tmp_path).as_posix(),
            "file_sha256": sha256_file(pack_path),
            "canonical_pack_sha256": canonical_pack_sha256(pack),
            "pack_id": PACK_ID,
        },
        "task_binding": _binding(tmp_path, tmp_path / "task.md"),
        "authority_packet": packet_binding,
        "pre_commit_verification": {
            "ref": pre_commit["verification_ref"],
            "sha256": pre_commit["verification_sha256"],
        },
        "consume_idempotency_key": CONSUME_KEY,
        "prepared_at": PRE_COMMIT_AT,
        "reason_code": REASON_CODE,
    }
    assert (
        command_retire_legacy(
            argparse.Namespace(root=str(tmp_path), plan=json.dumps(plan), dry_run=False)
        )
        == 0
    )
    retired = _capture_json(capsys)
    assert retired["status"] == "pending_settlement"
    assert retired["authority_consume"] == {
        "reservation_id": reserved["reservation"]["reservation_id"],
        "idempotency_key": CONSUME_KEY,
        "execution_result": retired["execution_result"],
    }
    assert pack_path.read_bytes() == original_pack_bytes
    assert task_pack_store_findings(tmp_path)

    assert (
        command_consume(
            argparse.Namespace(
                root=str(tmp_path),
                reservation_ref=reserved["reservation_ref"],
                reservation_sha256=reserved["reservation_sha256"],
                execution_result=json.dumps(retired["execution_result"]),
                at=CONSUMED_AT,
                expected_version=0,
                idempotency_key=CONSUME_KEY,
                skills_root=str(SKILLS_ROOT),
            )
        )
        == 0
    )
    consumed = _capture_json(capsys)
    assert consumed["status"] == "consumed"

    assert (
        command_activate_legacy_retirement(
            argparse.Namespace(
                root=str(tmp_path),
                completion_ref=retired["execution_result"]["ref"],
                completion_sha256=retired["execution_result"]["sha256"],
                use_receipt_ref=consumed["ref"],
                use_receipt_sha256=consumed["sha256"],
            )
        )
        == 0
    )
    activated = _capture_json(capsys)
    assert activated["status"] == "active"
    assert activated["raw_findings_preserved"] is True
    assert pack_path.read_bytes() == original_pack_bytes
    assert task_pack_store_findings(tmp_path) == []

    historical_activation, historical_overlay, historical_plan = (
        validate_activation_binding(
            tmp_path, activated["activation"], phase="historical"
        )
    )
    assert historical_activation["authority_use_receipt"] == {
        "ref": consumed["ref"],
        "sha256": consumed["sha256"],
    }
    assert historical_overlay["non_claims"]["historical_authority_pass"] is False
    assert historical_plan == plan

    assert _command_status_locked(tmp_path) == 0
    status = _capture_json(capsys)
    assert status["status"] == "not_applicable"
    assert status["legacy_retired_pack_count"] == 1
    assert status["closed_packs"][0]["operational_disposition"] == "retired_legacy"

    assert (
        _command_validate_locked(
            tmp_path, argparse.Namespace(pack=None, strict_findings=False)
        )
        == 0
    )
    report = _capture_json(capsys)
    assert report["status"] == "ok"
    assert report["raw_finding_count"] > 0
    assert report["results"][0]["raw_status"] == "block"
    assert report["results"][0]["operational_status"] == "retired_legacy"
    assert pack_path.read_bytes() == original_pack_bytes
