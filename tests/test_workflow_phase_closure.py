from __future__ import annotations

from pathlib import Path
from typing import Any

from orchestrate_task_cycle import (
    cycle_ledger,
    render_cycle_dashboard as dashboard,
    render_subskill_packet as packets,
    validate_cycle_transition as transition,
)
from orchestrate_task_cycle.result_contract import api as result_contract


ROOT = Path(__file__).resolve().parents[1]
ORCHESTRATOR = ROOT / "orchestrate-task-cycle"
PACKAGE_ROOT = ORCHESTRATOR / "scripts" / "orchestrate_task_cycle"


EXPECTED_ORDER = [
    "context",
    "authority",
    "repo_skill_adapter_scan",
    "acceptance",
    "route_plan",
    "validation_scope_plan",
    "validation_set_plan",
    "governance",
    "result_contract",
    "repo_skill_adapter_validate",
    "ledger_append",
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
    "validate",
    "issue",
    "schema_pre_derive",
    "derive",
    "schema_post_derive",
    "index",
    "commit",
    "dashboard",
    "report",
    "closeout_commit",
]


def finding_codes(result: dict[str, Any]) -> set[str]:
    return {str(item.get("code")) for item in result.get("findings", [])}


def completed_steps(*steps: str) -> dict[str, Any]:
    return {"steps": {step: {"status": "complete"} for step in steps}}


def scope_payload(target: str) -> dict[str, Any]:
    finalized = target == "validation_scope_finalize"
    return {
        "step": target,
        "task_id": "task-1",
        "mode": "finalize" if finalized else "plan",
        "validation_profile": "affected_chain",
        "profile_floor": "current_only",
        "profile_changed": finalized,
        "planned_changed_files": ["src/app.py"],
        "actual_changed_files": ["src/app.py"] if finalized else [],
        "changed_surfaces": ["source"],
        "surface_counts": {"source": 1},
        "required_commands": ["python -m pytest -q"],
        "reused_prerequisites": [],
        "escalation_reasons": [],
        "rationale": [],
        "finalized": finalized,
        "findings": [],
        "evidence_paths": ["scope.json"],
    }


def test_phase_order_is_identical_across_transition_dashboard_and_contract() -> None:
    assert transition.ORDER == EXPECTED_ORDER
    assert dashboard.DEFAULT_STEPS == EXPECTED_ORDER
    assert list(result_contract.CANONICAL_LEDGER_STEPS) == EXPECTED_ORDER


def test_formal_packets_and_transitions_exist_for_new_phases() -> None:
    formal_targets = {
        "repo_skill_adapter_scan",
        "acceptance",
        "validation_scope_plan",
        "repo_skill_adapter_validate",
        "visible_increment",
        "repo_skill_gap_analysis",
        "cycle_efficiency_profile",
        "validation_scope_finalize",
        "index_pre_validate",
        "dashboard",
    }
    assert formal_targets <= packets.TARGETS
    assert formal_targets <= result_contract.TARGETS
    assert {f"pre_{target}" for target in formal_targets} <= transition.TRANSITION_REQUIREMENTS.keys()
    for index, step in enumerate(EXPECTED_ORDER):
        assert transition.TRANSITION_REQUIREMENTS[f"pre_{step}"] == EXPECTED_ORDER[:index]
    assert transition.ORDER.index("repo_skill_adapter_scan") < transition.ORDER.index("acceptance")
    assert transition.ORDER.index("validate") < transition.ORDER.index("issue") < transition.ORDER.index("derive")
    assert {"validate", "issue", "schema_pre_derive"} <= set(transition.TRANSITION_REQUIREMENTS["pre_derive"])
    for target in formal_targets | {"validation_set_plan"}:
        packet = packets.packet_for(target, {}, {})
        assert f"step: {target}" in packet["required_outputs"]


def test_packet_routing_reference_is_workspace_relative_and_preindex_is_deterministic() -> None:
    packet = packets.packet_for("index_pre_validate", {}, {})
    packet_source = (PACKAGE_ROOT / "render_subskill_packet.py").read_text(encoding="utf-8")

    assert Path(packet["routing_reference"]).resolve() == (ORCHESTRATOR / "references" / "workflow-routing.md").resolve()
    assert '"/home/swfool/' not in packet_source
    assert packet["routing"]["agent_routing_applicability"] == "deterministic_only"


def test_packets_bind_validate_derive_dashboard_and_report_to_finalization_receipt() -> None:
    validate_packet = packets.packet_for("validate", {}, {})
    derive_packet = packets.packet_for("derive", {}, {})
    dashboard_packet = packets.packet_for("dashboard", {}, {})
    report_packet = packets.packet_for("report", {}, {})

    assert any("cycle_final_candidate" in item for item in validate_packet["required_outputs"])
    assert any("finalization_consumption" in item for item in derive_packet["required_outputs"])
    assert any("current_finalization.json" in item for item in dashboard_packet["required_inputs"])
    assert any("authoritative_projection_digest convergence" in item for item in report_packet["required_outputs"])


