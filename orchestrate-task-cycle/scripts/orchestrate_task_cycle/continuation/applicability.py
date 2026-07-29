"""Compile deterministic adaptive-session stage applicability."""

from __future__ import annotations

from typing import Any

from ..result_contract.configuration import CANONICAL_LEDGER_STEPS
from .contracts import ContinuationContractError, digest, sha


APPLICABILITY_CONTRACT_ID = "stage_applicability_plan@v1"
PROFILE_ID = "adaptive_session_v1"
_CORE = frozenset(
    {
        "context",
        "authority",
        "repo_skill_adapter_scan",
        "acceptance",
        "route_plan",
        "governance",
        "result_contract",
        "ledger_append",
        "run",
        "qualitative_review",
        "loopback_audit",
        "validation_scope_finalize",
        "index_pre_validate",
        "validate",
        "derive",
        "index",
        "dashboard",
        "report",
    }
)
_FACT_FIELDS = {
    "needs_validation_set",
    "adapter_changed",
    "code_surface_changed",
    "user_visible_delta",
    "repeated_friction",
    "issue_context",
    "schema_impact",
    "tracked_delta",
}


def _decision(
    *,
    step: str,
    required: bool,
    reason: str,
    inputs_sha256: str,
) -> dict[str, str]:
    return {
        "step": step,
        "disposition": "required" if required else "not_applicable",
        "reason": reason,
        "inputs_sha256": inputs_sha256,
    }


def compile_applicability_plan(
    *,
    cycle_id: str,
    evidence_binding: dict[str, str],
    facts: dict[str, bool | None],
) -> dict[str, Any]:
    if (
        not isinstance(evidence_binding, dict)
        or set(evidence_binding) != {"ref", "sha256"}
    ):
        raise ContinuationContractError("applicability evidence binding is not closed")
    sha(evidence_binding.get("sha256"), "applicability evidence sha256")
    if set(facts) != _FACT_FIELDS:
        raise ContinuationContractError("applicability facts are not closed")
    if any(value not in {True, False, None} for value in facts.values()):
        raise ContinuationContractError(
            "applicability facts must be booleans or unknown"
        )
    inputs_sha256 = digest(
        {
            "cycle_id": cycle_id,
            "evidence_binding": evidence_binding,
            "facts": facts,
        }
    )
    rows: list[dict[str, str]] = []
    for step in CANONICAL_LEDGER_STEPS:
        if step in _CORE:
            rows.append(
                _decision(
                    step=step,
                    required=True,
                    reason="canonical_core",
                    inputs_sha256=inputs_sha256,
                )
            )
            continue
        predicate: bool | None
        reason = "predicate_false"
        if step in {"validation_scope_plan", "validation_set_plan", "validation_set_build"}:
            predicate = facts["needs_validation_set"]
            reason = "validation_set_required" if predicate else reason
        elif step == "repo_skill_adapter_validate":
            predicate = facts["adapter_changed"]
            reason = "adapter_changed" if predicate else reason
        elif step == "code_structure_audit":
            predicate = facts["code_surface_changed"]
            reason = "code_surface_changed" if predicate else reason
        elif step == "visible_increment":
            predicate = facts["user_visible_delta"]
            reason = "user_visible_delta" if predicate else reason
        elif step in {"repo_skill_gap_analysis", "cycle_efficiency_profile"}:
            predicate = facts["repeated_friction"]
            reason = "repeated_friction" if predicate else reason
        elif step == "issue":
            predicate = facts["issue_context"]
            reason = "issue_context" if predicate else reason
        elif step in {"schema_pre_derive", "schema_post_derive"}:
            predicate = facts["schema_impact"]
            reason = "schema_impact" if predicate else reason
        elif step == "commit":
            predicate = False
            reason = "deferred_to_batched_closeout"
        elif step == "closeout_commit":
            predicate = facts["tracked_delta"]
            reason = "tracked_cycle_delta" if predicate else reason
        else:  # Defensive compatibility for future canonical stages.
            predicate = None
        if predicate is None:
            rows.append(
                _decision(
                    step=step,
                    required=True,
                    reason="unknown_escalated_to_required",
                    inputs_sha256=inputs_sha256,
                )
            )
        else:
            rows.append(
                _decision(
                    step=step,
                    required=predicate,
                    reason=reason,
                    inputs_sha256=inputs_sha256,
                )
            )
    plan = {
        "contract_id": APPLICABILITY_CONTRACT_ID,
        "profile_id": PROFILE_ID,
        "cycle_id": cycle_id,
        "evidence_binding": dict(evidence_binding),
        "inputs_sha256": inputs_sha256,
        "decisions": rows,
    }
    plan["plan_sha256"] = digest(plan)
    return plan


__all__ = (
    "APPLICABILITY_CONTRACT_ID",
    "PROFILE_ID",
    "compile_applicability_plan",
)
