"""Closed structural contract for task-doctor coordination journals."""

from __future__ import annotations

from datetime import datetime
import re
from typing import Any

from .common import (
    HEX64,
    KIND,
    RESOLUTIONS,
    SCHEMA_VERSION,
    SAFE_ID,
    WorkflowError,
    expect_keys,
    require,
    sha256_json,
)
from .plan import validate_normalized_plan
from .authority_basis import authority_bundle


JOURNAL_KEYS = {
    "kind",
    "schema_version",
    "workflow_id",
    "plan_sha256",
    "plan",
    "revision",
    "created_at",
    "updated_at",
    "approval_interactions_used",
    "operation_state",
    "events",
}
RFC3339 = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
)
RECORD_OUTCOMES = {
    "effect_applied", "completed", "no_effect", "confirmed_no_effect",
    "unknown_effect", "blocked_by_defect", "projection_repair", "plan_changed",
}
RECONCILE_OUTCOMES = {"confirmed_effect", "confirmed_no_effect", "still_unknown"}


def _timestamp(value: Any, label: str) -> datetime:
    require(isinstance(value, str) and RFC3339.fullmatch(value) is not None,
            "invalid_journal", f"{label} must be an RFC3339 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise WorkflowError(
            "invalid_journal", f"{label} must be an RFC3339 timestamp"
        ) from error
    require(parsed.utcoffset() is not None, "invalid_journal",
            f"{label} must include a timezone offset")
    return parsed
STATE_KEYS = {"status", "resolution", "resolution_evidence", "result_evidence"}
STATUSES = {
    "pending",
    "in_progress",
    "effect_applied",
    "recovery_required",
    "blocked",
    "complete",
    "skipped",
}
EVENT_KEYS = {
    "prepared": {"at", "event"},
    "authority_resolved": {
        "at", "event", "operation_id", "classification", "evidence",
    },
    "authority_bundle_resolved": {
        "at", "event", "from_classification", "operations", "bundle_ref",
        "bundle_sha256", "user_interaction",
    },
    "semantic_approval_scope_bound": {
        "at", "event", "operations", "bundle_id", "bundle_fingerprint",
    },
    "owner_dispatched": {"at", "event", "operation_id", "plan_sha256"},
    "owner_result_recorded": {
        "at", "event", "operation_id", "outcome", "evidence",
    },
    "resume_detected_unknown_effects": {"at", "event", "operations"},
    "effect_reconciled": {"at", "event", "operation_id", "outcome", "evidence"},
    "optional_operation_skipped": {"at", "event", "operation_id", "evidence"},
    "dependency_plan_cancelled": {
        "at", "event", "operation_id", "trigger_dependency", "evidence",
    },
}


def _binding(value: Any, label: str, *, exact: bool) -> None:
    require(isinstance(value, dict), "invalid_journal", f"{label} must be an object")
    if exact:
        expect_keys(value, {"ref", "sha256"}, set(), label, "invalid_journal")
    else:
        require({"ref", "sha256"} <= set(value), "invalid_journal",
                f"{label} must contain an exact file binding")
    require(isinstance(value.get("ref"), str) and bool(value["ref"]),
            "invalid_journal", f"{label}.ref must be non-empty")
    require(isinstance(value.get("sha256"), str)
            and HEX64.fullmatch(value["sha256"]) is not None,
            "invalid_journal", f"{label}.sha256 must be lowercase SHA-256")


def _operation_ids(plan: Any) -> tuple[list[str], dict[str, dict[str, Any]]]:
    require(isinstance(plan, dict), "invalid_journal", "journal plan must be an object")
    operations = plan.get("operations")
    require(isinstance(operations, list) and bool(operations), "invalid_journal",
            "journal plan must contain operations")
    identifiers: list[str] = []
    by_id: dict[str, dict[str, Any]] = {}
    for offset, item in enumerate(operations):
        require(isinstance(item, dict), "invalid_journal",
                f"journal plan operation {offset} must be an object")
        operation_id = item.get("operation_id")
        require(isinstance(operation_id, str) and SAFE_ID.fullmatch(operation_id),
                "invalid_journal", f"journal plan operation {offset} has an invalid ID")
        require(operation_id not in by_id, "invalid_journal",
                "journal plan operation IDs must be unique")
        identifiers.append(operation_id)
        by_id[operation_id] = item
    return identifiers, by_id


