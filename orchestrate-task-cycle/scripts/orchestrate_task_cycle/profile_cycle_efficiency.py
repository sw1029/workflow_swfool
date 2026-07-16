"""Public facade for cycle-efficiency profiling."""

from .cycle_efficiency.analysis import analyze
from .cycle_efficiency.budgets import (
    COMMAND_SURFACE_RE,
    PROCESSED_CANDIDATE_THRESHOLD,
    RUN_DIR_THRESHOLD,
    VERSIONED_FAMILY_THRESHOLD,
    artifact_sprawl_budget,
    command_surface_budget,
)
from .cycle_efficiency.cli import main
from .cycle_efficiency.common import (
    CYCLE_ID_PATTERN,
    INDEPENDENT_EVIDENCE_STATUSES,
    OPAQUE_ID_MAX_LENGTH,
    TRACE_LABEL_RE,
    _axis_bound_independent_evidence,
    _independent_status,
    artifact_payload_identity,
    artifact_ref_identity,
    boolish,
    bounded_opaque_id,
    collect_events,
    current_cycle_events,
    cycle_groups,
    deep_get,
    execution_scope,
    family_scope,
    first_present,
    fresh_run_id,
    is_metadata_only,
    read_jsonl,
    read_text,
    same_execution_scope,
    same_family_scope,
    semantic_goal_movement,
    stable_scope_value,
)

__all__ = [
    "COMMAND_SURFACE_RE",
    "CYCLE_ID_PATTERN",
    "INDEPENDENT_EVIDENCE_STATUSES",
    "OPAQUE_ID_MAX_LENGTH",
    "PROCESSED_CANDIDATE_THRESHOLD",
    "RUN_DIR_THRESHOLD",
    "TRACE_LABEL_RE",
    "VERSIONED_FAMILY_THRESHOLD",
    "_axis_bound_independent_evidence",
    "_independent_status",
    "analyze",
    "artifact_payload_identity",
    "artifact_ref_identity",
    "artifact_sprawl_budget",
    "boolish",
    "bounded_opaque_id",
    "collect_events",
    "command_surface_budget",
    "current_cycle_events",
    "cycle_groups",
    "deep_get",
    "execution_scope",
    "family_scope",
    "first_present",
    "fresh_run_id",
    "is_metadata_only",
    "main",
    "read_jsonl",
    "read_text",
    "same_execution_scope",
    "same_family_scope",
    "semantic_goal_movement",
    "stable_scope_value",
]


if __name__ == "__main__":
    raise SystemExit(main())
