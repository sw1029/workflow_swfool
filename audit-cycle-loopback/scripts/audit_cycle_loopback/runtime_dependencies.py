"""Explicit dependency facade for evaluation stages.

Stage modules import named dependencies from this module so their contracts stay
inspectable without ambient global rebinding or reflective service lookup.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
import argparse
import re

from .acceptance import (
    acceptance_reachability_gate,
    acceptance_target_from_value,
    merge_acceptance_verifier_contract,
    oracle_metric_validity_gate,
)

from .adapters import (
    apply_gate_artifact_compatibility,
    call_adapter,
    compute_quality,
    domain_adapter_candidate_paths,
    gate_artifact_compatibility_result,
    load_artifact_selection,
    load_domain_adapter,
)

from .advice import (
    advice_coherence_finding,
    validator_disagreement_finding,
)

from .blockers import (
    blocker_mutation_kind,
    classify_task_correction,
    detection_only_streak,
    first_named_value,
    forward_mutation_streak,
    infer_ladder_rung,
    normalize_ladder_rung,
    validator_integrity_gate,
)

from .chain import (
    adapter_contract_unmet_fields,
    adapter_mandate_gate,
    adapter_wiring_gate,
    chain_stall_forced_retarget_gate,
    consumer_context_conformance_gate,
    consumer_receipt_binding_sha256,
    cumulative_goal_distance_gate,
    first_actionable_capability_ladder_option,
    normalize_primary_metric_gate,
    previous_primary_metric_value,
    updated_high_water,
)

from .common import (
    BLOCKER_SIGNATURE_KEYS,
    IDEMPOTENT_REPLAY_KEYS,
    ROOT_CAUSE_LEDGER_MAX_ROWS_PER_FAMILY_DEFAULT,
    ROOT_CAUSE_LEDGER_REL_PATH,
    ROOT_KEY_KEYS,
    SCHEMA_VERSION,
)

from .domain import (
    advice_freshness_gate,
    collapse_root_family,
    extract_check_ids,
    extract_frontier_observations,
    frontier_key,
    normalize_facet_root_map,
    partial_progress_axes_gate,
    vacuous_corrective_gate,
)

from .failure import (
    diagnostics_unavailable_gate,
    same_input_contract_gate,
    terminal_stage_resolution_gate,
)

from .families import (
    normalize_family_key,
    normalize_root_family_key,
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
    gate_allowed_task_kinds,
    measurement_progress_details,
    normalize_portfolio_budget_gate,
    normalize_task_kinds,
    row_root_family,
)

from .outcome import (
    latest_root_family_row,
    normalize_root_cause_slug,
    observed_delta_class,
    previous_micro_hardening_count,
    previous_micro_hardening_count_for_count_key,
    terminal_outcome_changed,
    terminal_outcome_key,
    terminal_outcome_root_family,
    terminal_self_resolution_gate,
)

from .quality import (
    apply_quality_policy_compatibility,
    coverage_quality_delta_gate,
    metric_stall_observation_allowed,
    normalize_quality_delta_policy,
    provider_scale_dispatch_gate,
    public_quality_delta_policy,
    quality_high_water_for_policy,
)

from .registry import (
    attempt_revision_value,
    compact_registry,
    compact_root_cause_ledger,
    content_bound_attempt_identity,
    decision_input_state_fingerprint,
    default_high_water,
    exhausted_family_seal_record,
    finalized_projection_rows,
    finalized_seal_projection,
    hook_demand_threshold_from_value,
    legacy_content_bound_attempt_identity,
    load_registry,
    load_verified_finalized_loopback_state,
    merge_adapter_hook_demand,
    normalize_hook_id,
    project_exhausted_family_seal,
)

from .root_cause import (
    harden_repo_owned_actionability,
    normalize_repo_owned_source_roots,
    normalize_root_cause_hypotheses,
    root_cause_hypothesis_gate,
    root_cause_provenance_refs,
)

from .values import (
    bool_value,
    budget_evaluation,
    budget_value,
    first_field_value,
    load_json_value,
    load_json_values,
    positive_int_or_none,
)

from .vectors import (
    apply_evidence_provenance_filter,
    coverage_quality_delta_reconciliation_gate,
    evidence_provenance_gate,
    find_coverage_quality_delta_gate,
    normalize_evidence_provenance,
    normalize_previous_accepted_baseline,
    normalize_provenance_label,
    numeric_vector,
    string_list,
    structure_metrics_gate,
    vector_delta_gate,
)

from .verification import (
    coupled_verifier_gate,
    load_changed_files,
    normalize_gate_key,
    normalize_verifier_source_paths,
    verification_source_separation_gate,
)

__all__ = (
    "Any",
    "BLOCKER_SIGNATURE_KEYS",
    "IDEMPOTENT_REPLAY_KEYS",
    "Path",
    "ROOT_CAUSE_LEDGER_MAX_ROWS_PER_FAMILY_DEFAULT",
    "ROOT_CAUSE_LEDGER_REL_PATH",
    "ROOT_KEY_KEYS",
    "SCHEMA_VERSION",
    "acceptance_reachability_gate",
    "acceptance_target_from_value",
    "adapter_contract_unmet_fields",
    "adapter_mandate_gate",
    "adapter_wiring_gate",
    "advice_coherence_finding",
    "advice_freshness_gate",
    "apply_evidence_provenance_filter",
    "apply_gate_artifact_compatibility",
    "apply_quality_policy_compatibility",
    "argparse",
    "attempt_revision_value",
    "blocker_mutation_kind",
    "bool_value",
    "budget_evaluation",
    "budget_value",
    "call_adapter",
    "chain_stall_forced_retarget_gate",
    "classify_task_correction",
    "collapse_root_family",
    "compact_registry",
    "compact_root_cause_ledger",
    "compute_quality",
    "consolidation_streak",
    "consumer_context_conformance_gate",
    "consumer_receipt_binding_sha256",
    "content_bound_attempt_identity",
    "coupled_verifier_gate",
    "coverage_quality_delta_gate",
    "coverage_quality_delta_reconciliation_gate",
    "cumulative_goal_distance_gate",
    "decision_input_state_fingerprint",
    "default_high_water",
    "detection_only_streak",
    "diagnostics_unavailable_gate",
    "domain_adapter_candidate_paths",
    "effective_allowed_dispositions",
    "evidence_provenance_gate",
    "exhausted_family_seal_record",
    "extract_check_ids",
    "extract_disposition_gates",
    "extract_frontier_observations",
    "finalized_projection_rows",
    "finalized_seal_projection",
    "find_coverage_quality_delta_gate",
    "first_actionable_capability_ladder_option",
    "first_field_value",
    "first_named_value",
    "forward_mutation_streak",
    "frontier_key",
    "gate_allowed_task_kinds",
    "gate_artifact_compatibility_result",
    "harden_repo_owned_actionability",
    "hook_demand_threshold_from_value",
    "infer_ladder_rung",
    "latest_root_family_row",
    "legacy_content_bound_attempt_identity",
    "load_artifact_selection",
    "load_changed_files",
    "load_domain_adapter",
    "load_json_value",
    "load_json_values",
    "load_registry",
    "load_verified_finalized_loopback_state",
    "measurement_progress_details",
    "merge_acceptance_verifier_contract",
    "merge_adapter_hook_demand",
    "metric_stall_observation_allowed",
    "normalize_evidence_provenance",
    "normalize_facet_root_map",
    "normalize_family_key",
    "normalize_gate_key",
    "normalize_hook_id",
    "normalize_ladder_rung",
    "normalize_portfolio_budget_gate",
    "normalize_previous_accepted_baseline",
    "normalize_primary_metric_gate",
    "normalize_provenance_label",
    "normalize_quality_delta_policy",
    "normalize_repo_owned_source_roots",
    "normalize_root_cause_hypotheses",
    "normalize_root_cause_slug",
    "normalize_root_family_key",
    "normalize_task_kinds",
    "normalize_verifier_source_paths",
    "now_iso",
    "numeric_vector",
    "observed_delta_class",
    "oracle_metric_validity_gate",
    "partial_progress_axes_gate",
    "positive_int_or_none",
    "previous_micro_hardening_count",
    "previous_micro_hardening_count_for_count_key",
    "previous_primary_metric_value",
    "project_exhausted_family_seal",
    "provider_scale_dispatch_gate",
    "public_quality_delta_policy",
    "quality_high_water_for_policy",
    "re",
    "read_json",
    "read_jsonl",
    "rel_path",
    "root_cause_hypothesis_gate",
    "root_cause_provenance_refs",
    "row_root_family",
    "same_input_contract_gate",
    "string_list",
    "structure_metrics_gate",
    "terminal_outcome_changed",
    "terminal_outcome_key",
    "terminal_outcome_root_family",
    "terminal_self_resolution_gate",
    "terminal_stage_resolution_gate",
    "updated_high_water",
    "vacuous_corrective_gate",
    "validator_disagreement_finding",
    "validator_integrity_gate",
    "vector_delta_gate",
    "verification_source_separation_gate",
)
