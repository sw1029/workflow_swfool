from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import pytest
from orchestrate_task_cycle import (
    cycle_ledger as ledger,
    profile_cycle_efficiency as profile,
    render_subskill_packet as packets,
    validate_cycle_transition as transition,
    visible_increment as visible,
)
from orchestrate_task_cycle.result_contract import api as contracts


def codes(result: dict[str, Any]) -> set[str]:
    return {str(item.get("code")) for item in result.get("findings", [])}


def test_transition_uses_current_routing_packet_not_prior_ledger_route() -> None:
    stage = {
        "target": "governance",
        **packets.routing_profile("code_worker"),
        "steps": {
            step: {"step": step, "status": "complete"}
            for step in transition.TRANSITION_REQUIREMENTS["pre_derive"]
        },
    }
    routing = {"target": "derive", **packets.routing_profile("derive_synthesis")}

    result = transition.validate({}, stage, "pre_derive", routing)

    assert "routing_target_transition_mismatch" not in codes(result)
    assert "target_profile_mismatch" not in codes(result)

    missing = transition.validate({}, stage, "pre_derive")
    assert "current_target_routing_packet_missing" in codes(missing)


def pending_context(status: str = "running") -> dict[str, Any]:
    return {
        "events": [
            {
                "step": "run",
                "event_kind": "long_run_monitor",
                "long_run_branch": True,
                "run_id": "run-pending-1",
                "owner_task_id": "task-1",
                "execution_status": status,
                "remaining_validation": ["harvest", "validate"],
            }
        ]
    }


def test_result_contract_consumes_pending_long_run_context() -> None:
    validate_payload = {
        "step": "validate",
        "task_id": "task-1",
        "validation_verdict": "pass",
        "progress_verdict": "advanced",
        "blockers": [],
        "evidence_paths": ["validation.json"],
    }
    blocked = contracts.validate("validate", validate_payload, "warn", pending_context())
    finding = next(item for item in blocked["findings"] if item["code"] == "pending_long_run_validate_overclaim")
    assert finding["severity"] == "block"
    assert finding["evidence"]["pending_long_runs"][0]["run_id"] == "run-pending-1"

    partial = contracts.validate(
        "validate",
        {**validate_payload, "validation_verdict": "partial", "progress_verdict": "partial"},
        "warn",
        pending_context("completed_pending_validation"),
    )
    assert "pending_long_run_validate_overclaim" not in codes(partial)

    ordinary = contracts.validate(
        "derive",
        {
            "step": "derive",
            "completed_task_id": "task-1",
            "next_task_id": "task-2",
            "selected_task_source": "standalone",
            "selected_task_kind": "feature_work",
            "loop_breaker_disposition": "continue",
            "progress_kind": "goal_productive",
            "semantic_signature": "feature-work",
            "evidence_paths": ["derive.json"],
            "agent_routing_applicability": "delegation_unavailable",
            "routing_limitation": "test",
        },
        "block",
        pending_context("launching"),
    )
    assert "pending_long_run_ordinary_derive" in codes(ordinary)


def test_result_contract_requires_checked_state_and_reads_canonical_long_run_context() -> None:
    validation = {
        "step": "validate",
        "task_id": "task-1",
        "validation_verdict": "pass",
        "progress_verdict": "advanced",
        "blockers": [],
        "evidence_paths": ["validation.json"],
    }
    unchecked = contracts.validate("validate", validation, "warn")
    assert "long_run_state_not_checked" in codes(unchecked)

    canonical_context = {
        "long_run_state_checked": True,
        "cycle_state": {
            "latest_events": [
                {
                    "step": "run",
                    "long_run_branch": True,
                    "run_id": "run-stale",
                    "execution_status": "stale",
                }
            ]
        },
    }
    pending = contracts.validate("validate", validation, "warn", canonical_context)
    assert "pending_long_run_validate_overclaim" in codes(pending)

    derive = {
        "step": "derive",
        "completed_task_id": "task-1",
        "next_task_id": "task-2",
        "selected_task_source": "standalone",
        "selected_task_kind": "feature_work",
        "loop_breaker_disposition": "continue",
        "progress_kind": "goal_productive",
        "semantic_signature": "feature-work",
        "evidence_paths": ["derive.json"],
        "agent_routing_applicability": "delegation_unavailable",
        "routing_limitation": "test",
    }
    unchecked_derive = contracts.validate("derive", derive, "warn")
    assert "long_run_state_not_checked" in codes(unchecked_derive)


def test_visible_increment_helper_is_directly_contract_valid() -> None:
    payload = visible.build(
        argparse.Namespace(
            cycle_id="cycle-1",
            task_id="task-1",
            summary="CLI output changed",
            delta_type=["cli"],
            before=None,
            after=None,
            changed_file=[],
            artifact=[],
            output_delta_status=None,
            produced_domain_delta=None,
            metadata_only=None,
            effective_progress_kind=None,
        )
    )
    result = contracts.validate("visible_increment", payload, "block")
    assert result["status"] == "ok"
    assert payload["step"] == "visible_increment"
    assert payload["not_validation_evidence"] is True