def _validate_state(
    operation_id: str, state: Any, plan_item: dict[str, Any],
) -> None:
    require(isinstance(state, dict), "invalid_journal",
            f"operation_state.{operation_id} must be an object")
    expect_keys(state, STATE_KEYS, set(), f"operation_state.{operation_id}",
                "invalid_journal")
    status = state["status"]
    resolution = state["resolution"]
    require(status in STATUSES, "invalid_journal",
            f"operation_state.{operation_id} has an invalid status")
    require(resolution in RESOLUTIONS, "invalid_journal",
            f"operation_state.{operation_id} has an invalid resolution")
    resolution_evidence = state["resolution_evidence"]
    result_evidence = state["result_evidence"]
    if resolution_evidence is not None:
        _binding(resolution_evidence, f"{operation_id}.resolution_evidence", exact=False)
    if result_evidence is not None:
        _binding(result_evidence, f"{operation_id}.result_evidence", exact=True)

    authority_free = plan_item.get("authority", {}).get("applicability") == "none"
    require((resolution == "authority_not_applicable") == authority_free,
            "invalid_journal",
            f"operation_state.{operation_id} authority applicability is inconsistent")
    if resolution == "authority_not_applicable":
        require(resolution_evidence is None, "invalid_journal",
                "authority-free operation cannot carry reservation evidence")
    if resolution == "needs_user_approval":
        require(status == "pending" and resolution_evidence is None
                and result_evidence is None, "invalid_journal",
                f"operation_state.{operation_id} unresolved review state is inconsistent")
    if resolution == "already_covered":
        require(status == "pending" and result_evidence is None,
                "invalid_journal",
                f"operation_state.{operation_id} source-covered state is inconsistent")
    if resolution == "already_settled":
        require(status == "complete" and result_evidence is not None,
                "invalid_journal", f"operation_state.{operation_id} settled state is incomplete")
    if resolution == "effect_reconciliation":
        require(status == "recovery_required", "invalid_journal",
                f"operation_state.{operation_id} reconciliation state is inconsistent")
    if resolution in {"blocked_by_defect", "plan_changed"}:
        require(status == "blocked", "invalid_journal",
                f"operation_state.{operation_id} blocked resolution is inconsistent")
    if status in {"complete", "skipped"}:
        require(result_evidence is not None, "invalid_journal",
                f"terminal operation {operation_id} lacks completion evidence")
    if status == "skipped":
        require(plan_item.get("required") is False, "invalid_journal",
                f"required operation {operation_id} cannot be skipped")
    if status in {"pending", "in_progress"}:
        require(result_evidence is None, "invalid_journal",
                f"operation_state.{operation_id} has premature result evidence")
    if status == "effect_applied":
        require(result_evidence is not None, "invalid_journal",
                f"operation_state.{operation_id} lacks applied-effect evidence")


def _event_operation_ids(value: Any, known: set[str], label: str) -> list[str]:
    require(isinstance(value, list) and bool(value), "invalid_journal",
            f"{label} must be a non-empty operation list")
    require(all(isinstance(item, str) and item in known for item in value),
            "invalid_journal", f"{label} contains an unknown operation")
    require(len(value) == len(set(value)), "invalid_journal",
            f"{label} contains duplicate operations")
    return value


