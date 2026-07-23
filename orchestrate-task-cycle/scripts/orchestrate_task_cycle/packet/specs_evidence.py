from __future__ import annotations

from typing import Any

from .context import PacketBuildContext


def build_qualitative_review(ctx: PacketBuildContext) -> dict[str, Any]:
    return {
        "skill": "$review-cycle-output-quality",
        "routing": {
            "review_agent_count": "exactly one",
            "reviewer": ctx.route("qualitative_review"),
            "reviewer_reasoning": ctx.route("qualitative_review")[
                "requested_reasoning_effort"
            ],
            "access": "read-only direct inspection of task output artifacts",
            "implementation_edits": "forbidden",
        },
        "required_inputs": [
            "run result status and evidence paths",
            "generated output artifact paths from run/governance evidence",
            "validation set artifact paths when the task produced or consumed validation assets",
            "task acceptance criteria or output expectations",
            "authority_policy and no-overclaim constraints",
            "active non-GT external advice packet when relevant",
            "schema/contract summaries that define output expectations",
            "output_delta_contract_packet when available; call the contract helper on produced artifact paths",
        ],
        "required_outputs": [
            "task_id",
            "review_agent_count: 1",
            "review_status",
            "quality_verdict",
            "reviewed_artifacts",
            "qualitative_findings",
            "direction_recommendations",
            "blocker_taxonomy_delta",
            "output_delta_status",
            "produced_domain_delta",
            "metadata_only",
            "effective_progress_kind",
            "output_delta_summary",
            "evidence_paths",
            "used_advice or advice disposition rationale when active advice is in scope",
        ],
    }


def build_loopback_audit(ctx: PacketBuildContext) -> dict[str, Any]:
    return {
        "skill": "$audit-cycle-loopback",
        "routing": {
            "phase": "post-review anti-loop packet production",
            "optional_threshold_reviewer": ctx.route("loopback_analysis"),
            "implementation_edits": "forbidden",
            "truth_policy": "recompute from raw artifacts and registry; do not trust self-declared progress",
        },
        "required_inputs": [
            "run result status and safe scalar provider counts",
            "generated output artifact paths from run/governance/review evidence",
            "qualitative review packet when available",
            "artifact_family and semantic_signature",
            ".task/anti_loop/family_progress_registry.jsonl when present",
            "active non-GT external advice packet when relevant",
            "acceptance_scenarios, command_argv/provenance, blocker_actionability, stochastic variance, and instrumentation first-fire fields from prior packets when present",
            "Part K expectation lineage, parity/adoption, evidence-resolution, and report-key integrity fields from prior packets when present",
        ],
        "required_outputs": [
            "task_id",
            "cycle_id",
            "family_key",
            "changed_vs_previous",
            "semantic_progress",
            "same_family_micro_hardening_count",
            "provider_request_count",
            "quality_vector",
            "recommended_disposition",
            "hard_stop_required",
            "decision_contract_version=1 plus explicit required/consumed gate scopes",
            "hash-bound anti_loop_handoff version 1 with applicability, packet/artifact identity, compatible/incompatible gate IDs, and allowed_next_action_classes",
            "full consumer invocation receipts for acceptance-required adapter hooks",
            "verification_axes with coupling_status and evidence_provenance when verification evidence is consumed",
            "evidence_class",
            "acceptance_scenario_gate, command_provenance_gate, blocker_actionability_gate, stochastic_feasibility_gate, and instrumentation_first_fire_gate when corresponding evidence is present",
            "expectation_lineage_gate, comparison_parity_gate, adoption_axis_gate, resolution_downgrade_gate, and report_key_integrity_gate when corresponding evidence is present",
            "evidence_paths",
        ],
    }


def build_validation_set_build(ctx: PacketBuildContext) -> dict[str, Any]:
    return {
        "skill": "$build-validation-set-with-agents",
        "mode": "build",
        "routing": {
            "phase": "post-run validation asset production or refresh",
            "reasoning": "use independent labeler/adjudicator agents only for semantic labels; deterministic scripts first",
            "semantic_labeler": ctx.route("validation_set"),
            "final_adjudicator": ctx.route("validation_set_adjudication"),
            "implementation_edits": "forbidden",
            "quality_claim": "default not_gold unless human-reviewed or fully deterministic authoritative evidence exists",
        },
        "required_inputs": [
            "validation_set_plan result or build-only task rationale",
            "run output artifact paths or explicit no-run reason",
            "qualitative review findings or not_applicable/blocker reason",
            "source locators, source hashes, and source_class policy",
            ".schema/.contract validation-set contracts when present",
            "authority_policy and no-overclaim policy",
            "active non-GT external advice disposition",
            "acceptance_scenarios from validation_set_plan or normalized acceptance when present",
        ],
        "required_outputs": [
            "step: validation_set_build",
            "task_id",
            "validation_set_status",
            "when built: validation_set_id, quality_tier, not_gold, item_count, label_count, oracle_count, source_class_distribution",
            "when built: oracle_manifest_path, split_manifest_path, leakage_report_path, validation_set_root_path",
            "when not_applicable/skipped: concrete reason and no fabricated manifest/root paths",
            "candidate scenario invocation supply and hashed evidence when scenario-shaped acceptance is in scope; do not claim completion coverage until run emits a full premise_receipts row",
            "evidence_paths",
            "used_advice or advice disposition rationale when active advice is in scope",
        ],
        "forbidden_bypasses": [
            "raw body persistence",
            "fixture or metadata promotion to sampled-real evidence",
            "gold claim without human-reviewed or deterministic authoritative evidence",
            "sealed holdout label exposure to implementation workers",
        ],
    }


