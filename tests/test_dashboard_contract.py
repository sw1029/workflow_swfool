from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from orchestrate_task_cycle import render_cycle_dashboard as dashboard
from orchestrate_task_cycle.cycle_ledger import append_event, init_cycle
from orchestrate_task_cycle.result_contract import api as result_contract
from orchestrate_task_cycle.stage.service import advance_stage


def events() -> list[dict[str, Any]]:
    return [
        {"cycle_id": "cycle-1", "step": "context", "status": "complete", "task_id": "task-1", "evidence_paths": ["context.json"]},
        {
            "cycle_id": "cycle-1",
            "step": "validate",
            "status": "complete",
            "task_id": "task-1",
            "validation_verdict": "complete",
            "progress_verdict": "advanced",
            "progress_axes": {"behavior": "advanced"},
            "axis_delta": {"quality": 1},
            "blockers": [],
            "evidence_paths": ["validation.json"],
        },
        {
            "cycle_id": "cycle-1",
            "step": "issue",
            "status": "not_applicable",
            "task_id": "task-1",
            "issue_packet_id": "issue-packet-1",
            "issue_ids": [],
        },
        {
            "cycle_id": "cycle-1",
            "step": "commit",
            "status": "complete",
            "task_id": "task-1",
            "commit_role": "implementation",
            "commit_status": "committed",
            "commit_hash": "abc123",
            "commit_subject": "test: workflow",
        },
    ]


def finding_codes(result: dict[str, Any]) -> set[str]:
    return {str(item.get("code")) for item in result.get("findings", [])}


def test_dashboard_summary_surfaces_ids_evidence_commit_and_axes() -> None:
    rows = events()
    summary = dashboard.summarize(rows, {"event_count": len(rows)}, "loaded", "cycle-1")
    summary["dashboard_path"] = ".task/cycle/cycle-1/dashboard.md"
    summary["evidence_paths"] = [".task/cycle/cycle-1/stage.jsonl", summary["dashboard_path"]]
    markdown = dashboard.render_summary(summary)
    validated = result_contract.validate("dashboard", summary, "block")

    assert summary["dashboard_status"] == "rendered"
    assert summary["snapshot_status"] == "current"
    assert summary["task_ids"] == ["task-1"]
    assert summary["commit_results"][0]["commit_hash"] == "abc123"
    assert summary["progress_axes"]
    assert "validation.json" in summary["artifacts"]
    assert "Commit 결과" in markdown
    assert validated["status"] != "block", validated


def test_dashboard_loader_fails_closed_on_malformed_json(tmp_path: Path) -> None:
    ledger = tmp_path / "stage.jsonl"
    ledger.write_text('{"step":"context","status":"complete"}\n{broken\n', encoding="utf-8")

    with pytest.raises(dashboard.DashboardDataError, match="line 2"):
        dashboard.load_events(ledger)


def test_dashboard_loader_keeps_canonical_versionless_ledger_readable(
    tmp_path: Path,
) -> None:
    cycle_dir = tmp_path / ".task/cycle/cycle-legacy"
    ledger = cycle_dir / "stage.jsonl"
    ledger.parent.mkdir(parents=True)
    legacy = {"step": "validate", "status": "complete", "reason": "historical"}
    ledger.write_text(json.dumps(legacy) + "\n", encoding="utf-8")
    current_value = {"event_count": 1, "latest_event": legacy}
    current_path = cycle_dir / "current_stage.json"
    current_path.write_text(json.dumps(current_value) + "\n", encoding="utf-8")

    assert dashboard.load_events(ledger) == [{**legacy, "_ledger_line": 1}]
    assert dashboard.load_current(current_path) == (current_value, "loaded")


def test_dashboard_hydrates_compiled_format_v2_ledger_and_current_projection(
    tmp_path: Path,
) -> None:
    cycle_id = "cycle-dashboard-compact"
    (tmp_path / "task.md").write_text("# Task\n\nCompact dashboard.\n", encoding="utf-8")
    init_cycle(tmp_path, cycle_id, "task-dashboard", "compact dashboard")
    advance_stage(tmp_path, cycle_id, apply=True, max_steps=1)
    append_event(
        tmp_path,
        cycle_id,
        {
            "step": "authority",
            "status": "completed",
            "event_id": "authority-dashboard-compact",
            "task_id": "task-dashboard",
            "reason": "authority fixture",
        },
    )
    advance_stage(tmp_path, cycle_id, apply=True, max_steps=2)
    cycle_dir = tmp_path / ".task/cycle" / cycle_id

    rows = dashboard.load_events(cycle_dir / "stage.jsonl")
    compact = [event for event in rows if event.get("format_version") == 2]
    assert compact
    assert all(
        "unsupported_format_version"
        not in dashboard.event_malformed_reasons(event, cycle_id)
        for event in compact
    )
    current, status = dashboard.load_current(cycle_dir / "current_stage.json")
    assert status == "loaded"
    assert current["latest_event"]["event_id"] == rows[-1]["event_id"]
    summary = dashboard.summarize(rows, current, status, cycle_id, tmp_path)
    assert not any(
        "unsupported_format_version"
        in event.get("_dashboard_malformed_reasons", [])
        for event in summary["malformed_events"]
    )


