from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from argparse import Namespace
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


work_log = load_module(
    ROOT / "record-agent-work-log" / "scripts" / "write_agent_log.py",
    "agent_work_log_integrity_tests",
)


def args_for(root: Path, index: int = 0, **overrides: Any) -> Namespace:
    values: dict[str, Any] = {
        "root": str(root),
        "title": f"Concurrent record {index}",
        "status": "informational",
        "intent": "Preserve an evidence-backed handoff.",
        "work": f"Recorded bounded work item {index}.",
        "result": "A durable record was produced; no completion verdict was inferred.",
        "shortcomings": "Completion remains owned by the validation workflow.",
        "agent_note": [],
        "command": [],
        "changed_file": [],
        "follow_up": [],
        "tag": ["integrity"],
        "retention_class": "immutable-evidence",
        "archive_reference": ".agent_log/archive-manifest.json",
        "retention_exclusion_reason": None,
        "sensitivity": "internal",
        "actor": "test-agent",
    }
    values.update(overrides)
    return Namespace(**values)


def test_status_is_explicit_closed_vocabulary_and_required_fields_are_nonblank() -> None:
    parser = work_log.build_parser()
    required = [
        "--intent",
        "intent",
        "--work",
        "work",
        "--result",
        "result",
        "--shortcomings",
        "none",
    ]
    with pytest.raises(SystemExit):
        parser.parse_args(required)
    with pytest.raises(SystemExit):
        parser.parse_args(["--status", "invented", *required])
    with pytest.raises(SystemExit):
        parser.parse_args(["--status", "informational", *required[:-7], "--intent", "   ", *required[2:]])


def test_record_contains_versions_status_retention_and_sensitivity(tmp_path: Path) -> None:
    result = work_log.write_log(args_for(tmp_path))
    record = json.loads((tmp_path / ".agent_log" / "index.jsonl").read_text(encoding="utf-8"))
    body = Path(result["path"]).read_text(encoding="utf-8")

    assert result["log_id"] == record["log_id"]
    assert record["format_version"] == work_log.LOG_FORMAT_VERSION
    assert record["schema_version"] == work_log.LOG_SCHEMA_VERSION
    assert record["status"] == "informational"
    assert record["retention_class"] == "immutable-evidence"
    assert record["sensitivity"] == "internal"
    assert f"- Log ID: {record['log_id']}" in body
    assert "- Retention class: immutable-evidence" in body
    assert "- Sensitivity: internal" in body


def test_blank_direct_input_cannot_be_labeled_completed(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="must be explicitly non-empty"):
        work_log.write_log(args_for(tmp_path, status="completed", result=""))
    assert not (tmp_path / ".agent_log").exists()


def test_legacy_index_is_readable_and_new_record_is_versioned(tmp_path: Path) -> None:
    index = tmp_path / ".agent_log" / "index.jsonl"
    index.parent.mkdir(parents=True)
    legacy = {
        "timestamp": "2026-01-01T00:00:00+00:00",
        "status": "partial",
        "path": ".agent_log/2026-01-01/legacy.md",
    }
    index.write_text(json.dumps(legacy) + "\n", encoding="utf-8")

    work_log.write_log(args_for(tmp_path))
    rows = [json.loads(line) for line in index.read_text(encoding="utf-8").splitlines()]

    assert rows[0] == legacy
    assert rows[1]["format_version"] == work_log.LOG_FORMAT_VERSION
    assert rows[1]["schema_version"] == work_log.LOG_SCHEMA_VERSION


def test_malformed_index_fails_closed_before_publishing_log(tmp_path: Path) -> None:
    index = tmp_path / ".agent_log" / "index.jsonl"
    index.parent.mkdir(parents=True)
    index.write_text("{\n", encoding="utf-8")
    before = index.read_bytes()

    with pytest.raises(ValueError, match="Malformed agent-log index"):
        work_log.write_log(args_for(tmp_path))

    assert index.read_bytes() == before
    assert not list((tmp_path / ".agent_log").rglob("*.md"))


def test_concurrent_writes_have_unique_ids_paths_and_complete_jsonl_rows(tmp_path: Path) -> None:
    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(lambda index: work_log.write_log(args_for(tmp_path, index)), range(32)))

    index = tmp_path / ".agent_log" / "index.jsonl"
    rows = [json.loads(line) for line in index.read_text(encoding="utf-8").splitlines()]
    ids = {record["log_id"] for record in rows}
    paths = {record["path"] for record in rows}

    assert len(results) == len(rows) == len(ids) == len(paths) == 32
    assert all((tmp_path / path).is_file() for path in paths)
    assert all(record["status"] == "informational" for record in rows)
    assert all(record["format_version"] == work_log.LOG_FORMAT_VERSION for record in rows)
    assert not list((tmp_path / ".agent_log").rglob("*.tmp"))


def test_concurrent_cli_processes_share_the_workspace_lock(tmp_path: Path) -> None:
    script = ROOT / "record-agent-work-log" / "scripts" / "write_agent_log.py"
    environment = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}

    def invoke(index: int) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(script),
                "--root",
                str(tmp_path),
                "--title",
                f"Process record {index}",
                "--status",
                "informational",
                "--intent",
                "Exercise cross-process locking.",
                "--work",
                f"Writer process {index} created one record.",
                "--result",
                "The process returned its durable record path.",
                "--shortcomings",
                "No completion verdict was evaluated.",
                "--sensitivity",
                "internal",
            ],
            check=False,
            capture_output=True,
            text=True,
            env=environment,
        )

    with ThreadPoolExecutor(max_workers=6) as executor:
        results = list(executor.map(invoke, range(12)))

    assert all(result.returncode == 0 for result in results), [result.stderr for result in results]
    index = tmp_path / ".agent_log" / "index.jsonl"
    rows = [json.loads(line) for line in index.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 12
    assert len({row["log_id"] for row in rows}) == 12
    assert all((tmp_path / row["path"]).is_file() for row in rows)
