"""Shared task-pack vocabulary and action normalization."""
from __future__ import annotations

import re
import threading



PACK_STATUSES = {"active", "completed", "blocked", "terminal_blocked", "superseded"}
ITEM_STATUSES = {
    "planned",
    "promoted",
    "in_progress",
    "consumed",
    "inserted",
    "reordered",
    "skipped",
    "blocked",
    "terminal_blocked",
    "superseded",
}
VALIDATION_PROFILES = {"current_only", "affected_chain", "full_chain"}
PROGRESS_TARGETS = {"advanced", "safety_only", "no_progress", "regressed"}
PROGRESS_KINDS = {"goal_productive", "governance_only"}
OPEN_RESIDUAL_STATUSES = {"planned", "promoted", "in_progress", "inserted", "reordered", "blocked"}
PACK_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
ITEM_KIND_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
SHA256_PATTERN = re.compile(r"^(?:sha256:)?([0-9a-f]{64})$")
PROMOTION_VALIDATION_VERDICTS = {"complete", "pass", "passed"}
PROMOTION_TERMINAL_EXECUTION_STATUSES = {
    "blocked_no_execution",
    "complete",
    "completed",
    "no_execution",
    "not_applicable",
    "skipped",
    "success",
}
ISSUE_NOOP_STATUSES = {"not_applicable", "skipped"}
ISSUE_MUTATION_STATUSES = {"closed", "created", "open", "reopened", "resolved", "tracked", "updated"}
PACK_COHERENCE_VERSION = 1
PACK_COHERENCE_MUTATIONS = {
    "create",
    "promote",
    "insert",
    "reorder",
    "skip",
    "supersede",
    "terminal_block",
    "mark_consumed",
    "normalize_initial_selection_provenance",
    "replace",
}
PROMOTION_ORIGINS = {
    "predecessor_completion",
    "bootstrap_initial_selection",
    "authorized_initial_selection",
}
VERDICT_AXIS_STATUSES = {"pass", "fail", "partial", "blocked", "not_evaluated", "not_applicable", "conflicted"}
VERDICT_AXES = (
    "task_acceptance_verdict",
    "artifact_truth_verdict",
    "artifact_semantic_verdict",
    "pack_transition_verdict",
    "historical_index_verdict",
    "goal_readiness_verdict",
)
INITIAL_SELECTION_RECEIPT_VERSION = 1
CREATION_SNAPSHOT_CANONICALIZATION_VERSION = 1
AUTHORITY_RECEIPT_TEMPORALITIES = {
    "contemporaneous_selection_authority",
    "current_ratification",
    "retrospective_evidence_assessment",
}
AUTHORITY_RECEIPT_SOURCE_KINDS = {
    "explicit_current_user_instruction",
    "effective_authority_policy",
    "contemporaneous_authority_record",
}
CONTEMPORANEOUS_AUTHORITY_SOURCE_KINDS = {
    "explicit_current_user_instruction",
    "effective_authority_policy",
    "contemporaneous_authority_record",
}
_PACK_MUTATION_THREAD_LOCK = threading.RLock()
_CONTENT_ADDRESSED_WRITE_STATE = threading.local()
def normalize_action(action: str) -> str:
    normalized = action.strip().lower()
    mapping = {
        "insert_items": "insert",
        "insert_item": "insert",
        "reorder_items": "reorder",
        "skip_items": "skip",
        "exclude_items": "skip",
        "supersede_pack": "supersede",
        "terminal_blocked": "terminal_block",
        "terminal_block": "terminal_block",
        "create_pack": "create",
        "replace_pack": "replace",
        "promote_next_item": "promote",
        "normalize_initial_selection_provenance": "normalize_initial_selection_provenance",
    }
    return mapping.get(normalized, normalized)

