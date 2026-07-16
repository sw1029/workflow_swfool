"""Static public API for the loopback evaluator.

Every public symbol is declared here explicitly. Internal modules may evolve without
reflective export discovery or ambient namespace rebinding.
"""

from __future__ import annotations

from .public_contract import PUBLIC_NAMES as PUBLIC_NAMES

from typing import Any
from pathlib import Path
from dataclasses import dataclass
from dataclasses import field

from .acceptance import (
    acceptance_reachability_gate,
    acceptance_target_from_value,
    infer_reachability_verdict,
    merge_acceptance_verifier_contract,
    metric_validity_states,
    normalize_gate_evaluation_status,
    normalize_verifier_contract,
    oracle_metric_validity_gate,
    verifier_evaluation_status,
)

from .adapters import (
    apply_gate_artifact_compatibility,
    call_adapter,
    canonicalize,
    compute_quality,
    domain_adapter_candidate_paths,
    fingerprint_rows,
    gate_artifact_compatibility_result,
    load_artifact_paths,
    load_artifact_selection,
    load_domain_adapter,
    load_python_module,
)

from .advice import (
    active_advice_hashes,
    advice_coherence_finding,
    semantic_progress_value,
    sha256_file,
    validator_disagreement_finding,
)

from .assembly import (
    build_base_packet,
)

from .blockers import (
    blocker_mutation_kind,
    classify_task_correction,
    collect_result_bools,
    detection_only_streak,
    explicit_result_bool,
    first_int_by_key,
    first_named_value,
    forward_mutation_streak,
    infer_ladder_rung,
    mapping_result_bool,
    normalize_ladder_rung,
    validator_integrity_gate,
)

from .chain import (
    adapter_contract_unmet_fields,
    adapter_mandate_gate,
    adapter_missing_streak,
    adapter_wiring_gate,
    chain_stall_forced_retarget_gate,
    consumer_context_conformance_gate,
    consumer_receipt_binding_sha256,
    consumer_receipt_pass,
    cumulative_goal_distance_gate,
    cumulative_goal_distance_scope_key,
    first_actionable_capability_ladder_option,
    normalize_primary_metric_gate,
    previous_primary_metric_value,
    primary_metric_artifact_binding,
    primary_metric_registry_high_water,
    primary_metric_zero_movement_streak,
    row_adapter_contract_unmet,
    row_goal_distance_scope,
    row_vector_delta_passed,
    semantic_progress_from_high_water,
    updated_high_water,
)

from .cli import (
    main,
)

from .common import (
    ADAPTER_MANDATE_STREAK_CAP_DEFAULT,
    BLOCKER_SIGNATURE_KEYS,
    CHECK_ID_KEYS,
    CONSOLIDATION_STREAK_CAP_DEFAULT,
    CORRECTION_TERMS_RE,
    CUMULATIVE_CHAIN_STREAK_CAP_DEFAULT,
    DEFAULT_DOMAIN_ADAPTER_REL_PATH,
    DETECTION_ONLY_STREAK_CAP_DEFAULT,
    DETECTION_TERMS_RE,
    DISPOSITION_UNIVERSE,
    DOMAIN_ADAPTER_ENV,
    ENVELOPE_THAW_STREAK_CAP_DEFAULT,
    FACET_SUFFIX_RE,
    FAIL_STATUS_VALUES,
    FRONTIER_CHECK_KEYS,
    HOOK_DEMAND_THRESHOLD_DEFAULT,
    IDEMPOTENT_REPLAY_KEYS,
    INSPECTED_COUNT_KEYS,
    INSTRUMENTATION_TRIGGER_THRESHOLD_DEFAULT,
    LADDER_RANK,
    MAX_FORWARD_MUTATIONS_DEFAULT,
    MEASUREMENT_STREAK_CAP_DEFAULT,
    PASS_STATUS_VALUES,
    POPULATION_COUNT_KEYS,
    QUALITY_DELTA_KEYS,
    REGISTRY_REL_PATH,
    ROOT_CAUSE_LEDGER_MAX_ROWS_PER_FAMILY_DEFAULT,
    ROOT_CAUSE_LEDGER_REL_PATH,
    ROOT_KEY_KEYS,
    ROOT_STEERING_DOC_NAMES,
    RUNG_ALIASES,
    SAFETY_VALVES,
    SCHEMA_VERSION,
    UNTRIED_PROMOTION_BUDGET_DEFAULT,
    VALIDATOR_CHILD_KEYS,
    VALIDATOR_RESULT_KEYS,
    VOLATILE_KEYS,
)

