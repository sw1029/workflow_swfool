from __future__ import annotations

from argparse import Namespace
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from typing import Any

import pytest


sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "record-agent-work-log" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import agent_log_integrity as integrity  # noqa: E402
import agent_log_migration as migration  # noqa: E402
import write_agent_log as writer  # noqa: E402


def load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


cycle_context = load_module(
    ROOT / "orchestrate-task-cycle" / "scripts" / "collect_cycle_context.py",
    "agent_log_migration_cycle_context_tests",
)
completion_evidence = load_module(
    ROOT / "validate-task-completion" / "scripts" / "collect_completion_evidence.py",
    "agent_log_migration_completion_evidence_tests",
)
task_state_index = load_module(
    ROOT / "manage-task-state-index" / "scripts" / "task_state_index.py",
    "agent_log_migration_task_state_index_tests",
)
progress_loop = load_module(
    ROOT / "orchestrate-task-cycle" / "scripts" / "detect_progress_loop.py",
    "agent_log_migration_progress_loop_tests",
)


def body(
    title: str,
    *,
    log_id: str | None = None,
    status: str | None = None,
    timestamp: str = "2026-01-01T00:00:00Z",
) -> bytes:
    lines = [f"# {title}", ""]
    if log_id is not None:
        lines.append(f"- Log ID: {log_id}")
    lines.append(f"- Timestamp: {timestamp}")
    if status is not None:
        lines.append(f"- Status: {status}")
    lines.extend(
        [
            "",
            "## Task Intent",
            "fixture intent",
            "",
            "## Work Performed",
            "fixture work",
            "",
            "## Result",
            "fixture result",
            "",
            "## Shortcomings",
            "not evaluated",
            "",
        ]
    )
    return "\n".join(lines).encode("utf-8")


def put_body(root: Path, relative: str, payload: bytes) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


def put_index(root: Path, rows: list[dict[str, Any] | bytes]) -> bytes:
    path = root / ".agent_log" / "index.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    chunks: list[bytes] = []
    for row in rows:
        if isinstance(row, bytes):
            chunks.append(row if row.endswith(b"\n") else row + b"\n")
        else:
            chunks.append(
                (
                    json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                    + "\n"
                ).encode("utf-8")
            )
    payload = b"".join(chunks)
    path.write_bytes(payload)
    return payload


