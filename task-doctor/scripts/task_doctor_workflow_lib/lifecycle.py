from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from .common import (
    DISPATCHABLE,
    KIND,
    SCHEMA_VERSION,
    now,
    read_json,
    require,
    sha256_json,
    workspace_file,
)
from .authority import (
    validate_completion,
    validate_reservation_evidence,
    verify_operation_plan,
)
from .authority_unknown import validate_unknown_settlement
from .journal import (
    atomic_write,
    dependencies_complete,
    event,
    load,
    locked,
    operation,
    workflow_paths,
)
from .journal_contract import validate_journal
from .plan import normalize_plan, verify_plan_bindings
from .terminal_validation import validate_terminal_operations
from .phase_validation import project_nonterminal_status
from .mutation import mutate_workflow as _mutate
from .effect_inventory import validate_root_effect_inventory
from .dependency_cancellation import cancel_index_dependents


def _evidence(root: Path, ref: str, digest: str, label: str) -> dict[str, str]:
    workspace_file(root, ref, digest, label)
    return {"ref": ref, "sha256": digest}


def _bind_initial_approval_scope(
    journal: dict[str, Any], projection: dict[str, Any],
) -> None:
    if (
        journal["plan"]["execution_mode"] != "consolidated_review"
        or projection.get("workflow_state") != "awaiting_approval"
        or projection.get("should_prompt") is not True
    ):
        return
    bundle = projection.get("approval_bundle")
    require(isinstance(bundle, dict), "invalid_workflow_projection",
            "initial approval projection lacks its exact bundle")
    items = bundle.get("items")
    require(isinstance(items, list) and bool(items), "invalid_workflow_projection",
            "initial approval projection lacks prompt-required operations")
    event(
        journal,
        "semantic_approval_scope_bound",
        operations=[item["operation_id"] for item in items],
        bundle_id=bundle["bundle_id"],
        bundle_fingerprint=bundle["fingerprint"],
    )


def prepare(root: Path, plan_path: Path) -> dict[str, Any]:
    plan = normalize_plan(read_json(plan_path))
    validate_root_effect_inventory(root, plan)
    plan_sha256 = sha256_json(plan)
    workflow_id = f"tdw-{plan_sha256[:20]}"
    journal_path, lock_path = workflow_paths(root, workflow_id)
    verified_new_plan = not journal_path.exists()
    if verified_new_plan:
        verify_plan_bindings(root, plan)
    with locked(root, lock_path):
        if journal_path.exists():
            journal = read_json(journal_path, "invalid_journal")
            validate_journal(journal, workflow_id)
            require(journal.get("plan_sha256") == plan_sha256, "workflow_collision",
                    "existing workflow id has a different immutable plan")
            verify_plan_bindings(root, plan, phase="structural")
            validate_terminal_operations(root, journal)
            result = project_nonterminal_status(root, journal)
            result.update(ok=True, command="prepare", replayed=True,
                          journal_ref=str(journal_path.relative_to(root)))
            return result
        if not verified_new_plan:
            verify_plan_bindings(root, plan)
        at = now()
        journal = {
            "kind": KIND, "schema_version": SCHEMA_VERSION,
            "workflow_id": workflow_id, "plan_sha256": plan_sha256, "plan": plan,
            "revision": 0, "created_at": at, "updated_at": at,
            "approval_interactions_used": 0,
            "operation_state": {
                item["operation_id"]: {
                    "status": "pending", "resolution": item["initial_resolution"],
                    "resolution_evidence": None, "result_evidence": None,
                }
                for item in plan["operations"]
            },
            "events": [{"at": at, "event": "prepared"}],
        }
        validate_journal(journal, workflow_id)
        result = project_nonterminal_status(
            root, journal, allow_unbound_initial_approval=True,
        )
        _bind_initial_approval_scope(journal, result)
        validate_journal(journal, workflow_id)
        atomic_write(root, journal_path, journal)
    result = project_nonterminal_status(root, journal)
    result.update(ok=True, command="prepare", replayed=False,
                  journal_ref=str(journal_path.relative_to(root)))
    return result


def status(root: Path, workflow_id: str) -> dict[str, Any]:
    journal_path, _, journal = load(root, workflow_id)
    validate_terminal_operations(root, journal)
    result = project_nonterminal_status(root, journal)
    result.update(ok=True, command="status",
                  journal_ref=str(journal_path.relative_to(root)),
                  operations=copy.deepcopy(journal["operation_state"]))
    return result