from .constant_registry import (
    PACKAGE_NAME,
    REGISTRY_FILENAME,
    constant_registry_path,
    load_constant_registry,
    validate_constant_registry,
)

from .context import (
    EvaluationContext,
    EvaluationState,
    RuntimeCache,
)

from .domain import (
    FINGERPRINT_CLAIM_RE,
    advice_freshness_gate,
    collapse_root_family,
    collect_values_by_key,
    extract_check_ids,
    extract_fingerprint_claims,
    extract_frontier_observations,
    frontier_key,
    gate_result_regressions,
    normalize_adapter_quality_result,
    normalize_corrective_resolution,
    normalize_facet_root_map,
    partial_progress_axes_gate,
    recent_family_rows,
    scalar_strings,
    vacuous_corrective_gate,
    verdict_state,
)

from .evaluator import (
    LoopbackEvaluator,
    evaluate,
)

from .failure import (
    FAILURE_STAGE_KEYS,
    LAST_STAGE_KEYS,
    TERMINAL_CLASSIFICATION_KEYS,
    diagnostics_unavailable_gate,
    next_failure_surface_stage,
    normalize_classification_stage_map,
    normalize_execution_stage_ladder,
    normalize_stage_name,
    same_input_contract_gate,
    terminal_stage_resolution_gate,
)

from .families import (
    normalize_family_key,
    normalize_root_family_key,
)

from .findings import (
    apply_disposition_and_findings,
)

from .io_utils import (
    now_iso,
    read_json,
    read_jsonl,
    rel_path,
)

from .measurement import (
    consolidation_streak,
    effective_allowed_dispositions,
    extract_disposition_gates,
    gate_allowed_dispositions,
    gate_allowed_task_kinds,
    gate_constrains_disposition,
    item_disposition,
    measurement_progress_details,
    normalize_dispositions,
    normalize_portfolio_budget_gate,
    normalize_task_kind,
    normalize_task_kinds,
    recent_root_rows,
    row_root_family,
)

from .outcome import (
    first_scalar_by_key,
    latest_root_family_row,
    normalize_root_cause_slug,
    observed_delta_class,
    previous_micro_hardening_count,
    previous_micro_hardening_count_for_count_key,
    row_effective_count_key,
    terminal_outcome_changed,
    terminal_outcome_key,
    terminal_outcome_root_family,
    terminal_self_resolution_gate,
)

from .packet import (
    FindingCollector,
    PacketBuilder,
)

from .quality import (
    METRIC_APPLICABILITY_STATUSES,
    METRIC_POLICY_CONTRACT_ERROR_CODES,
    OPAQUE_ID_MAX_LENGTH,
    apply_quality_policy_compatibility,
    coverage_quality_delta_gate,
    high_water_metric_value,
    metric_stall_observation_allowed,
    normalize_quality_delta_policy,
    provider_scale_dispatch_gate,
    public_quality_delta_policy,
    quality_high_water_for_policy,
    quality_metric_value,
)

from .registry import (
    append_root_cause_ledger,
    attempt_revision_value,
    bounded_durable_projection,
    canonical_json_sha256,
    compact_registry,
    compact_root_cause_ledger,
    content_bound_attempt_identity,
    decision_input_state_fingerprint,
    default_high_water,
    exhausted_family_seal_record,
    feed_exhausted_family_seal,
    finalized_projection_rows,
    finalized_seal_projection,
    hook_demand_threshold_from_value,
    latest_adapter_hook_demand,
    legacy_content_bound_attempt_identity,
    load_registry,
    load_verified_finalized_loopback_state,
    logical_attempt_key,
    merge_adapter_hook_demand,
    normalize_hook_id,
    project_exhausted_family_seal,
    write_registry,
)

