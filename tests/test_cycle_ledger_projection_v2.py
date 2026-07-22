from __future__ import annotations

import json
from pathlib import Path

import pytest

from orchestrate_task_cycle import cycle_ledger


def _current_path(root: Path, cycle_id: str) -> Path:
    return root / ".task" / "cycle" / cycle_id / "current_stage.json"


def _append_context(root: Path, cycle_id: str, *, sentinel: str) -> dict:
    return cycle_ledger.append_event(
        root,
        cycle_id,
        {
            "event_id": f"{cycle_id}-context",
            "step": "context",
            "status": "complete",
            "task_id": "task-1",
            "reason": "context established",
            "structured_context": {
                "sentinel": sentinel,
                "nested": {"body": "x" * 200_000},
            },
        },
    )


def test_legacy_cycle_preserves_full_current_stage_shape(tmp_path: Path) -> None:
    cycle_id = "cycle-legacy-projection"
    initialized = cycle_ledger.init_cycle(
        tmp_path,
        cycle_id,
        "task-1",
        "legacy projection",
        stage_compiler_protocol_version=1,
        stage_preparation_schema_version=1,
    )
    assert initialized["initialization"]["stage_compiler_protocol_version"] == 1
    assert initialized["initialization"]["stage_preparation_schema_version"] == 1

    _append_context(tmp_path, cycle_id, sentinel="legacy-full-sentinel")
    stored = json.loads(_current_path(tmp_path, cycle_id).read_text(encoding="utf-8"))

    assert "projection_version" not in stored
    assert stored["latest_event"]["structured_context"]["sentinel"] == (
        "legacy-full-sentinel"
    )
    assert cycle_ledger.read_current_expanded(tmp_path, cycle_id) == stored


def test_protocol_v2_stores_compact_refs_and_hydrates_exact_events(
    tmp_path: Path,
) -> None:
    cycle_id = "cycle-compact-projection"
    initialized = cycle_ledger.init_cycle(
        tmp_path,
        cycle_id,
        "task-1",
        "compact projection",
        stage_compiler_protocol_version=2,
    )
    assert initialized["initialization"]["stage_compiler_protocol_version"] == 2
    assert initialized["current_stage"]["projection_version"] == 2

    _append_context(tmp_path, cycle_id, sentinel="must-not-be-projected")
    stored_bytes = _current_path(tmp_path, cycle_id).read_bytes()
    stored = json.loads(stored_bytes)
    events = cycle_ledger.read_events(tmp_path, cycle_id)

    assert b"must-not-be-projected" not in stored_bytes
    assert b"structured_context" not in stored_bytes
    assert len(stored_bytes) < 16_384
    assert stored["kind"] == "cycle_current_stage_projection"
    assert stored["projection_version"] == 2
    assert stored["latest_event"]["kind"] == "cycle_ledger_event_ref"
    assert stored["latest_event"]["ledger_sequence"] == 1
    assert stored["latest_event"]["event_sha256"] == cycle_ledger.canonical_sha256(
        events[0]
    )

    expanded = cycle_ledger.read_current_expanded(tmp_path, cycle_id)
    assert expanded["latest_event"] == events[0]
    assert expanded["steps"]["context"] == events[0]
    assert expanded["latest_event"]["structured_context"]["sentinel"] == (
        "must-not-be-projected"
    )


def test_protocol_v2_current_projection_is_replay_stable(tmp_path: Path) -> None:
    cycle_id = "cycle-compact-replay"
    cycle_ledger.init_cycle(
        tmp_path,
        cycle_id,
        "task-1",
        "compact replay",
        stage_compiler_protocol_version=2,
    )
    first = _append_context(tmp_path, cycle_id, sentinel="replay-sentinel")
    replay = _append_context(tmp_path, cycle_id, sentinel="replay-sentinel")

    assert first.get("event_duplicate") is not True
    assert replay["event_duplicate"] is True
    assert len(cycle_ledger.read_events(tmp_path, cycle_id)) == 1
    assert replay["current_stage"]["latest_event"]["event_id"] == (
        first["event"]["event_id"]
    )
    assert cycle_ledger.read_current_expanded(tmp_path, cycle_id)["latest_event"] == (
        first["event"]
    )


def test_protocol_v2_hydrator_rejects_projection_tampering(tmp_path: Path) -> None:
    cycle_id = "cycle-compact-tamper"
    cycle_ledger.init_cycle(
        tmp_path,
        cycle_id,
        "task-1",
        "compact tamper",
        stage_compiler_protocol_version=2,
    )
    _append_context(tmp_path, cycle_id, sentinel="tamper-sentinel")

    path = _current_path(tmp_path, cycle_id)
    stored = json.loads(path.read_text(encoding="utf-8"))
    stored["latest_event"]["event_sha256"] = "0" * 64
    path.write_text(json.dumps(stored, sort_keys=True) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="does not match the authoritative ledger"):
        cycle_ledger.read_current_expanded(tmp_path, cycle_id)


def test_protocol_activation_is_explicit_and_immutable(tmp_path: Path) -> None:
    cycle_id = "cycle-explicit-protocol"
    first = cycle_ledger.init_cycle(
        tmp_path,
        cycle_id,
        "task-1",
        "explicit protocol",
        stage_compiler_protocol_version=2,
    )
    replay = cycle_ledger.init_cycle(
        tmp_path,
        cycle_id,
        "task-1",
        "explicit protocol",
    )

    assert first["initialization"]["stage_compiler_protocol_version"] == 2
    assert replay["current_stage"]["projection_version"] == 2
    with pytest.raises(ValueError, match="already initialized"):
        cycle_ledger.init_cycle(
            tmp_path,
            cycle_id,
            "task-1",
            "explicit protocol",
            stage_compiler_protocol_version=1,
        )
    with pytest.raises(ValueError, match="unsupported stage_compiler_protocol_version"):
        cycle_ledger.init_cycle(
            tmp_path,
            "cycle-unsupported-protocol",
            "task-1",
            "unsupported protocol",
            stage_compiler_protocol_version=3,
        )


def test_cli_defaults_new_cycles_to_v2_but_preserves_existing_v1(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert (
        cycle_ledger.main(
            [
                "--root",
                str(tmp_path),
                "init",
                "--cycle-id",
                "cycle-cli-v2",
                "--task-id",
                "task-1",
                "--reason",
                "cli v2",
            ]
        )
        == 0
    )
    created = json.loads(capsys.readouterr().out)
    assert created["initialization"]["stage_compiler_protocol_version"] == 2
    assert created["current_stage"]["projection_version"] == 2

    cycle_ledger.init_cycle(
        tmp_path,
        "cycle-cli-v1",
        "task-1",
        "cli v1",
        stage_compiler_protocol_version=1,
        stage_preparation_schema_version=1,
    )
    assert (
        cycle_ledger.main(
            [
                "--root",
                str(tmp_path),
                "init",
                "--cycle-id",
                "cycle-cli-v1",
                "--task-id",
                "task-1",
                "--reason",
                "cli v1",
            ]
        )
        == 0
    )
    replayed = json.loads(capsys.readouterr().out)
    assert replayed["initialization"]["stage_compiler_protocol_version"] == 1
    assert replayed["initialization"]["stage_preparation_schema_version"] == 1
    assert "projection_version" not in replayed["current_stage"]
