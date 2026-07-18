from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest


sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
TASK_STATE_SCRIPTS = ROOT / "manage-task-state-index" / "scripts"
AGENT_LOG_SCRIPTS = ROOT / "record-agent-work-log" / "scripts"
for package_root in (TASK_STATE_SCRIPTS, AGENT_LOG_SCRIPTS):
    if str(package_root) not in sys.path:
        sys.path.insert(0, str(package_root))


from manage_task_state_index import index as task_state_index  # noqa: E402


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


def test_audit_treats_completed_aliases_as_non_active_history(tmp_path: Path) -> None:
    artifact = tmp_path / ".task" / "task_pack" / "pack-P.json"
    artifact.parent.mkdir(parents=True)
    artifact.write_text('{"pack_id":"pack-P","status":"completed","items":[]}\n', encoding="utf-8")
    digest = task_state_index.sha256_file(artifact)
    for item_id in ("pack-old", "pack-current"):
        task_state_index.append_event(
            tmp_path,
            {
                "event": "upsert",
                "id": item_id,
                "type": "task_pack",
                "status": "completed",
                "path": ".task/task_pack/pack-P.json",
                "title": "pack-P",
                "updated_at": "2026-01-01T00:00:00+00:00",
                "content_sha256": digest,
            },
        )

    audit = task_state_index.audit_index(tmp_path)

    assert not any(issue["code"] == "duplicate_active_path" for issue in audit["issues"])


def test_audit_does_not_compare_superseded_identity_to_mutable_path_body(tmp_path: Path) -> None:
    artifact = tmp_path / ".task" / "task_pack" / "pack-P.json"
    artifact.parent.mkdir(parents=True)
    artifact.write_text('{"pack_id":"pack-P","status":"active","items":[]}\n', encoding="utf-8")
    task_state_index.append_event(
        tmp_path,
        {
            "event": "upsert",
            "id": "pack-history",
            "type": "task_pack",
            "status": "superseded",
            "path": ".task/task_pack/pack-P.json",
            "title": "pack-P history",
            "updated_at": "2026-01-01T00:00:00+00:00",
            "content_sha256": "0" * 64,
        },
    )

    audit = task_state_index.audit_index(tmp_path)

    assert not any(
        issue["code"] == "digest_mismatch" and "pack-history" in issue.get("ids", [])
        for issue in audit["issues"]
    )


def test_scan_retires_legacy_active_task_pack_render_identity(tmp_path: Path) -> None:
    pack_json = tmp_path / ".task" / "task_pack" / "pack-P.json"
    pack_md = pack_json.with_suffix(".md")
    pack_json.parent.mkdir(parents=True)
    pack_json.write_text('{"pack_id":"pack-P","status":"completed","items":[]}\n', encoding="utf-8")
    pack_md.write_text("# pack-P render\n", encoding="utf-8")
    task_state_index.append_event(
        tmp_path,
        {
            "event": "upsert",
            "id": "pack-render-alias",
            "type": "task_pack",
            "status": "active",
            "path": ".task/task_pack/pack-P.md",
            "title": "pack-P render",
            "updated_at": "2026-01-01T00:00:00+00:00",
            "content_sha256": task_state_index.sha256_file(pack_md),
        },
    )

    planned = task_state_index.scan_artifacts(tmp_path, dry_run=True)
    state_before = task_state_index.merge_state(task_state_index.load_events(tmp_path))
    applied = task_state_index.scan_artifacts(tmp_path)
    state_after = task_state_index.merge_state(task_state_index.load_events(tmp_path))
    replay = task_state_index.scan_artifacts(tmp_path, dry_run=True)

    assert state_before["pack-render-alias"]["status"] == "active"
    assert any(
        item.get("correction_reason") == "supersede_noncanonical_task_pack_render"
        for item in planned["pending_artifacts"]
    )
    assert applied["mutation_performed"] is True
    assert state_after["pack-render-alias"]["status"] == "superseded"
    assert state_after["pack-render-alias"]["fields"]["canonical_pack_path"] == ".task/task_pack/pack-P.json"
    assert replay["would_change"] is False
    assert pack_json.is_file() and pack_md.is_file()


