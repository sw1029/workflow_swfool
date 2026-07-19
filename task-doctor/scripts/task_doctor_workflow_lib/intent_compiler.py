"""Compile compact task-doctor intent and enforce a pre-journal review gate."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from manage_agent_authority.canonical import object_sha256, parse_time
from manage_agent_authority.operation_compiler import validate_compilation
from manage_agent_authority.source_approval import load_source_approval

from .authority_basis import verify_operation_source_approval
from .authority_snapshots import verify_policy_snapshot
from .common import (
    FORBIDDEN_EFFECTS,
    SAFE_ID,
    WorkflowError,
    expect_keys,
    read_json,
    require,
    sha256_json,
    workspace_file,
)
from .compilation_loader import load_compilation
from .plan import ROLE_BY_OPERATION, normalize_plan, validate_normalized_plan
from .task_transition_store import publish_immutable


INTENT_KEYS = {
    "schema_version", "intent_kind", "policy_snapshot", "expires_at",
    "git_finalization", "operations", "reporting",
}
OPERATION_KEYS = {
    "operation_id", "compiled_operation", "effect_summary", "required",
}
REVIEW_KEYS = {
    "schema_version", "artifact_kind", "review_id", "prepared_at",
    "intent_fingerprint", "review_fingerprint", "policy_snapshot",
    "expires_at", "git_finalization", "reporting", "operations",
    "approval_scope",
}
DECISION_KEYS = {
    "schema_version", "decision_kind", "review_id", "decided_at",
    "review_fingerprint", "evidence_id", "source_approvals",
}
SKILLS_ROOT = Path(__file__).resolve().parents[3]


def _binding(value: Any, label: str) -> dict[str, str]:
    require(isinstance(value, dict), "invalid_intent", f"{label} must be an object")
    expect_keys(value, {"ref", "sha256"}, set(), label, "invalid_intent")
    ref = value["ref"]
    digest = value["sha256"]
    require(isinstance(ref, str) and ref, "invalid_intent", f"{label}.ref is required")
    require(isinstance(digest, str) and len(digest) == 64,
            "invalid_intent", f"{label}.sha256 must be SHA-256")
    return {"ref": ref, "sha256": digest}


def _time(value: Any, label: str):
    try:
        return parse_time(value, label)
    except SystemExit as error:
        raise WorkflowError("invalid_intent", str(error)) from error


def _identity(request_sha256: str, operation_id: str) -> dict[str, str]:
    fingerprint = object_sha256({
        "request_sha256": request_sha256, "operation_id": operation_id,
    })
    return {
        "grant_id": f"tdg-{fingerprint[:24]}",
        "lineage_id": f"tdl-{fingerprint[8:32]}",
        "grant_idempotency_key": f"tdg-key-{fingerprint[:20]}",
        "reservation_idempotency_key": f"tdr-key-{fingerprint[:20]}",
    }


def _source_body(root: Path, binding: dict[str, str]) -> dict[str, Any]:
    path = workspace_file(root, binding["ref"], binding["sha256"], "source_approval")
    try:
        return load_source_approval(path)
    except (SystemExit, KeyError, TypeError, ValueError) as error:
        raise WorkflowError(
            "invalid_authorization_basis", f"source approval is invalid: {error}"
        ) from error


def _plan_item(
    row: dict[str, Any], source: dict[str, str], at: str,
    expires_at: str, policy: dict[str, str],
) -> dict[str, Any]:
    compilation = row["compiled_operation"]
    request = compilation["request"]
    identity = row["materialization_identity"]
    return {
        "operation_id": row["operation_id"],
        "workflow_role": row["workflow_role"],
        "owner_skill": row["owner_skill"],
        "effect_class": request["effect_class"],
        "effect_summary": row["effect_summary"],
        "required": row["required"],
        "dependencies": copy.deepcopy(row["dependencies"]),
        "plan": copy.deepcopy(row["plan"]),
        "plan_binding": copy.deepcopy(row["plan_binding"]),
        "authority": {
            "applicability": "required",
            "request": copy.deepcopy(request),
            "materialization": {
                "evaluation_context": copy.deepcopy(
                    compilation["evaluation_context"]
                ),
                "evaluated_at": at,
                "policy_snapshot": copy.deepcopy(policy),
                "grant_spec": {
                    "grant_id": identity["grant_id"],
                    "lineage_id": identity["lineage_id"],
                    "holder_rank": request["actor_rank"],
                    "cardinality": "single_use",
                    "max_uses": 1,
                    "not_before": at,
                    "expires_at": expires_at,
                    "idempotency_key": identity["grant_idempotency_key"],
                },
                "reservation": {
                    "not_before": at,
                    "expires_at": expires_at,
                    "idempotency_key": identity["reservation_idempotency_key"],
                },
            },
        },
        "initial_resolution": "already_covered",
        "source_approval": copy.deepcopy(source),
    }


def _verify_existing_source(
    root: Path, row: dict[str, Any], binding: dict[str, str], at: str,
    expires_at: str, policy: dict[str, str],
) -> None:
    item = _plan_item(row, binding, at, expires_at, policy)
    item["authority"]["request_sha256"] = row["compiled_operation"][
        "request_sha256"
    ]
    item["authority"]["source_approval"] = binding
    verify_operation_source_approval(root, item, binding)


def _normalize_rows(root: Path, raw: list[Any]) -> list[dict[str, Any]]:
    require(isinstance(raw, list) and raw, "invalid_intent",
            "intent operations must be non-empty")
    rows = []
    for index, value in enumerate(raw):
        require(isinstance(value, dict), "invalid_intent",
                f"operations[{index}] must be an object")
        expect_keys(value, OPERATION_KEYS, {"source_approval"},
                    f"operations[{index}]", "invalid_intent")
        operation_id = value["operation_id"]
        require(isinstance(operation_id, str) and SAFE_ID.fullmatch(operation_id),
                "invalid_intent", f"operations[{index}].operation_id is invalid")
        effect_summary = value["effect_summary"]
        require(isinstance(effect_summary, str) and bool(effect_summary.strip()),
                "invalid_intent",
                f"operations[{index}].effect_summary must be non-empty")
        require(isinstance(value["required"], bool), "invalid_intent",
                f"operations[{index}].required must be boolean")
        compilation = load_compilation(
            root, value["compiled_operation"], skills_root=SKILLS_ROOT
        )
        request = compilation["request"]
        identity = (request["skill_id"], request["operation_id"])
        role = ROLE_BY_OPERATION.get(identity)
        require(role is not None, "invalid_intent",
                f"operation {identity} has no task-doctor adapter")
        requirements = compilation["source_and_grant_requirements"]
        require(requirements["authorization_mechanism"] == "grant",
                "invalid_intent", "compact intent only accepts grant-governed effects")
        binding = {
            "ref": request["subject"]["ref"],
            "sha256": request["subject"]["digest"],
        }
        path = workspace_file(root, binding["ref"], binding["sha256"],
                              f"{operation_id}.plan_binding")
        plan = read_json(path, "invalid_intent")
        source = value.get("source_approval")
        rows.append({
            "operation_id": operation_id,
            "workflow_role": role,
            "owner_skill": request["skill_id"],
            "effect_summary": effect_summary.strip(),
            "required": value["required"],
            "plan": plan,
            "plan_binding": binding,
            "compiled_operation": compilation,
            "materialization_identity": _identity(
                compilation["request_sha256"], operation_id
            ),
            "existing_source_approval": (
                None if source is None else _binding(source, "source_approval")
            ),
        })
    identifiers = [row["operation_id"] for row in rows]
    require(len(identifiers) == len(set(identifiers)), "invalid_intent",
            "operation IDs must be unique")
    return _ordered(rows)


def _ordered(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    advice = [row for row in rows if row["workflow_role"] == "external_advice_intake"]
    scope = [row for row in rows if row["workflow_role"] == "task_scope_transition"]
    index = [row for row in rows if row["workflow_role"] == "task_index_transition"]
    require(len(scope) <= 1 and len(index) <= 1, "invalid_intent",
            "compact intent permits at most one task scope and one final index effect")
    require(not scope or len(index) == 1, "invalid_intent",
            "task scope changes require one final task-index effect")
    require(len(advice) + len(scope) + len(index) == len(rows), "invalid_intent",
            "compact intent contains an unsupported workflow role")
    ordered = [*advice, *scope, *index]
    prior_advice = [row["operation_id"] for row in advice]
    for row in advice:
        row["dependencies"] = []
    if scope:
        scope[0]["dependencies"] = prior_advice
    if index:
        index[0]["dependencies"] = [
            row["operation_id"] for row in ordered if row is not index[0]
        ]
    return ordered


def compile_intent(
    root: Path, intent: Any, *, prepared_at: str,
) -> dict[str, Any]:
    require(isinstance(intent, dict), "invalid_intent", "intent must be an object")
    expect_keys(intent, INTENT_KEYS, set(), "intent", "invalid_intent")
    require(intent["schema_version"] == 1
            and intent["intent_kind"] == "task_doctor_compact_intent",
            "invalid_intent", "unsupported compact intent contract")
    at = _time(prepared_at, "prepared_at").isoformat()
    expires_at = _time(intent["expires_at"], "expires_at")
    require(_time(at, "prepared_at") < expires_at, "invalid_intent",
            "intent expiry must follow preparation")
    policy = _binding(intent["policy_snapshot"], "policy_snapshot")
    verify_policy_snapshot(root, policy)
    git_finalization = intent["git_finalization"]
    require(isinstance(git_finalization, str), "invalid_intent",
            "git_finalization must be deferred or not_applicable")
    require(git_finalization in {"deferred", "not_applicable"},
            "invalid_intent", "compact task-doctor intent cannot request Git")
    reporting = intent["reporting"]
    require(isinstance(reporting, dict), "invalid_intent", "reporting must be an object")
    rows = _normalize_rows(root, intent["operations"])
    uncovered = []
    for row in rows:
        source = row["existing_source_approval"]
        if source is None:
            uncovered.append(row["operation_id"])
        else:
            _verify_existing_source(
                root, row, source, at, expires_at.isoformat(), policy
            )
    intent_core = {
        "prepared_at": at,
        "policy_snapshot": policy,
        "expires_at": expires_at.isoformat(),
        "git_finalization": git_finalization,
        "reporting": copy.deepcopy(reporting),
        "operations": rows,
    }
    intent_fingerprint = sha256_json(intent_core)
    scope_core = {
        "intent_fingerprint": intent_fingerprint,
        "operations": [
            {
                "operation_id": row["operation_id"],
                "owner_skill": row["owner_skill"],
                "effect_class": row["compiled_operation"]["request"]["effect_class"],
                "plan_binding": row["plan_binding"],
                "request_sha256": row["compiled_operation"]["request_sha256"],
                **row["materialization_identity"],
            }
            for row in rows if row["operation_id"] in uncovered
        ],
    }
    scope_fingerprint = sha256_json(scope_core)
    core = {
        "schema_version": 1,
        "artifact_kind": "task_doctor_review_intent",
        "prepared_at": at,
        "intent_fingerprint": intent_fingerprint,
        "policy_snapshot": policy,
        "expires_at": expires_at.isoformat(),
        "git_finalization": git_finalization,
        "reporting": copy.deepcopy(reporting),
        "operations": rows,
        "approval_scope": {
            **scope_core,
            "scope_fingerprint": scope_fingerprint,
        },
    }
    review_fingerprint = sha256_json(core)
    review = {
        **core,
        "review_id": f"tdr-{review_fingerprint[:20]}",
        "review_fingerprint": review_fingerprint,
    }
    if uncovered:
        return {
            "ok": True,
            "status": "awaiting_exact_approval",
            "review": review,
            "uncovered_operations": uncovered,
        }
    sources = {
        row["operation_id"]: row["existing_source_approval"] for row in rows
    }
    return {
        "ok": True,
        "status": "ready",
        "review": review,
        "plan": _build_plan(root, review, sources, at, evidence_id=None),
        "uncovered_operations": [],
    }


def validate_review(review: Any) -> dict[str, Any]:
    require(isinstance(review, dict), "invalid_review", "review must be an object")
    expect_keys(review, REVIEW_KEYS, set(), "review", "invalid_review")
    core = {key: copy.deepcopy(review[key]) for key in REVIEW_KEYS
            if key not in {"review_id", "review_fingerprint"}}
    fingerprint = sha256_json(core)
    require(review["review_fingerprint"] == fingerprint
            and review["review_id"] == f"tdr-{fingerprint[:20]}",
            "invalid_review", "review identity or fingerprint mismatch")
    for row in review["operations"]:
        validate_compilation(row["compiled_operation"])
    return review


def _build_plan(
    root: Path, review: dict[str, Any],
    sources: dict[str, dict[str, str] | None],
    decided_at: str, *, evidence_id: str | None,
) -> dict[str, Any]:
    approvals = []
    operations = []
    for row in review["operations"]:
        source = sources.get(row["operation_id"])
        require(source is not None, "awaiting_exact_approval",
                f"source approval is missing for {row['operation_id']}",
                user_action_required=True, next_action="supply_exact_source_snapshot")
        assert source is not None
        _verify_existing_source(
            root, row, source, decided_at, review["expires_at"],
            review["policy_snapshot"],
        )
        if evidence_id is not None and row["operation_id"] in {
            item["operation_id"] for item in review["approval_scope"]["operations"]
        }:
            approval = _source_body(root, source)
            require(approval["evidence_id"] == evidence_id,
                    "invalid_authorization_basis",
                    "new source approval evidence does not bind the accepted review")
            require(_time(approval["not_before"], "source not_before")
                    >= _time(decided_at, "decided_at"),
                    "invalid_authorization_basis",
                    "new source approval predates the review decision")
        item = _plan_item(
            row, source, decided_at, review["expires_at"],
            review["policy_snapshot"],
        )
        item.pop("source_approval")
        operations.append(item)
        approvals.append({"operation_id": row["operation_id"],
                          "source_approval": source})
    index_rows = [row for row in operations
                  if row["workflow_role"] == "task_index_transition"]
    raw = {
        "schema_version": 2,
        "execution_mode": "execute_with_declared_authorization",
        "complete_effect_inventory": True,
        "max_user_approval_interactions": 0,
        "authorized_local_effects": sorted({row["effect_class"] for row in operations}),
        "excluded_effects": sorted(FORBIDDEN_EFFECTS),
        "git_finalization": review["git_finalization"],
        "task_index_transition": (
            {"status": "planned", "operation_id": index_rows[0]["operation_id"]}
            if index_rows else
            {"status": "not_applicable", "reason": "No task-index effect."}
        ),
        "operations": operations,
        "reporting": copy.deepcopy(review["reporting"]),
        "authorization_basis": {
            "schema_version": 1,
            "basis_kind": "task_doctor_declared_authorization",
            "approvals": approvals,
        },
    }
    return normalize_plan(raw)


def publish_review(root: Path, review: dict[str, Any]) -> dict[str, Any]:
    normalized = validate_review(review)
    ref = f".task/task_doctor/reviews/{normalized['review_id']}.json"
    created, digest = publish_immutable(root, ref, normalized)
    return {"review_ref": ref, "review_sha256": digest,
            "created": created, "replayed": not created}


def publish_workflow_plan(root: Path, plan: dict[str, Any]) -> dict[str, Any]:
    normalized = (
        validate_normalized_plan(plan)
        if plan.get("kind") == "task_doctor_workflow_plan"
        else normalize_plan(plan)
    )
    digest = sha256_json(normalized)
    ref = f".task/task_doctor/workflow-plans/tdp-{digest[:20]}.json"
    created, file_digest = publish_immutable(root, ref, normalized)
    return {"plan_ref": ref, "plan_file_sha256": file_digest,
            "created": created, "replayed": not created}


def _revalidate_review_inputs(root: Path, review: dict[str, Any]) -> None:
    """Rehash compiler and owner-plan inputs before publishing an accepted plan."""

    for row in review["operations"]:
        compilation = load_compilation(
            root, row["compiled_operation"], skills_root=SKILLS_ROOT
        )
        require(compilation == row["compiled_operation"], "invalid_review",
                f"compiled operation changed for {row['operation_id']}")
        binding = row["plan_binding"]
        path = workspace_file(
            root, binding["ref"], binding["sha256"],
            f"{row['operation_id']}.plan_binding",
        )
        require(read_json(path, "invalid_review") == row["plan"],
                "invalid_review",
                f"owner plan changed for {row['operation_id']}")


def accept_review(
    root: Path, review_ref: str, review_sha256: str, decision: Any,
) -> dict[str, Any]:
    path = workspace_file(root, review_ref, review_sha256, "review")
    review = validate_review(read_json(path, "invalid_review"))
    require(isinstance(decision, dict), "invalid_review_decision",
            "review decision must be an object")
    expect_keys(decision, DECISION_KEYS, set(), "review decision",
                "invalid_review_decision")
    require(decision["schema_version"] == 1
            and decision["decision_kind"] == "task_doctor_review_acceptance"
            and decision["review_id"] == review["review_id"]
            and decision["review_fingerprint"] == review["review_fingerprint"],
            "invalid_review_decision", "review decision identity mismatch")
    decided_at = _time(decision["decided_at"], "decided_at")
    require(decided_at >= _time(review["prepared_at"], "prepared_at"),
            "invalid_review_decision", "review decision predates preparation")
    require(decided_at < _time(review["expires_at"], "expires_at"),
            "invalid_review_decision", "review decision is outside the plan lifetime")
    _revalidate_review_inputs(root, review)
    expected = {item["operation_id"] for item in review["approval_scope"]["operations"]}
    supplied = decision["source_approvals"]
    require(isinstance(supplied, dict) and set(supplied) == expected,
            "invalid_review_decision",
            "decision must bind every uncovered operation exactly once")
    sources = {
        row["operation_id"]: row["existing_source_approval"]
        for row in review["operations"]
    }
    sources.update({key: _binding(value, f"source_approvals.{key}")
                    for key, value in supplied.items()})
    plan = _build_plan(
        root, review, sources, decided_at.isoformat(),
        evidence_id=(
            f"{decision['evidence_id']}@{review['review_fingerprint']}"
        ),
    )
    return {"ok": True, "status": "ready", "plan": plan,
            **publish_workflow_plan(root, plan)}


__all__ = [
    "accept_review", "compile_intent", "publish_review",
    "publish_workflow_plan", "validate_review",
]
