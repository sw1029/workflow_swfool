from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "orchestrate-task-cycle" / "scripts"


def load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


dashboard = load_module(SCRIPTS / "render_cycle_dashboard.py", "dashboard_contract_renderer")
result_contract = load_module(SCRIPTS / "result_contract.py", "dashboard_contract_validator")


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
