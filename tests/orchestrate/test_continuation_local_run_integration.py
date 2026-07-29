from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil

from authority_historical_fixture_support import (
    register_historical_grant,
    snapshot_historical_source,
)
from compiler_first_fixture_support import append_fixture_event
from manage_agent_authority.artifact_store import snapshot_file
from manage_agent_authority.authority_cli import command_verify
from manage_agent_authority.canonical import (
    sha256_file,
    write_immutable_json,
)
from manage_agent_authority.evaluator import evaluate
from manage_agent_authority.lifecycle import reserve
from orchestrate_task_cycle.authority_packet import (
    build_authority_packet,
    publish_authority_packet,
)
from orchestrate_task_cycle.continuation.local_run_dispatch import (
    _OPERATION,
    _authority_packet,
    _sealed_authority_projection,
)
from orchestrate_task_cycle.cycle_ledger import init_cycle
from orchestrate_task_cycle.ledger.compiled_events import (
    append_compiled_system_stage,
)
from orchestrate_task_cycle.stage.input_compilers import publish_owner_result
from orchestrate_task_cycle.stage.preparation_store import publish_preparation
from orchestrate_task_cycle.stage.service import (
    advance_stage,
    prepare_stage,
    submit_stage,
)
from orchestrate_task_cycle.transition.constants import ORDER


AT = "2026-07-29T00:00:00+00:00"
VERIFY_AT = "2026-07-29T00:01:00+00:00"
EXPIRY = "2026-07-29T01:00:00+00:00"
CYCLE = "cycle-local-long-run"
TASK = "task-local-long-run"
SESSION = "session-local-long-run"


