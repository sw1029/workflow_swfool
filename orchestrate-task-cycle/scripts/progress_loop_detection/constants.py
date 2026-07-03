from __future__ import annotations

import re

PROGRESS_RE = re.compile(r"progress[_ -]?verdict\s*[:|-]\s*(advanced|safety_only|no_progress|regressed)", re.IGNORECASE)
ISSUE_RE = re.compile(r"(\.issue/[^\s)>\]]+|issue-[0-9A-Za-z_.-]+|#[0-9]+)")
BLOCKER_RE = re.compile(r"(?:blocker|blocking finding|남은 blocker)\s*[:|-]\s*(.+)", re.IGNORECASE)
INPUT_KIND_RE = re.compile(r"(?:new_input_kind|required_new_input_kind|input kind|input_kind)\s*[:=]\s*([A-Za-z0-9_.:-]+)", re.IGNORECASE)
PROVIDER_REQUEST_COUNT_RE = re.compile(r"\bprovider_request_count\s*[=:]\s*([0-9]+)\b", re.IGNORECASE)
FAILURE_CLASS_RE = re.compile(r"\bfailure_class\s*[=:]\s*([A-Za-z0-9_.:-]+)\b", re.IGNORECASE)
COMMAND_SURFACE_RE = re.compile(
    r"\b(?:build|validate|run|preflight)-[A-Za-z0-9_.:-]*[-_]v\d+[A-Za-z0-9_.:-]*"
    r"(?:contract|handoff|packet|gate|preflight|check|locator|resolution|recovery)?[A-Za-z0-9_.:-]*",
    re.IGNORECASE,
)
SIGNATURE_TOKEN_RE = re.compile(r"[^a-z0-9가-힣_.:/#-]+", re.IGNORECASE)
VOLATILE_SIGNATURE_RE = re.compile(
    r"(?:(?:20\d{2}[-_.]?\d{2}[-_.]?\d{2}(?:[-_.]?\d{2}[-_.]?\d{2}[-_.]?\d{2})?)|"
    r"(?:\b\d{8,14}\b)|(?:\b[0-9a-f]{7,40}\b)|(?:\bcycle[-_.]?[0-9a-z_.-]+\b)|"
    r"(?:\brun[-_.]?[0-9a-z_.-]+\b)|(?:\btask[-_.]?\d+[0-9a-z_.-]*\b)|"
    r"(?:\bafter[-_.][a-z0-9_.-]+\b)|(?:[-_.]?v\d+\b))",
    re.IGNORECASE,
)

SEMANTIC_AXIS_PATTERNS: tuple[tuple[str, str], ...] = (
    ("hash_reconcile", r"hash|digest|checksum|reconcile|rename|renam"),
    ("evidence_anchor", r"evidence[-_ ]?anchor|anchor|source[-_ ]?backed|source[-_ ]?evidence"),
    ("provider_terminal", r"provider|runtime|dispatch|live[-_ ]?provider|api|external[-_ ]?service|provider[-_ ]?terminal|runtime[-_ ]?terminal"),
    ("task_state_digest", r"task[-_ ]?state|index|candidate|task[_-]?miss|past[_-]?task|ledger"),
    ("oom_rebuild", r"oom|memory|rebuild|cache"),
    ("validation_set", r"validation[-_ ]?set|oracle|split|leakage|holdout|gold"),
    ("quality_review", r"quality|review|semantic[-_ ]?quality|reviewable[-_ ]?output"),
    ("kg_core", r"\bkg\b|knowledge[-_ ]?graph|graph|entity|relation"),
    ("claim_rights", r"claim|rights|policy|license|zkp|commitment"),
)

