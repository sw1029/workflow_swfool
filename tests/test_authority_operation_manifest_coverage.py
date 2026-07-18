from __future__ import annotations

import json
from pathlib import Path
import sys


SKILLS_ROOT = Path(__file__).resolve().parents[1]
AUTHORITY_SCRIPTS = SKILLS_ROOT / "manage-agent-authority" / "scripts"
if str(AUTHORITY_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(AUTHORITY_SCRIPTS))

from manage_agent_authority.operations import validate_manifest  # noqa: E402


REQUIRED_WORKFLOW_OPERATIONS = {
    "audit-cycle-loopback": {"publish_loopback_candidate"},
    "audit-session-governance": {
        "capture_session_projection",
        "rebuild_session_audit_index",
    },
    "build-validation-set-with-agents": {"mutate_validation_set_assets"},
    "deep-interview-goal-context": {
        "draft_concept_graph",
        "finalize_goal_truth",
    },
    "derive-improvement-task": {"propose_task", "publish_task"},
    "find-local-python-envs": {"inventory_local_python_environments"},
    "inspect-oom-risk": {"audit_oom_risk"},
    "inspect-repo-with-agents": {"inspect_repository"},
    "install-deps-with-agent": {
        "download_dependency_artifact",
        "inspect_dependency_availability",
        "install_dependency",
    },
    "maintain-cycle-ledger": {"append_cycle_evidence", "finalize_cycle_attempt"},
    "manage-agent-goal": {
        "read_agent_goal",
        "update_final_goal",
        "update_goal_conventions",
    },
    "manage-agent-authority": {
        "compose_grants",
        "consume_use",
        "delegate_grant",
        "evaluate_operation",
        "issue_grant",
        "prepare_source_authority_recovery",
        "release_use",
        "reserve_use",
        "snapshot_policy",
        "snapshot_source_approval",
        "status",
        "summarize_policy",
        "transition_grant",
        "update_policy",
        "validate_policy",
        "verify_reservation",
    },
    "manage-external-advice": {
        "mutate_advice_lifecycle",
        "prepare_advice_intake_plan",
    },
    "manage-evidence-cache": {
        "append_evidence_cache_record",
        "query_evidence_cache",
    },
    "manage-goal-architecture": {
        "summarize_architecture",
        "update_bounded_design",
    },
    "manage-goal-theory": {"summarize_theory", "update_core_theory"},
    "manage-implementation-issues": {
        "mutate_external_issue_lifecycle",
        "mutate_local_issue_lifecycle",
    },
    "manage-schema-contracts": {"inspect_contracts", "publish_contract"},
    "manage-task-state-index": {
        "mutate_task_state_index",
        "prepare_task_state_transition_plan",
    },
    "monitor-running-execution": {
        "record_execution_monitor_event",
        "terminate_running_execution",
    },
    "normalize-acceptance-and-demo": {"publish_acceptance_packet"},
    "optimize-task-slice": {"classify_task_slice"},
    "orchestrate-task-cycle": {
        "activate_terminal_wait_baseline_settlement",
        "activate_task_topology_settlement",
        "dispatch_external_operation",
        "dispatch_local_worker",
        "inspect_cycle",
        "materialize_terminal_wait_baseline_subject",
        "mutate_task_topology",
        "publish_terminal_wait_baseline_binding",
        "validate_exact_subject_premise",
        "validate_selection_decision_receipt",
    },
    "plan-validation-scope": {"publish_validation_scope"},
    "profile-cycle-efficiency": {"profile_cycle_efficiency"},
    "record-agent-work-log": {"publish_agent_work_log"},
    "record-visible-increment": {"publish_visible_increment"},
    "render-cycle-dashboard": {"publish_cycle_dashboard"},
    "repo-change-commit": {"finalize_git_state"},
    "review-cycle-output-quality": {"review_cycle_output"},
    "run-task-code-and-log": {
        "call_provider",
        "destructive_change",
        "edit_local",
        "run_long",
    },
    "shape-agent-goal-prompt": {"shape_goal_draft"},
    "task-doctor": {
        "coordinate_task_doctor_workflow",
        "diagnose_task",
        "mutate_task_scope",
    },
    "task-md-agent-governance": {
        "advance_task_state",
        "implement_local_change",
        "validate_local_change",
    },
    "validate-subskill-result-contract": {"validate_subskill_result"},
    "validate-task-completion": {"publish_validation_projection"},
}

BOUND_LIFECYCLE_MUTATIONS = {
    ("orchestrate-task-cycle", "activate_terminal_wait_baseline_settlement"),
    ("orchestrate-task-cycle", "activate_task_topology_settlement"),
}

