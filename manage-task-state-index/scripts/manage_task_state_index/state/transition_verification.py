"""Read-only phase verification and durable no-effect settlement."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .events import load_events_read_only, merge_state
from .render import _markdown_projection_matches
from .storage import (
    index_lock,
    now_iso,
    rel_path,
    sha256_file,
)
from .transition_intent import (
    _load_intent,
    assert_no_pending_transition_intents,
    intent_for_plan,
    intent_path,
)
from .transition_no_effect import (
    build_no_effect_receipt,
    load_no_effect_receipt,
    no_effect_receipt_path,
    publish_no_effect_receipt,
)
from .transition_plan_contract import (
    load_transition_plan,
    owned_transition_file,
    receipt_for_plan,
    receipt_status,
    regular_payload,
    sha256_bytes,
    workspace_path,
)
from .transition_recovery import committed_boundary_valid, matching_events
from .transition_semantics import validate_transition_plan_semantics


VERIFY_PHASES = {"planning", "apply"}


def _artifact_digest(root: Path, relative: str) -> str | None:
    path = workspace_path(root, relative)
    if path.exists() or path.is_symlink():
        regular_payload(path)
    return sha256_file(path)


def _materialization_status(
    root: Path,
    plan: dict[str, Any],
    planning_defects: list[str],
    apply_defects: list[str],
) -> str:
    canonical_defects = {
        "ledger_sha256_mismatch",
        "markdown_sha256_mismatch",
    }
    if canonical_defects.intersection(planning_defects + apply_defects):
        return "canonical_drift"
    states: list[str] = []
    for anchor in plan["artifact_anchors"]:
        try:
            observed = _artifact_digest(root, anchor["path"])
        except ValueError:
            return "foreign"
        if observed == anchor["expected_sha256"]:
            states.append("expected")
        elif observed == anchor["before_sha256"]:
            states.append("before")
        else:
            return "foreign"
    if all(state == "expected" for state in states):
        return "expected"
    if all(state == "before" for state in states):
        return "before"
    return "partial"


def cas_status(
    root: Path, plan: dict[str, Any], *, phase: str = "apply"
) -> tuple[bool, list[str]]:
    if phase not in VERIFY_PHASES:
        raise ValueError("Task-state transition verify phase must be planning or apply")
    defects: list[str] = []
    ledger_file = workspace_path(root, ".task/index.jsonl")
    markdown_file = workspace_path(root, ".task/index.md")
    ledger = regular_payload(ledger_file, missing=b"")
    if sha256_bytes(ledger) != plan["ledger"]["before_sha256"]:
        defects.append("ledger_sha256_mismatch")
    markdown = regular_payload(markdown_file, missing=b"")
    markdown_digest = sha256_bytes(markdown) if markdown else None
    if markdown_digest != plan["markdown"]["before_sha256"]:
        defects.append("markdown_sha256_mismatch")
    expected_field = "before_sha256" if phase == "planning" else "expected_sha256"
    for anchor in plan["artifact_anchors"]:
        try:
            observed = _artifact_digest(root, anchor["path"])
        except ValueError:
            defects.append(f"artifact_not_regular:{anchor['path']}")
            continue
        if observed != anchor[expected_field]:
            defects.append(f"artifact_sha256_mismatch:{anchor['path']}")
    return not defects, defects


def _intent_observation(
    root: Path,
    plan: dict[str, Any],
    plan_ref: str,
    plan_file_sha256: str,
) -> bool:
    path = intent_path(root, str(plan["plan_id"]))
    if not path.exists() and not path.is_symlink():
        return False
    intent = _load_intent(path)
    if intent != intent_for_plan(plan, plan_ref, plan_file_sha256):
        raise ValueError("Task-state transition intent plan binding mismatch")
    return True


def _apply_receipt(
    root: Path,
    plan: dict[str, Any],
    plan_ref: str,
    plan_file_sha256: str,
) -> tuple[Path, dict[str, Any], str, str | None]:
    path = owned_transition_file(
        root,
        "transition_receipts",
        f"{plan['plan_id']}.json",
        create_parent=False,
    )
    expected = receipt_for_plan(plan, plan_ref, plan_file_sha256)
    status, digest = receipt_status(path, expected)
    return path, expected, status, digest


def _observation(
    root: Path, plan: dict[str, Any], defects: list[str]
) -> dict[str, Any]:
    ledger = regular_payload(workspace_path(root, ".task/index.jsonl"), missing=b"")
    markdown = regular_payload(workspace_path(root, ".task/index.md"), missing=b"")
    return {
        "ledger_sha256": sha256_bytes(ledger),
        "markdown_sha256": sha256_bytes(markdown) if markdown else None,
        "artifact_sha256": [
            {"path": anchor["path"], "sha256": _artifact_digest(root, anchor["path"])}
            for anchor in plan["artifact_anchors"]
        ],
        "cas_defects": list(defects),
        "plan_effect_observed": False,
        "plan_intent_observed": False,
    }


def verify_transition_plan_state(
    root: Path, path_value: str | Path, *, phase: str = "apply"
) -> dict[str, Any]:
    root = root.resolve()
    if phase not in VERIFY_PHASES:
        raise ValueError("Task-state transition verify phase must be planning or apply")
    plan_path, plan, plan_file_sha256 = load_transition_plan(root, path_value)
    validate_transition_plan_semantics(root, plan)
    plan_ref = rel_path(root, plan_path)
    workspace_path(root, ".task/index.jsonl")
    workspace_path(root, ".task/index.md")
    existing, _ledger_digest = load_events_read_only(root)
    exact, conflicting_events = matching_events(existing, plan)
    effect_observed = any(
        event.get("transition_plan_id") == plan["plan_id"] for event in existing
    )
    boundary_valid = exact and committed_boundary_valid(root, plan, existing)
    intent_observed = _intent_observation(
        root, plan, plan_ref, plan_file_sha256
    )
    planning_current, planning_defects = cas_status(root, plan, phase="planning")
    apply_current, apply_defects = cas_status(root, plan, phase="apply")
    materialization_status = _materialization_status(
        root, plan, planning_defects, apply_defects
    )
    selected_current = planning_current if phase == "planning" else apply_current
    selected_defects = planning_defects if phase == "planning" else apply_defects
    apply_path, apply_receipt, apply_receipt_status, apply_receipt_digest = (
        _apply_receipt(root, plan, plan_ref, plan_file_sha256)
    )
    no_effect_status, no_effect_receipt, no_effect_digest = load_no_effect_receipt(
        root, plan, plan_ref, plan_file_sha256
    )
    projection_healthy = _markdown_projection_matches(root, merge_state(existing))
    historical_complete = bool(
        exact and boundary_valid and apply_receipt_status == "current"
    )
    defects = list(selected_defects)
    if conflicting_events or (exact and not boundary_valid):
        status = "conflict"
        if effect_observed and not boundary_valid:
            defects.append("committed_boundary_invalid")
    elif no_effect_status == "current" and (
        effect_observed or intent_observed or apply_receipt_status != "missing"
    ):
        status = "conflict"
        defects.append("no_effect_receipt_conflicts_with_plan_activity")
    elif exact:
        if apply_receipt_status == "conflict":
            status = "conflict"
            defects.append("apply_receipt_conflict")
        elif apply_receipt_status == "current" and projection_healthy:
            status = "already_applied"
        else:
            status = "recovery_required"
            if apply_receipt_status == "missing":
                defects.append("receipt_missing")
            if not projection_healthy:
                defects.append("markdown_projection_repair_required")
    elif intent_observed and apply_receipt_status != "missing":
        status = "conflict"
        defects.append("apply_receipt_without_committed_batch")
    elif intent_observed:
        status = "recovery_required"
        defects.append("intent_without_committed_batch")
    elif apply_receipt_status != "missing":
        status = "conflict"
        defects.append("apply_receipt_without_committed_batch")
    elif no_effect_status == "current":
        status = "settled_no_effect"
    elif materialization_status == "partial":
        status = "materializing"
    elif selected_current:
        status = "ready"
    else:
        status = "stale"
    no_effect_eligible = (
        not effect_observed
        and not intent_observed
        and apply_receipt_status == "missing"
        and no_effect_status == "missing"
        and materialization_status in {"canonical_drift", "foreign"}
    )
    no_effect_ref = rel_path(
        root, no_effect_receipt_path(root, str(plan["plan_id"]))
    )
    return {
        "result_kind": "task_state_transition_verify_result",
        "schema_version": 1,
        "status": status,
        "verification_phase": phase,
        "plan_id": plan["plan_id"],
        "plan_ref": plan_ref,
        "plan_sha256": plan["plan_sha256"],
        "plan_file_sha256": plan_file_sha256,
        "receipt_ref": rel_path(root, apply_path),
        "receipt_status": apply_receipt_status,
        "receipt_content_sha256": apply_receipt["receipt_content_sha256"],
        "receipt_file_sha256": apply_receipt_digest,
        "no_effect_receipt_ref": no_effect_ref,
        "no_effect_receipt_content_sha256": (
            no_effect_receipt.get("receipt_content_sha256")
            if isinstance(no_effect_receipt, dict)
            else None
        ),
        "no_effect_receipt_file_sha256": no_effect_digest,
        "integrity_valid": True,
        "apply_eligible": status in {
            "ready",
            "already_applied",
            "recovery_required",
        },
        "idempotent_replay": status == "already_applied",
        "plan_effect_observed": effect_observed,
        "plan_intent_observed": intent_observed,
        "prestate_current": selected_current,
        "planning_prestate_current": planning_current,
        "apply_prestate_current": apply_current,
        "no_effect_eligible": no_effect_eligible,
        "dependency_materialization_status": materialization_status,
        "no_effect_verified": status == "settled_no_effect",
        "historical_completion_observed": historical_complete,
        "historical_transaction_complete": historical_complete,
        "current_projection_healthy": projection_healthy,
        "cas_defects": defects,
        "planning_cas_defects": planning_defects,
        "apply_cas_defects": apply_defects,
        "mutation_performed": False,
    }


def settle_transition_no_effect(
    root: Path,
    path_value: str | Path,
    *,
    at: str | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    plan_path, plan, plan_file_sha256 = load_transition_plan(root, path_value)
    plan_ref = rel_path(root, plan_path)
    created = False
    with index_lock(root):
        assert_no_pending_transition_intents(root)
        verification = verify_transition_plan_state(root, plan_ref, phase="apply")
        if verification["status"] == "settled_no_effect":
            receipt_path = no_effect_receipt_path(root, str(plan["plan_id"]))
        else:
            if not verification["no_effect_eligible"]:
                raise ValueError(
                    "Task-state transition plan is not eligible for no-effect settlement"
                )
            observation = _observation(root, plan, verification["apply_cas_defects"])
            receipt = build_no_effect_receipt(
                plan,
                plan_ref,
                plan_file_sha256,
                observation,
                settled_at=at or now_iso(),
            )
            receipt_path, created = publish_no_effect_receipt(root, receipt)
        final = verify_transition_plan_state(root, plan_ref, phase="apply")
        if final["status"] != "settled_no_effect":
            raise ValueError("Task-state no-effect receipt did not settle the plan")
    return {
        "result_kind": "task_state_transition_no_effect_result",
        "schema_version": 1,
        "status": "settled_no_effect" if created else "already_settled_no_effect",
        "plan_id": plan["plan_id"],
        "plan_ref": plan_ref,
        "plan_sha256": plan["plan_sha256"],
        "plan_file_sha256": plan_file_sha256,
        "receipt_ref": rel_path(root, receipt_path),
        "receipt_content_sha256": final["no_effect_receipt_content_sha256"],
        "receipt_file_sha256": final["no_effect_receipt_file_sha256"],
        "execution_result_binding": {
            "ref": rel_path(root, receipt_path),
            "sha256": final["no_effect_receipt_file_sha256"],
        },
        "no_effect_verified": True,
        "mutation_performed": created,
    }


__all__ = ["cas_status", "settle_transition_no_effect", "verify_transition_plan_state"]
