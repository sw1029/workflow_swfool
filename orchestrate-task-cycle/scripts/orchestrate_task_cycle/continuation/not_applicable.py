"""Compiler-owned receipts for evidence-proved optional owner stages."""

from __future__ import annotations

from typing import Any

from ..stage.executor_registry import executor_spec
from ..stage.input_compilers import compile_routing, publish_owner_result
from ..stage.service import submit_stage
from .contracts import ContinuationContractError


AUTO_SETTLE_TARGETS = frozenset(
    {
        "validation_set_build",
        "visible_increment",
        "issue",
        "schema_pre_derive",
        "schema_post_derive",
        "closeout_commit",
    }
)


def _owner_result(
    preparation: dict[str, Any],
    plan: dict[str, Any],
    decision: dict[str, Any],
) -> dict[str, Any]:
    target = str(preparation["target"])
    reason = str(decision["reason"])
    evidence_ref = str(plan["evidence_binding"]["ref"])
    task_id = str((preparation.get("derived_values") or {}).get("task_id") or "")
    identity = str(plan["plan_sha256"])[:24]
    if target == "validation_set_build":
        return {
            "validation_set_status": "not_applicable",
            "validation_set_not_applicable_reason": reason,
            "evidence_paths": [],
        }
    if target == "visible_increment":
        return {
            "status": "recorded",
            "summary": "No user-visible delta was evidenced for this cycle.",
            "delta_types": ["none"],
            "changed_files": [],
            "artifacts": [],
            "not_validation_evidence": True,
            "blockers": [],
            "evidence_paths": [evidence_ref],
        }
    if target == "issue":
        return {
            "issue_packet_id": f"issue-na-{identity}",
            "issue_status": "not_applicable",
            "issue_ids": [],
            "issue_provenance": {
                "source_task_id": task_id,
                "validation_report_path": evidence_ref,
            },
            "issue_skipped_reason": reason,
            "blockers": [],
            "evidence_paths": [evidence_ref],
        }
    if target in {"schema_pre_derive", "schema_post_derive"}:
        return {
            "schema_status": "not_applicable",
            "schema_skipped_reason": reason,
            "evidence_paths": [],
        }
    if target == "closeout_commit":
        return {
            "commit_role": "closeout",
            "commit_status": "not_applicable",
            "commit_skipped_reason": reason,
            "tracked_artifacts": [],
            "evidence_paths": [evidence_ref],
        }
    raise ContinuationContractError(
        f"optional target {target} lacks a compiler-owned N/A receipt"
    )


def settle_not_applicable(
    root: Any,
    preparation: dict[str, Any],
    publication: dict[str, Any],
    plan: dict[str, Any],
    decision: dict[str, Any],
) -> dict[str, Any]:
    """Submit one target-valid N/A result bound to its exact fact evidence."""

    target = str(preparation["target"])
    if target not in AUTO_SETTLE_TARGETS:
        raise ContinuationContractError(
            f"optional target {target} is not safe for automatic settlement"
        )
    prep_ref = str(publication["preparation_ref"])
    prep_sha = str(publication["preparation_sha256"])
    owner = publish_owner_result(
        root,
        prep_ref,
        prep_sha,
        _owner_result(preparation, plan, decision),
    )
    registered = executor_spec(target)
    routing = None
    if registered.routing_required:
        profiles = sorted(registered.allowed_routing_profiles)
        if not profiles:
            raise ContinuationContractError(
                f"optional target {target} lacks a routing profile"
            )
        routing = compile_routing(root, prep_ref, prep_sha, profiles[0])
    return submit_stage(
        root,
        preparation,
        apply=True,
        owner_result_ref=owner["owner_result_binding"]["ref"],
        owner_result_sha256=owner["owner_result_binding"]["sha256"],
        routing_ref=(
            routing["routing_binding"]["ref"] if routing is not None else None
        ),
        routing_sha256=(
            routing["routing_binding"]["sha256"] if routing is not None else None
        ),
    )


__all__ = ("AUTO_SETTLE_TARGETS", "settle_not_applicable")
