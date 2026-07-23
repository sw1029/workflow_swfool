from __future__ import annotations

import re


DEFAULT_STEPS = [
    "context",
    "authority",
    "repo_skill_adapter_scan",
    "acceptance",
    "route_plan",
    "validation_scope_plan",
    "validation_set_plan",
    "governance",
    "result_contract",
    "repo_skill_adapter_validate",
    "ledger_append",
    "code_structure_audit",
    "run",
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
    "commit",
    "dashboard",
    "report",
    "closeout_commit",
]

CANONICAL_STEPS = set(DEFAULT_STEPS)

LEDGER_FORMAT_VERSION = 1
COMPACT_STAGE_EVENT_FORMAT_VERSION = 2
SUPPORTED_LEDGER_FORMAT_VERSIONS = {
    0,
    LEDGER_FORMAT_VERSION,
    COMPACT_STAGE_EVENT_FORMAT_VERSION,
}
CURRENT_STAGE_PROJECTION_VERSION = 2
STAGE_COMPILER_PROTOCOL_VERSION = 2
STAGE_PREPARATION_SCHEMA_VERSION = 3
SUPPORTED_STAGE_COMPILER_PROTOCOL_VERSIONS = {1, STAGE_COMPILER_PROTOCOL_VERSION}
COMPILER_FIRST_WORKFLOW_CONTRACT_PROFILE = "compiler_first_enforced_v1"
COMPILED_STAGE_RESULT_EVENT_KIND = "compiled_stage_result_ref"
COMPILED_SYSTEM_EVENT_KIND = "compiled_system_event_ref"
COMPILED_STAGE_OBSERVATION_EVENT_KIND = "compiled_stage_observation_ref"
COMPILED_TERMINAL_LIFECYCLE_EVENT_KIND = "compiled_terminal_lifecycle_ref"
TERMINAL_LATCH_KEY_VERSION = 2
CYCLE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
EVENT_ID_PATTERN = re.compile(r"^[^\x00-\x20/\\]{1,255}$")

FINALIZATION_SCHEMA_VERSION = 1
FINAL_CANDIDATE_KIND = "cycle_final_candidate"
FINALIZATION_SNAPSHOT_KIND = "cycle_finalization_snapshot"
FINALIZATION_RECEIPT_KIND = "cycle_finalization_receipt"
FINALIZATION_POINTER_KIND = "cycle_finalization_pointer"
VERDICT_AXES = (
    "task_acceptance_verdict",
    "artifact_truth_verdict",
    "artifact_semantic_verdict",
    "pack_transition_verdict",
    "historical_index_verdict",
    "goal_readiness_verdict",
)
VERDICT_AXIS_STATUSES = {
    "pass",
    "fail",
    "partial",
    "blocked",
    "not_evaluated",
    "not_applicable",
    "conflicted",
}
DURABLE_STATE_MODES = {"complete_projection", "typed_operations"}
DURABLE_OPERATION_TYPES = {"append_projection", "replace_projection"}
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
SENSITIVE_DURABLE_KEYS = {
    "character_count",
    "char_count",
    "direct_quote",
    "locator",
    "message",
    "offset",
    "original_title",
    "quote",
    "quoted_text",
    "raw_text",
    "source_text",
    "text",
    "text_span",
    "title",
}
SENSITIVE_DURABLE_KEY_PARTS = (
    "character_count",
    "char_count",
    "direct_quote",
    "line_number",
    "line_start",
    "line_end",
    "locator",
    "offset",
    "original_title",
    "quoted_text",
    "raw_text",
    "source_text",
    "text_span",
)

MIN_FIELDS = [
    "format_version",
    "cycle_id",
    "event_id",
    "step",
    "status",
    "reason",
    "task_id",
    "completed_task_id",
    "next_task_id",
    "changed_files",
    "artifacts",
    "artifact_refs",
    "unchanged_refs",
    "validation_verdict",
    "progress_verdict",
    "blockers",
    "code_structure_audit",
    "qualitative_review",
    "anti_loop_progress_gate",
    "validation_set",
    "task_pack_id",
    "task_pack_item_id",
    "task_pack_path",
    "task_pack_status",
    "selected_task_source",
    "promoted_item_id",
    "completed_item_id",
    "blocker_signature",
    "input_delta_gate",
    "terminal_blocker",
    "used_advice",
    "authority_policy",
    "authority_policy_source",
    "created_at",
]

STAGE_STATUS_NORMALIZATION = {
    "success": "complete",
    "succeeded": "complete",
    "block": "blocked",
}

TERMINAL_OBSERVATION_FIELDS = {
    "event_id",
    "step",
    "status",
    "reason",
    "task_id",
    "terminal_justified",
    "terminal_outcome_key",
    "terminal_outcome_family_key",
    "terminal_latch_key_version",
    "blocker_signature",
    "input_state_fingerprint",
    "authority_state_fingerprint",
    "external_state_fingerprint",
    "input_delta",
    "material_delta",
    "required_missing_input_count",
    "authority_policy",
    "authority_policy_source",
    "created_at",
}
