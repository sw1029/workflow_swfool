from __future__ import annotations

import json
from pathlib import Path

import pytest

from orchestrate_task_cycle.cycle_ledger import init_cycle, read_events
from orchestrate_task_cycle.stage import cli as stage_cli
from orchestrate_task_cycle.stage import deterministic_execution
from orchestrate_task_cycle.stage import service as stage_service


def _cycle(root: Path, cycle_id: str) -> str:
    (root / "task.md").write_text(
        "# Task\n\nExercise preparation stop propagation.\n",
        encoding="utf-8",
    )
    init_cycle(root, cycle_id, "task-preparation-stop", "preparation stop")
    return cycle_id


def _preparation(
    target: str,
    executor_kind: str,
    next_action: dict[str, object],
) -> dict[str, object]:
    return {
        "schema_version": 3,
        "target": target,
        "executor_kind": executor_kind,
        "preparation_id": f"prep-{target}",
        "next_action": next_action,
    }


def test_advance_propagates_owner_stop_and_preserves_applied_actions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cycle_id = _cycle(tmp_path, "cycle-owner-stop")
    blocked = _preparation(
        "authority",
        "owner",
        {"kind": "stop", "reason": "awaiting_advice_normalization"},
    )
    monkeypatch.setattr(stage_service, "prepare_stage", lambda *_args, **_kwargs: blocked)

    output = stage_service.advance_stage(
        tmp_path,
        cycle_id,
        apply=True,
        max_steps=2,
    )

    assert output["status"] == "block"
    assert output["stop_reason"] == "awaiting_advice_normalization"
    assert output["preparation"] is blocked
    assert output["applied"] is True
    assert [action["kind"] for action in output["actions"]] == [
        "append_system_context"
    ]
    assert [event["step"] for event in read_events(tmp_path, cycle_id)] == ["context"]
    assert output["model_call_count"] == 0
    assert output["model_visible_bytes"] == 0


def test_execute_stop_never_dispatches_renderer_and_cli_returns_block_exit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cycle_id = _cycle(tmp_path, "cycle-deterministic-stop")
    blocked = _preparation(
        "repo_skill_adapter_scan",
        "deterministic",
        {"kind": "stop", "reason": "awaiting_advice_normalization"},
    )
    monkeypatch.setattr(stage_service, "prepare_stage", lambda *_args, **_kwargs: blocked)

    def forbidden_renderer(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("blocked preparation reached deterministic renderer")

    monkeypatch.setattr(
        deterministic_execution,
        "apply_prepared_deterministic",
        forbidden_renderer,
    )

    exit_code = stage_cli.main(
        [
            "execute",
            "--root",
            str(tmp_path),
            "--cycle-id",
            cycle_id,
            "--target",
            "repo_skill_adapter_scan",
            "--apply",
        ]
    )
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 2
    assert output["status"] == "block"
    assert output["stop_reason"] == "awaiting_advice_normalization"
    assert output["applied"] is False
    assert output["model_call_count"] == 0
    assert output["model_visible_bytes"] == 0
    assert "action" not in output
    assert "actions" not in output
    assert "deterministic_execution" not in output


def test_normal_owner_preparation_still_waits_at_owner_boundary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cycle_id = _cycle(tmp_path, "cycle-owner-normal")
    ready = _preparation(
        "authority",
        "owner",
        {"kind": "submit_exact_inputs"},
    )
    monkeypatch.setattr(stage_service, "prepare_stage", lambda *_args, **_kwargs: ready)

    output = stage_service.advance_stage(
        tmp_path,
        cycle_id,
        apply=True,
        max_steps=2,
    )

    assert output["status"] == "waiting"
    assert output["stop_reason"] == "awaiting_authority"
    assert output["preparation"] is ready
    assert output["applied"] is True
    assert [action["kind"] for action in output["actions"]] == [
        "append_system_context"
    ]


def test_normal_deterministic_dry_run_still_returns_execute_action(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ready = _preparation(
        "repo_skill_adapter_scan",
        "deterministic",
        {"kind": "execute_deterministic"},
    )
    monkeypatch.setattr(stage_service, "prepare_stage", lambda *_args, **_kwargs: ready)

    output = stage_service.execute_deterministic_stage(
        tmp_path,
        "cycle-not-read-for-dry-run",
        "repo_skill_adapter_scan",
        apply=False,
    )

    assert output["status"] == "ready"
    assert output["stop_reason"] is None
    assert output["action"] == {
        "kind": "execute_deterministic",
        "target": "repo_skill_adapter_scan",
        "preparation_id": "prep-repo_skill_adapter_scan",
    }
    assert output["applied"] is False