def test_acceptance_provenance_is_fail_closed() -> None:
    base = {
        "step": "acceptance",
        "acceptance_id": "acceptance-1",
        "task_id": "task-1",
        "acceptance_status": "normalized",
        "acceptance_criteria": ["observable outcome"],
        "blockers": [],
        "evidence_paths": ["acceptance.json"],
    }
    missing = result_contract.validate("acceptance", base, "warn")
    mismatch = result_contract.validate(
        "acceptance",
        {
            **base,
            "acceptance_provenance": {
                "source_task_id": "task-2",
                "source_task_path": "task.md",
                "source_task_fingerprint": "a" * 64,
            },
        },
        "warn",
    )
    valid = result_contract.validate(
        "acceptance",
        {
            **base,
            "acceptance_provenance": {
                "source_task_id": "task-1",
                "source_task_path": "task.md",
                "source_task_fingerprint": "a" * 64,
            },
        },
        "block",
    )
    invalid_status = result_contract.validate(
        "acceptance",
        {
            **base,
            "acceptance_status": "complete",
            "acceptance_provenance": {
                "source_task_id": "task-1",
                "source_task_path": "task.md",
                "source_task_fingerprint": "a" * 64,
            },
        },
        "warn",
    )

    assert missing["status"] == "block"
    assert "acceptance_provenance_missing" in finding_codes(missing)
    assert "acceptance_task_identity_mismatch" in finding_codes(mismatch)
    assert "invalid_acceptance_status" in finding_codes(invalid_status)
    assert valid["status"] != "block", valid


def test_issue_mutations_require_validation_provenance_and_durable_ids() -> None:
    base = {
        "step": "issue",
        "issue_packet_id": "issue-packet-1",
        "task_id": "task-1",
        "issue_status": "created",
        "issue_ids": [],
        "blockers": [],
        "evidence_paths": ["issue.json"],
        "agent_routing_applicability": "deterministic_only",
    }
    missing = result_contract.validate(
        "issue",
        {
            **base,
            "issue_provenance": {
                "source_task_id": "task-1",
                "validation_id": "validation-1",
            },
        },
        "warn",
    )
    valid_noop = result_contract.validate(
        "issue",
        {
            **base,
            "issue_status": "not_applicable",
            "issue_provenance": {
                "source_task_id": "task-1",
                "validation_report_path": "validation.json",
            },
            "issue_skipped_reason": "validation found no implementation issue",
        },
        "block",
    )
    invalid_status = result_contract.validate(
        "issue",
        {
            **base,
            "issue_status": "complete-ish",
            "issue_provenance": {
                "source_task_id": "task-1",
                "validation_id": "validation-1",
            },
        },
        "warn",
    )

    assert missing["status"] == "block"
    assert "issue_identifier_missing" in finding_codes(missing)
    assert "invalid_issue_status" in finding_codes(invalid_status)
    assert valid_noop["status"] != "block", valid_noop


def test_validation_scope_two_pass_contract_requires_final_commands() -> None:
    plan = result_contract.validate("validation_scope_plan", scope_payload("validation_scope_plan"), "block")
    finalized = result_contract.validate("validation_scope_finalize", scope_payload("validation_scope_finalize"), "block")
    missing_commands_payload = scope_payload("validation_scope_finalize")
    missing_commands_payload["required_commands"] = []
    missing_commands = result_contract.validate("validation_scope_finalize", missing_commands_payload, "warn")
    string_boolean_payload = scope_payload("validation_scope_plan")
    string_boolean_payload["finalized"] = "false"
    string_boolean = result_contract.validate("validation_scope_plan", string_boolean_payload, "warn")

    assert plan["status"] != "block", plan
    assert finalized["status"] != "block", finalized
    assert "validation_scope_finalize_commands_missing" in finding_codes(missing_commands)
    assert "validation_scope_finalized_mismatch" in finding_codes(string_boolean)