def test_visible_increment_rejects_path_escape_and_output_symlink(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="path-safe token"):
        visible.build(
            argparse.Namespace(
                cycle_id="../escape",
                task_id="task-1",
                summary="escape",
                delta_type=["none"],
                before=None,
                after=None,
                changed_file=[],
                artifact=[],
                output_delta_status=None,
                produced_domain_delta=None,
                metadata_only=None,
                effective_progress_kind=None,
            )
        )

    delta_dir = tmp_path / ".task" / "delta"
    delta_dir.mkdir(parents=True)
    outside = tmp_path / "outside.json"
    outside.write_text("preserve\n", encoding="utf-8")
    (delta_dir / "cycle-1-visible-delta.json").symlink_to(outside)
    with pytest.raises(SystemExit, match="JSON path must stay inside"):
        visible.main(["--root", str(tmp_path), "--cycle-id", "cycle-1", "--task-id", "task-1", "--write"])
    assert outside.read_text(encoding="utf-8") == "preserve\n"


def test_cycle_efficiency_rejects_cycle_path_escape(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="path-safe token"):
        profile.collect_events(tmp_path, "../escape")


def test_na_contracts_do_not_require_fabricated_values() -> None:
    review = {
        "step": "qualitative_review",
        "task_id": "task-1",
        "review_agent_count": 0,
        "reviewer_routing": {},
        "review_status": "not_applicable",
        "quality_verdict": "not_applicable",
        "reviewed_artifacts": [],
        "direct_read_scope": [],
        "qualitative_findings": [],
        "direction_recommendations": [],
        "output_delta_status": "not_applicable",
        "changed_vs_previous": False,
        "semantic_progress": False,
        "produced_domain_delta": False,
        "metadata_only": True,
        "effective_progress_kind": "governance_only",
        "progress_cap": "not_advanced",
        "blocker_taxonomy_delta": [],
        "no_overclaim_flags": [],
        "evidence_paths": [],
        "agent_routing_applicability": "delegation_unavailable",
        "routing_limitation": "no output artifact exists",
        "reason": "run produced no reviewable output",
    }
    review_result = contracts.validate("qualitative_review", review, "warn")
    missing_review = {item.get("evidence", {}).get("field") for item in review_result["findings"] if item["code"] == "missing_required_field"}
    assert not ({"reviewed_artifacts", "direct_read_scope", "qualitative_findings", "direction_recommendations", "blocker_taxonomy_delta", "no_overclaim_flags"} & missing_review)
    assert "qualitative_review_agent_count_invalid" not in codes(review_result)
    assert "qualitative_review_blocked_reason_missing" not in codes(review_result)

    schema = contracts.validate(
        "schema_post_derive",
        {
            "step": "schema_post_derive",
            "schema_status": "terminal",
            "schema_terminal_reason": "derive selected terminal_blocked",
            "evidence_paths": [],
            "agent_routing_applicability": "delegation_unavailable",
            "routing_limitation": "terminal path",
        },
        "block",
    )
    assert "schema_post_derive_next_task_missing" not in codes(schema)
    assert "next_task_id" not in schema["missing_fields"]

    fabricated_schema = contracts.validate(
        "schema_post_derive",
        {
            "step": "schema_post_derive",
            "schema_status": "terminal",
            "schema_terminal_reason": "derive selected terminal_blocked",
            "next_task_id": "not_applicable",
            "evidence_paths": ["schema.json"],
        },
        "warn",
    )
    assert "schema_post_derive_terminal_next_task_forbidden" in codes(fabricated_schema)

    validation_set = contracts.validate(
        "validation_set_build",
        {
            "step": "validation_set_build",
            "task_id": "task-1",
            "validation_set_status": "not_applicable",
            "validation_set_not_applicable_reason": "task has no evaluation asset surface",
            "evidence_paths": [],
            "agent_routing_applicability": "delegation_unavailable",
            "routing_limitation": "not applicable",
        },
        "warn",
    )
    assert validation_set["missing_fields"] == []

    schema_complete = contracts.validate(
        "schema_post_derive",
        {"step": "schema_post_derive", "schema_status": "complete", "evidence_paths": ["schema.json"]},
        "warn",
    )
    assert "schema_post_derive_next_task_missing" in codes(schema_complete)

    build_without_manifests = contracts.validate(
        "validation_set_build",
        {
            "step": "validation_set_build",
            "task_id": "task-1",
            "validation_set_status": "complete",
            "evidence_paths": ["validation-set.json"],
        },
        "block",
    )
    assert "validation_set_build_artifact_field_missing" in codes(build_without_manifests)


