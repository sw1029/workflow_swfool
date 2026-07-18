from __future__ import annotations

from typing import Any

from .context import PacketBuildContext


def build_schema_pre_derive(ctx: PacketBuildContext) -> dict[str, Any]:
    return {
        "skill": "$manage-schema-contracts",
        "routing": {
            "phase": "pre-derive refresh",
            "schema_planning": ctx.route("schema_planning"),
            "implementation_edits": "forbidden",
        },
        "required_inputs": [
            "current-task validation result",
            "issue lifecycle packet",
            "implementation summary",
            "execution evidence or running startup evidence",
            "qualitative output review result when available",
            "validation_set_build result when applicable",
            ".agent_goal/goal_schema_contract.md when present",
            ".schema/.contract records",
            "changed shared schema/module/script surfaces",
        ],
        "required_outputs": [
            "schema_status",
            "evidence_paths",
            "changed schema/contract paths",
            "pending output-dependent evidence",
        ],
    }


def build_derive(ctx: PacketBuildContext) -> dict[str, Any]:
    return {
        "skill": "$derive-improvement-task",
        "routing": {
            "evidence_inspectors": ctx.route("derive_inspector"),
            "cross_contract_analysis": ctx.route("derive_cross_contract"),
            "synthesis": ctx.route("derive_synthesis"),
            "exceptional_arbitration": ctx.route("exceptional_arbitration"),
            "id_consistency": ctx.route("id_index"),
            "max_requires": "Tier 5 direction-profile/xhigh ran first, prior_tier5_unresolved=true, prior_tier5_evidence, one agent, and max_escalation_reason",
        },
        "required_inputs": [
            "validated completed-task evidence",
            "validation result for the current task",
            "issue lifecycle packet for the current task and its blockers",
            "authority_policy",
            "used_goal_truth",
            ".task/task_miss",
            ".task/candidate_task",
            ".task/task_pack active pack summary when present",
            ".issue",
            ".schema/.contract",
            ".validation/sets and validation_set_build result when present",
            "qualitative output review result and direction recommendations",
            "anti-loop progress gate with changed_vs_previous, semantic_progress, same-family micro-hardening count, and recommended disposition",
            "hash-bound anti-loop handoff; or a reasoned not_applicable contract only for initial/standalone derive",
            "six preserved verdict axes from validation, pack transition, index, and goal readiness",
            "verified current cycle_finalization_receipt and receipt-bound authoritative_projection for ordinary predecessor consumption",
            "Part J anti-loop findings: scenario_uncovered, acceptance_inversion, command_provenance_missing, repeated blocker_opacity, predetermined_unreachable, floor_edge_envelope, and instrumentation_first_fire",
            "Part K lineage/comparison findings: expectation_lineage_stale, parity_unverified, majority_vote_adoption without axis classification, measured_but_disqualified, repeated resolution_downgrade, and report_key_divergence",
            "output_delta gate result with produced_domain_delta, metadata_only, and effective_progress_kind when available",
            "progress loop detection result with blocker_signature, semantic_signature, goal_distance_gate, and progress_kind/governance_only evidence",
            "task pack status/result and terminal blocker state when present",
            "active non-GT external advice packet when present",
            "one frozen shared evidence manifest with exact artifact/body/lane/input identity",
            "adapter_decision_context and hash-bound adapter_post_use_seal, or evidenced no_registered_adapter applicability",
        ],
        "selection_rules": [
            "consume/promote the next safe task-pack item only after current-task validation and issue handling",
            "insert or reorder task-pack items only with new evidence, repeated blocker signature, missing positive input delta, or terminal blocker evidence",
            "prefer blocker-state-transition tasks",
            "batch adjacent no-live micro-contracts",
            "avoid repeated safety_only tasks on the same blocker",
            "prefer semantic_signature over volatile target_surface names when comparing loop families",
            "require positive input delta for evidence-family tasks when the pack item or loop-breaker packet requires it",
            "when goal_distance_gate.requires_goal_productive_next is true, select goal_productive work or record terminal_blocked",
            "do not treat metadata-only or produced_domain_delta=false work as goal_productive; use effective_progress_kind from the output-delta gate",
            "when an evaluated caller/adapter recurrence or goal-distance budget constrains governance-only work, select an allowed producer/body, bounded execution, terminal, or escalation direction",
            "do not turn raw governance-only or metadata-only streaks into a hard threshold when the controlling budget is unverified",
            "when an active long_run_branch exists, select monitor/harvest/finalize for that run_id or record terminal/user escalation; do not select unrelated goal work until the run is resolved",
            "when selecting long_run_launch, preserve original live-run acceptance through scope_fidelity and a residual harvest task; do not consume the domain target from launch evidence",
            "route Part J findings in place: scenario supply, code/contract repair, argv rerun/provenance repair, blocker-contract repair, stochastic contract revision/descope/escalation, or single first-fire credit ownership",
            "route Part K findings in place: expectation rebaseline, parity-axis resolution, adoption-axis repair/rejection, resolution restoration/contract revision, report repair, residual descope, terminal state, or user escalation",
            "record terminal_blocked instead of deriving another narrowing task when zero viable candidates remain",
            "do not derive another non-terminal task in a sealed semantic family without a new input kind, authority change, or external-state change",
            "do not seal a blocker family unless root_cause_attempted_for_family is true or an explicit not-required rationale is recorded",
            "include validation_set_gap, oracle_gap, leakage_gap, and source_class_gap candidates when evaluation assets block progress",
            "write progress_target and validation_profile in top Execution Environment",
        ],
        "required_outputs": [
            "completed_task_id",
            "next_task_id",
            "selected_task_source: task_pack|candidate_task|standalone|terminal_blocked",
            "progress_kind: goal_productive|governance_only",
            "effective_progress_kind when output-delta review changes the selected progress classification",
            "output_delta_status and produced_domain_delta when an output-delta contract is available",
            "root_cause_attempted_for_family when sealing or terminal-blocking a blocker family",
            "semantic_signature for selected or terminal blocker family",
            "selected_task_kind that consumes any active Part J constraint",
            "selected_task_kind that consumes any active Part K constraint",
            "task_pack_status when a pack exists",
            "pack_coherence before snapshot and pack_mutation_receipt for every current pack mutation",
            "consumed_anti_loop_packet_sha256 or anti_loop_handoff_consumption receipt exactly echoing the required handoff",
            "promotion_origin plus initial/predecessor receipt reference when promoting an item",
            "retry_axis matching the failed verdict axis when retry work is selected",
            "finalization_receipt plus finalization_consumption echoing finalization_token, attempt_id, attempt_revision, authoritative_projection_id, authoritative_projection_digest, and receipt_hash",
            "authoritative_projection exactly matching the verified immutable finalization snapshot",
            "loop_breaker_disposition",
            "evidence_paths",
            "used_advice or advice disposition rationale when active advice is in scope",
            "derive_contract_version=2 and improvement_analysis_manifest schema_version=1",
            "exactly three unique read-only lens receipts with identical shared-evidence digest and structured zero-to-five candidate outputs",
            "zero-candidate rejection inventory, exact candidate union, and one synthesis receipt consuming all three lenses",
            "selection_outcome: selected|terminal_wait|terminal_blocked|user_escalation with non-contradictory outcome fields",
            "canonical pack_disposition from references/derive-selection-contract.json",
        ],
    }