def test_scan_semantic_noop_preserves_markdown_bytes_timestamp_and_mtime(tmp_path: Path) -> None:
    task = tmp_path / "task.md"
    task.write_text("# Stable task\n", encoding="utf-8")
    first = task_state_index.scan_artifacts(tmp_path)
    index = tmp_path / ".task" / "index.jsonl"
    markdown = tmp_path / ".task" / "index.md"
    before_index = index.read_bytes()
    before_markdown = markdown.read_bytes()
    before_mtime = markdown.stat().st_mtime_ns

    second = task_state_index.scan_artifacts(tmp_path)

    assert first["index_md_changed"] is True
    assert second["indexed_events"] == 0
    assert second["index_md_changed"] is False
    assert second["mutation_performed"] is False
    assert index.read_bytes() == before_index
    assert markdown.read_bytes() == before_markdown
    assert markdown.stat().st_mtime_ns == before_mtime


def test_scan_real_projection_change_republishes_markdown(tmp_path: Path) -> None:
    task = tmp_path / "task.md"
    task.write_text("# Before title\n", encoding="utf-8")
    task_state_index.scan_artifacts(tmp_path)
    index = tmp_path / ".task" / "index.jsonl"
    markdown = tmp_path / ".task" / "index.md"
    before_index = index.read_bytes()
    before_markdown = markdown.read_bytes()

    task.write_text("# After title\n", encoding="utf-8")
    result = task_state_index.scan_artifacts(tmp_path)

    assert result["indexed_events"] == 1
    assert result["index_md_changed"] is True
    assert result["mutation_performed"] is True
    assert index.read_bytes() != before_index
    assert markdown.read_bytes() != before_markdown
    assert b"After title" in markdown.read_bytes()


def test_scan_repairs_missing_and_stale_markdown_without_ledger_event(tmp_path: Path) -> None:
    task = tmp_path / "task.md"
    task.write_text("# Repair view\n", encoding="utf-8")
    task_state_index.scan_artifacts(tmp_path)
    index = tmp_path / ".task" / "index.jsonl"
    markdown = tmp_path / ".task" / "index.md"
    ledger = index.read_bytes()

    markdown.unlink()
    missing = task_state_index.scan_artifacts(tmp_path)
    repaired = markdown.read_bytes()
    assert missing["indexed_events"] == 0
    assert missing["index_md_changed"] is True
    assert index.read_bytes() == ledger
    assert b"Repair view" in repaired

    malformed = repaired.decode("utf-8")
    malformed = re.sub(r"^- Generated: .+$", "- Generated: not-a-timestamp", malformed, flags=re.MULTILINE)
    markdown.write_text(malformed, encoding="utf-8")
    stale = task_state_index.scan_artifacts(tmp_path)
    assert stale["indexed_events"] == 0
    assert stale["index_md_changed"] is True
    assert index.read_bytes() == ledger
    assert b"not-a-timestamp" not in markdown.read_bytes()
    assert b"Repair view" in markdown.read_bytes()


def test_scan_dry_run_with_artifact_creates_no_task_state_files(tmp_path: Path) -> None:
    (tmp_path / "task.md").write_text("# Planned task\n", encoding="utf-8")

    result = task_state_index.scan_artifacts(tmp_path, dry_run=True)

    assert result["mode"] == "dry_run"
    assert result["mutation_performed"] is False
    assert result["planned_artifact_updates"] == 1
    assert result["would_change"] is True
    assert not (tmp_path / ".task").exists()


def test_scan_dry_run_without_index_context_is_a_clean_noop(tmp_path: Path) -> None:
    result = task_state_index.scan_artifacts(tmp_path, dry_run=True)

    assert result["scan_evidence_status"] == "not_evaluated_no_artifacts"
    assert result["would_change"] is False
    assert result["index_md_would_change"] is False
    assert not (tmp_path / ".task").exists()
    applied = task_state_index.scan_artifacts(tmp_path)
    assert applied["mutation_performed"] is False
    assert not (tmp_path / ".task").exists()