def build_visible_increment(ctx: PacketBuildContext) -> dict[str, Any]:
    return {
        "skill": "$record-visible-increment",
        "routing": {
            "phase": "post-evidence visible-delta recording",
            "agent_routing_applicability": "deterministic_only",
            "validation_boundary": "context only; never validation evidence",
        },
        "required_inputs": [
            "cycle_id and current/completed task_id",
            "implementation/run/schema evidence already produced",
            "output-delta result when an output-delta contract exists",
            "changed files and user-visible artifact paths",
        ],
        "required_outputs": [
            "step: visible_increment",
            "cycle_id",
            "task_id",
            "status: recorded",
            "summary",
            "delta_types including explicit [] or none",
            "changed_files and artifacts including explicit []",
            "not_validation_evidence: true",
            "blockers including explicit []",
            "evidence_paths",
        ],
        "forbidden_bypasses": [
            "using the visible-increment record as validation evidence",
            "claiming advanced progress from metadata-only or workflow-only output",
        ],
    }


def build_repo_skill_gap_analysis(ctx: PacketBuildContext) -> dict[str, Any]:
    return {
        "skill": "$orchestrate-task-cycle",
        "mode": "pre_derive_gap_analysis",
        "routing": {
            "phase": "repo-local reusable capability gap analysis",
            "agent_routing_applicability": "deterministic_only",
        },
        "required_inputs": [
            "current-cycle task_miss and friction evidence",
            "repo_skill_adapter_packet and adapter validation result",
            "run/review/loopback/validation-set evidence",
        ],
        "required_outputs": [
            "step: repo_skill_gap_analysis",
            "task_id",
            "gap_analysis_status",
            "gap_count including explicit zero",
            "repo_skill_gap_packet with select/defer/reject recommendation",
            "blockers including explicit []",
            "evidence_paths",
        ],
    }


def build_cycle_efficiency_profile(ctx: PacketBuildContext) -> dict[str, Any]:
    return {
        "skill": "$profile-cycle-efficiency",
        "routing": {
            "phase": "pre-validation and pre-derive efficiency profile",
            "agent_routing_applicability": "deterministic_only",
        },
        "required_inputs": [
            "cycle ledger",
            "run IDs",
            "output-delta/loopback evidence",
            "task-pack and blocker-family scope",
        ],
        "required_outputs": [
            "step: cycle_efficiency_profile",
            "task_id",
            "status",
            "cycle_fixed_cost",
            "cycle_cost_basis",
            "execution_starvation when applicable",
            "recommendation",
            "blockers including explicit []",
            "evidence_paths",
        ],
    }


def build_validation_scope_finalize(ctx: PacketBuildContext) -> dict[str, Any]:
    return {
        "skill": "$plan-validation-scope",
        "mode": "post_change_finalize",
        "routing": {
            "phase": "final validation scope from actual changed files",
            "agent_routing_applicability": "deterministic_only",
        },
        "required_inputs": [
            "validation_scope_plan manifest",
            "governance actual changed_files",
            "code_structure_audit validation_scope_delta",
            "run/review/loopback/validation-set evidence",
        ],
        "required_outputs": [
            "step: validation_scope_finalize",
            "task_id",
            "mode: finalize",
            "validation_profile",
            "profile_floor and profile_changed",
            "planned_changed_files and actual_changed_files",
            "changed_surfaces and surface_counts",
            "required_commands and reused_prerequisites",
            "escalation_reasons, rationale, finalized: true, and findings",
            "evidence_paths",
        ],
    }


def build_index_pre_validate(ctx: PacketBuildContext) -> dict[str, Any]:
    return {
        "skill": "$manage-task-state-index",
        "mode": "pre_validation_snapshot",
        "routing": {
            "phase": "pre-validation traceability snapshot",
            "agent_routing_applicability": "deterministic_only",
        },
        "required_inputs": [
            "current task and cycle artifacts",
            "run/review/loopback evidence",
            "final validation-scope manifest",
        ],
        "required_outputs": [
            "step: index_pre_validate",
            "task_id",
            "index_status",
            "index_snapshot_id",
            "blockers including explicit []",
            "audit_observation_scope",
            "live_revalidation_required",
            "prevalidation_owner_result_binding",
            "evidence_paths",
        ],
    }
