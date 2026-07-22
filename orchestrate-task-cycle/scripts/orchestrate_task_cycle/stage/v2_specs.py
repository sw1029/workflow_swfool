"""Closed v2 executor, provenance, and dependency classifications."""

from __future__ import annotations


EXECUTOR_KINDS = frozenset({"system", "deterministic", "owner", "hybrid"})
SYSTEM_STEPS = frozenset({"context", "route_plan", "result_contract", "ledger_append"})

DETERMINISTIC_TARGETS = frozenset(
    {
        "repo_skill_adapter_scan",
        "repo_skill_adapter_validate",
        "code_structure_audit",
        "repo_skill_gap_analysis",
        "cycle_efficiency_profile",
        "dashboard",
        "report",
    }
)
HYBRID_TARGETS = frozenset(
    {"qualitative_review", "loopback_audit", "derive", "validate"}
)


def executor_kind(target: str) -> str:
    if target in DETERMINISTIC_TARGETS:
        return "deterministic"
    if target in HYBRID_TARGETS:
        return "hybrid"
    return "owner"


# These are the only required result fields that a coordinator model may author.
# Every unlisted required field is source/owner material, never an implicit semantic
# fallback.
SEMANTIC_FIELDS: dict[str, tuple[str, ...]] = {
    "qualitative_review": (
        "review_status",
        "quality_verdict",
        "qualitative_findings",
        "direction_recommendations",
        "output_delta_status",
        "changed_vs_previous",
        "semantic_progress",
        "produced_domain_delta",
        "metadata_only",
        "effective_progress_kind",
        "progress_cap",
        "blocker_taxonomy_delta",
        "no_overclaim_flags",
    ),
    "loopback_audit": (
        "family_key",
        "changed_vs_previous",
        "semantic_progress",
        "same_family_micro_hardening_count",
        "recommended_disposition",
        "hard_stop_required",
        "evidence_class",
    ),
    "derive": (
        "selection_outcome",
        "pack_disposition",
        "loop_breaker_disposition",
        "progress_kind",
        "semantic_signature",
    ),
    "validate": (
        "validation_verdict",
        "progress_verdict",
        "blockers",
    ),
}


GIT_TARGETS = frozenset(
    {
        "repo_skill_adapter_scan",
        "validation_scope_plan",
        "governance",
        "repo_skill_adapter_validate",
        "code_structure_audit",
        "run",
        "qualitative_review",
        "visible_increment",
        "validation_scope_finalize",
        "commit",
        "dashboard",
        "report",
        "closeout_commit",
    }
)
TASK_STATE_TARGETS = frozenset(
    {
        "acceptance",
        "validation_set_plan",
        "validation_set_build",
        "repo_skill_gap_analysis",
        "index_pre_validate",
        "schema_pre_derive",
        "derive",
        "schema_post_derive",
        "index",
        "validate",
        "issue",
        "dashboard",
        "report",
    }
)
ADVICE_TARGETS = frozenset(
    {
        "governance",
        "validation_set_plan",
        "qualitative_review",
        "loopback_audit",
        "validation_set_build",
        "schema_pre_derive",
        "derive",
        "schema_post_derive",
        "index",
        "validate",
        "issue",
        "commit",
        "report",
        "closeout_commit",
    }
)
VALIDATION_TARGETS = frozenset(
    {"validation_set_plan", "validation_set_build", "validate", "report"}
)
SCHEMA_TARGETS = frozenset(
    {"schema_pre_derive", "derive", "schema_post_derive", "index", "validate", "report"}
)
ISSUE_TARGETS = frozenset({"validate", "issue", "dashboard", "report"})
LOG_TARGETS = frozenset(
    {"qualitative_review", "loopback_audit", "derive", "validate", "dashboard", "report"}
)
SESSION_TARGETS = frozenset(
    {"run", "qualitative_review", "loopback_audit", "validate", "report"}
)
GOAL_TARGETS = frozenset(
    {"qualitative_review", "loopback_audit", "derive", "validate", "report"}
)
SELECTION_TARGETS = frozenset({"derive", "index", "dashboard", "report"})


def dependency_selectors(target: str) -> tuple[str, ...]:
    # Keep effect-capable state in atomic selectors.  A composite `core`
    # fingerprint used to let an allowed task.md mutation hide an unrelated
    # concurrent cycle/authority change under the same changed selector.
    selectors = ["core", "task", "cycle", "authority", "pending_runs"]
    for name, targets in (
        ("git_head", GIT_TARGETS),
        ("git_worktree", GIT_TARGETS),
        ("task_state", TASK_STATE_TARGETS),
        ("advice", ADVICE_TARGETS),
        ("validation", VALIDATION_TARGETS),
        ("schema", SCHEMA_TARGETS),
        ("issue", ISSUE_TARGETS),
        ("agent_log", LOG_TARGETS),
        ("session", SESSION_TARGETS),
        ("goal", GOAL_TARGETS),
        ("selection", SELECTION_TARGETS),
    ):
        if target in targets:
            selectors.append(name)
    return tuple(selectors)


__all__ = [
    "DETERMINISTIC_TARGETS",
    "EXECUTOR_KINDS",
    "HYBRID_TARGETS",
    "GOAL_TARGETS",
    "SELECTION_TARGETS",
    "SEMANTIC_FIELDS",
    "SYSTEM_STEPS",
    "dependency_selectors",
    "executor_kind",
]
