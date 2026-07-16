"""Migration schema constants and error type."""

TOOL_VERSION = "1.1.0"
PLAN_SCHEMA_VERSION = 2
MAPPING_SCHEMA_VERSION = 1
MANIFEST_SCHEMA_VERSION = 2
RECEIPT_SCHEMA_VERSION = 2
INDEX_FORMAT_VERSION = 2
INDEX_SCHEMA_VERSION = 1
MISSING_TOKEN = "__MISSING__"
INFER_TOKEN = "__INFER__"

EVENT_KINDS = {"upsert", "link"}
LIFECYCLE_STATUSES = {
    "active", "applied", "archived", "blocked", "candidate", "closed",
    "complete", "completed", "deferred", "deleted", "deprecated", "failed",
    "in_progress", "informational", "logged", "needs_review", "not_applicable",
    "obsolete", "open", "partial", "partially_resolved", "passed", "raw",
    "rejected", "resolved", "running", "skipped", "stale", "superseded",
    "terminal_blocked",
}
NON_ACTIVE_STATUSES = {
    "applied", "archived", "closed", "deleted", "deprecated", "obsolete",
    "rejected", "resolved", "superseded",
}
ARTIFACT_TYPES = {
    "task", "task_pack", "past_task", "candidate_task", "task_miss",
    "agent_log", "execution", "audit", "validation", "goal", "goal_prompt",
    "interview", "environment", "external_advice", "issue", "issue_resolution",
    "issue_map", "schema_contract", "schema_map",
}
CLASSIFICATIONS = {
    "accepted_current", "normalized_legacy", "mapped_legacy",
    "quarantined_historical", "blocked_unknown_or_future",
}
PROJECTION_IMPACTS = {"independent", "affected", "unknown"}
MIGRATION_EVENT_FIELD = "task_state_migration_event"
SEAL_KIND = "task_state_migration_seal"
ANCHOR_KIND = "task_state_migration_receipt_anchor"

class MigrationError(ValueError):
    """Fail-closed migration or sealed-reader error."""