from .root_cause import (
    ROOT_CAUSE_PROVENANCE_KEYS,
    clean_provenance_path_ref,
    equivalent_root_cause,
    harden_repo_owned_actionability,
    normalize_repo_owned_source_roots,
    normalize_root_cause_equivalence_slug,
    normalize_root_cause_hypotheses,
    repo_owned_provenance_refs,
    root_cause_actionability,
    root_cause_actionable,
    root_cause_attempt_weight,
    root_cause_delta_class,
    root_cause_distinct_key,
    root_cause_exhaustion_state,
    root_cause_hypothesis_gate,
    root_cause_provenance_refs,
    root_cause_target_surface,
    same_root_cause_scope,
    untried_root_cause_hypotheses,
)

from .root_cause_runtime import (
    apply_root_cause_ledger,
)

from .values import (
    bool_value,
    budget_evaluation,
    budget_value,
    first_field_value,
    float_value,
    int_metric,
    iter_dicts,
    list_values,
    load_json_value,
    load_json_values,
    positive_int_or_none,
    truthy_observation,
)

from .vectors import (
    ATTESTED_PROVENANCE_VALUES,
    INDEPENDENT_PROVENANCE_VALUES,
    apply_evidence_provenance_filter,
    compact_coverage_gate,
    coverage_gate_pass_value,
    coverage_gate_vector,
    coverage_quality_delta_reconciliation_gate,
    evidence_provenance_gate,
    find_coverage_quality_delta_gate,
    metric_is_independently_verified,
    normalize_evidence_provenance,
    normalize_previous_accepted_baseline,
    normalize_provenance_label,
    numeric_vector,
    provenance_for_metric,
    string_list,
    structure_metrics_gate,
    vector_delta_gate,
)

from .verification import (
    coupled_verifier_gate,
    evidence_source_metadata,
    gate_evaluation_status,
    gate_is_passing,
    load_changed_files,
    normalize_gate_key,
    normalize_verifier_source_paths,
    path_matches_pattern,
    verification_source_separation_gate,
)

