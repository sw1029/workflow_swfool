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
from manage_agent_authority.artifact_store import load_grant  # noqa: E402
from manage_agent_authority.artifact_store import register_grant  # noqa: E402
from manage_agent_authority.artifact_store import snapshot_file  # noqa: E402
from manage_agent_authority.artifact_store import transition_grants  # noqa: E402
from manage_agent_authority.canonical import object_sha256  # noqa: E402
from manage_agent_authority.canonical import sha256_file  # noqa: E402
from manage_agent_authority.canonical import write_immutable_json  # noqa: E402
from manage_agent_authority.composition import create_composition  # noqa: E402
from manage_agent_authority.evaluator import evaluate  # noqa: E402
from manage_agent_authority.lifecycle import consume  # noqa: E402
from manage_agent_authority.lifecycle import release  # noqa: E402
from manage_agent_authority.lifecycle import reserve  # noqa: E402
from manage_agent_authority.operations import load_operation  # noqa: E402
from manage_agent_authority.projection_recovery import MAX_INTENT_BYTES  # noqa: E402
from manage_agent_authority.projection_recovery import recover_projection_intents  # noqa: E402


AT = "2026-07-17T10:00:00+09:00"
LATER = "2026-07-17T10:05:00+09:00"
EXPIRY = "2026-07-17T11:00:00+09:00"


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