def _validate_events(
    events: Any, operations: dict[str, dict[str, Any]], created_at: str,
    updated_at: str, revision: int, interactions: int,
) -> None:
    require(isinstance(events, list) and bool(events), "invalid_journal",
            "journal events must be a non-empty list")
    known = set(operations)
    interaction_events = 0
    created = _timestamp(created_at, "journal.created_at")
    updated = _timestamp(updated_at, "journal.updated_at")
    previous = created
    for offset, item in enumerate(events):
        require(isinstance(item, dict), "invalid_journal",
                f"journal event {offset} must be an object")
        name = item.get("event")
        require(name in EVENT_KEYS, "invalid_journal",
                f"journal event {offset} has an unsupported type")
        expect_keys(item, EVENT_KEYS[name], set(), f"journal event {offset}",
                    "invalid_journal")
        observed = _timestamp(item["at"], f"journal event {offset}.at")
        require(previous <= observed, "invalid_journal",
                "journal event timestamps must be nondecreasing")
        previous = observed
        if "operation_id" in item:
            operation_id = item["operation_id"]
            require(operation_id in known, "invalid_journal",
                    f"journal event {offset} names an unknown operation")
        if "operations" in item:
            _event_operation_ids(item["operations"], known, f"journal event {offset}")
        if "evidence" in item:
            _binding(item["evidence"], f"journal event {offset}.evidence", exact=False)
        if name == "owner_dispatched":
            require(item["plan_sha256"] == operations[item["operation_id"]].get("plan_sha256"),
                    "invalid_journal", "owner dispatch plan digest mismatch")
        if name == "dependency_plan_cancelled":
            require(item["trigger_dependency"] in known,
                    "invalid_journal",
                    "dependency cancellation names an unknown trigger")
        if name == "authority_resolved":
            require(item["classification"] in RESOLUTIONS, "invalid_journal",
                    "authority resolution event classification is invalid")
        if name == "owner_result_recorded":
            require(item["outcome"] in RECORD_OUTCOMES, "invalid_journal",
                    "owner result event outcome is invalid")
        if name == "effect_reconciled":
            require(item["outcome"] in RECONCILE_OUTCOMES, "invalid_journal",
                    "effect reconciliation event outcome is invalid")
        if name == "authority_bundle_resolved":
            require(item["from_classification"] in {
                "needs_user_approval", "already_covered"
            }, "invalid_journal", "authority bundle source classification is invalid")
            require(isinstance(item["bundle_ref"], str) and bool(item["bundle_ref"]),
                    "invalid_journal", "authority bundle ref must be non-empty")
            require(isinstance(item["bundle_sha256"], str)
                    and HEX64.fullmatch(item["bundle_sha256"]) is not None,
                    "invalid_journal", "authority bundle digest must be lowercase SHA-256")
            require(isinstance(item["user_interaction"], bool), "invalid_journal",
                    "authority bundle interaction marker must be boolean")
            interaction_events += int(item["user_interaction"])
        if name == "semantic_approval_scope_bound":
            require(isinstance(item["bundle_id"], str) and bool(item["bundle_id"]),
                    "invalid_journal", "approval scope bundle ID must be non-empty")
            require(isinstance(item["bundle_fingerprint"], str)
                    and HEX64.fullmatch(item["bundle_fingerprint"]) is not None,
                    "invalid_journal",
                    "approval scope fingerprint must be lowercase SHA-256")
    require(events[0] == {"at": created_at, "event": "prepared"},
            "invalid_journal", "journal must begin with the exact prepared event")
    require(sum(item.get("event") == "prepared" for item in events) == 1,
            "invalid_journal", "journal must contain one prepared event")
    require(revision == len(events) - 1, "invalid_journal",
            "journal revision must equal its mutation-event count")
    require(updated_at == events[-1]["at"], "invalid_journal",
            "journal updated_at must match its last event")
    require(updated == previous, "invalid_journal",
            "journal updated_at timestamp must equal the last event time")
    require(interactions == interaction_events, "invalid_journal",
            "journal approval interaction counter differs from its event history")


def _validate_semantic_approval_scope(journal: dict[str, Any]) -> None:
    scopes = [
        (offset, item) for offset, item in enumerate(journal["events"])
        if item["event"] == "semantic_approval_scope_bound"
    ]
    require(len(scopes) <= 1, "invalid_journal",
            "journal contains multiple semantic approval scopes")
    if not scopes:
        return
    offset, scope = scopes[0]
    require(offset == 1, "invalid_journal",
            "semantic approval scope must immediately follow workflow preparation")
    require(journal["plan"]["execution_mode"] == "consolidated_review",
            "invalid_journal",
            "semantic approval scope is valid only for consolidated review")
    operation_ids = scope["operations"]
    plan_rows = {
        item["operation_id"]: item for item in journal["plan"]["operations"]
    }
    require(all(plan_rows[value]["initial_resolution"] == "needs_user_approval"
                for value in operation_ids), "invalid_journal",
            "semantic approval scope contains an operation that did not require review")
    expected = authority_bundle(
        journal, operation_ids, "consolidated_approval_bundle"
    )
    require(scope["bundle_id"] == expected["bundle_id"]
            and scope["bundle_fingerprint"] == expected["fingerprint"],
            "invalid_journal",
            "semantic approval scope differs from its immutable plan projection")


