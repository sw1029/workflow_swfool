from __future__ import annotations

from typing import Any

from .context import PacketBuildContext


def build_repo_skill_adapter_scan(ctx: PacketBuildContext) -> dict[str, Any]:
    return {
        "skill": "$orchestrate-task-cycle",
        "mode": "metadata_only",
        "routing": {
            "phase": "pre-acceptance repo-local adapter discovery",
            "agent_routing_applicability": "deterministic_only",
        },
        "required_inputs": [
            "cycle_id",
            "workspace `.codex/skills/*/SKILL.md` frontmatter",
            "optional adapter.manifest.json metadata",
            "optional adapter packet renderer existence",
            "previous adapter validation status when available",
        ],
        "required_outputs": [
            "step: repo_skill_adapter_scan",
            "cycle_id",
            "adapter_scan_status",
            "adapter_count including explicit zero",
            "repo_skill_adapter_packet with IDs, paths, statuses, renderer availability, and non-GT warning",
            "blockers including explicit []",
            "evidence_paths",
        ],
        "forbidden_bypasses": [
            "loading long adapter bodies during metadata scan",
            "treating adapters as GT or authority",
        ],
    }


def build_acceptance(ctx: PacketBuildContext) -> dict[str, Any]:
    return {
        "skill": "$normalize-acceptance-and-demo",
        "routing": {
            "phase": "task-bound acceptance normalization after adapter scan",
            "agent_routing_applicability": "deterministic_only",
        },
        "required_inputs": [
            "active task.md created before this normal cycle",
            "authority_policy",
            "repo_skill_adapter_packet and acceptance-relevant adapter hooks",
            "active non-GT advice packet when present",
            "schema/contract summaries",
        ],
        "required_outputs": [
            "step: acceptance",
            "acceptance_id",
            "task_id",
            "acceptance_status",
            "acceptance_provenance.source_task_id matching task_id",
            "acceptance_provenance.source_task_path",
            "acceptance_provenance.source_task_fingerprint",
            "acceptance_criteria and preserved measurable encodings",
            "blockers including explicit []",
            "evidence_paths",
        ],
        "forbidden_bypasses": [
            "normalizing acceptance before task.md exists",
            "reusing acceptance from another task fingerprint",
        ],
    }


def build_validation_scope_plan(ctx: PacketBuildContext) -> dict[str, Any]:
    return {
        "skill": "$plan-validation-scope",
        "mode": "pre_change_plan",
        "routing": {
            "phase": "planned change-surface validation scope",
            "agent_routing_applicability": "deterministic_only",
        },
        "required_inputs": [
            "task.md",
            "acceptance packet",
            "planned touch surfaces",
            "adapter gate/artifact compatibility when supplied",
        ],
        "required_outputs": [
            "step: validation_scope_plan",
            "task_id",
            "mode: plan",
            "validation_profile",
            "profile_floor and profile_changed",
            "planned_changed_files and explicit empty actual_changed_files",
            "changed_surfaces and surface_counts",
            "required_commands and reused_prerequisites",
            "escalation_reasons, rationale, finalized: false, and findings",
            "evidence_paths",
        ],
    }


def build_governance(ctx: PacketBuildContext) -> dict[str, Any]:
    return {
        "skill": "$task-md-agent-governance",
        "routing": {
            "code_analysis": ctx.route("code_analysis"),
            "important_review": ctx.route("important_review"),
            "code_worker": ctx.route("code_worker"),
            "code_worker_high_reliability": ctx.route("code_worker_high_reliability"),
            "id_correction": ctx.route("id_index"),
            "code_worker_model": ctx.route("code_worker")["requested_model"],
        },
        "required_inputs": [
            "task.md",
            "authority_policy",
            "used_goal_truth",
            ".agent_goal/goal_schema_contract.md when present",
            ".schema/.contract records when relevant",
            ".task/index when available",
            "active `.agent_advice/active` packet when present",
        ],
        "forbidden_bypasses": [
            "implementation edits outside $task-md-agent-governance",
            "stale historical worker-model routing",
        ],
    }


def build_validation_set_plan(ctx: PacketBuildContext) -> dict[str, Any]:
    return {
        "skill": "$build-validation-set-with-agents",
        "mode": "plan",
        "routing": {
            "phase": "pre-implementation validation asset planning",
            "planning_agents": ctx.route("validation_set"),
            "final_adjudication": ctx.route("validation_set_adjudication"),
            "implementation_edits": "forbidden",
            "label_visibility": "public criteria only; sealed labels must not be exposed to implementation workers",
        },
        "required_inputs": [
            "active task.md; initial_init must finish in a separate bootstrap transaction",
            "authority_policy",
            "available_goal_truth and used_goal_truth",
            "active non-GT external advice packet when present",
            ".schema/.contract summaries",
            "existing `.validation/sets` registry or inventory",
            ".task/task_miss and .issue validation gaps",
            "source_class and no-overclaim policy",
            "normalized acceptance_scenarios when scenario-shaped acceptance exists",
        ],
        "required_outputs": [
            "step: validation_set_plan",
            "task_id",
            "validation_set_need",
            "task_family",
            "failure_taxonomy",
            "oracle_strategy",
            "split_strategy",
            "leakage_policy",
            "label_visibility_policy",
            "scenario_coverage requirements, or scenario_uncovered with missing premise-satisfying input reason",
            "evidence_paths",
            "used_advice or advice disposition rationale when active advice is in scope",
        ],
    }


