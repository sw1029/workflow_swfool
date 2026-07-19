"""Deterministic resolution-bundle builder and bounded task-doctor advance."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from manage_agent_authority.artifact_store import AUTHORIZATION_ROOT, register_grant
from manage_agent_authority.canonical import parse_time, write_immutable_json
from manage_agent_authority.evaluator import evaluate
from manage_agent_authority.lifecycle import reserve

from .authority_basis import materialization_item
from .common import WorkflowError, require, sha256_json, workspace_file
from .journal import load
from .lifecycle import status
from .resolution import resolve_all
from .task_transition_store import publish_immutable


SKILLS_ROOT = Path(__file__).resolve().parents[3]


def _binding(root: Path, value: Any, label: str) -> dict[str, str]:
    require(isinstance(value, dict) and set(value) == {"ref", "sha256"},
            "invalid_resolution_seed", f"{label} must contain ref and sha256")
    ref = value["ref"]
    digest = value["sha256"]
    require(isinstance(ref, str) and isinstance(digest, str),
            "invalid_resolution_seed", f"{label} binding is invalid")
    workspace_file(root, ref, digest, label)
    return {"ref": ref, "sha256": digest}


def _seed_map(
    root: Path, value: Any | None,
) -> dict[str, dict[str, str]]:
    if value is None:
        return {}
    require(isinstance(value, dict), "invalid_resolution_seed",
            "evidence map must be an object")
    return {
        str(operation_id): _binding(root, binding, f"evidence.{operation_id}")
        for operation_id, binding in value.items()
    }


def _live_resolution(
    root: Path, item: dict[str, Any], evidence: dict[str, str] | None,
) -> tuple[str, dict[str, str]]:
    resolution = item["resolution"]
    basis = item.get("workflow_basis")
    require(isinstance(basis, dict), "invalid_workflow_projection",
            "live authority item lacks workflow basis")
    if resolution == "source_approval_ready_for_grant":
        candidate = basis.get("source_approval")
        classification = "already_covered"
    elif resolution == "ready_to_reserve":
        raise WorkflowError(
            "advance_boundary",
            "authority decision is ready for JIT reservation",
            next_action="reserve_exact_authority",
        )
    elif resolution == "ready_to_resume":
        candidate = basis.get("reservation")
        classification = "ready_to_resume"
    else:
        raise WorkflowError(
            "advance_boundary",
            f"live authority resolution requires external routing: {resolution}",
            next_action=item.get("next_action", {}).get("code", "inspect_status"),
        )
    selected = evidence or candidate
    require(isinstance(selected, dict), "invalid_workflow_projection",
            "live authority evidence is unavailable")
    projected = {key: selected.get(key) for key in ("ref", "sha256")}
    return classification, _binding(root, projected, "live authority evidence")


def build_resolution_bundle(
    root: Path, workflow_id: str, *, evidence_map: Any | None = None,
) -> dict[str, Any]:
    """Build the canonical bundle from live status plus a compact evidence map."""

    _, _, journal = load(root, workflow_id)
    projection = status(root, workflow_id)
    seeds = _seed_map(root, evidence_map)
    resolutions = []
    if (
        projection.get("workflow_state") == "awaiting_approval"
        and projection.get("should_prompt") is True
    ):
        source = "needs_user_approval"
        interaction = True
        items = projection["approval_bundle"]["items"]
        expected = {item["operation_id"] for item in items}
        require(set(seeds) == expected, "incomplete_resolution_seed",
                "approval evidence map must cover the exact current review scope")
        for item in items:
            binding = seeds[item["operation_id"]]
            resolutions.append({
                "operation_id": item["operation_id"],
                "classification": "already_covered",
                "evidence_ref": binding["ref"],
                "evidence_sha256": binding["sha256"],
            })
    else:
        live = projection.get("live_authority_progress", {}).get("items")
        require(isinstance(live, list) and live, "no_resolution_bundle",
                "current workflow state has no deterministic resolution bundle",
                next_action=projection.get("next_action", "inspect_status"))
        source = projection.get("authority_resolution_source")
        require(source in {"needs_user_approval", "already_covered"},
                "invalid_workflow_projection",
                "live authority projection lacks its source classification")
        interaction = False
        expected = {item["operation_id"] for item in live}
        require(set(seeds) <= expected, "invalid_resolution_seed",
                "evidence map contains operations outside the live bundle")
        for projected in live:
            operation_id = projected["operation_id"]
            classification, binding = _live_resolution(
                root, projected, seeds.get(operation_id)
            )
            resolutions.append({
                "operation_id": operation_id,
                "classification": classification,
                "evidence_ref": binding["ref"],
                "evidence_sha256": binding["sha256"],
            })
    body = {
        "kind": "task_doctor_authority_resolution_bundle",
        "schema_version": 1,
        "workflow_id": workflow_id,
        "plan_sha256": journal["plan_sha256"],
        "from_classification": source,
        "user_interaction": interaction,
        "resolutions": resolutions,
    }
    return body


def publish_resolution_bundle(
    root: Path, bundle: dict[str, Any],
) -> dict[str, Any]:
    digest = sha256_json(bundle)
    ref = f".task/task_doctor/bundles/tdb-{digest[:20]}.json"
    created, file_digest = publish_immutable(root, ref, bundle)
    return {"bundle_ref": ref, "bundle_sha256": file_digest,
            "created": created, "replayed": not created}


def _jit_time(recipe: dict[str, Any], at: str):
    try:
        actual = parse_time(at, "advance.at")
        if "reserved_at" in recipe:
            expected = parse_time(recipe["reserved_at"], "reservation.reserved_at")
            require(actual == expected, "jit_reservation_window_mismatch",
                    "legacy v1 reservation requires its exact planned time")
        else:
            start = parse_time(recipe["not_before"], "reservation.not_before")
            end = parse_time(recipe["expires_at"], "reservation.expires_at")
            require(start <= actual < end, "jit_reservation_window_mismatch",
                    "advance.at falls outside the v2 JIT reservation window")
        return actual.isoformat()
    except SystemExit as error:
        raise WorkflowError("invalid_advance_time", str(error)) from error


def _jit_materialize(
    root: Path, workflow_id: str, operation_id: str, at: str,
) -> dict[str, Any]:
    _, _, journal = load(root, workflow_id)
    item = next(
        row for row in journal["plan"]["operations"]
        if row["operation_id"] == operation_id
    )
    recipe = materialization_item(item)
    require(recipe["applicability"] == "required", "invalid_workflow_projection",
            "JIT materialization requires a governed operation")
    source = recipe["snapshot_sources"]["source_approval"]
    require(isinstance(source, dict), "awaiting_exact_approval",
            "JIT materialization cannot invent a missing source approval",
            user_action_required=True, next_action="supply_exact_source_snapshot")
    actual = _jit_time(recipe["reserve"], at)
    grant_recipe = recipe["register_grant_recipe"]
    grant_result = register_grant(root, grant_recipe, parent_id=None)
    decision = evaluate(
        root, recipe["request"], recipe["evaluate"]["evaluation_context"],
        evaluated_at=recipe["evaluate"]["evaluated_at"], skills_root=SKILLS_ROOT,
    )
    require(decision["decision"] == "allowed", "authority_not_settled",
            "JIT authority evaluation did not produce an allowed decision",
            next_action="inspect_authority_decision",
            details={"decision": decision["decision"],
                     "reason_codes": decision["reason_codes"]})
    decision_path = (
        root / AUTHORIZATION_ROOT / "decisions" / f"{decision['decision_id']}.json"
    )
    decision_digest = write_immutable_json(
        decision_path, decision, "task-doctor authority decision"
    )
    reserved = reserve(
        root,
        decision_path.relative_to(root).as_posix(),
        decision_digest,
        reserved_at=actual,
        idempotency_key=recipe["reserve"]["idempotency_key"],
        skills_root=SKILLS_ROOT,
    )
    return {
        "operation_id": operation_id,
        "grant": grant_result,
        "decision": {
            "ref": decision_path.relative_to(root).as_posix(),
            "sha256": decision_digest,
            "decision_id": decision["decision_id"],
        },
        "reservation": {
            "ref": reserved["reservation_ref"],
            "sha256": reserved["reservation_sha256"],
        },
        "reserved_at": actual,
    }


def _route(projection: dict[str, Any]) -> dict[str, Any]:
    state = projection.get("workflow_state")
    if state == "complete":
        reason = "complete"
    elif state == "awaiting_approval":
        reason = "awaiting_exact_approval"
    elif state == "authorized":
        reason = "awaiting_owner_result"
    elif state == "applying":
        reason = "awaiting_owner_result"
    elif state == "authority_materialization":
        reason = "awaiting_authority_materialization"
    elif state == "recovery_required":
        reason = "awaiting_effect_settlement"
    elif state == "replanning_required":
        reason = "stale_plan"
    else:
        reason = "blocked_transition"
    result = copy.deepcopy(projection)
    result.update(stop_reason=reason)
    return result


def advance_workflow(
    root: Path, workflow_id: str, *, max_steps: int = 8,
    apply_changes: bool = False, evidence_map: Any | None = None,
    at: str | None = None,
) -> dict[str, Any]:
    require(isinstance(max_steps, int) and 1 <= max_steps <= 32,
            "invalid_step_budget", "max_steps must be between 1 and 32")
    require(not apply_changes or isinstance(at, str), "invalid_advance_time",
            "mutating advance requires an exact --at timestamp")
    seen: set[str] = set()
    steps = []
    for _ in range(max_steps):
        projection = status(root, workflow_id)
        fingerprint = sha256_json({
            "revision": projection["revision"],
            "workflow_state": projection["workflow_state"],
            "classification": projection["classification"],
            "next_action": projection["next_action"],
            "next_operation": projection.get("next_operation"),
        })
        if fingerprint in seen:
            return {**_route(projection), "stop_reason": "no_progress_replay",
                    "steps": steps}
        seen.add(fingerprint)
        steps.append({"revision": projection["revision"],
                      "fingerprint": fingerprint,
                      "next_action": projection["next_action"]})
        if not apply_changes:
            return {**_route(projection), "steps": steps, "dry_run": True}
        live = projection.get("live_authority_progress", {}).get("items", [])
        jit = next(
            (
                item for item in live
                if item.get("resolution") in {
                    "source_approval_ready_for_grant", "ready_to_reserve"
                }
            ),
            None,
        )
        if jit is not None:
            assert at is not None
            steps[-1]["jit_authority"] = _jit_materialize(
                root, workflow_id, jit["operation_id"], at
            )
            continue
        try:
            bundle = build_resolution_bundle(
                root, workflow_id, evidence_map=evidence_map
            )
        except WorkflowError as error:
            if error.code in {"no_resolution_bundle", "advance_boundary"}:
                return {**_route(projection), "steps": steps, "dry_run": False}
            raise
        published = publish_resolution_bundle(root, bundle)
        resolved = resolve_all(
            root, workflow_id, published["bundle_ref"],
            published["bundle_sha256"], projection["revision"],
        )
        steps[-1]["resolution_bundle"] = published
        steps[-1]["result_revision"] = resolved["revision"]
        evidence_map = None
    projection = status(root, workflow_id)
    return {**_route(projection), "stop_reason": "step_budget_exhausted",
            "steps": steps, "dry_run": not apply_changes}


__all__ = [
    "advance_workflow", "build_resolution_bundle", "publish_resolution_bundle",
]