def _recorded_state(outcome: str) -> tuple[str, str | None]:
    status = {
        "effect_applied": "effect_applied", "completed": "complete",
        "no_effect": "complete", "confirmed_no_effect": "complete",
        "unknown_effect": "recovery_required", "blocked_by_defect": "blocked",
        "projection_repair": "blocked", "plan_changed": "blocked",
    }[outcome]
    resolution = {
        "unknown_effect": "effect_reconciliation",
        "blocked_by_defect": "blocked_by_defect",
        "projection_repair": "plan_changed", "plan_changed": "plan_changed",
    }.get(outcome)
    return status, resolution


def _replay_events(
    events: list[dict[str, Any]], operations: dict[str, dict[str, Any]],
    observed: dict[str, dict[str, Any]],
) -> None:
    derived: dict[str, dict[str, Any]] = {
        operation_id: {
            "status": "pending", "resolution": item["initial_resolution"],
            "resolution_allowed": None, "result_evidence": None,
        }
        for operation_id, item in operations.items()
    }
    for event_item in events[1:]:
        name = event_item["event"]
        if name == "authority_bundle_resolved":
            for operation_id in event_item["operations"]:
                row = derived[operation_id]
                pending = row["status"] == "pending" or (
                    isinstance(row["status"], set)
                    and "pending" in row["status"]
                )
                require(pending, "invalid_journal",
                        "authority bundle re-resolves a non-pending operation")
                row["status"] = {"pending", "complete"}
                row["resolution"] = None
                row["resolution_allowed"] = {
                    "already_covered", "ready_to_resume", "already_settled",
                }
                row["result_evidence"] = None
        elif name == "authority_resolved":
            row = derived[event_item["operation_id"]]
            classification = event_item["classification"]
            row["resolution"] = classification
            row["resolution_allowed"] = None
            row["status"] = (
                "complete" if classification == "already_settled"
                else "blocked" if classification in {"blocked_by_defect", "plan_changed"}
                else "pending"
            )
            row["result_evidence"] = (
                event_item["evidence"] if classification == "already_settled" else None
            )
        elif name == "owner_dispatched":
            row = derived[event_item["operation_id"]]
            allowed = row["status"] == "pending" or (
                isinstance(row["status"], set) and "pending" in row["status"]
            )
            require(allowed, "invalid_journal",
                    "owner dispatch follows an impossible operation state")
            row["status"] = "in_progress"
            if row["resolution"] is None:
                row["resolution_allowed"] = {"ready_to_resume"}
        elif name == "owner_result_recorded":
            row = derived[event_item["operation_id"]]
            require(row["status"] in {"in_progress", "effect_applied"},
                    "invalid_journal", "owner result was not preceded by dispatch")
            status, resolution = _recorded_state(event_item["outcome"])
            row["status"] = status
            if resolution is not None:
                row["resolution"] = resolution
                row["resolution_allowed"] = None
            row["result_evidence"] = event_item["evidence"]
        elif name == "resume_detected_unknown_effects":
            for operation_id in event_item["operations"]:
                row = derived[operation_id]
                require(row["status"] == "in_progress", "invalid_journal",
                        "resume recovery event names a non-running operation")
                row["status"] = "recovery_required"
                row["resolution"] = "effect_reconciliation"
                row["resolution_allowed"] = None
        elif name == "effect_reconciled":
            row = derived[event_item["operation_id"]]
            require(row["status"] == "recovery_required", "invalid_journal",
                    "effect reconciliation was not preceded by recovery state")
            if event_item["outcome"] == "still_unknown":
                row["status"] = "recovery_required"
                row["resolution"] = "effect_reconciliation"
            else:
                row["status"] = "complete"
                row["resolution"] = "already_settled"
            row["resolution_allowed"] = None
            row["result_evidence"] = event_item["evidence"]
        elif name == "optional_operation_skipped":
            row = derived[event_item["operation_id"]]
            skippable = row["status"] in {"pending", "blocked"} or (
                isinstance(row["status"], set) and "pending" in row["status"]
            )
            require(skippable, "invalid_journal",
                    "optional skip follows an impossible operation state")
            row["status"] = "skipped"
            row["result_evidence"] = event_item["evidence"]
        elif name == "dependency_plan_cancelled":
            row = derived[event_item["operation_id"]]
            require(row["status"] == "pending", "invalid_journal",
                    "dependency cancellation follows a non-pending owner row")
            row["status"] = "blocked"
            row["resolution"] = "plan_changed"
            row["resolution_allowed"] = None
            row["result_evidence"] = event_item["evidence"]
    for operation_id, expected in derived.items():
        actual = observed[operation_id]
        expected_status = expected["status"]
        require(
            actual["status"] in expected_status
            if isinstance(expected_status, set) else actual["status"] == expected_status,
            "invalid_journal",
            f"operation_state.{operation_id} rolls back or diverges from event history",
        )
        if expected["resolution"] is not None:
            require(actual["resolution"] == expected["resolution"], "invalid_journal",
                    f"operation_state.{operation_id} resolution differs from event history")
        elif expected["resolution_allowed"] is not None:
            require(actual["resolution"] in expected["resolution_allowed"],
                    "invalid_journal",
                    f"operation_state.{operation_id} has an impossible bundle resolution")
        if expected["result_evidence"] is not None:
            require(actual["result_evidence"] == expected["result_evidence"],
                    "invalid_journal",
                    f"operation_state.{operation_id} result differs from event history")