def put_status_map(
    root: Path,
    mappings: list[tuple[str | None, str, str, str | None]],
    *,
    filename: str = "status-map.json",
) -> Path:
    path = root / filename
    document = {
        "schema_version": 1,
        "mapping_policy_id": "fixture-exact-status-policy",
        "version": "1",
        "entries": [
            {
                "original_status": original,
                "normalized_status": normalized,
                "reason": reason,
                **({"status_evidence": evidence} if evidence is not None else {}),
            }
            for original, normalized, reason, evidence in mappings
        ],
    }
    path.write_text(
        json.dumps(document, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def plan_store(root: Path, status_map: Path) -> tuple[dict[str, Any], Path, str, dict[str, Any]]:
    inspection = migration.inspect_store(root)
    plan_path = root / "migration-plan.json"
    result = migration.write_plan(
        root,
        expected_index_sha256=inspection["source_index"]["sha256"],
        status_map_raw=status_map,
        output_raw=plan_path,
    )
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    return inspection, plan_path, result["plan_sha256"], plan


def apply_store(
    root: Path,
    inspection: dict[str, Any],
    plan_path: Path,
    plan_sha: str,
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    return migration.apply_plan(
        root,
        plan_raw=plan_path,
        expected_plan_sha256=plan_sha,
        expected_index_sha256=inspection["source_index"]["sha256"],
        expected_inventory_sha256=inspection["source_inventory_sha256"],
        dry_run=dry_run,
    )


def writer_args(root: Path, index: int = 0) -> Namespace:
    return Namespace(
        root=str(root),
        title=f"Post migration append {index}",
        status="informational",
        intent="Exercise the standard writer after a sealed migration.",
        work="Appended one current-format row.",
        result="The append remained strictly integrity-bound.",
        shortcomings="No completion claim was evaluated.",
        agent_note=[],
        command=[],
        changed_file=[],
        follow_up=[],
        tag=["migration-test"],
        retention_class="unspecified",
        archive_reference=None,
        retention_exclusion_reason=None,
        sensitivity="internal",
        actor="test-agent",
    )


def basic_legacy_store(root: Path) -> tuple[bytes, Path]:
    first_path = ".agent_log/2026-01-01/first.md"
    second_path = ".agent_log/2026-01-01/second.md"
    orphan_path = ".agent_log/2026-01-01/orphan.md"
    first_body = body("First", log_id="log-first", status="partial")
    second_body = body("Second", log_id="log-second", status=None)
    put_body(root, first_path, first_body)
    put_body(root, second_path, second_body)
    put_body(root, orphan_path, body("Orphan"))
    source = put_index(
        root,
        [
            {
                "timestamp": "2026-01-01T00:00:00Z",
                "status": "partial",
                "path": first_path,
                "log_id": "log-first",
                "title": "First",
            },
            {
                "timestamp": "2026-01-01T00:00:00Z",
                "status": "completed",
                "path": first_path,
                "log_id": "wrong-alias",
                "title": "Wrong alias",
            },
            {
                "timestamp": "2026-01-01T00:00:00Z",
                "path": second_path,
                "log_id": "log-second",
                "title": "Second",
            },
            {
                "timestamp": "2026-01-01T00:00:00Z",
                "status": "informational",
                "event": "foreign lifecycle evidence",
            },
        ],
    )
    status_map = put_status_map(
        root,
        [
            ("partial", "partial", "exact partial identity", None),
            ("completed", "completed", "exact completed identity", None),
            ("informational", "informational", "exact informational identity", None),
            (None, "informational", "missing status is not evaluated", "not_evaluated"),
        ],
    )
    return source, status_map


def test_plan_apply_receipt_idempotence_and_standard_append(tmp_path: Path) -> None:
    source, status_map = basic_legacy_store(tmp_path)
    source_sha = hashlib.sha256(source).hexdigest()
    body_hashes = {
        path.relative_to(tmp_path).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (tmp_path / ".agent_log").rglob("*.md")
    }
    inspection, plan_path, plan_sha, plan = plan_store(tmp_path, status_map)
    second_plan = tmp_path / "migration-plan-2.json"
    second = migration.write_plan(
        tmp_path,
        expected_index_sha256=source_sha,
        status_map_raw=status_map,
        output_raw=second_plan,
    )

    assert second["plan_sha256"] == plan_sha
    assert second_plan.read_bytes() == plan_path.read_bytes()
    assert plan["unresolved_count"] == 0
    assert plan["classification_counts"]["canonical_log"] == 2
    assert plan["classification_counts"]["duplicate_alias"] == 1
    assert plan["classification_counts"]["foreign_event"] == 1
    assert plan["classification_counts"]["orphan_markdown"] == 1
    assert len(plan["rows"]) == 4
    assert len(plan["body_resolutions"]) == 3

    before_dry_run = (tmp_path / ".agent_log" / "index.jsonl").read_bytes()
    dry_run = apply_store(tmp_path, inspection, plan_path, plan_sha, dry_run=True)
    assert dry_run["status"] == "dry_run_pass"
    assert (tmp_path / ".agent_log" / "index.jsonl").read_bytes() == before_dry_run
    assert not (tmp_path / ".agent_log" / "migrations").exists()

    applied = apply_store(tmp_path, inspection, plan_path, plan_sha)
    assert applied["status"] == "committed"
    assert applied["source_snapshot_sha256"] == source_sha
    assert Path(applied["source_snapshot"]).read_bytes() == source
    assert all(
        hashlib.sha256((tmp_path / relative).read_bytes()).hexdigest() == digest
        for relative, digest in body_hashes.items()
    )
    validated = migration.validate_receipt(
        tmp_path, applied["receipt"], require_appendable=True
    )
    assert validated["status"] == "valid"
    assert validated["appendability"] == "pass"
    integrity_result, markdown, _ = integrity.inspect_agent_log_store(tmp_path)
    assert integrity_result["status"] == "valid"
    assert integrity_result["legacy_count"] == 0
    assert integrity_result["orphan_count"] == 0
    assert integrity_result["duplicate_count"] == 0
    assert len(markdown) == 3

    marker = json.loads(
        (tmp_path / ".agent_log" / "migrations" / "active.json").read_text(
            encoding="utf-8"
        )
    )
    prefix_size = marker["after_index_size"]
    prefix_sha = marker["after_index_sha256"]
    writer.write_log(writer_args(tmp_path))
    appended_index = (tmp_path / ".agent_log" / "index.jsonl").read_bytes()
    assert len(appended_index) > prefix_size
    assert hashlib.sha256(appended_index[:prefix_size]).hexdigest() == prefix_sha
    after_append = migration.validate_receipt(
        tmp_path, applied["receipt"], require_appendable=True
    )
    assert after_append["status"] == "valid"
    assert after_append["current_index_sha256"] != prefix_sha

    reapplied = apply_store(tmp_path, inspection, plan_path, plan_sha)
    assert reapplied["status"] == "already_committed"
    assert reapplied["idempotent"] is True


def test_exact_status_map_and_missing_status_fail_closed(tmp_path: Path) -> None:
    path = ".agent_log/2026-01-01/unknown.md"
    put_body(tmp_path, path, body("Unknown", status="repository-token"))
    put_index(
        tmp_path,
        [
            {
                "timestamp": "2026-01-01T00:00:00Z",
                "status": "repository-token",
                "path": path,
            }
        ],
    )
    incomplete = put_status_map(
        tmp_path,
        [("informational", "informational", "unrelated exact token", None)],
    )
    inspection, plan_path, plan_sha, plan = plan_store(tmp_path, incomplete)
    assert plan["unresolved_count"] == 1
    assert "not mapped" in plan["rows"][0]["unresolved_reason"]
    with pytest.raises(migration.MigrationError, match="unresolved_count"):
        apply_store(tmp_path, inspection, plan_path, plan_sha)

    unsafe_upgrade = put_status_map(
        tmp_path,
        [("repository-token", "completed", "unsafe promotion", None)],
        filename="unsafe-map.json",
    )
    with pytest.raises(migration.MigrationError, match="may not create"):
        migration.write_plan(
            tmp_path,
            expected_index_sha256=inspection["source_index"]["sha256"],
            status_map_raw=unsafe_upgrade,
            output_raw=tmp_path / "unsafe-plan.json",
        )

    missing_bad = put_status_map(
        tmp_path,
        [(None, "informational", "missing", None)],
        filename="missing-bad.json",
    )
    with pytest.raises(migration.MigrationError, match="status_evidence"):
        migration.write_plan(
            tmp_path,
            expected_index_sha256=inspection["source_index"]["sha256"],
            status_map_raw=missing_bad,
            output_raw=tmp_path / "missing-bad-plan.json",
        )


@pytest.mark.parametrize(
    "case",
    [
        "malformed_json",
        "missing_body",
        "tampered_body",
        "path_traversal",
        "future_version",
        "tampered_current",
    ],
)
def test_unsafe_source_rows_are_unresolved_without_mutation(
    tmp_path: Path, case: str
) -> None:
    safe_path = ".agent_log/2026-01-01/safe.md"
    safe_body = body("Safe", status="informational")
    put_body(tmp_path, safe_path, safe_body)
    if case == "malformed_json":
        rows: list[dict[str, Any] | bytes] = [b"{"]
    elif case == "missing_body":
        rows = [
            {
                "timestamp": "2026-01-01T00:00:00Z",
                "status": "informational",
                "path": ".agent_log/2026-01-01/missing.md",
            }
        ]
    elif case == "tampered_body":
        rows = [
            {
                "timestamp": "2026-01-01T00:00:00Z",
                "status": "informational",
                "path": safe_path,
                "body_sha256": "0" * 64,
            }
        ]
    elif case == "path_traversal":
        rows = [
            {
                "timestamp": "2026-01-01T00:00:00Z",
                "status": "informational",
                "path": ".agent_log/../outside.md",
            }
        ]
    elif case == "future_version":
        rows = [
            {
                "format_version": integrity.LOG_FORMAT_VERSION + 1,
                "schema_version": integrity.LOG_SCHEMA_VERSION,
                "timestamp": "2026-01-01T00:00:00Z",
                "status": "informational",
                "path": safe_path,
            }
        ]
    else:
        body_sha = hashlib.sha256(safe_body).hexdigest()
        current = {
            "format_version": integrity.LOG_FORMAT_VERSION,
            "schema_version": integrity.LOG_SCHEMA_VERSION,
            "log_id": "log-current-tampered",
            "body_sha256": body_sha,
            "content_id": integrity.content_id_for(body_sha),
            "timestamp": "2026-01-01T00:00:00Z",
            "status": "informational",
            "path": safe_path,
        }
        current["record_id"] = "log-record-" + "0" * 32
        rows = [current]
    source = put_index(tmp_path, rows)
    status_map = put_status_map(
        tmp_path,
        [("informational", "informational", "exact identity", None)],
    )
    inspection, plan_path, plan_sha, plan = plan_store(tmp_path, status_map)
    assert plan["unresolved_count"] >= 1
    with pytest.raises(migration.MigrationError, match="unresolved_count"):
        apply_store(tmp_path, inspection, plan_path, plan_sha)
    assert (tmp_path / ".agent_log" / "index.jsonl").read_bytes() == source
    assert not (tmp_path / ".agent_log" / "migrations").exists()


def test_conflicting_duplicate_path_fails_closed(tmp_path: Path) -> None:
    path = ".agent_log/2026-01-01/conflict.md"
    put_body(tmp_path, path, b"opaque body without structured metadata\n")
    put_index(
        tmp_path,
        [
            {
                "timestamp": "2026-01-01T00:00:00Z",
                "status": "informational",
                "path": path,
                "variant": "a",
            },
            {
                "timestamp": "2026-01-01T00:00:00Z",
                "status": "informational",
                "path": path,
                "variant": "b",
            },
        ],
    )
    status_map = put_status_map(
        tmp_path,
        [("informational", "informational", "exact identity", None)],
    )
    _, _, _, plan = plan_store(tmp_path, status_map)
    assert plan["unresolved_count"] == 2
    assert all("tie or conflict" in row["unresolved_reason"] for row in plan["rows"])


def test_identical_body_different_path_is_sealed_nonconsumable_alias(
    tmp_path: Path,
) -> None:
    payload = body("Identical", log_id="log-identical", status="informational")
    paths = [
        ".agent_log/2026-01-01/identical-a.md",
        ".agent_log/2026-01-01/identical-b.md",
    ]
    for path in paths:
        put_body(tmp_path, path, payload)
    put_index(
        tmp_path,
        [
            {
                "timestamp": "2026-01-01T00:00:00Z",
                "status": "informational",
                "path": path,
                "log_id": "log-identical",
                "title": "Identical",
            }
            for path in paths
        ],
    )
    status_map = put_status_map(
        tmp_path,
        [("informational", "informational", "exact identity", None)],
    )
    inspection, plan_path, plan_sha, plan = plan_store(tmp_path, status_map)
    assert plan["unresolved_count"] == 0
    assert plan["classification_counts"]["canonical_log"] == 1
    assert plan["classification_counts"]["duplicate_alias"] == 1
    assert plan["classification_counts"]["body_alias_markdown"] == 1
    applied = apply_store(tmp_path, inspection, plan_path, plan_sha)
    result, markdown, _ = integrity.inspect_agent_log_store(tmp_path)
    assert result["status"] == "valid"
    assert result["orphan_count"] == 0
    assert result["migration"]["sealed_nonconsumable_count"] == 1
    assert len(markdown) == 1
    consumable_path = markdown[0].relative_to(tmp_path).as_posix()
    alias_path = next(path for path in paths if path != consumable_path)

    cycle_paths = {
        item["path"]
        for item in cycle_context.collect_agent_log(tmp_path, 100)["latest_markdown"]
    }
    completion_paths = {
        item["path"]
        for item in completion_evidence.collect_agent_log(tmp_path, 100)["latest_markdown"]
    }
    discovered_paths = {
        path
        for item_type, path, *_ in task_state_index.discover_standard_artifacts(tmp_path)
        if item_type in {"agent_log", "past_task"}
    }
    progress_paths = {
        path.relative_to(tmp_path).as_posix()
        for path in progress_loop.candidate_files(tmp_path)
        if ".agent_log" in path.parts
    }
    assert alias_path not in cycle_paths
    assert alias_path not in completion_paths
    assert alias_path not in discovered_paths
    assert alias_path not in progress_paths

    receipt = json.loads(Path(applied["receipt"]).read_text(encoding="utf-8"))
    assert receipt["body_alias_count"] == 1


def test_valid_current_row_identity_and_source_bytes_are_preserved_while_orphan_is_bound(
    tmp_path: Path,
) -> None:
    writer.write_log(writer_args(tmp_path))
    index_path = tmp_path / ".agent_log" / "index.jsonl"
    current_row_bytes = index_path.read_bytes()
    put_body(
        tmp_path,
        ".agent_log/2026-01-01/legacy-orphan.md",
        body("Legacy orphan"),
    )
    status_map = put_status_map(
        tmp_path,
        [("informational", "informational", "exact current identity", None)],
    )
    inspection, plan_path, plan_sha, plan = plan_store(tmp_path, status_map)
    assert plan["unresolved_count"] == 0
    applied = apply_store(tmp_path, inspection, plan_path, plan_sha)
    migrated_rows = [
        json.loads(line)
        for line in index_path.read_text(encoding="utf-8").splitlines()
    ]
    assert migrated_rows[0] == json.loads(current_row_bytes)
    assert migrated_rows[0]["record_id"] == json.loads(current_row_bytes)["record_id"]
    assert migrated_rows[1]["legacy_import"] is True
    assert Path(applied["source_snapshot"]).read_bytes() == current_row_bytes
    assert migration.validate_receipt(
        tmp_path, applied["receipt"], require_appendable=True
    )["status"] == "valid"


def test_symlink_inventory_is_rejected_read_only(tmp_path: Path) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir()
    (outside / "secret.md").write_text("secret\n", encoding="utf-8")
    log_root = tmp_path / ".agent_log"
    log_root.mkdir()
    (log_root / "linked").symlink_to(outside, target_is_directory=True)
    put_index(tmp_path, [])
    with pytest.raises(migration.MigrationError, match="symlink"):
        migration.inspect_store(tmp_path)
    assert (outside / "secret.md").read_text(encoding="utf-8") == "secret\n"


def test_source_or_status_map_drift_is_zero_mutation(tmp_path: Path) -> None:
    source, status_map = basic_legacy_store(tmp_path)
    inspection, plan_path, plan_sha, _ = plan_store(tmp_path, status_map)
    index_path = tmp_path / ".agent_log" / "index.jsonl"
    index_path.write_bytes(source + b"\n")
    with pytest.raises(migration.MigrationError, match="drift"):
        apply_store(tmp_path, inspection, plan_path, plan_sha)
    assert not (tmp_path / ".agent_log" / "migrations").exists()

    index_path.write_bytes(source)
    status_map.write_text(status_map.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    with pytest.raises(migration.MigrationError, match="status map drift"):
        apply_store(tmp_path, inspection, plan_path, plan_sha)
    assert not (tmp_path / ".agent_log" / "migrations").exists()


def test_directory_fsync_failure_propagates_before_index_switch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, status_map = basic_legacy_store(tmp_path)
    inspection, plan_path, plan_sha, _ = plan_store(tmp_path, status_map)

    def fail_fsync(_path: Path) -> None:
        raise OSError("injected directory fsync failure")

    monkeypatch.setattr(migration, "_strict_fsync_directory", fail_fsync)
    with pytest.raises(OSError, match="directory fsync failure"):
        apply_store(tmp_path, inspection, plan_path, plan_sha)
    assert (tmp_path / ".agent_log" / "index.jsonl").read_bytes() == source


def test_unknown_status_row_added_after_plan_rejects_stale_plan(tmp_path: Path) -> None:
    source, status_map = basic_legacy_store(tmp_path)
    inspection, plan_path, plan_sha, _ = plan_store(tmp_path, status_map)
    new_path = ".agent_log/2026-01-02/new-unknown.md"
    put_body(tmp_path, new_path, body("New unknown", status="new-repository-token"))
    new_row = {
        "timestamp": "2026-01-02T00:00:00Z",
        "status": "new-repository-token",
        "path": new_path,
    }
    index_path = tmp_path / ".agent_log" / "index.jsonl"
    index_path.write_bytes(
        source
        + (
            json.dumps(new_row, sort_keys=True, separators=(",", ":")) + "\n"
        ).encode("utf-8")
    )
    with pytest.raises(migration.MigrationError, match="source index drift"):
        apply_store(tmp_path, inspection, plan_path, plan_sha)
    assert not (tmp_path / ".agent_log" / "migrations").exists()


@pytest.mark.parametrize(
    "failpoint",
    [
        "after_snapshot",
        "after_sidecars",
        "after_prepare",
        "after_switch",
        "after_receipt",
        "after_journal_commit",
        "after_marker",
    ],
)
def test_crash_recovery_is_forward_only_or_source_preserving(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failpoint: str
) -> None:
    source, status_map = basic_legacy_store(tmp_path)
    inspection, plan_path, plan_sha, plan = plan_store(tmp_path, status_map)
    monkeypatch.setenv("AGENT_LOG_MIGRATION_FAILPOINT", failpoint)
    with pytest.raises(RuntimeError, match="injected migration crash"):
        apply_store(tmp_path, inspection, plan_path, plan_sha)
    monkeypatch.delenv("AGENT_LOG_MIGRATION_FAILPOINT")

    index_path = tmp_path / ".agent_log" / "index.jsonl"
    if failpoint in {"after_snapshot", "after_sidecars"}:
        assert index_path.read_bytes() == source
        result = apply_store(tmp_path, inspection, plan_path, plan_sha)
        assert result["status"] == "committed"
    elif failpoint == "after_prepare":
        recovered = migration.recover(tmp_path, plan["migration_id"])
        assert recovered["status"] == "prepared_aborted"
        assert index_path.read_bytes() == source
        result = apply_store(tmp_path, inspection, plan_path, plan_sha)
        assert result["status"] == "committed"
    else:
        assert index_path.read_bytes() != source
        recovered = migration.recover(tmp_path, plan["migration_id"])
        assert recovered["status"] == "forward_completed"
        result = recovered
    receipt = result["receipt"]
    assert migration.validate_receipt(
        tmp_path, receipt, require_appendable=True
    )["status"] == "valid"
    snapshot = (
        tmp_path
        / ".agent_log"
        / "migrations"
        / plan["migration_id"]
        / "source-index.snapshot"
    )
    assert snapshot.read_bytes() == source


def test_concurrent_apply_and_writer_share_exclusive_lock(tmp_path: Path) -> None:
    _, status_map = basic_legacy_store(tmp_path)
    inspection, plan_path, plan_sha, plan = plan_store(tmp_path, status_map)
    script = SCRIPTS / "agent_log_migration.py"
    command = [
        sys.executable,
        str(script),
        "apply",
        "--root",
        str(tmp_path),
        "--plan",
        str(plan_path),
        "--expected-plan-sha256",
        plan_sha,
        "--expected-index-sha256",
        inspection["source_index"]["sha256"],
        "--expected-inventory-sha256",
        inspection["source_inventory_sha256"],
    ]
    environment = {
        **os.environ,
        "PYTHONDONTWRITEBYTECODE": "1",
        "AGENT_LOG_MIGRATION_LOCK_HOLD_SECONDS": "0.4",
    }
    first = subprocess.Popen(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=environment)
    journal = (
        tmp_path
        / ".agent_log"
        / "migrations"
        / plan["migration_id"]
        / "journal.json"
    )
    deadline = time.monotonic() + 5
    while not journal.exists() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert journal.exists()

    writer_script = SCRIPTS / "write_agent_log.py"
    writer_command = [
        sys.executable,
        str(writer_script),
        "--root",
        str(tmp_path),
        "--title",
        "Concurrent append",
        "--status",
        "informational",
        "--intent",
        "Wait for the migration lock.",
        "--work",
        "Append after migration publication.",
        "--result",
        "Writer returned a current row.",
        "--shortcomings",
        "No completion verdict.",
    ]
    writer_process = subprocess.Popen(
        writer_command,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    second = subprocess.run(command, text=True, capture_output=True, env=environment, check=False)
    first_stdout, first_stderr = first.communicate(timeout=10)
    writer_stdout, writer_stderr = writer_process.communicate(timeout=10)
    assert first.returncode == 0, first_stderr
    assert second.returncode == 0, second.stderr
    assert writer_process.returncode == 0, writer_stderr
    statuses = {
        json.loads(first_stdout)["status"],
        json.loads(second.stdout)["status"],
    }
    assert statuses == {"committed", "already_committed"}
    assert json.loads(writer_stdout)["record_id"].startswith("log-record-")
    result, _, _ = integrity.inspect_agent_log_store(tmp_path)
    assert result["status"] == "valid"
    assert result["indexed_count"] == plan["expected_after_row_count"] + 1


@pytest.mark.parametrize(
    "target", ["resolution_manifest_ref", "receipt", "journal", "active_marker"]
)
def test_tampered_or_missing_seal_evidence_is_rejected(
    tmp_path: Path, target: str
) -> None:
    _, status_map = basic_legacy_store(tmp_path)
    inspection, plan_path, plan_sha, _ = plan_store(tmp_path, status_map)
    applied = apply_store(tmp_path, inspection, plan_path, plan_sha)
    receipt_path = Path(applied["receipt"])
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if target == "resolution_manifest_ref":
        manifest = tmp_path / receipt["resolution_manifest_ref"]
        manifest.write_bytes(manifest.read_bytes() + b"\n")
    elif target == "receipt":
        receipt_path.write_bytes(receipt_path.read_bytes() + b"\n")
    elif target == "journal":
        marker = json.loads(
            (tmp_path / ".agent_log" / "migrations" / "active.json").read_text(
                encoding="utf-8"
            )
        )
        journal = tmp_path / marker["journal_ref"]
        journal.write_bytes(journal.read_bytes() + b"\n")
    else:
        (tmp_path / ".agent_log" / "migrations" / "active.json").unlink()
    with pytest.raises(migration.MigrationError):
        migration.validate_receipt(tmp_path, receipt_path, require_appendable=True)
    inspection_result, _, _ = integrity.inspect_agent_log_store(tmp_path)
    assert inspection_result["status"] == "invalid"


def test_marker_sidecars_cannot_be_deleted_to_bypass_migration_validation(
    tmp_path: Path,
) -> None:
    _, status_map = basic_legacy_store(tmp_path)
    inspection, plan_path, plan_sha, _ = plan_store(tmp_path, status_map)
    applied = apply_store(tmp_path, inspection, plan_path, plan_sha)
    migrations = tmp_path / ".agent_log" / "migrations"
    shutil.rmtree(migrations)
    result, _, _ = integrity.inspect_agent_log_store(tmp_path)
    assert result["status"] == "invalid"
    assert "require a committed marker" in result["findings"][0]["detail"]
    with pytest.raises(integrity.AgentLogIntegrityError):
        writer.write_log(writer_args(tmp_path))
    assert Path(applied["receipt"]).exists() is False
