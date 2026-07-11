from __future__ import annotations

import importlib.util
import json
import os
import subprocess
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


task_state_index = load_module(
    ROOT / "manage-task-state-index" / "scripts" / "task_state_index.py",
    "task_state_index_registry_tests",
)


def test_scan_keeps_stable_id_for_ordinary_same_path_edit(tmp_path: Path) -> None:
    task = tmp_path / "task.md"
    task.write_text("# First task wording\n", encoding="utf-8")
    first = task_state_index.scan_artifacts(tmp_path)
    first_id = first["events"][0]["id"]

    task.write_text("# Clarified task wording\n\nSame semantic task, more detail.\n", encoding="utf-8")
    second = task_state_index.scan_artifacts(tmp_path)
    state = task_state_index.merge_state(task_state_index.load_events(tmp_path))
    audit = task_state_index.audit_index(tmp_path)

    assert second["events"][0]["id"] == first_id
    assert set(state) == {first_id}
    assert state[first_id]["title"] == "Clarified task wording"
    assert state[first_id]["content_sha256"] == task_state_index.sha256_file(task)
    assert not any(issue["code"] == "duplicate_active_path" for issue in audit["issues"])


def test_explicit_new_id_is_a_semantic_replacement(tmp_path: Path) -> None:
    task = tmp_path / "task.md"
    task.write_text("# First task\n", encoding="utf-8")
    first = task_state_index.upsert_item(tmp_path, "task", "task.md", "active", replace_existing=False)

    task.write_text("# Replacement task\n", encoding="utf-8")
    second = task_state_index.upsert_item(
        tmp_path,
        "task",
        "task.md",
        "active",
        item_id="task-explicit-replacement",
        replace_existing=False,
    )
    state = task_state_index.merge_state(task_state_index.load_events(tmp_path))

    assert second["id"] == "task-explicit-replacement"
    assert state[first["id"]]["status"] == "superseded"
    assert {tuple(link.values()) for link in state[first["id"]]["links"]} >= {
        ("superseded_by", "task-explicit-replacement")
    }
    assert {tuple(link.values()) for link in state[second["id"]]["links"]} >= {
        ("supersedes", first["id"])
    }
    assert second["lifecycle_transition_result"]["atomic"] is True


def test_replace_flag_allocates_a_new_id_even_with_same_title_and_second(tmp_path: Path) -> None:
    task = tmp_path / "task.md"
    task.write_text("# Same title\n", encoding="utf-8")
    first = task_state_index.upsert_item(tmp_path, "task", "task.md", "active", replace_existing=False)
    task.write_text("# Same title\n\nSemantically replaced body.\n", encoding="utf-8")

    second = task_state_index.upsert_item(tmp_path, "task", "task.md", "active", replace_existing=True)

    assert second["id"] != first["id"]
    assert second["lifecycle_transition_result"]["atomic"] is True


def test_partially_resolved_is_preserved_as_an_open_residual_state(tmp_path: Path) -> None:
    miss = tmp_path / "partially_resolved-gap.md"
    miss.write_text("# Gap\n\n- status: partially_resolved\n", encoding="utf-8")

    assert task_state_index.infer_miss_status(miss) == "partially_resolved"
    assert "partially_resolved" in task_state_index.LIFECYCLE_STATUSES
    assert "partially_resolved" not in task_state_index.NON_ACTIVE_STATUSES


def test_closed_status_vocabulary_and_versioned_legacy_compatibility(tmp_path: Path) -> None:
    index = tmp_path / ".task" / "index.jsonl"
    index.parent.mkdir(parents=True)
    legacy = {
        "event": "upsert",
        "id": "task-legacy",
        "type": "task",
        "status": "active",
        "path": "task.md",
        "title": "Legacy",
        "updated_at": "2026-01-01T00:00:00+00:00",
    }
    index.write_text(json.dumps(legacy) + "\n", encoding="utf-8")

    assert task_state_index.load_events(tmp_path) == [legacy]
    task_state_index.append_event(
        tmp_path,
        {
            "event": "link",
            "id": "task-legacy",
            "updated_at": "2026-01-01T00:00:01+00:00",
            "links": [{"rel": "related_to", "id": "task-legacy-peer"}],
        },
    )
    rows = task_state_index.load_events(tmp_path)
    assert rows[-1]["format_version"] == task_state_index.INDEX_FORMAT_VERSION
    assert rows[-1]["schema_version"] == task_state_index.INDEX_SCHEMA_VERSION

    with pytest.raises(ValueError, match="Unsupported lifecycle status"):
        task_state_index.upsert_item(tmp_path, "task", "task.md", "made_up")


