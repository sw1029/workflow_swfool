"""Durable cancellation of speculative final-index work after dependency no-effect."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from .authority import SKILLS_ROOT, validate_completion
from .common import (
    SCHEMA_VERSION,
    WorkflowError,
    expect_keys,
    now,
    read_json,
    require,
    sha256_json,
    workspace_file,
    workspace_regular_file,
)
from .journal import event
from .task_transition_store import owned_ref, publish_immutable


AUTHORITY_SCRIPTS = SKILLS_ROOT / "manage-agent-authority" / "scripts"
if str(AUTHORITY_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(AUTHORITY_SCRIPTS))

from manage_agent_authority.lifecycle import release  # noqa: E402
from manage_agent_authority.projection_io import (  # noqa: E402
    validate_reservation_state,
)
from manage_agent_authority.projection_receipts import (  # noqa: E402
    validate_release_receipt,
)
from manage_agent_authority.workflow_status import resolve_operation  # noqa: E402


INTENT_KIND = "task_doctor_dependency_cancellation_intent"
RECEIPT_KIND = "task_doctor_dependency_cancellation_receipt"
OWNER_ACTIVITY_FIELDS = (
    "status",
    "integrity_valid",
    "plan_effect_observed",
    "plan_intent_observed",
    "receipt_status",
    "historical_completion_observed",
    "historical_transaction_complete",
    "no_effect_verified",
)


def _binding(
    value: Any, label: str, *, exact: bool = True,
) -> dict[str, str]:
    require(isinstance(value, dict), "invalid_dependency_cancellation",
            f"{label} must be an object")
    if exact:
        expect_keys(value, {"ref", "sha256"}, set(), label,
                    "invalid_dependency_cancellation")
    else:
        require({"ref", "sha256"} <= set(value),
                "invalid_dependency_cancellation",
                f"{label} lacks an exact file binding")
    return {"ref": str(value["ref"]), "sha256": str(value["sha256"])}


def _public_authority_state(
    root: Path, item: dict[str, Any], *, evaluated_at: str,
) -> dict[str, Any]:
    if item["authority"]["applicability"] == "none":
        return {"reservation": None, "settlement_receipt": None}
    authority = item["authority"]
    try:
        resolved = resolve_operation(
            root, authority["request"],
            authority["materialization"]["evaluation_context"],
            evaluated_at=evaluated_at, skills_root=SKILLS_ROOT,
        )
    except (SystemExit, KeyError, TypeError, ValueError) as error:
        raise WorkflowError(
            "invalid_dependency_cancellation",
            f"cannot inspect downstream authority before cancellation: {error}",
        ) from error
    basis = resolved.get("workflow_basis")
    require(isinstance(basis, dict)
            and basis.get("request_sha256") == authority["request_sha256"],
            "invalid_dependency_cancellation",
            "downstream authority projection binds a different request")
    reservation = basis.get("reservation")
    settlement = basis.get("settlement_receipt")
    return {
        "reservation": _binding(reservation, "reservation", exact=False)
        if isinstance(reservation, dict) else None,
        "settlement_receipt": _binding(
            settlement, "settlement_receipt", exact=False
        )
        if isinstance(settlement, dict) else None,
    }


def _intent_body(
    journal: dict[str, Any], item: dict[str, Any], trigger_id: str,
    trigger_evidence: dict[str, str], authority_state: dict[str, Any],
    owner_activity: dict[str, Any],
) -> dict[str, Any]:
    identity = {
        "workflow_id": journal["workflow_id"],
        "operation_id": item["operation_id"],
        "plan_sha256": item["plan_sha256"],
        "trigger_dependency": trigger_id,
        "trigger_completion": trigger_evidence,
        "owner_activity": owner_activity,
    }
    cancellation_id = f"depc-{sha256_json(identity)[:24]}"
    return {
        "schema_version": SCHEMA_VERSION,
        "artifact_kind": INTENT_KIND,
        "cancellation_id": cancellation_id,
        **identity,
        "plan_binding": item["plan_binding"],
        "reservation": authority_state["reservation"],
        "owner_dispatch_observed": False,
        "reason": "required_dependency_confirmed_no_effect",
    }


def _owner_activity(owner: dict[str, Any]) -> dict[str, Any]:
    require(all(field in owner for field in OWNER_ACTIVITY_FIELDS),
            "invalid_dependency_cancellation",
            "public index verifier omitted cancellation activity fields")
    return {field: owner[field] for field in OWNER_ACTIVITY_FIELDS}


def _cancel_safe_owner_state(owner: dict[str, Any]) -> bool:
    """Require public proof that the index owner never started or completed."""

    return (
        owner.get("status") == "stale"
        and owner.get("integrity_valid") is True
        and owner.get("plan_effect_observed") is False
        and owner.get("plan_intent_observed") is False
        and owner.get("receipt_status") == "missing"
        and owner.get("historical_completion_observed") is False
        and owner.get("historical_transaction_complete") is False
        and owner.get("no_effect_verified") is False
    )


def _reopen_cancel_safe_owner(
    root: Path, item: dict[str, Any], expected: dict[str, Any],
) -> None:
    from .authority import verify_operation_plan

    current = _owner_activity(verify_operation_plan(
        root, item, phase="planning", dependencies_ready=True,
    ))
    require(current == expected and _cancel_safe_owner_state(current),
            "stale_dependency_cancellation",
            "public index activity changed after dependency cancellation planning")


def _release_or_reopen(
    root: Path, intent: dict[str, Any], intent_binding: dict[str, str],
    authority_state: dict[str, Any], item: dict[str, Any], *, released_at: str,
) -> dict[str, Any]:
    _reopen_cancel_safe_owner(root, item, intent["owner_activity"])
    reservation = authority_state["reservation"]
    if reservation is None:
        return {"status": "not_reserved"}
    existing = authority_state["settlement_receipt"]
    if existing is None:
        try:
            released = release(
                root, reservation["ref"], reservation["sha256"], intent_binding,
                released_at=released_at, expected_version=0,
                idempotency_key=f"cancel-{intent['cancellation_id']}",
                effect_status="not_started",
            )
        except SystemExit as error:
            raise WorkflowError(
                "dependency_cancellation_release_failed", str(error)
            ) from error
        existing = {"ref": released["ref"], "sha256": released["sha256"]}
    _verify_release(root, existing, reservation, intent_binding)
    return {"status": "released_not_started", "receipt": existing}


def _verify_release(
    root: Path, receipt_binding: dict[str, str], reservation: dict[str, str],
    intent_binding: dict[str, str],
) -> None:
    path = workspace_file(
        root, receipt_binding["ref"], receipt_binding["sha256"],
        "dependency cancellation release receipt",
    )
    receipt = read_json(path, "invalid_dependency_cancellation")
    try:
        validate_release_receipt(root, receipt, path)
    except (SystemExit, KeyError, TypeError, ValueError) as error:
        raise WorkflowError(
            "invalid_dependency_cancellation",
            f"dependency cancellation release receipt is invalid: {error}",
        ) from error
    require(receipt.get("reservation") == reservation
            and receipt.get("no_effect_evidence") == intent_binding
            and receipt.get("effect_status") == "not_started"
            and receipt.get("release_applied") is True,
            "invalid_dependency_cancellation",
            "release does not bind exact not-started dependency cancellation")
    changes = [
        change for change in receipt["state_changes"]
        if change.get("after", {}).get("artifact_kind")
        == "authority_reservation_state"
    ]
    require(len(changes) == 1, "invalid_dependency_cancellation",
            "release receipt lacks one downstream reservation state change")
    state_ref = changes[0]["ref"]
    state_path = workspace_regular_file(
        root, state_ref, "released downstream reservation state",
    )
    try:
        state = validate_reservation_state(
            read_json(state_path, "invalid_dependency_cancellation"),
            receipt["state_changes"][-1]["after"]["reservation_id"],
            "dependency cancellation reservation state",
        )
    except (SystemExit, KeyError, TypeError, ValueError) as error:
        raise WorkflowError("invalid_dependency_cancellation", str(error)) from error
    require(state["status"] == "released"
            and state["last_event_id"] == receipt["receipt_id"]
            and changes[0]["after"] == state,
            "invalid_dependency_cancellation",
            "downstream reservation is not currently released by cancellation")


def validate_dependency_cancellation(
    root: Path, journal: dict[str, Any], operation_id: str,
    binding: dict[str, str],
) -> dict[str, Any]:
    item = next(entry for entry in journal["plan"]["operations"]
                if entry["operation_id"] == operation_id)
    path = workspace_file(root, binding["ref"], binding["sha256"],
                          "dependency cancellation receipt")
    receipt = read_json(path, "invalid_dependency_cancellation")
    expect_keys(receipt, {"schema_version", "artifact_kind", "cancellation_id",
                          "intent", "authority_settlement", "outcome",
                          "replacement_required"}, set(),
                "dependency cancellation receipt", "invalid_dependency_cancellation")
    require(receipt["schema_version"] == SCHEMA_VERSION
            and receipt["artifact_kind"] == RECEIPT_KIND
            and receipt["outcome"] == "dependent_plan_cancelled"
            and receipt["replacement_required"] is True,
            "invalid_dependency_cancellation",
            "dependency cancellation receipt contract mismatch")
    intent_binding = _binding(receipt["intent"], "intent")
    intent_path = workspace_file(root, intent_binding["ref"], intent_binding["sha256"],
                                 "dependency cancellation intent")
    intent = read_json(intent_path, "invalid_dependency_cancellation")
    _verify_intent(root, journal, item, intent, receipt["cancellation_id"])
    settlement = receipt["authority_settlement"]
    require(isinstance(settlement, dict), "invalid_dependency_cancellation",
            "authority_settlement must be an object")
    if settlement.get("status") == "released_not_started":
        _verify_release(root, _binding(settlement.get("receipt"), "release receipt"),
                        _binding(intent["reservation"], "reservation"), intent_binding)
    else:
        require(settlement == {"status": "not_reserved"}
                and intent["reservation"] is None,
                "invalid_dependency_cancellation",
                "unreserved cancellation settlement is inconsistent")
    return receipt


def _verify_intent(
    root: Path, journal: dict[str, Any], item: dict[str, Any],
    intent: dict[str, Any], cancellation_id: str,
) -> None:
    expect_keys(intent, {"schema_version", "artifact_kind", "cancellation_id",
                         "workflow_id", "operation_id", "plan_sha256",
                         "trigger_dependency", "trigger_completion", "plan_binding",
                         "reservation", "owner_activity",
                         "owner_dispatch_observed", "reason"}, set(),
                "dependency cancellation intent", "invalid_dependency_cancellation")
    trigger = intent["trigger_dependency"]
    completion = _binding(intent["trigger_completion"], "trigger_completion")
    require(intent["schema_version"] == SCHEMA_VERSION
            and intent["artifact_kind"] == INTENT_KIND
            and intent["cancellation_id"] == cancellation_id
            and intent["workflow_id"] == journal["workflow_id"]
            and intent["operation_id"] == item["operation_id"]
            and intent["plan_sha256"] == item["plan_sha256"]
            and intent["plan_binding"] == item["plan_binding"]
            and trigger in item["dependencies"]
            and intent["owner_dispatch_observed"] is False
            and intent["reason"] == "required_dependency_confirmed_no_effect",
            "invalid_dependency_cancellation",
            "dependency cancellation intent binding mismatch")
    activity = intent["owner_activity"]
    require(isinstance(activity, dict)
            and set(activity) == set(OWNER_ACTIVITY_FIELDS),
            "invalid_dependency_cancellation",
            "dependency cancellation owner activity projection is not closed")
    identity = {
        "workflow_id": journal["workflow_id"],
        "operation_id": item["operation_id"],
        "plan_sha256": item["plan_sha256"],
        "trigger_dependency": trigger,
        "trigger_completion": completion,
        "owner_activity": activity,
    }
    require(cancellation_id == f"depc-{sha256_json(identity)[:24]}",
            "invalid_dependency_cancellation",
            "dependency cancellation ID does not bind owner activity")
    _reopen_cancel_safe_owner(root, item, activity)
    dependency_state = journal["operation_state"][trigger]
    require(dependency_state["result_evidence"] == completion,
            "invalid_dependency_cancellation",
            "cancellation trigger differs from terminal dependency evidence")
    _completion, effect = validate_completion(
        root, journal, trigger, completion["ref"], completion["sha256"]
    )
    require(effect == "confirmed_no_effect", "invalid_dependency_cancellation",
            "dependency cancellation trigger is not verified no-effect")


def cancel_index_dependents(
    root: Path, journal: dict[str, Any], trigger_id: str,
    trigger_evidence: dict[str, str], *, cancelled_at: str | None = None,
) -> list[str]:
    """Cancel never-dispatched final-index plans invalidated by one no-effect."""

    cancelled: list[str] = []
    at = cancelled_at or now()
    for item in journal["plan"]["operations"]:
        operation_id = item["operation_id"]
        state = journal["operation_state"][operation_id]
        if (item["workflow_role"] != "task_index_transition"
                or trigger_id not in item["dependencies"]
                or state["status"] != "pending"):
            continue
        from .authority import verify_operation_plan

        owner = verify_operation_plan(
            root, item, phase="planning", dependencies_ready=True,
        )
        activity = _owner_activity(owner)
        if not _cancel_safe_owner_state(activity):
            continue
        require(not any(
            value.get("event") == "owner_dispatched"
            and value.get("operation_id") == operation_id
            for value in journal["events"]
        ), "invalid_dependency_cancellation",
                "dependency cancellation cannot follow an owner dispatch")
        authority_state = _public_authority_state(root, item, evaluated_at=at)
        intent = _intent_body(
            journal, item, trigger_id, trigger_evidence, authority_state,
            activity,
        )
        intent_ref = owned_ref(
            intent["cancellation_id"], "dependency-cancellations", "intent.json"
        )
        _created, intent_sha = publish_immutable(root, intent_ref, intent)
        intent_binding = {"ref": intent_ref, "sha256": intent_sha}
        settlement = _release_or_reopen(
            root, intent, intent_binding, authority_state, item, released_at=at,
        )
        receipt = {
            "schema_version": SCHEMA_VERSION,
            "artifact_kind": RECEIPT_KIND,
            "cancellation_id": intent["cancellation_id"],
            "intent": intent_binding,
            "authority_settlement": settlement,
            "outcome": "dependent_plan_cancelled",
            "replacement_required": True,
        }
        receipt_ref = owned_ref(
            intent["cancellation_id"], "dependency-cancellations", "receipt.json"
        )
        _created, receipt_sha = publish_immutable(root, receipt_ref, receipt)
        receipt_binding = {"ref": receipt_ref, "sha256": receipt_sha}
        validate_dependency_cancellation(
            root, journal, operation_id, receipt_binding,
        )
        state.update(status="blocked", resolution="plan_changed",
                     result_evidence=receipt_binding)
        event(journal, "dependency_plan_cancelled", operation_id=operation_id,
              trigger_dependency=trigger_id, evidence=receipt_binding)
        cancelled.append(operation_id)
    return cancelled


__all__ = ["cancel_index_dependents", "validate_dependency_cancellation"]