def resolve(
    root: Path, workflow_id: str, operation_id: str, classification: str,
    evidence_ref: str, evidence_sha256: str, expected_revision: int,
) -> dict[str, Any]:
    require(classification in {"ready_to_resume", "projection_repair", "already_settled",
                               "blocked_by_defect", "plan_changed"},
            "invalid_resolution", f"unsupported classification: {classification}")

    def mutate(journal: dict[str, Any]) -> dict[str, Any]:
        plan_item, state = operation(journal, operation_id)
        completion_effect: str | None = None
        if classification in {"ready_to_resume", "projection_repair"}:
            require(dependencies_complete(journal, plan_item),
                    "dependency_incomplete",
                    "downstream authority cannot be reserved before dependencies settle",
                    retryable=True, next_action="complete_dependencies")
            owner_lifecycle = verify_operation_plan(
                root, plan_item, phase="planning", dependencies_ready=True,
            )
            require(owner_lifecycle.get("status") == "ready",
                    "owner_not_dispatchable",
                    "cannot bind a reservation to a non-ready public owner plan",
                    next_action="route_owner_lifecycle",
                    details={"status": owner_lifecycle.get("status")})
            evidence = validate_reservation_evidence(
                root, plan_item, {"ref": evidence_ref, "sha256": evidence_sha256},
                dependencies_ready=True,
            )
        elif classification == "already_settled":
            _completion, completion_effect = validate_completion(
                root, journal, operation_id, evidence_ref, evidence_sha256,
            )
            evidence = _evidence(root, evidence_ref, evidence_sha256,
                                 "settled_completion")
        else:
            evidence = _evidence(root, evidence_ref, evidence_sha256,
                                 "resolution_evidence")
        if state["resolution"] == classification and state["resolution_evidence"] == evidence:
            if completion_effect == "confirmed_no_effect":
                cancel_index_dependents(
                    root, journal, operation_id, evidence,
                )
            return {"command": "resolve", "operation_id": operation_id}
        require(state["status"] in {"pending", "blocked"}, "invalid_transition",
                f"cannot resolve operation in state {state['status']}")
        require(state["resolution"] != "plan_changed", "plan_changed",
                "a changed plan requires a new immutable workflow",
                next_action="prepare_new_plan")
        require(state["resolution"] != "effect_reconciliation", "invalid_transition",
                "effect reconciliation must use recover")
        state["resolution"] = classification
        state["resolution_evidence"] = evidence
        state["status"] = (
            "blocked" if classification in {"blocked_by_defect", "plan_changed"}
            else "complete" if classification == "already_settled" else "pending"
        )
        if classification == "already_settled":
            state["result_evidence"] = evidence
        event(journal, "authority_resolved", operation_id=operation_id,
              classification=classification, evidence=evidence)
        if completion_effect == "confirmed_no_effect":
            cancel_index_dependents(
                root, journal, operation_id, evidence,
            )
        return {"command": "resolve", "operation_id": operation_id}

    return _mutate(root, workflow_id, expected_revision, mutate)


def apply(
    root: Path, workflow_id: str, operation_id: str | None, expected_revision: int
) -> dict[str, Any]:
    def mutate(journal: dict[str, Any]) -> dict[str, Any]:
        projection = project_nonterminal_status(root, journal)
        require(projection["classification"] in DISPATCHABLE,
                "authority_not_settled",
                f"workflow classification is {projection['classification']}",
                user_action_required=projection["should_prompt"],
                next_action=projection["next_action"])
        selected = operation_id or projection.get("next_operation")
        require(isinstance(selected, str), "no_dispatchable_operation",
                "workflow has no dispatchable owner operation")
        assert isinstance(selected, str)
        require(selected == projection["next_operation"], "invalid_dispatch_order",
                "dispatch the projected next operation before later dependencies")
        plan_item, state = operation(journal, selected)
        require(state["status"] == "pending", "invalid_transition",
                f"cannot apply operation in state {state['status']}")
        require(dependencies_complete(journal, plan_item), "dependency_incomplete",
                f"dependencies are incomplete for {selected}", retryable=True,
                next_action="complete_dependencies")
        require(state["resolution"] in DISPATCHABLE, "authority_not_settled",
                f"operation classification is {state['resolution']}")
        owner_lifecycle = verify_operation_plan(
            root, plan_item, dependencies_ready=True,
        )
        require(owner_lifecycle.get("status") == "ready",
                "owner_not_dispatchable",
                "public owner lifecycle is not ready for a new dispatch",
                next_action="refresh_owner_lifecycle",
                details={"status": owner_lifecycle.get("status")})
        if plan_item["authority"]["applicability"] == "required":
            evidence = state["resolution_evidence"]
            require(isinstance(evidence, dict), "authority_evidence_missing",
                    "dispatch requires exact authority/reservation evidence")
            refreshed = validate_reservation_evidence(
                root, plan_item, {"ref": evidence["ref"], "sha256": evidence["sha256"]},
                dependencies_ready=True,
            )
            require(refreshed == evidence, "authority_evidence_stale",
                    "reservation projection changed after workflow resolution")
        else:
            require(state["resolution"] == "authority_not_applicable"
                    and state["resolution_evidence"] is None,
                    "invalid_authority_evidence",
                    "authority-free dispatch must retain its closed classification")
        state["status"] = "in_progress"
        event(journal, "owner_dispatched", operation_id=selected,
              plan_sha256=plan_item["plan_sha256"])
        return {"command": "apply", "operation_id": selected,
                "owner_dispatch": copy.deepcopy(plan_item)}

    return _mutate(root, workflow_id, expected_revision, mutate)