def test_scan_rejects_non_file_canonical_index_path_without_mutation(tmp_path: Path) -> None:
    invalid = tmp_path / ".task" / "index.jsonl"
    invalid.mkdir(parents=True)
    with pytest.raises(ValueError, match="not a regular file"):
        task_state_index.scan_artifacts(tmp_path, dry_run=True)
    with pytest.raises(ValueError, match="not a regular file"):
        task_state_index.scan_artifacts(tmp_path)
    assert invalid.is_dir()
    assert not (tmp_path / ".task" / "index.md").exists()


def test_scan_check_reports_missing_jsonl_without_rewriting_matching_view(tmp_path: Path) -> None:
    task_dir = tmp_path / ".task"
    task_dir.mkdir(parents=True)
    markdown = task_dir / "index.md"
    markdown.write_bytes(task_state_index._render_markdown_payload({}, "2026-07-12T00:00:00+09:00"))
    before = markdown.read_bytes()

    planned = task_state_index.scan_artifacts(tmp_path, dry_run=True)
    assert planned["would_change"] is True
    assert planned["index_jsonl_would_change"] is True
    assert planned["index_md_would_change"] is False

    applied = task_state_index.scan_artifacts(tmp_path)
    assert applied["mutation_performed"] is True
    assert applied["index_jsonl_changed"] is True
    assert (task_dir / "index.jsonl").is_file()
    assert markdown.read_bytes() == before


