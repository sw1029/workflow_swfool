from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "manage-agent-authority" / "scripts"))

from manage_agent_authority import authority_receipt  # noqa: E402
from manage_agent_authority import artifact_store as artifact_store_module  # noqa: E402
from manage_agent_authority import lifecycle as lifecycle_module  # noqa: E402
from manage_agent_authority import authority_cli  # noqa: E402
from manage_agent_authority.artifact_store import load_grant  # noqa: E402
from manage_agent_authority.artifact_store import register_grant  # noqa: E402
from manage_agent_authority.artifact_store import snapshot_file  # noqa: E402
from manage_agent_authority.artifact_store import transition_grants  # noqa: E402
from manage_agent_authority.canonical import object_sha256  # noqa: E402
from manage_agent_authority.canonical import parse_time  # noqa: E402
from manage_agent_authority.canonical import sha256_file  # noqa: E402
from manage_agent_authority.canonical import write_immutable_json  # noqa: E402
from manage_agent_authority.composition import create_composition  # noqa: E402
from manage_agent_authority.contracts import validate_grant  # noqa: E402
from manage_agent_authority.evaluator import evaluate  # noqa: E402
from manage_agent_authority.lifecycle import consume as _consume  # noqa: E402
from manage_agent_authority.lifecycle import release  # noqa: E402
from manage_agent_authority.reconciliation import reconcile_quarantine  # noqa: E402
from manage_agent_authority.reconciliation_evidence import (  # noqa: E402
    prepare_reconciliation_evidence,
)
from manage_agent_authority.source_recovery import prepare_source_recovery  # noqa: E402
from manage_agent_authority.source_approval import validate_source_approval  # noqa: E402
from manage_agent_authority.lifecycle import reserve  # noqa: E402
from manage_agent_authority.lifecycle import verify_reservation_with_recovery  # noqa: E402
from manage_agent_authority.operations import load_operation  # noqa: E402
from manage_agent_authority.projection_recovery import MAX_INTENT_BYTES  # noqa: E402
from manage_agent_authority.projection_recovery import recover_projection_intents  # noqa: E402
from manage_agent_authority.workflow_status import resolve_operation  # noqa: E402
from manage_agent_authority.workflow_status import status_snapshot  # noqa: E402


AT = "2026-07-17T10:00:00+09:00"
LATER = "2026-07-17T10:05:00+09:00"
APPROVAL_AT = "2026-07-17T10:10:00+09:00"
EXPIRY = "2026-07-17T11:00:00+09:00"
AFTER_EXPIRY = "2026-07-17T11:05:00+09:00"


def precommit_binding(
    root: Path,
    reservation_ref: str,
    reservation_sha256: str,
    *,
    expected_version: int,
    at: str = LATER,
) -> dict[str, str]:
    verification_dir = root / ".task/authorization/verifications"
    for existing_path in sorted(verification_dir.glob("*.json")):
        existing = json.loads(existing_path.read_text(encoding="utf-8"))
        if (
            existing.get("stage") == "pre_commit"
            and existing.get("reservation")
            == {"ref": reservation_ref, "sha256": reservation_sha256}
        ):
            return {
                "ref": str(existing_path.relative_to(root)),
                "sha256": sha256_file(existing_path),
            }
    reservation, state, verified, state_sha256 = verify_reservation_with_recovery(
        root,
        reservation_ref,
        reservation_sha256,
        verified_at=at,
        expected_version=expected_version,
        skills_root=ROOT,
    )
    state_path = (
        root
        / ".task/authorization/state/reservations"
        / f"{reservation['reservation_id']}.json"
    )
    core = {
        "schema_version": 2,
        "artifact_kind": "authority_verification",
        "stage": "pre_commit",
        "reservation": {
            "ref": reservation_ref,
            "sha256": reservation_sha256,
        },
        "reservation_state": {
            "ref": str(state_path.relative_to(root)),
            "sha256": state_sha256,
            "version": state["version"],
            "status": state["status"],
        },
        "grant_states": verified["grant_states"],
        "request_id": verified["decision"]["request"]["request_id"],
        "effective_authority_fingerprint": reservation[
            "effective_authority_fingerprint"
        ],
        "verified_at": parse_time(at, "at").isoformat(),
    }
    artifact = {
        "verification_id": f"authv-{object_sha256(core)[:24]}",
        **core,
    }
    path = (
        root
        / ".task/authorization/verifications"
        / f"{artifact['verification_id']}.json"
    )
    digest = write_immutable_json(path, artifact, "test pre-commit verification")
    return {"ref": str(path.relative_to(root)), "sha256": digest}


def consume(
    root: Path,
    reservation_ref: str,
    reservation_sha256: str,
    execution_result: dict[str, str],
    **kwargs: Any,
) -> dict[str, Any]:
    kwargs.setdefault(
        "pre_commit_verification",
        precommit_binding(
            root,
            reservation_ref,
            reservation_sha256,
            expected_version=kwargs["expected_version"],
            at=kwargs["consumed_at"],
        ),
    )
    subject_ref = json.loads(
        (
            root / reservation_ref
        ).read_text(encoding="utf-8")
    )["decision"]["ref"]
    decision = json.loads((root / subject_ref).read_text(encoding="utf-8"))
    current_subject = root / decision["request"]["subject"]["ref"]
    kwargs.setdefault("expected_subject_after_sha256", sha256_file(current_subject))
    return _consume(
        root,
        reservation_ref,
        reservation_sha256,
        execution_result,
        **kwargs,
    )


def reconciliation_evidence(
    root: Path,
    reserved: dict[str, Any],
    outcome: str,
    *,
    at: str = LATER,
) -> dict[str, str]:
    owner_binding = None
    if outcome != "still_unknown":
        owner = write(
            root / f".task/authorization/results/{outcome}-owner.json",
            json.dumps(
                {
                    "schema_version": 1,
                    "artifact_kind": "test_effect_reconciliation_result",
                    "outcome": outcome,
                },
                sort_keys=True,
            )
            + "\n",
        )
        owner_binding = {
            "ref": str(owner.relative_to(root)),
            "sha256": sha256_file(owner),
        }
    prepared = prepare_reconciliation_evidence(
        root,
        reserved["reservation_ref"],
        reserved["reservation_sha256"],
        outcome=outcome,
        owner_result=owner_binding,
        observed_at=at,
        expected_version=1,
    )
    return prepared["effect_evidence"]