def _validate_record_evidence(
    root: Path, journal: dict[str, Any], operation_id: str, outcome: str,
    evidence_ref: str, evidence_sha256: str,
) -> None:
    plan_item, state = operation(journal, operation_id)
    if outcome in {"completed", "no_effect", "confirmed_no_effect"}:
        _, effect = validate_completion(root, journal, operation_id,
                                        evidence_ref, evidence_sha256)
        expected = ("confirmed_effect" if outcome == "completed"
                    else "confirmed_no_effect")
        require(effect == expected, "invalid_owner_result",
                "recorded outcome differs from the settled owner effect")
    elif outcome == "unknown_effect":
        resolution = state.get("resolution_evidence") or {}
        reservation = {key: resolution.get(key, "") for key in ("ref", "sha256")}
        validate_unknown_settlement(
            root, plan_item, reservation, evidence_ref, evidence_sha256
        )
    elif outcome in {"blocked_by_defect", "projection_repair", "plan_changed"}:
        _, effect = validate_completion(root, journal, operation_id,
                                        evidence_ref, evidence_sha256)
        require(effect == "confirmed_no_effect", "invalid_owner_result",
                "a blocked or changed dispatch requires verified no-effect release")


def record_result(
    root: Path, workflow_id: str, operation_id: str, outcome: str,
    evidence_ref: str, evidence_sha256: str, expected_revision: int,
) -> dict[str, Any]:
    outcomes = {"effect_applied", "completed", "no_effect", "confirmed_no_effect",
                "unknown_effect",
                "blocked_by_defect", "projection_repair", "plan_changed"}
    require(outcome in outcomes, "invalid_result", f"unsupported outcome: {outcome}")
    evidence = _evidence(root, evidence_ref, evidence_sha256, "owner_result")

    def mutate(journal: dict[str, Any]) -> dict[str, Any]:
        _, state = operation(journal, operation_id)
        final_state = {
            "effect_applied": "effect_applied", "completed": "complete",
            "no_effect": "complete", "confirmed_no_effect": "complete",
            "unknown_effect": "recovery_required",
            "blocked_by_defect": "blocked", "projection_repair": "blocked",
            "plan_changed": "blocked",
        }[outcome]
        _validate_record_evidence(root, journal, operation_id, outcome,
                                  evidence_ref, evidence_sha256)
        if state["status"] == final_state and state["result_evidence"] == evidence:
            if outcome in {"no_effect", "confirmed_no_effect"}:
                cancel_index_dependents(
                    root, journal, operation_id, evidence,
                )
            return {"command": "record-result", "operation_id": operation_id,
                    "outcome": outcome}
        require(state["status"] in {"in_progress", "effect_applied"},
                "invalid_transition",
                f"cannot record result from state {state['status']}")
        state["status"] = final_state
        if outcome == "unknown_effect":
            state["resolution"] = "effect_reconciliation"
        elif outcome in {"blocked_by_defect", "plan_changed"}:
            state["resolution"] = outcome
        elif outcome == "projection_repair":
            state["resolution"] = "plan_changed"
        state["result_evidence"] = evidence
        event(journal, "owner_result_recorded", operation_id=operation_id,
              outcome=outcome, evidence=evidence)
        if outcome in {"no_effect", "confirmed_no_effect"}:
            cancel_index_dependents(
                root, journal, operation_id, evidence,
            )
        return {"command": "record-result", "operation_id": operation_id,
                "outcome": outcome}

    return _mutate(root, workflow_id, expected_revision, mutate)