def test_noncanonical_event_and_stale_snapshot_remain_visible() -> None:
    rows = events() + [{"cycle_id": "cycle-1", "step": "mystery", "status": "complete", "reason": "legacy extension"}]
    summary = dashboard.summarize(rows, {"event_count": len(rows) - 1}, "loaded", "cycle-1")
    markdown = dashboard.render_summary(summary)

    assert summary["dashboard_status"] == "warn"
    assert summary["snapshot_status"] == "stale"
    assert summary["malformed_events"][0]["_dashboard_malformed_reasons"] == ["noncanonical_step"]
    assert "비정상/비정식 이벤트" in markdown


def test_dashboard_contract_rejects_rendered_stale_snapshot() -> None:
    payload = {
        "step": "dashboard",
        "task_id": "task-1",
        "dashboard_status": "rendered",
        "event_count": 3,
        "current_stage_event_count": 2,
        "snapshot_status": "stale",
        "validation_verdict": "partial",
        "progress_verdict": "no_progress",
        "blockers": [],
        "dashboard_path": "dashboard.md",
        "evidence_paths": ["stage.jsonl"],
    }

    result = result_contract.validate("dashboard", payload, "block")

    assert result["status"] == "block"
    assert "dashboard_rendered_from_noncurrent_snapshot" in finding_codes(result)


def test_malformed_cross_cycle_event_cannot_supply_dashboard_truth() -> None:
    rows = events() + [
        {
            "format_version": 1,
            "cycle_id": "cycle-other",
            "event_id": "foreign-validation",
            "step": "validate",
            "status": "complete",
            "task_id": "task-foreign",
            "validation_verdict": "failed",
            "progress_verdict": "regressed",
            "blockers": ["foreign-blocker"],
            "evidence_paths": ["foreign.json"],
        }
    ]
    current = {"event_count": len(rows), "latest_event": rows[-1]}

    summary = dashboard.summarize(rows, current, "loaded", "cycle-1")

    assert summary["dashboard_status"] == "warn"
    assert summary["task_id"] == "task-1"
    assert summary["validation_verdict"] == "complete"
    assert summary["progress_verdict"] == "advanced"
    assert "task-foreign" not in summary["task_ids"]
    assert "foreign-blocker" not in summary["blockers"]
    assert "foreign.json" not in summary["artifacts"]
    assert summary["commit_results"][0]["commit_hash"] == "abc123"


def test_same_count_snapshot_with_different_latest_event_id_is_stale() -> None:
    rows = [
        {
            "format_version": 1,
            "cycle_id": "cycle-1",
            "event_id": "context-1",
            "step": "context",
            "status": "complete",
            "task_id": "task-1",
        }
    ]
    current = {
        "event_count": len(rows),
        "latest_event": {**rows[-1], "event_id": "context-stale"},
    }

    summary = dashboard.summarize(rows, current, "loaded", "cycle-1")

    assert summary["snapshot_status"] == "stale"
    assert summary["ledger_latest_event_id"] == "context-1"
    assert summary["current_stage_latest_event_id"] == "context-stale"


def test_dashboard_preserves_six_verdict_axes_and_deduplicates_unchanged_refs() -> None:
    rows = events()
    verdicts = {
        "task_acceptance_verdict": {"status": "pass", "evidence_ref": "packet_K.json"},
        "artifact_truth_verdict": {"status": "pass", "evidence_ref": "packet_K.json"},
        "artifact_semantic_verdict": {"status": "fail", "evidence_ref": "packet_K.json"},
        "pack_transition_verdict": {"status": "pass", "evidence_ref": "pack_P.json"},
        "historical_index_verdict": {"status": "not_evaluated", "evidence_ref": "index_row_R"},
        "goal_readiness_verdict": {"status": "blocked", "evidence_ref": "verdict_V.json"},
    }
    rows[-1].update(
        {
            **verdicts,
            "unchanged_refs": [
                {"path": "packet_K.json", "sha256": "a" * 64},
                {"path": "packet_K.json", "sha256": "a" * 64},
            ],
        }
    )

    summary = dashboard.summarize(rows, {"event_count": len(rows)}, "loaded", "cycle-1")

    assert {item["axis"] for item in summary["verdict_axes"]} == set(verdicts)
    assert summary["unchanged_ref_count"] == 1
    assert summary["unchanged_refs"] == [{"path": "packet_K.json", "sha256": "a" * 64}]
