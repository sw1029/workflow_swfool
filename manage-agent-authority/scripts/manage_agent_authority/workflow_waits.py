from __future__ import annotations

from pathlib import Path
from typing import Any

from .projection_reservations import current_operation_manifest_blockers
from .source_recovery import discover_source_recovery
from .workflow_candidates import current_allowed_decision
from .workflow_interaction import wait_identity
from .workflow_sources import source_approvals_covering, source_recovery_identity


def _decision_candidates(
    root: Path,
    decisions: list[tuple[dict[str, Any], dict[str, Any]]],
    at: Any,
    skills_root: Path | None,
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[tuple[dict[str, Any], dict[str, Any]]],
]:
    current: list[dict[str, Any]] = []
    stale: list[dict[str, Any]] = []
    approvals: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for decision, summary in decisions:
        if decision["decision"] == "allowed":
            usable, blockers = current_allowed_decision(
                root, decision, at, skills_root
            )
            candidate = {**summary, "current_blocker_codes": blockers}
            (current if usable else stale).append(candidate)
        elif decision["decision"] == "approval_required":
            approvals.append((decision, summary))
    return current, stale, approvals


def _source_groups(approvals: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    return {
        status: [
            item for item in approvals if item["materialization_status"] == status
        ]
        for status in ("ready", "defect", "fresh_authority_required")
    }


def _recipe_classification(
    wait: dict[str, Any], recipe: dict[str, Any]
) -> tuple[str, dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    sources = recipe["historical_source_approvals"]
    binding = {key: recipe[key] for key in ("ref", "sha256", "recipe_id")}
    entry = {
        **wait,
        "previous_wait_identity": wait["wait_identity"],
        "recovery_identity": recipe["recovery_identity"],
        "source_approvals": sources,
        "recovery_recipe": binding,
    }
    history = [{**wait, "superseded_by_recovery_recipe": binding}]
    if recipe["continuation_status"] == "replanning_required":
        replan = {
            **entry,
            "projection": None,
            "reason_codes": [recipe["replan_reason"]],
            "wait_identity": None,
            "post_approval_handoff": {
                **recipe["post_approval_handoff"],
                "authority_status": "non_authoritative_window_closed",
                "continuation_status": "replanning_required",
                "continuation_rule": "do not materialize; prepare a fresh recovery plan",
            },
        }
        return "recovery_replan", replan, history, []
    recovery_wait = {
        **entry,
        "projection": recipe["approval_projection"],
        "reason_codes": ["source_authority_replacement_requires_exact_user_approval"],
        "wait_identity": recipe["wait_identity"],
        "post_approval_handoff": recipe["post_approval_handoff"],
    }
    return "recovery_wait", recovery_wait, history, []


def _classify_wait(
    root: Path,
    decision: dict[str, Any],
    summary: dict[str, Any],
    reservations: list[dict[str, Any]],
    current_allowed: list[dict[str, Any]],
    grant_records: dict[str, Any],
    at: Any,
    skills_root: Path | None,
) -> tuple[str, dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    wait = {
        "decision": summary,
        "projection": decision["approval_projection"],
        "reason_codes": decision["reason_codes"],
        "wait_identity": wait_identity(decision),
    }
    terminal = [
        row
        for row in reservations
        if row["reservation"]["request_sha256"] == decision["request_sha256"]
        and row["state"]["status"]
        in {"reserved", "consumed", "released", "quarantined_unknown_effect"}
    ]
    if terminal:
        return "historical", wait, [{**wait, "superseded_by": terminal[0]["reservation"]}], []
    allowed = [
        item
        for item in current_allowed
        if item["request_sha256"] == decision["request_sha256"]
    ]
    if allowed:
        return "historical", wait, [{**wait, "superseded_by": allowed[0]}], []
    manifest_blockers = current_operation_manifest_blockers(decision, skills_root)
    if manifest_blockers:
        return (
            "historical",
            wait,
            [{**wait, "current_blocker_codes": manifest_blockers}],
            [],
        )
    recipe = discover_source_recovery(
        root,
        decision["request_sha256"],
        evaluated_at=at.isoformat(),
        skills_root=skills_root,
    )
    if recipe is not None:
        return _recipe_classification(wait, recipe)
    approvals = source_approvals_covering(
        root,
        decision["request"],
        decision["request_sha256"],
        decision["evaluation_context"],
        at.isoformat(),
        skills_root,
        grant_records,
    )
    groups = _source_groups(approvals)
    if groups["ready"]:
        entry = {**wait, "source_approvals": groups["ready"]}
        history = [{**wait, "superseded_by_source_approval": groups["ready"][0]}]
        return "source_ready", entry, history, approvals
    if groups["defect"]:
        return (
            "source_defect",
            {**wait, "source_approvals": groups["defect"]},
            [],
            approvals,
        )
    if groups["fresh_authority_required"]:
        exhausted = groups["fresh_authority_required"]
        recovery = source_recovery_identity(decision["request_sha256"], exhausted)
        entry = {
            **wait,
            "reason_codes": ["source_authority_no_usable_or_materializable_grant"],
            "previous_wait_identity": wait["wait_identity"],
            "wait_identity": None,
            "recovery_identity": recovery,
            "source_approvals": exhausted,
        }
        history = [
            {
                **wait,
                "superseded_by_source_exhaustion": {
                    "recovery_identity": recovery,
                    "source_approval": exhausted[0],
                },
            }
        ]
        return "source_exhausted", entry, history, approvals
    return "pending", wait, [], approvals


def classify_authority_candidates(
    root: Path,
    inventory: dict[str, Any],
    at: Any,
    skills_root: Path | None,
) -> dict[str, Any]:
    current, stale, approval_decisions = _decision_candidates(
        root, inventory["decisions"], at, skills_root
    )
    result: dict[str, Any] = {
        "current_allowed": current,
        "stale_allowed": stale,
        "waits": [],
        "historical_waits": [],
        "source_ready_waits": [],
        "source_defect_waits": [],
        "source_exhausted_waits": [],
        "recovery_waits": [],
        "recovery_replans": [],
        "covering_sources": [],
    }
    destinations = {
        "pending": "waits",
        "source_ready": "source_ready_waits",
        "source_defect": "source_defect_waits",
        "source_exhausted": "source_exhausted_waits",
        "recovery_wait": "recovery_waits",
        "recovery_replan": "recovery_replans",
    }
    for decision, summary in approval_decisions:
        category, entry, history, sources = _classify_wait(
            root,
            decision,
            summary,
            inventory["reservations"],
            current,
            inventory["grant_records"],
            at,
            skills_root,
        )
        if category in destinations:
            result[destinations[category]].append(entry)
        result["historical_waits"].extend(history)
        result["covering_sources"].extend(
            {
                **item,
                "request_sha256": decision["request_sha256"],
                "decision": summary,
            }
            for item in sources
        )
    unique_recovery: dict[str, dict[str, Any]] = {}
    for item in result["recovery_waits"]:
        unique_recovery.setdefault(item["wait_identity"], item)
    result["recovery_waits"] = list(unique_recovery.values())
    return result


__all__ = ["classify_authority_candidates"]