def write(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def setup_workspace(root: Path) -> dict[str, Any]:
    policy = write(
        root / ".agent_goal/agent_authority.md",
        "# Authority\n\nBounded local changes.\n",
    )
    goal = write(
        root / ".agent_goal/goal_architecture.md",
        "# Goal Architecture\n\n- concept_id: concept-1\n",
    )
    task = write(root / ".task/task.md", "# Task\n\nImplement bounded local change.\n")
    subject = {
        "kind": "task",
        "ref": str(task.relative_to(root)),
        "digest": sha256_file(task),
        "revision": "revision-1",
    }
    approval_body = {
        "schema_version": 2,
        "artifact_kind": "authority_source_approval",
        "approval_id": "approval-1",
        "source_kind": "explicit_user_instruction",
        "source_rank": "S3",
        "decision_type": "grant_authority",
        "capabilities": [
            "authority.grant.compose",
            "authority.grant.issue",
            "authority.grant.transition",
            "execution.external.provider",
            "implementation.local.edit",
            "task.scope.publish",
            "task.state.advance",
        ],
        "subjects": [subject],
        "operations": [
            {
                "skill_id": "derive-improvement-task",
                "skill_version": "2.0.0",
                "operation_id": "publish_task",
                "operation_version": "1",
            },
            {
                "skill_id": "task-md-agent-governance",
                "skill_version": "2.0.0",
                "operation_id": "implement_local_change",
                "operation_version": "1",
            },
        ],
        "risk_ceiling": "R3",
        "decision_classes": ["D2", "D3"],
        "cardinalities": ["bounded_reusable", "single_use"],
        "max_uses": 10,
        "grant_ids": [
            "composition-1",
            "grant-1",
            "grant-a",
            "grant-b",
            "grant-child",
            "grant-child-a",
            "grant-child-b",
            "grant-expanded",
            "grant-parent",
            "grant-parent-budget",
        ],
        "request_digests": [],
        "lineage_ids": ["lineage-1"],
        "delegation_binding": None,
        "not_before": AT,
        "expires_at": EXPIRY,
        "evidence_id": "user-message-1",
        "integrity_status": "verified",
    }
    approval = write(
        root / ".task/authorization/user-approval.json",
        json.dumps(approval_body, indent=2, sort_keys=True) + "\n",
    )
    policy_binding = snapshot_file(root, str(policy.relative_to(root)), "policy")
    source_binding = snapshot_file(
        root, str(approval.relative_to(root)), "source_approval"
    )
    return {
        "policy": policy,
        "approval": approval,
        "goal": goal,
        "task": task,
        "policy_binding": policy_binding,
        "source_binding": source_binding,
    }


def request_for(workspace: dict[str, Any], **changes: Any) -> dict[str, Any]:
    task = workspace["task"]
    request = {
        "schema_version": 2,
        "request_kind": "authority_operation",
        "request_id": "request-1",
        "skill_id": "task-md-agent-governance",
        "skill_version": "2.0.0",
        "operation_id": "implement_local_change",
        "operation_version": "1",
        "cycle_id": "cycle-1",
        "task_id": "task-1",
        "pack_id": None,
        "attempt_id": "attempt-1",
        "actor_rank": "S0",
        "subject": {
            "kind": "task",
            "ref": str(task.relative_to(task.parents[1])),
            "digest": sha256_file(task),
            "revision": "revision-1",
        },
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
        "idempotency_key": "request-key-1",
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
    request.update(changes)
    return request


def context_for(workspace: dict[str, Any], request: dict[str, Any]) -> dict[str, Any]:
    goal = workspace["goal"]
    operation = ":".join(
        request[key]
        for key in ("skill_id", "skill_version", "operation_id", "operation_version")
    )
    return {
        "schema_version": 2,
        "context_kind": "authority_evaluation",
        "session_ceiling": {
            "capabilities": list(request["required_capabilities"]),
            "risk_ceiling": "R3",
            "mutation_classes": [
                "observe",
                "local_mutation",
                "external_mutation",
                "destructive",
            ],
            "evidence_id": "session-1",
        },
        "goal_autonomy_envelope": {
            "envelope_id": "envelope-1",
            "capabilities": list(request["required_capabilities"]),
            "risk_ceiling": "R3",
            "decision_classes": [request["decision_class"]],
            "subjects": [request["subject"]["digest"]],
            "operations": [operation],
            "source_binding": {
                "ref": str(goal.relative_to(goal.parents[1])),
                "sha256": sha256_file(goal),
            },
        },
    }


def grant_for(
    workspace: dict[str, Any],
    request: dict[str, Any],
    *,
    grant_id: str = "grant-1",
    capabilities: list[str] | None = None,
    issuer_rank: str = "S3",
    holder_rank: str = "S0",
    parent_grant_id: str | None = None,
    lineage_id: str = "lineage-1",
    max_uses: int | None = 1,
    expires_at: str | None = EXPIRY,
) -> dict[str, Any]:
    return {
        "schema_version": 2,
        "artifact_kind": "authority_grant",
        "grant_id": grant_id,
        "lineage_id": lineage_id,
        "parent_grant_id": parent_grant_id,
        "issuer_rank": issuer_rank,
        "holder_rank": holder_rank,
        "capabilities": capabilities or list(request["required_capabilities"]),
        "subjects": [request["subject"]],
        "operations": [
            {
                key: request[key]
                for key in (
                    "skill_id",
                    "skill_version",
                    "operation_id",
                    "operation_version",
                )
            }
        ],
        "risk_ceiling": "R3",
        "decision_classes": [request["decision_class"]],
        "cardinality": "single_use" if max_uses == 1 else "bounded_reusable",
        "max_uses": max_uses,
        "not_before": AT,
        "expires_at": expires_at,
        "session_id": None,
        "task_id": request["task_id"],
        "improvement_id": None,
        "source_approval": workspace["source_binding"],
        "policy_snapshot": workspace["policy_binding"],
        "created_at": AT,
        "idempotency_key": f"key-{grant_id}",
    }


def delegated_source_for(
    root: Path,
    workspace: dict[str, Any],
    *,
    approval_id: str = "delegated-approval-1",
    source_rank: str = "S2",
    source_kind: str = "delegated_policy_steward",
    delegation_binding: dict[str, str] | None = None,
    **changes: Any,
) -> dict[str, str]:
    body = json.loads(workspace["approval"].read_text(encoding="utf-8"))
    body.update(
        {
            "approval_id": approval_id,
            "source_kind": source_kind,
            "source_rank": source_rank,
            "grant_ids": ["grant-1"],
            "delegation_binding": delegation_binding
            if delegation_binding is not None
            else workspace["source_binding"],
            **changes,
        }
    )
    source = write(
        root / f".task/authorization/{approval_id}.json",
        json.dumps(body, indent=2, sort_keys=True) + "\n",
    )
    return snapshot_file(root, str(source.relative_to(root)), "source_approval")


def persist_decision(root: Path, decision: dict[str, Any]) -> tuple[str, str]:
    path = root / ".task/authorization/decisions" / f"{decision['decision_id']}.json"
    digest = write_immutable_json(path, decision, "test authority decision")
    return str(path.relative_to(root)), digest


def reserve_default_operation(root: Path, *, idempotency_key: str) -> dict[str, Any]:
    workspace = setup_workspace(root)
    request = request_for(workspace)
    context = context_for(workspace, request)
    register_grant(root, grant_for(workspace, request))
    decision = evaluate(root, request, context, evaluated_at=AT, skills_root=ROOT)
    decision_ref, decision_sha = persist_decision(root, decision)
    return reserve(
        root,
        decision_ref,
        decision_sha,
        reserved_at=LATER,
        idempotency_key=idempotency_key,
        skills_root=ROOT,
    )


def isolated_skills_root(root: Path) -> Path:
    skills_root = root / "isolated-skills"
    skill_id = "task-md-agent-governance"
    source = ROOT / skill_id / "authority.operations.json"
    write(
        skills_root / skill_id / "authority.operations.json",
        source.read_text(encoding="utf-8"),
    )
    return skills_root


def isolated_skills_root_with_unrelated_alias(root: Path) -> Path:
    skills_root = isolated_skills_root(root)
    source = ROOT / "task-md-agent-governance" / "authority.operations.json"
    manifest = json.loads(source.read_text(encoding="utf-8"))
    manifest["skill_id"] = "unrelated-authority-skill"
    write(
        skills_root / "unrelated-authority-skill" / "authority.operations.json",
        json.dumps(manifest, sort_keys=True) + "\n",
    )
    return skills_root


def persist_unrelated_decision(
    root: Path,
    workspace: dict[str, Any],
    skills_root: Path,
    *,
    stale_manifest: bool,
) -> tuple[dict[str, Any], str]:
    request = request_for(
        workspace,
        request_id="unrelated-request",
        skill_id="unrelated-authority-skill",
        attempt_id="unrelated-attempt",
        idempotency_key="unrelated-request-key",
    )
    decision = evaluate(
        root,
        request,
        context_for(workspace, request),
        evaluated_at=AT,
        skills_root=skills_root,
    )
    decision_ref, _ = persist_decision(root, decision)
    if stale_manifest:
        manifest = (
            skills_root
            / "unrelated-authority-skill"
            / "authority.operations.json"
        )
        manifest.write_text(
            manifest.read_text(encoding="utf-8") + "\n", encoding="utf-8"
        )
    return decision, decision_ref


def replace_with_narrow_source(
    root: Path, workspace: dict[str, Any], grant_ids: list[str]
) -> dict[str, Any]:
    previous_snapshot = root / workspace["source_binding"]["ref"]
    body = json.loads(workspace["approval"].read_text(encoding="utf-8"))
    body["approval_id"] = "approval-narrow-source"
    body["grant_ids"] = grant_ids
    source = write(
        root / ".task/authorization/narrow-source.json",
        json.dumps(body, indent=2, sort_keys=True) + "\n",
    )
    binding = snapshot_file(root, str(source.relative_to(root)), "source_approval")
    previous_snapshot.unlink()
    return {**workspace, "source_binding": binding}


def legacy_receipt(root: Path, schema_version: int) -> dict[str, Any]:
    workspace = setup_workspace(root)
    return {
        "schema_version": schema_version,
        "receipt_id": f"receipt-v{schema_version}",
        "receipt_kind": "operation_authority",
        "operation": "task_pack.normalize_initial_selection",
        "decision": "allowed",
        "basis_temporality": "current_ratification",
        "issued_at": AT,
        "effective_at": AT,
        "subject": {
            "pack_ref": ".task/task_pack/pack-P.json",
            "pack_creation_snapshot_ref": "git:abc:snapshot.json",
            "pack_creation_snapshot_sha256": "a" * 64,
            "initial_item_id": "item-I",
            "initial_order": 1,
            "task_id": "task-T",
            "task_snapshot_ref": ".task/task_pack/task_snapshots/task-T.md",
            "task_snapshot_sha256": "b" * 64,
        },
        "authority_basis": {
            "policy_ref": ".agent_goal/agent_authority.md",
            "policy_sha256": sha256_file(workspace["policy"]),
            "source_kind": "explicit_current_user_instruction",
            "source_id": "instruction-I",
            "source_evidence_ref": ".task/authorization/user-approval.json",
            "source_evidence_sha256": sha256_file(workspace["approval"]),
            "integrity_status": "verified",
        },
        "historical_effect": {
            "historical_selection_authority_status": "unverifiable_before_ratification",
            "historical_authority_verdict": "partial",
            "retroactive_claim_allowed": False,
        },
        "allowed_effects": ["append_initial_selection_normalization_provenance"],
        "forbidden_effects": ["claim_historical_authority_pass"],
    }


def test_v2_receipt_survives_mutable_policy_and_source_updates(tmp_path: Path) -> None:
    body = legacy_receipt(tmp_path, 2)
    args = argparse.Namespace(
        root=str(tmp_path),
        plan=json.dumps(body),
        output=".task/authority_receipts/receipt-v2.json",
    )
    assert authority_receipt.command_issue(args) == 0
    receipt = json.loads((tmp_path / args.output).read_text(encoding="utf-8"))
    write(
        tmp_path / ".agent_goal/agent_authority.md",
        "# Authority\n\nNew unrelated policy.\n",
    )
    write(
        tmp_path / ".task/authorization/user-approval.json",
        "{}\n",
    )
    assert authority_receipt.validate_receipt(tmp_path, receipt)["status"] == "valid"


def test_v1_receipt_preserves_current_file_digest_semantics(tmp_path: Path) -> None:
    body = legacy_receipt(tmp_path, 1)
    assert authority_receipt.validate_receipt(tmp_path, body)["status"] == "valid"
    write(tmp_path / ".agent_goal/agent_authority.md", "changed\n")
    with pytest.raises(SystemExit, match="policy SHA-256"):
        authority_receipt.validate_receipt(tmp_path, body)


def test_scoped_fingerprint_ignores_unrelated_envelope_additions(
    tmp_path: Path,
) -> None:
    workspace = setup_workspace(tmp_path)
    request = request_for(workspace)
    context = context_for(workspace, request)
    register_grant(tmp_path, grant_for(workspace, request))
    first = evaluate(tmp_path, request, context, evaluated_at=AT, skills_root=ROOT)
    context["session_ceiling"]["capabilities"].append("unrelated.capability.read")
    context["goal_autonomy_envelope"]["capabilities"].append(
        "unrelated.capability.read"
    )
    context["goal_autonomy_envelope"]["subjects"].append("f" * 64)
    context["goal_autonomy_envelope"]["operations"].append("other-skill:1.0.0:read:1")
    second = evaluate(tmp_path, request, context, evaluated_at=AT, skills_root=ROOT)
    assert first["decision"] == second["decision"] == "allowed"
    assert first["evaluation_context_sha256"] != second["evaluation_context_sha256"]
    assert (
        first["effective_authority_fingerprint"]
        == second["effective_authority_fingerprint"]
    )


def test_unknown_mutation_and_unsupplyable_input_fail_without_approval_loop(
    tmp_path: Path,
) -> None:
    workspace = setup_workspace(tmp_path)
    unknown = request_for(workspace, operation_id="unknown_mutation")
    context = context_for(workspace, unknown)
    denied = evaluate(tmp_path, unknown, context, evaluated_at=AT, skills_root=ROOT)
    assert denied["decision"] == "denied"
    assert denied["reason_codes"] == ["unknown_mutating_operation_fail_closed"]

    blocked_request = request_for(workspace)
    blocked_request["context"]["external_input_status"] = "missing_unsupplyable"
    availability = write(
        tmp_path / ".task/authorization/evidence/input-status.json", "{}\n"
    )
    blocked_request["context"]["external_input_evidence"] = {
        "ref": str(availability.relative_to(tmp_path)),
        "sha256": sha256_file(availability),
    }
    blocked = evaluate(
        tmp_path,
        blocked_request,
        context_for(workspace, blocked_request),
        evaluated_at=AT,
        skills_root=ROOT,
    )
    assert blocked["decision"] == "waiting_external_input"
    assert (
        "external_input_unsupplyable_route_local_or_descope" in blocked["reason_codes"]
    )


def test_single_use_reserve_consume_is_idempotent_and_cannot_double_spend(
    tmp_path: Path,
) -> None:
    workspace = setup_workspace(tmp_path)
    request = request_for(workspace)
    context = context_for(workspace, request)
    register_grant(tmp_path, grant_for(workspace, request))
    decision = evaluate(tmp_path, request, context, evaluated_at=AT, skills_root=ROOT)
    decision_ref, decision_sha = persist_decision(tmp_path, decision)
    reserved = reserve(
        tmp_path,
        decision_ref,
        decision_sha,
        reserved_at=LATER,
        idempotency_key="reserve-key",
        skills_root=ROOT,
    )
    replay = reserve(
        tmp_path,
        decision_ref,
        decision_sha,
        reserved_at=LATER,
        idempotency_key="reserve-key",
        skills_root=ROOT,
    )
    assert replay["reservation_sha256"] == reserved["reservation_sha256"]

    result_file = write(tmp_path / ".task/authorization/results/result-1.json", "{}\n")
    result_binding = {
        "ref": str(result_file.relative_to(tmp_path)),
        "sha256": sha256_file(result_file),
    }
    consumed = consume(
        tmp_path,
        reserved["reservation_ref"],
        reserved["reservation_sha256"],
        result_binding,
        consumed_at=LATER,
        expected_version=0,
        idempotency_key="consume-key",
        skills_root=ROOT,
    )
    consumed_replay = consume(
        tmp_path,
        reserved["reservation_ref"],
        reserved["reservation_sha256"],
        result_binding,
        consumed_at=LATER,
        expected_version=0,
        idempotency_key="consume-key",
        skills_root=ROOT,
    )
    assert consumed_replay["sha256"] == consumed["sha256"]
    _, _, state = load_grant(tmp_path, "grant-1")
    assert state["status"] == "exhausted"
    assert state["remaining_uses"] == 0
    assert state["consumed_uses"] == 1
    after = evaluate(tmp_path, request, context, evaluated_at=LATER, skills_root=ROOT)
    assert after["decision"] == "approval_required"


def test_consume_accepts_exact_mutable_subject_after_precommit(tmp_path: Path) -> None:
    workspace = setup_workspace(tmp_path)
    request = request_for(workspace)
    register_grant(tmp_path, grant_for(workspace, request))
    decision = evaluate(
        tmp_path, request, context_for(workspace, request), evaluated_at=AT, skills_root=ROOT
    )
    decision_ref, decision_sha = persist_decision(tmp_path, decision)
    reserved = reserve(
        tmp_path,
        decision_ref,
        decision_sha,
        reserved_at=LATER,
        idempotency_key="mutable-reserve",
        skills_root=ROOT,
    )
    precommit = precommit_binding(
        tmp_path,
        reserved["reservation_ref"],
        reserved["reservation_sha256"],
        expected_version=0,
    )
    write(workspace["task"], "# Task\n\nExact expected after state.\n")
    owner_result = write(
        tmp_path / ".task/authorization/results/mutable-result.json",
        '{"schema_version": 1, "artifact_kind": "test_execution_result"}\n',
    )
    result = _consume(
        tmp_path,
        reserved["reservation_ref"],
        reserved["reservation_sha256"],
        {"ref": str(owner_result.relative_to(tmp_path)), "sha256": sha256_file(owner_result)},
        pre_commit_verification=precommit,
        expected_subject_after_sha256=sha256_file(workspace["task"]),
        consumed_at=LATER,
        expected_version=0,
        idempotency_key="mutable-consume",
        skills_root=ROOT,
    )
    typed_binding = result["use_receipt"]["execution_result"]
    typed = json.loads((tmp_path / typed_binding["ref"]).read_text(encoding="utf-8"))
    assert typed["artifact_kind"] == "authority_execution_result"
    assert typed["subject_before"]["digest"] == request["subject"]["digest"]
    assert typed["subject_after"]["sha256"] == sha256_file(workspace["task"])


def test_consume_requires_explicit_precommit_and_expected_after(tmp_path: Path) -> None:
    workspace = setup_workspace(tmp_path)
    request = request_for(workspace)
    register_grant(tmp_path, grant_for(workspace, request))
    decision = evaluate(
        tmp_path, request, context_for(workspace, request), evaluated_at=AT, skills_root=ROOT
    )
    decision_ref, decision_sha = persist_decision(tmp_path, decision)
    reserved = reserve(
        tmp_path,
        decision_ref,
        decision_sha,
        reserved_at=LATER,
        idempotency_key="strict-reserve",
        skills_root=ROOT,
    )
    owner_result = write(
        tmp_path / ".task/authorization/results/strict-result.json", "{}\n"
    )
    binding = {
        "ref": str(owner_result.relative_to(tmp_path)),
        "sha256": sha256_file(owner_result),
    }
    with pytest.raises(SystemExit, match="explicit exact pre_commit"):
        _consume(
            tmp_path,
            reserved["reservation_ref"],
            reserved["reservation_sha256"],
            binding,
            expected_subject_after_sha256=sha256_file(workspace["task"]),
            consumed_at=LATER,
            expected_version=0,
            idempotency_key="strict-consume",
            skills_root=ROOT,
        )
    precommit = precommit_binding(
        tmp_path,
        reserved["reservation_ref"],
        reserved["reservation_sha256"],
        expected_version=0,
    )
    with pytest.raises(SystemExit, match="requires expected_subject_after"):
        _consume(
            tmp_path,
            reserved["reservation_ref"],
            reserved["reservation_sha256"],
            binding,
            pre_commit_verification=precommit,
            consumed_at=LATER,
            expected_version=0,
            idempotency_key="strict-consume",
            skills_root=ROOT,
        )


def test_reusable_budget_reserves_only_explicit_dispatch_units(tmp_path: Path) -> None:
    workspace = setup_workspace(tmp_path)
    request = request_for(
        workspace,
        cardinality_requested="bounded_reusable",
        use_budget_requested=5,
        reservation_units=1,
    )
    register_grant(tmp_path, grant_for(workspace, request, max_uses=5))
    decision = evaluate(
        tmp_path, request, context_for(workspace, request), evaluated_at=AT, skills_root=ROOT
    )
    decision_ref, decision_sha = persist_decision(tmp_path, decision)
    reserved = reserve(
        tmp_path,
        decision_ref,
        decision_sha,
        reserved_at=LATER,
        idempotency_key="split-units-reserve",
        skills_root=ROOT,
    )
    assert {use["units"] for use in reserved["reservation"]["grant_uses"]} == {1}
    assert load_grant(tmp_path, "grant-1")[2]["reserved_uses"] == 1


@pytest.mark.parametrize(
    ("outcome", "expected_status", "remaining", "consumed"),
    [
        ("confirmed_effect", "consumed", 0, 1),
        ("confirmed_no_effect", "released", 1, 0),
        ("still_unknown", "quarantined_unknown_effect", 1, 0),
    ],
)
def test_quarantine_reconciliation_has_closed_cas_outcomes(
    tmp_path: Path,
    outcome: str,
    expected_status: str,
    remaining: int,
    consumed: int,
) -> None:
    workspace = setup_workspace(tmp_path)
    request = request_for(workspace)
    register_grant(tmp_path, grant_for(workspace, request))
    decision = evaluate(
        tmp_path, request, context_for(workspace, request), evaluated_at=AT, skills_root=ROOT
    )
    decision_ref, decision_sha = persist_decision(tmp_path, decision)
    reserved = reserve(
        tmp_path,
        decision_ref,
        decision_sha,
        reserved_at=LATER,
        idempotency_key=f"reconcile-{outcome}-reserve",
        skills_root=ROOT,
    )
    precommit = precommit_binding(
        tmp_path,
        reserved["reservation_ref"],
        reserved["reservation_sha256"],
        expected_version=0,
    )
    unknown_evidence = write(
        tmp_path / f".task/authorization/results/quarantine-{outcome}.json",
        json.dumps({"schema_version": 1, "artifact_kind": "unknown_effect_evidence"}) + "\n",
    )
    unknown_binding = {
        "ref": str(unknown_evidence.relative_to(tmp_path)),
        "sha256": sha256_file(unknown_evidence),
    }
    release(
        tmp_path,
        reserved["reservation_ref"],
        reserved["reservation_sha256"],
        unknown_binding,
        released_at=LATER,
        expected_version=0,
        idempotency_key=f"reconcile-{outcome}-quarantine",
        effect_status="unknown_effect",
    )
    evidence_binding = reconciliation_evidence(tmp_path, reserved, outcome)
    assert reconciliation_evidence(tmp_path, reserved, outcome) == evidence_binding
    reconciled = reconcile_quarantine(
        tmp_path,
        reserved["reservation_ref"],
        reserved["reservation_sha256"],
        evidence_binding,
        outcome=outcome,
        pre_commit_verification=precommit if outcome == "confirmed_effect" else None,
        reconciled_at=LATER,
        expected_version=1,
        idempotency_key=f"reconcile-{outcome}-settle",
    )
    state_path = (
        tmp_path
        / ".task/authorization/state/reservations"
        / f"{reserved['reservation']['reservation_id']}.json"
    )
    assert json.loads(state_path.read_text(encoding="utf-8"))["status"] == expected_status
    grant_state = load_grant(tmp_path, "grant-1")[2]
    assert grant_state["remaining_uses"] == remaining
    assert grant_state["consumed_uses"] == consumed
    assert reconciled["reconciliation_receipt"]["outcome"] == outcome


def test_quarantine_reconciliation_rejects_arbitrary_json_evidence(tmp_path: Path) -> None:
    workspace = setup_workspace(tmp_path)
    request = request_for(workspace)
    register_grant(tmp_path, grant_for(workspace, request))
    decision = evaluate(
        tmp_path, request, context_for(workspace, request), evaluated_at=AT, skills_root=ROOT
    )
    decision_ref, decision_sha = persist_decision(tmp_path, decision)
    reserved = reserve(
        tmp_path,
        decision_ref,
        decision_sha,
        reserved_at=LATER,
        idempotency_key="forged-evidence-reserve",
        skills_root=ROOT,
    )
    arbitrary = write(
        tmp_path / ".task/authorization/results/arbitrary-evidence.json", "{}\n"
    )
    arbitrary_binding = {
        "ref": str(arbitrary.relative_to(tmp_path)),
        "sha256": sha256_file(arbitrary),
    }
    release(
        tmp_path,
        reserved["reservation_ref"],
        reserved["reservation_sha256"],
        arbitrary_binding,
        released_at=LATER,
        expected_version=0,
        idempotency_key="forged-evidence-quarantine",
        effect_status="unknown_effect",
    )
    with pytest.raises(SystemExit, match="not closed"):
        reconcile_quarantine(
            tmp_path,
            reserved["reservation_ref"],
            reserved["reservation_sha256"],
            arbitrary_binding,
            outcome="confirmed_no_effect",
            pre_commit_verification=None,
            reconciled_at=LATER,
            expected_version=1,
            idempotency_key="forged-evidence-settle",
        )


def test_prepare_reconciliation_evidence_cli_is_deterministic(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    workspace = setup_workspace(tmp_path)
    request = request_for(workspace)
    register_grant(tmp_path, grant_for(workspace, request))
    decision = evaluate(
        tmp_path, request, context_for(workspace, request), evaluated_at=AT, skills_root=ROOT
    )
    decision_ref, decision_sha = persist_decision(tmp_path, decision)
    reserved = reserve(
        tmp_path,
        decision_ref,
        decision_sha,
        reserved_at=LATER,
        idempotency_key="evidence-cli-reserve",
        skills_root=ROOT,
    )
    unknown = write(tmp_path / ".task/authorization/results/cli-unknown.json", "{}\n")
    release(
        tmp_path,
        reserved["reservation_ref"],
        reserved["reservation_sha256"],
        {"ref": str(unknown.relative_to(tmp_path)), "sha256": sha256_file(unknown)},
        released_at=LATER,
        expected_version=0,
        idempotency_key="evidence-cli-quarantine",
        effect_status="unknown_effect",
    )
    owner = write(
        tmp_path / ".task/authorization/results/cli-owner.json",
        '{"schema_version": 1, "artifact_kind": "verified_no_effect"}\n',
    )
    argv = [
        "prepare-reconciliation-evidence",
        "--root",
        str(tmp_path),
        "--reservation-ref",
        reserved["reservation_ref"],
        "--reservation-sha256",
        reserved["reservation_sha256"],
        "--owner-result",
        json.dumps({"ref": str(owner.relative_to(tmp_path)), "sha256": sha256_file(owner)}),
        "--expected-version",
        "1",
        "--outcome",
        "confirmed_no_effect",
        "--at",
        LATER,
    ]
    assert authority_cli.main(argv) == 0
    first = json.loads(capsys.readouterr().out)
    assert authority_cli.main(argv) == 0
    second = json.loads(capsys.readouterr().out)
    assert first["effect_evidence"] == second["effect_evidence"]
    assert first["evidence"]["artifact_kind"] == "authority_effect_reconciliation_evidence"


def test_resolve_reuses_source_approval_and_stable_wait_without_prompt(
    tmp_path: Path,
) -> None:
    workspace = setup_workspace(tmp_path)
    request = request_for(workspace)
    context = context_for(workspace, request)
    first = resolve_operation(
        tmp_path, request, context, evaluated_at=AT, skills_root=ROOT
    )
    second = resolve_operation(
        tmp_path, request, context, evaluated_at=LATER, skills_root=ROOT
    )
    assert first["decision"] == "approval_required"
    assert first["resolution"] == "source_approval_ready_for_grant"
    assert first["outcome"] == first["workflow_state"] == first["resolution"]
    assert first["should_prompt"] is False
    assert first["approval_projection"] is None
    assert second["approval_projection"] is None
    assert first["user_action"] is None
    assert first["next_action"]["code"] == "materialize_grant"
    assert first["wait_identity"] == second["wait_identity"]
    assert "no_authority_grants_registered" in first["reason_codes"]


def test_resolve_returns_one_common_user_interaction_projection(
    tmp_path: Path,
) -> None:
    workspace = setup_workspace(tmp_path)
    request = request_for(workspace)
    context = context_for(workspace, request)
    (tmp_path / workspace["source_binding"]["ref"]).unlink()

    result = resolve_operation(
        tmp_path, request, context, evaluated_at=AT, skills_root=ROOT
    )
    assert result["resolution"] == "needs_user_approval"
    assert result["outcome"] == result["workflow_state"] == result["resolution"]
    assert result["should_prompt"] is True
    assert result["approval_projection"] is not None
    assert result["user_action"] == result["next_action"] == {
        "actor": "user",
        "code": "approve_exact_projection",
    }


def test_status_reuses_existing_usable_source_grant_without_prompt(
    tmp_path: Path,
) -> None:
    workspace = replace_with_narrow_source(
        tmp_path, setup_workspace(tmp_path), ["grant-1"]
    )
    request = request_for(workspace)
    context = context_for(workspace, request)
    waiting = evaluate(tmp_path, request, context, evaluated_at=AT, skills_root=ROOT)
    persist_decision(tmp_path, waiting)
    register_grant(tmp_path, grant_for(workspace, request))

    status = status_snapshot(
        tmp_path,
        request_sha256=waiting["request_sha256"],
        evaluated_at=LATER,
        skills_root=ROOT,
    )
    assert status["workflow_state"] == "source_approval_ready_for_grant"
    assert status["should_prompt"] is False
    assert status["approval_projection"] is None
    assert status["next_action"] == {
        "actor": "system",
        "code": "evaluate_existing_grant",
    }
    source = status["workflow_basis"]["source_approval"]
    assert source["materializable_grant_ids"] == []
    assert source["usable_grant_ids"] == ["grant-1"]
    assert status["pending_waits"] == []


def test_exhausted_exact_source_prepares_one_closed_recovery_approval(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    workspace = replace_with_narrow_source(
        tmp_path, setup_workspace(tmp_path), ["grant-1"]
    )
    first_request = request_for(workspace)
    first_context = context_for(workspace, first_request)
    register_grant(tmp_path, grant_for(workspace, first_request))
    allowed = evaluate(
        tmp_path,
        first_request,
        first_context,
        evaluated_at=AT,
        skills_root=ROOT,
    )
    decision_ref, decision_sha = persist_decision(tmp_path, allowed)
    reserved = reserve(
        tmp_path,
        decision_ref,
        decision_sha,
        reserved_at=LATER,
        idempotency_key="exhaust-source-reserve",
        skills_root=ROOT,
    )
    owner_result = write(
        tmp_path / ".task/authorization/results/exhaust-source.json", "{}\n"
    )
    consume(
        tmp_path,
        reserved["reservation_ref"],
        reserved["reservation_sha256"],
        {
            "ref": str(owner_result.relative_to(tmp_path)),
            "sha256": sha256_file(owner_result),
        },
        consumed_at=LATER,
        expected_version=0,
        idempotency_key="exhaust-source-consume",
        skills_root=ROOT,
    )
    request = request_for(
        workspace,
        request_id="request-2",
        attempt_id="attempt-2",
        idempotency_key="request-key-2",
    )
    context = context_for(workspace, request)
    waiting = evaluate(
        tmp_path, request, context, evaluated_at=LATER, skills_root=ROOT
    )
    recovery_decision_ref, recovery_decision_sha = persist_decision(tmp_path, waiting)

    status = status_snapshot(
        tmp_path,
        request_sha256=waiting["request_sha256"],
        evaluated_at=LATER,
        skills_root=ROOT,
    )
    assert status["workflow_state"] == "source_authority_exhausted"
    assert status["should_prompt"] is False
    assert status["approval_projection"] is None
    assert status["next_action"] == {
        "actor": "system",
        "code": "prepare_exact_recovery_recipe",
    }
    refresh_wait = status["source_exhausted_waits"][0]
    assert refresh_wait["reason_codes"] == [
        "source_authority_no_usable_or_materializable_grant"
    ]
    assert refresh_wait["wait_identity"] is None
    assert refresh_wait["recovery_identity"] != refresh_wait["previous_wait_identity"]
    assert status["pending_waits"] == []
    assert status["historical_waits"][0]["wait_identity"] == refresh_wait[
        "previous_wait_identity"
    ]
    source = refresh_wait["source_approvals"][0]
    assert source["materialization_status"] == "fresh_authority_required"
    assert source["materializable_grant_ids"] == []
    assert source["usable_grant_ids"] == []
    assert source["unavailable_grants"][0]["state_binding"]["sha256"]

    resolved = resolve_operation(
        tmp_path, request, context, evaluated_at=LATER, skills_root=ROOT
    )
    assert resolved["workflow_state"] == "source_authority_exhausted"
    assert resolved["should_prompt"] is False
    assert resolved["next_action"]["code"] == "prepare_exact_recovery_recipe"
    assert (
        "source_authority_no_usable_or_materializable_grant"
        in resolved["reason_codes"]
    )
    assert resolved["wait_identity"] is None
    assert resolved["recovery_identity"] == refresh_wait["recovery_identity"]
    assert resolved["approval_projection"] is None

    prepared = prepare_source_recovery(
        tmp_path,
        recovery_decision_ref,
        recovery_decision_sha,
        prepared_at=LATER,
        skills_root=ROOT,
    )
    assert prepared["status"] == "prepared"
    assert prepared["authority_status"] == "non_authoritative_prepare_only"
    assert prepared["should_prompt"] is True
    assert prepared["next_action"] == {
        "actor": "user",
        "code": "approve_exact_recovery_projection",
    }
    recipe_path = tmp_path / prepared["recovery_recipe"]["ref"]
    recipe = json.loads(recipe_path.read_text(encoding="utf-8"))
    assert sha256_file(recipe_path) == prepared["recovery_recipe"]["sha256"]
    assert recipe["recovery_identity"] == refresh_wait["recovery_identity"]
    assert recipe["exhausted_authority"]["decision"] == {
        "ref": recovery_decision_ref,
        "sha256": recovery_decision_sha,
        "decision_id": waiting["decision_id"],
        "request_sha256": waiting["request_sha256"],
    }
    old_ids = {
        request["request_id"],
        request["attempt_id"],
        workspace["source_binding"]["ref"],
        "approval-narrow-source",
        "grant-1",
        "lineage-1",
        request["idempotency_key"],
    }
    replacement_ids = set(recipe["replacement_ids"].values())
    assert len(replacement_ids) == 6
    assert not replacement_ids.intersection(old_ids)
    assert recipe["replacement_request"]["request_id"] == recipe[
        "replacement_ids"
    ]["request_id"]
    assert recipe["replacement_request"]["attempt_id"] == recipe[
        "replacement_ids"
    ]["attempt_id"]
    assert recipe["replacement_request"]["idempotency_key"] == recipe[
        "replacement_ids"
    ]["exact_replay_key"]
    requirements = recipe["approval_requirements"]
    assert requirements["status"] == "requires_exact_user_approval"
    source_requirements = recipe["source_approval_requirements"]
    assert source_requirements["approval_id"] == recipe[
        "replacement_ids"
    ]["source_approval_id"]
    assert source_requirements["grant_ids_required"] == [
        recipe["replacement_ids"]["grant_id"]
    ]
    assert source_requirements["evidence_id_requirement"] == (
        "exact_explicit_user_decision_evidence_id"
    )
    assert source_requirements["prepared_at_floor"] == LATER
    assert source_requirements["not_before_requirement"] == (
        "actual_explicit_user_decision_time"
    )
    assert "integrity_status" not in source_requirements
    grant_requirements = recipe["grant_requirements"]
    assert grant_requirements["grant_id"] == recipe["replacement_ids"][
        "grant_id"
    ]
    assert "source_approval" not in grant_requirements
    assert grant_requirements["prepared_at_floor"] == LATER
    assert grant_requirements["not_before_requirement"] == (
        "at_or_after_actual_explicit_user_decision_time"
    )
    assert grant_requirements["source_approval_binding_requirement"][
        "binding"
    ] == "actual_post_user_approval_snapshot_ref_and_sha256"

    nested_dicts: list[dict[str, Any]] = []
    pending_values: list[Any] = [recipe]
    while pending_values:
        value = pending_values.pop()
        if isinstance(value, dict):
            nested_dicts.append(value)
            pending_values.extend(value.values())
        elif isinstance(value, list):
            pending_values.extend(value)
    for candidate in nested_dicts:
        with pytest.raises(SystemExit):
            validate_source_approval(candidate)
        with pytest.raises(SystemExit):
            validate_grant(candidate)

    source_snapshot_dir = tmp_path / ".task/authorization/source_snapshots"
    snapshots_before = set(source_snapshot_dir.iterdir())
    extracted_source = write(
        tmp_path / ".task/authorization/extracted-recovery-source.json",
        json.dumps(source_requirements),
    )
    with pytest.raises(SystemExit):
        snapshot_file(
            tmp_path, str(extracted_source.relative_to(tmp_path)), "source_approval"
        )
    assert set(source_snapshot_dir.iterdir()) == snapshots_before
    with pytest.raises(SystemExit):
        register_grant(tmp_path, grant_requirements)
    projection = recipe["approval_projection"]
    assert "authority.grant.issue" in projection["capabilities"]
    assert projection["grant_id"] == recipe["replacement_ids"]["grant_id"]
    assert projection["lineage_id"] == recipe["replacement_ids"]["lineage_id"]
    assert projection["exact_replay_key"] == recipe["replacement_ids"][
        "exact_replay_key"
    ]

    replay = prepare_source_recovery(
        tmp_path,
        recovery_decision_ref,
        recovery_decision_sha,
        prepared_at=LATER,
        skills_root=ROOT,
    )
    assert replay == prepared
    assert (
        authority_cli.main(
            [
                "prepare-source-recovery",
                "--root",
                str(tmp_path),
                "--decision-ref",
                recovery_decision_ref,
                "--decision-sha256",
                recovery_decision_sha,
                "--at",
                LATER,
                "--skills-root",
                str(ROOT),
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["recovery_recipe"] == prepared[
        "recovery_recipe"
    ]

    status_after = status_snapshot(
        tmp_path,
        request_sha256=waiting["request_sha256"],
        evaluated_at=LATER,
        skills_root=ROOT,
    )
    assert status_after["workflow_state"] == "needs_user_approval"
    assert status_after["should_prompt"] is True
    assert status_after["next_action"] == {
        "actor": "user",
        "code": "approve_exact_recovery_projection",
    }
    assert status_after["source_exhausted_waits"] == []
    assert len(status_after["pending_waits"]) == 1
    assert len(status_after["recovery_waits"]) == 1
    assert status_after["approval_projection"] == projection
    assert status_after["wait_identity"] == prepared["wait_identity"]

    resolved_after = resolve_operation(
        tmp_path, request, context, evaluated_at=LATER, skills_root=ROOT
    )
    assert resolved_after["workflow_state"] == "needs_user_approval"
    assert resolved_after["next_action"]["code"] == (
        "approve_exact_recovery_projection"
    )
    assert resolved_after["approval_projection"] == projection
    assert resolved_after["wait_identity"] == prepared["wait_identity"]
    assert resolved_after["recovery_identity"] == recipe["recovery_identity"]

    handoff = status_after["post_approval_handoff"]
    assert handoff == prepared["post_approval_handoff"]
    assert handoff == resolved_after["post_approval_handoff"]
    assert handoff["commands"] == [
        "snapshot-source",
        "register-grant",
        "evaluate",
    ]
    assert handoff["continuation_request_sha256"] == recipe[
        "replacement_request_sha256"
    ]

    actual_source_body = {
        "schema_version": 2,
        "artifact_kind": "authority_source_approval",
        "approval_id": source_requirements["approval_id"],
        "source_kind": source_requirements["source_kind_required"],
        "source_rank": source_requirements["source_rank_required"],
        "decision_type": source_requirements["decision_type_required"],
        "capabilities": source_requirements["capabilities_required"],
        "subjects": source_requirements["subjects_required"],
        "operations": source_requirements["operations_required"],
        "risk_ceiling": source_requirements["risk_ceiling_required"],
        "decision_classes": source_requirements["decision_classes_required"],
        "cardinalities": source_requirements["cardinalities_required"],
        "max_uses": source_requirements["max_uses_required"],
        "grant_ids": source_requirements["grant_ids_required"],
        "request_digests": source_requirements["request_digests_required"],
        "lineage_ids": source_requirements["lineage_ids_required"],
        "delegation_binding": source_requirements["delegation_binding_required"],
        "not_before": APPROVAL_AT,
        "expires_at": source_requirements["expires_at_ceiling"],
        "evidence_id": "explicit-user-decision-recovery-1",
        "integrity_status": "verified",
    }
    actual_source_path = write(
        tmp_path / ".task/authorization/approved-recovery-source.json",
        json.dumps(actual_source_body, indent=2, sort_keys=True) + "\n",
    )
    assert (
        authority_cli.main(
            [
                "snapshot-source",
                "--root",
                str(tmp_path),
                "--source-ref",
                str(actual_source_path.relative_to(tmp_path)),
            ]
        )
        == 0
    )
    actual_source_binding = json.loads(capsys.readouterr().out)["source_approval"]

    actual_grant = {
        "schema_version": 2,
        "artifact_kind": "authority_grant",
        "grant_id": grant_requirements["grant_id"],
        "lineage_id": grant_requirements["lineage_id"],
        "parent_grant_id": grant_requirements["parent_grant_id_required"],
        "issuer_rank": grant_requirements["issuer_rank_required"],
        "holder_rank": grant_requirements["holder_rank_required"],
        "capabilities": grant_requirements["capabilities_required"],
        "subjects": grant_requirements["subjects_required"],
        "operations": grant_requirements["operations_required"],
        "risk_ceiling": grant_requirements["risk_ceiling_required"],
        "decision_classes": grant_requirements["decision_classes_required"],
        "cardinality": grant_requirements["cardinality_required"],
        "max_uses": grant_requirements["max_uses_required"],
        "not_before": APPROVAL_AT,
        "expires_at": grant_requirements["expires_at_ceiling"],
        "session_id": grant_requirements["session_id_required"],
        "task_id": grant_requirements["task_id_required"],
        "improvement_id": grant_requirements["improvement_id_required"],
        "source_approval": actual_source_binding,
        "policy_snapshot": grant_requirements["policy_snapshot_required"],
        "created_at": APPROVAL_AT,
        "idempotency_key": grant_requirements["idempotency_key_required"],
    }
    actual_grant_path = write(
        tmp_path / ".task/authorization/approved-recovery-grant.json",
        json.dumps(actual_grant, indent=2, sort_keys=True) + "\n",
    )
    assert (
        authority_cli.main(
            [
                "register-grant",
                "--root",
                str(tmp_path),
                "--grant",
                str(actual_grant_path),
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["status"] == "registered"

    replacement_request_path = write(
        tmp_path / ".task/authorization/replacement-request.json",
        json.dumps(recipe["replacement_request"]),
    )
    replacement_context_path = write(
        tmp_path / ".task/authorization/replacement-context.json",
        json.dumps(context_for(workspace, recipe["replacement_request"])),
    )
    assert (
        authority_cli.main(
            [
                "evaluate",
                "--root",
                str(tmp_path),
                "--request",
                str(replacement_request_path),
                "--context",
                str(replacement_context_path),
                "--at",
                LATER,
                "--skills-root",
                str(ROOT),
            ]
        )
        == 0
    )
    replacement_before_approval = json.loads(capsys.readouterr().out)
    assert replacement_before_approval["decision"] != "allowed"
    assert replacement_before_approval["evaluated_at"] == LATER
    assert (
        authority_cli.main(
            [
                "evaluate",
                "--root",
                str(tmp_path),
                "--request",
                str(replacement_request_path),
                "--context",
                str(replacement_context_path),
                "--at",
                APPROVAL_AT,
                "--skills-root",
                str(ROOT),
            ]
        )
        == 0
    )
    replacement_decision = json.loads(capsys.readouterr().out)
    assert replacement_decision["decision"] == "allowed"
    assert replacement_decision["evaluated_at"] == APPROVAL_AT
    assert replacement_decision["request_sha256"] == handoff[
        "continuation_request_sha256"
    ]
    assert (
        authority_cli.main(
            [
                "status",
                "--root",
                str(tmp_path),
                "--request-sha256",
                handoff["continuation_request_sha256"],
                "--at",
                APPROVAL_AT,
                "--skills-root",
                str(ROOT),
            ]
        )
        == 0
    )
    continuation_status = json.loads(capsys.readouterr().out)
    assert continuation_status["workflow_state"] == "ready_to_reserve"
    assert continuation_status["should_prompt"] is False

    expired_status = status_snapshot(
        tmp_path,
        request_sha256=waiting["request_sha256"],
        evaluated_at=AFTER_EXPIRY,
        skills_root=ROOT,
    )
    assert expired_status["workflow_state"] == "source_authority_exhausted"
    assert expired_status["should_prompt"] is False
    assert expired_status["next_action"] == {
        "actor": "system",
        "code": "prepare_fresh_recovery_plan",
    }
    assert expired_status["approval_projection"] is None
    assert expired_status["wait_identity"] is None
    assert expired_status["pending_waits"] == []
    assert len(expired_status["recovery_replans"]) == 1
    assert expired_status["workflow_basis"]["kind"] == (
        "source_recovery_window_closed"
    )
    assert expired_status["workflow_basis"]["recovery_recipe"] == prepared[
        "recovery_recipe"
    ]
    assert expired_status["post_approval_handoff"]["continuation_status"] == (
        "replanning_required"
    )
    assert expired_status["wait_identity"] != refresh_wait[
        "previous_wait_identity"
    ]

    expired_resolution = resolve_operation(
        tmp_path,
        request,
        context,
        evaluated_at=AFTER_EXPIRY,
        skills_root=ROOT,
    )
    assert expired_resolution["workflow_state"] == "source_authority_exhausted"
    assert expired_resolution["should_prompt"] is False
    assert expired_resolution["next_action"]["code"] == (
        "prepare_fresh_recovery_plan"
    )
    assert expired_resolution["reason_codes"] == ["source_recovery_window_closed"]
    assert expired_resolution["approval_projection"] is None
    assert expired_resolution["wait_identity"] is None
    assert expired_resolution["recovery_identity"] == recipe["recovery_identity"]

    with pytest.raises(SystemExit, match="Conflicting authority source recovery recipe"):
        prepare_source_recovery(
            tmp_path,
            recovery_decision_ref,
            recovery_decision_sha,
            prepared_at="2026-07-17T10:06:00+09:00",
            skills_root=ROOT,
        )

    recipe["authority_status"] = "authoritative"
    recipe_path.write_text(json.dumps(recipe), encoding="utf-8")
    with pytest.raises(SystemExit, match="conflicting or stale"):
        status_snapshot(
            tmp_path,
            request_sha256=waiting["request_sha256"],
            evaluated_at=LATER,
            skills_root=ROOT,
        )
    recipe_path.unlink()
    recipe_path.symlink_to(tmp_path / "missing-recovery-recipe.json")
    with pytest.raises(SystemExit, match="must not be a symlink"):
        status_snapshot(
            tmp_path,
            request_sha256=waiting["request_sha256"],
            evaluated_at=LATER,
            skills_root=ROOT,
        )


def test_orphan_grant_projection_is_internal_source_defect(tmp_path: Path) -> None:
    workspace = replace_with_narrow_source(
        tmp_path, setup_workspace(tmp_path), ["grant-1"]
    )
    request = request_for(workspace)
    context = context_for(workspace, request)
    waiting = evaluate(tmp_path, request, context, evaluated_at=AT, skills_root=ROOT)
    persist_decision(tmp_path, waiting)
    write(tmp_path / ".task/authorization/state/grants/grant-1.json", "{}\n")

    status = status_snapshot(
        tmp_path,
        request_sha256=waiting["request_sha256"],
        evaluated_at=LATER,
        skills_root=ROOT,
    )
    assert status["workflow_state"] == "source_authority_defect"
    assert status["should_prompt"] is False
    assert status["next_action"]["code"] == "repair_source_authority_candidate"
    assert "conflicting_or_orphan_grant_projection" in status["workflow_basis"][
        "blocker_codes"
    ]


def test_status_rejects_symlinked_owned_decision_directory(tmp_path: Path) -> None:
    workspace = setup_workspace(tmp_path)
    request = request_for(workspace)
    decision = evaluate(
        tmp_path,
        request,
        context_for(workspace, request),
        evaluated_at=AT,
        skills_root=ROOT,
    )
    persist_decision(tmp_path, decision)
    directory = tmp_path / ".task/authorization/decisions"
    real = tmp_path / "real-decisions"
    directory.rename(real)
    directory.symlink_to(real, target_is_directory=True)

    with pytest.raises(SystemExit, match="must not traverse a symlink directory"):
        status_snapshot(tmp_path, evaluated_at=LATER, skills_root=ROOT)


def test_status_rejects_symlinked_source_snapshot_directory(tmp_path: Path) -> None:
    workspace = setup_workspace(tmp_path)
    request = request_for(workspace)
    decision = evaluate(
        tmp_path,
        request,
        context_for(workspace, request),
        evaluated_at=AT,
        skills_root=ROOT,
    )
    persist_decision(tmp_path, decision)
    directory = tmp_path / ".task/authorization/source_snapshots"
    real = tmp_path / "real-source-snapshots"
    directory.rename(real)
    directory.symlink_to(real, target_is_directory=True)

    with pytest.raises(SystemExit, match="must not traverse a symlink directory"):
        status_snapshot(tmp_path, evaluated_at=LATER, skills_root=ROOT)


def test_status_rejects_symlinked_owned_directory_ancestor(tmp_path: Path) -> None:
    real = tmp_path / "real-task"
    (real / "authorization").mkdir(parents=True)
    (tmp_path / ".task").symlink_to(real, target_is_directory=True)

    with pytest.raises(SystemExit, match="must not traverse a symlink directory"):
        status_snapshot(tmp_path, evaluated_at=LATER, skills_root=ROOT)


def test_status_rehashes_bound_operation_manifest(tmp_path: Path) -> None:
    workspace = setup_workspace(tmp_path)
    request = request_for(workspace)
    context = context_for(workspace, request)
    skills_root = isolated_skills_root(tmp_path)
    decision = evaluate(
        tmp_path,
        request,
        context,
        evaluated_at=AT,
        skills_root=skills_root,
    )
    persist_decision(tmp_path, decision)
    manifest = skills_root / request["skill_id"] / "authority.operations.json"
    manifest.unlink()

    with pytest.raises(SystemExit, match="operation manifest binding is stale"):
        status_snapshot(tmp_path, evaluated_at=LATER, skills_root=skills_root)


def test_exact_request_filter_ignores_only_unrelated_stale_manifest(
    tmp_path: Path,
) -> None:
    workspace = setup_workspace(tmp_path)
    skills_root = isolated_skills_root_with_unrelated_alias(tmp_path)
    unrelated, _ = persist_unrelated_decision(
        tmp_path, workspace, skills_root, stale_manifest=True
    )
    request = request_for(workspace)
    context = context_for(workspace, request)
    current = evaluate(
        tmp_path,
        request,
        context,
        evaluated_at=AT,
        skills_root=skills_root,
    )
    persist_decision(tmp_path, current)
    assert unrelated["request_sha256"] != current["request_sha256"]

    with pytest.raises(SystemExit, match="operation manifest binding is stale"):
        status_snapshot(tmp_path, evaluated_at=LATER, skills_root=skills_root)

    filtered = status_snapshot(
        tmp_path,
        request_sha256=current["request_sha256"],
        evaluated_at=LATER,
        skills_root=skills_root,
    )
    assert filtered["request_sha256_filter"] == current["request_sha256"]
    assert filtered["workflow_state"] == "source_approval_ready_for_grant"
    assert filtered["workflow_basis"]["request_sha256"] == current["request_sha256"]

    resolved = resolve_operation(
        tmp_path,
        request,
        context,
        evaluated_at=LATER,
        skills_root=skills_root,
    )
    assert resolved["workflow_state"] == "source_approval_ready_for_grant"
    assert resolved["workflow_basis"]["request_sha256"] == current["request_sha256"]


def test_exact_request_filter_rejects_same_request_stale_manifest(
    tmp_path: Path,
) -> None:
    workspace = setup_workspace(tmp_path)
    request = request_for(workspace)
    context = context_for(workspace, request)
    skills_root = isolated_skills_root(tmp_path)
    decision = evaluate(
        tmp_path,
        request,
        context,
        evaluated_at=AT,
        skills_root=skills_root,
    )
    persist_decision(tmp_path, decision)
    manifest = skills_root / request["skill_id"] / "authority.operations.json"
    manifest.write_text(
        manifest.read_text(encoding="utf-8") + "\n", encoding="utf-8"
    )

    with pytest.raises(SystemExit, match="operation manifest binding is stale"):
        status_snapshot(
            tmp_path,
            request_sha256=decision["request_sha256"],
            evaluated_at=LATER,
            skills_root=skills_root,
        )


def test_exact_request_filter_rejects_unrelated_malformed_decision(
    tmp_path: Path,
) -> None:
    workspace = setup_workspace(tmp_path)
    skills_root = isolated_skills_root_with_unrelated_alias(tmp_path)
    _, unrelated_ref = persist_unrelated_decision(
        tmp_path, workspace, skills_root, stale_manifest=False
    )
    request = request_for(workspace)
    current = evaluate(
        tmp_path,
        request,
        context_for(workspace, request),
        evaluated_at=AT,
        skills_root=skills_root,
    )
    persist_decision(tmp_path, current)
    unrelated_path = tmp_path / unrelated_ref
    malformed = json.loads(unrelated_path.read_text(encoding="utf-8"))
    malformed["unknown_field"] = True
    unrelated_path.write_text(json.dumps(malformed) + "\n", encoding="utf-8")

    with pytest.raises(SystemExit, match="decision is not closed"):
        status_snapshot(
            tmp_path,
            request_sha256=current["request_sha256"],
            evaluated_at=LATER,
            skills_root=skills_root,
        )


def test_exact_request_filter_rejects_unrelated_unsettled_intent_graph(
    tmp_path: Path,
) -> None:
    workspace = setup_workspace(tmp_path)
    unrelated_request = request_for(
        workspace,
        request_id="unrelated-intent-request",
        attempt_id="unrelated-intent-attempt",
        idempotency_key="unrelated-intent-request-key",
    )
    register_grant(
        tmp_path, grant_for(workspace, unrelated_request, max_uses=2)
    )
    unrelated = evaluate(
        tmp_path,
        unrelated_request,
        context_for(workspace, unrelated_request),
        evaluated_at=AT,
        skills_root=ROOT,
    )
    unrelated_ref, unrelated_sha = persist_decision(tmp_path, unrelated)
    reserved = reserve(
        tmp_path,
        unrelated_ref,
        unrelated_sha,
        reserved_at=LATER,
        idempotency_key="unrelated-unsettled-reservation",
        skills_root=ROOT,
    )
    current_request = request_for(
        workspace,
        request_id="current-filter-request",
        attempt_id="current-filter-attempt",
        idempotency_key="current-filter-request-key",
    )
    current = evaluate(
        tmp_path,
        current_request,
        context_for(workspace, current_request),
        evaluated_at=LATER,
        skills_root=ROOT,
    )
    persist_decision(tmp_path, current)
    regressed = next(
        change
        for change in reserved["reservation"]["state_changes"]
        if "/state/grants/" in f"/{change['ref']}"
    )
    (tmp_path / regressed["ref"]).write_text(
        json.dumps(regressed["before"], sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(SystemExit, match="intent replay is not settled"):
        status_snapshot(
            tmp_path,
            request_sha256=current["request_sha256"],
            evaluated_at=LATER,
            skills_root=ROOT,
        )


@pytest.mark.parametrize(
    ("lifecycle_state", "expected_workflow_state", "settlement_directory"),
    [
        ("reserved", "ready_to_resume", None),
        ("consumed", "already_consumed", "use_receipts"),
        ("released", "already_released", "release_receipts"),
    ],
)
def test_exact_request_filter_preserves_current_lifecycle_precedence_and_basis(
    tmp_path: Path,
    lifecycle_state: str,
    expected_workflow_state: str,
    settlement_directory: str | None,
) -> None:
    workspace = setup_workspace(tmp_path)
    skills_root = isolated_skills_root_with_unrelated_alias(tmp_path)
    persist_unrelated_decision(
        tmp_path, workspace, skills_root, stale_manifest=True
    )
    request = request_for(workspace)
    register_grant(tmp_path, grant_for(workspace, request))
    current = evaluate(
        tmp_path,
        request,
        context_for(workspace, request),
        evaluated_at=AT,
        skills_root=skills_root,
    )
    decision_ref, decision_sha = persist_decision(tmp_path, current)
    reserved = reserve(
        tmp_path,
        decision_ref,
        decision_sha,
        reserved_at=LATER,
        idempotency_key=f"current-{lifecycle_state}-reservation",
        skills_root=skills_root,
    )
    if lifecycle_state == "consumed":
        result = write(
            tmp_path / ".task/authorization/results/current-consumed.json", "{}\n"
        )
        consume(
            tmp_path,
            reserved["reservation_ref"],
            reserved["reservation_sha256"],
            {"ref": str(result.relative_to(tmp_path)), "sha256": sha256_file(result)},
            consumed_at=LATER,
            expected_version=0,
            idempotency_key="current-consumed-settlement",
            skills_root=skills_root,
        )
    elif lifecycle_state == "released":
        evidence = write(
            tmp_path / ".task/authorization/results/current-released.json", "{}\n"
        )
        release(
            tmp_path,
            reserved["reservation_ref"],
            reserved["reservation_sha256"],
            {
                "ref": str(evidence.relative_to(tmp_path)),
                "sha256": sha256_file(evidence),
            },
            released_at=LATER,
            expected_version=0,
            idempotency_key="current-released-settlement",
            effect_status="verified_no_effect",
        )

    filtered = status_snapshot(
        tmp_path,
        request_sha256=current["request_sha256"],
        evaluated_at=LATER,
        skills_root=skills_root,
    )
    assert filtered["workflow_state"] == expected_workflow_state
    assert filtered["workflow_basis"]["request_sha256"] == current["request_sha256"]
    assert filtered["workflow_basis"]["reservation"]["ref"] == reserved[
        "reservation_ref"
    ]
    settlement = filtered["workflow_basis"]["settlement_receipt"]
    if settlement_directory is None:
        assert settlement is None
    else:
        assert f"/{settlement_directory}/" in f"/{settlement['ref']}"


def test_resolve_rejects_tampered_bound_operation_manifest(tmp_path: Path) -> None:
    workspace = setup_workspace(tmp_path)
    request = request_for(workspace)
    context = context_for(workspace, request)
    skills_root = isolated_skills_root(tmp_path)
    decision = evaluate(
        tmp_path,
        request,
        context,
        evaluated_at=AT,
        skills_root=skills_root,
    )
    persist_decision(tmp_path, decision)
    manifest = skills_root / request["skill_id"] / "authority.operations.json"
    manifest.write_text(
        manifest.read_text(encoding="utf-8") + "\n", encoding="utf-8"
    )

    with pytest.raises(SystemExit, match="operation manifest binding is stale"):
        resolve_operation(
            tmp_path,
            request,
            context,
            evaluated_at=LATER,
            skills_root=skills_root,
        )


def test_status_rejects_allowed_decision_when_operation_identity_disappears(
    tmp_path: Path,
) -> None:
    workspace = setup_workspace(tmp_path)
    request = request_for(workspace)
    context = context_for(workspace, request)
    skills_root = isolated_skills_root(tmp_path)
    register_grant(tmp_path, grant_for(workspace, request))
    decision = evaluate(
        tmp_path,
        request,
        context,
        evaluated_at=AT,
        skills_root=skills_root,
    )
    manifest = skills_root / request["skill_id"] / "authority.operations.json"
    body = json.loads(manifest.read_text(encoding="utf-8"))
    for operation in body["operations"]:
        if operation["operation_id"] == request["operation_id"]:
            operation["operation_id"] = "renamed_operation"
            break
    manifest.write_text(json.dumps(body, sort_keys=True) + "\n", encoding="utf-8")
    decision["operation_manifest"]["sha256"] = sha256_file(manifest)
    core = {key: value for key, value in decision.items() if key != "decision_id"}
    decision["decision_id"] = f"authd-{object_sha256(core)[:24]}"
    persist_decision(tmp_path, decision)

    with pytest.raises(SystemExit, match="operation identity is no longer valid"):
        status_snapshot(tmp_path, evaluated_at=LATER, skills_root=skills_root)


def test_status_suppresses_superseded_wait_and_reports_full_lifecycle(
    tmp_path: Path,
) -> None:
    workspace = setup_workspace(tmp_path)
    request = request_for(workspace)
    context = context_for(workspace, request)
    waiting = evaluate(tmp_path, request, context, evaluated_at=AT, skills_root=ROOT)
    persist_decision(tmp_path, waiting)
    register_grant(tmp_path, grant_for(workspace, request))
    allowed = evaluate(tmp_path, request, context, evaluated_at=AT, skills_root=ROOT)
    decision_ref, decision_sha = persist_decision(tmp_path, allowed)
    ready = status_snapshot(
        tmp_path,
        request_sha256=allowed["request_sha256"],
        evaluated_at=LATER,
        skills_root=ROOT,
    )
    assert ready["workflow_state"] == "ready_to_reserve"
    assert ready["should_prompt"] is False
    assert ready["pending_waits"] == []
    assert ready["workflow_basis"]["decision"]["ref"] == decision_ref
    assert len(ready["historical_waits"]) == 1
    reserved = reserve(
        tmp_path,
        decision_ref,
        decision_sha,
        reserved_at=LATER,
        idempotency_key="status-reserve",
        skills_root=ROOT,
    )
    before = status_snapshot(
        tmp_path,
        request_sha256=allowed["request_sha256"],
        evaluated_at=LATER,
    )
    assert before["workflow_state"] == "ready_to_resume"
    assert before["outcome"] == before["workflow_state"]
    assert before["should_prompt"] is False
    assert before["user_action"] is None
    assert before["pending_waits"] == []
    assert len(before["historical_waits"]) == 1
    result_path = write(
        tmp_path / ".task/authorization/results/status-result.json", "{}\n"
    )
    consume(
        tmp_path,
        reserved["reservation_ref"],
        reserved["reservation_sha256"],
        {"ref": str(result_path.relative_to(tmp_path)), "sha256": sha256_file(result_path)},
        consumed_at=LATER,
        expected_version=0,
        idempotency_key="status-consume",
        skills_root=ROOT,
    )
    after = status_snapshot(
        tmp_path,
        request_sha256=allowed["request_sha256"],
        evaluated_at=LATER,
    )
    assert after["workflow_state"] == "already_consumed"
    assert after["outcome"] == after["workflow_state"]
    assert after["should_prompt"] is False
    assert after["verifications"]
    assert after["execution_results"]
    assert after["use_receipts"]


def test_status_marks_child_unusable_when_parent_is_suspended(tmp_path: Path) -> None:
    workspace = setup_workspace(tmp_path)
    request = request_for(workspace)
    parent = grant_for(
        workspace,
        request,
        grant_id="grant-parent",
        holder_rank="S1",
        max_uses=2,
    )
    parent_result = register_grant(tmp_path, parent)
    child = grant_for(
        workspace,
        request,
        grant_id="grant-child",
        issuer_rank="S1",
        holder_rank="S0",
        parent_grant_id="grant-parent",
        max_uses=2,
    )
    child["source_approval"] = {
        "ref": ".task/authorization/grants/grant-parent.json",
        "sha256": parent_result["grant_sha256"],
    }
    register_grant(tmp_path, child, parent_id="grant-parent")
    transition_grants(
        tmp_path,
        "grant-parent",
        "suspended",
        event_id="suspend-parent-for-status",
        expected_version=0,
        source_approval=workspace["source_binding"],
        transitioned_at=LATER,
    )
    child_status = status_snapshot(
        tmp_path, grant_id="grant-child", evaluated_at=LATER
    )["grants"][0]
    assert child_status["state"]["status"] == "active"
    assert child_status["effective_usable"] is False
    assert child_status["lineage_blocker_codes"] == [
        "ancestor_grant_suspended:grant-parent"
    ]


def test_status_uses_one_time_for_grant_and_ancestor_windows(tmp_path: Path) -> None:
    workspace = setup_workspace(tmp_path)
    request = request_for(workspace)
    parent = grant_for(
        workspace,
        request,
        grant_id="grant-parent",
        holder_rank="S1",
        max_uses=2,
    )
    parent_result = register_grant(tmp_path, parent)
    child = grant_for(
        workspace,
        request,
        grant_id="grant-child",
        issuer_rank="S1",
        holder_rank="S0",
        parent_grant_id="grant-parent",
        max_uses=2,
    )
    child["source_approval"] = {
        "ref": ".task/authorization/grants/grant-parent.json",
        "sha256": parent_result["grant_sha256"],
    }
    register_grant(tmp_path, child, parent_id="grant-parent")

    early_at = "2026-07-17T09:59:59+09:00"
    early = status_snapshot(
        tmp_path, grant_id="grant-child", evaluated_at=early_at
    )
    assert early["evaluated_at"] == early_at
    assert early["grants"][0]["lineage_blocker_codes"] == [
        "grant_not_yet_active",
        "ancestor_grant_not_yet_active:grant-parent",
    ]

    expired = status_snapshot(
        tmp_path, grant_id="grant-child", evaluated_at=EXPIRY
    )
    assert expired["evaluated_at"] == EXPIRY
    assert expired["grants"][0]["lineage_blocker_codes"] == [
        "grant_time_expired",
        "ancestor_grant_time_expired:grant-parent",
    ]


def test_status_does_not_resume_reserved_operation_after_expiry(tmp_path: Path) -> None:
    reserved = reserve_default_operation(tmp_path, idempotency_key="expiry-reserve")

    status = status_snapshot(
        tmp_path,
        request_sha256=reserved["reservation"]["request_sha256"],
        evaluated_at=EXPIRY,
        skills_root=ROOT,
    )
    assert status["workflow_state"] == "reserved_authority_recovery"
    assert status["should_prompt"] is False
    assert status["resumable_reservations"] == []
    assert status["blocked_reservations"][0]["authority_blocker_codes"] == [
        "selected_grant_time_expired:grant-1"
    ]
    assert status["release_receipts"] == []
    assert status["workflow_basis"]["reservation"]["ref"] == reserved[
        "reservation_ref"
    ]
    assert status["workflow_basis"]["reservation_state"]["sha256"]


def test_status_does_not_resume_when_reserved_ancestor_is_suspended(
    tmp_path: Path,
) -> None:
    workspace = setup_workspace(tmp_path)
    request = request_for(workspace)
    context = context_for(workspace, request)
    parent = grant_for(
        workspace,
        request,
        grant_id="grant-parent",
        holder_rank="S1",
        max_uses=2,
    )
    parent_result = register_grant(tmp_path, parent)
    child = grant_for(
        workspace,
        request,
        grant_id="grant-child",
        issuer_rank="S1",
        holder_rank="S0",
        parent_grant_id="grant-parent",
        max_uses=2,
    )
    child["source_approval"] = {
        "ref": ".task/authorization/grants/grant-parent.json",
        "sha256": parent_result["grant_sha256"],
    }
    register_grant(tmp_path, child, parent_id="grant-parent")
    decision = evaluate(tmp_path, request, context, evaluated_at=AT, skills_root=ROOT)
    decision_ref, decision_sha = persist_decision(tmp_path, decision)
    reserve(
        tmp_path,
        decision_ref,
        decision_sha,
        reserved_at=LATER,
        idempotency_key="ancestor-reserve",
        skills_root=ROOT,
    )
    transition_grants(
        tmp_path,
        "grant-parent",
        "suspended",
        event_id="suspend-reserved-parent",
        expected_version=1,
        source_approval=workspace["source_binding"],
        transitioned_at=LATER,
    )

    status = status_snapshot(
        tmp_path,
        request_sha256=decision["request_sha256"],
        evaluated_at=LATER,
        skills_root=ROOT,
    )
    assert status["workflow_state"] == "reserved_authority_recovery"
    assert status["blocked_reservations"][0]["authority_blocker_codes"] == [
        "ancestor_grant_status_suspended:grant-parent"
    ]
    state_path = tmp_path / status["workflow_basis"]["reservation_state"]["ref"]
    assert json.loads(state_path.read_text(encoding="utf-8"))["status"] == "reserved"
    assert status["release_receipts"] == []


def test_status_returns_exact_verified_no_effect_settlement(tmp_path: Path) -> None:
    reserved = reserve_default_operation(tmp_path, idempotency_key="release-reserve")
    evidence = write(tmp_path / ".task/authorization/results/no-effect.json", "{}\n")
    released = release(
        tmp_path,
        reserved["reservation_ref"],
        reserved["reservation_sha256"],
        {
            "ref": str(evidence.relative_to(tmp_path)),
            "sha256": sha256_file(evidence),
        },
        released_at=LATER,
        expected_version=0,
        idempotency_key="release-settlement",
        effect_status="verified_no_effect",
    )

    status = status_snapshot(
        tmp_path,
        request_sha256=reserved["reservation"]["request_sha256"],
        evaluated_at=LATER,
        skills_root=ROOT,
    )
    assert status["workflow_state"] == "already_released"
    assert status["should_prompt"] is False
    assert status["next_action"]["code"] == "return_existing_no_effect_settlement"
    assert status["workflow_basis"]["settlement_receipt"]["ref"] == released["ref"]
    assert status["workflow_basis"]["settlement_receipt"]["sha256"] == released[
        "sha256"
    ]
    reservation_artifact = json.loads(
        (tmp_path / reserved["reservation_ref"]).read_text(encoding="utf-8")
    )
    decision = json.loads(
        (tmp_path / reservation_artifact["decision"]["ref"]).read_text(
            encoding="utf-8"
        )
    )
    resolved = resolve_operation(
        tmp_path,
        decision["request"],
        decision["evaluation_context"],
        evaluated_at=LATER,
        skills_root=ROOT,
    )
    assert resolved["workflow_state"] == "already_released"
    assert resolved["workflow_basis"]["settlement_receipt"]["ref"] == released["ref"]


def test_status_cli_accepts_deterministic_evaluation_time(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert (
        authority_cli.main(
            [
                "status",
                "--root",
                str(tmp_path),
                "--at",
                AT,
                "--skills-root",
                str(ROOT),
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["evaluated_at"] == AT


def test_status_rejects_malformed_decision(tmp_path: Path) -> None:
    workspace = setup_workspace(tmp_path)
    request = request_for(workspace)
    context = context_for(workspace, request)
    decision = evaluate(tmp_path, request, context, evaluated_at=AT, skills_root=ROOT)
    decision_ref, _ = persist_decision(tmp_path, decision)
    pending = status_snapshot(tmp_path, evaluated_at=LATER, skills_root=ROOT)
    assert (
        pending["outcome"]
        == pending["workflow_state"]
        == "source_approval_ready_for_grant"
    )
    assert pending["should_prompt"] is False
    assert pending["user_action"] is None
    assert pending["workflow_basis"]["source_approval"]["ref"]
    assert pending["workflow_basis"]["source_approval"][
        "materializable_grant_ids"
    ]
    path = tmp_path / decision_ref
    malformed = json.loads(path.read_text(encoding="utf-8"))
    malformed["unknown_field"] = True
    path.write_text(json.dumps(malformed) + "\n", encoding="utf-8")

    with pytest.raises(SystemExit, match="decision is not closed"):
        status_snapshot(tmp_path, evaluated_at=LATER)
    with pytest.raises(SystemExit, match="decision is not closed"):
        resolve_operation(
            tmp_path,
            request,
            context,
            evaluated_at=LATER,
            skills_root=ROOT,
        )


def test_status_rejects_malformed_reservation(tmp_path: Path) -> None:
    reserved = reserve_default_operation(
        tmp_path, idempotency_key="malformed-reservation"
    )
    path = tmp_path / reserved["reservation_ref"]
    malformed = json.loads(path.read_text(encoding="utf-8"))
    malformed["unknown_field"] = True
    path.write_text(json.dumps(malformed) + "\n", encoding="utf-8")

    with pytest.raises(SystemExit, match="reservation is not closed"):
        status_snapshot(tmp_path, evaluated_at=LATER)


def test_status_rejects_malformed_release_receipt(tmp_path: Path) -> None:
    reserved = reserve_default_operation(tmp_path, idempotency_key="receipt-reserve")
    evidence = write(tmp_path / ".task/authorization/results/no-effect.json", "{}\n")
    released = release(
        tmp_path,
        reserved["reservation_ref"],
        reserved["reservation_sha256"],
        {
            "ref": str(evidence.relative_to(tmp_path)),
            "sha256": sha256_file(evidence),
        },
        released_at=LATER,
        expected_version=0,
        idempotency_key="malformed-release-receipt",
        effect_status="verified_no_effect",
    )
    path = tmp_path / released["ref"]
    malformed = json.loads(path.read_text(encoding="utf-8"))
    malformed["unknown_field"] = True
    path.write_text(json.dumps(malformed) + "\n", encoding="utf-8")

    with pytest.raises(SystemExit, match="release receipt is not closed"):
        status_snapshot(tmp_path, evaluated_at=LATER)


def test_status_rejects_malformed_grant_state(tmp_path: Path) -> None:
    workspace = setup_workspace(tmp_path)
    request = request_for(workspace)
    register_grant(tmp_path, grant_for(workspace, request))
    path = tmp_path / ".task/authorization/state/grants/grant-1.json"
    malformed = json.loads(path.read_text(encoding="utf-8"))
    malformed["unknown_field"] = True
    path.write_text(json.dumps(malformed) + "\n", encoding="utf-8")

    with pytest.raises(SystemExit, match="grant state is not closed"):
        status_snapshot(tmp_path, evaluated_at=LATER)


def test_cli_failures_use_stable_structured_json(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = authority_cli.main(
        [
            "snapshot-source",
            "--root",
            str(tmp_path),
            "--source-ref",
            ".task/authorization/missing.json",
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    assert code == 2
    assert payload["status"] == "error"
    assert payload["command"] == "snapshot-source"
    assert payload["error"]["code"] == "authority_operation_failed"
    assert payload["error"]["user_action_required"] is False


def test_subject_change_is_rejected_at_reserve_preflight(tmp_path: Path) -> None:
    workspace = setup_workspace(tmp_path)
    request = request_for(workspace)
    context = context_for(workspace, request)
    register_grant(tmp_path, grant_for(workspace, request))
    decision = evaluate(tmp_path, request, context, evaluated_at=AT, skills_root=ROOT)
    decision_ref, decision_sha = persist_decision(tmp_path, decision)
    write(workspace["task"], "# Task\n\nChanged after decision.\n")
    with pytest.raises(SystemExit, match="subject changed"):
        reserve(
            tmp_path,
            decision_ref,
            decision_sha,
            reserved_at=LATER,
            idempotency_key="reserve-key",
            skills_root=ROOT,
        )


def test_subject_deletion_is_rejected_at_reserve_preflight(tmp_path: Path) -> None:
    workspace = setup_workspace(tmp_path)
    request = request_for(workspace)
    context = context_for(workspace, request)
    register_grant(tmp_path, grant_for(workspace, request))
    decision = evaluate(tmp_path, request, context, evaluated_at=AT, skills_root=ROOT)
    decision_ref, decision_sha = persist_decision(tmp_path, decision)
    workspace["task"].unlink()

    with pytest.raises(SystemExit, match="does not identify an existing path"):
        reserve(
            tmp_path,
            decision_ref,
            decision_sha,
            reserved_at=LATER,
            idempotency_key="reserve-key",
            skills_root=ROOT,
        )


def test_subject_directory_replacement_is_rejected_at_reserve_preflight(
    tmp_path: Path,
) -> None:
    workspace = setup_workspace(tmp_path)
    request = request_for(workspace)
    context = context_for(workspace, request)
    register_grant(tmp_path, grant_for(workspace, request))
    decision = evaluate(tmp_path, request, context, evaluated_at=AT, skills_root=ROOT)
    decision_ref, decision_sha = persist_decision(tmp_path, decision)
    workspace["task"].unlink()
    workspace["task"].mkdir()

    with pytest.raises(SystemExit, match="does not identify an existing path"):
        reserve(
            tmp_path,
            decision_ref,
            decision_sha,
            reserved_at=LATER,
            idempotency_key="reserve-key",
            skills_root=ROOT,
        )


def test_subject_symlink_replacement_is_rejected_at_reserve_preflight(
    tmp_path: Path,
) -> None:
    workspace = setup_workspace(tmp_path)
    request = request_for(workspace)
    context = context_for(workspace, request)
    register_grant(tmp_path, grant_for(workspace, request))
    decision = evaluate(tmp_path, request, context, evaluated_at=AT, skills_root=ROOT)
    decision_ref, decision_sha = persist_decision(tmp_path, decision)
    replacement = write(tmp_path / "replacement-task.md", workspace["task"].read_text())
    workspace["task"].unlink()
    workspace["task"].symlink_to(replacement)

    with pytest.raises(SystemExit, match="symlink component"):
        reserve(
            tmp_path,
            decision_ref,
            decision_sha,
            reserved_at=LATER,
            idempotency_key="reserve-key",
            skills_root=ROOT,
        )


def test_delegation_is_subset_only_and_revocation_cascades(tmp_path: Path) -> None:
    workspace = setup_workspace(tmp_path)
    request = request_for(workspace)
    parent = grant_for(
        workspace,
        request,
        grant_id="grant-parent",
        issuer_rank="S3",
        holder_rank="S2",
        max_uses=3,
    )
    parent_result = register_grant(tmp_path, parent)
    child = grant_for(
        workspace,
        request,
        grant_id="grant-child",
        issuer_rank="S2",
        holder_rank="S0",
        parent_grant_id="grant-parent",
        max_uses=1,
    )
    child["source_approval"] = {
        "ref": ".task/authorization/grants/grant-parent.json",
        "sha256": parent_result["grant_sha256"],
    }
    register_grant(tmp_path, child, parent_id="grant-parent")

    expanded = {
        **child,
        "grant_id": "grant-expanded",
        "capabilities": ["implementation.local.edit", "execution.external.provider"],
    }
    with pytest.raises(SystemExit, match="capabilities must be a subset"):
        register_grant(tmp_path, expanded, parent_id="grant-parent")

    escaped_task_scope = {**child, "grant_id": "grant-scope-escape", "task_id": None}
    with pytest.raises(SystemExit, match="bounded task scope"):
        register_grant(tmp_path, escaped_task_scope, parent_id="grant-parent")

    transition_grants(
        tmp_path,
        "grant-parent",
        "revoked",
        event_id="revoke-1",
        expected_version=0,
        source_approval=workspace["source_binding"],
        transitioned_at=LATER,
    )
    assert load_grant(tmp_path, "grant-parent")[2]["status"] == "revoked"
    assert load_grant(tmp_path, "grant-child")[2]["status"] == "revoked"


def test_suspended_grant_has_explicit_unexpired_reactivation_path(
    tmp_path: Path,
) -> None:
    workspace = setup_workspace(tmp_path)
    request = request_for(workspace)
    register_grant(tmp_path, grant_for(workspace, request))

    transition_grants(
        tmp_path,
        "grant-1",
        "suspended",
        event_id="suspend-1",
        expected_version=0,
        source_approval=workspace["source_binding"],
        transitioned_at=LATER,
    )
    assert load_grant(tmp_path, "grant-1")[2]["status"] == "suspended"

    transition_grants(
        tmp_path,
        "grant-1",
        "reactivated",
        event_id="reactivate-1",
        expected_version=1,
        source_approval=workspace["source_binding"],
        transitioned_at=LATER,
    )
    state = load_grant(tmp_path, "grant-1")[2]
    assert state["status"] == "active"
    assert state["version"] == 2


def test_transition_api_rejects_expiry_before_exact_grant_expiry(
    tmp_path: Path,
) -> None:
    workspace = setup_workspace(tmp_path)
    request = request_for(workspace)
    register_grant(tmp_path, grant_for(workspace, request))

    with pytest.raises(SystemExit, match="cannot expire before its exact expires_at"):
        transition_grants(
            tmp_path,
            "grant-1",
            "expired",
            event_id="expire-too-early",
            expected_version=0,
            source_approval=workspace["source_binding"],
            transitioned_at=LATER,
        )

    state = load_grant(tmp_path, "grant-1")[2]
    assert state["status"] == "active"
    assert state["version"] == 0
    assert not (tmp_path / ".task/authorization/events/expire-too-early.json").exists()


def test_explicit_composition_is_required_for_capability_union(tmp_path: Path) -> None:
    workspace = setup_workspace(tmp_path)
    request = request_for(
        workspace,
        required_capabilities=["implementation.local.edit", "task.state.advance"],
    )
    context = context_for(workspace, request)
    register_grant(
        tmp_path,
        grant_for(
            workspace,
            request,
            grant_id="grant-a",
            capabilities=["implementation.local.edit"],
        ),
    )
    register_grant(
        tmp_path,
        grant_for(
            workspace, request, grant_id="grant-b", capabilities=["task.state.advance"]
        ),
    )
    without = evaluate(tmp_path, request, context, evaluated_at=AT, skills_root=ROOT)
    assert without["decision"] == "approval_required"
    with pytest.raises(SystemExit, match="exact base request digest"):
        create_composition(
            tmp_path,
            {
                "schema_version": 2,
                "artifact_kind": "authority_grant_composition",
                "composition_id": "composition-unapproved",
                "request_sha256": object_sha256(request),
                "grant_ids": ["grant-a", "grant-b"],
                "source_approval": workspace["source_binding"],
                "created_at": AT,
                "idempotency_key": "composition-unapproved-key",
            },
        )
    composition_approval_body = json.loads(
        workspace["approval"].read_text(encoding="utf-8")
    )
    composition_approval_body["approval_id"] = "composition-approval-1"
    composition_approval_body["request_digests"] = [object_sha256(request)]
    composition_approval_file = write(
        tmp_path / ".task/authorization/composition-approval.json",
        json.dumps(composition_approval_body, indent=2, sort_keys=True) + "\n",
    )
    composition_source = snapshot_file(
        tmp_path,
        str(composition_approval_file.relative_to(tmp_path)),
        "source_approval",
    )
    composition = create_composition(
        tmp_path,
        {
            "schema_version": 2,
            "artifact_kind": "authority_grant_composition",
            "composition_id": "composition-1",
            "request_sha256": object_sha256(request),
            "grant_ids": ["grant-a", "grant-b"],
            "source_approval": composition_source,
            "created_at": AT,
            "idempotency_key": "composition-key",
        },
    )
    request["composition_receipt"] = {
        "ref": composition["ref"],
        "sha256": composition["sha256"],
    }
    allowed = evaluate(tmp_path, request, context, evaluated_at=AT, skills_root=ROOT)
    assert allowed["decision"] == "allowed"
    assert [item["grant_id"] for item in allowed["selected_grants"]] == [
        "grant-a",
        "grant-b",
    ]


def test_unknown_effect_quarantines_and_does_not_restore_budget(tmp_path: Path) -> None:
    workspace = setup_workspace(tmp_path)
    request = request_for(workspace)
    context = context_for(workspace, request)
    register_grant(tmp_path, grant_for(workspace, request))
    decision = evaluate(tmp_path, request, context, evaluated_at=AT, skills_root=ROOT)
    decision_ref, decision_sha = persist_decision(tmp_path, decision)
    reserved = reserve(
        tmp_path,
        decision_ref,
        decision_sha,
        reserved_at=LATER,
        idempotency_key="reserve-key",
        skills_root=ROOT,
    )
    evidence = write(tmp_path / ".task/authorization/results/unknown.json", "{}\n")
    outcome = release(
        tmp_path,
        reserved["reservation_ref"],
        reserved["reservation_sha256"],
        {"ref": str(evidence.relative_to(tmp_path)), "sha256": sha256_file(evidence)},
        released_at=LATER,
        expected_version=0,
        idempotency_key="release-key",
        effect_status="unknown_effect",
    )
    assert outcome["release_receipt"]["release_applied"] is False
    _, _, grant_state = load_grant(tmp_path, "grant-1")
    assert grant_state["reserved_uses"] == 1
    reservation_state = json.loads(
        (
            tmp_path
            / ".task/authorization/state/reservations"
            / f"{reserved['reservation']['reservation_id']}.json"
        ).read_text(encoding="utf-8")
    )
    assert reservation_state["status"] == "quarantined_unknown_effect"


def test_typed_intents_and_risk_acceptance_remain_separate(tmp_path: Path) -> None:
    workspace = setup_workspace(tmp_path)
    request = request_for(workspace)
    register_grant(tmp_path, grant_for(workspace, request))

    ratification = request_for(workspace, intent_type="ratify_goal_truth")
    ratification_result = evaluate(
        tmp_path,
        ratification,
        context_for(workspace, ratification),
        evaluated_at=AT,
        skills_root=ROOT,
    )
    assert ratification_result["decision"] == "approval_required"
    assert (
        "goal_truth_ratification_requires_goal_owner_decision"
        in ratification_result["reason_codes"]
    )
    ratification_projection = ratification_result["approval_projection"]
    assert ratification_projection["typed_intent"] == "ratify_goal_truth"
    assert "change_goal_truth" not in ratification_projection["excluded_effects"]

    risk_request = request_for(workspace, risk_tier="R2")
    risk_request["context"]["risk_acceptance_status"] = "unresolved"
    risk_result = evaluate(
        tmp_path,
        risk_request,
        context_for(workspace, risk_request),
        evaluated_at=AT,
        skills_root=ROOT,
    )
    assert risk_result["decision"] == "approval_required"
    assert risk_result["reason_codes"] == ["risk_acceptance_unresolved"]
    risk_projection = risk_result["approval_projection"]
    assert risk_projection["typed_intent"] == "accept_risk_or_cost"
    assert "accept_risk_or_cost" not in risk_projection["excluded_effects"]


def test_design_wait_projects_only_design_selection_intent(tmp_path: Path) -> None:
    workspace = setup_workspace(tmp_path)
    skills_root = tmp_path / "skills"
    manifest = json.loads(
        (ROOT / "manage-agent-authority/authority.operations.json").read_text(
            encoding="utf-8"
        )
    )
    operation = {
        **manifest["operations"][5],
        "operation_id": "choose_design",
        "required_capabilities": ["implementation.local.edit"],
        "source_rank_floor": "S1",
        "risk_floor": "R1",
        "decision_class": "D1",
        "effect_classes": ["edit_local"],
        "data_classes": ["repository_code"],
        "reversibility": "conditionally_reversible",
        "subject_kinds": ["task"],
        "authorization_mechanism": "grant",
        "authority_applicability": "required",
    }
    write(
        skills_root / "design-skill/authority.operations.json",
        json.dumps(
            {
                "schema_version": 2,
                "manifest_kind": "authority_operations",
                "skill_id": "design-skill",
                "skill_version": "1.0.0",
                "operations": [operation],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
    )
    request = request_for(
        workspace,
        skill_id="design-skill",
        skill_version="1.0.0",
        operation_id="choose_design",
        decision_class="D1",
    )
    request["context"]["design_selection_status"] = "unresolved"
    result = evaluate(
        tmp_path,
        request,
        context_for(workspace, request),
        evaluated_at=AT,
        skills_root=skills_root,
    )
    assert result["decision"] == "approval_required"
    projection = result["approval_projection"]
    assert projection["typed_intent"] == "select_design_option"
    assert "select_design_option" not in projection["excluded_effects"]


def test_positive_typed_status_requires_exact_immutable_evidence(
    tmp_path: Path,
) -> None:
    workspace = setup_workspace(tmp_path)
    base = request_for(workspace)
    register_grant(tmp_path, grant_for(workspace, base))

    available = request_for(workspace)
    available["context"]["external_input_status"] = "available"
    with pytest.raises(SystemExit, match="external_input_evidence is required"):
        evaluate(
            tmp_path,
            available,
            context_for(workspace, available),
            evaluated_at=AT,
            skills_root=ROOT,
        )
    evidence = write(
        tmp_path / ".task/authorization/evidence/external-input.json", "{}\n"
    )
    available["context"]["external_input_evidence"] = {
        "ref": str(evidence.relative_to(tmp_path)),
        "sha256": "0" * 64,
    }
    with pytest.raises(SystemExit, match="external_input_evidence SHA-256"):
        evaluate(
            tmp_path,
            available,
            context_for(workspace, available),
            evaluated_at=AT,
            skills_root=ROOT,
        )
    available["context"]["external_input_evidence"]["sha256"] = sha256_file(evidence)
    assert (
        evaluate(
            tmp_path,
            available,
            context_for(workspace, available),
            evaluated_at=AT,
            skills_root=ROOT,
        )["decision"]
        == "allowed"
    )

    resolved = request_for(workspace, risk_tier="R2")
    resolved["context"]["risk_acceptance_status"] = "resolved"
    with pytest.raises(SystemExit, match="risk_acceptance_evidence is required"):
        evaluate(
            tmp_path,
            resolved,
            context_for(workspace, resolved),
            evaluated_at=AT,
            skills_root=ROOT,
        )


def test_unverified_typed_status_routes_classification_repair(tmp_path: Path) -> None:
    workspace = setup_workspace(tmp_path)
    request = request_for(workspace, risk_tier="R2")
    request["context"]["risk_acceptance_status"] = "unverified"
    result = evaluate(
        tmp_path,
        request,
        context_for(workspace, request),
        evaluated_at=AT,
        skills_root=ROOT,
    )
    assert result["decision"] == "classification_repair"
    assert result["reason_codes"] == ["risk_acceptance_status_unverified"]


def test_exact_operation_scope_prevents_task_authority_from_becoming_action_authority(
    tmp_path: Path,
) -> None:
    workspace = setup_workspace(tmp_path)
    implementation_request = request_for(workspace)
    task_grant = grant_for(workspace, implementation_request)
    task_grant["operations"] = [
        {
            "skill_id": "derive-improvement-task",
            "skill_version": "2.0.0",
            "operation_id": "publish_task",
            "operation_version": "1",
        }
    ]
    task_grant["capabilities"] = ["task.scope.publish"]
    register_grant(tmp_path, task_grant)
    result = evaluate(
        tmp_path,
        implementation_request,
        context_for(workspace, implementation_request),
        evaluated_at=AT,
        skills_root=ROOT,
    )
    assert result["decision"] == "approval_required"
    assert result["selected_grants"] == []


def test_expiry_and_finite_reuse_are_enforced(tmp_path: Path) -> None:
    workspace = setup_workspace(tmp_path)
    request = request_for(workspace)
    grant = grant_for(
        workspace,
        request,
        max_uses=2,
        expires_at=EXPIRY,
    )
    register_grant(tmp_path, grant)
    expired = evaluate(
        tmp_path,
        request,
        context_for(workspace, request),
        evaluated_at=EXPIRY,
        skills_root=ROOT,
    )
    assert expired["decision"] == "approval_required"


def test_bounded_reusable_grant_consumes_exact_counter(tmp_path: Path) -> None:
    workspace = setup_workspace(tmp_path)
    base_request = request_for(workspace)
    register_grant(
        tmp_path,
        grant_for(workspace, base_request, max_uses=2, expires_at=EXPIRY),
    )
    for index in (1, 2):
        request = request_for(
            workspace,
            request_id=f"request-{index}",
            attempt_id=f"attempt-{index}",
            idempotency_key=f"request-key-{index}",
        )
        context = context_for(workspace, request)
        decision = evaluate(
            tmp_path, request, context, evaluated_at=AT, skills_root=ROOT
        )
        assert decision["decision"] == "allowed"
        decision_ref, decision_sha = persist_decision(tmp_path, decision)
        reserved = reserve(
            tmp_path,
            decision_ref,
            decision_sha,
            reserved_at=LATER,
            idempotency_key=f"reserve-{index}",
            skills_root=ROOT,
        )
        result = write(
            tmp_path / f".task/authorization/results/result-{index}.json",
            "{}\n",
        )
        consume(
            tmp_path,
            reserved["reservation_ref"],
            reserved["reservation_sha256"],
            {"ref": str(result.relative_to(tmp_path)), "sha256": sha256_file(result)},
            consumed_at=LATER,
            expected_version=0,
            idempotency_key=f"consume-{index}",
            skills_root=ROOT,
        )
    _, _, state = load_grant(tmp_path, "grant-1")
    assert state["remaining_uses"] == 0
    assert state["consumed_uses"] == 2
    assert state["status"] == "exhausted"


def test_earlier_reservation_may_be_consumed_after_a_later_reservation(
    tmp_path: Path,
) -> None:
    workspace = setup_workspace(tmp_path)
    base = request_for(workspace)
    register_grant(tmp_path, grant_for(workspace, base, max_uses=2))
    reservations = []
    for index in (1, 2):
        request = request_for(
            workspace,
            request_id=f"concurrent-request-{index}",
            attempt_id=f"concurrent-attempt-{index}",
            idempotency_key=f"concurrent-request-key-{index}",
        )
        decision = evaluate(
            tmp_path,
            request,
            context_for(workspace, request),
            evaluated_at=AT,
            skills_root=ROOT,
        )
        decision_ref, decision_sha = persist_decision(tmp_path, decision)
        reservations.append(
            reserve(
                tmp_path,
                decision_ref,
                decision_sha,
                reserved_at=LATER,
                idempotency_key=f"concurrent-reserve-{index}",
                skills_root=ROOT,
            )
        )
    for index, reserved in enumerate(reservations, 1):
        result = write(
            tmp_path / f".task/authorization/results/concurrent-{index}.json",
            "{}\n",
        )
        consume(
            tmp_path,
            reserved["reservation_ref"],
            reserved["reservation_sha256"],
            {"ref": str(result.relative_to(tmp_path)), "sha256": sha256_file(result)},
            consumed_at=LATER,
            expected_version=0,
            idempotency_key=f"concurrent-consume-{index}",
            skills_root=ROOT,
        )
    assert load_grant(tmp_path, "grant-1")[2]["status"] == "exhausted"


def test_conflicting_grant_replay_is_rejected(tmp_path: Path) -> None:
    workspace = setup_workspace(tmp_path)
    request = request_for(workspace)
    grant = grant_for(workspace, request)
    first = register_grant(tmp_path, grant)
    replay = register_grant(tmp_path, grant)
    assert first["grant_sha256"] == replay["grant_sha256"]
    conflicting = {**grant, "risk_ceiling": "R1"}
    with pytest.raises(SystemExit, match="Conflicting authority grant"):
        register_grant(tmp_path, conflicting)


def test_release_exact_replay_is_idempotent(tmp_path: Path) -> None:
    workspace = setup_workspace(tmp_path)
    request = request_for(workspace)
    context = context_for(workspace, request)
    register_grant(tmp_path, grant_for(workspace, request))
    decision = evaluate(tmp_path, request, context, evaluated_at=AT, skills_root=ROOT)
    decision_ref, decision_sha = persist_decision(tmp_path, decision)
    reserved = reserve(
        tmp_path,
        decision_ref,
        decision_sha,
        reserved_at=LATER,
        idempotency_key="reserve-key",
        skills_root=ROOT,
    )
    evidence = write(tmp_path / ".task/authorization/results/no-effect.json", "{}\n")
    binding = {
        "ref": str(evidence.relative_to(tmp_path)),
        "sha256": sha256_file(evidence),
    }
    first = release(
        tmp_path,
        reserved["reservation_ref"],
        reserved["reservation_sha256"],
        binding,
        released_at=LATER,
        expected_version=0,
        idempotency_key="release-key",
        effect_status="verified_no_effect",
    )
    replay = release(
        tmp_path,
        reserved["reservation_ref"],
        reserved["reservation_sha256"],
        binding,
        released_at=LATER,
        expected_version=0,
        idempotency_key="release-key",
        effect_status="verified_no_effect",
    )
    assert first["sha256"] == replay["sha256"]
    assert load_grant(tmp_path, "grant-1")[2]["reserved_uses"] == 0


def test_delegated_children_share_parent_finite_budget(tmp_path: Path) -> None:
    workspace = setup_workspace(tmp_path)
    base_request = request_for(workspace)
    parent = grant_for(
        workspace,
        base_request,
        grant_id="grant-parent-budget",
        issuer_rank="S3",
        holder_rank="S2",
        max_uses=2,
    )
    parent_result = register_grant(tmp_path, parent)
    parent_binding = {
        "ref": ".task/authorization/grants/grant-parent-budget.json",
        "sha256": parent_result["grant_sha256"],
    }
    for child_id in ("grant-child-a", "grant-child-b"):
        child = grant_for(
            workspace,
            base_request,
            grant_id=child_id,
            issuer_rank="S2",
            holder_rank="S0",
            parent_grant_id="grant-parent-budget",
            lineage_id="lineage-1",
            max_uses=2,
        )
        child["source_approval"] = parent_binding
        register_grant(tmp_path, child, parent_id="grant-parent-budget")

    for index in (1, 2):
        request = request_for(
            workspace,
            request_id=f"lineage-request-{index}",
            attempt_id=f"lineage-attempt-{index}",
            idempotency_key=f"lineage-request-key-{index}",
        )
        context = context_for(workspace, request)
        decision = evaluate(
            tmp_path, request, context, evaluated_at=AT, skills_root=ROOT
        )
        assert decision["decision"] == "allowed"
        assert [item["grant_id"] for item in decision["lineage_grants"]] == [
            "grant-parent-budget"
        ]
        decision_ref, decision_sha = persist_decision(tmp_path, decision)
        reserved = reserve(
            tmp_path,
            decision_ref,
            decision_sha,
            reserved_at=LATER,
            idempotency_key=f"lineage-reserve-{index}",
            skills_root=ROOT,
        )
        result = write(
            tmp_path / f".task/authorization/results/lineage-{index}.json",
            "{}\n",
        )
        consume(
            tmp_path,
            reserved["reservation_ref"],
            reserved["reservation_sha256"],
            {"ref": str(result.relative_to(tmp_path)), "sha256": sha256_file(result)},
            consumed_at=LATER,
            expected_version=0,
            idempotency_key=f"lineage-consume-{index}",
            skills_root=ROOT,
        )
    parent_state = load_grant(tmp_path, "grant-parent-budget")[2]
    assert parent_state["remaining_uses"] == 0
    assert parent_state["consumed_uses"] == 2
    third = request_for(
        workspace,
        request_id="lineage-request-3",
        attempt_id="lineage-attempt-3",
        idempotency_key="lineage-request-key-3",
    )
    assert (
        evaluate(
            tmp_path,
            third,
            context_for(workspace, third),
            evaluated_at=LATER,
            skills_root=ROOT,
        )["decision"]
        == "approval_required"
    )


def test_reserve_intent_recovers_partially_applied_projection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = setup_workspace(tmp_path)
    request = request_for(workspace)
    register_grant(tmp_path, grant_for(workspace, request))
    decision = evaluate(
        tmp_path,
        request,
        context_for(workspace, request),
        evaluated_at=AT,
        skills_root=ROOT,
    )
    decision_ref, decision_sha = persist_decision(tmp_path, decision)
    real_apply = lifecycle_module.apply_projection_changes

    def partial(root: Path, changes: list[dict[str, Any]]) -> None:
        real_apply(root, changes[:1])
        raise RuntimeError("injected crash")

    monkeypatch.setattr(lifecycle_module, "apply_projection_changes", partial)
    with pytest.raises(RuntimeError, match="injected crash"):
        reserve(
            tmp_path,
            decision_ref,
            decision_sha,
            reserved_at=LATER,
            idempotency_key="recover-reserve",
            skills_root=ROOT,
        )
    monkeypatch.setattr(lifecycle_module, "apply_projection_changes", real_apply)
    recovered = reserve(
        tmp_path,
        decision_ref,
        decision_sha,
        reserved_at=LATER,
        idempotency_key="recover-reserve",
        skills_root=ROOT,
    )
    assert recovered["state"]["status"] == "reserved"
    assert load_grant(tmp_path, "grant-1")[2]["reserved_uses"] == 1


def test_consume_intent_recovers_partially_applied_projection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = setup_workspace(tmp_path)
    request = request_for(workspace)
    register_grant(tmp_path, grant_for(workspace, request))
    decision = evaluate(
        tmp_path,
        request,
        context_for(workspace, request),
        evaluated_at=AT,
        skills_root=ROOT,
    )
    decision_ref, decision_sha = persist_decision(tmp_path, decision)
    reserved = reserve(
        tmp_path,
        decision_ref,
        decision_sha,
        reserved_at=LATER,
        idempotency_key="reserve-before-consume-crash",
        skills_root=ROOT,
    )
    result = write(tmp_path / ".task/authorization/results/crash-result.json", "{}\n")
    binding = {"ref": str(result.relative_to(tmp_path)), "sha256": sha256_file(result)}
    real_apply = lifecycle_module.apply_projection_changes

    def partial(root: Path, changes: list[dict[str, Any]]) -> None:
        real_apply(root, changes[:1])
        raise RuntimeError("injected crash")

    monkeypatch.setattr(lifecycle_module, "apply_projection_changes", partial)
    with pytest.raises(RuntimeError, match="injected crash"):
        consume(
            tmp_path,
            reserved["reservation_ref"],
            reserved["reservation_sha256"],
            binding,
            consumed_at=LATER,
            expected_version=0,
            idempotency_key="recover-consume",
            skills_root=ROOT,
        )
    monkeypatch.setattr(lifecycle_module, "apply_projection_changes", real_apply)
    recovered = consume(
        tmp_path,
        reserved["reservation_ref"],
        reserved["reservation_sha256"],
        binding,
        consumed_at=LATER,
        expected_version=0,
        idempotency_key="recover-consume",
        skills_root=ROOT,
    )
    assert recovered["use_receipt"]["artifact_kind"] == "authority_use_receipt"
    assert load_grant(tmp_path, "grant-1")[2]["status"] == "exhausted"


def test_release_intent_recovers_partially_applied_projection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = setup_workspace(tmp_path)
    request = request_for(workspace)
    register_grant(tmp_path, grant_for(workspace, request))
    decision = evaluate(
        tmp_path,
        request,
        context_for(workspace, request),
        evaluated_at=AT,
        skills_root=ROOT,
    )
    decision_ref, decision_sha = persist_decision(tmp_path, decision)
    reserved = reserve(
        tmp_path,
        decision_ref,
        decision_sha,
        reserved_at=LATER,
        idempotency_key="reserve-before-release-crash",
        skills_root=ROOT,
    )
    evidence = write(
        tmp_path / ".task/authorization/results/release-crash.json", "{}\n"
    )
    binding = {
        "ref": str(evidence.relative_to(tmp_path)),
        "sha256": sha256_file(evidence),
    }
    real_apply = lifecycle_module.apply_projection_changes

    def partial(root: Path, changes: list[dict[str, Any]]) -> None:
        real_apply(root, changes[:1])
        raise RuntimeError("injected crash")

    monkeypatch.setattr(lifecycle_module, "apply_projection_changes", partial)
    with pytest.raises(RuntimeError, match="injected crash"):
        release(
            tmp_path,
            reserved["reservation_ref"],
            reserved["reservation_sha256"],
            binding,
            released_at=LATER,
            expected_version=0,
            idempotency_key="recover-release",
            effect_status="verified_no_effect",
        )
    monkeypatch.setattr(lifecycle_module, "apply_projection_changes", real_apply)
    recovered = release(
        tmp_path,
        reserved["reservation_ref"],
        reserved["reservation_sha256"],
        binding,
        released_at=LATER,
        expected_version=0,
        idempotency_key="recover-release",
        effect_status="verified_no_effect",
    )
    assert recovered["release_receipt"]["release_applied"] is True
    reservation_id = reserved["reservation"]["reservation_id"]
    reservation_state = json.loads(
        (
            tmp_path
            / ".task/authorization/state/reservations"
            / f"{reservation_id}.json"
        ).read_text(encoding="utf-8")
    )
    assert reservation_state["status"] == "released"


def test_reserve_exact_replay_accepts_valid_consumed_descendants(
    tmp_path: Path,
) -> None:
    workspace = setup_workspace(tmp_path)
    request = request_for(workspace)
    register_grant(tmp_path, grant_for(workspace, request))
    decision = evaluate(
        tmp_path,
        request,
        context_for(workspace, request),
        evaluated_at=AT,
        skills_root=ROOT,
    )
    decision_ref, decision_sha = persist_decision(tmp_path, decision)
    reserved = reserve(
        tmp_path,
        decision_ref,
        decision_sha,
        reserved_at=LATER,
        idempotency_key="reserve-replay-after-consume",
        skills_root=ROOT,
    )
    result = write(
        tmp_path / ".task/authorization/results/reserve-replay-result.json", "{}\n"
    )
    consume(
        tmp_path,
        reserved["reservation_ref"],
        reserved["reservation_sha256"],
        {"ref": str(result.relative_to(tmp_path)), "sha256": sha256_file(result)},
        consumed_at=LATER,
        expected_version=0,
        idempotency_key="consume-before-reserve-replay",
        skills_root=ROOT,
    )

    replay = reserve(
        tmp_path,
        decision_ref,
        decision_sha,
        reserved_at=LATER,
        idempotency_key="reserve-replay-after-consume",
        skills_root=ROOT,
    )

    assert replay["reservation_sha256"] == reserved["reservation_sha256"]
    assert replay["state"]["status"] == "consumed"
    assert load_grant(tmp_path, "grant-1")[2]["status"] == "exhausted"


def test_consume_exact_replay_accepts_later_valid_reservation_descendant(
    tmp_path: Path,
) -> None:
    workspace = setup_workspace(tmp_path)
    first_request = request_for(workspace)
    register_grant(tmp_path, grant_for(workspace, first_request, max_uses=2))
    first_decision = evaluate(
        tmp_path,
        first_request,
        context_for(workspace, first_request),
        evaluated_at=AT,
        skills_root=ROOT,
    )
    first_ref, first_sha = persist_decision(tmp_path, first_decision)
    first_reservation = reserve(
        tmp_path,
        first_ref,
        first_sha,
        reserved_at=LATER,
        idempotency_key="first-reserve-before-consume-replay",
        skills_root=ROOT,
    )
    result = write(
        tmp_path / ".task/authorization/results/consume-replay-result.json", "{}\n"
    )
    result_binding = {
        "ref": str(result.relative_to(tmp_path)),
        "sha256": sha256_file(result),
    }
    first_consume = consume(
        tmp_path,
        first_reservation["reservation_ref"],
        first_reservation["reservation_sha256"],
        result_binding,
        consumed_at=LATER,
        expected_version=0,
        idempotency_key="consume-replay-key",
        skills_root=ROOT,
    )
    second_request = request_for(
        workspace,
        request_id="later-reservation-request",
        attempt_id="later-reservation-attempt",
        idempotency_key="later-reservation-request-key",
    )
    second_decision = evaluate(
        tmp_path,
        second_request,
        context_for(workspace, second_request),
        evaluated_at=LATER,
        skills_root=ROOT,
    )
    second_ref, second_sha = persist_decision(tmp_path, second_decision)
    reserve(
        tmp_path,
        second_ref,
        second_sha,
        reserved_at=LATER,
        idempotency_key="later-reservation",
        skills_root=ROOT,
    )

    replay = consume(
        tmp_path,
        first_reservation["reservation_ref"],
        first_reservation["reservation_sha256"],
        result_binding,
        consumed_at=LATER,
        expected_version=0,
        idempotency_key="consume-replay-key",
        skills_root=ROOT,
    )

    assert replay["sha256"] == first_consume["sha256"]
    grant_state = load_grant(tmp_path, "grant-1")[2]
    assert grant_state["remaining_uses"] == 1
    assert grant_state["reserved_uses"] == 1
    assert grant_state["consumed_uses"] == 1


def test_release_exact_replay_accepts_later_valid_reservation_descendant(
    tmp_path: Path,
) -> None:
    workspace = setup_workspace(tmp_path)
    first_request = request_for(workspace)
    register_grant(tmp_path, grant_for(workspace, first_request, max_uses=2))
    first_decision = evaluate(
        tmp_path,
        first_request,
        context_for(workspace, first_request),
        evaluated_at=AT,
        skills_root=ROOT,
    )
    first_ref, first_sha = persist_decision(tmp_path, first_decision)
    first_reservation = reserve(
        tmp_path,
        first_ref,
        first_sha,
        reserved_at=LATER,
        idempotency_key="first-reserve-before-release-replay",
        skills_root=ROOT,
    )
    evidence = write(
        tmp_path / ".task/authorization/results/release-replay-evidence.json", "{}\n"
    )
    evidence_binding = {
        "ref": str(evidence.relative_to(tmp_path)),
        "sha256": sha256_file(evidence),
    }
    first_release = release(
        tmp_path,
        first_reservation["reservation_ref"],
        first_reservation["reservation_sha256"],
        evidence_binding,
        released_at=LATER,
        expected_version=0,
        idempotency_key="release-replay-key",
        effect_status="verified_no_effect",
    )
    second_request = request_for(
        workspace,
        request_id="later-release-reservation-request",
        attempt_id="later-release-reservation-attempt",
        idempotency_key="later-release-reservation-request-key",
    )
    second_decision = evaluate(
        tmp_path,
        second_request,
        context_for(workspace, second_request),
        evaluated_at=LATER,
        skills_root=ROOT,
    )
    second_ref, second_sha = persist_decision(tmp_path, second_decision)
    reserve(
        tmp_path,
        second_ref,
        second_sha,
        reserved_at=LATER,
        idempotency_key="later-release-reservation",
        skills_root=ROOT,
    )

    replay = release(
        tmp_path,
        first_reservation["reservation_ref"],
        first_reservation["reservation_sha256"],
        evidence_binding,
        released_at=LATER,
        expected_version=0,
        idempotency_key="release-replay-key",
        effect_status="verified_no_effect",
    )

    assert replay["sha256"] == first_release["sha256"]
    grant_state = load_grant(tmp_path, "grant-1")[2]
    assert grant_state["remaining_uses"] == 2
    assert grant_state["reserved_uses"] == 1
    assert grant_state["consumed_uses"] == 0


def test_recovery_rejects_forged_reservation_change_before_mutation(
    tmp_path: Path,
) -> None:
    workspace = setup_workspace(tmp_path)
    request = request_for(workspace)
    register_grant(tmp_path, grant_for(workspace, request))
    decision = evaluate(
        tmp_path,
        request,
        context_for(workspace, request),
        evaluated_at=AT,
        skills_root=ROOT,
    )
    decision_ref, decision_sha = persist_decision(tmp_path, decision)
    reserved = reserve(
        tmp_path,
        decision_ref,
        decision_sha,
        reserved_at=LATER,
        idempotency_key="forged-reservation",
        skills_root=ROOT,
    )
    artifact_path = tmp_path / reserved["reservation_ref"]
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    artifact["state_changes"][0]["after"]["reserved_uses"] = 2
    artifact_path.write_text(json.dumps(artifact), encoding="utf-8")
    before = load_grant(tmp_path, "grant-1")[2]

    with pytest.raises(SystemExit, match="forged|invalid"):
        recover_projection_intents(tmp_path)

    assert load_grant(tmp_path, "grant-1")[2] == before


def test_recovery_rejects_duplicate_projection_refs_before_mutation(
    tmp_path: Path,
) -> None:
    workspace = setup_workspace(tmp_path)
    request = request_for(workspace)
    register_grant(tmp_path, grant_for(workspace, request))
    decision = evaluate(
        tmp_path,
        request,
        context_for(workspace, request),
        evaluated_at=AT,
        skills_root=ROOT,
    )
    decision_ref, decision_sha = persist_decision(tmp_path, decision)
    reserved = reserve(
        tmp_path,
        decision_ref,
        decision_sha,
        reserved_at=LATER,
        idempotency_key="duplicate-ref-reservation",
        skills_root=ROOT,
    )
    artifact_path = tmp_path / reserved["reservation_ref"]
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    artifact["state_changes"].append(artifact["state_changes"][0])
    artifact_path.write_text(json.dumps(artifact), encoding="utf-8")
    before = load_grant(tmp_path, "grant-1")[2]

    with pytest.raises(SystemExit, match="duplicate state ref"):
        recover_projection_intents(tmp_path)

    assert load_grant(tmp_path, "grant-1")[2] == before


def test_recovery_rejects_individually_valid_competing_release_edges(
    tmp_path: Path,
) -> None:
    workspace = setup_workspace(tmp_path)
    request = request_for(workspace)
    register_grant(tmp_path, grant_for(workspace, request, max_uses=2))
    decision = evaluate(
        tmp_path,
        request,
        context_for(workspace, request),
        evaluated_at=AT,
        skills_root=ROOT,
    )
    decision_ref, decision_sha = persist_decision(tmp_path, decision)
    reserved = reserve(
        tmp_path,
        decision_ref,
        decision_sha,
        reserved_at=LATER,
        idempotency_key="competing-edge-reservation",
        skills_root=ROOT,
    )
    evidence = write(
        tmp_path / ".task/authorization/results/competing-edge-evidence.json", "{}\n"
    )
    evidence_binding = {
        "ref": str(evidence.relative_to(tmp_path)),
        "sha256": sha256_file(evidence),
    }
    first = release(
        tmp_path,
        reserved["reservation_ref"],
        reserved["reservation_sha256"],
        evidence_binding,
        released_at=LATER,
        expected_version=0,
        idempotency_key="competing-release-one",
        effect_status="verified_no_effect",
    )
    second_key = "competing-release-two"
    second_id = (
        "authx-"
        + object_sha256(
            {"reservation": reserved["reservation_sha256"], "key": second_key}
        )[:24]
    )
    second = json.loads((tmp_path / first["ref"]).read_text(encoding="utf-8"))
    second["receipt_id"] = second_id
    second["idempotency_key"] = second_key
    for change in second["state_changes"]:
        change["after"]["last_event_id"] = second_id
    second_path = (
        tmp_path / ".task/authorization/release_receipts" / f"{second_id}.json"
    )
    second_path.write_text(json.dumps(second), encoding="utf-8")
    before = load_grant(tmp_path, "grant-1")[2]

    with pytest.raises(SystemExit, match="Competing authority recovery intents"):
        recover_projection_intents(tmp_path)

    assert load_grant(tmp_path, "grant-1")[2] == before


def test_recovery_rejects_symlinked_unknown_and_oversized_intents(
    tmp_path: Path,
) -> None:
    reservations = tmp_path / ".task/authorization/reservations"
    reservations.mkdir(parents=True)
    target = write(tmp_path / "intent-target.json", "{}\n")
    symlink = reservations / "authz-symlink.json"
    symlink.symlink_to(target)
    with pytest.raises(SystemExit, match="symlink"):
        recover_projection_intents(tmp_path)

    symlink.unlink()
    unknown = reservations / "authz-unknown.json"
    unknown.write_text(
        json.dumps({"schema_version": 2, "artifact_kind": "unknown_intent"}),
        encoding="utf-8",
    )
    with pytest.raises(SystemExit, match="Unknown or misplaced"):
        recover_projection_intents(tmp_path)

    unknown.unlink()
    oversized = reservations / "authz-oversized.json"
    oversized.write_bytes(b"{" + b" " * MAX_INTENT_BYTES + b"}")
    with pytest.raises(SystemExit, match="safety limit"):
        recover_projection_intents(tmp_path)


def test_unrelated_lifecycle_entry_recovers_partial_release_before_accounting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = setup_workspace(tmp_path)
    base = request_for(workspace)
    register_grant(tmp_path, grant_for(workspace, base, max_uses=2))
    reservations = []
    for index in (1, 2):
        request = request_for(
            workspace,
            request_id=f"isolation-request-{index}",
            attempt_id=f"isolation-attempt-{index}",
            idempotency_key=f"isolation-request-key-{index}",
        )
        decision = evaluate(
            tmp_path,
            request,
            context_for(workspace, request),
            evaluated_at=AT,
            skills_root=ROOT,
        )
        decision_ref, decision_sha = persist_decision(tmp_path, decision)
        reservations.append(
            reserve(
                tmp_path,
                decision_ref,
                decision_sha,
                reserved_at=LATER,
                idempotency_key=f"isolation-reserve-{index}",
                skills_root=ROOT,
            )
        )
    evidence = write(
        tmp_path / ".task/authorization/results/isolation-release.json", "{}\n"
    )
    evidence_binding = {
        "ref": str(evidence.relative_to(tmp_path)),
        "sha256": sha256_file(evidence),
    }
    real_apply = lifecycle_module.apply_projection_changes

    def partial(root: Path, changes: list[dict[str, Any]]) -> None:
        real_apply(root, changes[:1])
        raise RuntimeError("injected isolation crash")

    monkeypatch.setattr(lifecycle_module, "apply_projection_changes", partial)
    with pytest.raises(RuntimeError, match="injected isolation crash"):
        release(
            tmp_path,
            reservations[0]["reservation_ref"],
            reservations[0]["reservation_sha256"],
            evidence_binding,
            released_at=LATER,
            expected_version=0,
            idempotency_key="isolation-release",
            effect_status="verified_no_effect",
        )
    monkeypatch.setattr(lifecycle_module, "apply_projection_changes", real_apply)

    result = write(
        tmp_path / ".task/authorization/results/isolation-consume.json", "{}\n"
    )
    with pytest.raises(SystemExit, match="expected reserved CAS state"):
        consume(
            tmp_path,
            reservations[0]["reservation_ref"],
            reservations[0]["reservation_sha256"],
            {"ref": str(result.relative_to(tmp_path)), "sha256": sha256_file(result)},
            consumed_at=LATER,
            expected_version=0,
            idempotency_key="must-not-consume-released-reservation",
            skills_root=ROOT,
        )
    reservation_id = reservations[0]["reservation"]["reservation_id"]
    recovered_state = json.loads(
        (
            tmp_path
            / ".task/authorization/state/reservations"
            / f"{reservation_id}.json"
        ).read_text(encoding="utf-8")
    )
    assert recovered_state["status"] == "released"
    grant_state = load_grant(tmp_path, "grant-1")[2]
    assert grant_state["reserved_uses"] == 1
    assert grant_state["remaining_uses"] == 2


def test_transition_intent_recovers_partially_applied_cascade(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = setup_workspace(tmp_path)
    request = request_for(workspace)
    parent = grant_for(
        workspace,
        request,
        grant_id="grant-parent",
        issuer_rank="S3",
        holder_rank="S2",
        max_uses=2,
    )
    parent_result = register_grant(tmp_path, parent)
    child = grant_for(
        workspace,
        request,
        grant_id="grant-child",
        issuer_rank="S2",
        holder_rank="S0",
        parent_grant_id="grant-parent",
        max_uses=1,
    )
    child["source_approval"] = {
        "ref": ".task/authorization/grants/grant-parent.json",
        "sha256": parent_result["grant_sha256"],
    }
    register_grant(tmp_path, child, parent_id="grant-parent")
    real_apply = artifact_store_module.apply_projection_changes

    def partial(root: Path, changes: list[dict[str, Any]]) -> None:
        real_apply(root, changes[:1])
        raise RuntimeError("injected crash")

    monkeypatch.setattr(artifact_store_module, "apply_projection_changes", partial)
    with pytest.raises(RuntimeError, match="injected crash"):
        transition_grants(
            tmp_path,
            "grant-parent",
            "revoked",
            event_id="recover-transition",
            expected_version=0,
            source_approval=workspace["source_binding"],
            transitioned_at=LATER,
        )
    monkeypatch.setattr(artifact_store_module, "apply_projection_changes", real_apply)
    transition_grants(
        tmp_path,
        "grant-parent",
        "revoked",
        event_id="recover-transition",
        expected_version=0,
        source_approval=workspace["source_binding"],
        transitioned_at=LATER,
    )
    assert load_grant(tmp_path, "grant-parent")[2]["status"] == "revoked"
    assert load_grant(tmp_path, "grant-child")[2]["status"] == "revoked"


def test_cardinality_session_and_nonlease_scopes_are_enforced(tmp_path: Path) -> None:
    workspace = setup_workspace(tmp_path)
    request = request_for(workspace)
    grant = grant_for(workspace, request)
    grant["session_id"] = "different-session"
    register_grant(tmp_path, grant)
    assert (
        evaluate(
            tmp_path,
            request,
            context_for(workspace, request),
            evaluated_at=AT,
            skills_root=ROOT,
        )["decision"]
        == "approval_required"
    )

    workspace_two = setup_workspace(tmp_path / "other")
    request_two = request_for(workspace_two, cardinality_requested="standing_policy")
    register_grant(tmp_path / "other", grant_for(workspace_two, request_two))
    result = evaluate(
        tmp_path / "other",
        request_two,
        context_for(workspace_two, request_two),
        evaluated_at=AT,
        skills_root=ROOT,
    )
    assert result["decision"] == "approval_required"


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        (
            {"cardinality_requested": "single_use", "use_budget_requested": 2},
            "single_use requests require use_budget_requested=1",
        ),
        (
            {"cardinality_requested": "task_lease", "task_id": None},
            "task_lease requests require an exact task_id",
        ),
        (
            {"cardinality_requested": "improvement_lease", "pack_id": None},
            "improvement_lease requests require an exact pack_id",
        ),
    ],
)
def test_request_cardinality_requires_matching_budget_and_scope(
    tmp_path: Path, changes: dict[str, Any], message: str
) -> None:
    workspace = setup_workspace(tmp_path)
    request = {**request_for(workspace), **changes}
    with pytest.raises(SystemExit, match=message):
        evaluate(
            tmp_path,
            request,
            context_for(workspace, request),
            evaluated_at=AT,
            skills_root=ROOT,
        )


def test_approval_projection_is_deterministic_and_minimum_scope(tmp_path: Path) -> None:
    workspace = setup_workspace(tmp_path)
    request = request_for(workspace)
    context = context_for(workspace, request)
    first = evaluate(tmp_path, request, context, evaluated_at=AT, skills_root=ROOT)
    second = evaluate(tmp_path, request, context, evaluated_at=AT, skills_root=ROOT)
    projection = first["approval_projection"]
    assert first["decision"] == "approval_required"
    assert projection == second["approval_projection"]
    assert projection["projection_id"].startswith("authp-")
    assert projection["subject"]["digest"] == request["subject"]["digest"]
    assert projection["scope"]["cardinality"] == "single_use"
    assert projection["scope"]["use_budget"] == 1
    assert projection["exact_replay_key"] == request["idempotency_key"]
    assert "supply_external_input" in projection["excluded_effects"]


def test_manifest_binding_is_raw_file_digest_and_cli_operations_are_covered() -> None:
    _, binding = load_operation(
        "manage-agent-authority",
        "2.0.0",
        "evaluate_operation",
        "1",
        skills_root=ROOT,
    )
    manifest_path = ROOT / "manage-agent-authority/authority.operations.json"
    assert binding == {
        "ref": "manage-agent-authority/authority.operations.json",
        "sha256": sha256_file(manifest_path),
    }
    operations = {
        item["operation_id"]
        for item in json.loads(manifest_path.read_text(encoding="utf-8"))["operations"]
    }
    command_operations = {
        "snapshot_policy",
        "snapshot_source_approval",
        "issue_grant",
        "delegate_grant",
        "evaluate_operation",
        "compose_grants",
        "reserve_use",
        "verify_reservation",
        "consume_use",
        "release_use",
        "prepare_source_authority_recovery",
        "transition_grant",
        "status",
    }
    assert command_operations.issubset(operations)


def test_operation_manifest_rejects_symlink_file_and_parent_component(
    tmp_path: Path,
) -> None:
    skills_root = tmp_path / "skills"
    real_manifest = write(
        tmp_path / "real/authority.operations.json",
        (ROOT / "manage-agent-authority/authority.operations.json").read_text(
            encoding="utf-8"
        ),
    )
    linked_skill = skills_root / "linked-skill"
    linked_skill.mkdir(parents=True)
    os.symlink(real_manifest, linked_skill / "authority.operations.json")
    with pytest.raises(SystemExit, match="symlink component"):
        load_operation(
            "linked-skill",
            "2.0.0",
            "evaluate_operation",
            "1",
            skills_root=skills_root,
        )

    os.symlink(real_manifest.parent, skills_root / "linked-parent")
    with pytest.raises(SystemExit, match="symlink component"):
        load_operation(
            "linked-parent",
            "2.0.0",
            "evaluate_operation",
            "1",
            skills_root=skills_root,
        )


def test_authority_artifact_resolution_rejects_symlink_components(
    tmp_path: Path,
) -> None:
    workspace = setup_workspace(tmp_path)
    link = tmp_path / ".task/authorization/link.json"
    os.symlink(workspace["source_binding"]["ref"], link)
    bad_binding = {
        "ref": str(link.relative_to(tmp_path)),
        "sha256": workspace["source_binding"]["sha256"],
    }
    grant = grant_for(workspace, request_for(workspace))
    grant["source_approval"] = bad_binding
    with pytest.raises(SystemExit, match="symlink component"):
        register_grant(tmp_path, grant)


def test_snapshot_does_not_publish_source_changed_during_copy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = write(
        tmp_path / ".agent_goal/agent_authority.md",
        "A" * (1024 * 1024 + 64),
    )
    real_sha256 = artifact_store_module.hashlib.sha256
    changed = False

    class MutatingDigest:
        def __init__(self) -> None:
            self._digest = real_sha256()

        def update(self, chunk: bytes) -> None:
            nonlocal changed
            self._digest.update(chunk)
            if not changed:
                changed = True
                source.write_text("changed during copy\n", encoding="utf-8")

        def hexdigest(self) -> str:
            return self._digest.hexdigest()

    monkeypatch.setattr(artifact_store_module.hashlib, "sha256", MutatingDigest)
    with pytest.raises(SystemExit, match="changed during acquisition"):
        snapshot_file(tmp_path, str(source.relative_to(tmp_path)), "policy")

    snapshot_dir = tmp_path / ".task/authorization/policy_snapshots"
    assert not list(snapshot_dir.glob("policy-*"))
    assert not list(snapshot_dir.glob(".snapshot.*"))


def test_source_approval_prevents_retroactive_grant_creation(tmp_path: Path) -> None:
    workspace = setup_workspace(tmp_path)
    grant = grant_for(workspace, request_for(workspace))
    grant["created_at"] = "2026-07-17T09:59:59+09:00"
    with pytest.raises(SystemExit, match="creation predates"):
        register_grant(tmp_path, grant)


def test_exact_higher_rank_source_can_delegate_s2_root_grant(tmp_path: Path) -> None:
    workspace = setup_workspace(tmp_path)
    request = request_for(workspace)
    delegated_source = delegated_source_for(tmp_path, workspace)
    grant = grant_for(
        workspace,
        request,
        issuer_rank="S2",
        holder_rank="S0",
    )
    grant["source_approval"] = delegated_source

    result = register_grant(tmp_path, grant)

    assert result["grant"]["issuer_rank"] == "S2"
    assert result["state"]["status"] == "active"


def test_rank_monotone_s3_s2_s1_source_lineage_can_issue_root_grant(
    tmp_path: Path,
) -> None:
    workspace = setup_workspace(tmp_path)
    request = request_for(workspace)
    delegated_s2 = delegated_source_for(
        tmp_path,
        workspace,
        approval_id="delegated-s2-parent",
    )
    delegated_s1 = delegated_source_for(
        tmp_path,
        workspace,
        approval_id="delegated-s1-leaf",
        source_kind="cycle_coordination_grant",
        source_rank="S1",
        delegation_binding=delegated_s2,
    )
    grant = grant_for(
        workspace,
        request,
        issuer_rank="S1",
        holder_rank="S0",
    )
    grant["source_approval"] = delegated_s1

    result = register_grant(tmp_path, grant)

    assert result["grant"]["issuer_rank"] == "S1"
    assert result["state"]["status"] == "active"


def test_forged_s2_nonexistent_binding_cannot_issue_root_grant(
    tmp_path: Path,
) -> None:
    workspace = setup_workspace(tmp_path)
    request = request_for(workspace)
    delegated_source = delegated_source_for(
        tmp_path,
        workspace,
        delegation_binding={
            "ref": ".task/authorization/source_snapshots/nonexistent.json",
            "sha256": "0" * 64,
        },
    )
    grant = grant_for(
        workspace,
        request,
        issuer_rank="S2",
        holder_rank="S0",
    )
    grant["source_approval"] = delegated_source

    with pytest.raises(SystemExit, match="does not identify an existing path"):
        register_grant(tmp_path, grant)


def test_delegated_grant_issue_capability_must_reach_the_root(
    tmp_path: Path,
) -> None:
    workspace = setup_workspace(tmp_path)
    request = request_for(workspace)
    root_body = json.loads(workspace["approval"].read_text(encoding="utf-8"))
    root_body["approval_id"] = "root-without-issue-capability"
    root_body["capabilities"].remove("authority.grant.issue")
    root_file = write(
        tmp_path / ".task/authorization/root-without-issue.json",
        json.dumps(root_body, indent=2, sort_keys=True) + "\n",
    )
    root_without_issue = snapshot_file(
        tmp_path, str(root_file.relative_to(tmp_path)), "source_approval"
    )
    delegated_source = delegated_source_for(
        tmp_path,
        workspace,
        approval_id="delegated-from-root-without-issue",
        delegation_binding=root_without_issue,
    )
    grant = grant_for(
        workspace,
        request,
        issuer_rank="S2",
        holder_rank="S0",
    )
    grant["source_approval"] = delegated_source

    with pytest.raises(SystemExit, match="capabilities exceed"):
        register_grant(tmp_path, grant)

    delegated_without_issue = delegated_source_for(
        tmp_path,
        workspace,
        approval_id="delegated-without-issue",
        capabilities=["implementation.local.edit"],
    )
    grant["source_approval"] = delegated_without_issue
    with pytest.raises(SystemExit, match="lacks authority.grant.issue"):
        register_grant(tmp_path, grant)


def test_delegated_source_rejects_digest_and_equal_rank_roots(tmp_path: Path) -> None:
    workspace = setup_workspace(tmp_path)
    request = request_for(workspace)
    bad_digest_source = delegated_source_for(
        tmp_path,
        workspace,
        approval_id="delegated-bad-digest",
        delegation_binding={
            **workspace["source_binding"],
            "sha256": "0" * 64,
        },
    )
    grant = grant_for(
        workspace,
        request,
        issuer_rank="S2",
        holder_rank="S0",
    )
    grant["source_approval"] = bad_digest_source
    with pytest.raises(SystemExit, match="digest mismatch"):
        register_grant(tmp_path, grant)

    valid_s2_source = delegated_source_for(
        tmp_path,
        workspace,
        approval_id="delegated-valid-s2-parent",
    )
    equal_rank_source = delegated_source_for(
        tmp_path,
        workspace,
        approval_id="delegated-equal-rank",
        delegation_binding=valid_s2_source,
    )
    equal_rank_grant = {
        **grant,
        "source_approval": equal_rank_source,
        "idempotency_key": "key-equal-rank",
    }
    with pytest.raises(SystemExit, match="strictly higher-rank"):
        register_grant(tmp_path, equal_rank_grant)


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        (
            {
                "capabilities": [
                    "authority.grant.issue",
                    "implementation.unapproved.edit",
                ]
            },
            "capabilities",
        ),
        ({"grant_ids": ["grant-1", "grant-unapproved"]}, "grant_ids"),
        (
            {"not_before": "2026-07-17T09:59:59+09:00"},
            "begins before",
        ),
        (
            {"expires_at": "2026-07-17T11:00:01+09:00"},
            "outlives",
        ),
    ],
)
def test_delegated_source_cannot_expand_parent_scope_or_time(
    tmp_path: Path, changes: dict[str, Any], message: str
) -> None:
    workspace = setup_workspace(tmp_path)
    request = request_for(workspace)
    delegated_source = delegated_source_for(
        tmp_path,
        workspace,
        approval_id=f"delegated-invalid-{message.replace(' ', '-')}",
        **changes,
    )
    grant = grant_for(
        workspace,
        request,
        capabilities=["implementation.unapproved.edit"]
        if "capabilities" in changes
        else None,
        issuer_rank="S2",
        holder_rank="S0",
    )
    grant["source_approval"] = delegated_source
    if "not_before" in changes:
        grant["not_before"] = changes["not_before"]
        grant["created_at"] = changes["not_before"]
    if "expires_at" in changes:
        grant["expires_at"] = changes["expires_at"]

    with pytest.raises(SystemExit, match=message):
        register_grant(tmp_path, grant)


def test_delegated_s2_can_transition_exact_s0_grant_but_not_unrelated(
    tmp_path: Path,
) -> None:
    workspace = setup_workspace(tmp_path)
    request = request_for(workspace)
    register_grant(tmp_path, grant_for(workspace, request, grant_id="grant-1"))
    register_grant(tmp_path, grant_for(workspace, request, grant_id="grant-a"))
    delegated_body = json.loads(workspace["approval"].read_text(encoding="utf-8"))
    delegated_body.update(
        {
            "approval_id": "delegated-transition-1",
            "source_kind": "delegated_policy_steward",
            "source_rank": "S2",
            "grant_ids": ["grant-1"],
            "delegation_binding": workspace["source_binding"],
        }
    )
    delegated_file = write(
        tmp_path / ".task/authorization/delegated-transition.json",
        json.dumps(delegated_body, indent=2, sort_keys=True) + "\n",
    )
    delegated_source = snapshot_file(
        tmp_path,
        str(delegated_file.relative_to(tmp_path)),
        "source_approval",
    )
    transition_grants(
        tmp_path,
        "grant-1",
        "revoked",
        event_id="delegated-revoke-1",
        expected_version=0,
        source_approval=delegated_source,
        transitioned_at=LATER,
    )
    assert load_grant(tmp_path, "grant-1")[2]["status"] == "revoked"
    with pytest.raises(SystemExit, match="exact grant ID"):
        transition_grants(
            tmp_path,
            "grant-a",
            "revoked",
            event_id="delegated-revoke-unrelated",
            expected_version=0,
            source_approval=delegated_source,
            transitioned_at=LATER,
        )