ROOT_AXIS_PATTERNS: tuple[tuple[str, str], ...] = (
    (
        "source_to_llm_output_execution",
        r"openai|provider|credential|dispatch|llm|api|source[-_ ]?backed|"
        r"provider[-_ ]?neutral.*(?:kg|validation[-_ ]?set|oracle|quality)",
    ),
    ("validation_oracle_quality", r"validation[-_ ]?set|oracle|split|leakage|holdout|quality[-_ ]?review"),
    ("kg_evidence_anchor", r"\bkg\b|knowledge[-_ ]?graph|evidence[-_ ]?anchor|preimage|source[-_ ]?locator|same[-_ ]?preimage"),
    ("task_state_lifecycle", r"task[-_ ]?state|index|candidate|task[_-]?miss|past[_-]?task|ledger|sealed"),
    ("claim_rights_commitment", r"claim|rights|policy|license|zkp|commitment"),
)
REGISTRY_REL_PATH = ".task/dedup_symbol_registry.jsonl"
DISPOSITION_UNIVERSE = {"goal_productive", "consolidation", "terminal_blocked", "user_escalation"}
SAFETY_VALVES = {"terminal_blocked", "user_escalation"}
CONSOLIDATION_STREAK_CAP = 2
QUALITY_DELTA_KEYS = (
    "event_named_ratio",
    "proper_noun_character_ratio",
    "coreference_resolved_ratio",
    "causal_edge_count",
    "windows_covered",
)
KG_NODE_EDGE_FILES = {"kg_nodes.jsonl", "kg_edges.jsonl"}
INPUT_MANIFEST_NAMES = {"input_manifest.json", "hash_summary.json"}
PATH_FIELD_NAMES = {
    "artifact_path",
    "artifact_paths",
    "artifacts",
    "changed_files",
    "command_log_paths",
    "evidence_path",
    "evidence_paths",
    "generated_artifacts",
    "input_artifact_paths",
    "input_manifest_path",
    "input_manifest_paths",
    "output_artifact_paths",
    "output_layer_path",
    "output_layer_paths",
    "processed_output_dir",
    "processed_output_path",
    "processed_candidate_dir",
    "run_artifact_dir",
    "task_local_artifacts_dir",
}
INPUT_PATH_FIELD_NAMES = {
    "input_artifact_paths",
    "input_manifest_path",
    "input_manifest_paths",
    "hash_summary_path",
    "hash_summary_paths",
    "manifest_path",
    "source_manifest_path",
    "supplied_input_artifact_paths",
}
TARGET_UNIT_KEYS = {
    "chunk_id",
    "chunk_ids",
    "document_id",
    "document_ids",
    "edge_id",
    "edge_ids",
    "evidence_id",
    "evidence_ids",
    "node_id",
    "node_ids",
    "preimage_id",
    "preimage_ids",
    "row_id",
    "row_ids",
    "source_window_id",
    "source_window_ids",
    "target_id",
    "target_ids",
    "target_unit_id",
    "target_unit_ids",
    "work_id",
    "work_ids",
}
NODE_ID_KEYS = ("id", "node_id", "entity_id", "canonical_id")
EDGE_ID_KEYS = ("id", "edge_id", "relation_id")
EDGE_ENDPOINT_KEYS = ("source", "source_id", "from", "target", "target_id", "to", "type", "relation", "predicate")
DETECTION_ONLY_STREAK_CAP = 2
TERMINAL_QUIESCENCE_STREAK_DEFAULT = 2
TERMINAL_ESCALATION_STREAK_DEFAULT = 2
FACET_SUFFIX_RE = re.compile(
    r"([_.:/|-])(?:v\d+|ver\d+|version\d+|facet|variant|case|mode|phase|stage|"
    r"vocab|pov|timing|typing|schema|contract|gate|metric|oracle|validator|lineage|"
    r"coverage|preflight|handoff|packet|dashboard|report|field|scalar|check|review|surface)$",
    re.IGNORECASE,
)
DETECTION_TERMS_RE = re.compile(
    r"(validator|validation|oracle|metric|gate|contract|check|dashboard|lineage|gap[-_ ]?report|"
    r"coverage[-_ ]?report|instrumentation|measurement)",
    re.IGNORECASE,
)
CORRECTION_TERMS_RE = re.compile(
    r"(producer|transform|prompt|resolver|resolution|extract|extraction|generate|generation|"
    r"repair|fix|implementation|run|primary[-_ ]?output|source[-_ ]?backed)",
    re.IGNORECASE,
)
PASS_STATUS_VALUES = {"pass", "passed", "ok", "valid", "success", "succeeded", "complete", "completed", "true"}
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

TRANSIENT_PROVIDER_FAILURE_CLASSES = {
    "empty",
    "parse",
    "parse_error",
    "parsing",
    "malformed",
    "rate_limit",
    "timeout",
    "transient",
    "incomplete",
}
PERMANENT_PROVIDER_FAILURE_CLASSES = {"auth", "permanent", "policy", "forbidden", "invalid_request"}
MITIGATION_REQUIREMENTS: dict[str, set[str]] = {
    "empty": {"structured_output"},
    "parse": {"structured_output"},
    "parse_error": {"structured_output"},
    "parsing": {"structured_output"},
    "malformed": {"structured_output"},
    "timeout": {"window_reduce", "timeout_budget_increase", "backoff_retry>=3", "model_fallback"},
    "transient": {"window_reduce", "timeout_budget_increase", "backoff_retry>=3", "model_fallback"},
    "rate_limit": {"backoff_retry>=3", "model_fallback"},
    "incomplete": {"structured_output", "window_reduce"},
}
