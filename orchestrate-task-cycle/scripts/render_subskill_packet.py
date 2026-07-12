#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from result_contract_lib.session_audit import sanitize_collection_summary  # noqa: E402


TARGETS = {
    "repo_skill_adapter_scan",
    "acceptance",
    "validation_scope_plan",
    "governance",
    "validation_set_plan",
    "repo_skill_adapter_validate",
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
    "schema_pre_derive",
    "derive",
    "schema_post_derive",
    "index",
    "validate",
    "issue",
    "commit",
    "dashboard",
    "report",
    "closeout_commit",
}

OUTPUT_DELTA_CONTRACT_CANDIDATES = (
    ".task/contracts/output_delta_contract.json",
    ".agent_goal/output_delta_contract.json",
)

MODEL_EFFORT_PROFILE_PATH = Path(__file__).resolve().parents[1] / "references" / "model-effort-profiles.json"
MODEL_EFFORT_ROUTER_PATH = Path(__file__).resolve().parent / "model_effort_router.py"
ROUTING_REFERENCE_PATH = Path(__file__).resolve().parents[1] / "references" / "workflow-routing.md"


def load_model_effort_router() -> Any:
    spec = importlib.util.spec_from_file_location("orchestrate_model_effort_router", MODEL_EFFORT_ROUTER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load model-effort router: {MODEL_EFFORT_ROUTER_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MODEL_EFFORT_ROUTER = load_model_effort_router()
MODEL_EFFORT_POLICY = MODEL_EFFORT_ROUTER.load_policy(MODEL_EFFORT_PROFILE_PATH)


def routing_profile(profile_id: str, request: dict[str, Any] | None = None) -> dict[str, Any]:
    return MODEL_EFFORT_ROUTER.select_route(profile_id, request, MODEL_EFFORT_POLICY)


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


def routing_request_for(profile_id: str, context: dict[str, Any], stage: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = {"signals": {}}
    for source in (context, stage):
        routing = source.get("model_effort_routing") if isinstance(source.get("model_effort_routing"), dict) else {}
        profiles = routing.get("profiles") if isinstance(routing.get("profiles"), dict) else {}
        profile_request = profiles.get(profile_id) if isinstance(profiles.get(profile_id), dict) else {}
        profile_signals = profile_request.get("signals") if isinstance(profile_request.get("signals"), dict) else {}
        merged["signals"].update(profile_signals)
        profile_evidence = profile_request.get("signal_evidence") if isinstance(profile_request.get("signal_evidence"), dict) else {}
        if profile_evidence:
            merged.setdefault("signal_evidence", {}).update(profile_evidence)
        for field in ("final_direction_ownership", "request_max", "max_escalation_reason", "prior_tier5_evidence", "agent_count"):
            if field in profile_request:
                merged[field] = profile_request[field]
    return merged


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
        "session_audit_count": deep_get(context, "session_audit", "valid_count") or 0,
    }


def packet_for(
    target: str,
    context: dict[str, Any],
    stage: dict[str, Any],
    workflow_mode: str = "normal",
) -> dict[str, Any]:
    gt = goal_truth(context)
    available_gt = available_goal_truth(context)
    authority = authority_policy(stage)

    def route(profile_id: str) -> dict[str, Any]:
        return routing_profile(profile_id, routing_request_for(profile_id, context, stage))

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
        "routing_reference": str(ROUTING_REFERENCE_PATH),
        "model_effort_policy": {
            "policy_id": MODEL_EFFORT_POLICY["policy_id"],
            "policy_path": str(MODEL_EFFORT_PROFILE_PATH),
            "models": MODEL_EFFORT_POLICY["models"],
            "tiers": MODEL_EFFORT_POLICY["tiers"],
            "dynamic_routing_input": {
                "path": "model_effort_routing.profiles.<profile_id>",
                    "fields": ["final_direction_ownership", "signals", "signal_evidence", "request_max", "max_escalation_reason", "prior_tier5_evidence", "agent_count"],
                "allowed_signals": MODEL_EFFORT_POLICY["dynamic_signals"],
            },
            "routing_result_contract": {
                "agent_routing_applicability": "delegated|deterministic_only|delegation_unavailable",
                "routing_enforcement": MODEL_EFFORT_POLICY["result_enforcement_values"],
                "required_when_delegated": [
                    "policy_id",
                    "profile_id",
                    "routing_tier",
                    "requested_model",
                    "requested_reasoning_effort",
                    "routing_reason_codes",
                    "routing_violations",
                    "routing_enforcement",
                ],
                "optional_runtime_evidence": ["actual_model", "actual_reasoning_effort"],
                "limitation_field": "routing_limitation",
            },
        },
    }
    output_delta_packet = output_delta_contract_packet(context)
    if output_delta_packet:
        base["output_delta_contract_packet"] = output_delta_packet
    session_audit = sanitize_collection_summary(context.get("session_audit"), max_packets=12)
    if session_audit:
        base["session_audit"] = session_audit
    active_pack = deep_get(context, "task_state", "task_pack", "active_pack")
    if isinstance(active_pack, dict) and active_pack:
        base["task_pack_packet"] = active_pack
    if target == "repo_skill_adapter_scan":
        base.update(
            {
                "skill": "$orchestrate-task-cycle",
                "mode": "metadata_only",
                "routing": {"phase": "pre-acceptance repo-local adapter discovery", "agent_routing_applicability": "deterministic_only"},
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
                "forbidden_bypasses": ["loading long adapter bodies during metadata scan", "treating adapters as GT or authority"],
            }
        )
    elif target == "acceptance":
        base.update(
            {
                "skill": "$normalize-acceptance-and-demo",
                "routing": {"phase": "task-bound acceptance normalization after adapter scan", "agent_routing_applicability": "deterministic_only"},
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
                "forbidden_bypasses": ["normalizing acceptance before task.md exists", "reusing acceptance from another task fingerprint"],
            }
        )
    elif target == "validation_scope_plan":
        base.update(
            {
                "skill": "$plan-validation-scope",
                "mode": "pre_change_plan",
                "routing": {"phase": "planned change-surface validation scope", "agent_routing_applicability": "deterministic_only"},
                "required_inputs": ["task.md", "acceptance packet", "planned touch surfaces", "adapter gate/artifact compatibility when supplied"],
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
        )
    elif target == "governance":
        base.update(
            {
                "skill": "$task-md-agent-governance",
                "routing": {
                    "code_analysis": route("code_analysis"),
                    "important_review": route("important_review"),
                    "code_worker": route("code_worker"),
                    "code_worker_high_reliability": route("code_worker_high_reliability"),
                    "id_correction": route("id_index"),
                    "code_worker_model": route("code_worker")["requested_model"],
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
                    "planning_agents": route("validation_set"),
                    "final_adjudication": route("validation_set_adjudication"),
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
        )
    elif target == "repo_skill_adapter_validate":
        base.update(
            {
                "skill": "$orchestrate-task-cycle applying $skill-creator validation rules",
                "mode": "post_governance_adapter_validation",
                "routing": {"phase": "validate changed repo-local adapters before consumption", "agent_routing_applicability": "deterministic_only"},
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
                "forbidden_bypasses": ["consuming an invalid changed adapter", "patching adapter files from the validation phase"],
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
        )
    elif target == "qualitative_review":
        base.update(
            {
                "skill": "$review-cycle-output-quality",
                "routing": {
                    "review_agent_count": "exactly one",
                    "reviewer": route("qualitative_review"),
                    "reviewer_reasoning": route("qualitative_review")["requested_reasoning_effort"],
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
                    "optional_threshold_reviewer": route("loopback_analysis"),
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
        )
    elif target == "validation_set_build":
        base.update(
            {
                "skill": "$build-validation-set-with-agents",
                "mode": "build",
                "routing": {
                    "phase": "post-run validation asset production or refresh",
                    "reasoning": "use independent labeler/adjudicator agents only for semantic labels; deterministic scripts first",
                    "semantic_labeler": route("validation_set"),
                    "final_adjudicator": route("validation_set_adjudication"),
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
    elif target == "visible_increment":
        base.update(
            {
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
        )
    elif target == "repo_skill_gap_analysis":
        base.update(
            {
                "skill": "$orchestrate-task-cycle",
                "mode": "pre_derive_gap_analysis",
                "routing": {"phase": "repo-local reusable capability gap analysis", "agent_routing_applicability": "deterministic_only"},
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
        )
    elif target == "cycle_efficiency_profile":
        base.update(
            {
                "skill": "$profile-cycle-efficiency",
                "routing": {"phase": "pre-validation and pre-derive efficiency profile", "agent_routing_applicability": "deterministic_only"},
                "required_inputs": ["cycle ledger", "run IDs", "output-delta/loopback evidence", "task-pack and blocker-family scope"],
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
        )
    elif target == "validation_scope_finalize":
        base.update(
            {
                "skill": "$plan-validation-scope",
                "mode": "post_change_finalize",
                "routing": {"phase": "final validation scope from actual changed files", "agent_routing_applicability": "deterministic_only"},
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
        )
    elif target == "index_pre_validate":
        base.update(
            {
                "skill": "$manage-task-state-index",
                "mode": "pre_validation_snapshot",
                "routing": {"phase": "pre-validation traceability snapshot", "agent_routing_applicability": "deterministic_only"},
                "required_inputs": ["current task and cycle artifacts", "run/review/loopback evidence", "final validation-scope manifest"],
                "required_outputs": [
                    "step: index_pre_validate",
                    "task_id",
                    "index_status",
                    "index_snapshot_id",
                    "blockers including explicit []",
                    "evidence_paths",
                ],
            }
        )
    elif target == "schema_pre_derive":
        base.update(
            {
                "skill": "$manage-schema-contracts",
                "routing": {
                    "phase": "pre-derive refresh",
                    "schema_planning": route("schema_planning"),
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
                "required_outputs": ["schema_status", "evidence_paths", "changed schema/contract paths", "pending output-dependent evidence"],
            }
        )
    elif target == "derive":
        base.update(
            {
                "skill": "$derive-improvement-task",
                "routing": {
                    "evidence_inspectors": route("derive_inspector"),
                    "cross_contract_analysis": route("derive_cross_contract"),
                    "synthesis": route("derive_synthesis"),
                    "exceptional_arbitration": route("exceptional_arbitration"),
                    "id_consistency": route("id_index"),
                    "max_requires": "Tier 5 Sol/xhigh ran first, prior_tier5_unresolved=true, prior_tier5_evidence, one agent, and max_escalation_reason",
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
                    "Part J anti-loop findings: scenario_uncovered, acceptance_inversion, command_provenance_missing, repeated blocker_opacity, predetermined_unreachable, floor_edge_envelope, and instrumentation_first_fire",
                    "Part K lineage/comparison findings: expectation_lineage_stale, parity_unverified, majority_vote_adoption without axis classification, measured_but_disqualified, repeated resolution_downgrade, and report_key_divergence",
                    "output_delta gate result with produced_domain_delta, metadata_only, and effective_progress_kind when available",
                    "progress loop detection result with blocker_signature, semantic_signature, goal_distance_gate, and progress_kind/governance_only evidence",
                    "task pack status/result and terminal blocker state when present",
                    "active non-GT external advice packet when present",
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
                    "when the last two progress-bearing cycles are governance_only, select goal_productive work or record terminal_blocked",
                    "when the last two progress-bearing cycles are metadata_only, choose resume_primary_output, bounded source-backed run/preflight, root-cause repair, or terminal_blocked",
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
                    "loop_breaker_disposition",
                    "evidence_paths",
                    "used_advice or advice disposition rationale when active advice is in scope",
                    "degraded_agents and unavailable agent/lens notes when the requested tiered role fanout is unavailable",
                ],
            }
        )
    elif target == "schema_post_derive":
        base.update(
            {
                "skill": "$manage-schema-contracts",
                "routing": {
                    "phase": "post-derive planned-contract reconciliation",
                    "schema_planning": route("schema_planning"),
                    "implementation_edits": "forbidden",
                },
                "required_inputs": [
                    "new active task.md",
                    "retained candidate tasks",
                    ".agent_goal/goal_schema_contract.md when present",
                    ".schema/.contract records",
                ],
                "required_outputs": ["next_task_id", "schema_status", "evidence_paths", "planned contract paths", "needs_review items"],
                "terminal_or_skipped_outputs": [
                    "schema_status: terminal|terminal_blocked|skipped|not_applicable|blocked|deferred",
                    "concrete reason",
                    "no fabricated next_task_id",
                ],
            }
        )
    elif target == "index":
        base.update(
            {
                "skill": "$manage-task-state-index",
                "routing": {"id_correction": route("id_index"), "deterministic_scan_first": True},
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
                "required_outputs": ["index_status", "audit verdict", "high-severity ID blockers"],
            }
        )
    elif target == "validate":
        base.update(
            {
                "skill": "$validate-task-completion",
                "routing": {
                    "repository_audit": route("completion_review"),
                    "oom_audit_when_relevant": route("completion_review"),
                    "id_correction": route("id_index"),
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
                    "verdict_contract_version=1 plus task_acceptance_verdict, artifact_truth_verdict, artifact_semantic_verdict, pack_transition_verdict, historical_index_verdict, and goal_readiness_verdict with evidence refs",
                    "decision_contract_version=1, exact decision artifact identity, and explicit required/consumed compatibility gate scopes",
                    "verification_axes and full consumer invocation receipts when required by acceptance",
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
                "routing": {
                    "issue_lifecycle": "after validation, before commit",
                    "issue_fit_agent": route("issue_fit"),
                },
                "required_inputs": [
                    "validation_verdict",
                    "progress_verdict",
                    "remaining blockers",
                    "run/log/miss evidence",
                    "current task.md that was just validated",
                ],
                "required_outputs": [
                    "issue_packet_id",
                    "task_id",
                    "issue_status",
                    "issue_provenance.source_task_id matching task_id",
                    "issue_provenance.validation_id or validation_report_path",
                    "durable issue ID/path/URL for lifecycle mutations",
                    "resolution evidence for close/resolve",
                    "blockers including explicit []",
                    "evidence_paths",
                ],
            }
        )
    elif target == "commit":
        base.update(
            {
                "skill": "$repo-change-commit",
                "routing": {"commit_finalization": route("commit")},
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
    elif target == "dashboard":
        base.update(
            {
                "skill": "$render-cycle-dashboard",
                "routing": {
                    "agent_routing_applicability": "deterministic_only",
                    "phase": "post-commit ledger snapshot before report",
                },
                "required_inputs": [
                    "stage.jsonl with explicit canonical step/status rows",
                    "current_stage.json snapshot when present",
                    "current task/completed task/next task IDs",
                    "validation and progress verdicts/axes",
                    "issue and commit results",
                    "blockers, changed files, artifact/evidence paths",
                ],
                "required_outputs": [
                    "step: dashboard",
                    "task_id",
                    "dashboard_status",
                    "event_count and explicit current_stage_event_count",
                    "snapshot_status",
                    "validation_verdict and progress_verdict",
                    "blockers including explicit []",
                    "dashboard_path",
                    "evidence_paths",
                ],
                "fail_closed": [
                    "malformed ledger JSON is an error, never a skipped row",
                    "noncanonical or incomplete event envelopes remain visible in a separate section",
                    "dashboard never upgrades validation or progress truth",
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
                    "모델/effort 라우팅",
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
                "routing": {"commit_finalization": route("commit"), "phase": "closeout artifact commit after report"},
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
    if target == "derive" and workflow_mode == "bootstrap":
        base.update(
            {
                "mode": "initial_init",
                "workflow_mode": "bootstrap",
                "task": "task.md absent",
                "required_inputs": [
                    "task-absent context packet",
                    "authority_policy and used_goal_truth",
                    ".agent_goal goal architecture/theory/schema-contract evidence when present",
                    ".task/task_miss, candidate_task, and task_pack evidence when relevant",
                    "pre-derive schema reconciliation result or explicit skipped/not-applicable reason",
                ],
                "selection_rules": [
                    "derive exactly one initial task.md",
                    "write the required Execution Environment section",
                    "skip past_task archival because no prior task exists",
                    "do not emit acceptance, governance, run, validation, issue, promotion, commit, dashboard, or report evidence",
                    "finish schema-post-derive and index, then close the bootstrap transaction",
                    "start a fresh normal cycle from context and repo_skill_adapter_scan",
                ],
                "required_outputs": [
                    "step: derive",
                    "derive_mode: initial_init",
                    "next_task_id",
                    "selected_task_source: standalone",
                    "progress_kind",
                    "semantic_signature",
                    "evidence_paths",
                    "no fabricated completed_task_id",
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
    parser.add_argument("--workflow-mode", choices=("normal", "bootstrap"), default="normal")
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    args = parser.parse_args(argv)

    context = load_json(args.context)
    stage = load_json(args.stage)
    packet = packet_for(args.target, context, stage, args.workflow_mode)
    if args.format == "json":
        json.dump(packet, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(render_markdown(packet))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
