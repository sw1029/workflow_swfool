from __future__ import annotations

from typing import Any

from .authority_basis import authority_bundle as _bundle
from .journal import dependencies_complete


def _base(journal: dict[str, Any]) -> dict[str, Any]:
    return {
        "workflow_id": journal["workflow_id"],
        "plan_sha256": journal["plan_sha256"],
        "revision": journal["revision"],
        "execution_mode": journal["plan"]["execution_mode"],
        "git_finalization": journal["plan"]["git_finalization"],
        "user_action": "none",
        "should_prompt": False,
        "next_operation": None,
        "approval_interactions": {
            "used": journal["approval_interactions_used"],
            "maximum": journal["plan"]["max_user_approval_interactions"],
        },
    }


def _classified_ids(
    journal: dict[str, Any], classification: str, *,
    owner_lifecycle: dict[str, dict[str, Any]] | None = None,
    require_owner_ready: bool = False,
) -> list[str]:
    states = journal["operation_state"]
    owner_lifecycle = owner_lifecycle or {}
    return [
        item["operation_id"] for item in journal["plan"]["operations"]
        if states[item["operation_id"]]["status"] not in {"complete", "skipped"}
        and states[item["operation_id"]]["resolution"] == classification
        and (
            not require_owner_ready
            or (
                dependencies_complete(journal, item)
                and owner_lifecycle.get(item["operation_id"], {}).get("status")
                == "ready"
            )
        )
    ]


