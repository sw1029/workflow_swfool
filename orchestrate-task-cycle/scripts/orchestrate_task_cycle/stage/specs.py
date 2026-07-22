"""Static provenance classification for every canonical result target."""

from __future__ import annotations

from dataclasses import dataclass

from ..packet.registry import TARGET_BUILDERS
from ..result_contract.configuration import (
    AGENT_ROUTING_TARGETS,
    COMMON_FIELDS,
    TARGETS,
)
from .v2_specs import SEMANTIC_FIELDS, dependency_selectors, executor_kind


OWNER_FIELD_NAMES = frozenset(
    {
        "actual_changed_files",
        "artifacts",
        "changed_files",
        "commands",
        "dashboard_path",
        "direct_read_scope",
        "evidence_paths",
        "planned_changed_files",
        "reviewed_artifacts",
        "review_agent_count",
        "reviewer_routing",
        "tracked_artifacts",
    }
)
DERIVED_FIELD_NAMES = frozenset(
    {"step", "cycle_id", "task_id", "used_goal_truth", "used_advice"}
)
GIT_DEPENDENT_TARGETS = frozenset(
    {
        "repo_skill_adapter_scan",
        "validation_scope_plan",
        "governance",
        "repo_skill_adapter_validate",
        "code_structure_audit",
        "run",
        "qualitative_review",
        "visible_increment",
        "validation_scope_finalize",
        "commit",
        "dashboard",
        "report",
        "closeout_commit",
    }
)
DIAGNOSTIC_DEPENDENT_TARGETS = frozenset(
    {
        "repo_skill_adapter_scan",
        "acceptance",
        "validation_set_plan",
        "repo_skill_adapter_validate",
        "qualitative_review",
        "loopback_audit",
        "validation_set_build",
        "repo_skill_gap_analysis",
        "cycle_efficiency_profile",
        "index_pre_validate",
        "schema_pre_derive",
        "derive",
        "schema_post_derive",
        "index",
        "validate",
        "issue",
        "dashboard",
        "report",
    }
)


@dataclass(frozen=True, slots=True)
class TargetCompileSpec:
    target: str
    required_fields: tuple[str, ...]
    derived_fields: tuple[str, ...]
    semantic_fields: tuple[str, ...]
    owner_receipt_fields: tuple[str, ...]
    optional_semantic_fields: tuple[str, ...] = ()
    optional_owner_fields: tuple[str, ...] = ()
    reasoned_not_applicable_fields: tuple[str, ...] = ()
    dependency_roles: tuple[str, ...] = ("core",)
    dependency_selectors: tuple[str, ...] = ("core",)
    executor_kind: str = "owner"

    @property
    def classified_fields(self) -> frozenset[str]:
        return frozenset(
            (
                *self.derived_fields,
                *self.semantic_fields,
                *self.owner_receipt_fields,
                *self.reasoned_not_applicable_fields,
            )
        )


