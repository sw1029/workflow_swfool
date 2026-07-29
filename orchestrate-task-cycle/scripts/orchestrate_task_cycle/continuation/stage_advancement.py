"""Applicability-aware stage advancement for adaptive sessions."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from ..cycle_ledger import read_events
from ..ledger.support import initialization_path, rel_path
from ..stage.artifact_store import load_compiler_artifact
from ..stage.executor_registry import executor_spec
from ..stage.input_compilers import compile_routing, publish_owner_result
from ..stage.preparation_store import publish_preparation
from ..stage.service import _next_target, advance_stage, submit_stage
from .applicability import compile_applicability_plan
from .applicability_facts import derive_applicability_facts
from .contracts import ContinuationContractError
from .not_applicable import AUTO_SETTLE_TARGETS, settle_not_applicable


CLOSURE_SAFE_TARGETS = frozenset(
    {
        "qualitative_review",
        "loopback_audit",
        "validation_set_build",
        "visible_increment",
        "repo_skill_gap_analysis",
        "cycle_efficiency_profile",
        "validation_scope_finalize",
        "index_pre_validate",
        "validate",
        "issue",
        "schema_pre_derive",
        "derive",
        "schema_post_derive",
        "index",
        "dashboard",
        "report",
        "closeout_commit",
    }
)
_UNKNOWN_APPLICABILITY_FACTS: dict[str, bool | None] = {
    "needs_validation_set": None,
    "adapter_changed": None,
    "code_surface_changed": None,
    "user_visible_delta": None,
    "repeated_friction": None,
    "issue_context": None,
    "schema_impact": None,
    "tracked_delta": None,
}


def _applicability_input(
    root: Path,
    cycle_id: str,
    preparation: dict[str, Any] | None,
) -> tuple[dict[str, str], dict[str, bool | None]]:
    if isinstance(preparation, dict):
        context_binding = preparation.get("context_binding")
        machine_binding = preparation.get("machine_input_binding")
        if isinstance(context_binding, dict):
            context = load_compiler_artifact(
                root, cycle_id, context_binding, "context"
            )
            model = context.get("model_context")
            if not isinstance(model, dict):
                raise ContinuationContractError(
                    "applicability context lacks its sealed model projection"
                )
            binding = context_binding
        elif isinstance(machine_binding, dict):
            model = load_compiler_artifact(
                root, cycle_id, machine_binding, "machine_input"
            )
            binding = machine_binding
        else:
            raise ContinuationContractError(
                "applicability requires one sealed preparation input"
            )
        return (
            {"ref": str(binding["ref"]), "sha256": str(binding["sha256"])},
            derive_applicability_facts(model),
        )
    path = initialization_path(root, cycle_id)
    payload = path.read_bytes()
    return (
        {
            "ref": rel_path(root, path),
            "sha256": hashlib.sha256(payload).hexdigest(),
        },
        dict(_UNKNOWN_APPLICABILITY_FACTS),
    )


def _applicability_plan(
    root: Path,
    cycle_id: str,
    preparation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    evidence, facts = _applicability_input(root, cycle_id, preparation)
    return compile_applicability_plan(
        cycle_id=cycle_id,
        evidence_binding=evidence,
        facts=facts,
    )


def _applicability_decision(
    root: Path,
    cycle_id: str,
    target: str,
    preparation: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    plan = _applicability_plan(root, cycle_id, preparation)
    rows = [
        row for row in plan["decisions"] if row.get("step") == target
    ]
    if len(rows) != 1:
        raise ContinuationContractError(
            f"applicability plan lacks one decision for {target}"
        )
    return plan, rows[0]


def _settle_deferred_commit(
    root: Path,
    preparation: dict[str, Any],
    publication: dict[str, Any],
    plan: dict[str, Any],
    decision: dict[str, Any],
) -> dict[str, Any]:
    """Publish a compiler-bound non-effect receipt for the normal commit."""

    prep_ref = str(publication["preparation_ref"])
    prep_sha = str(publication["preparation_sha256"])
    owner = publish_owner_result(
        root,
        prep_ref,
        prep_sha,
        {
            "commit_role": "implementation",
            "commit_status": "not_applicable",
            "commit_skipped_reason": str(decision["reason"]),
            "evidence_paths": [str(plan["evidence_binding"]["ref"])],
        },
    )
    registered = executor_spec("commit")
    profiles = sorted(registered.allowed_routing_profiles)
    if not profiles:
        raise ContinuationContractError(
            "deferred commit lacks a registered routing profile"
        )
    routing = compile_routing(root, prep_ref, prep_sha, profiles[0])
    return submit_stage(
        root,
        preparation,
        apply=True,
        owner_result_ref=owner["owner_result_binding"]["ref"],
        owner_result_sha256=owner["owner_result_binding"]["sha256"],
        routing_ref=routing["routing_binding"]["ref"],
        routing_sha256=routing["routing_binding"]["sha256"],
    )


def advance(
    root: Path,
    workflow_mode: str,
    cycle_id: str,
    *,
    closure_only: bool,
) -> dict[str, Any]:
    """Advance through every evidence-proved optional owner stage."""

    auto_settled: set[str] = set()
    for _attempt in range(len(AUTO_SETTLE_TARGETS) + 3):
        next_target = _next_target(
            read_events(root, cycle_id),
            workflow_mode,
            3,
            root=root,
            cycle_id=cycle_id,
        )
        if closure_only and next_target not in {
            None,
            "commit",
            *CLOSURE_SAFE_TARGETS,
        }:
            return {
                "status": "block",
                "stop_reason": "closure_target_not_safe",
                "blocked_target": next_target,
                "closure_only": True,
                "applied": False,
            }
        if next_target == "commit":
            _plan, commit_decision = _applicability_decision(
                root, cycle_id, "commit"
            )
            if (
                closure_only
                and commit_decision.get("disposition") != "not_applicable"
            ):
                return {
                    "status": "block",
                    "stop_reason": "closure_target_not_safe",
                    "blocked_target": "commit",
                    "closure_only": True,
                    "applied": False,
                }
        result = advance_stage(
            root,
            cycle_id,
            workflow_mode=workflow_mode,
            max_steps=32,
            apply=True,
            preparation_schema_version=3,
        )
        preparation = result.get("preparation")
        if result.get("status") == "waiting" and isinstance(
            preparation, dict
        ):
            plan, decision = _applicability_decision(
                root,
                cycle_id,
                str(preparation.get("target") or ""),
                preparation,
            )
            publication = publish_preparation(root, preparation)
            if (
                preparation.get("target") == "commit"
                and decision.get("disposition") == "not_applicable"
            ):
                if "commit" in auto_settled:
                    raise ContinuationContractError(
                        "automatic N/A settlement made no stage progress"
                    )
                settlement = _settle_deferred_commit(
                    root, preparation, publication, plan, decision
                )
                if settlement.get("status") in {"block", "failed"}:
                    return {
                        "status": "block",
                        "stop_reason": (
                            settlement.get("stop_reason")
                            or "rejected_result"
                        ),
                        "stage_result": settlement,
                        "closure_only": closure_only,
                        "applied": bool(settlement.get("applied")),
                    }
                auto_settled.add("commit")
                continue
            if (
                preparation.get("target") in AUTO_SETTLE_TARGETS
                and decision.get("disposition") == "not_applicable"
            ):
                target = str(preparation["target"])
                if target in auto_settled:
                    raise ContinuationContractError(
                        "automatic N/A settlement made no stage progress"
                    )
                settlement = settle_not_applicable(
                    root, preparation, publication, plan, decision
                )
                if settlement.get("status") in {"block", "failed"}:
                    return {
                        "status": "block",
                        "stop_reason": (
                            settlement.get("stop_reason")
                            or "rejected_result"
                        ),
                        "stage_result": settlement,
                        "closure_only": closure_only,
                        "applied": bool(settlement.get("applied")),
                    }
                auto_settled.add(target)
                continue
            result = dict(result)
            result["preparation_publication"] = publication
        if closure_only:
            result = dict(result)
            result["closure_only"] = True
        return result
    raise ContinuationContractError(
        "automatic N/A settlement did not advance the workflow"
    )


__all__ = ("CLOSURE_SAFE_TARGETS", "advance")
