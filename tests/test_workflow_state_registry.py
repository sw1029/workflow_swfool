from __future__ import annotations

import json
import hashlib
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
from manage_task_state_index.state import transition_intent as transition_intent_module  # noqa: E402
from manage_task_state_index.state import transition_plan as transition_plan_module  # noqa: E402
from manage_task_state_index.state import transition_plan_contract as transition_contract_module  # noqa: E402
from manage_task_state_index.state import transition_publication as transition_publication_module  # noqa: E402


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


def _transition_request(tmp_path: Path, old_id: str) -> dict[str, object]:
    task = tmp_path / "task.md"
    advice = tmp_path / ".agent_advice" / "active" / "advice.md"
    pack = tmp_path / ".task" / "task_pack" / "pack-A.json"
    archive = tmp_path / ".agent_log" / "past-task.md"
    advice.parent.mkdir(parents=True, exist_ok=True)
    pack.parent.mkdir(parents=True, exist_ok=True)
    archive.parent.mkdir(parents=True, exist_ok=True)
    advice.write_text("# Advice\n", encoding="utf-8")
    pack.write_text('{"pack_id":"pack-A","status":"active"}\n', encoding="utf-8")
    archive.write_text("# Archived task\n", encoding="utf-8")
    task.write_text("# Successor task\n", encoding="utf-8")
    return {
        "schema_version": 1,
        "updated_at": "2026-07-18T12:00:00+09:00",
        "render": True,
        "events": [
            {
                "event": "upsert",
                "id": old_id,
                "status": "superseded",
            },
            {
                "event": "link",
                "id": old_id,
                "links": [{"rel": "superseded_by", "id": "task-successor"}],
            },
            {
                "event": "upsert",
                "id": "past-archive",
                "type": "past_task",
                "status": "archived",
                "path": ".agent_log/past-task.md",
                "title": "Archived task",
                "content_sha256": task_state_index.sha256_file(archive),
                "links": [{"rel": "related_to", "id": old_id}],
            },
            {
                "event": "upsert",
                "id": "adv-direction",
                "type": "external_advice",
                "status": "active",
                "path": ".agent_advice/active/advice.md",
                "title": "Advice",
                "content_sha256": task_state_index.sha256_file(advice),
            },
            {
                "event": "upsert",
                "id": "pack-A",
                "type": "task_pack",
                "status": "active",
                "path": ".task/task_pack/pack-A.json",
                "title": "pack-A",
                "content_sha256": task_state_index.sha256_file(pack),
            },
            {
                "event": "upsert",
                "id": "task-successor",
                "type": "task",
                "status": "active",
                "path": "task.md",
                "title": "Successor task",
                "content_sha256": task_state_index.sha256_file(task),
                "links": [
                    {"rel": "supersedes", "id": old_id},
                    {"rel": "archived_as", "id": "past-archive"},
                    {"rel": "advice_for", "id": "adv-direction"},
                    {"rel": "promoted_from_pack", "id": "pack-A"},
                ],
            },
            {
                "event": "link",
                "id": "adv-direction",
                "links": [{"rel": "advice_for", "id": "task-successor"}],
            },
            {
                "event": "link",
                "id": "pack-A",
                "links": [{"rel": "pack_for_task", "id": "task-successor"}],
            },
        ],
    }


def test_transition_plan_applies_task_archive_supersede_advice_and_pack_links_once(
    tmp_path: Path,
) -> None:
    task = tmp_path / "task.md"
    task.write_text("# Original task\n", encoding="utf-8")
    original = task_state_index.upsert_item(
        tmp_path,
        "task",
        "task.md",
        "active",
        item_id="task-original",
        replace_existing=False,
    )
    request = _transition_request(tmp_path, original["id"])

    dry_run = task_state_index.build_transition_plan(tmp_path, request)
    assert dry_run["plan_kind"] == "task_state_transition_plan"
    assert not (tmp_path / ".task" / "transition_plans").exists()

    planned = task_state_index.publish_transition_plan(tmp_path, dry_run)
    verified = task_state_index.verify_transition_plan(tmp_path, planned["plan_ref"])
    before_rows = task_state_index.load_events(tmp_path)
    applied = task_state_index.apply_transition_plan(tmp_path, planned["plan_ref"])
    after_rows = task_state_index.load_events(tmp_path)
    replay = task_state_index.apply_transition_plan(tmp_path, planned["plan_ref"])
    state = task_state_index.merge_state(after_rows)

    assert planned["result_kind"] == "task_state_transition_plan_result"
    assert verified["status"] == "ready"
    assert applied["status"] == "applied"
    assert applied["events_appended"] == len(request["events"])
    assert replay["status"] == "already_applied"
    assert replay["events_appended"] == 0
    assert task_state_index.load_events(tmp_path) == after_rows
    assert len(after_rows) == len(before_rows) + len(request["events"])
    assert state["task-original"]["status"] == "superseded"
    assert state["task-successor"]["status"] == "active"
    assert state["past-archive"]["status"] == "archived"
    assert {link["rel"] for link in state["task-successor"]["links"]} >= {
        "supersedes",
        "archived_as",
        "advice_for",
        "promoted_from_pack",
    }
    assert (tmp_path / applied["receipt_ref"]).is_file()
    assert task_state_index.sha256_file(tmp_path / planned["plan_ref"]) == planned[
        "plan_file_sha256"
    ]
    assert task_state_index.sha256_file(tmp_path / applied["receipt_ref"]) == applied[
        "receipt_file_sha256"
    ]
    assert applied["execution_result_binding"] == {
        "ref": applied["receipt_ref"],
        "sha256": applied["receipt_file_sha256"],
    }


