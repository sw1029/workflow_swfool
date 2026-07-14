from __future__ import annotations

import re


# Stable protocol vocabulary. Repository-specific axes, artifact layouts,
# metrics, retry rules, and semantic budgets must arrive in a policy packet.
PROGRESS_RE = re.compile(
    r"progress[_ -]?verdict\s*[:|-]\s*(advanced|safety_only|no_progress|regressed)",
    re.IGNORECASE,
)
ISSUE_RE = re.compile(r"(\.issue/[^\s)>\]]+|issue-[0-9A-Za-z_.-]+|#[0-9]+)")
BLOCKER_RE = re.compile(r"(?:blocker|blocking finding)\s*[:|-]\s*(.+)", re.IGNORECASE)
INPUT_KIND_RE = re.compile(
    r"(?:new_input_kind|required_new_input_kind|input kind|input_kind)\s*[:=]\s*([A-Za-z0-9_.:-]+)",
    re.IGNORECASE,
)
PROVIDER_REQUEST_COUNT_RE = re.compile(
    r"\bprovider_request_count\s*[=:]\s*([0-9]+)\b",
    re.IGNORECASE,
)
FAILURE_CLASS_RE = re.compile(
    r"\bfailure_class\s*[=:]\s*([A-Za-z0-9_.:-]+)\b",
    re.IGNORECASE,
)
SIGNATURE_TOKEN_RE = re.compile(r"[^a-z0-9_.:/#-]+", re.IGNORECASE)
VOLATILE_SIGNATURE_RE = re.compile(
    r"(?:(?:20\d{2}[-_.]?\d{2}[-_.]?\d{2}(?:[-_.]?\d{2}[-_.]?\d{2}[-_.]?\d{2})?)|"
    r"(?:\b\d{8,14}\b)|(?:\b[0-9a-f]{7,40}\b)|(?:\bcycle[-_.]?[0-9a-z_.-]+\b)|"
    r"(?:\brun[-_.]?[0-9a-z_.-]+\b)|(?:\btask[-_.]?\d+[0-9a-z_.-]*\b)|"
    r"(?:\bafter[-_.][a-z0-9_.-]+\b)|(?:[-_.]?v\d+\b))",
    re.IGNORECASE,
)
FACET_SUFFIX_RE = re.compile(
    r"([_.:/|-])(?:v\d+|ver\d+|version\d+|facet|variant|case|mode|phase|stage|"
    r"schema|contract|gate|preflight|handoff|packet|report|check|review)$",
    re.IGNORECASE,
)

REGISTRY_REL_PATH = ".task/dedup_symbol_registry.jsonl"
DISPOSITION_UNIVERSE = {
    "goal_productive",
    "consolidation",
    "terminal_blocked",
    "user_escalation",
}
SAFETY_VALVES = {"terminal_blocked", "user_escalation"}

# Compatibility exports intentionally contain no repository policy. Callers
# that require these catalogs or budgets must supply them explicitly.
SEMANTIC_AXIS_PATTERNS: tuple[tuple[str, str], ...] = ()
ROOT_AXIS_PATTERNS: tuple[tuple[str, str], ...] = ()
QUALITY_DELTA_KEYS: tuple[str, ...] = ()
INPUT_MANIFEST_NAMES: set[str] = set()
PATH_FIELD_NAMES: set[str] = set()
INPUT_PATH_FIELD_NAMES: set[str] = set()
TARGET_UNIT_KEYS: set[str] = set()
COMMAND_SURFACE_RE: re.Pattern[str] | None = None
DETECTION_TERMS_RE: re.Pattern[str] | None = None
CORRECTION_TERMS_RE: re.Pattern[str] | None = None
TRANSIENT_PROVIDER_FAILURE_CLASSES: set[str] = set()
PERMANENT_PROVIDER_FAILURE_CLASSES: set[str] = set()
MITIGATION_REQUIREMENTS: dict[str, set[str]] = {}
CONSOLIDATION_STREAK_CAP: int | None = None
DETECTION_ONLY_STREAK_CAP: int | None = None
TERMINAL_QUIESCENCE_STREAK_DEFAULT: int | None = None
TERMINAL_ESCALATION_STREAK_DEFAULT: int | None = None

PASS_STATUS_VALUES = {
    "pass",
    "passed",
    "ok",
    "valid",
    "success",
    "succeeded",
    "complete",
    "completed",
    "true",
}
FAIL_STATUS_VALUES = {"fail", "failed", "invalid", "error", "blocked", "false"}
VALIDATOR_RESULT_KEYS = {
    "pass",
    "passed",
    "ok",
    "valid",
    "success",
    "succeeded",
    "semantic_progress",
    "result",
    "status",
    "validates",
}
VALIDATOR_CHILD_KEYS = {
    "checks",
    "sub_checks",
    "sub_results",
    "subresults",
    "results",
    "validators",
    "validations",
    "assertions",
    "items",
    "embedded_results",
}
POPULATION_COUNT_KEYS = {
    "population_count",
    "declared_population_count",
    "target_count",
    "expected_count",
    "total_count",
    "candidate_count",
    "declared_count",
}
INSPECTED_COUNT_KEYS = {
    "checked_count",
    "validated_count",
    "inspected_count",
    "reviewed_count",
    "actual_count",
    "covered_count",
    "processed_count",
}
