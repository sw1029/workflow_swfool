from __future__ import annotations

import hashlib
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
for package_root in (
    ROOT / "record-agent-work-log" / "scripts",
    ROOT / "manage-task-state-index" / "scripts",
    ROOT / "manage-external-advice" / "scripts",
    ROOT / "orchestrate-task-cycle" / "scripts",
    ROOT / "validate-task-completion" / "scripts",
):
    if str(package_root) not in sys.path:
        sys.path.insert(0, str(package_root))


from record_agent_work_log import write as work_log  # noqa: E402
from manage_task_state_index import index as task_state_index  # noqa: E402
from manage_external_advice import registry as advice_registry  # noqa: E402
from orchestrate_task_cycle import collect_cycle_context as cycle_context  # noqa: E402
from orchestrate_task_cycle.progress import api as progress_loop  # noqa: E402
from validate_task_completion import collect_completion_evidence as completion_evidence  # noqa: E402


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
    assert record["body_sha256"] == hashlib.sha256(Path(result["path"]).read_bytes()).hexdigest()
    assert record["content_id"] == f"log-content-{record['body_sha256'][:32]}"
    assert record["record_id"] == work_log.expected_record_id(record)
    assert f"- Log ID: {record['log_id']}" in body
    assert "- Retention class: immutable-evidence" in body
    assert "- Sensitivity: internal" in body
    for collector in (cycle_context.collect_agent_log, completion_evidence.collect_agent_log):
        integrity = collector(tmp_path, 10)["integrity"]
        assert integrity["status"] == "valid"
        assert integrity["verified_count"] == 1


def test_blank_direct_input_cannot_be_labeled_completed(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="must be explicitly non-empty"):
        work_log.write_log(args_for(tmp_path, status="completed", result=""))
    assert not (tmp_path / ".agent_log").exists()


def test_external_advice_handoff_uses_integrity_bound_writer(tmp_path: Path) -> None:
    relative = advice_registry.write_past_advice_log(
        tmp_path,
        {
            "advice_id": "advice-1",
            "title": "Use bounded evidence",
            "path": ".agent_advice/active/advice-1.md",
            "raw_source_path": ".agent_advice/raw/advice-1.md",
        },
        "task.md:12",
        "Applied to the active task.",
    )

    assert relative.startswith(".agent_log/")
    integrity = cycle_context.collect_agent_log(tmp_path, 10)["integrity"]
    assert integrity["status"] == "valid"
    assert integrity["verified_count"] == 1
    records = [
        json.loads(line)
        for line in (tmp_path / ".agent_log" / "index.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert records[0]["title"].startswith("past_advice:")
    assert records[0]["body_sha256"]


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
    environment = {
        **os.environ,
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONPATH": str(ROOT / "record-agent-work-log" / "scripts"),
    }

    def invoke(index: int) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                "-m",
                "record_agent_work_log",
                "write",
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


def test_agent_log_symlink_is_rejected_without_writing_or_collecting_outside(
    tmp_path: Path,
) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-outside-agent-log"
    outside.mkdir()
    (outside / "secret.md").write_text("# outside secret\n", encoding="utf-8")
    (tmp_path / ".agent_log").symlink_to(outside, target_is_directory=True)

    with pytest.raises(ValueError, match="symlink|workspace"):
        work_log.write_log(args_for(tmp_path))

    assert sorted(path.name for path in outside.iterdir()) == ["secret.md"]
    for collector in (cycle_context.collect_agent_log, completion_evidence.collect_agent_log):
        projection = collector(tmp_path, 10)
        assert projection["integrity"]["status"] == "unsafe"
        assert projection["markdown_count"] == 0
        assert "outside secret" not in json.dumps(projection, sort_keys=True)
    discovered = task_state_index.discover_standard_artifacts(tmp_path)
    assert not any(item_type in {"agent_log", "past_task"} for item_type, *_ in discovered)
    assert "outside secret" not in json.dumps(discovered, sort_keys=True)
    assert not progress_loop.candidate_files(tmp_path)


def test_body_tampering_fails_closed_and_is_reported_by_collectors(tmp_path: Path) -> None:
    result = work_log.write_log(args_for(tmp_path))
    Path(result["path"]).write_text("tampered\n", encoding="utf-8")

    with pytest.raises(ValueError, match="body SHA-256 mismatch"):
        work_log.write_log(args_for(tmp_path, 1))

    for collector in (cycle_context.collect_agent_log, completion_evidence.collect_agent_log):
        projection = collector(tmp_path, 10)
        assert projection["integrity"]["status"] == "invalid"
        assert projection["integrity"]["tampered_count"] == 1
        assert "agent_log_body_hash_mismatch" in {
            finding["code"] for finding in projection["integrity"]["findings"]
        }
    assert not any(
        item_type in {"agent_log", "past_task"}
        for item_type, *_ in task_state_index.discover_standard_artifacts(tmp_path)
    )
    assert not any(
        ".agent_log" in path.parts
        for path in progress_loop.candidate_files(tmp_path)
    )


def test_duplicate_ids_and_paths_fail_closed(tmp_path: Path) -> None:
    work_log.write_log(args_for(tmp_path))
    index = tmp_path / ".agent_log" / "index.jsonl"
    row = index.read_text(encoding="utf-8")
    index.write_text(row + row, encoding="utf-8")

    with pytest.raises(ValueError, match="duplicate log_id"):
        work_log.write_log(args_for(tmp_path, 1))

    for collector in (cycle_context.collect_agent_log, completion_evidence.collect_agent_log):
        integrity = collector(tmp_path, 10)["integrity"]
        assert integrity["status"] == "invalid"
        assert integrity["duplicate_count"] >= 2


def test_orphan_markdown_fails_closed_and_is_reported(tmp_path: Path) -> None:
    work_log.write_log(args_for(tmp_path))
    orphan = tmp_path / ".agent_log" / "2026-01-01" / "orphan.md"
    orphan.parent.mkdir(parents=True)
    orphan.write_text("# orphan\n", encoding="utf-8")

    with pytest.raises(ValueError, match="orphan agent-log Markdown"):
        work_log.write_log(args_for(tmp_path, 1))

    for collector in (cycle_context.collect_agent_log, completion_evidence.collect_agent_log):
        projection = collector(tmp_path, 10)
        assert projection["integrity"]["status"] == "invalid"
        assert projection["integrity"]["orphan_count"] == 1
        assert projection["integrity"]["orphan_paths"] == [
            ".agent_log/2026-01-01/orphan.md"
        ]


def test_nested_agent_log_symlink_component_is_rejected(tmp_path: Path) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-outside-nested-agent-log"
    outside.mkdir()
    log_root = tmp_path / ".agent_log"
    log_root.mkdir()
    (log_root / "2099-01-01").symlink_to(outside, target_is_directory=True)

    with pytest.raises(ValueError, match="symlink"):
        work_log.write_log(args_for(tmp_path))

    for collector in (cycle_context.collect_agent_log, completion_evidence.collect_agent_log):
        projection = collector(tmp_path, 10)
        assert projection["integrity"]["status"] == "unsafe"
        assert projection["markdown_count"] == 0
