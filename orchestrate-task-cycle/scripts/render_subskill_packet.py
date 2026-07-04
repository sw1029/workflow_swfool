#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


TARGETS = {
    "governance",
    "validation_set_plan",
    "code_structure_audit",
    "run",
    "qualitative_review",
    "loopback_audit",
    "validation_set_build",
    "schema_pre_derive",
    "derive",
    "schema_post_derive",
    "index",
    "validate",
    "issue",
    "commit",
    "report",
    "closeout_commit",
}

OUTPUT_DELTA_CONTRACT_CANDIDATES = (
    ".task/contracts/output_delta_contract.json",
    ".agent_goal/output_delta_contract.json",
)


def load_json(path_value: str | None) -> dict[str, Any]:
    if not path_value:
        return {}
    if path_value == "-":
        raw = sys.stdin.read()
        return json.loads(raw) if raw.strip() else {}
    stripped = path_value.strip()
    if stripped.startswith("{") or stripped.startswith("["):
        return json.loads(stripped)
    path = Path(path_value)
    try:
        if path.exists():
            raw = path.read_text(encoding="utf-8")
            return json.loads(raw) if raw.strip() else {}
    except OSError:
        pass
    return json.loads(stripped)


def deep_get(data: dict[str, Any], *keys: str) -> Any:
    current: Any = data
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def goal_truth(context: dict[str, Any]) -> list[str]:
    used = deep_get(context, "agent_goal", "used_goal_truth")
    if isinstance(used, list):
        return [str(item) for item in used]
    return []


def available_goal_truth(context: dict[str, Any]) -> list[str]:
    available = deep_get(context, "agent_goal", "available_goal_truth")
    if isinstance(available, list):
        return [str(item) for item in available]
    files = deep_get(context, "agent_goal", "goal_truth_files")
    if isinstance(files, dict):
        return [str(item.get("path")) for item in files.values() if isinstance(item, dict) and item.get("exists")]
    return []


def active_advice(context: dict[str, Any]) -> list[dict[str, Any]]:
    value = deep_get(context, "external_advice", "active_files")
    if isinstance(value, list):
        workspace = context.get("workspace")
        root = Path(str(workspace)) if workspace else None
        return [enrich_advice(item, root) for item in value if isinstance(item, dict)]
    return []


def output_delta_contract_packet(context: dict[str, Any]) -> dict[str, Any] | None:
    workspace = context.get("workspace")
    if not workspace:
        return None
    root = Path(str(workspace))
    for relative in OUTPUT_DELTA_CONTRACT_CANDIDATES:
        path = root / relative
        if not path.is_file():
            continue
        try:
            contract = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"status": "malformed", "path": relative}
        if not isinstance(contract, dict):
            return {"status": "malformed", "path": relative}
        provider = contract.get("output_delta_provider") if isinstance(contract.get("output_delta_provider"), dict) else {}
        return {
            "status": "available",
            "path": relative,
            "output_layer_paths": contract.get("output_layer_paths") or [],
            "positive_evidence_predicate": contract.get("positive_evidence_predicate"),
            "provider_kind": provider.get("kind"),
            "provider_entry": provider.get("entry"),
            "gate_contract": "Call scripts/output_delta_contract.py before qualitative_review/derive when artifact paths are available.",
        }
    return {"status": "not_applicable_no_contract"}


def section_lines(text: str) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for line in text.splitlines():
        if line.startswith("## "):
            current = line[3:].strip()
            sections.setdefault(current, [])
            continue
        if current:
            sections[current].append(line)
    return sections


def section_text(lines: list[str], limit: int = 700) -> str:
    value = " ".join(line.strip() for line in lines if line.strip())
    if len(value) > limit:
        return value[: limit - 3].rstrip() + "..."
    return value