def test_transition_plan_stale_ledger_cas_fails_without_partial_batch(
    tmp_path: Path,
) -> None:
    task = tmp_path / "task.md"
    task.write_text("# Original task\n", encoding="utf-8")
    original = task_state_index.upsert_item(
        tmp_path,
        "task",
        "task.md",
        "active",
        item_id="task-original",
        replace_existing=False,
    )
    request = _transition_request(tmp_path, original["id"])
    plan = task_state_index.build_transition_plan(tmp_path, request)
    planned = task_state_index.publish_transition_plan(tmp_path, plan)
    task_state_index.append_event(
        tmp_path,
        {
            "event": "link",
            "id": original["id"],
            "updated_at": "2026-07-18T12:00:01+09:00",
            "links": [{"rel": "related_to", "id": original["id"]}],
        },
    )
    before = task_state_index.load_events(tmp_path)

    with pytest.raises(ValueError, match="CAS mismatch"):
        task_state_index.apply_transition_plan(tmp_path, planned["plan_ref"])

    assert task_state_index.load_events(tmp_path) == before
    assert not any(row.get("transition_plan_id") == plan["plan_id"] for row in before)
    assert task_state_index.verify_transition_plan(
        tmp_path, planned["plan_ref"]
    )["status"] == "stale"


def test_transition_plan_accepts_owner_published_prospective_artifact(
    tmp_path: Path,
) -> None:
    artifact = tmp_path / ".task" / "task_pack" / "pack-new.json"
    payload = b'{"pack_id":"pack-new","status":"active"}\n'
    expected = hashlib.sha256(payload).hexdigest()
    request = {
        "updated_at": "2026-07-18T15:20:00+09:00",
        "events": [
            {
                "event": "upsert",
                "id": "pack-new",
                "type": "task_pack",
                "status": "active",
                "path": ".task/task_pack/pack-new.json",
                "title": "Prospective pack",
                "content_sha256": expected,
            }
        ],
    }
    plan = task_state_index.build_transition_plan(tmp_path, request)
    assert plan["artifact_anchors"] == [
        {
            "path": ".task/task_pack/pack-new.json",
            "before_sha256": None,
            "expected_sha256": expected,
            "expectation": "planned_content_sha256",
        }
    ]
    planned = task_state_index.publish_transition_plan(tmp_path, plan)
    planning_before = task_state_index.verify_transition_plan(
        tmp_path, planned["plan_ref"], phase="planning"
    )
    apply_before = task_state_index.verify_transition_plan(
        tmp_path, planned["plan_ref"], phase="apply"
    )
    assert planning_before["status"] == "ready"
    assert planning_before["prestate_current"] is True
    assert apply_before["status"] == "stale"
    assert apply_before["prestate_current"] is False
    assert apply_before["no_effect_eligible"] is False
    with pytest.raises(ValueError, match="not eligible for no-effect"):
        task_state_index.settle_transition_no_effect(
            tmp_path, planned["plan_ref"]
        )
    artifact.parent.mkdir(parents=True)
    artifact.write_bytes(payload)

    replayed_plan = task_state_index.publish_transition_plan(tmp_path, plan)
    assert replayed_plan["status"] == "already_planned"
    assert replayed_plan["mutation_performed"] is False

    planning_after = task_state_index.verify_transition_plan(
        tmp_path, planned["plan_ref"], phase="planning"
    )
    apply_after = task_state_index.verify_transition_plan(
        tmp_path, planned["plan_ref"], phase="apply"
    )
    assert planning_after["status"] == "stale"
    assert apply_after["status"] == "ready"

    applied = task_state_index.apply_transition_plan(tmp_path, planned["plan_ref"])

    assert applied["status"] == "applied"


def test_transition_plan_partial_dependency_materialization_is_not_no_effect(
    tmp_path: Path,
) -> None:
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    first_payload = b'{"id":"first"}\n'
    second_payload = b'{"id":"second"}\n'
    plan = task_state_index.build_transition_plan(
        tmp_path,
        {
            "updated_at": "2026-07-18T15:20:10+09:00",
            "events": [
                {
                    "event": "upsert",
                    "id": "issue-first",
                    "type": "issue",
                    "status": "active",
                    "path": "first.json",
                    "title": "First",
                    "content_sha256": hashlib.sha256(first_payload).hexdigest(),
                },
                {
                    "event": "upsert",
                    "id": "issue-second",
                    "type": "issue",
                    "status": "active",
                    "path": "second.json",
                    "title": "Second",
                    "content_sha256": hashlib.sha256(second_payload).hexdigest(),
                },
            ],
        },
    )
    planned = task_state_index.publish_transition_plan(tmp_path, plan)
    first.write_bytes(first_payload)

    planning = task_state_index.verify_transition_plan(
        tmp_path, planned["plan_ref"], phase="planning"
    )
    applying = task_state_index.verify_transition_plan(
        tmp_path, planned["plan_ref"], phase="apply"
    )

    assert planning["status"] == "materializing"
    assert applying["status"] == "materializing"
    assert applying["dependency_materialization_status"] == "partial"
    assert applying["no_effect_eligible"] is False
    with pytest.raises(ValueError, match="not eligible for no-effect"):
        task_state_index.settle_transition_no_effect(
            tmp_path, planned["plan_ref"]
        )

    second.write_bytes(second_payload)
    assert task_state_index.verify_transition_plan(
        tmp_path, planned["plan_ref"], phase="apply"
    )["status"] == "ready"