def build_schema_post_derive(ctx: PacketBuildContext) -> dict[str, Any]:
    return {
        "skill": "$manage-schema-contracts",
        "routing": {
            "phase": "post-derive planned-contract reconciliation",
            "schema_planning": ctx.route("schema_planning"),
            "implementation_edits": "forbidden",
        },
        "required_inputs": [
            "new active task.md",
            "retained candidate tasks",
            ".agent_goal/goal_schema_contract.md when present",
            ".schema/.contract records",
        ],
        "required_outputs": [
            "next_task_id",
            "schema_status",
            "evidence_paths",
            "planned contract paths",
            "needs_review items",
        ],
        "terminal_or_skipped_outputs": [
            "schema_status: terminal|terminal_blocked|skipped|not_applicable|blocked|deferred",
            "concrete reason",
            "no fabricated next_task_id",
        ],
    }


def build_index(ctx: PacketBuildContext) -> dict[str, Any]:
    return {
        "skill": "$manage-task-state-index",
        "routing": {
            "id_correction": ctx.route("id_index"),
            "deterministic_scan_first": True,
        },
        "required_inputs": [
            "task.md",
            "past_task log",
            "candidate tasks",
            "task_miss",
            "issues",
            "agent logs",
            "schema/contract artifacts",
            "validation set manifests, roots, oracles, splits, leakage reports, and cycle-local validation_set artifacts",
            "pre-validation index snapshot and validation result",
            "derive and schema-post-derive artifacts",
            "cycle ledger",
        ],
        "required_outputs": [
            "index_status",
            "audit verdict",
            "high-severity ID blockers",
        ],
    }


def build_validate(ctx: PacketBuildContext) -> dict[str, Any]:
    return {
        "skill": "$validate-task-completion",
        "routing": {
            "repository_audit": ctx.route("completion_review"),
            "oom_audit_when_relevant": ctx.route("completion_review"),
            "id_correction": ctx.route("id_index"),
        },
        "required_inputs": [
            "implementation summary",
            "execution log or not_applicable/blocker reason",
            "qualitative output review result or not_applicable/blocker reason",
            "validation set build/consume result or not_applicable/blocker reason",
            "task_miss status",
            "schema/contract status",
            "final validation-scope manifest based on actual changed files",
            "pre-validation task-state index snapshot",
            "cycle-efficiency profile",
            "validation set artifact status and not_gold/quality_tier when relevant",
            "task-state audit",
            "advice application/rejection/defer status when task referenced advice",
            "Part J gates from validation-set, run, and loopback packets when present",
            "Part K gates from acceptance, run, loopback, report, and validation-set packets when present",
        ],
        "required_outputs": [
            "validation_verdict",
            "progress_verdict",
            "progress_axes",
            "finalization_contract_version=1, finalization_applicability=required, schema_version=1, kind=cycle_final_candidate, and final_candidate=true for governed completion validation",
            "cycle_id, attempt_id, and explicit expected_previous_revision/expected_previous_attempt_id/expected_previous_finalization_token including null first-publication values",
            "durable_state_candidate prepared without registry, ledger, seal, or current-pointer mutation",
            "verdict_contract_version=1 plus task_acceptance_verdict, artifact_truth_verdict, artifact_semantic_verdict, pack_transition_verdict, historical_index_verdict, and goal_readiness_verdict with evidence refs",
            "decision_contract_version=1, exact decision artifact identity, and explicit required/consumed compatibility gate scopes",
            "verification_axes and full consumer invocation receipts when required by acceptance",
            "validation report path",
            "acceptance_scenario_gate with recomputed structured premise_receipts, command_provenance_gate, blocker_actionability_gate, stochastic_feasibility_gate, and instrumentation_first_fire_gate when applicable",
            "expectation_lineage_gate, comparison_parity_gate, adoption_axis_gate, resolution_downgrade_gate, and report_key_integrity_gate when applicable",
        ],
    }
