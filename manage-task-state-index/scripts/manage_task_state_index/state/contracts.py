"""Task-state event and lifecycle constants."""


try:
    import fcntl
except ImportError:  # pragma: no cover - Windows fallback keeps thread safety only.
    fcntl = None  # type: ignore[assignment]


PREFIXES = {
    "task": "task",
    "task_pack": "pack",
    "past_task": "past",
    "candidate_task": "cand",
    "task_miss": "miss",
    "agent_log": "log",
    "execution": "run",
    "audit": "audit",
    "validation": "val",
    "goal": "goal",
    "goal_prompt": "prompt",
    "interview": "int",
    "environment": "env",
    "external_advice": "adv",
    "schema_contract": "schema",
    "schema_map": "schema-map",
    "issue": "issue",
    "issue_resolution": "issue-res",
    "issue_map": "issue-map",
}

INDEX_FORMAT_VERSION = 2
INDEX_SCHEMA_VERSION = 1
SUPPORTED_EVENT_KINDS = {"upsert", "link"}
LIFECYCLE_STATUSES = {
    "active",
    "applied",
    "archived",
    "blocked",
    "candidate",
    "closed",
    "complete",
    "completed",
    "deferred",
    "deleted",
    "deprecated",
    "failed",
    "in_progress",
    "informational",
    "logged",
    "needs_review",
    "not_applicable",
    "obsolete",
    "open",
    "partial",
    "partially_resolved",
    "passed",
    "raw",
    "rejected",
    "resolved",
    "running",
    "skipped",
    "stale",
    "superseded",
    "terminal_blocked",
}
NON_ACTIVE_STATUSES = {
    "applied",
    "archived",
    "closed",
    "deleted",
    "deprecated",
    "obsolete",
    "rejected",
    "resolved",
    "superseded",
}
TASK_SCAN_PRESERVED_NONEXECUTABLE_STATUSES = {
    "complete",
    "completed",
}