def test_transition_plan_stale_without_intent_settles_with_immutable_no_effect_receipt(
    tmp_path: Path,
) -> None:
    task = tmp_path / "task.md"
    task.write_text("# Original task\n", encoding="utf-8")
    original = task_state_index.upsert_item(
        tmp_path,
        "task",
        "task.md",
        "active",
        item_id="task-original",
        replace_existing=False,
    )
    plan = task_state_index.build_transition_plan(
        tmp_path, _transition_request(tmp_path, original["id"])
    )
    planned = task_state_index.publish_transition_plan(tmp_path, plan)
    task_state_index.append_event(
        tmp_path,
        {
            "event": "link",
            "id": original["id"],
            "updated_at": "2026-07-18T15:20:30+09:00",
            "links": [{"rel": "related_to", "id": original["id"]}],
        },
    )

    stale = task_state_index.verify_transition_plan(tmp_path, planned["plan_ref"])
    assert stale["status"] == "stale"
    assert stale["plan_effect_observed"] is False
    assert stale["plan_intent_observed"] is False
    assert stale["no_effect_eligible"] is True

    settled = task_state_index.settle_transition_no_effect(
        tmp_path, planned["plan_ref"], at="2026-07-18T15:20:31+09:00"
    )
    replay = task_state_index.settle_transition_no_effect(
        tmp_path, planned["plan_ref"], at="2026-07-18T15:20:32+09:00"
    )
    verified = task_state_index.verify_transition_plan(tmp_path, planned["plan_ref"])

    assert settled["status"] == "settled_no_effect"
    assert replay["status"] == "already_settled_no_effect"
    assert replay["receipt_file_sha256"] == settled["receipt_file_sha256"]
    assert settled["execution_result_binding"] == {
        "ref": settled["receipt_ref"],
        "sha256": settled["receipt_file_sha256"],
    }
    assert verified["status"] == "settled_no_effect"
    assert verified["no_effect_verified"] is True
    assert verified["no_effect_receipt_file_sha256"] == settled[
        "receipt_file_sha256"
    ]
    assert not any(
        row.get("transition_plan_id") == plan["plan_id"]
        for row in task_state_index.load_events(tmp_path)
    )
    with pytest.raises(ValueError, match="settled with no effect"):
        task_state_index.apply_transition_plan(tmp_path, planned["plan_ref"])

    receipt_path = tmp_path / settled["receipt_ref"]
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="bytes are not canonical"):
        task_state_index.verify_transition_plan(tmp_path, planned["plan_ref"])


def test_transition_plan_cannot_settle_no_effect_while_still_apply_ready(
    tmp_path: Path,
) -> None:
    task = tmp_path / "task.md"
    task.write_text("# Original task\n", encoding="utf-8")
    original = task_state_index.upsert_item(
        tmp_path,
        "task",
        "task.md",
        "active",
        item_id="task-original",
        replace_existing=False,
    )
    plan = task_state_index.build_transition_plan(
        tmp_path, _transition_request(tmp_path, original["id"])
    )
    planned = task_state_index.publish_transition_plan(tmp_path, plan)

    with pytest.raises(ValueError, match="not eligible for no-effect"):
        task_state_index.settle_transition_no_effect(
            tmp_path, planned["plan_ref"]
        )

    assert task_state_index.verify_transition_plan(
        tmp_path, planned["plan_ref"]
    )["status"] == "ready"


def test_transition_plan_apply_after_no_effect_is_zero_canonical_mutation(
    tmp_path: Path,
) -> None:
    artifact = tmp_path / "prospective.json"
    expected = b'{"state":"expected"}\n'
    foreign = b'{"state":"foreign"}\n'
    plan = task_state_index.build_transition_plan(
        tmp_path,
        {
            "updated_at": "2026-07-18T15:20:40+09:00",
            "events": [
                {
                    "event": "upsert",
                    "id": "issue-prospective",
                    "type": "issue",
                    "status": "active",
                    "path": "prospective.json",
                    "title": "Prospective",
                    "content_sha256": hashlib.sha256(expected).hexdigest(),
                }
            ],
        },
    )
    planned = task_state_index.publish_transition_plan(tmp_path, plan)
    artifact.write_bytes(foreign)
    settled = task_state_index.settle_transition_no_effect(
        tmp_path, planned["plan_ref"], at="2026-07-18T15:20:41+09:00"
    )
    ledger = tmp_path / ".task" / "index.jsonl"
    markdown = tmp_path / ".task" / "index.md"
    assert settled["status"] == "settled_no_effect"
    assert not ledger.exists()
    assert not markdown.exists()

    with pytest.raises(ValueError, match="settled with no effect"):
        task_state_index.apply_transition_plan(tmp_path, planned["plan_ref"])

    assert not ledger.exists()
    assert not markdown.exists()


def test_transition_plan_rejects_symlinked_owned_receipt_root(tmp_path: Path) -> None:
    task = tmp_path / "task.md"
    task.write_text("# Original task\n", encoding="utf-8")
    original = task_state_index.upsert_item(
        tmp_path,
        "task",
        "task.md",
        "active",
        item_id="task-original",
        replace_existing=False,
    )
    plan = task_state_index.build_transition_plan(
        tmp_path, _transition_request(tmp_path, original["id"])
    )
    planned = task_state_index.publish_transition_plan(tmp_path, plan)
    outside = tmp_path / "outside-receipts"
    outside.mkdir()
    (tmp_path / ".task" / "transition_receipts").symlink_to(
        outside, target_is_directory=True
    )

    with pytest.raises(ValueError, match="owned root"):
        task_state_index.apply_transition_plan(tmp_path, planned["plan_ref"])

    assert list(outside.iterdir()) == []