def resume(root: Path, workflow_id: str, expected_revision: int) -> dict[str, Any]:
    def mutate(journal: dict[str, Any]) -> dict[str, Any]:
        validate_terminal_operations(root, journal)
        interrupted = []
        for operation_id, state in journal["operation_state"].items():
            if state["status"] == "in_progress":
                state["status"] = "recovery_required"
                state["resolution"] = "effect_reconciliation"
                interrupted.append(operation_id)
        if interrupted:
            event(journal, "resume_detected_unknown_effects", operations=interrupted)
        return {"command": "resume", "interrupted_operations": interrupted}

    return _mutate(root, workflow_id, expected_revision, mutate)


def recover(
    root: Path, workflow_id: str, operation_id: str, outcome: str,
    evidence_ref: str, evidence_sha256: str, expected_revision: int,
) -> dict[str, Any]:
    require(outcome in {"confirmed_effect", "confirmed_no_effect", "still_unknown"},
            "invalid_recovery", f"unsupported recovery outcome: {outcome}")
    def mutate(journal: dict[str, Any]) -> dict[str, Any]:
        plan_item, state = operation(journal, operation_id)
        if outcome == "still_unknown":
            reservation = state.get("resolution_evidence") or {}
            reservation_binding = {key: reservation.get(key, "")
                                   for key in ("ref", "sha256")}
            evidence = validate_unknown_settlement(
                root, plan_item, reservation_binding, evidence_ref, evidence_sha256
            )
        else:
            evidence = _evidence(root, evidence_ref, evidence_sha256,
                                 "recovery_evidence")
            _, effect = validate_completion(root, journal, operation_id,
                                            evidence_ref, evidence_sha256)
            require(effect == outcome, "invalid_owner_result",
                    "recovery outcome differs from settled authority evidence")
        target = {"confirmed_effect": "complete",
                  "confirmed_no_effect": "complete",
                  "still_unknown": "recovery_required"}[outcome]
        target_resolution = ("effect_reconciliation" if outcome == "still_unknown"
                             else "already_settled")
        if (state["status"] == target and state["resolution"] == target_resolution
                and state["result_evidence"] == evidence):
            if outcome == "confirmed_no_effect":
                cancel_index_dependents(
                    root, journal, operation_id, evidence,
                )
            return {"command": "recover", "operation_id": operation_id,
                    "outcome": outcome}
        require(state["status"] == "recovery_required"
                or state["resolution"] == "effect_reconciliation",
                "invalid_transition", "operation does not require effect reconciliation")
        state["status"] = target
        state["resolution"] = target_resolution
        state["result_evidence"] = evidence
        event(journal, "effect_reconciled", operation_id=operation_id,
              outcome=outcome, evidence=evidence)
        if outcome == "confirmed_no_effect":
            cancel_index_dependents(
                root, journal, operation_id, evidence,
            )
        return {"command": "recover", "operation_id": operation_id,
                "outcome": outcome}

    return _mutate(root, workflow_id, expected_revision, mutate)


def skip(
    root: Path, workflow_id: str, operation_id: str,
    evidence_ref: str, evidence_sha256: str, expected_revision: int,
) -> dict[str, Any]:
    def mutate(journal: dict[str, Any]) -> dict[str, Any]:
        plan_item, state = operation(journal, operation_id)
        _, effect = validate_completion(root, journal, operation_id,
                                        evidence_ref, evidence_sha256)
        require(effect == "confirmed_no_effect", "invalid_owner_result",
                "skipped operation requires a verified no-effect completion")
        evidence = _evidence(root, evidence_ref, evidence_sha256, "skip_evidence")
        if state["status"] == "skipped" and state["result_evidence"] == evidence:
            return {"command": "skip", "operation_id": operation_id}
        require(plan_item["required"] is False, "invalid_transition",
                "required operations cannot be skipped")
        require(state["status"] in {"pending", "blocked"}, "invalid_transition",
                f"cannot skip operation in state {state['status']}")
        require(dependencies_complete(journal, plan_item), "dependency_incomplete",
                "optional operation dependencies must finish before skip")
        state["status"] = "skipped"
        state["result_evidence"] = evidence
        event(journal, "optional_operation_skipped", operation_id=operation_id,
              evidence=evidence)
        return {"command": "skip", "operation_id": operation_id}

    return _mutate(root, workflow_id, expected_revision, mutate)