ROUTING_OWNER_FIELDS = (
    "agent_routing_applicability",
    "policy_id",
    "profile_id",
    "routing_tier",
    "requested_model_ref",
    "requested_model",
    "model_configuration_status",
    "requested_reasoning_effort",
    "routing_reason_codes",
    "routing_violations",
    "routing_enforcement",
    "routing_limitation",
    "actual_model",
    "actual_reasoning_effort",
)
OPTIONAL_SEMANTIC_FIELDS: dict[str, tuple[str, ...]] = {
    "validation_set_plan": (
        "failure_taxonomy",
        "leakage_policy",
        "label_visibility_policy",
        "scenario_coverage",
        "scenario_uncovered",
    ),
    "run": (
        "long_run_branch",
        "long_run_role",
        "not_applicable_reason",
        "command_provenance_missing",
        "blocker_opacity",
    ),
    "qualitative_review": ("output_delta_summary",),
    "loopback_audit": (
        "provider_request_count",
        "decision_contract_version",
        "required_gate_scopes",
        "consumed_gate_scopes",
    ),
    "validation_set_build": (
        "quality_tier",
        "not_gold",
        "item_count",
        "label_count",
        "oracle_count",
        "source_class_distribution",
        "not_applicable_reason",
    ),
    "cycle_efficiency_profile": ("execution_starvation",),
    "schema_pre_derive": ("pending_output_dependent_evidence",),
    "derive": (
        "derive_mode",
        "next_task_id",
        "effective_progress_kind",
        "output_delta_status",
        "produced_domain_delta",
        "root_cause_attempted_for_family",
        "selected_task_kind",
        "task_pack_status",
        "promotion_origin",
        "retry_axis",
        "task_pack_path",
        "task_pack_item_id",
        "derive_standalone_rationale",
        "terminal_blocker",
    ),
    "schema_post_derive": ("next_task_id", "needs_review"),
    "index": ("audit_verdict", "high_severity_id_blockers"),
    "validate": (
        "progress_axes",
        "finalization_contract_version",
        "finalization_applicability",
        "schema_version",
        "kind",
        "final_candidate",
        "cycle_id",
        "attempt_id",
        "expected_previous_revision",
        "expected_previous_attempt_id",
        "expected_previous_finalization_token",
        "verdict_contract_version",
        "task_acceptance_verdict",
        "artifact_truth_verdict",
        "artifact_semantic_verdict",
        "pack_transition_verdict",
        "historical_index_verdict",
        "goal_readiness_verdict",
        "decision_contract_version",
    ),
}
OPTIONAL_OWNER_FIELDS: dict[str, tuple[str, ...]] = {
    "repo_skill_adapter_validate": (
        "adapter_consumability_status",
        "adapter_architecture_status",
        "adapter_revision_before_sha256",
        "adapter_revision_after_sha256",
        "adapter_architecture",
        "field_origins",
    ),
    "code_structure_audit": ("field_origins",),
    "run": (
        "run_id",
        "owner_task_id",
        "launch_cycle_id",
        "command_argv",
        "workdir",
        "output_dir",
        "log_path",
        "heartbeat",
        "startup_or_heartbeat_evidence",
        "monitor_command",
        "stop_command",
        "remaining_validation",
        "expected_completion_signal",
        "expected_completion_artifacts",
        "failure_autopsy",
    ),
    "qualitative_review": (
        "direct_read_scope",
        "reviewer_routing",
        "review_agent_count",
        "artifact_presence_evidence",
        "verification_axes",
        "consumer_invocation_receipts",
        "output_delta_evidence",
    ),
    "loopback_audit": (
        "anti_loop_handoff",
        "verification_axes",
        "consumer_invocation_receipts",
        "quality_vector",
        "acceptance_scenario_gate",
        "command_provenance_gate",
        "blocker_actionability_gate",
        "stochastic_feasibility_gate",
        "instrumentation_first_fire_gate",
        "expectation_lineage_gate",
        "comparison_parity_gate",
        "adoption_axis_gate",
        "resolution_downgrade_gate",
        "report_key_integrity_gate",
    ),
    "validation_set_build": (
        "validation_set_id",
        "oracle_manifest_path",
        "split_manifest_path",
        "leakage_report_path",
        "validation_set_root_path",
        "premise_receipts",
    ),
    "derive": (
        "finalization_receipt",
        "finalization_consumption",
        "authoritative_projection",
        "improvement_analysis_receipts",
        "advice_consumption_receipts",
        "pack_mutation_receipt",
        "selection_receipt",
        "anti_loop_handoff_consumption",
        "pack_coherence",
        "promotion_receipt",
    ),
    "validate": (
        "finalization_receipt",
        "finalization_consumption",
        "durable_state_candidate",
        "decision_artifact",
        "verification_axes",
        "consumer_invocation_receipts",
        "validation_report_path",
        "premise_receipts",
        "acceptance_scenario_gate",
        "command_provenance_gate",
        "blocker_actionability_gate",
        "stochastic_feasibility_gate",
        "instrumentation_first_fire_gate",
        "expectation_lineage_gate",
        "comparison_parity_gate",
        "adoption_axis_gate",
        "resolution_downgrade_gate",
        "report_key_integrity_gate",
    ),
    "issue": ("issue_paths", "issue_urls", "resolution_evidence"),
    "commit": ("commit_hash", "commit_subject", "commit_skipped_reason"),
    "dashboard": (
        "authoritative_projection",
        "finalization_receipt",
        "finalization_consumption",
        "current_stage_event_count",
    ),
    "report": (
        "authoritative_final",
        "authoritative_projection",
        "finalization_receipt",
        "finalization_consumption",
        "authoritative_projection_digest",
    ),
    "closeout_commit": (
        "commit_hash",
        "commit_subject",
        "commit_skipped_reason",
    ),
}


