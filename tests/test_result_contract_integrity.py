from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


def load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


result_contract = load_module(
    ROOT / "orchestrate-task-cycle" / "scripts" / "result_contract.py",
    "result_contract_integrity",
)
assemble_cycle_report = load_module(
    ROOT / "orchestrate-task-cycle" / "scripts" / "assemble_cycle_report.py",
    "assemble_cycle_report_integrity",
)


def finding_codes(result: dict[str, Any]) -> set[str]:
    return {str(item.get("code")) for item in result.get("findings", [])}


def test_validate_accepts_explicit_empty_blockers() -> None:
    result = result_contract.validate(
        "validate",
        {
            "step": "validate",
            "task_id": "task-1",
            "validation_verdict": "partial",
            "progress_verdict": "no_progress",
            "blockers": [],
            "evidence_paths": ["validation.json"],
            "agent_routing_applicability": "deterministic_only",
        },
        "block",
    )

    assert "missing_required_field" not in finding_codes(result)


def test_commit_role_mismatch_blocks_in_block_mode() -> None:
    result = result_contract.validate(
        "closeout_commit",
        {
            "step": "closeout_commit",
            "commit_role": "implementation",
            "commit_status": "skipped",
            "commit_skipped_reason": "no changes",
            "tracked_artifacts": [],
            "evidence_paths": ["commit.json"],
            "agent_routing_applicability": "deterministic_only",
        },
        "block",
    )

    assert result["status"] == "block"
    assert "commit_role_mismatch" in finding_codes(result)


def test_report_assembler_output_is_directly_contract_validatable() -> None:
    report = assemble_cycle_report.assemble(
        context={},
        stage={"task_id": "task-1", "blockers": [], "used_goal_truth": [], "used_advice": []},
        validation={
            "task_id": "task-1",
            "validation_verdict": "partial",
            "progress_verdict": "no_progress",
            "blockers": [],
            "progress_axes": {},
        },
        progress={},
        commit={},
        closeout_commit={},
    )
    validated = result_contract.validate("report", report, "block")

    assert report["blockers"] == []
    assert report["used_advice"] == []
    assert validated["status"] != "block", validated


def test_report_assembler_recognizes_validator_complete_vocabulary() -> None:
    report = assemble_cycle_report.assemble(
        context={},
        stage={
            "task_id": "task-1",
            "next_task_id": "task-2",
            "blockers": [],
            "used_goal_truth": [],
            "used_advice": [],
            "events": [
                {"step": "issue", "status": "not_applicable", "task_id": "task-1"},
                {"step": "derive", "status": "complete", "task_id": "task-1", "next_task_id": "task-2"},
                {"step": "commit", "status": "complete", "task_id": "task-1"},
                {"step": "dashboard", "status": "complete", "task_id": "task-1"},
            ],
        },
        validation={
            "task_id": "task-1",
            "validation_verdict": "complete",
            "progress_verdict": "advanced",
            "blockers": [],
            "progress_axes": {"behavior": "advanced"},
            "validation_commands": [{"command": "python -m pytest -q", "status": "passed"}],
            "evidence_paths": ["validation.json"],
        },
        progress={},
        commit={"task_id": "task-1", "commit_status": "committed", "evidence_paths": ["commit.json"]},
        closeout_commit={},
    )

    assert report["completion_status"] == "complete_verified"
    assert report["validation_verdict"] == "passed"


def test_report_completion_rejects_cross_task_closure_and_failed_commit() -> None:
    report = assemble_cycle_report.assemble(
        context={},
        stage={
            "task_id": "task-a",
            "next_task_id": "task-b",
            "blockers": [],
            "events": [
                {"step": "issue", "status": "complete", "task_id": "task-other"},
                {"step": "derive", "status": "complete", "task_id": "task-other", "next_task_id": "task-b"},
                {"step": "dashboard", "status": "complete", "task_id": "task-other"},
            ],
        },
        validation={
            "task_id": "task-a",
            "validation_verdict": "complete",
            "progress_verdict": "advanced",
            "blockers": [],
            "progress_axes": {"behavior": "advanced"},
            "commands": [{"command": "pytest", "status": "failed"}],
            "evidence_paths": ["validation.json"],
        },
        progress={},
        commit={"task_id": "task-other", "commit_status": "failed", "commit_skipped_reason": "tests failed"},
        closeout_commit={},
    )

    validated = result_contract.validate("report", report, "block")

    assert report["completion_status"] == "not_complete"
    assert "report_completion_evidence_incomplete" in finding_codes(validated)
    assert validated["status"] == "block"


def test_report_assembler_blocks_placeholder_only_completion() -> None:
    report = assemble_cycle_report.assemble(
        context={},
        stage={},
        validation={"validation_verdict": "complete", "progress_verdict": "advanced", "blockers": []},
        progress={},
        commit={},
        closeout_commit={},
    )

    validated = result_contract.validate("report", report, "block")

    assert report["completion_status"] == "not_complete"
    assert "report_completion_evidence_incomplete" in finding_codes(validated)
    assert validated["status"] == "block"


def test_report_assembler_does_not_discard_malformed_blockers() -> None:
    report = assemble_cycle_report.assemble(
        context={},
        stage={"task_id": "task-1", "next_task_id": "task-2"},
        validation={"task_id": "task-1", "validation_verdict": "complete", "progress_verdict": "advanced", "blockers": "UNRESOLVED"},
        progress={},
        commit={},
        closeout_commit={},
    )

    validated = result_contract.validate("report", report, "block")

    assert report["completion_status"] == "not_complete"
    assert "invalid_report_blockers_input" in finding_codes(validated)
    assert validated["status"] == "block"


def test_report_explicit_empty_usage_does_not_claim_context_inventory() -> None:
    report = assemble_cycle_report.assemble(
        context={
            "agent_goal": {"used_goal_truth": [".agent_goal/final_goal.md"]},
            "external_advice": {"active_files": [{"path": ".agent_advice/active/note.md"}]},
        },
        stage={"task_id": "task-1", "used_goal_truth": [], "used_advice": [], "blockers": []},
        validation={"task_id": "task-1", "validation_verdict": "partial", "progress_verdict": "no_progress", "blockers": []},
        progress={},
        commit={},
        closeout_commit={},
    )

    assert report["used_goal_truth"] == []
    assert report["used_advice"] == []


def test_report_contract_rejects_inconsistent_complete_verified() -> None:
    report = assemble_cycle_report.assemble(
        context={},
        stage={"task_id": "task-1", "next_task_id": "task-2", "blockers": [], "used_goal_truth": [], "used_advice": []},
        validation={"task_id": "task-1", "validation_verdict": "partial", "progress_verdict": "advanced", "blockers": []},
        progress={},
        commit={},
        closeout_commit={},
    )
    report["completion_status"] = "complete_verified"

    validated = result_contract.validate("report", report, "block")

    assert validated["status"] == "block"
    assert "report_complete_verified_inconsistent" in finding_codes(validated)