def _write(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def _write_json(path: Path, value: dict[str, object]) -> Path:
    return _write(path, json.dumps(value, indent=2, sort_keys=True) + "\n")


def _request(subject: dict[str, str]) -> dict[str, object]:
    return {
        "schema_version": 2,
        "request_kind": "authority_operation",
        "request_id": "request-local-long-run",
        **_OPERATION,
        "cycle_id": CYCLE,
        "task_id": TASK,
        "pack_id": None,
        "attempt_id": "attempt-local-long-run",
        "actor_rank": "S0",
        "subject": subject,
        "required_capabilities": ["execution.local.long_run"],
        "effect_class": "run_long",
        "data_class": "runtime_state",
        "mutation_class": "local_mutation",
        "reversibility": "conditionally_reversible",
        "risk_tier": "R2",
        "decision_class": "D3",
        "intent_type": "grant_authority",
        "cardinality_requested": "single_use",
        "use_budget_requested": 1,
        "reservation_units": 1,
        "idempotency_key": "request-key-local-long-run",
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


def _authority(
    root: Path, capsys,
) -> dict[str, object]:
    policy = _write(root / ".agent_goal/agent_authority.md", "# Authority\n")
    goal = _write(root / ".agent_goal/goal_architecture.md", "# Goal\n")
    _write(root / "task.md", "# Local long run\n")
    task = _write(root / ".task/task.md", "# Local long run\n")
    subject = {
        "kind": "task",
        "ref": ".task/task.md",
        "digest": sha256_file(task),
        "revision": "revision-local-long-run",
    }
    request = _request(subject)
    skills_root = root / "test-skills"
    source_manifest = (
        Path(__file__).resolve().parents[2]
        / "run-task-code-and-log"
        / "authority.operations.json"
    )
    manifest = skills_root / "run-task-code-and-log/authority.operations.json"
    manifest.parent.mkdir(parents=True)
    shutil.copyfile(source_manifest, manifest)
    policy_binding = snapshot_file(
        root, str(policy.relative_to(root)), "policy"
    )
    approval = _write_json(
        root / ".task/authorization/root-source.json",
        {
            "schema_version": 2,
            "artifact_kind": "authority_source_approval",
            "approval_id": "approval-local-long-run",
            "source_kind": "explicit_user_instruction",
            "source_rank": "S3",
            "decision_type": "grant_authority",
            "capabilities": [
                "authority.grant.issue",
                "execution.local.long_run",
            ],
            "subjects": [subject],
            "operations": [_OPERATION],
            "risk_ceiling": "R2",
            "decision_classes": ["D3"],
            "cardinalities": ["single_use"],
            "max_uses": 1,
            "grant_ids": ["grant-local-long-run"],
            "request_digests": [],
            "lineage_ids": ["lineage-local-long-run"],
            "delegation_binding": None,
            "not_before": AT,
            "expires_at": EXPIRY,
            "evidence_id": "user-local-long-run",
            "integrity_status": "verified",
        },
    )
    source_binding = snapshot_historical_source(root, approval)
    register_historical_grant(
        root,
        {
            "schema_version": 2,
            "artifact_kind": "authority_grant",
            "grant_id": "grant-local-long-run",
            "lineage_id": "lineage-local-long-run",
            "parent_grant_id": None,
            "issuer_rank": "S3",
            "holder_rank": "S0",
            "capabilities": ["execution.local.long_run"],
            "subjects": [subject],
            "operations": [_OPERATION],
            "risk_ceiling": "R2",
            "decision_classes": ["D3"],
            "cardinality": "single_use",
            "max_uses": 1,
            "not_before": AT,
            "expires_at": EXPIRY,
            "session_id": SESSION,
            "task_id": TASK,
            "improvement_id": None,
            "source_approval": source_binding,
            "policy_snapshot": policy_binding,
            "created_at": AT,
            "idempotency_key": "grant-key-local-long-run",
        },
    )
    operation_key = ":".join(_OPERATION.values())
    context = {
        "schema_version": 2,
        "context_kind": "authority_evaluation",
        "session_ceiling": {
            "capabilities": ["execution.local.long_run"],
            "risk_ceiling": "R2",
            "mutation_classes": ["local_mutation"],
            "evidence_id": SESSION,
        },
        "goal_autonomy_envelope": {
            "envelope_id": "envelope-local-long-run",
            "capabilities": ["execution.local.long_run"],
            "risk_ceiling": "R2",
            "decision_classes": ["D3"],
            "subjects": [subject["digest"]],
            "operations": [operation_key],
            "source_binding": {
                "ref": str(goal.relative_to(root)),
                "sha256": sha256_file(goal),
            },
        },
    }
    decision = evaluate(
        root, request, context, evaluated_at=AT, skills_root=skills_root
    )
    decision_path = (
        root / ".task/authorization/decisions" / f"{decision['decision_id']}.json"
    )
    decision_sha = write_immutable_json(
        decision_path, decision, "local long-run decision"
    )
    reserved = reserve(
        root,
        str(decision_path.relative_to(root)),
        decision_sha,
        reserved_at=VERIFY_AT,
        idempotency_key="reservation-key-local-long-run",
        skills_root=skills_root,
    )
    command_verify(
        argparse.Namespace(
            root=str(root),
            reservation_ref=reserved["reservation_ref"],
            reservation_sha256=reserved["reservation_sha256"],
            at=VERIFY_AT,
            expected_version=0,
            skills_root=str(skills_root),
            stage="pre_dispatch",
        )
    )
    verification = json.loads(capsys.readouterr().out)
    return build_authority_packet(
        root,
        {
            "ref": str(decision_path.relative_to(root)),
            "sha256": decision_sha,
        },
        reservation_binding={
            "ref": reserved["reservation_ref"],
            "sha256": reserved["reservation_sha256"],
        },
        verification_binding={
            "ref": verification["verification_ref"],
            "sha256": verification["verification_sha256"],
        },
    )


def test_real_run_long_authority_stage_binds_run_preparation(
    tmp_path: Path, capsys,
) -> None:
    packet = _authority(tmp_path, capsys)
    init_cycle(tmp_path, CYCLE, TASK, "local long-run integration")
    assert advance_stage(tmp_path, CYCLE, apply=True)["stop_reason"] == (
        "awaiting_authority"
    )
    publication = publish_authority_packet(tmp_path, CYCLE, packet)
    authority_preparation = prepare_stage(
        tmp_path,
        CYCLE,
        "authority",
        persist_compiler_artifacts=True,
    )
    prepared = publish_preparation(tmp_path, authority_preparation)
    owner = publish_owner_result(
        tmp_path,
        prepared["preparation_ref"],
        prepared["preparation_sha256"],
        source_ref=publication["owner_result_binding"]["ref"],
        source_sha256=publication["owner_result_binding"]["sha256"],
    )
    submitted = submit_stage(
        tmp_path,
        authority_preparation,
        apply=True,
        owner_result_ref=owner["owner_result_binding"]["ref"],
        owner_result_sha256=owner["owner_result_binding"]["sha256"],
    )
    assert submitted["status"] == "ok"

    for step in ORDER[ORDER.index("authority") + 1 : ORDER.index("run")]:
        if step in {"route_plan", "result_contract", "ledger_append"}:
            append_compiled_system_stage(tmp_path, CYCLE, step)
        else:
            append_fixture_event(
                tmp_path,
                CYCLE,
                {
                    "step": step,
                    "status": "completed",
                    "event_id": f"fixture-local-long-run-{step}",
                    "task_id": TASK,
                    "reason": "run preparation predecessor",
                },
            )
    run_preparation = prepare_stage(
        tmp_path,
        CYCLE,
        "run",
        persist_compiler_artifacts=True,
    )
    sealed = _sealed_authority_projection(tmp_path, run_preparation)
    reopened, decision = _authority_packet(tmp_path, CYCLE, sealed)
    assert reopened["operation_binding"]["operation_id"] == "run_long"
    assert decision["request"]["effect_class"] == "run_long"
    assert decision["evaluation_context"]["session_ceiling"]["evidence_id"] == (
        SESSION
    )