def validate_journal(journal: Any, workflow_id: str) -> dict[str, Any]:
    """Validate a loaded journal before any status projection or mutation."""

    require(isinstance(journal, dict), "invalid_journal", "journal must be an object")
    expect_keys(journal, JOURNAL_KEYS, set(), "journal", "invalid_journal")
    require(journal["kind"] == KIND and journal["schema_version"] == SCHEMA_VERSION,
            "invalid_journal", "journal kind or schema version mismatch")
    require(journal["workflow_id"] == workflow_id, "invalid_journal",
            "journal workflow id mismatch")
    plan_digest = sha256_json(journal["plan"])
    require(journal["plan_sha256"] == plan_digest, "invalid_journal",
            "journal plan digest mismatch")
    require(workflow_id == f"tdw-{plan_digest[:20]}", "invalid_journal",
            "journal workflow id does not bind its immutable plan")
    validate_normalized_plan(journal["plan"])
    revision = journal["revision"]
    interactions = journal["approval_interactions_used"]
    require(isinstance(revision, int) and not isinstance(revision, bool) and revision >= 0,
            "invalid_journal", "journal revision must be a non-negative integer")
    require(isinstance(interactions, int) and not isinstance(interactions, bool)
            and interactions >= 0, "invalid_journal",
            "journal approval interaction count must be a non-negative integer")
    maximum = journal["plan"].get("max_user_approval_interactions")
    require(isinstance(maximum, int) and not isinstance(maximum, bool)
            and 0 <= interactions <= maximum, "invalid_journal",
            "journal approval interaction count exceeds its plan")
    for field in ("created_at", "updated_at"):
        _timestamp(journal[field], f"journal.{field}")
    identifiers, operations = _operation_ids(journal["plan"])
    states = journal["operation_state"]
    require(isinstance(states, dict) and set(states) == set(identifiers),
            "invalid_journal", "journal operation_state does not match its plan")
    for operation_id in identifiers:
        _validate_state(operation_id, states[operation_id], operations[operation_id])
    _validate_events(
        journal["events"], operations, journal["created_at"], journal["updated_at"],
        revision, interactions,
    )
    _validate_semantic_approval_scope(journal)
    _replay_events(journal["events"], operations, states)
    return journal


__all__ = ["validate_journal"]
