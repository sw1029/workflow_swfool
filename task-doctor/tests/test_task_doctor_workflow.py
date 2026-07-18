from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from typing import Any

import pytest


SCRIPT = Path(__file__).parents[1] / "scripts" / "task_doctor_workflow.py"
LIB = SCRIPT.parent / "task_doctor_workflow_lib"
SKILLS_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SCRIPT.parent))
sys.path.insert(0, str(SKILLS_ROOT / "manage-agent-authority" / "scripts"))
sys.path.insert(0, str(SKILLS_ROOT / "manage-external-advice" / "scripts"))
sys.path.insert(0, str(SKILLS_ROOT / "manage-task-state-index" / "scripts"))
SPEC = importlib.util.spec_from_file_location("task_doctor_workflow_facade", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
workflow = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(workflow)

from manage_agent_authority.artifact_store import register_grant, snapshot_file  # noqa: E402
from manage_agent_authority.canonical import (  # noqa: E402
    object_sha256,
    parse_time,
    sha256_file,
    write_immutable_json,
)
from manage_agent_authority.evaluator import evaluate  # noqa: E402
from manage_agent_authority.lifecycle import (  # noqa: E402
    consume,
    release,
    reserve,
    verify_reservation_with_recovery,
)
from manage_agent_authority.operations import load_operation  # noqa: E402
from manage_task_state_index.state.transition_plan_contract import (  # type: ignore[import-not-found]  # noqa: E402
    validate_transition_plan,
)
from manage_task_state_index.state.transition_plan import (  # type: ignore[import-not-found]  # noqa: E402
    apply_transition_plan,
    build_transition_plan,
    publish_transition_plan,
    settle_transition_no_effect,
    verify_transition_plan,
)
from manage_task_state_index.state.transition_intent import (  # type: ignore[import-not-found]  # noqa: E402
    publish_transition_intent,
)
from manage_external_advice.intake_plan_contract import (  # type: ignore[import-not-found]  # noqa: E402
    validate_intake_plan,
)
from manage_external_advice.intake_plan import (  # type: ignore[import-not-found]  # noqa: E402
    apply_intake_plan,
    build_intake_plan,
    publish_intake_plan,
)
from task_doctor_workflow_lib.task_transition_plan import (  # noqa: E402
    build_task_transition_plan,
)
from task_doctor_workflow_lib.task_transition_transaction import (  # noqa: E402
    apply_task_transition_plan,
    verify_task_transition_execution,
)
from task_doctor_workflow_lib.task_transition_store import (  # noqa: E402
    publish_task_transition_plan,
)
from task_doctor_workflow_lib import task_transition_transaction  # noqa: E402
from task_doctor_workflow_lib import task_transition_store  # noqa: E402
from task_doctor_workflow_lib import journal as journal_store  # noqa: E402


AT = "2026-07-18T10:00:00+09:00"
RESERVED_AT = "2026-07-18T10:05:00+09:00"
SETTLED_AT = "2026-07-18T10:10:00+09:00"
EXPIRY = "2030-07-18T10:00:00+09:00"


@pytest.fixture(autouse=True)
def _freeze_live_authority_time(monkeypatch: pytest.MonkeyPatch) -> None:
    from task_doctor_workflow_lib import authority_overlay

    monkeypatch.setattr(authority_overlay, "now", lambda: SETTLED_AT)


def _write_json(
    root: Path, ref: str, body: object, *, newline: bool = True,
) -> dict[str, str]:
    path = root / ref
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(
        body, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8") + (b"\n" if newline else b"")
    path.write_bytes(payload)
    return {"ref": ref, "sha256": hashlib.sha256(payload).hexdigest()}


def _workspace(root: Path) -> dict[str, Any]:
    policy = root / ".agent_goal/agent_authority.md"
    goal = root / ".agent_goal/goal_architecture.md"
    policy.parent.mkdir(parents=True, exist_ok=True)
    policy.write_text("# Authority\n\nBounded local task transitions.\n", encoding="utf-8")
    goal.write_text("# Goal\n\n- concept_id: concept-1\n", encoding="utf-8")
    return {
        "policy": snapshot_file(root, str(policy.relative_to(root)), "policy"),
        "goal": {"ref": str(goal.relative_to(root)), "sha256": sha256_file(goal)},
    }


def _operation_identity(spec: dict[str, str]) -> dict[str, str]:
    return {key: spec[key] for key in (
        "skill_id", "skill_version", "operation_id", "operation_version"
    )}


def _default_spec() -> dict[str, str]:
    return {
        "skill_id": "task-doctor", "skill_version": "2.2.0",
        "operation_id": "mutate_task_scope", "operation_version": "1",
        "capability": "task.scope.mutate", "effect_class": "retarget_or_replace_task",
        "data_class": "task_state", "subject_kind": "task_transition_plan",
        "decision_class": "D2",
    }


def _index_spec() -> dict[str, str]:
    return {
        "skill_id": "manage-task-state-index", "skill_version": "2.0.0",
        "operation_id": "mutate_task_state_index", "operation_version": "1",
        "capability": "task.index.mutate",
        "effect_class": "append_or_project_task_lifecycle",
        "data_class": "task_state_index", "subject_kind": "task_index_transition_plan",
        "decision_class": "D2",
    }


def _advice_spec() -> dict[str, str]:
    return {
        "skill_id": "manage-external-advice", "skill_version": "2.0.0",
        "operation_id": "mutate_advice_lifecycle", "operation_version": "1",
        "capability": "advice.lifecycle.mutate",
        "effect_class": "intake_apply_defer_reject_or_retire_advice",
        "data_class": "external_advice", "subject_kind": "advice_intake_plan",
        "decision_class": "D2",
    }


def _request(
    binding: dict[str, str], spec: dict[str, str], suffix: str,
) -> dict[str, Any]:
    return {
        "schema_version": 2, "request_kind": "authority_operation",
        "request_id": f"request-{suffix}", **_operation_identity(spec),
        "cycle_id": "cycle-test", "task_id": "task-test", "pack_id": None,
        "attempt_id": f"attempt-{suffix}", "actor_rank": "S0",
        "subject": {"kind": spec["subject_kind"], "ref": binding["ref"],
                    "digest": binding["sha256"], "revision": f"plan-{suffix}"},
        "required_capabilities": [spec["capability"]],
        "effect_class": spec["effect_class"], "data_class": spec["data_class"],
        "mutation_class": "local_mutation",
        "reversibility": "conditionally_reversible", "risk_tier": "R2",
        "decision_class": spec["decision_class"], "intent_type": "grant_authority",
        "cardinality_requested": "single_use", "use_budget_requested": 1,
        "reservation_units": 1, "idempotency_key": f"request-key-{suffix}",
        "context": {"external_input_status": "not_required",
                    "goal_truth_status": "aligned",
                    "risk_acceptance_status": "not_required",
                    "design_selection_status": "not_required",
                    "external_input_evidence": None,
                    "risk_acceptance_evidence": None,
                    "design_selection_evidence": None},
        "composition_receipt": None,
    }


def _context(
    workspace: dict[str, Any], request: dict[str, Any], suffix: str,
) -> dict[str, Any]:
    operation = ":".join(
        request[key] for key in (
            "skill_id", "skill_version", "operation_id", "operation_version"
        )
    )
    return {
        "schema_version": 2, "context_kind": "authority_evaluation",
        "session_ceiling": {"capabilities": request["required_capabilities"],
                            "risk_ceiling": "R3",
                            "mutation_classes": ["local_mutation"],
                            "evidence_id": f"session-{suffix}"},
        "goal_autonomy_envelope": {
            "envelope_id": f"envelope-{suffix}",
            "capabilities": request["required_capabilities"],
            "risk_ceiling": "R3", "decision_classes": [request["decision_class"]],
            "subjects": [request["subject"]["digest"]], "operations": [operation],
            "source_binding": workspace["goal"],
        },
    }


def _authority_operation(
    root: Path, workspace: dict[str, Any], suffix: str,
    *, workflow_role: str = "external_advice_intake",
    dependencies: list[str] | None = None,
    spec: dict[str, str] | None = None, owner_plan: dict[str, Any] | None = None,
    plan_binding: dict[str, str] | None = None,
) -> tuple[dict[str, Any], dict[str, str], dict[str, Any]]:
    spec = spec or (
        _default_spec() if workflow_role == "task_scope_transition"
        else _advice_spec()
    )
    if owner_plan is None:
        if workflow_role == "task_scope_transition":
            prospective_ref = f".task/task_doctor/prospective/{suffix}.md"
            prospective = root / prospective_ref
            prospective.parent.mkdir(parents=True, exist_ok=True)
            prospective.write_text(
                f"# Task\n\n## Objective\n\nApply transition {suffix}.\n",
                encoding="utf-8",
            )
            owner_plan = build_task_transition_plan(
                root, suffix,
                "replace_task" if (root / "task.md").is_file() else "initial_task",
                prospective_ref,
            )
        else:
            source = root / f"inputs/advice-{suffix}.md"
            source.parent.mkdir(parents=True, exist_ok=True)
            text = f"# Advice {suffix}\n\nApply exact advice intake {suffix}.\n"
            source.write_text(text, encoding="utf-8")
            owner_plan = build_intake_plan(
                root, text, f"Advice {suffix}", "normal", at=AT,
                source_ref=str(source.relative_to(root)),
            )
            published = publish_intake_plan(root, owner_plan)
            plan_binding = {
                "ref": published["plan_ref"],
                "sha256": published["plan_file_sha256"],
            }
    if plan_binding is None:
        if owner_plan.get("plan_kind") == "task_transition_plan":
            task_plan = publish_task_transition_plan(root, owner_plan)
            plan_binding = {
                "ref": task_plan["plan_ref"],
                "sha256": task_plan["plan_file_sha256"],
            }
        else:
            plan_binding = _write_json(root, f"plans/{suffix}.json", owner_plan)
    request = _request(plan_binding, spec, suffix)
    grant_id = f"grant-{suffix}"
    lineage_id = f"lineage-{suffix}"
    approval = {
        "schema_version": 2, "artifact_kind": "authority_source_approval",
        "approval_id": f"approval-{suffix}",
        "source_kind": "explicit_user_instruction", "source_rank": "S3",
        "decision_type": "grant_authority",
        "capabilities": ["authority.grant.issue", spec["capability"]],
        "subjects": [request["subject"]], "operations": [_operation_identity(spec)],
        "risk_ceiling": "R2", "decision_classes": [spec["decision_class"]],
        "cardinalities": ["single_use"], "max_uses": 1,
        "grant_ids": [grant_id], "request_digests": [object_sha256(request)],
        "lineage_ids": [lineage_id], "delegation_binding": None,
        "not_before": AT, "expires_at": EXPIRY,
        "evidence_id": f"user-event-{suffix}", "integrity_status": "verified",
    }
    approval_source = _write_json(
        root, f".task/authorization/source-{suffix}.json", approval
    )
    approval_binding = snapshot_file(root, approval_source["ref"], "source_approval")
    grant = {
        "schema_version": 2, "artifact_kind": "authority_grant",
        "grant_id": grant_id, "lineage_id": lineage_id, "parent_grant_id": None,
        "issuer_rank": "S3", "holder_rank": "S0",
        "capabilities": request["required_capabilities"],
        "subjects": [request["subject"]], "operations": [_operation_identity(spec)],
        "risk_ceiling": "R2", "decision_classes": [spec["decision_class"]],
        "cardinality": "single_use", "max_uses": 1,
        "not_before": AT, "expires_at": EXPIRY, "session_id": None,
        "task_id": request["task_id"], "improvement_id": None,
        "source_approval": approval_binding, "policy_snapshot": workspace["policy"],
        "created_at": AT, "idempotency_key": f"grant-key-{suffix}",
    }
    register_grant(root, grant)
    context = _context(workspace, request, suffix)
    operation = {
        "operation_id": suffix, "workflow_role": workflow_role,
        "owner_skill": f"${spec['skill_id']}", "effect_class": spec["effect_class"],
        "effect_summary": f"Apply exact owner effect {suffix}.", "required": True,
        "dependencies": dependencies or [], "plan": owner_plan,
        "plan_binding": plan_binding,
        "authority": {
            "applicability": "required", "request": request,
            "materialization": {
                "evaluation_context": context, "evaluated_at": AT,
                "policy_snapshot": workspace["policy"],
                "grant_spec": {"grant_id": grant_id, "lineage_id": lineage_id,
                               "holder_rank": "S0", "cardinality": "single_use",
                               "max_uses": 1, "not_before": AT,
                               "expires_at": EXPIRY,
                               "idempotency_key": f"grant-key-{suffix}"},
                "reservation": {"reserved_at": RESERVED_AT,
                                "idempotency_key": f"reserve-key-{suffix}"},
            },
        },
    }
    runtime = {"request": request, "context": context,
               "reservation_key": f"reserve-key-{suffix}",
               "source_approval": approval_binding}
    return operation, approval_binding, runtime


def _plan(
    root: Path, count: int = 1, *, mode: str = "execute_with_declared_authorization",
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    workspace = _workspace(root)
    operations = []
    approvals = []
    runtime = {}
    for index in range(count):
        suffix = f"op-{index + 1}"
        operation, approval, item_runtime = _authority_operation(
            root, workspace, suffix,
            dependencies=[] if index == 0 else [f"op-{index}"],
        )
        operations.append(operation)
        approvals.append({"operation_id": suffix, "source_approval": approval})
        runtime[suffix] = item_runtime
    result = {
        "schema_version": 1, "execution_mode": mode,
        "complete_effect_inventory": True,
        "max_user_approval_interactions": 0 if mode.startswith("execute") else 1,
        "authorized_local_effects": sorted({
            operation["effect_class"] for operation in operations
        }),
        "excluded_effects": sorted(workflow.FORBIDDEN_EFFECTS),
        "git_finalization": "deferred",
        "task_index_transition": {"status": "not_applicable", "reason": "No index role."},
        "operations": operations,
        "reporting": {"detail": "concise", "language": "ko"},
    }
    if mode.startswith("execute"):
        result["authorization_basis"] = {
            "schema_version": 1,
            "basis_kind": "task_doctor_declared_authorization",
            "approvals": approvals,
        }
    return result, runtime


def _task_scope_workflow(
    root: Path,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    workspace = _workspace(root)
    scope, scope_approval, scope_runtime = _authority_operation(
        root, workspace, "scope", workflow_role="task_scope_transition",
        spec=_default_spec(),
    )
    index_plan = build_transition_plan(
        root,
        {
            "schema_version": 1, "updated_at": AT, "render": True,
            "events": [{
                "event": "upsert", "id": "task-id-scope", "type": "task",
                "status": "active", "path": "task.md", "title": "Task Scope",
                "content_sha256": scope["plan"]["after_task"]["sha256"],
            }],
        },
    )
    published = publish_transition_plan(root, index_plan)
    index_binding = {
        "ref": published["plan_ref"], "sha256": published["plan_file_sha256"]
    }
    index, index_approval, index_runtime = _authority_operation(
        root, workspace, "index", workflow_role="task_index_transition",
        dependencies=["scope"], spec=_index_spec(), owner_plan=index_plan,
        plan_binding=index_binding,
    )
    body = {
        "schema_version": 1,
        "execution_mode": "execute_with_declared_authorization",
        "complete_effect_inventory": True,
        "max_user_approval_interactions": 0,
        "authorized_local_effects": sorted({
            scope["effect_class"], index["effect_class"]
        }),
        "excluded_effects": sorted(workflow.FORBIDDEN_EFFECTS),
        "git_finalization": "deferred",
        "task_index_transition": {"status": "planned", "operation_id": "index"},
        "operations": [scope, index],
        "authorization_basis": {
            "schema_version": 1,
            "basis_kind": "task_doctor_declared_authorization",
            "approvals": [
                {"operation_id": "scope", "source_approval": scope_approval},
                {"operation_id": "index", "source_approval": index_approval},
            ],
        },
        "reporting": {"detail": "concise", "language": "ko"},
    }
    return body, {"scope": scope_runtime, "index": index_runtime}


def _index_only_workflow(
    root: Path, index_plan: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, str]]:
    workspace = _workspace(root)
    published = publish_transition_plan(root, index_plan)
    binding = {
        "ref": published["plan_ref"], "sha256": published["plan_file_sha256"]
    }
    operation, approval, runtime = _authority_operation(
        root, workspace, "index", workflow_role="task_index_transition",
        spec=_index_spec(), owner_plan=index_plan, plan_binding=binding,
    )
    body = {
        "schema_version": 1,
        "execution_mode": "execute_with_declared_authorization",
        "complete_effect_inventory": True,
        "max_user_approval_interactions": 0,
        "authorized_local_effects": ["append_or_project_task_lifecycle"],
        "excluded_effects": sorted(workflow.FORBIDDEN_EFFECTS),
        "git_finalization": "deferred",
        "task_index_transition": {"status": "planned", "operation_id": "index"},
        "operations": [operation],
        "authorization_basis": {
            "schema_version": 1,
            "basis_kind": "task_doctor_declared_authorization",
            "approvals": [{"operation_id": "index", "source_approval": approval}],
        },
        "reporting": {"detail": "concise", "language": "ko"},
    }
    return body, runtime, binding


def _prepare(root: Path, body: dict[str, Any]) -> dict[str, Any]:
    plan_path = root / "workflow-plan.json"
    plan_path.write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")
    return workflow.prepare(root, plan_path)


def _materialize(root: Path, runtime: dict[str, Any]) -> dict[str, str]:
    decision = evaluate(
        root, runtime["request"], runtime["context"], evaluated_at=AT,
        skills_root=SKILLS_ROOT,
    )
    assert decision["decision"] == "allowed", decision
    decision_path = (
        root / ".task/authorization/decisions" / f"{decision['decision_id']}.json"
    )
    digest = write_immutable_json(decision_path, decision, "test decision")
    reserved = reserve(
        root, str(decision_path.relative_to(root)), digest,
        reserved_at=RESERVED_AT, idempotency_key=runtime["reservation_key"],
        skills_root=SKILLS_ROOT,
    )
    return {"ref": reserved["reservation_ref"],
            "sha256": reserved["reservation_sha256"]}


def _resolve_all(
    root: Path, prepared: dict[str, Any], reservations: dict[str, dict[str, str]],
    *, classifications: dict[str, str] | None = None,
) -> tuple[dict[str, Any], dict[str, str]]:
    source = prepared.get("authority_resolution_source", prepared["classification"])
    key = (
        "authority_bundle" if "authority_bundle" in prepared else "approval_bundle"
    )
    items = []
    for item in prepared[key]["items"]:
        operation_id = item["operation_id"]
        evidence = reservations[operation_id]
        items.append({"operation_id": operation_id,
                      "classification": (classifications or {}).get(
                          operation_id, "ready_to_resume"
                      ),
                      "evidence_ref": evidence["ref"],
                      "evidence_sha256": evidence["sha256"]})
    body = {"kind": "task_doctor_authority_resolution_bundle",
            "schema_version": 1, "workflow_id": prepared["workflow_id"],
            "plan_sha256": prepared["plan_sha256"],
            "from_classification": source,
            "user_interaction": (
                source == "needs_user_approval" and prepared["should_prompt"]
            ),
            "resolutions": items}
    binding = _write_json(
        root, f"resolution-bundle-{prepared['revision']}.json", body,
    )
    result = workflow.resolve_all(
        root, prepared["workflow_id"], binding["ref"], binding["sha256"],
        prepared["revision"],
    )
    return result, binding


def _precommit(root: Path, reservation: dict[str, str]) -> dict[str, str]:
    value, state, verified, state_sha = verify_reservation_with_recovery(
        root, reservation["ref"], reservation["sha256"], verified_at=SETTLED_AT,
        expected_version=0, skills_root=SKILLS_ROOT,
    )
    state_path = (root / ".task/authorization/state/reservations"
                  / f"{value['reservation_id']}.json")
    core = {
        "schema_version": 2, "artifact_kind": "authority_verification",
        "stage": "pre_commit", "reservation": reservation,
        "reservation_state": {"ref": str(state_path.relative_to(root)),
                              "sha256": state_sha, "version": state["version"],
                              "status": state["status"]},
        "grant_states": verified["grant_states"],
        "request_id": verified["decision"]["request"]["request_id"],
        "effective_authority_fingerprint": value["effective_authority_fingerprint"],
        "verified_at": parse_time(SETTLED_AT, "settled_at").isoformat(),
    }
    artifact = {"verification_id": f"authv-{object_sha256(core)[:24]}", **core}
    path = root / ".task/authorization/verifications" / f"{artifact['verification_id']}.json"
    digest = write_immutable_json(path, artifact, "test verification")
    return {"ref": str(path.relative_to(root)), "sha256": digest}


def _owner_effect(
    root: Path, workflow_id: str, dispatch: dict[str, Any], effect: str,
) -> dict[str, str]:
    operation_id = dispatch["operation_id"]
    owner_dispatch = dispatch["owner_dispatch"]
    if owner_dispatch["workflow_role"] == "task_scope_transition":
        if effect == "confirmed_no_effect":
            prospective = root / owner_dispatch["plan"]["prospective_task"]["ref"]
            prospective.unlink()
        transaction = apply_task_transition_plan(
            root, owner_dispatch["plan_binding"]["ref"]
        )
        assert transaction["effect_status"] == effect
        actual = transaction["execution_result_binding"]
    elif owner_dispatch["workflow_role"] == "external_advice_intake":
        owner_plan = owner_dispatch.get("plan") or json.loads(
            (root / owner_dispatch["plan_binding"]["ref"]).read_text(encoding="utf-8")
        )
        if effect == "confirmed_no_effect":
            (root / owner_plan["raw"]["source_ref"]).unlink()
        actual = apply_intake_plan(
            root, owner_dispatch["plan_binding"]["ref"]
        )["execution_result_binding"]
    elif owner_dispatch["workflow_role"] == "task_index_transition":
        if effect == "confirmed_no_effect":
            index_md = root / ".task/index.md"
            index_md.parent.mkdir(parents=True, exist_ok=True)
            index_md.write_text("# Unrelated current projection\n", encoding="utf-8")
            actual = settle_transition_no_effect(
                root, owner_dispatch["plan_binding"]["ref"], at=SETTLED_AT
            )["execution_result_binding"]
        else:
            actual = apply_transition_plan(
                root, owner_dispatch["plan_binding"]["ref"]
            )["execution_result_binding"]
    else:
        actual_body = {
            "schema_version": 1, "artifact_kind": "test_owner_result",
            "operation_id": operation_id, "status": effect,
        }
        actual = _write_json(root, f"results/{operation_id}-actual.json", actual_body)
    body = {"schema_version": 1,
            "artifact_kind": "task_doctor_owner_effect_result",
            "workflow_id": workflow_id, "operation_id": operation_id,
            "owner_skill": dispatch["owner_dispatch"]["owner_skill"],
            "plan_sha256": dispatch["owner_dispatch"]["plan_sha256"],
            "effect_status": effect, "owner_artifact": actual}
    return _write_json(root, f"results/{operation_id}-effect.json", body)


def _completion(
    root: Path, workflow_id: str, dispatch: dict[str, Any], owner: dict[str, str],
    receipt: dict[str, str], outcome: str,
) -> dict[str, str]:
    return _write_json(
        root, f"results/{dispatch['operation_id']}-completion.json",
        {"schema_version": 1, "artifact_kind": "task_doctor_owner_completion",
         "workflow_id": workflow_id, "operation_id": dispatch["operation_id"],
         "plan_sha256": dispatch["owner_dispatch"]["plan_sha256"],
         "outcome": outcome, "owner_result": owner,
         "authority_settlement": {"status": "settled", "receipt": receipt}},
    )


def _settle(
    root: Path, result: dict[str, Any], reservation: dict[str, str],
    *, no_effect: bool = False,
) -> tuple[dict[str, Any], dict[str, str]]:
    dispatch = workflow.apply(
        root, result["workflow_id"], result["next_operation"], result["revision"]
    )
    effect = "confirmed_no_effect" if no_effect else "confirmed_effect"
    owner = _owner_effect(root, result["workflow_id"], dispatch, effect)
    if no_effect:
        settled = release(
            root, reservation["ref"], reservation["sha256"], owner,
            released_at=SETTLED_AT, expected_version=0,
            idempotency_key=f"release-{dispatch['operation_id']}",
            effect_status="verified_no_effect",
        )
        receipt = {"ref": settled["ref"], "sha256": settled["sha256"]}
        outcome = "confirmed_no_effect"
    else:
        subject = root / dispatch["owner_dispatch"]["plan_binding"]["ref"]
        settled = consume(
            root, reservation["ref"], reservation["sha256"], owner,
            pre_commit_verification=_precommit(root, reservation),
            expected_subject_after_sha256=sha256_file(subject),
            consumed_at=SETTLED_AT, expected_version=0,
            idempotency_key=f"consume-{dispatch['operation_id']}",
            skills_root=SKILLS_ROOT,
        )
        receipt = {"ref": settled["ref"], "sha256": settled["sha256"]}
        outcome = "completed"
    completion = _completion(root, result["workflow_id"], dispatch, owner,
                             receipt, outcome)
    recorded = workflow.record_result(
        root, result["workflow_id"], dispatch["operation_id"], outcome,
        completion["ref"], completion["sha256"], dispatch["revision"],
    )
    return recorded, completion


def _released_completion(
    root: Path, result: dict[str, Any], reservation: dict[str, str],
    dispatch: dict[str, Any], *, key: str,
) -> tuple[dict[str, Any], dict[str, str]]:
    owner = _owner_effect(root, result["workflow_id"], dispatch,
                          "confirmed_no_effect")
    released = release(
        root, reservation["ref"], reservation["sha256"], owner,
        released_at=SETTLED_AT, expected_version=0,
        idempotency_key=key, effect_status="verified_no_effect",
    )
    completion = _completion(
        root, result["workflow_id"], dispatch, owner,
        {"ref": released["ref"], "sha256": released["sha256"]},
        "confirmed_no_effect",
    )
    return dispatch, completion


def test_arbitrary_json_cannot_resolve_authority(tmp_path: Path) -> None:
    body, _ = _plan(tmp_path)
    prepared = _prepare(tmp_path, body)
    fake = _write_json(tmp_path, "fake-reservation.json", {"reservation_id": "fake"})
    with pytest.raises(workflow.WorkflowError) as caught:
        workflow.resolve(tmp_path, prepared["workflow_id"], "op-1", "ready_to_resume",
                         fake["ref"], fake["sha256"], prepared["revision"])
    assert caught.value.code == "invalid_authority_evidence"


def test_wrong_operation_reservation_is_rejected(tmp_path: Path) -> None:
    body, runtime = _plan(tmp_path, count=2)
    prepared = _prepare(tmp_path, body)
    wrong = _materialize(tmp_path, runtime["op-2"])
    with pytest.raises(workflow.WorkflowError) as caught:
        workflow.resolve(tmp_path, prepared["workflow_id"], "op-1", "ready_to_resume",
                         wrong["ref"], wrong["sha256"], prepared["revision"])
    assert caught.value.code == "authority_binding_mismatch"


@pytest.mark.parametrize("effect_status", ["verified_no_effect", "unknown_effect"])
def test_released_or_quarantined_reservation_cannot_dispatch(
    tmp_path: Path, effect_status: str,
) -> None:
    body, runtime = _plan(tmp_path)
    prepared = _prepare(tmp_path, body)
    reservation = _materialize(tmp_path, runtime["op-1"])
    evidence = _write_json(tmp_path, "release-evidence.json", {"typed": True})
    release(tmp_path, reservation["ref"], reservation["sha256"], evidence,
            released_at=SETTLED_AT, expected_version=0,
            idempotency_key=f"release-{effect_status}", effect_status=effect_status)
    with pytest.raises(workflow.WorkflowError) as caught:
        workflow.resolve(tmp_path, prepared["workflow_id"], "op-1", "ready_to_resume",
                         reservation["ref"], reservation["sha256"],
                         prepared["revision"])
    assert caught.value.code == "authority_reservation_not_current"


def test_not_started_release_routes_replan_instead_of_owner_completion(
    tmp_path: Path,
) -> None:
    body, runtime = _plan(tmp_path)
    prepared = _prepare(tmp_path, body)
    reservation = _materialize(tmp_path, runtime["op-1"])
    evidence = _write_json(tmp_path, "not-started.json", {"dispatched": False})
    release(
        tmp_path, reservation["ref"], reservation["sha256"], evidence,
        released_at=SETTLED_AT, expected_version=0,
        idempotency_key="release-before-dispatch", effect_status="not_started",
    )

    status = workflow.status(tmp_path, prepared["workflow_id"])
    assert status["classification"] == "plan_changed"
    assert status["workflow_state"] == "replanning_required"
    assert status["next_action"] == "prepare_new_plan"
    assert status["should_prompt"] is False


def test_exhausted_fixed_grant_recipe_routes_immutable_replan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    body, _runtime = _plan(tmp_path)
    from task_doctor_workflow_lib import authority_overlay

    def exhausted(
        _root: Path, request: dict[str, Any], _context: dict[str, Any], **_kwargs: Any,
    ) -> dict[str, Any]:
        return {
            "schema_version": 2,
            "status": "resolved",
            "resolution": "source_authority_exhausted",
            "should_prompt": False,
            "user_action": None,
            "next_action": {"actor": "system", "code": "rebuild_exact_grant_recipe"},
            "workflow_basis": {
                "kind": "source_authority_exhausted",
                "request_sha256": object_sha256(request),
                "reservation": None, "reservation_state": None,
                "decision": None, "source_approval": None,
                "settlement_receipt": None,
                "blocker_codes": ["source_authority_no_usable_grant"],
            },
        }

    monkeypatch.setattr(authority_overlay, "resolve_operation", exhausted)
    prepared = _prepare(tmp_path, body)
    assert prepared["classification"] == "plan_changed"
    assert prepared["workflow_state"] == "replanning_required"
    assert prepared["next_action"] == "prepare_new_plan"
    assert prepared["should_prompt"] is False
    assert prepared["approval_interactions"] == {"used": 0, "maximum": 0}


@pytest.mark.parametrize(
    "mode", ["execute_with_declared_authorization", "consolidated_review"],
)
def test_source_recovery_approval_wait_requires_new_plan_without_interaction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str,
) -> None:
    body, _runtime = _plan(tmp_path, mode=mode)
    from task_doctor_workflow_lib import authority_overlay

    def recovery_wait(
        _root: Path, request: dict[str, Any], _context: dict[str, Any], **_kwargs: Any,
    ) -> dict[str, Any]:
        runtime_source = {"approval_id": "old-source"}
        return {
            "schema_version": 2,
            "status": "resolved",
            "resolution": "needs_user_approval",
            "should_prompt": True,
            "user_action": "approve",
            "next_action": {
                "actor": "user", "code": "approve_exact_recovery_projection",
            },
            "workflow_basis": {
                "kind": "source_authority_recovery_approval",
                "request_sha256": object_sha256(request),
                "reservation": None, "reservation_state": None,
                "decision": None,
                "source_approval": runtime_source,
                "recovery_recipe": {"recovery_id": "replacement-recipe"},
                "settlement_receipt": None,
                "blocker_codes": ["replacement_source_requires_user_approval"],
            },
            "covering_source_approvals": [runtime_source],
            "approval_projection": {"projection_id": "replacement-projection"},
        }

    monkeypatch.setattr(authority_overlay, "resolve_operation", recovery_wait)
    prepared = _prepare(tmp_path, body)

    assert prepared["classification"] == "plan_changed"
    assert prepared["workflow_state"] == "replanning_required"
    assert prepared["next_action"] == "prepare_new_plan"
    assert prepared["should_prompt"] is False
    assert prepared["user_action"] == "none"
    assert prepared["approval_interactions"] == {
        "used": 0,
        "maximum": 0 if mode.startswith("execute") else 1,
    }
    assert "approval_bundle" not in prepared
    journal = json.loads(
        (tmp_path / prepared["journal_ref"]).read_text(encoding="utf-8")
    )
    assert all(
        item["event"] != "semantic_approval_scope_bound"
        for item in journal["events"]
    )


def test_one_exhausted_row_suppresses_other_semantic_approval_prompt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    body, _runtime = _plan(tmp_path, count=2, mode="consolidated_review")
    from task_doctor_workflow_lib import authority_overlay

    def mixed(
        _root: Path, request: dict[str, Any], _context: dict[str, Any], **_kwargs: Any,
    ) -> dict[str, Any]:
        if request["request_id"] == "request-op-2":
            return _approval_wait_projection(object_sha256(request))
        return {
            "schema_version": 2, "status": "resolved",
            "resolution": "source_authority_exhausted", "should_prompt": False,
            "user_action": None,
            "next_action": {"actor": "system", "code": "rebuild_exact_grant_recipe"},
            "workflow_basis": {
                "kind": "source_authority_exhausted",
                "request_sha256": object_sha256(request),
                "reservation": None, "reservation_state": None,
                "decision": None, "source_approval": None,
                "settlement_receipt": None,
                "blocker_codes": ["source_authority_no_usable_grant"],
            },
        }

    monkeypatch.setattr(authority_overlay, "resolve_operation", mixed)
    prepared = _prepare(tmp_path, body)
    assert prepared["classification"] == "plan_changed"
    assert prepared["workflow_state"] == "replanning_required"
    assert prepared["should_prompt"] is False
    assert prepared["next_operation"] == "op-1"
    assert prepared["approval_interactions"] == {"used": 0, "maximum": 1}


def test_verified_no_effect_release_requires_and_recovers_exact_owner_result(
    tmp_path: Path,
) -> None:
    body, runtime = _plan(tmp_path)
    prepared = _prepare(tmp_path, body)
    reservation = _materialize(tmp_path, runtime["op-1"])
    owner_dispatch = prepared["authority_bundle"]["items"][0]
    dispatch = {"operation_id": "op-1", "owner_dispatch": owner_dispatch}
    owner = _owner_effect(
        tmp_path, prepared["workflow_id"], dispatch, "confirmed_no_effect"
    )
    released = release(
        tmp_path, reservation["ref"], reservation["sha256"], owner,
        released_at=SETTLED_AT, expected_version=0,
        idempotency_key="release-after-owner-no-effect",
        effect_status="verified_no_effect",
    )
    from task_doctor_workflow_lib import authority_overlay

    journal = json.loads(
        (tmp_path / prepared["journal_ref"]).read_text(encoding="utf-8")
    )
    live = authority_overlay.resolve_operation(
        tmp_path, runtime["op-1"]["request"], runtime["op-1"]["context"],
        evaluated_at=SETTLED_AT, skills_root=SKILLS_ROOT,
    )
    assert live["workflow_basis"]["settlement_receipt"]["ref"] == released["ref"]
    projected = authority_overlay._settlement_projection(
        tmp_path, journal, journal["plan"]["operations"][0], live
    )
    assert projected["resolution"] == "recover_settlement"
    assert projected["next_action"] == {
        "actor": "system", "code": "recover_owner_completion"
    }


def test_real_v2_reservation_use_receipt_and_replay(tmp_path: Path) -> None:
    body, runtime = _plan(tmp_path)
    prepared = _prepare(tmp_path, body)
    reservation = _materialize(tmp_path, runtime["op-1"])
    resolved, _ = _resolve_all(tmp_path, prepared, {"op-1": reservation})
    assert resolved["classification"] == "ready_to_resume"
    recorded, completion = _settle(tmp_path, resolved, reservation)
    assert recorded["workflow_state"] == "complete"
    replay = workflow.record_result(
        tmp_path, recorded["workflow_id"], "op-1", "completed",
        completion["ref"], completion["sha256"], recorded["revision"],
    )
    assert replay["replayed"] is True
    assert replay["revision"] == recorded["revision"]
    completion_body = json.loads((tmp_path / completion["ref"]).read_text(encoding="utf-8"))
    effect_binding = completion_body["owner_result"]
    effect_body = json.loads((tmp_path / effect_binding["ref"]).read_text(encoding="utf-8"))
    (tmp_path / effect_body["owner_artifact"]["ref"]).unlink()
    with pytest.raises(workflow.WorkflowError) as caught:
        workflow.record_result(
            tmp_path, recorded["workflow_id"], "op-1", "completed",
            completion["ref"], completion["sha256"], replay["revision"],
        )
    assert caught.value.code == "evidence_not_found"


def test_fake_settlement_receipt_is_rejected(tmp_path: Path) -> None:
    body, runtime = _plan(tmp_path)
    prepared = _prepare(tmp_path, body)
    reservation = _materialize(tmp_path, runtime["op-1"])
    resolved, _ = _resolve_all(tmp_path, prepared, {"op-1": reservation})
    dispatch = workflow.apply(
        tmp_path, resolved["workflow_id"], "op-1", resolved["revision"]
    )
    owner = _owner_effect(tmp_path, resolved["workflow_id"], dispatch,
                          "confirmed_effect")
    fake = _write_json(tmp_path, "fake-use-receipt.json",
                       {"schema_version": 2,
                        "artifact_kind": "authority_use_receipt",
                        "reservation": reservation})
    completion = _completion(tmp_path, resolved["workflow_id"], dispatch, owner,
                             fake, "completed")
    with pytest.raises(workflow.WorkflowError) as caught:
        workflow.record_result(
            tmp_path, resolved["workflow_id"], "op-1", "completed",
            completion["ref"], completion["sha256"], dispatch["revision"],
        )
    assert caught.value.code == "invalid_authority_settlement"


def test_verified_no_effect_is_terminal_and_advances(tmp_path: Path) -> None:
    body, runtime = _plan(tmp_path, count=2)
    prepared = _prepare(tmp_path, body)
    reservations = {key: _materialize(tmp_path, value) for key, value in runtime.items()}
    resolved, _ = _resolve_all(tmp_path, prepared, reservations)
    advanced, completion = _settle(tmp_path, resolved, reservations["op-1"],
                                   no_effect=True)
    assert advanced["next_operation"] == "op-2"
    assert advanced["operations"] if "operations" in advanced else True
    replay = workflow.record_result(
        tmp_path, advanced["workflow_id"], "op-1", "confirmed_no_effect",
        completion["ref"], completion["sha256"], advanced["revision"],
    )
    assert replay["replayed"] is True
    assert replay["next_operation"] == "op-2"


def test_optional_skip_requires_release_and_leaves_no_reserved_budget(
    tmp_path: Path,
) -> None:
    body, runtime = _plan(tmp_path)
    body["operations"][0]["required"] = False
    prepared = _prepare(tmp_path, body)
    reservation = _materialize(tmp_path, runtime["op-1"])
    resolved, _ = _resolve_all(tmp_path, prepared, {"op-1": reservation})
    fake = _write_json(tmp_path, "skip-note.json", {"decision": "skip"})
    with pytest.raises(workflow.WorkflowError) as caught:
        workflow.skip(tmp_path, resolved["workflow_id"], "op-1",
                      fake["ref"], fake["sha256"], resolved["revision"])
    assert caught.value.code == "invalid_owner_result"
    dispatch = {"operation_id": "op-1",
                "owner_dispatch": prepared["authority_bundle"]["items"][0]}
    _, completion = _released_completion(
        tmp_path, resolved, reservation, dispatch, key="skip-release"
    )
    skipped = workflow.skip(
        tmp_path, resolved["workflow_id"], "op-1",
        completion["ref"], completion["sha256"], resolved["revision"],
    )
    assert skipped["workflow_state"] == "complete"
    grant_state = json.loads(
        (tmp_path / ".task/authorization/state/grants/grant-op-1.json")
        .read_text(encoding="utf-8")
    )
    assert grant_state["reserved_uses"] == 0
    assert grant_state["consumed_uses"] == 0
    assert grant_state["remaining_uses"] == 1


@pytest.mark.parametrize("outcome", ["plan_changed", "blocked_by_defect"])
def test_post_dispatch_block_requires_verified_no_effect_release(
    tmp_path: Path, outcome: str,
) -> None:
    body, runtime = _plan(tmp_path)
    prepared = _prepare(tmp_path, body)
    reservation = _materialize(tmp_path, runtime["op-1"])
    resolved, _ = _resolve_all(tmp_path, prepared, {"op-1": reservation})
    dispatch = workflow.apply(
        tmp_path, resolved["workflow_id"], "op-1", resolved["revision"]
    )
    fake = _write_json(tmp_path, "blocked-note.json", {"reason": outcome})
    with pytest.raises(workflow.WorkflowError) as caught:
        workflow.record_result(
            tmp_path, resolved["workflow_id"], "op-1", outcome,
            fake["ref"], fake["sha256"], dispatch["revision"],
        )
    assert caught.value.code == "invalid_owner_result"
    _, completion = _released_completion(
        tmp_path, resolved, reservation, dispatch, key=f"release-{outcome}"
    )
    blocked = workflow.record_result(
        tmp_path, resolved["workflow_id"], "op-1", outcome,
        completion["ref"], completion["sha256"], dispatch["revision"],
    )
    assert blocked["classification"] == outcome
    grant_state = json.loads(
        (tmp_path / ".task/authorization/state/grants/grant-op-1.json")
        .read_text(encoding="utf-8")
    )
    assert grant_state["reserved_uses"] == 0
    assert grant_state["consumed_uses"] == 0


def test_unknown_effect_requires_actual_quarantine_receipt(tmp_path: Path) -> None:
    body, runtime = _plan(tmp_path)
    prepared = _prepare(tmp_path, body)
    reservation = _materialize(tmp_path, runtime["op-1"])
    resolved, _ = _resolve_all(tmp_path, prepared, {"op-1": reservation})
    dispatch = workflow.apply(
        tmp_path, resolved["workflow_id"], "op-1", resolved["revision"]
    )
    fake = _write_json(tmp_path, "unknown-note.json", {"status": "unknown"})
    with pytest.raises(workflow.WorkflowError) as caught:
        workflow.record_result(
            tmp_path, resolved["workflow_id"], "op-1", "unknown_effect",
            fake["ref"], fake["sha256"], dispatch["revision"],
        )
    assert caught.value.code == "invalid_authority_settlement"
    quarantined = release(
        tmp_path, reservation["ref"], reservation["sha256"], fake,
        released_at=SETTLED_AT, expected_version=0,
        idempotency_key="quarantine-op-1", effect_status="unknown_effect",
    )
    receipt = {"ref": quarantined["ref"], "sha256": quarantined["sha256"]}
    unknown = workflow.record_result(
        tmp_path, resolved["workflow_id"], "op-1", "unknown_effect",
        receipt["ref"], receipt["sha256"], dispatch["revision"],
    )
    assert unknown["classification"] == "effect_reconciliation"
    replay = workflow.recover(
        tmp_path, resolved["workflow_id"], "op-1", "still_unknown",
        receipt["ref"], receipt["sha256"], unknown["revision"],
    )
    assert replay["replayed"] is True
    reservation_state = json.loads(
        (tmp_path / ".task/authorization/state/reservations"
         / f"{quarantined['release_receipt']['reservation']['ref'].split('/')[-1].removesuffix('.json')}.json")
        .read_text(encoding="utf-8")
    )
    assert reservation_state["status"] == "quarantined_unknown_effect"


def test_unregistered_authority_free_owner_operation_fails_closed(tmp_path: Path) -> None:
    owner_plan = {"record_id": "record-id-1", "fact_kind": "task-doctor"}
    plan_binding = _write_json(tmp_path, "plans/record-id-1.json",
                               owner_plan)
    operation = {
        "operation_id": "record", "workflow_role": "workflow_record",
        "owner_skill": "$record-agent-work-log",
        "effect_class": "publish_factual_work_record",
        "effect_summary": "Publish one exact factual workflow record.",
        "required": True, "dependencies": [], "plan": owner_plan,
        "plan_binding": plan_binding,
        "authority": {"applicability": "none",
                      "operation": {"skill_id": "record-agent-work-log",
                                    "skill_version": "2.0.0",
                                    "operation_id": "publish_agent_work_log",
                                    "operation_version": "1"}},
    }
    body = {"schema_version": 1,
            "execution_mode": "execute_with_declared_authorization",
            "complete_effect_inventory": True, "max_user_approval_interactions": 0,
            "authorized_local_effects": ["publish_factual_work_record"],
            "excluded_effects": sorted(workflow.FORBIDDEN_EFFECTS),
            "git_finalization": "deferred",
            "task_index_transition": {"status": "not_applicable",
                                      "reason": "Record-only workflow."},
            "operations": [operation],
            "authorization_basis": {
                "schema_version": 1,
                "basis_kind": "task_doctor_declared_authorization",
                "approvals": []},
            "reporting": {"detail": "concise", "language": "ko"}}
    with pytest.raises(workflow.WorkflowError) as caught:
        _prepare(tmp_path, body)
    assert caught.value.code == "invalid_plan"


def test_already_settled_resolution_closes_recreated_operation(tmp_path: Path) -> None:
    body, runtime = _plan(tmp_path)
    prepared = _prepare(tmp_path, body)
    reservation = _materialize(tmp_path, runtime["op-1"])
    dispatch = {"operation_id": "op-1", "owner_dispatch": prepared["authority_bundle"]["items"][0]}
    owner = _owner_effect(tmp_path, prepared["workflow_id"], dispatch, "confirmed_no_effect")
    released = release(
        tmp_path, reservation["ref"], reservation["sha256"], owner,
        released_at=SETTLED_AT, expected_version=0, idempotency_key="settled-before-resume",
        effect_status="verified_no_effect",
    )
    completion = _completion(
        tmp_path, prepared["workflow_id"], dispatch, owner,
        {"ref": released["ref"], "sha256": released["sha256"]},
        "confirmed_no_effect",
    )
    resolved, bundle = _resolve_all(
        tmp_path, prepared, {"op-1": completion},
        classifications={"op-1": "already_settled"},
    )
    assert resolved["workflow_state"] == "complete"
    replay = workflow.resolve_all(
        tmp_path, prepared["workflow_id"], bundle["ref"], bundle["sha256"],
        resolved["revision"],
    )
    assert replay["replayed"] is True
    (tmp_path / completion["ref"]).unlink()
    with pytest.raises(workflow.WorkflowError) as caught:
        workflow.resolve_all(
            tmp_path, prepared["workflow_id"], bundle["ref"], bundle["sha256"],
            replay["revision"],
        )
    assert caught.value.code == "evidence_not_found"


def test_old_arbitrary_authorization_basis_is_rejected(tmp_path: Path) -> None:
    body, _ = _plan(tmp_path)
    fake = _write_json(tmp_path, "user-event.json", {"event_id": "u-1"})
    body["authorization_basis"] = fake
    with pytest.raises(workflow.WorkflowError) as caught:
        _prepare(tmp_path, body)
    assert caught.value.code == "invalid_plan"


def test_declared_basis_rejects_source_copy_outside_snapshot_store(tmp_path: Path) -> None:
    body, _ = _plan(tmp_path)
    original = body["authorization_basis"]["approvals"][0]["source_approval"]
    copied = tmp_path / "copied-source-approval.json"
    copied.write_bytes((tmp_path / original["ref"]).read_bytes())
    body["authorization_basis"]["approvals"][0]["source_approval"] = {
        "ref": str(copied.relative_to(tmp_path)), "sha256": sha256_file(copied)
    }
    with pytest.raises(workflow.WorkflowError) as caught:
        _prepare(tmp_path, body)
    assert caught.value.code == "invalid_authorization_basis"


def test_materialization_bundle_exposes_exact_bridge_inputs(tmp_path: Path) -> None:
    body, _ = _plan(tmp_path)
    prepared = _prepare(tmp_path, body)
    authority = prepared["authority_bundle"]["items"][0]["authority"]
    assert authority["request_sha256"] == object_sha256(authority["request"])
    assert authority["subject"] == authority["request"]["subject"]
    assert set(authority) == {
        "applicability", "request", "request_sha256", "subject",
        "operation_manifest", "snapshot_sources", "evaluate",
        "register_grant_recipe", "reserve",
    }
    assert authority["register_grant_recipe"]["source_approval"] == (
        body["authorization_basis"]["approvals"][0]["source_approval"]
    )


def test_real_task_index_plan_kind_and_dependencies(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    indexed = tmp_path / "task.md"
    indexed.write_text("# Existing Task\n", encoding="utf-8")
    scope, scope_approval, _ = _authority_operation(
        tmp_path, workspace, "scope", workflow_role="task_scope_transition",
        spec=_default_spec(),
    )
    index_body = build_transition_plan(
        tmp_path,
        {"schema_version": 1, "updated_at": AT, "render": True,
         "events": [{"event": "upsert", "id": "task-id-1", "type": "task",
                     "status": "active", "path": "task.md", "title": "Task ID 1",
                     "content_sha256": scope["plan"]["after_task"]["sha256"]}]},
    )
    validate_transition_plan(index_body)
    index_published = publish_transition_plan(tmp_path, index_body)
    index_binding = {"ref": index_published["plan_ref"],
                     "sha256": index_published["plan_file_sha256"]}
    index, index_approval, _ = _authority_operation(
        tmp_path, workspace, "index", workflow_role="task_index_transition",
        dependencies=["scope"], spec=_index_spec(), owner_plan=index_body,
        plan_binding=index_binding,
    )
    body = {"schema_version": 1,
            "execution_mode": "execute_with_declared_authorization",
            "complete_effect_inventory": True, "max_user_approval_interactions": 0,
            "authorized_local_effects": ["retarget_or_replace_task",
                                         "append_or_project_task_lifecycle"],
            "excluded_effects": sorted(workflow.FORBIDDEN_EFFECTS),
            "git_finalization": "deferred",
            "task_index_transition": {"status": "planned", "operation_id": "index"},
            "operations": [scope, index],
            "authorization_basis": {
                "schema_version": 1,
                "basis_kind": "task_doctor_declared_authorization",
                "approvals": [{"operation_id": "scope",
                               "source_approval": scope_approval},
                              {"operation_id": "index",
                               "source_approval": index_approval}]},
            "reporting": {"detail": "concise", "language": "ko"}}
    prepared = _prepare(tmp_path, body)
    assert [item["workflow_role"] for item in prepared["authority_bundle"]["items"]] == [
        "task_scope_transition"
    ]


def test_real_index_already_applied_routes_to_effect_reconciliation(
    tmp_path: Path,
) -> None:
    task = tmp_path / "task.md"
    task.write_text("# Indexed task\n", encoding="utf-8")
    plan = build_transition_plan(
        tmp_path,
        {"schema_version": 1, "updated_at": AT, "render": True,
         "events": [{"event": "upsert", "id": "task-index-applied",
                     "type": "task", "status": "active", "path": "task.md",
                     "title": "Indexed task",
                     "content_sha256": sha256_file(task)}]},
    )
    body, _runtime, binding = _index_only_workflow(tmp_path, plan)
    apply_transition_plan(tmp_path, binding["ref"])

    prepared = _prepare(tmp_path, body)
    assert prepared["classification"] == "owner_effect_reconciliation"
    assert prepared["next_action"] == "reconcile_owner_effect"
    assert prepared["next_operation"] == "index"
    assert prepared["should_prompt"] is False


def test_real_index_settled_no_effect_routes_to_internal_settlement(
    tmp_path: Path,
) -> None:
    task = tmp_path / "task.md"
    task.write_text("# Before stale index\n", encoding="utf-8")
    plan = build_transition_plan(
        tmp_path,
        {"schema_version": 1, "updated_at": AT, "render": True,
         "events": [{"event": "upsert", "id": "task-index-no-effect",
                     "type": "task", "status": "active", "path": "task.md",
                     "title": "No effect task",
                     "content_sha256": sha256_file(task)}]},
    )
    body, _runtime, binding = _index_only_workflow(tmp_path, plan)
    task.write_text("# Foreign task bytes\n", encoding="utf-8")
    settled = settle_transition_no_effect(tmp_path, binding["ref"], at=SETTLED_AT)
    assert settled["status"] in {"settled_no_effect", "already_settled_no_effect"}

    prepared = _prepare(tmp_path, body)
    assert prepared["classification"] == "owner_settled_no_effect"
    assert prepared["next_action"] == "settle_owner_no_effect"
    assert prepared["next_operation"] == "index"
    assert prepared["should_prompt"] is False


def test_real_index_materializing_routes_to_internal_wait(tmp_path: Path) -> None:
    first = tmp_path / "tasks/first.md"
    second = tmp_path / "tasks/second.md"
    first.parent.mkdir(parents=True)
    first.write_text("# First before\n", encoding="utf-8")
    second.write_text("# Second before\n", encoding="utf-8")
    first_after = b"# First after\n"
    second_after = b"# Second after\n"
    plan = build_transition_plan(
        tmp_path,
        {"schema_version": 1, "updated_at": AT, "render": True,
         "events": [
             {"event": "upsert", "id": "task-index-first", "type": "task",
              "status": "active", "path": "tasks/first.md", "title": "First",
              "content_sha256": hashlib.sha256(first_after).hexdigest()},
             {"event": "upsert", "id": "task-index-second", "type": "task",
              "status": "active", "path": "tasks/second.md", "title": "Second",
              "content_sha256": hashlib.sha256(second_after).hexdigest()},
         ]},
    )
    body, _runtime, binding = _index_only_workflow(tmp_path, plan)
    first.write_bytes(first_after)
    assert verify_transition_plan(
        tmp_path, binding["ref"], phase="apply"
    )["status"] == "materializing"

    prepared = _prepare(tmp_path, body)
    assert prepared["classification"] == "owner_materializing"
    assert prepared["next_action"] == "wait_for_owner_materialization"
    assert prepared["should_prompt"] is False


def test_real_index_recovery_required_routes_to_owner_recovery(
    tmp_path: Path,
) -> None:
    task = tmp_path / "task.md"
    task.write_text("# Recovery task\n", encoding="utf-8")
    plan = build_transition_plan(
        tmp_path,
        {"schema_version": 1, "updated_at": AT, "render": True,
         "events": [{"event": "upsert", "id": "task-index-recovery",
                     "type": "task", "status": "active", "path": "task.md",
                     "title": "Recovery task",
                     "content_sha256": sha256_file(task)}]},
    )
    body, _runtime, binding = _index_only_workflow(tmp_path, plan)
    publish_transition_intent(
        tmp_path, plan, binding["ref"], binding["sha256"]
    )
    assert verify_transition_plan(
        tmp_path, binding["ref"], phase="apply"
    )["status"] == "recovery_required"

    prepared = _prepare(tmp_path, body)
    assert prepared["classification"] == "owner_recovery_required"
    assert prepared["next_action"] == "recover_owner_operation"
    assert prepared["should_prompt"] is False


def test_real_external_advice_plan_is_owner_validated(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    source = tmp_path / "inputs/advice-id-1.md"
    source.parent.mkdir(parents=True, exist_ok=True)
    text = "# Advice ID 1\n\nPreserve one exact owner plan.\n"
    source.write_text(text, encoding="utf-8")
    advice_body = build_intake_plan(
        tmp_path, text, "Advice ID 1", "normal", at=AT,
        source_ref=str(source.relative_to(tmp_path)),
    )
    validate_intake_plan(advice_body)
    advice_published = publish_intake_plan(tmp_path, advice_body)
    advice_binding = {"ref": advice_published["plan_ref"],
                      "sha256": advice_published["plan_file_sha256"]}
    operation, approval, _ = _authority_operation(
        tmp_path, workspace, "advice", workflow_role="external_advice_intake",
        spec=_advice_spec(), owner_plan=advice_body, plan_binding=advice_binding,
    )
    body = {"schema_version": 1,
            "execution_mode": "execute_with_declared_authorization",
            "complete_effect_inventory": True, "max_user_approval_interactions": 0,
            "authorized_local_effects": [
                "intake_apply_defer_reject_or_retire_advice"
            ],
            "excluded_effects": sorted(workflow.FORBIDDEN_EFFECTS),
            "git_finalization": "deferred",
            "task_index_transition": {"status": "not_applicable",
                                      "reason": "Advice-only transition."},
            "operations": [operation],
            "authorization_basis": {
                "schema_version": 1,
                "basis_kind": "task_doctor_declared_authorization",
                "approvals": [{"operation_id": "advice",
                               "source_approval": approval}]},
            "reporting": {"detail": "concise", "language": "ko"}}
    prepared = _prepare(tmp_path, body)
    assert prepared["authority_bundle"]["items"][0]["workflow_role"] == (
        "external_advice_intake"
    )


def test_advice_workflow_requires_final_index_when_live_store_exists(
    tmp_path: Path,
) -> None:
    body, _runtime = _plan(tmp_path)
    index_dir = tmp_path / ".task"
    index_dir.mkdir(exist_ok=True)
    (index_dir / "index.jsonl").write_bytes(b"")
    (index_dir / "index.md").write_text("# Task State Index\n", encoding="utf-8")
    with pytest.raises(workflow.WorkflowError) as caught:
        _prepare(tmp_path, body)
    assert caught.value.code == "plan_incomplete"
    workflows = tmp_path / ".task/task_doctor/workflows"
    assert not workflows.exists() or not list(workflows.glob("*.json"))


def test_advice_workflow_rejects_partial_live_index_store(tmp_path: Path) -> None:
    body, _runtime = _plan(tmp_path)
    index_dir = tmp_path / ".task"
    index_dir.mkdir(exist_ok=True)
    (index_dir / "index.jsonl").write_bytes(b"")
    with pytest.raises(workflow.WorkflowError) as caught:
        _prepare(tmp_path, body)
    assert caught.value.code == "invalid_task_index_store"


def test_task_scope_forward_completion_status_resume_and_staging_cleanup(
    tmp_path: Path,
) -> None:
    body, runtime = _task_scope_workflow(tmp_path)
    prepared = _prepare(tmp_path, body)
    reservations = {
        key: _materialize(tmp_path, value) for key, value in runtime.items()
    }
    resolved, _ = _resolve_all(tmp_path, prepared, reservations)
    scope_done, completion = _settle(tmp_path, resolved, reservations["scope"])
    expected = body["operations"][0]["plan"]["after_task"]["sha256"]
    assert sha256_file(tmp_path / "task.md") == expected

    prospective = tmp_path / body["operations"][0]["plan"]["prospective_task"]["ref"]
    prospective.unlink()
    observed = workflow.status(tmp_path, scope_done["workflow_id"])
    assert observed["next_operation"] == "index"
    replay = workflow.record_result(
        tmp_path, scope_done["workflow_id"], "scope", "completed",
        completion["ref"], completion["sha256"], scope_done["revision"],
    )
    assert replay["replayed"] is True

    index_ready, _ = _resolve_all(
        tmp_path, replay, {"index": reservations["index"]}
    )
    complete, _ = _settle(
        tmp_path, index_ready, reservations["index"], no_effect=True
    )
    assert complete["workflow_state"] == "complete"
    status = workflow.status(tmp_path, complete["workflow_id"])
    assert status["classification"] == "complete"
    journal = tmp_path / status["journal_ref"]
    before = journal.read_bytes()
    resumed = workflow.resume(tmp_path, complete["workflow_id"], complete["revision"])
    assert resumed["replayed"] is True
    assert resumed["revision"] == complete["revision"]
    assert journal.read_bytes() == before


def test_scope_no_effect_cancels_index_and_releases_early_reservation(
    tmp_path: Path,
) -> None:
    body, runtime = _task_scope_workflow(tmp_path)
    prepared = _prepare(tmp_path, body)
    assert [
        item["operation_id"] for item in prepared["authority_bundle"]["items"]
    ] == ["scope"]

    scope_reservation = _materialize(tmp_path, runtime["scope"])
    early_index_reservation = _materialize(tmp_path, runtime["index"])
    resolved, _ = _resolve_all(
        tmp_path, prepared, {"scope": scope_reservation}
    )
    cancelled, _completion_binding = _settle(
        tmp_path, resolved, scope_reservation, no_effect=True
    )

    assert cancelled["classification"] == "plan_changed"
    assert cancelled["workflow_state"] == "replanning_required"
    assert cancelled["next_operation"] == "index"
    assert cancelled["next_action"] == "prepare_new_plan"
    assert cancelled["should_prompt"] is False
    journal = json.loads(
        (tmp_path / cancelled["journal_ref"]).read_text(encoding="utf-8")
    )
    index_state = journal["operation_state"]["index"]
    assert index_state["status"] == "blocked"
    assert index_state["resolution"] == "plan_changed"
    cancellation = json.loads(
        (tmp_path / index_state["result_evidence"]["ref"]).read_text(
            encoding="utf-8"
        )
    )
    assert cancellation["artifact_kind"] == (
        "task_doctor_dependency_cancellation_receipt"
    )
    assert cancellation["authority_settlement"]["status"] == (
        "released_not_started"
    )
    reservation = json.loads(
        (tmp_path / early_index_reservation["ref"]).read_text(encoding="utf-8")
    )
    state = json.loads(
        (tmp_path / ".task/authorization/state/reservations"
         / f"{reservation['reservation_id']}.json").read_text(encoding="utf-8")
    )
    assert state["status"] == "released"
    assert verify_transition_plan(
        tmp_path, body["operations"][1]["plan_binding"]["ref"], phase="apply"
    )["status"] == "stale"

    observed = workflow.status(tmp_path, cancelled["workflow_id"])
    assert observed["classification"] == "plan_changed"
    assert observed["should_prompt"] is False


def test_scope_no_effect_does_not_cancel_already_applied_index(
    tmp_path: Path,
) -> None:
    body, runtime = _task_scope_workflow(tmp_path)
    prepared = _prepare(tmp_path, body)
    scope_reservation = _materialize(tmp_path, runtime["scope"])
    index_reservation = _materialize(tmp_path, runtime["index"])
    resolved, _ = _resolve_all(
        tmp_path, prepared, {"scope": scope_reservation}
    )
    dispatch = workflow.apply(
        tmp_path, resolved["workflow_id"], "scope", resolved["revision"]
    )

    scope_plan = dispatch["owner_dispatch"]["plan"]
    prospective = tmp_path / scope_plan["prospective_task"]["ref"]
    (tmp_path / "task.md").write_bytes(prospective.read_bytes())
    index_binding = body["operations"][1]["plan_binding"]
    apply_transition_plan(tmp_path, index_binding["ref"])
    (tmp_path / "task.md").unlink()
    assert verify_transition_plan(
        tmp_path, index_binding["ref"], phase="apply"
    )["status"] == "already_applied"

    owner = _owner_effect(
        tmp_path, resolved["workflow_id"], dispatch, "confirmed_no_effect"
    )
    released = release(
        tmp_path, scope_reservation["ref"], scope_reservation["sha256"], owner,
        released_at=SETTLED_AT, expected_version=0,
        idempotency_key="release-scope-with-applied-index",
        effect_status="verified_no_effect",
    )
    completion = _completion(
        tmp_path, resolved["workflow_id"], dispatch, owner,
        {"ref": released["ref"], "sha256": released["sha256"]},
        "confirmed_no_effect",
    )
    recorded = workflow.record_result(
        tmp_path, resolved["workflow_id"], "scope", "confirmed_no_effect",
        completion["ref"], completion["sha256"], dispatch["revision"],
    )

    assert recorded["classification"] == "owner_effect_reconciliation"
    journal = json.loads(
        (tmp_path / recorded["journal_ref"]).read_text(encoding="utf-8")
    )
    index_state = journal["operation_state"]["index"]
    assert index_state["status"] == "pending"
    assert index_state["resolution"] == "already_covered"
    assert index_state["result_evidence"] is None
    reservation = json.loads(
        (tmp_path / index_reservation["ref"]).read_text(encoding="utf-8")
    )
    state = json.loads(
        (tmp_path / ".task/authorization/state/reservations"
         / f"{reservation['reservation_id']}.json").read_text(encoding="utf-8")
    )
    assert state["status"] == "reserved"


def test_dependency_cancellation_fails_if_old_index_effect_appears_later(
    tmp_path: Path,
) -> None:
    body, runtime = _task_scope_workflow(tmp_path)
    prospective = (
        tmp_path / body["operations"][0]["plan"]["prospective_task"]["ref"]
    )
    prospective_payload = prospective.read_bytes()
    prepared = _prepare(tmp_path, body)
    scope_reservation = _materialize(tmp_path, runtime["scope"])
    resolved, _ = _resolve_all(
        tmp_path, prepared, {"scope": scope_reservation}
    )
    cancelled, _ = _settle(
        tmp_path, resolved, scope_reservation, no_effect=True
    )
    assert cancelled["classification"] == "plan_changed"

    (tmp_path / "task.md").write_bytes(prospective_payload)
    index_binding = body["operations"][1]["plan_binding"]
    apply_transition_plan(tmp_path, index_binding["ref"])
    assert verify_transition_plan(
        tmp_path, index_binding["ref"], phase="apply"
    )["status"] == "already_applied"

    with pytest.raises(workflow.WorkflowError) as caught:
        workflow.status(tmp_path, cancelled["workflow_id"])
    assert caught.value.code == "stale_dependency_cancellation"


def test_terminal_evidence_loss_blocks_later_dispatch_without_writing(
    tmp_path: Path,
) -> None:
    body, runtime = _plan(tmp_path, count=2)
    prepared = _prepare(tmp_path, body)
    reservations = {
        key: _materialize(tmp_path, value) for key, value in runtime.items()
    }
    resolved, _ = _resolve_all(tmp_path, prepared, reservations)
    advanced, completion = _settle(
        tmp_path, resolved, reservations["op-1"], no_effect=True
    )
    journal = tmp_path / advanced["journal_ref"]
    before = journal.read_bytes()
    (tmp_path / completion["ref"]).unlink()
    with pytest.raises(workflow.WorkflowError) as caught:
        workflow.apply(
            tmp_path, advanced["workflow_id"], "op-2", advanced["revision"]
        )
    assert caught.value.code == "evidence_not_found"
    assert journal.read_bytes() == before


@pytest.mark.parametrize(
    "tamper",
    ["false_terminal", "revision", "unknown_event", "classification", "timestamp", "extra"],
)
def test_closed_journal_rejects_structural_and_event_tampering(
    tmp_path: Path, tamper: str,
) -> None:
    body, _ = _plan(tmp_path)
    prepared = _prepare(tmp_path, body)
    journal_path = tmp_path / prepared["journal_ref"]
    journal = json.loads(journal_path.read_text(encoding="utf-8"))
    if tamper == "false_terminal":
        journal["operation_state"]["op-1"].update(
            status="complete", resolution="already_settled",
            resolution_evidence=None, result_evidence=None,
        )
    elif tamper == "revision":
        journal["revision"] += 1
    elif tamper == "unknown_event":
        journal["events"].append({"at": journal["updated_at"], "event": "unknown"})
        journal["revision"] += 1
    elif tamper == "classification":
        journal["events"].append({
            "at": journal["updated_at"], "event": "authority_resolved",
            "operation_id": "op-1", "classification": "invented",
            "evidence": {"ref": "evidence.json", "sha256": "0" * 64},
        })
        journal["revision"] += 1
    elif tamper == "timestamp":
        journal["created_at"] = "not-rfc3339"
        journal["events"][0]["at"] = "not-rfc3339"
    else:
        journal["unexpected"] = True
    journal_path.write_bytes(
        json.dumps(journal, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    )
    with pytest.raises(workflow.WorkflowError) as caught:
        workflow.status(tmp_path, prepared["workflow_id"])
    assert caught.value.code == "invalid_journal"


def test_plan_changed_projection_does_not_prompt_before_new_exact_plan(
    tmp_path: Path,
) -> None:
    body, _ = _plan(tmp_path)
    prepared = _prepare(tmp_path, body)
    evidence = _write_json(tmp_path, "plan-change.json", {"reason_id": "reason-1"})
    changed = workflow.resolve(
        tmp_path, prepared["workflow_id"], "op-1", "plan_changed",
        evidence["ref"], evidence["sha256"], prepared["revision"],
    )
    assert changed["classification"] == "plan_changed"
    assert changed["next_action"] == "prepare_new_plan"
    assert changed["should_prompt"] is False
    assert changed["user_action"] == "none"
    assert "wait" not in changed


@pytest.mark.parametrize(
    "initial_resolution",
    [
        "ready_to_resume", "projection_repair", "already_settled",
        "effect_reconciliation", "plan_changed", "blocked_by_defect",
    ],
)
def test_live_resolution_cannot_be_declared_in_initial_plan(
    tmp_path: Path, initial_resolution: str,
) -> None:
    body, _ = _plan(tmp_path)
    body["operations"][0]["initial_resolution"] = initial_resolution
    with pytest.raises(workflow.WorkflowError) as caught:
        workflow.normalize_plan(body)
    assert caught.value.code == "invalid_plan"


@pytest.mark.parametrize(
    "identity",
    [
        "request_id", "request_idempotency", "grant_id",
        "grant_idempotency", "reservation_idempotency",
    ],
)
def test_governed_operation_collision_identities_are_rejected(
    tmp_path: Path, identity: str,
) -> None:
    body, _ = _plan(tmp_path, count=2)
    first = body["operations"][0]["authority"]
    second = body["operations"][1]["authority"]
    if identity == "request_id":
        second["request"]["request_id"] = first["request"]["request_id"]
    elif identity == "request_idempotency":
        second["request"]["idempotency_key"] = first["request"]["idempotency_key"]
    elif identity == "grant_id":
        second["materialization"]["grant_spec"]["grant_id"] = (
            first["materialization"]["grant_spec"]["grant_id"]
        )
    elif identity == "grant_idempotency":
        second["materialization"]["grant_spec"]["idempotency_key"] = (
            first["materialization"]["grant_spec"]["idempotency_key"]
        )
    else:
        second["materialization"]["reservation"]["idempotency_key"] = (
            first["materialization"]["reservation"]["idempotency_key"]
        )
    with pytest.raises(workflow.WorkflowError) as caught:
        workflow.normalize_plan(body)
    assert caught.value.code == "invalid_authority_contract"


def test_lineage_and_attempt_ids_may_be_shared_across_exact_operations(
    tmp_path: Path,
) -> None:
    body, _ = _plan(tmp_path, count=2)
    first = body["operations"][0]["authority"]
    second = body["operations"][1]["authority"]
    second["request"]["attempt_id"] = first["request"]["attempt_id"]
    second["materialization"]["grant_spec"]["lineage_id"] = (
        first["materialization"]["grant_spec"]["lineage_id"]
    )
    normalized = workflow.normalize_plan(body)
    assert len(normalized["operations"]) == 2


@pytest.mark.parametrize(
    "invalid_recipe",
    [
        "request_budget_bool", "reservation_units_bool", "missing_reservation_units",
        "grant_budget_bool", "invalid_evaluated_at", "reservation_before_evaluation",
        "expires_at_reservation", "invalid_grant_id",
    ],
)
def test_invalid_authority_materialization_fails_during_plan_normalization(
    tmp_path: Path, invalid_recipe: str,
) -> None:
    body, _ = _plan(tmp_path)
    authority = body["operations"][0]["authority"]
    request = authority["request"]
    materialization = authority["materialization"]
    if invalid_recipe == "request_budget_bool":
        request["use_budget_requested"] = True
    elif invalid_recipe == "reservation_units_bool":
        request["reservation_units"] = True
    elif invalid_recipe == "missing_reservation_units":
        request.pop("reservation_units")
    elif invalid_recipe == "grant_budget_bool":
        materialization["grant_spec"]["max_uses"] = True
    elif invalid_recipe == "invalid_evaluated_at":
        materialization["evaluated_at"] = "today"
    elif invalid_recipe == "reservation_before_evaluation":
        materialization["reservation"]["reserved_at"] = (
            "2026-07-18T09:59:00+09:00"
        )
    elif invalid_recipe == "expires_at_reservation":
        materialization["grant_spec"]["expires_at"] = RESERVED_AT
    else:
        materialization["grant_spec"]["grant_id"] = "bad id"
    with pytest.raises(workflow.WorkflowError) as caught:
        workflow.normalize_plan(body)
    assert caught.value.code == "invalid_authority_contract"


def test_task_scope_arbitrary_owner_plan_fails_closed_before_publication(
    tmp_path: Path,
) -> None:
    body, _ = _task_scope_workflow(tmp_path)
    operation = body["operations"][0]
    arbitrary = {"plan_kind": "task_transition_plan", "payload": "untyped"}
    binding = _write_json(tmp_path, "bad-task-transition.json", arbitrary)
    operation["plan"] = arbitrary
    operation["plan_binding"] = binding
    operation["authority"]["request"]["subject"].update(
        ref=binding["ref"], digest=binding["sha256"]
    )
    with pytest.raises(workflow.WorkflowError) as caught:
        _prepare(tmp_path, body)
    assert caught.value.code == "invalid_owner_plan"
    assert not list((tmp_path / ".task/task_doctor/workflows").glob("*.json"))


@pytest.mark.parametrize("workflow_role", ["owner_effect", "task_pack_transition"])
def test_task_scope_operation_cannot_spoof_or_reuse_task_pack_role(
    tmp_path: Path, workflow_role: str,
) -> None:
    body, _ = _task_scope_workflow(tmp_path)
    body["operations"][0]["workflow_role"] = workflow_role
    with pytest.raises(workflow.WorkflowError) as caught:
        workflow.normalize_plan(body)
    assert caught.value.code == "invalid_plan"


def test_unsupported_task_pack_operation_is_absent_from_public_manifest() -> None:
    operation, binding = load_operation(
        "task-doctor", "2.2.0", "normalize_initial_selection", "1",
        skills_root=SKILLS_ROOT,
    )
    assert operation is None
    assert binding is not None


def test_task_transition_kind_must_match_before_task_existence(tmp_path: Path) -> None:
    prospective = tmp_path / ".task/task_doctor/prospective/new-task.md"
    prospective.parent.mkdir(parents=True)
    prospective.write_text("# New Task\n", encoding="utf-8")
    with pytest.raises(workflow.WorkflowError) as caught:
        build_task_transition_plan(
            tmp_path, "new-task", "replace_task",
            ".task/task_doctor/prospective/new-task.md",
        )
    assert caught.value.code == "invalid_owner_plan"


@pytest.mark.parametrize("transition_kind", ["candidate_promotion", "task_pack_promotion"])
def test_task_transition_rejects_non_task_promotion_kinds(
    tmp_path: Path, transition_kind: str,
) -> None:
    prospective = tmp_path / ".task/task_doctor/prospective/no-pack-kind.md"
    prospective.parent.mkdir(parents=True)
    prospective.write_text("# Task-only transition\n", encoding="utf-8")
    with pytest.raises(workflow.WorkflowError) as caught:
        build_task_transition_plan(
            tmp_path, "no-pack-kind", transition_kind,
            ".task/task_doctor/prospective/no-pack-kind.md",
        )
    assert caught.value.code == "invalid_owner_plan"


def test_task_scope_typed_looking_arbitrary_result_is_rejected(
    tmp_path: Path,
) -> None:
    body, runtime = _task_scope_workflow(tmp_path)
    prepared = _prepare(tmp_path, body)
    reservation = _materialize(tmp_path, runtime["scope"])
    index_reservation = _materialize(tmp_path, runtime["index"])
    resolved, _ = _resolve_all(
        tmp_path, prepared, {"scope": reservation, "index": index_reservation}
    )
    dispatch = workflow.apply(
        tmp_path, resolved["workflow_id"], "scope", resolved["revision"]
    )
    plan = dispatch["owner_dispatch"]["plan"]
    prospective = tmp_path / plan["prospective_task"]["ref"]
    (tmp_path / "task.md").write_bytes(prospective.read_bytes())
    arbitrary = _write_json(
        tmp_path, "results/scope-arbitrary.json",
        {"schema_version": 1, "artifact_kind": "task_transition_result",
         "transition_id": plan["transition_id"]},
    )
    owner = _write_json(
        tmp_path, "results/scope-effect-arbitrary.json",
        {"schema_version": 1,
         "artifact_kind": "task_doctor_owner_effect_result",
         "workflow_id": resolved["workflow_id"], "operation_id": "scope",
         "owner_skill": "task-doctor",
         "plan_sha256": dispatch["owner_dispatch"]["plan_sha256"],
         "effect_status": "confirmed_effect", "owner_artifact": arbitrary},
    )
    settled = consume(
        tmp_path, reservation["ref"], reservation["sha256"], owner,
        pre_commit_verification=_precommit(tmp_path, reservation),
        expected_subject_after_sha256=sha256_file(
            tmp_path / dispatch["owner_dispatch"]["plan_binding"]["ref"]
        ),
        consumed_at=SETTLED_AT, expected_version=0,
        idempotency_key="consume-scope-arbitrary", skills_root=SKILLS_ROOT,
    )
    completion = _completion(
        tmp_path, resolved["workflow_id"], dispatch, owner,
        {"ref": settled["ref"], "sha256": settled["sha256"]}, "completed",
    )
    with pytest.raises(workflow.WorkflowError) as caught:
        workflow.record_result(
            tmp_path, resolved["workflow_id"], "scope", "completed",
            completion["ref"], completion["sha256"], dispatch["revision"],
        )
    assert caught.value.code == "invalid_owner_result"


def test_task_scope_closed_result_rejects_raw_canonical_task_mismatch(
    tmp_path: Path,
) -> None:
    body, runtime = _task_scope_workflow(tmp_path)
    prepared = _prepare(tmp_path, body)
    reservation = _materialize(tmp_path, runtime["scope"])
    index_reservation = _materialize(tmp_path, runtime["index"])
    resolved, _ = _resolve_all(
        tmp_path, prepared, {"scope": reservation, "index": index_reservation}
    )
    dispatch = workflow.apply(
        tmp_path, resolved["workflow_id"], "scope", resolved["revision"]
    )
    plan = dispatch["owner_dispatch"]["plan"]
    actual = _write_json(
        tmp_path, "results/scope-claimed.json",
        {"schema_version": 1, "artifact_kind": "task_transition_result",
         "transition_id": plan["transition_id"],
         "transition_kind": plan["transition_kind"],
         "plan_sha256": plan["plan_sha256"],
         "effect_status": "confirmed_effect",
         "canonical_task": {"ref": "task.md", "exists": True,
                            "sha256": plan["after_task"]["sha256"]}},
    )
    owner = _write_json(
        tmp_path, "results/scope-effect-claimed.json",
        {"schema_version": 1,
         "artifact_kind": "task_doctor_owner_effect_result",
         "workflow_id": resolved["workflow_id"], "operation_id": "scope",
         "owner_skill": "task-doctor",
         "plan_sha256": dispatch["owner_dispatch"]["plan_sha256"],
         "effect_status": "confirmed_effect", "owner_artifact": actual},
    )
    settled = consume(
        tmp_path, reservation["ref"], reservation["sha256"], owner,
        pre_commit_verification=_precommit(tmp_path, reservation),
        expected_subject_after_sha256=sha256_file(
            tmp_path / dispatch["owner_dispatch"]["plan_binding"]["ref"]
        ),
        consumed_at=SETTLED_AT, expected_version=0,
        idempotency_key="consume-scope-claimed", skills_root=SKILLS_ROOT,
    )
    completion = _completion(
        tmp_path, resolved["workflow_id"], dispatch, owner,
        {"ref": settled["ref"], "sha256": settled["sha256"]}, "completed",
    )
    with pytest.raises(workflow.WorkflowError) as caught:
        workflow.record_result(
            tmp_path, resolved["workflow_id"], "scope", "completed",
            completion["ref"], completion["sha256"], dispatch["revision"],
        )
    assert caught.value.code == "invalid_owner_result"


def test_declared_basis_rejects_unused_extra_approval(tmp_path: Path) -> None:
    body, _ = _plan(tmp_path)
    source = body["authorization_basis"]["approvals"][0]["source_approval"]
    body["authorization_basis"]["approvals"].append(
        {"operation_id": "unused", "source_approval": source}
    )
    with pytest.raises(workflow.WorkflowError) as caught:
        workflow.normalize_plan(body)
    assert caught.value.code == "invalid_authorization_basis"


def test_owner_plan_binding_rejects_noncanonical_alias_ref(tmp_path: Path) -> None:
    body, _ = _plan(tmp_path)
    operation = body["operations"][0]
    aliased = f"./{operation['plan_binding']['ref']}"
    operation["plan_binding"]["ref"] = aliased
    operation["authority"]["request"]["subject"]["ref"] = aliased
    with pytest.raises(workflow.WorkflowError) as caught:
        _prepare(tmp_path, body)
    assert caught.value.code == "invalid_evidence"


def test_owner_plan_binding_rejects_symlink_ancestor(tmp_path: Path) -> None:
    body, _ = _task_scope_workflow(tmp_path)
    original = tmp_path / ".task/task_doctor/transition-plans"
    relocated = tmp_path / ".task/task_doctor/transition-plans-real"
    original.rename(relocated)
    original.symlink_to("transition-plans-real", target_is_directory=True)
    with pytest.raises(workflow.WorkflowError) as caught:
        _prepare(tmp_path, body)
    assert caught.value.code == "invalid_evidence"
    workflows = tmp_path / ".task/task_doctor/workflows"
    assert not workflows.exists() or not list(workflows.glob("*.json"))


def test_journal_publication_fails_on_mid_write_ancestor_swap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    body, _runtime = _plan(tmp_path)
    original_verify = journal_store._verify_directory_identity
    checks = 0

    def swap_workflow_directory(
        root_path: Path, relative_parent: Any, expected: Any,
    ) -> None:
        nonlocal checks
        checks += 1
        if checks == 4:
            workflows = root_path / relative_parent
            workflows.rename(workflows.parent / "workflows-detached")
            workflows.mkdir()
        original_verify(root_path, relative_parent, expected)

    monkeypatch.setattr(
        journal_store, "_verify_directory_identity", swap_workflow_directory
    )
    with pytest.raises(workflow.WorkflowError) as caught:
        _prepare(tmp_path, body)
    assert caught.value.code == "invalid_journal_path"
    assert not list(
        (tmp_path / ".task/task_doctor/workflows").glob("*.json")
    )


def test_reservation_state_rejects_symlink_ancestor(tmp_path: Path) -> None:
    body, runtime = _plan(tmp_path)
    prepared = _prepare(tmp_path, body)
    reservation = _materialize(tmp_path, runtime["op-1"])
    original = tmp_path / ".task/authorization/state"
    relocated = tmp_path / ".task/authorization/state-real"
    original.rename(relocated)
    original.symlink_to("state-real", target_is_directory=True)
    journal = tmp_path / prepared["journal_ref"]
    before = journal.read_bytes()
    with pytest.raises(workflow.WorkflowError) as caught:
        workflow.resolve(
            tmp_path, prepared["workflow_id"], "op-1", "ready_to_resume",
            reservation["ref"], reservation["sha256"], prepared["revision"],
        )
    assert caught.value.code in {"invalid_evidence", "invalid_authority_evidence"}
    assert journal.read_bytes() == before


def test_terminal_completion_rejects_symlink_ancestor(tmp_path: Path) -> None:
    body, runtime = _plan(tmp_path)
    prepared = _prepare(tmp_path, body)
    reservation = _materialize(tmp_path, runtime["op-1"])
    resolved, _ = _resolve_all(tmp_path, prepared, {"op-1": reservation})
    complete, _ = _settle(tmp_path, resolved, reservation, no_effect=True)
    original = tmp_path / "results"
    relocated = tmp_path / "results-real"
    original.rename(relocated)
    original.symlink_to("results-real", target_is_directory=True)
    with pytest.raises(workflow.WorkflowError) as caught:
        workflow.status(tmp_path, complete["workflow_id"])
    assert caught.value.code == "invalid_evidence"


def test_journal_output_rejects_symlinked_task_ancestor(tmp_path: Path) -> None:
    body, _ = _plan(tmp_path)
    original = tmp_path / ".task"
    target = tmp_path / "journal-target"
    original.rename(target)
    (tmp_path / ".task").symlink_to("journal-target", target_is_directory=True)
    with pytest.raises(workflow.WorkflowError) as caught:
        _prepare(tmp_path, body)
    assert caught.value.code == "invalid_journal_path"
    workflows = target / "task_doctor/workflows"
    assert not workflows.exists() or not list(workflows.glob("*.json"))


@pytest.mark.parametrize("semantic_tamper", ["forbidden_effect", "authority_free"])
def test_journal_rejects_rehashed_semantically_invalid_embedded_plan(
    tmp_path: Path, semantic_tamper: str,
) -> None:
    body, _ = _plan(tmp_path)
    prepared = _prepare(tmp_path, body)
    original = tmp_path / prepared["journal_ref"]
    journal = json.loads(original.read_text(encoding="utf-8"))
    operation = journal["plan"]["operations"][0]
    if semantic_tamper == "forbidden_effect":
        operation["effect_class"] = "implementation"
        journal["plan"]["authorized_local_effects"] = ["implementation"]
    else:
        operation["owner_skill"] = "record-agent-work-log"
        operation["workflow_role"] = "workflow_record"
        operation["effect_class"] = "publish_factual_work_record"
        operation["initial_resolution"] = "authority_not_applicable"
        operation["authority"] = {
            "applicability": "none",
            "operation": {
                "skill_id": "record-agent-work-log", "skill_version": "2.0.0",
                "operation_id": "publish_agent_work_log", "operation_version": "1",
            },
            "operation_manifest": operation["authority"]["operation_manifest"],
        }
        journal["plan"]["authorized_local_effects"] = [
            "publish_factual_work_record"
        ]
        journal["operation_state"]["op-1"]["resolution"] = (
            "authority_not_applicable"
        )
    payload = json.dumps(
        journal["plan"], ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode() + b"\n"
    plan_sha = hashlib.sha256(payload).hexdigest()
    workflow_id = f"tdw-{plan_sha[:20]}"
    journal["plan_sha256"] = plan_sha
    journal["workflow_id"] = workflow_id
    forged = original.parent / f"{workflow_id}.json"
    forged.write_bytes(
        json.dumps(journal, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    )
    with pytest.raises(workflow.WorkflowError) as caught:
        workflow.status(tmp_path, workflow_id)
    assert caught.value.code == "invalid_journal"


@pytest.mark.parametrize(
    "rollback", ["dispatched_to_pending", "completed_to_pending", "outcome_mismatch"],
)
def test_journal_event_replay_rejects_operation_state_rollback(
    tmp_path: Path, rollback: str,
) -> None:
    body, runtime = _plan(tmp_path)
    prepared = _prepare(tmp_path, body)
    reservation = _materialize(tmp_path, runtime["op-1"])
    resolved, _ = _resolve_all(tmp_path, prepared, {"op-1": reservation})
    if rollback == "dispatched_to_pending":
        current = workflow.apply(
            tmp_path, resolved["workflow_id"], "op-1", resolved["revision"]
        )
    else:
        current, _ = _settle(tmp_path, resolved, reservation, no_effect=True)
    journal_path = tmp_path / current["journal_ref"]
    journal = json.loads(journal_path.read_text(encoding="utf-8"))
    if rollback in {"dispatched_to_pending", "completed_to_pending"}:
        journal["operation_state"]["op-1"].update(
            status="pending", resolution="ready_to_resume", result_evidence=None,
        )
    else:
        event = next(
            item for item in journal["events"]
            if item["event"] == "owner_result_recorded"
        )
        event["outcome"] = "unknown_effect"
    journal_path.write_bytes(
        json.dumps(journal, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    )
    with pytest.raises(workflow.WorkflowError) as caught:
        workflow.status(tmp_path, current["workflow_id"])
    assert caught.value.code == "invalid_journal"


def test_live_authority_overlay_suppresses_reapproval_after_materialization_crash(
    tmp_path: Path,
) -> None:
    body, runtime = _plan(tmp_path, mode="consolidated_review")
    prepared = _prepare(tmp_path, body)
    assert prepared["classification"] == "ready_to_reserve"
    assert prepared["authority_resolution_source"] == "needs_user_approval"
    assert prepared["should_prompt"] is False
    assert "wait" not in prepared
    assert "approval_bundle" not in prepared
    assert [
        item["operation_id"] for item in prepared["authority_bundle"]["items"]
    ] == ["op-1"]
    assert [
        item["operation_id"]
        for item in prepared["live_authority_progress"]["items"]
    ] == ["op-1"]

    reservation = _materialize(tmp_path, runtime["op-1"])
    current = workflow.status(tmp_path, prepared["workflow_id"])
    assert current["classification"] == "ready_to_resume"
    assert current["should_prompt"] is False
    assert "approval_bundle" not in current
    assert [
        item["operation_id"] for item in current["authority_bundle"]["items"]
    ] == ["op-1"]
    advanced, _ = _resolve_all(tmp_path, current, {"op-1": reservation})
    assert advanced["classification"] == "ready_to_resume"
    assert advanced["next_action"] == "dispatch_owner"
    assert advanced["should_prompt"] is False
    assert advanced["approval_interactions"] == {"used": 0, "maximum": 1}
    journal = json.loads(
        (tmp_path / advanced["journal_ref"]).read_text(encoding="utf-8")
    )
    assert journal["operation_state"]["op-1"]["resolution"] == "ready_to_resume"


def _approval_wait_projection(request_sha256: str) -> dict[str, Any]:
    """Return one exact read-only semantic-review wait for overlay tests."""

    return {
        "schema_version": 2,
        "status": "resolved",
        "resolution": "needs_user_approval",
        "should_prompt": True,
        "user_action": "approve",
        "next_action": {"actor": "user", "code": "approve_exact_projection"},
        "workflow_basis": {
            "kind": "approval_wait",
            "request_sha256": request_sha256,
            "reservation": None,
            "reservation_state": None,
            "decision": None,
            "source_approval": None,
            "settlement_receipt": None,
            "blocker_codes": [],
        },
    }


@pytest.mark.parametrize("count", [2, 3])
def test_consolidated_review_inventory_includes_all_dependency_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, count: int,
) -> None:
    body, _runtime = _plan(tmp_path, count=count, mode="consolidated_review")
    from task_doctor_workflow_lib import authority_overlay

    monkeypatch.setattr(
        authority_overlay,
        "resolve_operation",
        lambda _root, request, _context, **_kwargs: _approval_wait_projection(
            object_sha256(request)
        ),
    )
    prepared = _prepare(tmp_path, body)

    assert prepared["classification"] == "needs_user_approval"
    assert prepared["should_prompt"] is True
    assert [
        item["operation_id"] for item in prepared["approval_bundle"]["items"]
    ] == [f"op-{index}" for index in range(1, count + 1)]
    assert not list(
        (tmp_path / ".task/authorization/reservations").glob("*.json")
    )


def test_one_semantic_approval_covers_chain_without_downstream_reprompt_or_reserve(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    body, runtime = _plan(tmp_path, count=3, mode="consolidated_review")
    from task_doctor_workflow_lib import authority_overlay

    public_resolver = authority_overlay.resolve_operation
    monkeypatch.setattr(
        authority_overlay,
        "resolve_operation",
        lambda _root, request, _context, **_kwargs: _approval_wait_projection(
            object_sha256(request)
        ),
    )
    prepared = _prepare(tmp_path, body)
    monkeypatch.setattr(authority_overlay, "resolve_operation", public_resolver)

    source_approved, _ = _resolve_all(
        tmp_path,
        prepared,
        {operation_id: item["source_approval"]
         for operation_id, item in runtime.items()},
        classifications={operation_id: "already_covered" for operation_id in runtime},
    )
    assert source_approved["approval_interactions"] == {"used": 1, "maximum": 1}
    assert source_approved["classification"] == "ready_to_reserve"
    assert source_approved["should_prompt"] is False
    assert source_approved["next_operation"] == "op-1"
    assert [
        item["operation_id"]
        for item in source_approved["authority_bundle"]["items"]
    ] == ["op-1"]
    journal = json.loads(
        (tmp_path / source_approved["journal_ref"]).read_text(encoding="utf-8")
    )
    assert {
        operation_id: state["resolution"]
        for operation_id, state in journal["operation_state"].items()
    } == {"op-1": "already_covered", "op-2": "already_covered",
          "op-3": "already_covered"}
    assert not list(
        (tmp_path / ".task/authorization/reservations").glob("*.json")
    )

    current = source_approved
    for index in range(1, 3):
        operation_id = f"op-{index}"
        reservation = _materialize(tmp_path, runtime[operation_id])
        current, _ = _resolve_all(
            tmp_path, current, {operation_id: reservation}
        )
        current, _ = _settle(tmp_path, current, reservation, no_effect=True)
        assert current["approval_interactions"] == {"used": 1, "maximum": 1}
        assert current["should_prompt"] is False
        assert current["next_operation"] == f"op-{index + 1}"
        assert current["classification"] == "ready_to_reserve"
        reservation_files = list(
            (tmp_path / ".task/authorization/reservations").glob("*.json")
        )
        assert len(reservation_files) == index


def test_live_covered_plan_does_not_open_new_prompt_after_source_loss(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    body, _runtime = _plan(tmp_path, mode="consolidated_review")
    prepared = _prepare(tmp_path, body)
    journal_path = tmp_path / prepared["journal_ref"]
    before = journal_path.read_bytes()
    journal = json.loads(before)
    assert all(
        item["event"] != "semantic_approval_scope_bound"
        for item in journal["events"]
    )

    from task_doctor_workflow_lib import authority_overlay

    monkeypatch.setattr(
        authority_overlay,
        "resolve_operation",
        lambda _root, request, _context, **_kwargs: _approval_wait_projection(
            object_sha256(request)
        ),
    )
    current = workflow.status(tmp_path, prepared["workflow_id"])

    assert current["classification"] == "plan_changed"
    assert current["workflow_state"] == "replanning_required"
    assert current["next_action"] == "prepare_new_plan"
    assert current["should_prompt"] is False
    assert current["user_action"] == "none"
    assert current["approval_interactions"] == {"used": 0, "maximum": 1}
    assert "approval_bundle" not in current
    assert journal_path.read_bytes() == before


def test_scope_excluded_row_source_loss_replans_without_second_prompt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    body, runtime = _plan(tmp_path, count=2, mode="consolidated_review")
    from task_doctor_workflow_lib import authority_overlay

    public_resolver = authority_overlay.resolve_operation

    def mixed(
        root: Path, request: dict[str, Any], context: dict[str, Any], **kwargs: Any,
    ) -> dict[str, Any]:
        if request["request_id"] == "request-op-2":
            return _approval_wait_projection(object_sha256(request))
        return public_resolver(root, request, context, **kwargs)

    monkeypatch.setattr(authority_overlay, "resolve_operation", mixed)
    prepared = _prepare(tmp_path, body)
    resolved, _ = _resolve_all(
        tmp_path,
        prepared,
        {"op-2": runtime["op-2"]["source_approval"]},
        classifications={"op-2": "already_covered"},
    )
    assert resolved["approval_interactions"] == {"used": 1, "maximum": 1}

    monkeypatch.setattr(
        authority_overlay,
        "resolve_operation",
        lambda _root, request, _context, **_kwargs: _approval_wait_projection(
            object_sha256(request)
        ),
    )
    journal_path = tmp_path / resolved["journal_ref"]
    before = journal_path.read_bytes()
    current = workflow.status(tmp_path, resolved["workflow_id"])

    assert current["classification"] == "plan_changed"
    assert current["workflow_state"] == "replanning_required"
    assert current["next_operation"] == "op-1"
    assert current["next_action"] == "prepare_new_plan"
    assert current["should_prompt"] is False
    assert current["user_action"] == "none"
    assert current["approval_interactions"] == {"used": 1, "maximum": 1}
    assert "approval_bundle" not in current
    assert journal_path.read_bytes() == before


def test_mixed_covered_and_uncovered_rows_accept_displayed_bundle_without_widening(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    body, runtime = _plan(tmp_path, count=2, mode="consolidated_review")
    from task_doctor_workflow_lib import authority_overlay

    public_resolver = authority_overlay.resolve_operation

    def mixed(
        root: Path, request: dict[str, Any], context: dict[str, Any], **kwargs: Any,
    ) -> dict[str, Any]:
        if request["request_id"] == "request-op-2":
            return _approval_wait_projection(object_sha256(request))
        return public_resolver(root, request, context, **kwargs)

    monkeypatch.setattr(authority_overlay, "resolve_operation", mixed)
    prepared = _prepare(tmp_path, body)

    assert prepared["classification"] == "needs_user_approval"
    assert prepared["should_prompt"] is True
    assert [
        item["operation_id"] for item in prepared["approval_bundle"]["items"]
    ] == ["op-2"]
    assert [
        item["operation_id"]
        for item in prepared["live_authority_progress"]["items"]
    ] == ["op-1"]

    journal_path = tmp_path / prepared["journal_ref"]
    before = journal_path.read_bytes()
    widened = _write_json(
        tmp_path,
        "widened-resolution-bundle.json",
        {
            "kind": "task_doctor_authority_resolution_bundle",
            "schema_version": 1,
            "workflow_id": prepared["workflow_id"],
            "plan_sha256": prepared["plan_sha256"],
            "from_classification": "needs_user_approval",
            "user_interaction": True,
            "resolutions": [{
                "operation_id": "op-1",
                "classification": "already_covered",
                "evidence_ref": runtime["op-1"]["source_approval"]["ref"],
                "evidence_sha256": runtime["op-1"]["source_approval"]["sha256"],
            }],
        },
    )
    with pytest.raises(workflow.WorkflowError) as caught:
        workflow.resolve_all(
            tmp_path, prepared["workflow_id"], widened["ref"], widened["sha256"],
            prepared["revision"],
        )
    assert caught.value.code == "incomplete_resolution_bundle"
    assert journal_path.read_bytes() == before

    resolved, bundle = _resolve_all(
        tmp_path,
        prepared,
        {"op-2": runtime["op-2"]["source_approval"]},
        classifications={"op-2": "already_covered"},
    )
    submitted = json.loads((tmp_path / bundle["ref"]).read_text(encoding="utf-8"))
    assert [item["operation_id"] for item in submitted["resolutions"]] == ["op-2"]
    assert resolved["approval_interactions"] == {"used": 1, "maximum": 1}
    assert resolved["should_prompt"] is False
    assert "approval_bundle" not in resolved
    assert "wait" not in resolved
    assert [
        item["operation_id"] for item in resolved["authority_bundle"]["items"]
    ] == ["op-1"]

    journal = json.loads(journal_path.read_text(encoding="utf-8"))
    assert journal["operation_state"]["op-1"]["resolution"] == "needs_user_approval"
    assert journal["operation_state"]["op-1"]["resolution_evidence"] is None
    assert journal["operation_state"]["op-2"]["resolution"] == "already_covered"
    assert journal["operation_state"]["op-2"]["resolution_evidence"] == (
        runtime["op-2"]["source_approval"]
    )
    event = journal["events"][-1]
    assert event["event"] == "authority_bundle_resolved"
    assert event["operations"] == ["op-2"]

    monkeypatch.setattr(authority_overlay, "resolve_operation", public_resolver)
    current = workflow.status(tmp_path, resolved["workflow_id"])
    assert current["should_prompt"] is False
    assert current["approval_interactions"] == {"used": 1, "maximum": 1}
    replay = workflow.resolve_all(
        tmp_path, current["workflow_id"], bundle["ref"], bundle["sha256"],
        current["revision"],
    )
    assert replay["replayed"] is True
    assert replay["revision"] == current["revision"]
    assert replay["should_prompt"] is False
    assert replay["approval_interactions"] == {"used": 1, "maximum": 1}

    reservation = _materialize(tmp_path, runtime["op-1"])
    reservable = workflow.status(tmp_path, resolved["workflow_id"])
    assert reservable["classification"] == "ready_to_resume"
    assert reservable["should_prompt"] is False
    assert "approval_bundle" not in reservable
    assert [
        item["operation_id"] for item in reservable["authority_bundle"]["items"]
    ] == ["op-1"]
    advanced, _ = _resolve_all(tmp_path, reservable, {"op-1": reservation})
    assert advanced["classification"] == "ready_to_resume"
    assert advanced["next_action"] == "dispatch_owner"
    assert advanced["approval_interactions"] == {"used": 1, "maximum": 1}
    advanced_journal = json.loads(journal_path.read_text(encoding="utf-8"))
    assert advanced_journal["operation_state"]["op-1"]["resolution"] == (
        "ready_to_resume"
    )


def test_expired_reserved_authority_routes_system_recovery_without_prompt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    body, runtime = _plan(tmp_path)
    prepared = _prepare(tmp_path, body)
    reservation = _materialize(tmp_path, runtime["op-1"])
    resolved, _ = _resolve_all(tmp_path, prepared, {"op-1": reservation})
    from task_doctor_workflow_lib import authority_overlay

    monkeypatch.setattr(
        authority_overlay, "now", lambda: "2031-07-18T10:00:00+09:00"
    )
    status = workflow.status(tmp_path, resolved["workflow_id"])
    assert status["classification"] == "reserved_authority_recovery"
    assert status["should_prompt"] is False
    assert status["user_action"] == "none"
    journal = tmp_path / status["journal_ref"]
    before = journal.read_bytes()
    with pytest.raises(workflow.WorkflowError):
        workflow.apply(
            tmp_path, resolved["workflow_id"], "op-1", resolved["revision"]
        )
    assert journal.read_bytes() == before


def _direct_task_transition(
    root: Path, transition_id: str, *, predecessor: bytes | None = None,
) -> tuple[dict[str, Any], dict[str, str], bytes]:
    if predecessor is not None:
        (root / "task.md").write_bytes(predecessor)
    prospective_ref = f".task/task_doctor/prospective/{transition_id}.md"
    prospective = root / prospective_ref
    prospective.parent.mkdir(parents=True, exist_ok=True)
    payload = f"# Task\n\n## Objective\n\nTransition {transition_id}.\n".encode()
    prospective.write_bytes(payload)
    plan = build_task_transition_plan(
        root,
        transition_id,
        "replace_task" if predecessor is not None else "initial_task",
        prospective_ref,
    )
    published = publish_task_transition_plan(root, plan)
    binding = {
        "ref": published["plan_ref"],
        "sha256": published["plan_file_sha256"],
    }
    return plan, binding, payload


def test_task_transition_public_apply_archives_and_replays_exact_bytes(
    tmp_path: Path,
) -> None:
    predecessor = b"# Prior Task\n\nPreserve these exact bytes.\n"
    plan, binding, payload = _direct_task_transition(
        tmp_path, "direct-replace", predecessor=predecessor
    )
    planning = verify_task_transition_execution(
        tmp_path, binding["ref"], phase="planning"
    )
    assert planning["status"] == "ready"
    applied = apply_task_transition_plan(tmp_path, binding["ref"])
    assert applied["status"] == "already_applied"
    assert applied["apply_status"] == "applied"
    assert applied["mutation_performed"] is True
    assert (tmp_path / "task.md").read_bytes() == payload
    assert (tmp_path / plan["archive_task"]["ref"]).read_bytes() == predecessor

    (tmp_path / plan["prospective_task"]["ref"]).unlink()
    verified = verify_task_transition_execution(
        tmp_path, binding["ref"], phase="apply"
    )
    assert verified["status"] == "already_applied"
    replay = apply_task_transition_plan(tmp_path, binding["ref"])
    assert replay["apply_status"] == "already_applied"
    assert replay["idempotent_replay"] is True
    assert replay["mutation_performed"] is False


def test_task_transition_plan_publisher_replays_and_rejects_id_collision(
    tmp_path: Path,
) -> None:
    prospective_ref = ".task/task_doctor/prospective/publish-contract.md"
    prospective = tmp_path / prospective_ref
    prospective.parent.mkdir(parents=True)
    prospective.write_text("# First publication\n", encoding="utf-8")
    first = build_task_transition_plan(
        tmp_path, "publish-contract", "initial_task", prospective_ref
    )
    published = publish_task_transition_plan(tmp_path, first)
    replayed = publish_task_transition_plan(tmp_path, first)
    assert published["created"] is True
    assert replayed == {**published, "created": False, "replayed": True}

    prospective.write_text("# Conflicting publication\n", encoding="utf-8")
    conflicting = build_task_transition_plan(
        tmp_path, "publish-contract", "initial_task", prospective_ref
    )
    with pytest.raises(workflow.WorkflowError) as caught:
        publish_task_transition_plan(tmp_path, conflicting)
    assert caught.value.code == "owner_artifact_conflict"


def test_task_transition_loader_rejects_noncanonical_json_bytes(
    tmp_path: Path,
) -> None:
    prospective_ref = ".task/task_doctor/prospective/noncanonical-plan.md"
    prospective = tmp_path / prospective_ref
    prospective.parent.mkdir(parents=True)
    prospective.write_text("# Canonical content\n", encoding="utf-8")
    plan = build_task_transition_plan(
        tmp_path, "noncanonical-plan", "initial_task", prospective_ref
    )
    target = (
        tmp_path
        / ".task/task_doctor/transition-plans/noncanonical-plan.json"
    )
    target.parent.mkdir(parents=True)
    target.write_text(json.dumps(plan, indent=2), encoding="utf-8")

    with pytest.raises(workflow.WorkflowError) as caught:
        verify_task_transition_execution(
            tmp_path, str(target.relative_to(tmp_path)), phase="planning"
        )
    assert caught.value.code == "invalid_owner_plan"


def test_plan_publication_fails_if_ancestor_identity_changes_mid_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    prospective_ref = ".task/task_doctor/prospective/ancestor-swap.md"
    prospective = tmp_path / prospective_ref
    prospective.parent.mkdir(parents=True)
    prospective.write_text("# Stable prospective\n", encoding="utf-8")
    plan = build_task_transition_plan(
        tmp_path, "ancestor-swap", "initial_task", prospective_ref
    )
    original_verify = task_transition_store._verify_directory_identity
    calls = 0

    def swap_then_verify(
        root_path: Path, relative_parent: Any, expected: Any,
    ) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            canonical = root_path / relative_parent
            detached = canonical.parent / "transition-plans-detached"
            canonical.rename(detached)
            canonical.mkdir()
        original_verify(root_path, relative_parent, expected)

    monkeypatch.setattr(
        task_transition_store, "_verify_directory_identity", swap_then_verify
    )
    with pytest.raises(workflow.WorkflowError) as caught:
        publish_task_transition_plan(tmp_path, plan)
    assert caught.value.code == "invalid_owner_path"
    assert not (
        tmp_path / ".task/task_doctor/transition-plans/ancestor-swap.json"
    ).exists()


def test_task_apply_fails_before_canonical_mutation_on_mid_intent_ancestor_swap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    predecessor = b"# Predecessor remains canonical\n"
    _plan_value, binding, _payload = _direct_task_transition(
        tmp_path, "intent-ancestor-swap", predecessor=predecessor
    )
    original_verify = task_transition_store._verify_directory_identity
    intent_checks = 0

    def swap_intent_ancestor(
        root_path: Path, relative_parent: Any, expected: Any,
    ) -> None:
        nonlocal intent_checks
        if str(relative_parent).endswith("transitions/intents"):
            intent_checks += 1
            if intent_checks == 2:
                transitions = root_path / ".task/task_doctor/transitions"
                transitions.rename(
                    root_path / ".task/task_doctor/transitions-detached"
                )
                transitions.mkdir()
        original_verify(root_path, relative_parent, expected)

    monkeypatch.setattr(
        task_transition_store, "_verify_directory_identity",
        swap_intent_ancestor,
    )
    with pytest.raises(workflow.WorkflowError) as caught:
        apply_task_transition_plan(tmp_path, binding["ref"])
    assert caught.value.code == "invalid_owner_path"
    assert (tmp_path / "task.md").read_bytes() == predecessor
    assert not (
        tmp_path
        / ".task/task_doctor/transitions/intents/intent-ancestor-swap.json"
    ).exists()


def test_task_transition_initial_apply_has_no_predecessor_archive(
    tmp_path: Path,
) -> None:
    plan, binding, payload = _direct_task_transition(tmp_path, "direct-initial")
    applied = apply_task_transition_plan(tmp_path, binding["ref"])
    assert applied["effect_status"] == "confirmed_effect"
    assert (tmp_path / "task.md").read_bytes() == payload
    archive = tmp_path / ".task/task_doctor/transitions/archives/direct-initial.md"
    assert plan["archive_task"]["required"] is False
    assert not archive.exists()


def test_task_transition_pre_intent_staleness_has_durable_no_effect_receipt(
    tmp_path: Path,
) -> None:
    predecessor = b"# Stable predecessor\n"
    plan, binding, _payload = _direct_task_transition(
        tmp_path, "direct-no-effect", predecessor=predecessor
    )
    (tmp_path / plan["prospective_task"]["ref"]).unlink()
    settled = apply_task_transition_plan(tmp_path, binding["ref"])
    assert settled["status"] == "settled_no_effect"
    assert settled["effect_status"] == "confirmed_no_effect"
    assert (tmp_path / "task.md").read_bytes() == predecessor
    assert not (tmp_path / ".task/task_doctor/transitions/intents/direct-no-effect.json").exists()
    assert not (tmp_path / plan["archive_task"]["ref"]).exists()
    verified = verify_task_transition_execution(
        tmp_path, binding["ref"], phase="apply"
    )
    assert verified["no_effect_verified"] is True
    assert apply_task_transition_plan(tmp_path, binding["ref"])[
        "mutation_performed"
    ] is False


def test_task_transition_recovers_crash_after_intent_and_archive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    predecessor = b"# Crash-safe predecessor\n"
    plan, binding, payload = _direct_task_transition(
        tmp_path, "direct-intent-crash", predecessor=predecessor
    )
    original = task_transition_transaction.replace_canonical_task

    def interrupted(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("simulated interruption before canonical replace")

    monkeypatch.setattr(
        task_transition_transaction, "replace_canonical_task", interrupted
    )
    with pytest.raises(RuntimeError, match="simulated interruption"):
        apply_task_transition_plan(tmp_path, binding["ref"])
    observed = verify_task_transition_execution(
        tmp_path, binding["ref"], phase="apply"
    )
    assert observed["status"] == "recovery_required"
    assert observed["intent_observed"] is True
    assert observed["no_effect_verified"] is False
    assert (tmp_path / plan["archive_task"]["ref"]).read_bytes() == predecessor

    monkeypatch.setattr(
        task_transition_transaction, "replace_canonical_task", original
    )
    recovered = apply_task_transition_plan(tmp_path, binding["ref"])
    assert recovered["status"] == "already_applied"
    assert (tmp_path / "task.md").read_bytes() == payload


def test_task_transition_recovers_crash_after_effect_before_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan, binding, payload = _direct_task_transition(
        tmp_path, "direct-receipt-crash", predecessor=b"# Before receipt crash\n"
    )
    original = task_transition_transaction._publish_effect_receipt

    def interrupted(*_args: Any, **_kwargs: Any) -> tuple[bool, str]:
        raise RuntimeError("simulated interruption before receipt")

    monkeypatch.setattr(
        task_transition_transaction, "_publish_effect_receipt", interrupted
    )
    with pytest.raises(RuntimeError, match="simulated interruption"):
        apply_task_transition_plan(tmp_path, binding["ref"])
    assert (tmp_path / "task.md").read_bytes() == payload
    observed = verify_task_transition_execution(
        tmp_path, binding["ref"], phase="apply"
    )
    assert observed["status"] == "recovery_required"
    assert observed["effect_observed"] is True
    assert observed["no_effect_verified"] is False

    monkeypatch.setattr(
        task_transition_transaction, "_publish_effect_receipt", original
    )
    recovered = apply_task_transition_plan(tmp_path, binding["ref"])
    assert recovered["publication_recovered"] is True
    assert recovered["status"] == "already_applied"
    assert (tmp_path / plan["archive_task"]["ref"]).is_file()


def test_task_transition_rejects_effect_without_intent_as_ambiguous(
    tmp_path: Path,
) -> None:
    plan, binding, payload = _direct_task_transition(
        tmp_path, "direct-ambiguous", predecessor=b"# Before ambiguous\n"
    )
    (tmp_path / "task.md").write_bytes(payload)
    observed = verify_task_transition_execution(
        tmp_path, binding["ref"], phase="apply"
    )
    assert observed["status"] == "conflict"
    assert observed["no_effect_verified"] is False
    with pytest.raises(workflow.WorkflowError) as caught:
        apply_task_transition_plan(tmp_path, binding["ref"])
    assert caught.value.code == "task_transition_conflict"
    assert not (tmp_path / ".task/task_doctor/transitions/receipts/direct-ambiguous.json").exists()
    assert not (tmp_path / plan["archive_task"]["ref"]).exists()


def test_task_transition_owned_symlink_ancestor_fails_before_effect(
    tmp_path: Path,
) -> None:
    _plan_body, binding, _payload = _direct_task_transition(
        tmp_path, "direct-symlink", predecessor=b"# Before symlink\n"
    )
    owned = tmp_path / ".task/task_doctor/transitions"
    outside = tmp_path / ".task/task_doctor/transitions-real"
    outside.mkdir(parents=True)
    owned.symlink_to("transitions-real", target_is_directory=True)
    before = (tmp_path / "task.md").read_bytes()
    with pytest.raises(workflow.WorkflowError) as caught:
        apply_task_transition_plan(tmp_path, binding["ref"])
    assert caught.value.code == "invalid_owner_path"
    assert (tmp_path / "task.md").read_bytes() == before


def test_prior_effect_receipt_survives_later_canonical_task_transition(
    tmp_path: Path,
) -> None:
    body, runtime = _task_scope_workflow(tmp_path)
    prepared = _prepare(tmp_path, body)
    reservations = {
        key: _materialize(tmp_path, value) for key, value in runtime.items()
    }
    resolved, _bundle = _resolve_all(tmp_path, prepared, reservations)
    scope_done, _scope_completion = _settle(
        tmp_path, resolved, reservations["scope"]
    )
    journal = json.loads(
        (tmp_path / scope_done["journal_ref"]).read_text(encoding="utf-8")
    )
    index_item = next(
        item for item in journal["plan"]["operations"]
        if item["operation_id"] == "index"
    )
    index_dispatch = {"operation_id": "index", "owner_dispatch": index_item}
    index_owner = _owner_effect(
        tmp_path, scope_done["workflow_id"], index_dispatch,
        "confirmed_no_effect",
    )
    released = release(
        tmp_path, reservations["index"]["ref"], reservations["index"]["sha256"],
        index_owner, released_at=SETTLED_AT, expected_version=0,
        idempotency_key="release-index-after-scope-no-effect",
        effect_status="verified_no_effect",
    )
    index_completion = _completion(
        tmp_path, scope_done["workflow_id"], index_dispatch, index_owner,
        {"ref": released["ref"], "sha256": released["sha256"]},
        "confirmed_no_effect",
    )
    complete = workflow.resolve(
        tmp_path, scope_done["workflow_id"], "index", "already_settled",
        index_completion["ref"], index_completion["sha256"],
        scope_done["revision"],
    )
    first_plan = body["operations"][0]
    first = verify_task_transition_execution(
        tmp_path, first_plan["plan_binding"]["ref"], phase="apply"
    )
    assert first["status"] == "already_applied"
    assert first["current_projection_healthy"] is True

    prior_bytes = (tmp_path / "task.md").read_bytes()
    _second_plan, second_binding, _payload = _direct_task_transition(
        tmp_path, "direct-successor", predecessor=prior_bytes
    )
    apply_task_transition_plan(tmp_path, second_binding["ref"])
    historical = verify_task_transition_execution(
        tmp_path, first_plan["plan_binding"]["ref"], phase="apply"
    )
    assert historical["status"] == "already_applied"
    assert historical["historical_transaction_complete"] is True
    assert historical["current_projection_healthy"] is False
    assert workflow.status(tmp_path, complete["workflow_id"])[
        "classification"
    ] == "complete"


def test_prior_no_effect_receipt_survives_later_unrelated_task_publication(
    tmp_path: Path,
) -> None:
    body, runtime = _task_scope_workflow(tmp_path)
    prepared = _prepare(tmp_path, body)
    reservations = {
        key: _materialize(tmp_path, value) for key, value in runtime.items()
    }
    resolved, _bundle = _resolve_all(tmp_path, prepared, reservations)
    scope_done, _scope_completion = _settle(
        tmp_path, resolved, reservations["scope"], no_effect=True
    )
    assert scope_done["classification"] == "plan_changed"
    first_plan = body["operations"][0]
    settled = verify_task_transition_execution(
        tmp_path, first_plan["plan_binding"]["ref"], phase="apply"
    )
    assert settled["status"] == "settled_no_effect"

    _later_plan, later_binding, _payload = _direct_task_transition(
        tmp_path, "later-unrelated"
    )
    apply_task_transition_plan(tmp_path, later_binding["ref"])
    historical = verify_task_transition_execution(
        tmp_path, first_plan["plan_binding"]["ref"], phase="apply"
    )
    assert historical["status"] == "settled_no_effect"
    assert historical["no_effect_verified"] is True
    assert historical["current_projection_healthy"] is False
    assert workflow.status(tmp_path, scope_done["workflow_id"])[
        "classification"
    ] == "plan_changed"


def test_helper_modules_and_definitions_have_hard_size_budgets() -> None:
    paths = [SCRIPT, *sorted(LIB.glob("*.py"))]
    for path in paths:
        source = path.read_text(encoding="utf-8")
        assert len(source.splitlines()) < 500, path
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                assert node.end_lineno is not None
                assert node.end_lineno - node.lineno + 1 < 140, (path, node.name)