PROJECTION_ONLY_MUTATIONS = {
    ("audit-cycle-loopback", "publish_loopback_candidate"),
    ("audit-session-governance", "rebuild_session_audit_index"),
    ("deep-interview-goal-context", "draft_concept_graph"),
    ("manage-agent-authority", "evaluate_operation"),
    ("manage-agent-authority", "prepare_source_authority_recovery"),
    ("manage-agent-authority", "snapshot_policy"),
    ("manage-agent-authority", "snapshot_source_approval"),
    ("manage-evidence-cache", "append_evidence_cache_record"),
    ("manage-external-advice", "prepare_advice_intake_plan"),
    ("manage-task-state-index", "prepare_task_state_transition_plan"),
    ("orchestrate-task-cycle", "materialize_terminal_wait_baseline_subject"),
    ("record-agent-work-log", "publish_agent_work_log"),
    ("record-visible-increment", "publish_visible_increment"),
    ("render-cycle-dashboard", "publish_cycle_dashboard"),
    ("task-doctor", "coordinate_task_doctor_workflow"),
    ("validate-task-completion", "publish_validation_projection"),
}


def _manifest(skill_id: str) -> dict[str, object]:
    path = SKILLS_ROOT / skill_id / "authority.operations.json"
    assert path.is_file(), f"missing operation manifest: {skill_id}"
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(raw, dict)
    return validate_manifest(raw, path)


def test_governed_workflow_mutators_have_closed_operation_manifests() -> None:
    discovered = {
        path.parent.name for path in SKILLS_ROOT.glob("*/SKILL.md") if path.is_file()
    }
    assert set(REQUIRED_WORKFLOW_OPERATIONS) == discovered
    for skill_id, required_operations in REQUIRED_WORKFLOW_OPERATIONS.items():
        manifest = _manifest(skill_id)
        assert manifest["skill_id"] == skill_id
        observed = {row["operation_id"] for row in manifest["operations"]}
        assert required_operations <= observed


def test_authority_free_mutations_are_bounded_derived_projections_only() -> None:
    observed_projection_only: set[tuple[str, str]] = set()
    observed_bound_lifecycle: set[tuple[str, str]] = set()
    for skill_id in REQUIRED_WORKFLOW_OPERATIONS:
        manifest = _manifest(skill_id)
        for operation in manifest["operations"]:
            key = (skill_id, operation["operation_id"])
            if (
                operation["mutation_class"] != "observe"
                and operation["authorization_mechanism"] == "none"
            ):
                observed_projection_only.add(key)
            if skill_id != "manage-agent-authority":
                if operation["authorization_mechanism"] == "bound_lifecycle_artifact":
                    observed_bound_lifecycle.add(key)
                else:
                    assert operation["authorization_mechanism"] in {"none", "grant"}
    assert observed_projection_only == PROJECTION_ONLY_MUTATIONS
    assert observed_bound_lifecycle == BOUND_LIFECYCLE_MUTATIONS


def test_all_manifested_skills_route_through_the_shared_authority_contract() -> None:
    for skill_id in REQUIRED_WORKFLOW_OPERATIONS:
        body = (SKILLS_ROOT / skill_id / "SKILL.md").read_text(encoding="utf-8")
        assert "authority.operations.json" in body
        assert "authority-v2-contract.md" in body


def test_mutating_operation_tiers_are_monotone_with_effect_and_decision_scope() -> None:
    rank = {f"S{index}": index for index in range(5)}
    risk = {f"R{index}": index for index in range(4)}
    for skill_id in REQUIRED_WORKFLOW_OPERATIONS:
        for operation in _manifest(skill_id)["operations"]:
            mutation = operation["mutation_class"]
            mechanism = operation["authorization_mechanism"]
            if mutation == "external_mutation":
                assert rank[operation["source_rank_floor"]] >= 2
                assert risk[operation["risk_floor"]] >= 2
                assert mechanism != "none"
            if mutation == "destructive":
                assert rank[operation["source_rank_floor"]] >= 3
                assert risk[operation["risk_floor"]] == 3
                assert operation["reversibility"] == "irreversible"
                assert mechanism != "none"
            if mechanism != "none" and operation["decision_class"] == "D0":
                assert rank[operation["source_rank_floor"]] >= 3
                assert risk[operation["risk_floor"]] == 3
            if mechanism != "none" and operation["decision_class"] == "D1":
                assert rank[operation["source_rank_floor"]] >= 2
                assert risk[operation["risk_floor"]] >= 2
            if mechanism != "none" and operation["decision_class"] == "D2":
                assert rank[operation["source_rank_floor"]] >= 2
                assert risk[operation["risk_floor"]] >= 2