def test_pending_long_run_allows_only_partial_validation_handoff() -> None:
    stage = completed_steps(*transition.TRANSITION_REQUIREMENTS["pre_validate"])
    stage["events"] = [
        {
            "step": "run",
            "status": "running",
            "execution_status": "running",
            "long_run_branch": True,
            "event_kind": "long_run_monitor",
            "run_id": "run-1",
            "owner_task_id": "task-1",
            "remaining_validation": ["harvest terminal output"],
        }
    ]
    before_validation = transition.validate({}, stage, "pre_validate")

    derive_stage = completed_steps(*transition.TRANSITION_REQUIREMENTS["pre_derive"])
    derive_stage["events"] = stage["events"]
    derive_stage["validation_verdict"] = "partial"
    before_derive = transition.validate({}, derive_stage, "pre_derive")

    assert "long_run_pending_partial_validation_only" in finding_codes(before_validation)
    assert "long_run_pending_final_output_phase" not in finding_codes(before_validation)
    assert "long_run_pending_final_output_phase" in finding_codes(before_derive)


def test_initial_init_is_documented_as_a_separate_bootstrap_transaction() -> None:
    skill = (ORCHESTRATOR / "SKILL.md").read_text(encoding="utf-8")
    routing = (ORCHESTRATOR / "references" / "workflow-routing.md").read_text(encoding="utf-8")
    interfaces = (ORCHESTRATOR / "references" / "workflow-interface-contracts.md").read_text(encoding="utf-8")

    assert "separate bootstrap transaction" in skill
    assert "separate bootstrap transaction" in routing
    assert "separate bootstrap transaction" in interfaces


def finalized_transition_event(root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    cycle_ledger.init_cycle(root, "cycle-T", "task-1", "transition finalization")
    absent_digest = cycle_ledger.absent_target_state_digest("registry_projection")
    observation = cycle_ledger.build_unchanged_target_observation(
        observation_id="attempt-T-registry-observation",
        attempt_identity="attempt-T",
        target_ref="registry_projection",
        state_status="absent",
        before_revision_id="absent",
        current_revision_id="absent",
        before_state_digest=absent_digest,
        current_state_digest=absent_digest,
    )
    candidate: dict[str, Any] = {
        "schema_version": 1,
        "kind": "cycle_final_candidate",
        "final_candidate": True,
        "cycle_id": "cycle-T",
        "attempt_id": "attempt-T",
        "expected_previous_revision": None,
        "expected_previous_attempt_id": None,
        "expected_previous_finalization_token": None,
        "verdict_contract_version": 1,
        "durable_state_candidate": cycle_ledger.build_no_durable_state_change_candidate(
            attempt_identity="attempt-T",
            reason_id="validation-has-no-durable-axis-change",
            evidence=cycle_ledger.build_no_change_evidence(
                evidence_id="attempt-T-no-change-evidence",
                attempt_identity="attempt-T",
                target_observations=[observation],
            ),
        ),
    }
    for axis in result_contract.VERDICT_AXES:
        candidate[axis] = {"status": "pass", "evidence_ref": f"{axis}-E"}
    finalized = cycle_ledger.finalize_candidate(root, "cycle-T", candidate)
    event = {
        "step": "validate",
        "status": "complete",
        "cycle_id": "cycle-T",
        "finalization_applicability": "required",
        "finalization_receipt": finalized["finalization_receipt"],
        "authoritative_projection": finalized["authoritative_projection"],
    }
    return event, candidate


def test_prederive_consumes_current_receipt_and_rejects_missing_or_stale(tmp_path: Path) -> None:
    validate_event, candidate = finalized_transition_event(tmp_path)
    stage = completed_steps(*transition.TRANSITION_REQUIREMENTS["pre_derive"])
    stage["steps"]["validate"] = validate_event
    accepted = transition.validate(
        {"workspace_root": str(tmp_path)},
        stage,
        "pre_derive",
        {"target": "derive", **packets.routing_profile("derive_synthesis")},
    )
    assert not {
        code
        for code in finding_codes(accepted)
        if "finalization_receipt" in code or "authoritative_projection" in code
    }

    missing_stage = completed_steps(*transition.TRANSITION_REQUIREMENTS["pre_derive"])
    missing = transition.validate(
        {"workspace_root": str(tmp_path)},
        missing_stage,
        "pre_derive",
        {"target": "derive", **packets.routing_profile("derive_synthesis")},
    )
    assert "pre_derive_finalization_receipt_missing" in finding_codes(missing)

    receipt = validate_event["finalization_receipt"]
    correction = {
        **candidate,
        "expected_previous_revision": receipt["attempt_revision"],
        "expected_previous_attempt_id": receipt["attempt_id"],
        "expected_previous_finalization_token": receipt["finalization_token"],
        "goal_readiness_verdict": {"status": "fail", "evidence_ref": "goal-E"},
    }
    cycle_ledger.finalize_candidate(tmp_path, "cycle-T", correction)
    stale = transition.validate(
        {"workspace_root": str(tmp_path)},
        stage,
        "pre_derive",
        {"target": "derive", **packets.routing_profile("derive_synthesis")},
    )
    assert "finalization_receipt_current_verification_failed" in finding_codes(stale)