def test_transition_plan_rejects_symlinked_index_lock_leaf(tmp_path: Path) -> None:
    task = tmp_path / "task.md"
    task.write_text("# Original task\n", encoding="utf-8")
    original = task_state_index.upsert_item(
        tmp_path,
        "task",
        "task.md",
        "active",
        item_id="task-original",
        replace_existing=False,
    )
    plan = task_state_index.build_transition_plan(
        tmp_path, _transition_request(tmp_path, original["id"])
    )
    planned = task_state_index.publish_transition_plan(tmp_path, plan)
    lock = tmp_path / ".task" / "index.lock"
    lock.unlink()
    outside = tmp_path / "outside.lock"
    lock.symlink_to(outside)

    with pytest.raises(ValueError, match="regular owned file"):
        task_state_index.apply_transition_plan(tmp_path, planned["plan_ref"])

    assert not outside.exists()


def test_transition_plan_rejects_symlinked_artifact_ancestor(tmp_path: Path) -> None:
    outside = tmp_path / "outside-artifacts"
    outside.mkdir()
    payload = b"{}\n"
    (outside / "artifact.json").write_bytes(payload)
    (tmp_path / "artifact-alias").symlink_to(outside, target_is_directory=True)

    with pytest.raises(ValueError, match="must not be a symlink"):
        task_state_index.build_transition_plan(
            tmp_path,
            {
                "updated_at": "2026-07-18T15:21:30+09:00",
                "events": [
                    {
                        "event": "upsert",
                        "id": "issue-symlink",
                        "type": "issue",
                        "status": "active",
                        "path": "artifact-alias/artifact.json",
                        "title": "Symlink",
                        "content_sha256": hashlib.sha256(payload).hexdigest(),
                    }
                ],
            },
        )


def test_transition_plan_rejects_noncanonical_artifact_path_text(
    tmp_path: Path,
) -> None:
    aliases = (
        "./issue.md",
        "nested//issue.md",
        "nested\\issue.md",
        str(tmp_path / "issue.md"),
    )
    for offset, alias in enumerate(aliases):
        with pytest.raises(ValueError, match="canonical workspace-relative"):
            task_state_index.build_transition_plan(
                tmp_path,
                {
                    "updated_at": f"2026-07-18T15:21:{40 + offset:02d}+09:00",
                    "events": [
                        {
                            "event": "upsert",
                            "id": f"issue-path-{offset}",
                            "type": "issue",
                            "status": "active",
                            "path": alias,
                            "title": "Path",
                        }
                    ],
                },
            )


def test_transition_plan_publication_rejects_owned_directory_swap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = task_state_index.build_transition_plan(
        tmp_path,
        {
            "updated_at": "2026-07-18T15:21:50+09:00",
            "events": [
                {
                    "event": "upsert",
                    "id": "issue-race",
                    "type": "issue",
                    "status": "active",
                    "path": "issue.md",
                    "title": "Race",
                }
            ],
        },
    )
    original = transition_plan_module._publish_immutable
    outside = tmp_path / "outside-publication"
    outside.mkdir()

    def swap_then_publish(path: Path, payload: bytes) -> bool:
        owned = path.parent
        backup = owned.with_name("transition_plans-backup")
        owned.rename(backup)
        owned.symlink_to(outside, target_is_directory=True)
        return original(path, payload)

    monkeypatch.setattr(
        transition_plan_module, "_publish_immutable", swap_then_publish
    )
    with pytest.raises(ValueError, match="publication path is unsafe"):
        task_state_index.publish_transition_plan(tmp_path, plan)

    assert list(outside.iterdir()) == []