def build_repo_skill_adapter_validate(ctx: PacketBuildContext) -> dict[str, Any]:
    return {
        "skill": "$orchestrate-task-cycle applying $skill-creator validation rules",
        "mode": "post_governance_adapter_validation",
        "routing": {
            "phase": "validate changed repo-local adapters before consumption",
            "agent_routing_applicability": "deterministic_only",
        },
        "required_inputs": [
            "governance changed_files",
            "repo_skill_adapter_packet",
            "changed `.codex/skills/` paths or explicit no-change evidence",
            "$skill-creator quick_validate.py when available",
            "adapter-local representative checks when scripts changed",
        ],
        "required_outputs": [
            "step: repo_skill_adapter_validate",
            "task_id",
            "adapter_validation_status",
            "adapter_change_count including explicit zero",
            "adapter_validation_count including explicit zero",
            "blockers including explicit []",
            "evidence_paths",
        ],
        "forbidden_bypasses": [
            "consuming an invalid changed adapter",
            "patching adapter files from the validation phase",
        ],
    }


def build_code_structure_audit(ctx: PacketBuildContext) -> dict[str, Any]:
    return {
        "skill": "$orchestrate-task-cycle",
        "helper": "scripts/code_structure_audit.py",
        "routing": {
            "phase": "post-governance pre-run structure gate",
            "implementation_edits": "forbidden",
            "refactor_owner": "$task-md-agent-governance in a later or rerouted implementation task",
            "reference": "references/code-structure-audit.md",
        },
        "required_inputs": [
            "governance changed_files list when available",
            "changed implementation source files",
            "task_id",
            "optional code_convention_contract or convention-json path when available",
            "explicit generated/vendor/migration/snapshot exemptions when applicable",
            "public API, CLI, schema, artifact-path, and test compatibility constraints when known",
        ],
        "required_outputs": [
            "task_id",
            "audit_status: pass|warn|refactor_required|blocked|not_applicable",
            "changed_files_scanned",
            "oversize_files",
            "thresholds",
            "responsibility_clusters",
            "semantic_structure_metrics",
            "semantic_structure_findings",
            "convention_conformance",
            "moduleization_required",
            "suggested_module_root",
            "responsibility_split_plan",
            "semantic_refactor_plan",
            "compatibility_constraints",
            "validation_scope_delta",
            "existing_debt_exemptions",
            "forbidden_raw_source_persisted: true",
            "evidence_paths",
        ],
        "forbidden_bypasses": [
            "creating module directories in this phase",
            "moving code in this phase",
            "patching implementation files in this phase",
            "persisting raw source bodies in workflow artifacts",
        ],
    }


def build_run(ctx: PacketBuildContext) -> dict[str, Any]:
    return {
        "skill": "$run-task-code-and-log",
        "routing": {
            "execution_source": "task.md commands or governance result only",
            "validation_profile": "current_only|affected_chain|full_chain from task/validation scope manifest",
            "running_status": "running is in-progress evidence, not success",
            "long_run_branch": "keep step=run and use event_kind long_run_launch|long_run_monitor|long_run_harvest|long_run_finalize",
        },
        "required_inputs": [
            "governance result",
            "validation_set_plan public criteria when present",
            "task-declared command or explicit not_applicable/blocker reason",
            "validation scope manifest when present",
            "validation set root/oracle/split hashes when consuming an existing validation set",
            "evidence-cache reuse candidate when present",
            "long-running authorization and monitor/stop details when applicable",
        ],
        "required_outputs": [
            "execution_status",
            "commands or not_applicable reason",
            "evidence_paths",
            "failure_autopsy for failed/nonzero execution when safe scalar extraction is possible",
            "running details when execution_status is running",
            "for long_run_branch=true: run_id, owner_task_id, launch_cycle_id, command_argv, workdir, output_dir, log_path, heartbeat, monitor_command, stop_command, remaining_validation, expected_completion_signal, expected_completion_artifacts",
            "long_run_role launch|monitor|harvest|finalize and residual/harvest task link when launch only starts the work",
            "full body-free command_argv for live execution, or command_provenance_missing=true",
            "blocker_actionability fields or blocker_opacity for gate/validator reason codes",
            "observed_producer_claim residual blockers as trace-only scenario review evidence when present",
        ],
    }
