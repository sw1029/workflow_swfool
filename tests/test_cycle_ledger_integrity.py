from __future__ import annotations

import importlib.util
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest


sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]


def load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


cycle_ledger = load_module(
    ROOT / "orchestrate-task-cycle" / "scripts" / "cycle_ledger.py",
    "cycle_ledger_integrity",
)


EXPECTED_STEPS = [
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


def test_canonical_step_order_matches_transition_contract() -> None:
    assert cycle_ledger.DEFAULT_STEPS == EXPECTED_STEPS


def initialize_with_context(root: Path, cycle_id: str, task_id: str = "task-1", reason: str = "init") -> None:
    cycle_ledger.init_cycle(root, cycle_id, task_id, reason)
    cycle_ledger.append_event(
        root,
        cycle_id,
        {"step": "context", "status": "complete", "task_id": task_id, "reason": "context established"},
    )


def test_append_requires_initialization_context_and_task_coherence(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="must be initialized"):
        cycle_ledger.append_event(tmp_path, "cycle-missing-init", {"step": "context", "status": "complete"})

    cycle_ledger.init_cycle(tmp_path, "cycle-order", "task-1", "init")
    with pytest.raises(ValueError, match="first canonical stage event"):
        cycle_ledger.append_event(tmp_path, "cycle-order", {"step": "authority", "status": "complete"})
    with pytest.raises(ValueError, match="context task_id must match"):
        cycle_ledger.append_event(
            tmp_path,
            "cycle-order",
            {"step": "context", "status": "complete", "task_id": "task-other"},
        )

    cycle_ledger.init_cycle(
        tmp_path,
        "cycle-bootstrap",
        None,
        "bootstrap",
        allow_missing_task_for_bootstrap=True,
    )
    bootstrap = cycle_ledger.append_event(
        tmp_path,
        "cycle-bootstrap",
        {"step": "context", "status": "complete", "task_absent": True},
    )
    assert bootstrap["event"]["task_id"] is None


def test_append_requires_status_and_matching_cycle_id(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="explicit non-empty `status`"):
        cycle_ledger.append_event(tmp_path, "cycle-a", {"step": "run"})

    with pytest.raises(ValueError, match="does not match ledger cycle"):
        cycle_ledger.append_event(
            tmp_path,
            "cycle-a",
            {"cycle_id": "cycle-b", "step": "run", "status": "complete"},
        )

    assert not (tmp_path / ".task" / "cycle" / "cycle-a" / "stage.jsonl").exists()


def test_cycle_directory_symlink_escape_is_rejected(tmp_path: Path) -> None:
    cycle_root = tmp_path / ".task" / "cycle"
    cycle_root.mkdir(parents=True)
    outside = tmp_path / "outside-cycle-storage"
    outside.mkdir()
    (cycle_root / "cycle-escape").symlink_to(outside, target_is_directory=True)

    with pytest.raises(ValueError, match="escapes .task/cycle"):
        cycle_ledger.append_event(
            tmp_path,
            "cycle-escape",
            {"step": "run", "status": "complete"},
        )

    assert not (outside / "stage.jsonl").exists()


def test_default_cycle_and_event_ids_are_collision_resistant(tmp_path: Path) -> None:
    first = cycle_ledger.init_cycle(tmp_path, None, "task-1", "first")
    second = cycle_ledger.init_cycle(tmp_path, None, "task-2", "second")

    assert first["cycle_id"] != second["cycle_id"]
    assert len(first["cycle_id"].rsplit("-", 1)[-1]) == 32
    cycle_ledger.append_event(
        tmp_path,
        first["cycle_id"],
        {"step": "context", "status": "complete", "task_id": "task-1"},
    )

    one = cycle_ledger.append_event(
        tmp_path,
        first["cycle_id"],
        {"step": "run", "status": "complete"},
    )
    two = cycle_ledger.append_event(
        tmp_path,
        first["cycle_id"],
        {"step": "run", "status": "complete"},
    )
    assert one["event"]["event_id"] != two["event"]["event_id"]


def test_explicit_event_id_is_idempotent_and_conflicts_fail_closed(tmp_path: Path) -> None:
    initialize_with_context(tmp_path, "cycle-dedupe")
    packet = {"event_id": "run-fixed", "step": "run", "status": "complete", "reason": "same"}

    first = cycle_ledger.append_event(tmp_path, "cycle-dedupe", packet)
    second = cycle_ledger.append_event(tmp_path, "cycle-dedupe", packet)

    assert first.get("event_duplicate") is not True
    assert second["event_duplicate"] is True
    assert len(cycle_ledger.read_events(tmp_path, "cycle-dedupe")) == 2

    with pytest.raises(ValueError, match="different content"):
        cycle_ledger.append_event(
            tmp_path,
            "cycle-dedupe",
            {**packet, "reason": "conflict"},
        )


def test_artifact_hashes_are_immutable_and_only_exact_repeats_are_unchanged(tmp_path: Path) -> None:
    artifact = tmp_path / "packet.json"
    artifact.write_text('{"value": 1}\n', encoding="utf-8")
    initialize_with_context(tmp_path, "cycle-artifact")

    first = cycle_ledger.append_event(
        tmp_path,
        "cycle-artifact",
        {"step": "run", "status": "complete", "artifacts": ["packet.json"]},
    )
    repeated = cycle_ledger.append_event(
        tmp_path,
        "cycle-artifact",
        {"step": "validate", "status": "complete", "artifacts": ["packet.json"]},
    )
    old_hash = first["event"]["artifact_refs"][0]["sha256"]
    assert repeated["event"]["unchanged_refs"] == [{"path": "packet.json", "sha256": old_hash}]

    artifact.write_text('{"value": 2}\n', encoding="utf-8")
    changed = cycle_ledger.append_event(
        tmp_path,
        "cycle-artifact",
        {"step": "report", "status": "complete", "artifacts": ["packet.json"]},
    )

    assert changed["event"]["artifact_refs"][0]["sha256"] != old_hash
    assert changed["event"]["unchanged_refs"] == []
    assert cycle_ledger.read_events(tmp_path, "cycle-artifact")[1]["artifact_refs"][0]["sha256"] == old_hash


def test_supplied_artifact_ref_must_match_current_body(tmp_path: Path) -> None:
    artifact = tmp_path / "packet.json"
    artifact.write_text("{}\n", encoding="utf-8")
    initialize_with_context(tmp_path, "cycle-supplied-ref")

    with pytest.raises(ValueError, match="does not match current artifact"):
        cycle_ledger.append_event(
            tmp_path,
            "cycle-supplied-ref",
            {
                "step": "run",
                "status": "complete",
                "artifact_refs": [{"path": "packet.json", "sha256": "0" * 64}],
            },
        )
    assert [row["step"] for row in cycle_ledger.read_events(tmp_path, "cycle-supplied-ref")] == ["context"]


def test_malformed_or_unsupported_jsonl_fails_closed_without_append(tmp_path: Path) -> None:
    cycle_id = "cycle-corrupt"
    cycle_ledger.init_cycle(tmp_path, cycle_id, "task-1", "init")
    ledger = tmp_path / ".task" / "cycle" / cycle_id / "stage.jsonl"
    ledger.parent.mkdir(parents=True, exist_ok=True)
    valid = {"cycle_id": cycle_id, "event_id": "event-1", "step": "run", "status": "complete"}
    ledger.write_text(json.dumps(valid) + "\n{\n", encoding="utf-8")
    before = ledger.read_bytes()

    with pytest.raises(ValueError, match="malformed ledger JSON"):
        cycle_ledger.read_events(tmp_path, cycle_id)
    with pytest.raises(ValueError, match="malformed ledger JSON"):
        cycle_ledger.append_event(tmp_path, cycle_id, {"step": "validate", "status": "complete"})
    assert ledger.read_bytes() == before

    ledger.write_text(
        json.dumps({**valid, "format_version": cycle_ledger.LEDGER_FORMAT_VERSION + 1}) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="unsupported ledger format_version"):
        cycle_ledger.read_events(tmp_path, cycle_id)


def test_corrective_event_clears_latest_step_failure(tmp_path: Path) -> None:
    initialize_with_context(tmp_path, "cycle-corrective")
    cycle_ledger.append_event(
        tmp_path,
        "cycle-corrective",
        {"step": "validate", "status": "failed"},
    )
    corrected = cycle_ledger.append_event(
        tmp_path,
        "cycle-corrective",
        {"step": "validate", "status": "complete", "reason": "corrected"},
    )

    assert corrected["current_stage"]["status"] == "complete"
    assert corrected["current_stage"]["steps"]["validate"]["status"] == "complete"


def test_terminal_latch_appends_compact_durable_observations(tmp_path: Path) -> None:
    terminal = {
        "step": "report",
        "status": "complete",
        "terminal_justified": True,
        "terminal_outcome_family_key": "family-a",
        "input_state_fingerprint": "input-a",
        "authority_state_fingerprint": "authority-a",
    }
    initialize_with_context(tmp_path, "cycle-terminal")
    cycle_ledger.append_event(tmp_path, "cycle-terminal", terminal)
    repeated = cycle_ledger.append_event(tmp_path, "cycle-terminal", terminal)
    rows = cycle_ledger.read_events(tmp_path, "cycle-terminal")

    assert repeated["event_suppressed"] is True
    assert repeated["observation_appended"] is True
    assert len(rows) == 3
    assert rows[-1]["event_kind"] == "terminal_latch_observation"
    assert rows[-1]["compact_observation"] is True
    assert rows[-1]["terminal_latch_streak"] == 2
    assert rows[-1]["unchanged_terminal_ref"] == rows[-2]["event_id"]

    restart = cycle_ledger.init_cycle(
        tmp_path,
        "cycle-restart-not-created",
        "task-1",
        "restart",
        {key: value for key, value in terminal.items() if key not in {"step", "status"}},
    )
    rows = cycle_ledger.read_events(tmp_path, "cycle-terminal")
    assert restart["cycle_suppressed"] is True
    assert restart["observation_result"]["observation_appended"] is True
    assert rows[-1]["terminal_latch_streak"] == 3
    assert not (tmp_path / ".task" / "cycle" / "cycle-restart-not-created").exists()


def test_concurrent_appends_are_complete_unique_jsonl_records(tmp_path: Path) -> None:
    cycle_id = "cycle-concurrent"
    initialize_with_context(tmp_path, cycle_id)

    def append(index: int) -> str:
        result = cycle_ledger.append_event(
            tmp_path,
            cycle_id,
            {
                "event_id": f"run-{index}",
                "step": "run",
                "status": "complete",
                "reason": f"worker-{index}",
            },
        )
        return str(result["event"]["event_id"])

    with ThreadPoolExecutor(max_workers=8) as executor:
        event_ids = list(executor.map(append, range(32)))

    rows = cycle_ledger.read_events(tmp_path, cycle_id)
    assert len(rows) == 33
    assert len(set(event_ids)) == 32
    assert len({row["event_id"] for row in rows}) == 33
    current = json.loads((tmp_path / ".task" / "cycle" / cycle_id / "current_stage.json").read_text(encoding="utf-8"))
    assert current["event_count"] == 33
    assert current["format_version"] == cycle_ledger.LEDGER_FORMAT_VERSION


def test_versionless_legacy_rows_remain_readable(tmp_path: Path) -> None:
    cycle_id = "cycle-legacy"
    ledger = tmp_path / ".task" / "cycle" / cycle_id / "stage.jsonl"
    ledger.parent.mkdir(parents=True)
    ledger.write_text(
        json.dumps({"cycle_id": cycle_id, "event_id": "legacy-1", "step": "run", "status": "complete"}) + "\n",
        encoding="utf-8",
    )

    assert cycle_ledger.read_events(tmp_path, cycle_id)[0].get("format_version") is None
    with pytest.raises(ValueError, match="must be initialized"):
        cycle_ledger.append_event(
            tmp_path,
            cycle_id,
            {"step": "validate", "status": "complete"},
        )