def section_bullets(lines: list[str], limit: int = 8) -> list[str]:
    values: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("- ") or stripped.startswith("* "):
            values.append(stripped[2:].strip())
        elif values and not stripped.startswith("#"):
            values[-1] = f"{values[-1]} {stripped}"
    return values[:limit]


def parse_advice_document(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8", errors="replace")
    metadata: dict[str, str] = {}
    for line in text.splitlines():
        if line.startswith("## "):
            break
        stripped = line.strip()
        if not stripped.startswith("- ") or ":" not in stripped:
            continue
        key, value = stripped[2:].split(":", 1)
        metadata[key.strip()] = value.strip()
    sections = section_lines(text)
    return {
        "advice_id": metadata.get("advice_id"),
        "status": metadata.get("status"),
        "not_goal_truth": metadata.get("not_goal_truth"),
        "raw_source_path": metadata.get("raw_source_path"),
        "scope": metadata.get("scope"),
        "priority": metadata.get("priority"),
        "source_label": metadata.get("source_label"),
        "summary": section_text(sections.get("Summary", [])),
        "actionable_directives": section_bullets(sections.get("Actionable Directives", [])),
        "application_gates": section_bullets(sections.get("Application Gates", [])),
        "evidence_to_mark_applied": section_bullets(sections.get("Evidence To Mark Applied", []), limit=5),
        "exclusions": section_bullets(sections.get("Exclusions", []), limit=5),
    }


def enrich_advice(item: dict[str, Any], root: Path | None) -> dict[str, Any]:
    enriched = dict(item)
    path_value = item.get("path")
    if not path_value or root is None:
        return enriched
    path = root / str(path_value)
    if not path.is_file():
        return enriched
    parsed = parse_advice_document(path)
    for key, value in parsed.items():
        if value:
            enriched[key] = value
    if parsed.get("source_label"):
        enriched["title"] = parsed["source_label"]
    return enriched


def authority_policy(stage: dict[str, Any]) -> str:
    value = stage.get("authority_policy") or deep_get(stage, "packet", "authority_policy") or deep_get(stage, "routing", "authority_policy")
    if value:
        return str(value)
    return "default_current_agent_permissions"


def task_summary(context: dict[str, Any]) -> str:
    task = context.get("task_md") if isinstance(context.get("task_md"), dict) else {}
    if not task or not task.get("exists"):
        return "task.md absent"
    title = task.get("title") or "task.md"
    return f"{task.get('path', 'task.md')} ({title})"


def counts(context: dict[str, Any]) -> dict[str, Any]:
    return {
        "task_miss_active": deep_get(context, "task_state", "task_miss", "active_count") or 0,
        "candidate_count": deep_get(context, "task_state", "candidate_task", "count") or 0,
        "task_pack_count": deep_get(context, "task_state", "task_pack", "count") or 0,
        "task_pack_active": deep_get(context, "task_state", "task_pack", "active_count") or 0,
        "issue_active": deep_get(context, "issue", "active_count") or 0,
        "schema_count": deep_get(context, "schema", "count") or 0,
        "contract_count": deep_get(context, "contract", "count") or 0,
        "agent_log_count": deep_get(context, "agent_log", "markdown_count") or 0,
        "external_advice_active": deep_get(context, "external_advice", "active_count") or 0,
        "validation_set_count": deep_get(context, "validation_assets", "sets", "count") or 0,
        "cycle_validation_set_count": deep_get(context, "task_state", "validation_set", "count") or 0,
    }


def packet_for(target: str, context: dict[str, Any], stage: dict[str, Any]) -> dict[str, Any]:
    gt = goal_truth(context)
    available_gt = available_goal_truth(context)
    authority = authority_policy(stage)
    base: dict[str, Any] = {
        "target": target,
        "workspace": context.get("workspace"),
        "task": task_summary(context),
        "authority_policy": authority,
        "available_goal_truth": available_gt,
        "used_goal_truth": gt,
        "used_advice": active_advice(context),
        "advice_not_goal_truth": True,
        "context_counts": counts(context),
        "routing_reference": "/home/swfool/.codex/skills/orchestrate-task-cycle/references/workflow-routing.md",
    }
    output_delta_packet = output_delta_contract_packet(context)
    if output_delta_packet:
        base["output_delta_contract_packet"] = output_delta_packet
    active_pack = deep_get(context, "task_state", "task_pack", "active_pack")
    if isinstance(active_pack, dict) and active_pack:
        base["task_pack_packet"] = active_pack
    if target == "governance":
        base.update(
            {
                "skill": "$task-md-agent-governance",
                "routing": {
                    "code_analysis_minimum": "reasoning_effort: high",
                    "important_review": "reasoning_effort: xhigh",
                    "code_worker_model": "gpt-5.5",
                    "code_worker_reasoning_default": "medium",
                    "code_worker_reasoning_high_reliability": "high",
                    "id_correction": "reasoning_effort: medium via $manage-task-state-index",
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
                "forbidden_bypasses": ["implementation edits outside $task-md-agent-governance", "stale historical worker-model routing"],
            }
        )
    elif target == "validation_set_plan":
        base.update(
            {
                "skill": "$build-validation-set-with-agents",
                "mode": "plan",
                "routing": {
                    "phase": "pre-implementation validation asset planning",
                    "reasoning": "use xhigh planning agents when agent delegation is available",
                    "implementation_edits": "forbidden",
                    "label_visibility": "public criteria only; sealed labels must not be exposed to implementation workers",
                },
                "required_inputs": [
                    "task.md or initial_init context",
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
        )
    elif target == "code_structure_audit":
        base.update(
            {
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
        )
    elif target == "run":
        base.update(
            {
                "skill": "$run-task-code-and-log",
                "routing": {
                    "execution_source": "task.md commands or governance result only",
                    "validation_profile": "current_only|affected_chain|full_chain from task/validation scope manifest",
                    "running_status": "running is in-progress evidence, not success",
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
                    "full body-free command_argv for live execution, or command_provenance_missing=true",
                    "blocker_actionability fields or blocker_opacity for gate/validator reason codes",
                    "observed_producer_claim residual blockers as trace-only scenario review evidence when present",
                ],
            }
        )
    elif target == "qualitative_review":
        base.update(
            {
                "skill": "$review-cycle-output-quality",
                "routing": {
                    "review_agent_count": "exactly one",
                    "reviewer_reasoning": "reasoning_effort: xhigh when available",
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
        )
    elif target == "loopback_audit":
        base.update(
            {
                "skill": "$audit-cycle-loopback",
                "routing": {
                    "phase": "post-review anti-loop packet production",
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
                    "evidence_class",
                    "acceptance_scenario_gate, command_provenance_gate, blocker_actionability_gate, stochastic_feasibility_gate, and instrumentation_first_fire_gate when corresponding evidence is present",
                    "expectation_lineage_gate, comparison_parity_gate, adoption_axis_gate, resolution_downgrade_gate, and report_key_integrity_gate when corresponding evidence is present",
                    "evidence_paths",
                ],
            }
        )
    elif target == "validation_set_build":
        base.update(
            {
                "skill": "$build-validation-set-with-agents",
                "mode": "build",
                "routing": {
                    "phase": "post-run validation asset production or refresh",
                    "reasoning": "use independent labeler/adjudicator agents only for semantic labels; deterministic scripts first",
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
                    "task_id",
                    "validation_set_id",
                    "validation_set_status",
                    "quality_tier",
                    "not_gold",
                    "item_count",
                    "label_count",
                    "oracle_count",
                    "source_class_distribution",
                    "oracle_manifest_path",
                    "split_manifest_path",
                    "leakage_report_path",
                    "validation_set_root_path",
                    "scenario_coverage, scenario_uncovered, and acceptance_inversion_candidate when scenario-shaped acceptance is in scope",
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
        )
    elif target == "schema_pre_derive":
        base.update(
            {
                "skill": "$manage-schema-contracts",
                "routing": {"phase": "pre-derive refresh", "implementation_edits": "forbidden"},
                "required_inputs": [
                    "implementation summary",
                    "execution evidence or running startup evidence",
                    "qualitative output review result when available",
                    "validation_set_build result when applicable",
                    ".agent_goal/goal_schema_contract.md when present",
                    ".schema/.contract records",
                    "changed shared schema/module/script surfaces",
                ],
                "required_outputs": ["schema_status", "evidence_paths", "changed schema/contract paths", "pending output-dependent evidence"],
            }
        )
    elif target == "derive":
        base.update(
            {
                "skill": "$derive-improvement-task",
                "routing": {
                    "all_derivation_agents": "fixed reasoning_effort: xhigh",
                    "id_consistency_agent": "fixed reasoning_effort: xhigh for this skill only",
                },
                "required_inputs": [
                    "completed task evidence or initial_init context",
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
                    "Part J anti-loop findings: scenario_uncovered, acceptance_inversion, command_provenance_missing, repeated blocker_opacity, predetermined_unreachable, floor_edge_envelope, and instrumentation_first_fire",
                    "Part K lineage/comparison findings: expectation_lineage_stale, parity_unverified, majority_vote_adoption without axis classification, measured_but_disqualified, repeated resolution_downgrade, and report_key_divergence",
                    "output_delta gate result with produced_domain_delta, metadata_only, and effective_progress_kind when available",
                    "progress loop detection result with blocker_signature, semantic_signature, goal_distance_gate, and progress_kind/governance_only evidence",
                    "task pack status/result and terminal blocker state when present",
                    "active non-GT external advice packet when present",
                ],
                "selection_rules": [
                    "consume the next safe task-pack item by promotion when an active pack is applicable",
                    "insert or reorder task-pack items only with new evidence, repeated blocker signature, missing positive input delta, or terminal blocker evidence",
                    "prefer blocker-state-transition tasks",
                    "batch adjacent no-live micro-contracts",
                    "avoid repeated safety_only tasks on the same blocker",
                    "prefer semantic_signature over volatile target_surface names when comparing loop families",
                    "require positive input delta for evidence-family tasks when the pack item or loop-breaker packet requires it",
                    "when goal_distance_gate.requires_goal_productive_next is true, select goal_productive work or record terminal_blocked",
                    "do not treat metadata-only or produced_domain_delta=false work as goal_productive; use effective_progress_kind from the output-delta gate",
                    "when the last two progress-bearing cycles are governance_only, select goal_productive work or record terminal_blocked",
                    "when the last two progress-bearing cycles are metadata_only, choose resume_primary_output, bounded source-backed run/preflight, root-cause repair, or terminal_blocked",
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
                    "loop_breaker_disposition",
                    "evidence_paths",
                    "used_advice or advice disposition rationale when active advice is in scope",
                    "degraded_agents and unavailable agent/lens notes when exact xhigh agent fanout is unavailable",
                ],
            }
        )
    elif target == "schema_post_derive":
        base.update(
            {
                "skill": "$manage-schema-contracts",
                "routing": {"phase": "post-derive planned-contract reconciliation", "implementation_edits": "forbidden"},
                "required_inputs": [
                    "new active task.md",
                    "retained candidate tasks",
                    ".agent_goal/goal_schema_contract.md when present",
                    ".schema/.contract records",
                ],
                "required_outputs": ["next_task_id", "schema_status", "evidence_paths", "planned contract paths", "needs_review items"],
            }
        )
    elif target == "index":
        base.update(
            {
                "skill": "$manage-task-state-index",
                "routing": {"id_correction": "fixed reasoning_effort: medium"},
                "required_inputs": [
                    "task.md",
                    "past_task log",
                    "candidate tasks",
                    "task_miss",
                    "issues",
                    "agent logs",
                    "schema/contract artifacts",
                    "validation set manifests, roots, oracles, splits, leakage reports, and cycle-local validation_set artifacts",
                    "validation and run artifacts",
                    "cycle ledger",
                ],
                "required_outputs": ["index_status", "audit verdict", "high-severity ID blockers"],
            }
        )
    elif target == "validate":
        base.update(
            {
                "skill": "$validate-task-completion",
                "routing": {
                    "repository_audit": "reasoning_effort: xhigh",
                    "oom_audit_when_relevant": "reasoning_effort: xhigh",
                    "id_correction": "reasoning_effort: medium via $manage-task-state-index",
                },
                "required_inputs": [
                    "implementation summary",
                    "execution log or not_applicable/blocker reason",
                    "qualitative output review result or not_applicable/blocker reason",
                    "validation set build/consume result or not_applicable/blocker reason",
                    "task_miss status",
                    "issue status",
                    "schema/contract status",
                    "validation set artifact status and not_gold/quality_tier when relevant",
                    "task-state audit",
                    "advice application/rejection/defer status when task referenced advice",
                    "Part J gates from validation-set, run, loopback, and derive packets when present",
                    "Part K gates from acceptance, run, loopback, derive, report, and validation-set packets when present",
                ],
                "required_outputs": [
                    "validation_verdict",
                    "progress_verdict",
                    "progress_axes",
                    "validation report path",
                    "acceptance_scenario_gate, command_provenance_gate, blocker_actionability_gate, stochastic_feasibility_gate, and instrumentation_first_fire_gate when applicable",
                    "expectation_lineage_gate, comparison_parity_gate, adoption_axis_gate, resolution_downgrade_gate, and report_key_integrity_gate when applicable",
                ],
            }
        )
    elif target == "issue":
        base.update(
            {
                "skill": "$manage-implementation-issues",
                "routing": {"issue_lifecycle": "after validation, before commit"},
                "required_inputs": [
                    "validation_verdict",
                    "progress_verdict",
                    "remaining blockers",
                    "run/log/miss evidence",
                    "new active task.md by default",
                ],
                "required_outputs": ["issue_status", "created/updated/closed issue paths", "blocker links"],
            }
        )
    elif target == "commit":
        base.update(
            {
                "skill": "$repo-change-commit",
                "routing": {"commit_finalization": "fixed reasoning_effort: low"},
                "required_inputs": [
                    "validation_verdict",
                    "progress_verdict",
                    "changed files",
                    "remaining blockers",
                    "issue IDs/paths when present",
                    "schema status",
                    "validation set artifact status and not_gold/quality_tier when relevant",
                    "advice status",
                ],
                "commit_gates": [
                    "run after validation and issue tracking",
                    "partial verdict requires partial/checkpoint commit intent",
                    "use commit_role: implementation",
                    "created implementation commit hash belongs only to $repo-change-commit result until report assembly",
                    "track used `.agent_advice` active/adopted files by default unless marked local_only with a reason",
                ],
                "required_outputs": [
                    "commit_role",
                    "commit_status",
                    "commit_hash and commit_subject when created",
                    "commit_skipped_reason when skipped/blocked/failed",
                    "evidence_paths",
                ],
            }
        )
    elif target == "report":
        base.update(
            {
                "skill": "$orchestrate-task-cycle",
                "routing": {"language": "Korean", "template": "references/cycle-report-template.md"},
                "required_fields_order": [
                    "기준 GT",
                    "비-GT 방향성 문서",
                    "주 진행 skill",
                    "수행한 task",
                    "변경한 파일",
                    "실행한 검증",
                    "validation verdict",
                    "progress verdict",
                    "progress axes",
                    "남은 blocker",
                    "다음 task/방향성",
                    "완료 여부",
                ],
            }
        )
    elif target == "closeout_commit":
        base.update(
            {
                "skill": "$repo-change-commit",
                "routing": {"commit_finalization": "fixed reasoning_effort: low", "phase": "closeout artifact commit after report"},
                "required_inputs": [
                    "rendered dashboard.md",
                    "final_report.md or report draft path",
                    "commit-result.json for implementation commit when present",
                    "stage.jsonl/current_stage.json updates",
                    "used `.agent_advice/active` or `.agent_advice/applied` files",
                    "local_only reason for any closeout artifact intentionally not tracked",
                ],
                "commit_gates": [
                    "use commit_role: closeout",
                    "do not backfill the closeout commit hash into a report that is part of that same commit",
                    "create a closeout commit when report/dashboard/advice artifacts are intentional and coherent",
                    "skip only with commit_skipped_reason",
                ],
                "required_outputs": [
                    "commit_role",
                    "commit_status",
                    "tracked_artifacts",
                    "commit_hash and commit_subject when created",
                    "commit_skipped_reason when skipped/blocked/failed",
                    "evidence_paths",
                ],
            }
        )
    return base


def render_markdown(packet: dict[str, Any]) -> str:
    lines = [f"# Subskill Packet: {packet['target']}", ""]
    for key in ("skill", "mode", "workspace", "task", "authority_policy", "routing_reference"):
        if key in packet:
            lines.append(f"- {key}: {packet[key]}")
    lines.append("")
    lines.append("## Available Goal Truth")
    available = packet.get("available_goal_truth") or []
    if available:
        lines.extend(f"- {item}" for item in available)
    else:
        lines.append("- 없음")
    lines.append("")
    lines.append("## Used Goal Truth")
    gt = packet.get("used_goal_truth") or []
    if gt:
        lines.extend(f"- {item}" for item in gt)
    else:
        lines.append("- 없음")
    lines.append("")
    lines.append("## Non-GT Direction Advice")
    advice = packet.get("used_advice") or []
    if advice:
        for item in advice:
            if isinstance(item, dict):
                lines.append(f"### {item.get('advice_id') or item.get('path')}")
                lines.append(f"- path: {item.get('path')}")
                lines.append(f"- title: {item.get('title') or item.get('source_label') or 'external advice'}")
                for key in ("status", "priority", "scope", "not_goal_truth", "raw_source_path"):
                    if item.get(key):
                        lines.append(f"- {key}: {item.get(key)}")
                if item.get("summary"):
                    lines.append(f"- summary: {item.get('summary')}")
                for key in ("actionable_directives", "application_gates", "evidence_to_mark_applied", "exclusions"):
                    values = item.get(key)
                    if isinstance(values, list) and values:
                        lines.append(f"- {key}:")
                        lines.extend(f"  - {value}" for value in values)
            else:
                lines.append(f"- {item}")
    else:
        lines.append("- 없음")
    for section_key in ("routing", "task_pack_packet", "required_inputs", "required_outputs", "selection_rules", "commit_gates", "forbidden_bypasses", "required_fields_order", "context_counts"):
        value = packet.get(section_key)
        if not value:
            continue
        title = section_key.replace("_", " ").title()
        lines.extend(["", f"## {title}"])
        if isinstance(value, dict):
            lines.extend(f"- {key}: {item}" for key, item in value.items())
        elif isinstance(value, list):
            lines.extend(f"- {item}" for item in value)
        else:
            lines.append(f"- {value}")
    return "\n".join(lines).rstrip() + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render a routing packet for an orchestrate-task-cycle subskill call.")
    parser.add_argument("--target", required=True, choices=sorted(TARGETS))
    parser.add_argument("--context", help="Cycle context JSON path, or '-' for stdin.")
    parser.add_argument("--stage", help="Optional stage/status JSON path.")
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    args = parser.parse_args(argv)

    context = load_json(args.context)
    stage = load_json(args.stage)
    packet = packet_for(args.target, context, stage)
    if args.format == "json":
        json.dump(packet, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(render_markdown(packet))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