def _project_owner_lifecycle(
    journal: dict[str, Any], result: dict[str, Any],
    owner_lifecycle: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    """Route public non-ready owner states without converting them to prompts."""

    routes = {
        "materializing": (
            "owner_materializing", "owner_materializing",
            "wait_for_owner_materialization",
        ),
        "already_applied": (
            "recovery_required", "owner_effect_reconciliation",
            "reconcile_owner_effect",
        ),
        "settled_no_effect": (
            "recovery_required", "owner_settled_no_effect",
            "settle_owner_no_effect",
        ),
        "recovery_required": (
            "recovery_required", "owner_recovery_required",
            "recover_owner_operation",
        ),
        "stale": (
            "superseded", "owner_plan_stale", "cancel_or_replan_owner_plan",
        ),
        "conflict": (
            "recovery_required", "blocked_by_defect", "repair_owner_conflict",
        ),
    }
    for item in journal["plan"]["operations"]:
        operation_id = item["operation_id"]
        state = journal["operation_state"][operation_id]
        if state["status"] != "pending" or not dependencies_complete(journal, item):
            continue
        observed = owner_lifecycle.get(operation_id, {})
        status = observed.get("status")
        if status not in routes:
            continue
        workflow_state, classification, next_action = routes[status]
        result.update(
            workflow_state=workflow_state,
            classification=classification,
            next_action=next_action,
            next_operation=operation_id,
            owner_lifecycle={
                "operation_id": operation_id,
                "status": status,
                "observation": observed,
            },
        )
        return result
    return None


def _live_bundle(
    operation_ids: list[str], live: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    return {
        "items": [
            {"operation_id": operation_id,
             "resolution": live[operation_id]["resolution"],
             "next_action": live[operation_id]["next_action"],
             "workflow_basis": live[operation_id]["workflow_basis"]}
            for operation_id in operation_ids
        ]
    }


def _project_live_progress(
    journal: dict[str, Any], result: dict[str, Any], operation_ids: list[str],
    live: dict[str, dict[str, Any]], *, source: str,
) -> dict[str, Any]:
    operation_id = operation_ids[0]
    overlay = live[operation_id]
    next_action = overlay["next_action"]
    result.update(
        workflow_state=(
            "replanning_required"
            if overlay["resolution"] == "plan_changed"
            else "authority_materialization"
        ),
        classification=overlay["resolution"],
        next_action=next_action["code"],
        next_operation=operation_id,
        authority_resolution_source=source,
        live_authority_progress=_live_bundle(operation_ids, live),
    )
    if source in {"already_covered", "needs_user_approval"}:
        result["authority_bundle"] = _bundle(
            journal=journal, operation_ids=operation_ids,
            kind="authority_materialization_bundle",
        )
    return result


def _semantic_scope(journal: dict[str, Any]) -> set[str] | None:
    scopes = [
        item for item in journal["events"]
        if item["event"] == "semantic_approval_scope_bound"
    ]
    if not scopes:
        return None
    return set(scopes[0]["operations"])


def _terminal_projection(
    journal: dict[str, Any], result: dict[str, Any],
) -> dict[str, Any] | None:
    states = journal["operation_state"]
    operations = journal["plan"]["operations"]
    if not all(
        states[item["operation_id"]]["status"] in {"complete", "skipped"}
        for item in operations
    ):
        return None
    result.update(workflow_state="complete", classification="complete",
                  next_action="report_outcome")
    return result


def _live_replan_projection(
    journal: dict[str, Any], result: dict[str, Any],
    live: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    states = journal["operation_state"]
    replans = [
        item["operation_id"] for item in journal["plan"]["operations"]
        if states[item["operation_id"]]["status"] == "pending"
        and item["operation_id"] in live
        and live[item["operation_id"]]["resolution"] == "plan_changed"
    ]
    if not replans:
        return None
    result.update(
        workflow_state="replanning_required", classification="plan_changed",
        next_action="prepare_new_plan", next_operation=replans[0],
        live_authority_progress=_live_bundle(replans, live),
    )
    return result


def _pending_approval_projection(
    journal: dict[str, Any], result: dict[str, Any],
    live: dict[str, dict[str, Any]], *, allow_unbound_initial: bool,
) -> dict[str, Any] | None:
    approvals = _classified_ids(journal, "needs_user_approval")
    if not approvals:
        return None
    prompting = [
        operation_id for operation_id in approvals
        if operation_id not in live or live[operation_id]["should_prompt"]
    ]
    scope = _semantic_scope(journal)
    outside_scope = (
        [] if allow_unbound_initial
        else [operation_id for operation_id in prompting
              if scope is None or operation_id not in scope]
    )
    if outside_scope:
        bundle = _bundle(journal, outside_scope, "changed_plan_bundle")
        result.update(
            workflow_state="replanning_required",
            classification="plan_changed",
            next_action="prepare_new_plan",
            next_operation=outside_scope[0],
            changed_plan_bundle=bundle,
        )
        return result
    unresolved = (
        prompting if allow_unbound_initial
        else [operation_id for operation_id in prompting if operation_id in scope]
    )
    progressed = [operation_id for operation_id in approvals
                  if operation_id in live and operation_id not in unresolved]
    if not unresolved:
        return _project_live_progress(
            journal, result, progressed, live, source="needs_user_approval"
        )
    bundle = _bundle(journal, unresolved, "consolidated_approval_bundle")
    result.update(workflow_state="awaiting_approval",
                  classification="needs_user_approval",
                  next_action="request_consolidated_approval",
                  next_operation=unresolved[0], user_action="approve",
                  should_prompt=True, approval_bundle=bundle, wait=bundle)
    if progressed:
        result["live_authority_progress"] = _live_bundle(progressed, live)
    return result


def project_status(
    journal: dict[str, Any], live: dict[str, dict[str, Any]] | None = None,
    owner_lifecycle: dict[str, dict[str, Any]] | None = None,
    *, allow_unbound_initial_approval: bool = False,
) -> dict[str, Any]:
    result = _base(journal)
    live = live or {}
    owner_lifecycle = owner_lifecycle or {}
    operations = journal["plan"]["operations"]
    states = journal["operation_state"]
    required_ids = [item["operation_id"] for item in operations if item["required"]]
    required_complete = all(states[item]["status"] == "complete" for item in required_ids)
    terminal = _terminal_projection(journal, result)
    if terminal is not None:
        return terminal

    recovery = [
        item["operation_id"] for item in operations
        if states[item["operation_id"]]["status"] == "recovery_required"
        or states[item["operation_id"]]["resolution"] == "effect_reconciliation"
    ]
    if recovery:
        result.update(workflow_state="recovery_required",
                      classification="effect_reconciliation",
                      next_action="recover_effect", next_operation=recovery[0])
        return result
    in_progress = [item["operation_id"] for item in operations
                   if states[item["operation_id"]]["status"] == "in_progress"]
    if in_progress:
        result.update(workflow_state="applying", classification="applying",
                      next_action="record_owner_result", next_operation=in_progress[0])
        return result
    applied = [item["operation_id"] for item in operations
               if states[item["operation_id"]]["status"] == "effect_applied"]
    if applied:
        result.update(workflow_state="applying", classification="ready_to_resume",
                      next_action="settle_authority_then_complete",
                      next_operation=applied[0])
        return result

    defects = _classified_ids(journal, "blocked_by_defect")
    if defects:
        result.update(workflow_state="recovery_required",
                      classification="blocked_by_defect",
                      next_action="repair_workflow_defect", next_operation=defects[0],
                      defect_bundle=_bundle(journal, defects, "defect_bundle"))
        return result
    changed = _classified_ids(journal, "plan_changed")
    if changed:
        bundle = _bundle(journal, changed, "changed_plan_bundle")
        result.update(workflow_state="replanning_required",
                      classification="plan_changed",
                      next_action="prepare_new_plan", next_operation=changed[0],
                      changed_plan_bundle=bundle)
        return result
    owner_projection = _project_owner_lifecycle(
        journal, result, owner_lifecycle
    )
    if owner_projection is not None:
        return owner_projection
    live_replan = _live_replan_projection(journal, result, live)
    if live_replan is not None:
        return live_replan
    approval_projection = _pending_approval_projection(
        journal, result, live,
        allow_unbound_initial=allow_unbound_initial_approval,
    )
    if approval_projection is not None:
        return approval_projection
    covered = _classified_ids(
        journal, "already_covered", owner_lifecycle=owner_lifecycle,
        require_owner_ready=True,
    )
    if covered:
        progressed = [operation_id for operation_id in covered if operation_id in live]
        if progressed:
            return _project_live_progress(
                journal, result, progressed, live, source="already_covered"
            )
        result.update(workflow_state="authority_materialization",
                      classification="already_covered",
                      next_action="materialize_exact_grants",
                      next_operation=covered[0],
                      authority_bundle=_bundle(journal, covered,
                                               "authority_materialization_bundle"))
        return result

    live_blocked = [
        item["operation_id"] for item in operations
        if states[item["operation_id"]]["status"] == "pending"
        and states[item["operation_id"]]["resolution"] in {
            "ready_to_resume", "projection_repair"
        }
        and item["operation_id"] in live
        and live[item["operation_id"]]["resolution"] != "ready_to_resume"
    ]
    if live_blocked:
        return _project_live_progress(
            journal, result, live_blocked, live,
            source=states[live_blocked[0]]["resolution"],
        )
    repairs = _classified_ids(journal, "projection_repair")
    if repairs:
        result.update(workflow_state="authorized", classification="projection_repair",
                      next_action="repair_projection", next_operation=repairs[0],
                      repair_bundle=_bundle(journal, repairs, "projection_repair_bundle"))
        return result

    ready = [
        item for item in operations
        if states[item["operation_id"]]["status"] == "pending"
        and states[item["operation_id"]]["resolution"] in {
            "authority_not_applicable", "ready_to_resume"
        }
        and dependencies_complete(journal, item)
        and owner_lifecycle.get(item["operation_id"], {}).get("status") == "ready"
    ]
    if ready:
        result.update(workflow_state="git_optional" if required_complete else "authorized",
                      classification="ready_to_resume", next_action="dispatch_owner",
                      next_operation=ready[0]["operation_id"])
        return result
    result.update(workflow_state="blocked", classification="blocked_by_defect",
                  next_action="inspect_dependency_or_optional_operation")
    return result