def test_malformed_or_future_jsonl_fails_closed_without_append(tmp_path: Path) -> None:
    index = tmp_path / ".task" / "index.jsonl"
    index.parent.mkdir(parents=True)
    index.write_text("{\n", encoding="utf-8")
    before = index.read_bytes()

    with pytest.raises(ValueError, match="Malformed task-state JSONL"):
        task_state_index.load_events(tmp_path)
    with pytest.raises(ValueError, match="Malformed task-state JSONL"):
        task_state_index.append_event(
            tmp_path,
            {"event": "link", "id": "task-a", "updated_at": "2026-01-01T00:00:00+00:00", "links": []},
        )
    assert index.read_bytes() == before

    future = {
        "format_version": task_state_index.INDEX_FORMAT_VERSION + 1,
        "schema_version": task_state_index.INDEX_SCHEMA_VERSION,
        "event": "upsert",
        "id": "task-future",
        "type": "task",
        "status": "active",
        "path": "task.md",
        "title": "Future",
        "updated_at": "2026-01-01T00:00:00+00:00",
    }
    index.write_text(json.dumps(future) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Unsupported task-state format_version"):
        task_state_index.load_events(tmp_path)


def test_concurrent_same_path_updates_keep_jsonl_durable_and_one_active_id(tmp_path: Path) -> None:
    task = tmp_path / "task.md"
    task.write_text("# Concurrent task\n", encoding="utf-8")

    def update(index: int) -> str:
        result = task_state_index.upsert_item(
            tmp_path,
            "task",
            "task.md",
            "active",
            title=f"Concurrent observation {index}",
            replace_existing=False,
        )
        return result["id"]

    with ThreadPoolExecutor(max_workers=8) as executor:
        ids = list(executor.map(update, range(32)))

    rows = task_state_index.load_events(tmp_path)
    state = task_state_index.merge_state(rows)
    audit = task_state_index.audit_index(tmp_path)

    assert len(set(ids)) == 1
    assert len(state) == 1
    assert len(rows) == 32
    assert all(row["format_version"] == task_state_index.INDEX_FORMAT_VERSION for row in rows)
    assert not any(issue["code"] == "duplicate_active_path" for issue in audit["issues"])
    assert not list((tmp_path / ".task").glob(".*.tmp"))


def test_concurrent_cli_processes_share_the_workspace_lock(tmp_path: Path) -> None:
    (tmp_path / "task.md").write_text("# Process-safe task\n", encoding="utf-8")
    script = ROOT / "manage-task-state-index" / "scripts" / "task_state_index.py"
    environment = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}

    def invoke(index: int) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(script),
                "--root",
                str(tmp_path),
                "add",
                "--type",
                "task",
                "--path",
                "task.md",
                "--status",
                "active",
                "--title",
                f"Process observation {index}",
            ],
            check=False,
            capture_output=True,
            text=True,
            env=environment,
        )

    with ThreadPoolExecutor(max_workers=6) as executor:
        results = list(executor.map(invoke, range(12)))

    assert all(result.returncode == 0 for result in results), [result.stderr for result in results]
    rows = task_state_index.load_events(tmp_path)
    state = task_state_index.merge_state(rows)
    assert len(rows) == 12
    assert len(state) == 1


def test_empty_registry_is_not_reported_as_evaluated_success(tmp_path: Path) -> None:
    audit = task_state_index.audit_index(tmp_path)

    assert audit["audit_evidence_status"] == "not_evaluated_no_artifacts"
    assert "success" not in audit and "complete" not in audit