def test_transition_directory_creation_rolls_back_child_after_parent_swap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = task_state_index.build_transition_plan(
        tmp_path,
        {
            "updated_at": "2026-07-18T15:21:49+09:00",
            "events": [
                {
                    "event": "upsert",
                    "id": "issue-parent-create-race",
                    "type": "issue",
                    "status": "active",
                    "path": "issue.md",
                    "title": "Parent create race",
                }
            ],
        },
    )
    original_mkdir = transition_publication_module.os.mkdir
    moved_parent = tmp_path / "moved-task-parent"
    moved_parent.mkdir()
    injected = False

    def swap_parent_then_mkdir(
        path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> None:
        nonlocal injected
        if path == "transition_plans" and not injected:
            injected = True
            (tmp_path / ".task").rename(moved_parent / ".task")
            original_mkdir(tmp_path / ".task", 0o700)
        original_mkdir(path, mode, dir_fd=dir_fd)

    monkeypatch.setattr(
        transition_publication_module.os, "mkdir", swap_parent_then_mkdir
    )
    with pytest.raises(ValueError, match="root changed"):
        task_state_index.publish_transition_plan(tmp_path, plan)

    assert list((moved_parent / ".task").iterdir()) == []
    assert list((tmp_path / ".task").iterdir()) == []


def test_transition_directory_creation_detects_new_child_swap_before_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = task_state_index.build_transition_plan(
        tmp_path,
        {
            "updated_at": "2026-07-18T15:21:48+09:00",
            "events": [
                {
                    "event": "upsert",
                    "id": "issue-child-create-race",
                    "type": "issue",
                    "status": "active",
                    "path": "issue.md",
                    "title": "Child create race",
                }
            ],
        },
    )
    original_open = transition_publication_module.os.open
    moved_parent = tmp_path / "moved-child-parent"
    moved_parent.mkdir()
    injected = False

    def swap_child_then_open(
        path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        nonlocal injected
        if path == "transition_plans" and not injected:
            injected = True
            owned = tmp_path / ".task" / "transition_plans"
            owned.rename(moved_parent / "transition_plans")
            owned.mkdir()
        return original_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(
        transition_publication_module.os, "open", swap_child_then_open
    )
    with pytest.raises(ValueError, match="changed before it was opened"):
        task_state_index.publish_transition_plan(tmp_path, plan)

    assert list((moved_parent / "transition_plans").iterdir()) == []
    assert list((tmp_path / ".task" / "transition_plans").iterdir()) == []


def test_transition_plan_publication_cleans_final_after_mid_write_directory_swap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = task_state_index.build_transition_plan(
        tmp_path,
        {
            "updated_at": "2026-07-18T15:21:51+09:00",
            "events": [
                {
                    "event": "upsert",
                    "id": "issue-mid-write-race",
                    "type": "issue",
                    "status": "active",
                    "path": "issue.md",
                    "title": "Mid-write race",
                }
            ],
        },
    )
    original_write = transition_publication_module._write_all
    moved_parent = tmp_path / "moved-publication"
    moved_parent.mkdir()

    def write_then_swap(descriptor: int, payload: bytes) -> None:
        original_write(descriptor, payload)
        owned = tmp_path / ".task" / "transition_plans"
        owned.rename(moved_parent / "transition_plans")
        owned.mkdir()

    monkeypatch.setattr(
        transition_publication_module, "_write_all", write_then_swap
    )
    with pytest.raises(ValueError, match="publication root changed"):
        task_state_index.publish_transition_plan(tmp_path, plan)

    moved = moved_parent / "transition_plans"
    assert list(moved.iterdir()) == []
    assert list((tmp_path / ".task" / "transition_plans").iterdir()) == []


def test_transition_plan_revalidates_event_semantics_before_intent(tmp_path: Path) -> None:
    issue = tmp_path / "issue.md"
    issue.write_text("# Issue\n", encoding="utf-8")
    plan = task_state_index.build_transition_plan(
        tmp_path,
        {
            "updated_at": "2026-07-18T15:21:31+09:00",
            "events": [
                {
                    "event": "upsert",
                    "id": "issue-invalid-plan",
                    "type": "issue",
                    "status": "active",
                    "path": "issue.md",
                    "title": "Issue",
                    "content_sha256": task_state_index.sha256_file(issue),
                }
            ],
        },
    )
    plan["events"][0]["type"] = "unsupported_type"
    body = {key: value for key, value in plan.items() if key != "plan_sha256"}
    plan["plan_sha256"] = transition_contract_module.sha256_bytes(
        transition_contract_module.canonical_bytes(body)
    )
    plan_path = (
        tmp_path / ".task" / "transition_plans" / f"{plan['plan_id']}.json"
    )
    plan_path.parent.mkdir(parents=True)
    plan_path.write_bytes(
        transition_contract_module.canonical_bytes(plan) + b"\n"
    )

    with pytest.raises(ValueError, match="request/event derivation|unsupported type"):
        task_state_index.verify_transition_plan(
            tmp_path, plan_path.relative_to(tmp_path).as_posix()
        )
    with pytest.raises(ValueError, match="request/event derivation|unsupported type"):
        task_state_index.apply_transition_plan(
            tmp_path, plan_path.relative_to(tmp_path).as_posix()
        )
    assert not (tmp_path / ".task" / "transition_intents").exists()


def test_transition_plan_prepare_rejects_noncanonical_metadata_output(
    tmp_path: Path,
) -> None:
    request = {
        "updated_at": "2026-07-18T15:20:01+09:00",
        "events": [
            {
                "event": "upsert",
                "id": "issue-plan-output",
                "type": "issue",
                "status": "active",
                "path": "issue.md",
                "title": "Plan output",
            }
        ],
    }
    plan = task_state_index.build_transition_plan(tmp_path, request)

    with pytest.raises(ValueError, match="plan output must be an exact canonical"):
        task_state_index.publish_transition_plan(tmp_path, plan, "outside.json")

    with pytest.raises(ValueError, match="exact canonical plan-id path"):
        task_state_index.publish_transition_plan(
            tmp_path, plan, ".task/transition_plans/alias.json"
        )

    assert not (tmp_path / "outside.json").exists()


def test_transition_plan_requires_current_markdown_projection(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="require Markdown rendering"):
        task_state_index.build_transition_plan(
            tmp_path,
            {
                "render": False,
                "updated_at": "2026-07-18T15:20:02+09:00",
                "events": [
                    {
                        "event": "upsert",
                        "id": "issue-render",
                        "type": "issue",
                        "status": "active",
                        "path": "issue.md",
                        "title": "Render",
                    }
                ],
            },
        )


@pytest.mark.parametrize(
    ("request_update", "at", "message"),
    (
        ({"unregistered_metadata": "opaque"}, None, "unsupported fields"),
        ({"updated_at": "not-a-time"}, None, "RFC3339"),
        ({"schema_version": True}, None, "schema_version"),
        ({}, "not-a-time", "RFC3339"),
    ),
)
def test_transition_plan_request_contract_is_closed_before_dry_run(
    tmp_path: Path,
    request_update: dict[str, object],
    at: str | None,
    message: str,
) -> None:
    request: dict[str, object] = {
        "events": [
            {
                "event": "upsert",
                "id": "issue-request-contract",
                "type": "issue",
                "status": "active",
                "path": "issue.md",
                "title": "Issue",
            }
        ],
        **request_update,
    }
    with pytest.raises(ValueError, match=message):
        task_state_index.build_transition_plan(tmp_path, request, at=at)

    assert not (tmp_path / ".task").exists()


@pytest.mark.parametrize("tamper", ("extra", "request_digest", "plan_id", "ledger_extra"))
def test_transition_plan_closed_metadata_and_identity_binding(
    tmp_path: Path, tamper: str,
) -> None:
    plan = task_state_index.build_transition_plan(
        tmp_path,
        {
            "updated_at": "2026-07-18T15:20:03+09:00",
            "events": [
                {
                    "event": "upsert",
                    "id": "issue-plan-contract",
                    "type": "issue",
                    "status": "active",
                    "path": "issue.md",
                    "title": "Issue",
                }
            ],
        },
    )
    if tamper == "extra":
        plan["unregistered_metadata"] = {"raw_locator": "forbidden"}
    elif tamper == "request_digest":
        plan["request_sha256"] = "0" * 64
    elif tamper == "plan_id":
        plan["plan_id"] = "transition-" + "0" * 32
    else:
        plan["ledger"]["unregistered"] = True
    body = {key: value for key, value in plan.items() if key != "plan_sha256"}
    plan["plan_sha256"] = transition_contract_module.sha256_bytes(
        transition_contract_module.canonical_bytes(body)
    )

    with pytest.raises(ValueError):
        transition_contract_module.validate_transition_plan(plan)


def test_transition_plan_file_requires_exact_canonical_bytes(tmp_path: Path) -> None:
    plan = task_state_index.build_transition_plan(
        tmp_path,
        {
            "updated_at": "2026-07-18T15:20:04+09:00",
            "events": [
                {
                    "event": "upsert",
                    "id": "issue-plan-bytes",
                    "type": "issue",
                    "status": "active",
                    "path": "issue.md",
                    "title": "Plan bytes",
                }
            ],
        },
    )
    planned = task_state_index.publish_transition_plan(tmp_path, plan)
    plan_path = tmp_path / planned["plan_ref"]
    plan_path.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="bytes are not canonical"):
        task_state_index.verify_transition_plan(tmp_path, planned["plan_ref"])


def test_transition_plan_accepts_planned_mutable_task_replacement(
    tmp_path: Path,
) -> None:
    task = tmp_path / "task.md"
    task.write_text("# Old task\n", encoding="utf-8")
    original = task_state_index.upsert_item(
        tmp_path,
        "task",
        "task.md",
        "active",
        item_id="task-old",
        replace_existing=False,
    )
    replacement = b"# New task\n"
    expected = hashlib.sha256(replacement).hexdigest()
    request = {
        "updated_at": "2026-07-18T15:21:00+09:00",
        "events": [
            {
                "event": "upsert",
                "id": original["id"],
                "status": "superseded",
                "links": [{"rel": "superseded_by", "id": "task-new"}],
            },
            {
                "event": "upsert",
                "id": "task-new",
                "type": "task",
                "status": "active",
                "path": "task.md",
                "title": "New task",
                "content_sha256": expected,
                "links": [{"rel": "supersedes", "id": original["id"]}],
            },
        ],
    }
    plan = task_state_index.build_transition_plan(tmp_path, request)
    planned = task_state_index.publish_transition_plan(tmp_path, plan)
    task.write_bytes(replacement)

    applied = task_state_index.apply_transition_plan(tmp_path, planned["plan_ref"])

    assert applied["status"] == "applied"
    assert task_state_index.merge_state(task_state_index.load_events(tmp_path))[
        "task-new"
    ]["content_sha256"] == expected


@pytest.mark.parametrize("tamper", ("missing", "duplicate", "expected"))
def test_transition_plan_rejects_rehashed_artifact_anchor_tamper(
    tmp_path: Path,
    tamper: str,
) -> None:
    artifact = tmp_path / "artifact.json"
    artifact.write_text("{}\n", encoding="utf-8")
    request = {
        "updated_at": "2026-07-18T15:22:00+09:00",
        "events": [
            {
                "event": "upsert",
                "id": "artifact-one",
                "type": "issue",
                "status": "active",
                "path": "artifact.json",
                "title": "Artifact",
                "content_sha256": task_state_index.sha256_file(artifact),
            }
        ],
    }
    plan = task_state_index.build_transition_plan(tmp_path, request)
    if tamper == "missing":
        plan["artifact_anchors"] = []
    elif tamper == "duplicate":
        plan["artifact_anchors"].append(dict(plan["artifact_anchors"][0]))
    else:
        plan["artifact_anchors"][0]["expected_sha256"] = "0" * 64
    body = {key: value for key, value in plan.items() if key != "plan_sha256"}
    plan["plan_sha256"] = transition_plan_module._sha256_bytes(
        transition_plan_module._canonical_bytes(body)
    )

    with pytest.raises(ValueError, match="artifact anchor"):
        task_state_index.publish_transition_plan(tmp_path, plan)


def test_transition_plan_recovers_post_append_render_and_rejects_receipt_tamper(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task = tmp_path / "task.md"
    task.write_text("# Original task\n", encoding="utf-8")
    original = task_state_index.upsert_item(
        tmp_path,
        "task",
        "task.md",
        "active",
        item_id="task-original",
        replace_existing=False,
    )
    request = _transition_request(tmp_path, original["id"])
    plan = task_state_index.build_transition_plan(tmp_path, request)
    planned = task_state_index.publish_transition_plan(tmp_path, plan)
    original_render = transition_plan_module._rebuild_markdown_unlocked

    def crash_after_append(*_args: object, **_kwargs: object) -> dict[str, object]:
        raise RuntimeError("injected post-append render failure")

    monkeypatch.setattr(
        transition_plan_module, "_rebuild_markdown_unlocked", crash_after_append
    )
    with pytest.raises(RuntimeError, match="post-append"):
        task_state_index.apply_transition_plan(tmp_path, planned["plan_ref"])

    assert len(
        [
            row
            for row in task_state_index.load_events(tmp_path)
            if row.get("transition_plan_id") == plan["plan_id"]
        ]
    ) == len(plan["events"])
    assert task_state_index.verify_transition_plan(
        tmp_path, planned["plan_ref"]
    )["status"] == "recovery_required"
    with pytest.raises(ValueError, match="Pending task-state transition intent"):
        task_state_index.append_event(
            tmp_path,
            {
                "event": "link",
                "id": original["id"],
                "updated_at": "2026-07-18T12:00:02+09:00",
                "links": [{"rel": "related_to", "id": original["id"]}],
            },
        )
    competing = task_state_index.build_transition_plan(
        tmp_path,
        {
            "updated_at": "2026-07-18T12:00:03+09:00",
            "events": [
                {
                    "event": "link",
                    "id": original["id"],
                    "links": [{"rel": "related_to", "id": original["id"]}],
                }
            ],
        },
    )
    competing_plan = task_state_index.publish_transition_plan(tmp_path, competing)
    with pytest.raises(ValueError, match="Pending task-state transition intent"):
        task_state_index.apply_transition_plan(tmp_path, competing_plan["plan_ref"])

    monkeypatch.setattr(
        transition_plan_module, "_rebuild_markdown_unlocked", original_render
    )
    recovered = task_state_index.apply_transition_plan(tmp_path, planned["plan_ref"])
    assert recovered["status"] == "already_applied"
    assert recovered["publication_recovered"] is True
    assert recovered["events_appended"] == 0

    receipt = tmp_path / recovered["receipt_ref"]
    receipt.write_text("{}\n", encoding="utf-8")
    assert task_state_index.verify_transition_plan(
        tmp_path, planned["plan_ref"]
    )["status"] == "conflict"
    with pytest.raises(ValueError, match="receipt conflict"):
        task_state_index.apply_transition_plan(tmp_path, planned["plan_ref"])


def test_transition_receipt_without_committed_batch_does_not_release_intent_barrier(
    tmp_path: Path,
) -> None:
    task = tmp_path / "task.md"
    task.write_text("# Original task\n", encoding="utf-8")
    original = task_state_index.upsert_item(
        tmp_path,
        "task",
        "task.md",
        "active",
        item_id="task-original",
        replace_existing=False,
    )
    plan = task_state_index.build_transition_plan(
        tmp_path, _transition_request(tmp_path, original["id"])
    )
    planned = task_state_index.publish_transition_plan(tmp_path, plan)
    transition_intent_module.publish_transition_intent(
        tmp_path, plan, planned["plan_ref"], planned["plan_file_sha256"]
    )
    receipt = transition_contract_module.receipt_for_plan(
        plan, planned["plan_ref"], planned["plan_file_sha256"]
    )
    receipt_path = transition_contract_module.owned_transition_file(
        tmp_path,
        "transition_receipts",
        f"{plan['plan_id']}.json",
        create_parent=True,
    )
    transition_contract_module.publish_immutable(
        receipt_path, transition_contract_module.canonical_bytes(receipt) + b"\n"
    )

    verification = task_state_index.verify_transition_plan(
        tmp_path, planned["plan_ref"]
    )
    assert verification["status"] == "conflict"
    assert "apply_receipt_without_committed_batch" in verification["cas_defects"]
    with pytest.raises(ValueError, match="lacks its committed event batch"):
        task_state_index.append_event(
            tmp_path,
            {
                "event": "link",
                "id": original["id"],
                "updated_at": "2026-07-18T15:28:00+09:00",
                "links": [{"rel": "related_to", "id": original["id"]}],
            },
        )
    with pytest.raises(ValueError, match="lacks its committed event batch"):
        task_state_index.apply_transition_plan(tmp_path, planned["plan_ref"])


def test_transition_intent_file_requires_exact_canonical_bytes(tmp_path: Path) -> None:
    plan = task_state_index.build_transition_plan(
        tmp_path,
        {
            "updated_at": "2026-07-18T15:28:01+09:00",
            "events": [
                {
                    "event": "upsert",
                    "id": "issue-intent-bytes",
                    "type": "issue",
                    "status": "active",
                    "path": "issue.md",
                    "title": "Intent bytes",
                }
            ],
        },
    )
    planned = task_state_index.publish_transition_plan(tmp_path, plan)
    transition_intent_module.publish_transition_intent(
        tmp_path, plan, planned["plan_ref"], planned["plan_file_sha256"]
    )
    intent_path = (
        tmp_path / ".task" / "transition_intents" / f"{plan['plan_id']}.json"
    )
    intent = json.loads(intent_path.read_text(encoding="utf-8"))
    intent_path.write_text(json.dumps(intent, indent=2) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="bytes are not canonical"):
        transition_intent_module.assert_no_pending_transition_intents(tmp_path)


def test_transition_plan_recovers_unique_batch_with_unrelated_suffix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task = tmp_path / "task.md"
    task.write_text("# Original task\n", encoding="utf-8")
    original = task_state_index.upsert_item(
        tmp_path,
        "task",
        "task.md",
        "active",
        item_id="task-original",
        replace_existing=False,
    )
    plan = task_state_index.build_transition_plan(
        tmp_path, _transition_request(tmp_path, original["id"])
    )
    planned = task_state_index.publish_transition_plan(tmp_path, plan)
    original_render = transition_plan_module._rebuild_markdown_unlocked

    def crash_after_append(*_args: object, **_kwargs: object) -> dict[str, object]:
        raise RuntimeError("injected suffix recovery failure")

    monkeypatch.setattr(
        transition_plan_module, "_rebuild_markdown_unlocked", crash_after_append
    )
    with pytest.raises(RuntimeError, match="suffix recovery failure"):
        task_state_index.apply_transition_plan(tmp_path, planned["plan_ref"])
    index = tmp_path / ".task" / "index.jsonl"
    suffix = task_state_index.versioned_event(
        {
            "event": "link",
            "id": "task-successor",
            "updated_at": "2026-07-18T12:10:00+09:00",
            "links": [{"rel": "related_to", "id": "task-successor"}],
        }
    )
    with index.open("ab") as handle:
        handle.write((json.dumps(suffix, sort_keys=True) + "\n").encode("utf-8"))
    suffix_bytes = index.read_bytes()
    assert task_state_index.verify_transition_plan(
        tmp_path, planned["plan_ref"]
    )["status"] == "recovery_required"

    monkeypatch.setattr(
        transition_plan_module, "_rebuild_markdown_unlocked", original_render
    )
    recovered = task_state_index.apply_transition_plan(tmp_path, planned["plan_ref"])

    assert recovered["status"] == "already_applied"
    assert recovered["publication_recovered"] is True
    assert index.read_bytes() == suffix_bytes
    assert task_state_index.load_events(tmp_path)[-1] == suffix


def test_transition_plan_replay_repairs_stale_current_suffix_projection(
    tmp_path: Path,
) -> None:
    task = tmp_path / "task.md"
    task.write_text("# Original task\n", encoding="utf-8")
    original = task_state_index.upsert_item(
        tmp_path,
        "task",
        "task.md",
        "active",
        item_id="task-original",
        replace_existing=False,
    )
    plan = task_state_index.build_transition_plan(
        tmp_path, _transition_request(tmp_path, original["id"])
    )
    planned = task_state_index.publish_transition_plan(tmp_path, plan)
    task_state_index.apply_transition_plan(tmp_path, planned["plan_ref"])
    task_state_index.append_event(
        tmp_path,
        {
            "event": "link",
            "id": "task-successor",
            "updated_at": "2026-07-18T15:29:00+09:00",
            "links": [{"rel": "related_to", "id": "task-successor"}],
        },
    )

    before = task_state_index.verify_transition_plan(tmp_path, planned["plan_ref"])
    repaired = task_state_index.apply_transition_plan(tmp_path, planned["plan_ref"])
    after = task_state_index.verify_transition_plan(tmp_path, planned["plan_ref"])

    assert before["status"] == "recovery_required"
    assert before["historical_completion_observed"] is True
    assert before["current_projection_healthy"] is False
    assert "markdown_projection_repair_required" in before["cas_defects"]
    assert repaired["status"] == "already_applied"
    assert repaired["events_appended"] == 0
    assert repaired["publication_recovered"] is True
    assert after["status"] == "already_applied"
    assert after["historical_completion_observed"] is True
    assert after["current_projection_healthy"] is True


@pytest.mark.parametrize("tamper", ("wrong_prefix", "noncontiguous", "invalid_suffix"))
def test_transition_plan_recovery_rejects_unproven_historical_boundary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    tamper: str,
) -> None:
    task = tmp_path / "task.md"
    task.write_text("# Original task\n", encoding="utf-8")
    original = task_state_index.upsert_item(
        tmp_path,
        "task",
        "task.md",
        "active",
        item_id="task-original",
        replace_existing=False,
    )
    plan = task_state_index.build_transition_plan(
        tmp_path, _transition_request(tmp_path, original["id"])
    )
    planned = task_state_index.publish_transition_plan(tmp_path, plan)

    def crash_after_append(*_args: object, **_kwargs: object) -> dict[str, object]:
        raise RuntimeError("injected boundary proof failure")

    monkeypatch.setattr(
        transition_plan_module, "_rebuild_markdown_unlocked", crash_after_append
    )
    with pytest.raises(RuntimeError, match="boundary proof failure"):
        task_state_index.apply_transition_plan(tmp_path, planned["plan_ref"])
    index = tmp_path / ".task" / "index.jsonl"
    rows = task_state_index.load_events(tmp_path)
    start = next(
        offset
        for offset, row in enumerate(rows)
        if row.get("transition_plan_id") == plan["plan_id"]
    )
    if tamper == "wrong_prefix":
        rows[0] = {**rows[0], "note": "mutated historical prefix"}
    elif tamper == "noncontiguous":
        rows.insert(
            start + 1,
            task_state_index.versioned_event(
                {
                    "event": "link",
                    "id": original["id"],
                    "updated_at": "2026-07-18T12:20:00+09:00",
                    "links": [{"rel": "related_to", "id": original["id"]}],
                }
            ),
        )
    else:
        rows.append(
            task_state_index.versioned_event(
                {
                    "event": "upsert",
                    "id": "invalid-suffix",
                    "type": "unsupported_type",
                    "status": "active",
                    "path": "invalid.md",
                    "updated_at": "2026-07-18T12:20:01+09:00",
                }
            )
        )
    index.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="committed boundary"):
        task_state_index.apply_transition_plan(tmp_path, planned["plan_ref"])


