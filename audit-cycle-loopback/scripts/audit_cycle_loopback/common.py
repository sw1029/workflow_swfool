from __future__ import annotations

import re


REGISTRY_REL_PATH = ".task/anti_loop/family_progress_registry.jsonl"
ROOT_CAUSE_LEDGER_REL_PATH = ".task/anti_loop/root_cause_ledger.jsonl"
SCHEMA_VERSION = "anti-loop-progress-gate-v1"
DOMAIN_ADAPTER_ENV = "TASK_CYCLE_DOMAIN_ADAPTER_PATH"
# Compatibility exports for callers that imported the former policy defaults.
# ``None`` is intentional: repository adapter locations and decision budgets
# must be supplied by the caller, environment, or repository configuration.
DEFAULT_DOMAIN_ADAPTER_REL_PATH: str | None = None
DISPOSITION_UNIVERSE = {
    "goal_productive",
    "consolidation",
    "terminal_blocked",
    "user_escalation",
}
SAFETY_VALVES = {"terminal_blocked", "user_escalation"}
CONSOLIDATION_STREAK_CAP_DEFAULT: int | None = None
MEASUREMENT_STREAK_CAP_DEFAULT: int | None = None
MAX_FORWARD_MUTATIONS_DEFAULT: int | None = None
DETECTION_ONLY_STREAK_CAP_DEFAULT: int | None = None
UNTRIED_PROMOTION_BUDGET_DEFAULT: int | None = None
ADAPTER_MANDATE_STREAK_CAP_DEFAULT: int | None = None
CUMULATIVE_CHAIN_STREAK_CAP_DEFAULT: int | None = None
INSTRUMENTATION_TRIGGER_THRESHOLD_DEFAULT: int | None = None
HOOK_DEMAND_THRESHOLD_DEFAULT: int | None = None
ENVELOPE_THAW_STREAK_CAP_DEFAULT: int | None = None
# This is a serialization/storage-hygiene bound, not a progress or terminal
# decision budget. It may compact history but cannot change a gate verdict.
ROOT_CAUSE_LEDGER_MAX_ROWS_PER_FAMILY_DEFAULT = 200
ROOT_STEERING_DOC_NAMES = {"task_advice.md", "skill_advice.md", "task_doctor_steering.md"}
# Domain quality axes are adapter-owned.  The empty tuple is retained as a
# compatibility export for callers that imported the old constant, but generic
# repositories must not inherit any metric names from this package.
QUALITY_DELTA_KEYS: tuple[str, ...] = ()
ROOT_KEY_KEYS = {"root_key", "semantic_root_key", "loop_root_key"}
IDEMPOTENT_REPLAY_KEYS = (
    "measurement_progress",
    "measurement_progress_allowed",
    "measurement_streak",
    "measurement_streak_cap",
    "measurement_check_ids",
    "measurement_frontiers_observed",
    "measurement_progress_basis",
    "measurement_progress_streak_for_root_key",
    "measurement_progress_streak_for_root_family",
    "legacy_family_key",
    "root_family_key",
    "blocker_root_family",
    "root_key",
    "previous_high_water_mark",
    "coverage_quality_delta_gate",
    "quality_delta_policy",
    "coverage_quality_delta_reconciliation_gate",
    "substance_metrics",
    "substance_delta_gate",
    "vacuous_corrective_gate",
    "facet_root_map_applied",
    "facet_root_map_missing",
    "facet_root_map_size",
    "terminal_outcome_key",
    "terminal_outcome_family_key",
    "terminal_outcome_family_fallback_applied",
    "terminal_outcome_family_previous_count",
    "advice_freshness_gate",
    "partial_progress_axes_gate",
    "structure_metrics_gate",
    "structure_high_water_key_scope",
    "structure_global_invariant_metrics",
    "previous_accepted_baseline",
    "provider_scale_dispatch_gate",
    "measurement_goal_productive_allowed",
    "requires_non_measurement_goal_productive",
    "blocker_signature",
    "blocker_ladder_rung",
    "blocker_mutation_kind",
    "forward_mutation_budget_remaining",
    "terminal_outcome_changed",
    "observed_delta_class",
    "forward_mutation_vacuous",
    "root_cause_ledger_path",
    "root_cause_ledger_status",
    "root_cause_ledger_entries",
    "root_cause_unverified_hypotheses",
    "root_cause_duplicate_hypotheses",
    "repo_owned_source_roots",
    "repo_owned_source_roots_status",
    "repo_owned_source_roots_error",
    "adapter_mandate_gate",
    "adapter_mandate_required",
    "adapter_missing_streak",
    "adapter_contract_unmet",
    "adapter_hook_demand",
    "hook_demand_threshold",
    "hook_supply_required",
    "demanded_hooks",
    "cumulative_goal_distance_gate",
    "cumulative_goal_distance_scope_key",
    "cumulative_goal_distance_stall_streak",
    "cumulative_goal_distance_stalled",
    "cumulative_untried_chain_without_quality_delta",
    "high_water_vector",
    "high_water_last_improved_cycle",
    "untried_veto_overridden_by_chain_stall",
    "acceptance_reachability_gate",
    "acceptance_unreachable_under_frozen_config",
    "acceptance_verifier_not_evaluated",
    "unverifiable_acceptance_contract",
    "relaxation_or_escalation_required",
    "residual_gap_policy",
    "residual_gap_ratio",
    "marginal_repair",
    "oracle_metric_validity_gate",
    "metric_verifier_not_evaluated",
    "adapter_wiring_gate",
    "adapter_wiring_defect",
    "adapter_loaded",
    "adapter_path",
    "adapter_registered",
    "adapter_expected_path",
    "chain_stall_forced_retarget_gate",
    "forced_selected_task",
    "forced_selected_task_options",
    "untried_actionable_root_cause_exists",
    "untried_root_cause_hypotheses",
    "untried_promotion_budget",
    "vacuous_untried_attempt_count",
    "vacuous_untried_streak",
    "hypothesis_exhausted",
    "hypothesis_exhaustion_seal_path",
    "terminal_blocked_invalid_due_to_untried_root_cause",
    "force_implementation_cycle",
    "task_correction_class",
    "detection_only",
    "detection_only_streak_for_root_family",
    "detection_only_streak_cap",
    "requires_correction_or_terminal",
    "validator_integrity_gate",
    "evidence_provenance_gate",
    "producer_attested_fields",
    "independently_verified_fields",
    "attested_only_movement",
    "primary_metric_gate",
    "primary_metric_high_water_moved",
    "primary_metric_zero_movement_streak",
    "primary_metric_stalled",
    "c4_user_escalation_backstop_required",
    "failure_surface_stage_gate",
    "execution_stage_ladder_status",
    "last_successful_stage",
    "failure_surface_stage",
    "failure_surface_count_key",
    "terminal_classification_stage_contradiction",
    "terminal_classification_invalid_for_counting",
    "same_input_contract_gate",
    "same_input_contract_violation",
    "diagnostics_unavailable",
    "diagnostics_unavailable_streak",
    "diagnostics_unavailable_gate",
    "instrumentation_supply_required",
    "verification_source_separation_gate",
    "independent_source_separation_status",
    "independently_verified_downgraded_fields",
    "envelope_thaw_item_required",
    "envelope_thaw_item",
    "envelope_thaw_streak",
    "root_dominant_parameter_key",
    "coupled_verifier_gate",
    "pass_with_coupled_verifier",
    "changed_verifier_source_paths",
    "effective_allowed_dispositions",
    "disposition_intersection_basis",
    "consolidation_streak",
    "consolidation_reduces_goal_distance",
    "consolidation_streak_cap",
    "authoritative_semantic_progress",
    "findings",
)
# Compatibility exports only. Frontier IDs and ladder ordering are supplied by
# callers/adapters instead of inferred from domain vocabulary.
FRONTIER_CHECK_KEYS: set[str] = set()
CHECK_ID_KEYS = {
    "check_id",
    "check_ids",
    "check_name",
    "check_names",
    "metric_id",
    "metric_ids",
    "oracle_id",
    "oracle_ids",
    "oracle_name",
    "oracle_names",
    "validation_check",
    "validation_checks",
}
BLOCKER_SIGNATURE_KEYS = {
    "blocker",
    "blocker_code",
    "blocker_reason",
    "blocker_signature",
    "failed_reason",
    "failure_reason",
}
LADDER_RANK: dict[str, int] = {}
RUNG_ALIASES: dict[str, str] = {}
VOLATILE_KEYS = {
    "created_at",
    "updated_at",
    "run_id",
    "cycle_id",
    "timestamp",
    "source_path",
    "path",
    "offset",
    "start_offset",
    "end_offset",
}
FACET_SUFFIX_RE = re.compile(
    r"([_.:/|-])(?:v\d+|ver\d+|version\d+|facet|variant|case|mode|phase|stage|"
    r"vocab|timing|typing|schema|contract|gate|metric|oracle|validator|lineage|"
    r"coverage|preflight|handoff|packet|dashboard|report|field|scalar|check|review|surface)$",
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

__all__ = (
    "REGISTRY_REL_PATH",
    "ROOT_CAUSE_LEDGER_REL_PATH",
    "SCHEMA_VERSION",
    "DOMAIN_ADAPTER_ENV",
    "DEFAULT_DOMAIN_ADAPTER_REL_PATH",
    "DISPOSITION_UNIVERSE",
    "SAFETY_VALVES",
    "CONSOLIDATION_STREAK_CAP_DEFAULT",
    "MEASUREMENT_STREAK_CAP_DEFAULT",
    "MAX_FORWARD_MUTATIONS_DEFAULT",
    "DETECTION_ONLY_STREAK_CAP_DEFAULT",
    "UNTRIED_PROMOTION_BUDGET_DEFAULT",
    "ADAPTER_MANDATE_STREAK_CAP_DEFAULT",
    "CUMULATIVE_CHAIN_STREAK_CAP_DEFAULT",
    "INSTRUMENTATION_TRIGGER_THRESHOLD_DEFAULT",
    "HOOK_DEMAND_THRESHOLD_DEFAULT",
    "ENVELOPE_THAW_STREAK_CAP_DEFAULT",
    "ROOT_CAUSE_LEDGER_MAX_ROWS_PER_FAMILY_DEFAULT",
    "ROOT_STEERING_DOC_NAMES",
    "QUALITY_DELTA_KEYS",
    "ROOT_KEY_KEYS",
    "IDEMPOTENT_REPLAY_KEYS",
    "FRONTIER_CHECK_KEYS",
    "CHECK_ID_KEYS",
    "BLOCKER_SIGNATURE_KEYS",
    "LADDER_RANK",
    "RUNG_ALIASES",
    "VOLATILE_KEYS",
    "FACET_SUFFIX_RE",
    "PASS_STATUS_VALUES",
    "FAIL_STATUS_VALUES",
    "VALIDATOR_RESULT_KEYS",
    "VALIDATOR_CHILD_KEYS",
    "POPULATION_COUNT_KEYS",
    "INSPECTED_COUNT_KEYS",
    "DETECTION_TERMS_RE",
    "CORRECTION_TERMS_RE",
)