def test_scan_dry_run_projects_body_only_update_per_surface(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task = tmp_path / "task.md"
    task.write_text("# Same title\n\nold body\n", encoding="utf-8")
    task_state_index.scan_artifacts(tmp_path)
    events = task_state_index.load_events(tmp_path)
    stable_time = str(events[-1]["updated_at"])
    markdown = tmp_path / ".task" / "index.md"
    before_markdown = markdown.read_bytes()
    monkeypatch.setattr(task_state_index, "now_iso", lambda: stable_time)
    task.write_text("# Same title\n\nnew body\n", encoding="utf-8")

    planned = task_state_index.scan_artifacts(tmp_path, dry_run=True)
    assert planned["would_change"] is True
    assert planned["planned_artifact_updates"] == 1
    assert planned["index_jsonl_would_change"] is True
    assert planned["index_md_would_change"] is False

    applied = task_state_index.scan_artifacts(tmp_path)
    assert applied["index_jsonl_changed"] is True
    assert applied["index_md_changed"] is False
    assert markdown.read_bytes() == before_markdown


def test_scan_dry_run_preserves_existing_index_and_markdown_bytes(tmp_path: Path) -> None:
    task = tmp_path / "task.md"
    task.write_text("# Existing task\n", encoding="utf-8")
    task_state_index.scan_artifacts(tmp_path)
    index = tmp_path / ".task" / "index.jsonl"
    markdown = tmp_path / ".task" / "index.md"
    task.write_text("# Pending title\n", encoding="utf-8")
    before_index = index.read_bytes()
    before_markdown = markdown.read_bytes()
    before_mtimes = (index.stat().st_mtime_ns, markdown.stat().st_mtime_ns)

    result = task_state_index.scan_artifacts(tmp_path, dry_run=True)

    assert result["planned_artifact_updates"] == 1
    assert result["would_change"] is True
    assert result["index_md_would_change"] is True
    assert index.read_bytes() == before_index
    assert markdown.read_bytes() == before_markdown
    assert (index.stat().st_mtime_ns, markdown.stat().st_mtime_ns) == before_mtimes


def test_scan_check_exit_code_reports_pending_changes_without_mutation(tmp_path: Path) -> None:
    task = tmp_path / "task.md"
    task.write_text("# Check task\n", encoding="utf-8")
    task_state_index.scan_artifacts(tmp_path)
    environment = {
        **os.environ,
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONPATH": os.pathsep.join((str(TASK_STATE_SCRIPTS), str(AGENT_LOG_SCRIPTS))),
    }
    index = tmp_path / ".task" / "index.jsonl"
    markdown = tmp_path / ".task" / "index.md"

    clean = subprocess.run(
        [sys.executable, "-m", "manage_task_state_index", "index", "--root", str(tmp_path), "scan", "--check"],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )
    assert clean.returncode == 0
    assert json.loads(clean.stdout)["mode"] == "check"

    task.write_text("# Check changed task\n", encoding="utf-8")
    before = (index.read_bytes(), markdown.read_bytes())
    pending = subprocess.run(
        [sys.executable, "-m", "manage_task_state_index", "index", "--root", str(tmp_path), "scan", "--check"],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )
    assert pending.returncode == 1
    assert json.loads(pending.stdout)["planned_artifact_updates"] == 1
    assert (index.read_bytes(), markdown.read_bytes()) == before


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
    environment = {
        **os.environ,
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONPATH": os.pathsep.join((str(TASK_STATE_SCRIPTS), str(AGENT_LOG_SCRIPTS))),
    }

    def invoke(index: int) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                "-m",
                "manage_task_state_index",
                "index",
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


def test_scan_prefers_canonical_advice_id_over_superseded_same_path_alias(tmp_path: Path) -> None:
    canonical_id = "adv-20260630-001746-canonical"
    alias_id = "adv-20260630-001908-external-advice"
    advice = tmp_path / ".agent_advice" / "active" / "20260630-001746-canonical.md"
    advice.parent.mkdir(parents=True)
    advice.write_text(
        f"# Canonical advice\n\n- advice_id: {canonical_id}\n- status: active\n",
        encoding="utf-8",
    )
    path_value = advice.relative_to(tmp_path).as_posix()
    index = tmp_path / ".task" / "index.jsonl"
    index.parent.mkdir(parents=True)
    events = [
        task_state_index.versioned_event({
            "event": "upsert", "id": alias_id, "type": "external_advice",
            "status": "superseded", "path": path_value, "title": "Alias",
            "updated_at": "2026-07-01T00:00:00+09:00",
            "fields": {"advice_id": canonical_id},
        }),
        task_state_index.versioned_event({
            "event": "upsert", "id": canonical_id, "type": "external_advice",
            "status": "active", "path": path_value, "title": "Canonical advice",
            "updated_at": "2026-07-01T00:00:01+09:00",
            "fields": {"advice_id": canonical_id},
        }),
    ]
    index.write_text(
        "".join(json.dumps(event, sort_keys=True) + "\n" for event in events),
        encoding="utf-8",
    )

    first = task_state_index.scan_artifacts(tmp_path)
    state = task_state_index.merge_state(task_state_index.load_events(tmp_path))
    assert first["indexed_events"] == 1
    assert state[canonical_id]["status"] == "active"
    assert state[canonical_id]["path"] == path_value
    assert state[alias_id]["status"] == "superseded"

    after_first = index.read_bytes()
    second = task_state_index.scan_artifacts(tmp_path)
    assert second["indexed_events"] == 0
    assert index.read_bytes() == after_first


def test_scan_reactivates_exact_canonical_advice_and_supersedes_active_same_path_alias(tmp_path: Path) -> None:
    canonical_id = "adv-canonical-active"
    alias_id = "adv-active-same-path-alias"
    advice = tmp_path / ".agent_advice" / "active" / "canonical-active.md"
    advice.parent.mkdir(parents=True)
    advice.write_text(
        f"# Canonical active advice\n\n- advice_id: {canonical_id}\n- status: active\n",
        encoding="utf-8",
    )
    path_value = advice.relative_to(tmp_path).as_posix()
    index = tmp_path / ".task" / "index.jsonl"
    index.parent.mkdir(parents=True)
    events = [
        task_state_index.versioned_event({
            "event": "upsert", "id": alias_id, "type": "external_advice",
            "status": "active", "path": path_value, "title": "Active alias",
            "updated_at": "2026-07-01T00:00:02+09:00",
            "fields": {"advice_id": canonical_id},
        }),
        task_state_index.versioned_event({
            "event": "upsert", "id": canonical_id, "type": "external_advice",
            "status": "superseded", "path": path_value, "title": "Canonical active advice",
            "updated_at": "2026-07-01T00:00:01+09:00",
            "fields": {"advice_id": canonical_id},
        }),
    ]
    index.write_text(
        "".join(json.dumps(event, sort_keys=True) + "\n" for event in events),
        encoding="utf-8",
    )

    result = task_state_index.scan_artifacts(tmp_path)
    state = task_state_index.merge_state(task_state_index.load_events(tmp_path))
    assert result["indexed_events"] == 1
    assert state[canonical_id]["status"] == "active"
    assert state[canonical_id]["path"] == path_value
    assert state[alias_id]["status"] == "superseded"
    assert task_state_index.scan_artifacts(tmp_path)["indexed_events"] == 0


def test_scan_rejects_active_cross_path_advice_alias_without_append(tmp_path: Path) -> None:
    canonical_id = "adv-cross-path-alias-canonical"
    advice = tmp_path / ".agent_advice" / "active" / "current-alias-target.md"
    advice.parent.mkdir(parents=True)
    advice.write_text(
        f"# Current advice\n\n- advice_id: {canonical_id}\n- status: active\n",
        encoding="utf-8",
    )
    index = tmp_path / ".task" / "index.jsonl"
    index.parent.mkdir(parents=True)
    alias = task_state_index.versioned_event({
        "event": "upsert", "id": "adv-cross-path-active-alias",
        "type": "external_advice", "status": "active",
        "path": ".agent_advice/active/other-alias.md", "title": "Other alias",
        "updated_at": "2026-07-01T00:00:00+09:00",
        "fields": {"advice_id": canonical_id},
    })
    index.write_text(json.dumps(alias, sort_keys=True) + "\n", encoding="utf-8")
    before = index.read_bytes()

    with pytest.raises(ValueError, match="active cross-path alias"):
        task_state_index.scan_artifacts(tmp_path)
    assert index.read_bytes() == before


def test_scan_rejects_exact_advice_id_owned_by_wrong_type_without_append(tmp_path: Path) -> None:
    canonical_id = "adv-wrong-type-owner"
    advice = tmp_path / ".agent_advice" / "active" / "wrong-type-owner.md"
    advice.parent.mkdir(parents=True)
    advice.write_text(
        f"# Advice with collided ID\n\n- advice_id: {canonical_id}\n- status: active\n",
        encoding="utf-8",
    )
    index = tmp_path / ".task" / "index.jsonl"
    index.parent.mkdir(parents=True)
    wrong_type = task_state_index.versioned_event({
        "event": "upsert", "id": canonical_id, "type": "validation",
        "status": "partial", "path": ".task/validation/collision.md",
        "title": "Wrong type owner", "updated_at": "2026-07-01T00:00:00+09:00",
    })
    index.write_text(json.dumps(wrong_type, sort_keys=True) + "\n", encoding="utf-8")
    before = index.read_bytes()

    with pytest.raises(ValueError, match="already bound to another artifact path"):
        task_state_index.scan_artifacts(tmp_path)
    assert index.read_bytes() == before


def test_scan_rejects_canonical_advice_id_cross_path_collision_without_append(tmp_path: Path) -> None:
    canonical_id = "adv-cross-path-canonical"
    advice = tmp_path / ".agent_advice" / "active" / "current.md"
    advice.parent.mkdir(parents=True)
    advice.write_text(
        f"# Current advice\n\n- advice_id: {canonical_id}\n- status: active\n",
        encoding="utf-8",
    )
    index = tmp_path / ".task" / "index.jsonl"
    index.parent.mkdir(parents=True)
    other = tmp_path / ".agent_advice" / "active" / "other.md"
    other.write_text(
        f"# Other advice\n\n- advice_id: {canonical_id}\n- status: active\n",
        encoding="utf-8",
    )
    event = task_state_index.versioned_event({
        "event": "upsert", "id": canonical_id, "type": "external_advice",
        "status": "active", "path": ".agent_advice/active/other.md",
        "title": "Other path", "updated_at": "2026-07-01T00:00:00+09:00",
        "fields": {"advice_id": canonical_id},
    })
    index.write_text(json.dumps(event, sort_keys=True) + "\n", encoding="utf-8")
    before = index.read_bytes()

    with pytest.raises(ValueError, match="already bound to another artifact path"):
        task_state_index.scan_artifacts(tmp_path)
    assert index.read_bytes() == before


def test_scan_preflight_rejects_two_new_advice_paths_with_same_id_before_first_append(
    tmp_path: Path,
) -> None:
    active = tmp_path / ".agent_advice" / "active"
    active.mkdir(parents=True)
    canonical_id = "adv-colliding-new-paths"
    for name in ("first.md", "second.md"):
        (active / name).write_text(
            f"# {name}\n\n- advice_id: {canonical_id}\n- status: active\n",
            encoding="utf-8",
        )

    with pytest.raises(ValueError, match="another artifact path"):
        task_state_index.scan_artifacts(tmp_path, dry_run=True)
    assert not (tmp_path / ".task").exists()

    with pytest.raises(ValueError, match="another artifact path"):
        task_state_index.scan_artifacts(tmp_path)
    assert not (tmp_path / ".task").exists()


def test_advice_metadata_normalizes_one_backtick_scalar_and_skips_pointer(tmp_path: Path) -> None:
    canonical_id = "adv-backtick-normalized"
    pointer = tmp_path / ".agent_advice" / "active" / "pointer.md"
    pointer.parent.mkdir(parents=True)
    pointer.write_text(
        "# Compatibility pointer\n\n"
        f"- advice_id: `{canonical_id}`\n"
        "- status: `deferred`\n"
        "- not_active_record: `true`\n",
        encoding="utf-8",
    )
    fields = task_state_index.extract_advice_fields(pointer)
    assert fields == {
        "advice_id": canonical_id,
        "status": "deferred",
        "not_active_record": "true",
    }
    assert not any(
        item_type == "external_advice" and path_value == ".agent_advice/active/pointer.md"
        for item_type, path_value, _status, _title in task_state_index.discover_standard_artifacts(tmp_path)
    )


def test_scan_relocates_canonical_advice_from_pointer_and_retires_backtick_alias(tmp_path: Path) -> None:
    canonical_id = "adv-pointer-relocation"
    pointer = tmp_path / ".agent_advice" / "active" / "relocation.md"
    canonical = tmp_path / ".agent_advice" / "deferred" / "relocation.md"
    pointer.parent.mkdir(parents=True)
    canonical.parent.mkdir(parents=True)
    pointer.write_text(
        "# Compatibility pointer\n\n"
        f"- advice_id: `{canonical_id}`\n"
        "- status: deferred\n"
        "- not_active_record: true\n",
        encoding="utf-8",
    )
    canonical.write_text(
        "# Canonical deferred advice\n\n"
        f"- advice_id: `{canonical_id}`\n"
        "- status: deferred\n",
        encoding="utf-8",
    )
    pointer_path = pointer.relative_to(tmp_path).as_posix()
    canonical_path = canonical.relative_to(tmp_path).as_posix()
    fake_id = f"`{canonical_id}`"
    index = tmp_path / ".task" / "index.jsonl"
    index.parent.mkdir(parents=True)
    events = [
        task_state_index.versioned_event({
            "event": "upsert", "id": canonical_id, "type": "external_advice",
            "status": "superseded", "path": pointer_path, "title": "Prior canonical",
            "updated_at": "2026-07-10T07:01:30+09:00",
            "fields": {"advice_id": canonical_id},
        }),
        task_state_index.versioned_event({
            "event": "upsert", "id": fake_id, "type": "external_advice",
            "status": "deferred", "path": pointer_path, "title": "Fake pointer alias",
            "updated_at": "2026-07-12T19:00:00+09:00",
            "fields": {"advice_id": fake_id},
        }),
    ]
    index.write_text(
        "".join(json.dumps(event, sort_keys=True) + "\n" for event in events),
        encoding="utf-8",
    )

    first = task_state_index.scan_artifacts(tmp_path)
    state = task_state_index.merge_state(task_state_index.load_events(tmp_path))
    assert first["indexed_events"] == 1
    assert state[canonical_id]["status"] == "deferred"
    assert state[canonical_id]["path"] == canonical_path
    assert state[fake_id]["status"] == "superseded"
    assert "body" not in state[canonical_id].get("fields", {})

    after_first = index.read_bytes()
    assert task_state_index.scan_artifacts(tmp_path)["indexed_events"] == 0
    assert index.read_bytes() == after_first


def test_empty_registry_is_not_reported_as_evaluated_success(tmp_path: Path) -> None:
    audit = task_state_index.audit_index(tmp_path)

    assert audit["audit_evidence_status"] == "not_evaluated_no_artifacts"
    assert "success" not in audit and "complete" not in audit


def test_mixed_legacy_malformed_and_current_rows_preserve_projection_uncertainty(tmp_path: Path) -> None:
    index = tmp_path / ".task" / "index.jsonl"
    index.parent.mkdir(parents=True)
    rows = [
        {
            "id": "item_I",
            "type": "task",
            "status": "active",
            "path": "task.md",
            "title": "item_I",
            "updated_at": "2026-01-01T00:00:00+00:00",
        },
        {
            "id": "item_I",
            "updated_at": "2026-01-01T00:00:01+00:00",
            "links": [],
        },
        {
            "format_version": task_state_index.INDEX_FORMAT_VERSION,
            "schema_version": task_state_index.INDEX_SCHEMA_VERSION,
            "event": "upsert",
            "id": "item_I",
            "type": "task",
            "status": "active",
            "path": "task.md",
            "title": "item_I current",
            "updated_at": "2026-01-01T00:00:02+00:00",
        },
        {
            "format_version": task_state_index.INDEX_FORMAT_VERSION,
            "schema_version": task_state_index.INDEX_SCHEMA_VERSION,
            "id": "item_I",
            "type": "task",
            "status": "active",
            "path": "task.md",
            "updated_at": "2026-01-01T00:00:03+00:00",
        },
    ]
    index.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    before = index.read_bytes()

    audit = task_state_index.audit_index(tmp_path)

    assert audit["legacy_normalized_count"] == 2
    assert audit["malformed_row_count"] == 1
    assert audit["projection_completeness"] == "incomplete"
    assert audit["current_projection_status"] == "not_evaluated"
    assert "item_I" in audit["projection_not_evaluated_ids"]
    with pytest.raises(ValueError, match="unsupported event"):
        task_state_index.load_events(tmp_path)
    with pytest.raises(ValueError, match="unsupported event"):
        task_state_index.append_event(
            tmp_path,
            {
                "event": "link",
                "id": "item_I",
                "updated_at": "2026-01-01T00:00:04+00:00",
                "links": [],
            },
        )
    assert index.read_bytes() == before


def test_scan_preflight_rejects_duplicate_discovered_task_pack_id_before_append(tmp_path: Path) -> None:
    pack_dir = tmp_path / ".task" / "task_pack"
    pack_dir.mkdir(parents=True)
    body = {"pack_id": "pack-duplicate-id", "status": "superseded", "items": []}
    for name in ("first.json", "second.json"):
        (pack_dir / name).write_text(json.dumps(body) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="already bound to another artifact path"):
        task_state_index.scan_artifacts(tmp_path, dry_run=True)
    assert not (tmp_path / ".task" / "index.jsonl").exists()

    with pytest.raises(ValueError, match="already bound to another artifact path"):
        task_state_index.scan_artifacts(tmp_path)
    assert not (tmp_path / ".task" / "index.jsonl").exists()


def test_task_pack_index_retains_bounded_initial_normalization_links(tmp_path: Path) -> None:
    pack = tmp_path / ".task" / "task_pack" / "pack-P.json"
    pack.parent.mkdir(parents=True)
    pack.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "pack_id": "pack-P",
                "status": "active",
                "goal": "bounded",
                "current_item_id": "item-B",
                "mutation_log": [],
                "items": [
                    {
                        "item_id": "item-A",
                        "order": 1,
                        "status": "consumed",
                        "promotion": {
                            "promotion_origin": "bootstrap_initial_selection",
                            "initial_selection_receipt_ref": "inline:sha256:abc",
                            "initial_selection_receipt": {
                                "pack_creation_snapshot_ref": "snapshot-C",
                                "authority_receipt_ref": ".task/authority_receipts/authr-R.json",
                                "authority_receipt_sha256": "a" * 64,
                                "authority_mode": "current_ratification",
                                "historical_selection_authority_status": "unverifiable_before_ratification",
                            },
                            "provenance_normalization": {
                                "mode": "legacy_initial_selection",
                                "historical_authority_verdict": "partial",
                            },
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    fields = task_state_index.extract_task_pack_fields(pack)
    assert fields["initial_promotion_origin"] == "bootstrap_initial_selection"
    assert fields["initial_authority_mode"] == "current_ratification"
    assert fields["initial_historical_authority_verdict"] == "partial"
    assert "receipt_body" not in fields