def test_transition_plan_build_reuses_suffix_and_completed_alias_validators(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="unsupported type"):
        task_state_index.build_transition_plan(
            tmp_path,
            {
                "updated_at": "2026-07-18T15:30:00+09:00",
                "events": [
                    {
                        "event": "upsert",
                        "id": "unsupported-one",
                        "type": "unsupported_type",
                        "status": "active",
                        "path": "unsupported.md",
                    }
                ],
            },
        )

    task = tmp_path / "task.md"
    task.write_text("# Completed alias\n", encoding="utf-8")
    task_state_index.append_event(
        tmp_path,
        {
            "event": "upsert",
            "id": "task-completed",
            "type": "task",
            "status": "completed",
            "path": "task.md",
            "title": "Completed alias",
            "updated_at": "2026-07-18T15:30:01+09:00",
            "content_sha256": task_state_index.sha256_file(task),
            "fields": {
                "record_class": "mutable_alias",
                "canonical_id": "task-completed",
            },
        },
    )
    with pytest.raises(ValueError, match="distinct linked successor"):
        task_state_index.build_transition_plan(
            tmp_path,
            {
                "updated_at": "2026-07-18T15:30:02+09:00",
                "events": [
                    {
                        "event": "upsert",
                        "id": "task-completed",
                        "status": "active",
                    }
                ],
            },
        )


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