def _legacy_spec(target: str) -> TargetCompileSpec:
    fields = tuple(dict.fromkeys(("step", *COMMON_FIELDS[target])))
    derived = tuple(field for field in fields if field in DERIVED_FIELD_NAMES)
    if target == "authority":
        owner = tuple(field for field in fields if field not in derived)
    else:
        owner = tuple(
            field
            for field in fields
            if field in OWNER_FIELD_NAMES and field not in derived
        )
    semantic = tuple(
        field for field in fields if field not in set(derived) | set(owner)
    )
    roles = ["core"]
    if target in GIT_DEPENDENT_TARGETS:
        roles.append("git")
    if target in DIAGNOSTIC_DEPENDENT_TARGETS:
        roles.append("diagnostics")
    optional_owner = list(OPTIONAL_OWNER_FIELDS.get(target, ()))
    if target in AGENT_ROUTING_TARGETS:
        optional_owner.extend(ROUTING_OWNER_FIELDS)
    return TargetCompileSpec(
        target=target,
        required_fields=tuple(COMMON_FIELDS[target]),
        derived_fields=derived,
        semantic_fields=semantic,
        owner_receipt_fields=owner,
        optional_semantic_fields=OPTIONAL_SEMANTIC_FIELDS.get(target, ()),
        optional_owner_fields=tuple(dict.fromkeys(optional_owner)),
        dependency_roles=tuple(roles),
        dependency_selectors=tuple(roles),
        executor_kind=("hybrid" if semantic else "owner"),
    )


LEGACY_TARGET_COMPILE_SPECS: dict[str, TargetCompileSpec] = {
    target: _legacy_spec(target) for target in TARGETS
}


def _v2_spec(target: str) -> TargetCompileSpec:
    fields = tuple(dict.fromkeys(("step", *COMMON_FIELDS[target])))
    derived = tuple(field for field in fields if field in DERIVED_FIELD_NAMES)
    semantic = SEMANTIC_FIELDS.get(target, ())
    if not set(semantic) <= set(fields):
        raise RuntimeError(f"v2 semantic provenance names unknown fields for {target}")
    owner = tuple(field for field in fields if field not in set(derived) | set(semantic))
    optional_semantic = (
        OPTIONAL_SEMANTIC_FIELDS.get(target, ())
        if target in SEMANTIC_FIELDS
        else ()
    )
    optional_owner = list(OPTIONAL_OWNER_FIELDS.get(target, ()))
    if target not in SEMANTIC_FIELDS:
        optional_owner.extend(OPTIONAL_SEMANTIC_FIELDS.get(target, ()))
    if target in AGENT_ROUTING_TARGETS:
        optional_owner.extend(ROUTING_OWNER_FIELDS)
    selectors = dependency_selectors(target)
    roles = ["core"]
    if "git" in selectors:
        roles.append("git")
    if len(selectors) > len(roles):
        roles.append("diagnostics")
    return TargetCompileSpec(
        target=target,
        required_fields=tuple(COMMON_FIELDS[target]),
        derived_fields=derived,
        semantic_fields=tuple(semantic),
        owner_receipt_fields=owner,
        optional_semantic_fields=tuple(optional_semantic),
        optional_owner_fields=tuple(dict.fromkeys(optional_owner)),
        dependency_roles=tuple(roles),
        dependency_selectors=selectors,
        executor_kind=executor_kind(target),
    )


TARGET_COMPILE_SPECS: dict[str, TargetCompileSpec] = {
    target: _v2_spec(target) for target in TARGETS
}


if set(TARGET_COMPILE_SPECS) != set(TARGETS):
    raise RuntimeError("TargetCompileSpec registry must cover every result target")
if set(TARGET_BUILDERS) - set(TARGET_COMPILE_SPECS):
    raise RuntimeError("TargetCompileSpec registry must cover every packet target")
for _target, _specification in TARGET_COMPILE_SPECS.items():
    _expected = frozenset(("step", *COMMON_FIELDS[_target]))
    if _specification.classified_fields != _expected:
        raise RuntimeError(f"result field provenance is incomplete for {_target}")


__all__ = [
    "DERIVED_FIELD_NAMES",
    "LEGACY_TARGET_COMPILE_SPECS",
    "TARGET_COMPILE_SPECS",
    "TargetCompileSpec",
]