# Keep the characterized facade contract literal and reviewable.  Compact layout
# keeps this compatibility module below the repository's 500-line source limit.
# fmt: off
__all__ = (
    'ADAPTER_MANDATE_STREAK_CAP_DEFAULT', 'ATTESTED_PROVENANCE_VALUES', 'Any', 'BLOCKER_SIGNATURE_KEYS',
    'CHECK_ID_KEYS', 'CONSOLIDATION_STREAK_CAP_DEFAULT', 'CORRECTION_TERMS_RE', 'CUMULATIVE_CHAIN_STREAK_CAP_DEFAULT',
    'DEFAULT_DOMAIN_ADAPTER_REL_PATH', 'DETECTION_ONLY_STREAK_CAP_DEFAULT', 'DETECTION_TERMS_RE', 'DISPOSITION_UNIVERSE',
    'DOMAIN_ADAPTER_ENV', 'ENVELOPE_THAW_STREAK_CAP_DEFAULT', 'EvaluationContext', 'EvaluationState',
    'FACET_SUFFIX_RE', 'FAILURE_STAGE_KEYS', 'FAIL_STATUS_VALUES', 'FINGERPRINT_CLAIM_RE',
    'FRONTIER_CHECK_KEYS', 'FindingCollector', 'HOOK_DEMAND_THRESHOLD_DEFAULT', 'IDEMPOTENT_REPLAY_KEYS',
    'INDEPENDENT_PROVENANCE_VALUES', 'INSPECTED_COUNT_KEYS', 'INSTRUMENTATION_TRIGGER_THRESHOLD_DEFAULT', 'LADDER_RANK',
    'LAST_STAGE_KEYS', 'LoopbackEvaluator', 'MAX_FORWARD_MUTATIONS_DEFAULT', 'MEASUREMENT_STREAK_CAP_DEFAULT',
    'METRIC_APPLICABILITY_STATUSES', 'METRIC_POLICY_CONTRACT_ERROR_CODES', 'OPAQUE_ID_MAX_LENGTH', 'PACKAGE_NAME',
    'PASS_STATUS_VALUES', 'POPULATION_COUNT_KEYS', 'PacketBuilder', 'Path',
    'QUALITY_DELTA_KEYS', 'REGISTRY_FILENAME', 'REGISTRY_REL_PATH', 'ROOT_CAUSE_LEDGER_MAX_ROWS_PER_FAMILY_DEFAULT',
    'ROOT_CAUSE_LEDGER_REL_PATH', 'ROOT_CAUSE_PROVENANCE_KEYS', 'ROOT_KEY_KEYS', 'ROOT_STEERING_DOC_NAMES',
    'RUNG_ALIASES', 'RuntimeCache', 'SAFETY_VALVES', 'SCHEMA_VERSION',
    'TERMINAL_CLASSIFICATION_KEYS', 'UNTRIED_PROMOTION_BUDGET_DEFAULT', 'VALIDATOR_CHILD_KEYS', 'VALIDATOR_RESULT_KEYS',
    'VOLATILE_KEYS', 'acceptance_reachability_gate', 'acceptance_target_from_value', 'active_advice_hashes',
    'adapter_contract_unmet_fields', 'adapter_mandate_gate', 'adapter_missing_streak', 'adapter_wiring_gate',
    'advice_coherence_finding', 'advice_freshness_gate', 'append_root_cause_ledger', 'apply_disposition_and_findings',
    'apply_evidence_provenance_filter', 'apply_gate_artifact_compatibility', 'apply_quality_policy_compatibility', 'apply_root_cause_ledger',
    'attempt_revision_value', 'blocker_mutation_kind', 'bool_value', 'bounded_durable_projection',
    'budget_evaluation', 'budget_value', 'build_base_packet', 'call_adapter',
    'canonical_json_sha256', 'canonicalize', 'chain_stall_forced_retarget_gate', 'classify_task_correction',
    'clean_provenance_path_ref', 'collapse_root_family', 'collect_result_bools', 'collect_values_by_key',
    'compact_coverage_gate', 'compact_registry', 'compact_root_cause_ledger', 'compute_quality',
    'consolidation_streak', 'constant_registry_path', 'consumer_context_conformance_gate', 'consumer_receipt_binding_sha256',
    'consumer_receipt_pass', 'content_bound_attempt_identity', 'coupled_verifier_gate', 'coverage_gate_pass_value',
    'coverage_gate_vector', 'coverage_quality_delta_gate', 'coverage_quality_delta_reconciliation_gate', 'cumulative_goal_distance_gate',
    'cumulative_goal_distance_scope_key', 'dataclass', 'decision_input_state_fingerprint', 'default_high_water',
    'detection_only_streak', 'diagnostics_unavailable_gate', 'domain_adapter_candidate_paths', 'effective_allowed_dispositions',
    'equivalent_root_cause', 'evaluate', 'evidence_provenance_gate', 'evidence_source_metadata',
    'exhausted_family_seal_record', 'explicit_result_bool', 'extract_check_ids', 'extract_disposition_gates',
    'extract_fingerprint_claims', 'extract_frontier_observations', 'feed_exhausted_family_seal', 'field',
    'finalized_projection_rows', 'finalized_seal_projection', 'find_coverage_quality_delta_gate', 'fingerprint_rows',
    'first_actionable_capability_ladder_option', 'first_field_value', 'first_int_by_key', 'first_named_value',
    'first_scalar_by_key', 'float_value', 'forward_mutation_streak', 'frontier_key',
    'gate_allowed_dispositions', 'gate_allowed_task_kinds', 'gate_artifact_compatibility_result', 'gate_constrains_disposition',
    'gate_evaluation_status', 'gate_is_passing', 'gate_result_regressions', 'harden_repo_owned_actionability',
    'high_water_metric_value', 'hook_demand_threshold_from_value', 'infer_ladder_rung', 'infer_reachability_verdict',
    'int_metric', 'item_disposition', 'iter_dicts', 'latest_adapter_hook_demand',
    'latest_root_family_row', 'legacy_content_bound_attempt_identity', 'list_values', 'load_artifact_paths',
    'load_artifact_selection', 'load_changed_files', 'load_constant_registry', 'load_domain_adapter',
    'load_json_value', 'load_json_values', 'load_python_module', 'load_registry',
    'load_verified_finalized_loopback_state', 'logical_attempt_key', 'main', 'mapping_result_bool',
    'measurement_progress_details', 'merge_acceptance_verifier_contract', 'merge_adapter_hook_demand', 'metric_is_independently_verified',
    'metric_stall_observation_allowed', 'metric_validity_states', 'next_failure_surface_stage', 'normalize_adapter_quality_result',
    'normalize_classification_stage_map', 'normalize_corrective_resolution', 'normalize_dispositions', 'normalize_evidence_provenance',
    'normalize_execution_stage_ladder', 'normalize_facet_root_map', 'normalize_family_key', 'normalize_gate_evaluation_status',
    'normalize_gate_key', 'normalize_hook_id', 'normalize_ladder_rung', 'normalize_portfolio_budget_gate',
    'normalize_previous_accepted_baseline', 'normalize_primary_metric_gate', 'normalize_provenance_label', 'normalize_quality_delta_policy',
    'normalize_repo_owned_source_roots', 'normalize_root_cause_equivalence_slug', 'normalize_root_cause_hypotheses', 'normalize_root_cause_slug',
    'normalize_root_family_key', 'normalize_stage_name', 'normalize_task_kind', 'normalize_task_kinds',
    'normalize_verifier_contract', 'normalize_verifier_source_paths', 'now_iso', 'numeric_vector',
    'observed_delta_class', 'oracle_metric_validity_gate', 'partial_progress_axes_gate', 'path_matches_pattern',
    'positive_int_or_none', 'previous_micro_hardening_count', 'previous_micro_hardening_count_for_count_key', 'previous_primary_metric_value',
    'primary_metric_artifact_binding', 'primary_metric_registry_high_water', 'primary_metric_zero_movement_streak', 'project_exhausted_family_seal',
    'provenance_for_metric', 'provider_scale_dispatch_gate', 'public_quality_delta_policy', 'quality_high_water_for_policy',
    'quality_metric_value', 'read_json', 'read_jsonl', 'recent_family_rows',
    'recent_root_rows', 'rel_path', 'repo_owned_provenance_refs', 'root_cause_actionability',
    'root_cause_actionable', 'root_cause_attempt_weight', 'root_cause_delta_class', 'root_cause_distinct_key',
    'root_cause_exhaustion_state', 'root_cause_hypothesis_gate', 'root_cause_provenance_refs', 'root_cause_target_surface',
    'row_adapter_contract_unmet', 'row_effective_count_key', 'row_goal_distance_scope', 'row_root_family',
    'row_vector_delta_passed', 'same_input_contract_gate', 'same_root_cause_scope', 'scalar_strings',
    'semantic_progress_from_high_water', 'semantic_progress_value', 'sha256_file', 'string_list',
    'structure_metrics_gate', 'terminal_outcome_changed', 'terminal_outcome_key', 'terminal_outcome_root_family',
    'terminal_self_resolution_gate', 'terminal_stage_resolution_gate', 'truthy_observation', 'untried_root_cause_hypotheses',
    'updated_high_water', 'vacuous_corrective_gate', 'validate_constant_registry', 'validator_disagreement_finding',
    'validator_integrity_gate', 'vector_delta_gate', 'verdict_state', 'verification_source_separation_gate',
    'verifier_evaluation_status', 'write_registry',
)
# fmt: on