def test_profile_helper_emits_formal_result_envelope(tmp_path: Path) -> None:
    payload = profile.analyze(tmp_path, [], [], "task-1")
    result = contracts.validate("cycle_efficiency_profile", payload, "block")
    assert result["status"] == "ok"
    assert payload["step"] == "cycle_efficiency_profile"
    assert payload["blockers"] == []


def test_fabricated_visible_and_efficiency_envelopes_fail_closed() -> None:
    visible_result = contracts.validate(
        "visible_increment",
        {
            "step": "visible_increment",
            "status": "fabricated-pass",
            "cycle_id": "../escape",
            "task_id": "task-1",
            "summary": "fabricated",
            "delta_types": ["fabricated"],
            "changed_files": [],
            "artifacts": [],
            "blockers": [],
            "not_validation_evidence": True,
            "evidence_paths": ["visible.json"],
        },
        "warn",
    )
    assert visible_result["status"] == "block"
    assert {"visible_increment_id_invalid", "visible_increment_status_invalid", "visible_increment_delta_types_invalid"} <= codes(visible_result)

    profile_result = contracts.validate(
        "cycle_efficiency_profile",
        {
            "step": "cycle_efficiency_profile",
            "task_id": "task-1",
            "status": "fabricated-pass",
            "cycle_fixed_cost": -99,
            "cycle_cost_basis": {},
            "recommendation": "ignore-all-gates",
            "blockers": [],
            "evidence_paths": ["profile.json"],
        },
        "warn",
    )
    assert profile_result["status"] == "block"
    assert {
        "cycle_efficiency_status_invalid",
        "cycle_efficiency_cost_invalid",
        "cycle_efficiency_cost_basis_invalid",
        "cycle_efficiency_recommendation_invalid",
    } <= codes(profile_result)


def test_missing_task_bootstrap_is_explicit_and_not_a_fake_normal_cycle() -> None:
    packet = packets.packet_for("derive", {}, {}, "bootstrap")
    assert packet["mode"] == "initial_init"
    assert "no fabricated completed_task_id" in packet["required_outputs"]

    derive = contracts.validate(
        "derive",
        {
            "step": "derive",
            "derive_mode": "initial_init",
            "next_task_id": "task-initial",
            "selected_task_source": "standalone",
            "progress_kind": "goal_productive",
            "semantic_signature": "initial-task",
            "evidence_paths": ["task.md"],
            "agent_routing_applicability": "delegation_unavailable",
            "routing_limitation": "bootstrap test",
        },
        "block",
    )
    assert "completed_task_id" not in derive["missing_fields"]

    stage = {
        "steps": {
            "context": {"step": "context", "status": "complete", "task_md_exists": False},
            "authority": {"step": "authority", "status": "complete", "authority_policy": "default_current_agent_permissions"},
            "schema_pre_derive": {"step": "schema_pre_derive", "status": "complete", "reason": "initial schema inspected"},
            "derive": {
                "step": "derive",
                "status": "complete",
                "derive_mode": "initial_init",
                "next_task_id": "task-initial",
                "task_path": "task.md",
                "artifacts": ["task.md"],
            },
            "schema_post_derive": {
                "step": "schema_post_derive",
                "status": "complete",
                "next_task_id": "task-initial",
            },
            "index": {
                "step": "index",
                "status": "complete",
                "task_id": "task-initial",
                "artifacts": [".task/index.jsonl", ".task/index.md"],
            },
        }
    }
    complete = transition.validate(
        {"task_md_exists": False},
        stage,
        "bootstrap_complete",
        workflow_mode="bootstrap",
    )
    assert complete["status"] != "block"
    assert not {code for code in codes(complete) if code.startswith("bootstrap_")}
    rejected = transition.validate({"task_md_exists": False}, stage, "pre_report", workflow_mode="bootstrap")
    assert "transition_not_allowed_for_workflow_mode" in codes(rejected)

    vacuous = {
        "steps": {
            step: {"step": step, "status": "not_applicable", "reason": "fabricated"}
            for step in transition.BOOTSTRAP_ORDER
        }
    }
    vacuous_result = transition.validate(
        {"task_md_exists": False},
        vacuous,
        "bootstrap_complete",
        workflow_mode="bootstrap",
    )
    assert "bootstrap_substantive_step_missing" in codes(vacuous_result)


def test_ledger_init_is_storage_metadata_and_context_is_first_stage(tmp_path: Path) -> None:
    initialized = ledger.init_cycle(tmp_path, "cycle-1", "task-1", "start")
    assert initialized["initialization"]["storage_bootstrap_only"] is True
    assert "ledger_init" not in ledger.DEFAULT_STEPS
    assert not (tmp_path / ".task" / "cycle" / "cycle-1" / "stage.jsonl").exists()

    ledger.append_event(
        tmp_path,
        "cycle-1",
        {"step": "context", "status": "complete", "task_id": "task-1"},
    )
    rows = ledger.read_events(tmp_path, "cycle-1")
    assert rows[0]["step"] == "context"
