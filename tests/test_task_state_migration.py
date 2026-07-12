from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest


sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
MIGRATION_PATH = ROOT / "manage-task-state-index" / "scripts" / "task_state_migration.py"
INDEX_PATH = ROOT / "manage-task-state-index" / "scripts" / "task_state_index.py"


def load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


migration = load_module(MIGRATION_PATH, "task_state_migration_tests")
task_index = load_module(INDEX_PATH, "task_state_index_migration_tests")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def mapping_manifest(*, row_resolutions: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    reason_codes = {
        "legacy_shape": "Unambiguous legacy event shape.",
        "exact_status": "Caller-owned exact status mapping.",
        "exact_type": "Caller-owned exact type mapping.",
        "historical_malformed": "Exact historical row is independent.",
    }
    return {
        "schema_version": 1,
        "mapping_policy_id": "fixture-exact-policy",
        "mapping_method": "exact_token_review",
        "pattern_inference_used": False,
        "effective_at": "2026-07-12T00:00:00+09:00",
        "event_mappings": {
            "__MISSING__": {"to": "__INFER__", "reason_code": "legacy_shape"},
            "upsert": {"to": "upsert", "reason_code": "legacy_shape"},
            "link": {"to": "link", "reason_code": "legacy_shape"},
            "legacy_upsert": {"to": "upsert", "reason_code": "legacy_shape"},
        },
        "status_mappings": {
            "active": {"to": "active", "reason_code": "exact_status"},
            "partial": {"to": "partial", "reason_code": "exact_status"},
            "old_active": {"to": "active", "reason_code": "exact_status"},
            "__MISSING__": {"to": "informational", "reason_code": "exact_status"},
        },
        "type_mappings": {
            "task": {"to": "task", "reason_code": "exact_type"},
            "task_pack": {"to": "task_pack", "reason_code": "exact_type"},
            "old_task": {"to": "task", "reason_code": "exact_type"},
            "__MISSING__": {"to": "schema_contract", "reason_code": "exact_type"},
        },
        "reason_codes": reason_codes,
        "row_resolutions": row_resolutions or [],
    }


def make_workspace(base: Path, *, malformed: bool = True, missing_status: bool = False) -> dict[str, Any]:
    root = base / "workspace"
    root.mkdir(parents=True)
    task_id = "task-current"
    pack_id = "pack-current"
    task = root / "task.md"
    task.write_text("# Current task\n", encoding="utf-8")
    pack = root / ".task" / "task_pack" / "pack-current.json"
    write_json(pack, {"schema_version": 1, "pack_id": pack_id, "status": "active", "items": []})
    rows: list[bytes] = []
    task_row: dict[str, Any] = {
        "id": task_id, "type": "old_task", "status": "old_active", "path": "task.md",
        "title": "Current task", "links": ["broken:missing-id", "promoted_from_pack:pack-old"],
        "updated_at": "2026-07-01T00:00:00+09:00",
    }
    if missing_status:
        task_row.pop("status")
    values = [
        task_row,
        {"id": "task-stale", "type": "task", "status": "active", "path": "task.md", "title": "Stale", "updated_at": "2026-07-01T00:00:01+09:00"},
        {"id": "pack-old", "type": "task_pack", "status": "active", "path": ".task/task_pack/old.json", "title": "Old", "updated_at": "2026-07-01T00:00:02+09:00"},
        {"id": pack_id, "event": "legacy_upsert", "type": "task_pack", "status": "old_active", "path": ".task/task_pack/pack-current.json", "title": "Current pack", "updated_at": "2026-07-01T00:00:03+09:00"},
    ]
    rows.extend((json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8") for value in values)
    malformed_line = b"{malformed historical row}\n"
    if malformed:
        rows.append(malformed_line)
    index = root / ".task" / "index.jsonl"
    index.parent.mkdir(parents=True, exist_ok=True)
    prefix = b"".join(rows)
    index.write_bytes(prefix)
    mapping = mapping_manifest()
    if malformed:
        mapping["row_resolutions"] = [{
            "line": len(rows), "raw_line_sha256": sha(malformed_line),
            "disposition": "quarantined_historical", "projection_impact": "independent",
            "reason_code": "historical_malformed", "deterministic_identity": "historical-row",
            "resolution": "historical_only",
        }]
    mapping_path = base / "mapping.json"
    write_json(mapping_path, mapping)
    return {
        "root": root, "prefix": prefix, "index": index, "mapping": mapping_path,
        "task_id": task_id, "task_sha": sha(task.read_bytes()),
        "pack_id": pack_id, "pack_path": ".task/task_pack/pack-current.json",
        "pack_sha": sha(pack.read_bytes()),
    }


def build_fixture_plan(fixture: dict[str, Any], output: Path) -> dict[str, Any]:
    plan = migration.build_plan(
        fixture["root"], sha(fixture["prefix"]), fixture["task_id"], "task.md", fixture["task_sha"],
        fixture["pack_id"], fixture["pack_path"], fixture["pack_sha"], fixture["mapping"],
    )
    output.write_bytes(migration._canonical_bytes(plan))
    return plan


def apply_fixture(fixture: dict[str, Any], base: Path) -> tuple[dict[str, Any], Path, dict[str, Any]]:
    plan_path = base / "plan.json"
    plan = build_fixture_plan(fixture, plan_path)
    result = migration.apply_plan(
        fixture["root"], plan_path, sha(plan_path.read_bytes()), sha(fixture["prefix"]),
    )
    receipt = fixture["root"] / plan["receipt_ref"]
    return plan, receipt, result


def test_inspect_is_read_only_and_reports_exact_tokens(tmp_path: Path) -> None:
    fixture = make_workspace(tmp_path)
    before = fixture["index"].read_bytes()
    result = migration.inspect_store(fixture["root"])
    assert result["raw_row_count"] == 5
    assert "old_active" in result["exact_tokens"]["statuses"]
    assert result["malformed_rows"][0]["raw_line_sha256"] == sha(b"{malformed historical row}\n")
    assert fixture["index"].read_bytes() == before


def test_deterministic_plan_and_dry_run_zero_mutation(tmp_path: Path) -> None:
    fixture = make_workspace(tmp_path)
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    plan_a = build_fixture_plan(fixture, first)
    plan_b = build_fixture_plan(fixture, second)
    assert first.read_bytes() == second.read_bytes()
    before = fixture["index"].read_bytes()
    result = migration.apply_plan(fixture["root"], first, sha(first.read_bytes()), sha(before), dry_run=True)
    assert result["mutation_performed"] is False
    assert plan_a == plan_b
    assert fixture["index"].read_bytes() == before
    assert not (fixture["root"] / ".task" / "migrations").exists()


def test_apply_preserves_prefix_classifies_every_row_and_reconciles_projection(tmp_path: Path) -> None:
    fixture = make_workspace(tmp_path)
    plan, receipt_path, result = apply_fixture(fixture, tmp_path)
    after = fixture["index"].read_bytes()
    assert after.startswith(fixture["prefix"])
    assert result["idempotent"] is False
    manifest = json.loads((fixture["root"] / plan["resolution_manifest"]["ref"]).read_text(encoding="utf-8"))
    assert len(manifest["rows"]) == 5
    assert {(row["line"], row["raw_line_sha256"]) for row in manifest["rows"]} == {
        (line, sha(raw)) for line, raw in enumerate(fixture["prefix"].splitlines(keepends=True), start=1)
    }
    checked = migration.validate_migration(fixture["root"], receipt_path)
    assert checked["active_task_count"] == 1
    assert checked["active_pack_count"] == 1
    assert checked["duplicate_active_alias_count"] == 0
    assert checked["current_broken_link_count"] == 0
    assert checked["projection_completeness"] == "complete"


def append_active_identity_switch(
    fixture: dict[str, Any], *, broken_link: bool = False, duplicate_alias: bool = False,
) -> tuple[str, str]:
    new_task_id = "task-successor"
    new_pack_id = "pack-successor"
    task_index.append_event(fixture["root"], migration._versioned({
        "event": "upsert", "id": fixture["task_id"], "status": "superseded",
        "updated_at": "2026-07-12T01:00:00+09:00",
    }))
    task_index.append_event(fixture["root"], migration._versioned({
        "event": "upsert", "id": fixture["pack_id"], "status": "superseded",
        "updated_at": "2026-07-12T01:00:01+09:00",
    }))
    task_index.append_event(fixture["root"], migration._versioned({
        "event": "upsert", "id": new_pack_id, "type": "task_pack", "status": "active",
        "path": ".task/task_pack/pack-successor.json", "title": "Successor pack",
        "updated_at": "2026-07-12T01:00:02+09:00",
    }))
    links = [{"rel": "pack_for_task", "id": new_pack_id}]
    if broken_link:
        links.append({"rel": "depends_on", "id": "missing-current-target"})
    task_index.append_event(fixture["root"], migration._versioned({
        "event": "upsert", "id": new_task_id, "type": "task", "status": "active",
        "path": "task.md", "title": "Successor task",
        "updated_at": "2026-07-12T01:00:03+09:00", "links": links,
    }))
    if duplicate_alias:
        task_index.append_event(fixture["root"], migration._versioned({
            "event": "upsert", "id": "task-successor-alias", "type": "task", "status": "partial",
            "path": "task.md", "title": "Conflicting successor alias",
            "updated_at": "2026-07-12T01:00:04+09:00",
        }))
    return new_task_id, new_pack_id


def test_validate_accepts_append_only_active_identity_switch_after_seal(tmp_path: Path) -> None:
    fixture = make_workspace(tmp_path)
    _plan, receipt_path, _result = apply_fixture(fixture, tmp_path)
    new_task_id, new_pack_id = append_active_identity_switch(fixture)

    checked = migration.validate_migration(fixture["root"], receipt_path)

    assert checked["migration_boundary_task_id"] == fixture["task_id"]
    assert checked["migration_boundary_pack_id"] == fixture["pack_id"]
    assert checked["migration_boundary_projection_completeness"] == "complete"
    assert checked["current_active_task_id"] == new_task_id
    assert checked["current_active_pack_id"] == new_pack_id
    assert checked["active_task_count"] == 1
    assert checked["active_pack_count"] == 1
    assert checked["duplicate_active_alias_count"] == 0
    assert checked["current_broken_link_count"] == 0
    assert checked["projection_completeness"] == "complete"
    assert checked["append_simulation_status"] == "pass"


@pytest.mark.parametrize(
    "invalid_projection",
    ["multi_active_task", "multi_active_pack", "no_active_task", "no_active_pack", "broken_link", "duplicate_alias"],
)
def test_validate_postseal_identity_switch_keeps_current_projection_fail_closed(
    tmp_path: Path, invalid_projection: str,
) -> None:
    fixture = make_workspace(tmp_path)
    _plan, receipt_path, _result = apply_fixture(fixture, tmp_path)
    if invalid_projection == "multi_active_task":
        task_index.append_event(fixture["root"], migration._versioned({
            "event": "upsert", "id": "task-second-active", "type": "task", "status": "active",
            "path": "second-task.md", "title": "Second active task",
            "updated_at": "2026-07-12T01:00:00+09:00",
        }))
    elif invalid_projection == "multi_active_pack":
        task_index.append_event(fixture["root"], migration._versioned({
            "event": "upsert", "id": "pack-second-active", "type": "task_pack", "status": "active",
            "path": ".task/task_pack/second-active.json", "title": "Second active pack",
            "updated_at": "2026-07-12T01:00:00+09:00",
        }))
    elif invalid_projection == "no_active_task":
        task_index.append_event(fixture["root"], migration._versioned({
            "event": "upsert", "id": fixture["task_id"], "status": "superseded",
            "updated_at": "2026-07-12T01:00:00+09:00",
        }))
    elif invalid_projection == "no_active_pack":
        task_index.append_event(fixture["root"], migration._versioned({
            "event": "upsert", "id": fixture["pack_id"], "status": "superseded",
            "updated_at": "2026-07-12T01:00:00+09:00",
        }))
    else:
        append_active_identity_switch(
            fixture, broken_link=invalid_projection == "broken_link",
            duplicate_alias=invalid_projection == "duplicate_alias",
        )

    with pytest.raises(migration.MigrationError, match="projection or prefix integrity is incomplete"):
        migration.validate_migration(fixture["root"], receipt_path)


def test_standard_reader_append_link_rebuild_audit_after_migration(tmp_path: Path) -> None:
    fixture = make_workspace(tmp_path)
    _plan, _receipt, _result = apply_fixture(fixture, tmp_path)
    events = task_index.load_events(fixture["root"])
    assert events
    state = task_index.merge_state(events)
    current_links = {(item["rel"], item["id"]) for item in state[fixture["task_id"]]["links"]}
    assert ("broken", "missing-id") not in current_links
    assert ("promoted_from_pack", "pack-old") not in current_links
    assert ("pack_for_task", fixture["pack_id"]) in current_links
    scan = task_index.scan_artifacts(fixture["root"])
    assert scan["scan_evidence_status"] == "evaluated"
    add = task_index.upsert_item(
        fixture["root"], "task", "task.md", "active",
        item_id=fixture["task_id"], title="Current task", replace_existing=False,
    )
    assert add["id"] == fixture["task_id"]
    task_index.append_event(fixture["root"], {
        "event": "link", "id": fixture["task_id"], "updated_at": "2026-07-12T00:00:01+09:00", "links": []
    })
    task_index.link_item(fixture["root"], fixture["task_id"], [{"rel": "related_to", "id": fixture["pack_id"]}])
    task_index.rebuild_markdown(fixture["root"])
    audit = task_index.audit_index(fixture["root"])
    assert audit["current_projection_status"] == "evaluated"
    assert audit["projection_completeness"] == "complete"


def test_sealed_suffix_accepts_writer_sparse_updates_only_for_existing_ids(tmp_path: Path) -> None:
    fixture = make_workspace(tmp_path)
    _plan, _receipt, _result = apply_fixture(fixture, tmp_path)
    task_index.append_event(fixture["root"], {
        "event": "upsert", "id": "task-stale", "status": "archived",
        "updated_at": "2026-07-12T00:00:01+09:00",
    })
    task_index.append_event(fixture["root"], {
        "event": "upsert", "id": "task-stale",
        "fields": {"lifecycle_note": "writer-owned sparse field update"},
        "updated_at": "2026-07-12T00:00:02+09:00",
    })
    state = task_index.merge_state(task_index.load_events(fixture["root"]))
    assert state["task-stale"]["status"] == "archived"
    assert state["task-stale"]["fields"]["lifecycle_note"] == "writer-owned sparse field update"


@pytest.mark.parametrize(
    ("event", "message"),
    [
        (
            {
                "event": "upsert", "id": "cand-unknown", "status": "superseded",
                "updated_at": "2026-07-12T00:00:01+09:00",
            },
            "unknown ID",
        ),
        (
            {
                "event": "upsert", "id": "future-new", "type": "unsupported_future_type",
                "status": "partial", "path": "future.md",
                "updated_at": "2026-07-12T00:00:01+09:00",
            },
            "unsupported type",
        ),
    ],
)
def test_writer_rejects_unknown_sparse_or_explicit_unsupported_type_before_append(
    tmp_path: Path, event: dict[str, Any], message: str,
) -> None:
    fixture = make_workspace(tmp_path)
    apply_fixture(fixture, tmp_path)
    before = fixture["index"].read_bytes()
    with pytest.raises(ValueError, match=message):
        task_index.append_event(fixture["root"], event)
    assert fixture["index"].read_bytes() == before


def test_standard_scan_repairs_postseal_duplicate_with_sparse_lifecycle_suffix(
    tmp_path: Path,
) -> None:
    fixture = make_workspace(tmp_path)
    candidate = fixture["root"] / ".task" / "candidate_task" / "shared.md"
    candidate.parent.mkdir(parents=True)
    candidate.write_text("# Shared candidate\n", encoding="utf-8")
    duplicates = [
        migration._versioned({
            "event": "upsert", "id": f"cand-duplicate-{suffix}",
            "type": "candidate_task", "status": "candidate",
            "path": ".task/candidate_task/shared.md", "title": f"Prior {suffix}",
            "updated_at": f"2026-07-01T00:03:0{ordinal}+09:00",
        })
        for ordinal, suffix in enumerate(("a", "b"), start=1)
    ]
    fixture["prefix"] += migration._event_bytes(duplicates)
    fixture["index"].write_bytes(fixture["prefix"])
    _plan, receipt_path, _result = apply_fixture(fixture, tmp_path)
    before_scan = fixture["index"].read_bytes()

    first = task_index.scan_artifacts(fixture["root"])
    after_first = fixture["index"].read_bytes()
    assert first["indexed_events"] >= 1
    assert after_first.startswith(before_scan)
    state = task_index.merge_state(task_index.load_events(fixture["root"]))
    duplicate_statuses = sorted(state[item_id]["status"] for item_id in ("cand-duplicate-a", "cand-duplicate-b"))
    assert duplicate_statuses == ["candidate", "superseded"]
    assert migration.validate_migration(fixture["root"], receipt_path)["valid"] is True

    second = task_index.scan_artifacts(fixture["root"])
    assert second["indexed_events"] == 0
    assert fixture["index"].read_bytes() == after_first


def test_audit_keeps_historical_duplicate_paths_as_debt_after_standard_consumers(
    tmp_path: Path,
) -> None:
    fixture = make_workspace(tmp_path)
    historical_duplicates = [
        migration._versioned({
            "event": "upsert", "id": f"val-historical-{suffix}",
            "type": "validation", "status": "partial",
            "path": "historical/shared-validation.md", "title": f"Historical {suffix}",
            "updated_at": f"2026-07-01T00:01:0{index}+09:00",
        })
        for index, suffix in enumerate(("a", "b"), start=1)
    ]
    fixture["prefix"] += migration._event_bytes(historical_duplicates)
    fixture["index"].write_bytes(fixture["prefix"])
    plan, receipt_path, _result = apply_fixture(fixture, tmp_path)

    task_index.scan_artifacts(fixture["root"])
    task_index.upsert_item(
        fixture["root"], "task", "task.md", "active",
        item_id=fixture["task_id"], title="Current task", replace_existing=False,
    )
    task_index.link_item(
        fixture["root"], fixture["task_id"],
        [{"rel": "related_to", "id": fixture["pack_id"]}],
    )
    task_index.rebuild_markdown(fixture["root"])

    checked = migration.validate_migration(fixture["root"], receipt_path)
    audit = task_index.audit_index(fixture["root"])
    duplicate_issues = [issue for issue in audit["issues"] if issue["code"] == "duplicate_active_path"]
    historical_duplicates_after = [
        issue for issue in audit["historical_debt"] if issue["code"] == "duplicate_active_path"
    ]
    assert checked["receipt"]["current_surface_blocker_count"] == 0
    assert audit["current_surface_blockers"] == []
    assert duplicate_issues == historical_duplicates_after
    assert len(historical_duplicates_after) == 1
    assert historical_duplicates_after[0]["ids"] == ["val-historical-a", "val-historical-b"]
    assert plan["projection"]["current_surface_blocker_count"] == 0


def test_audit_still_blocks_duplicate_current_task_alias(tmp_path: Path) -> None:
    (tmp_path / "task.md").write_text("# Current\n", encoding="utf-8")
    index = tmp_path / ".task" / "index.jsonl"
    index.parent.mkdir(parents=True)
    events = [
        migration._versioned({
            "event": "upsert", "id": item_id, "type": "task", "status": status,
            "path": "task.md", "title": item_id,
            "updated_at": f"2026-07-12T00:00:0{ordinal}+09:00",
        })
        for ordinal, (item_id, status) in enumerate(
            (("task-current", "active"), ("task-legacy-alias", "partial")), start=1,
        )
    ]
    index.write_bytes(migration._event_bytes(events))
    audit = task_index.audit_index(tmp_path)
    assert any(
        issue["code"] == "duplicate_active_path"
        for issue in audit["current_surface_blockers"]
    )


def test_exact_live_shape_stress_reconciles_11_tasks_10_aliases_38_links_and_stale_packs(tmp_path: Path) -> None:
    fixture = make_workspace(tmp_path, malformed=False)
    rows = fixture["prefix"].splitlines(keepends=True)
    current = json.loads(rows[0])
    current["links"] = [f"broken:missing-{index:02d}" for index in range(38)]
    rows[0] = (json.dumps(current, sort_keys=True) + "\n").encode()
    # Existing fixture has one stale task; add nine more for 11 active tasks
    # sharing the mutable root alias in total.
    for index in range(2, 11):
        rows.append((json.dumps({
            "id": f"task-stale-{index:02d}", "type": "task", "status": "active",
            "path": "task.md", "title": f"Stale {index}",
            "updated_at": f"2026-07-01T00:01:{index:02d}+09:00",
        }, sort_keys=True) + "\n").encode())
    for index in range(2):
        rows.append((json.dumps({
            "id": f"pack-stale-{index:02d}", "type": "task_pack", "status": "active",
            "path": f".task/task_pack/stale-{index:02d}.json", "title": "Stale pack",
            "updated_at": f"2026-07-01T00:02:{index:02d}+09:00",
        }, sort_keys=True) + "\n").encode())
    fixture["prefix"] = b"".join(rows)
    fixture["index"].write_bytes(fixture["prefix"])
    plan = build_fixture_plan(fixture, tmp_path / "stress-plan.json")
    assert plan["projection"]["before_active_task_count"] == 11
    assert plan["projection"]["before_duplicate_active_alias_count"] == 10
    assert plan["projection"]["before_current_broken_link_count"] == 38
    assert plan["projection"]["before_active_pack_count"] == 4
    assert len(plan["projection"]["superseded_task_ids"]) == 10
    assert len(plan["projection"]["retracted_links"]) == 38
    assert len(plan["projection"]["superseded_pack_ids"]) == 3
    assert plan["projection"]["active_task_count"] == 1
    assert plan["projection"]["duplicate_active_alias_count"] == 0
    assert plan["projection"]["current_broken_link_count"] == 0
    assert plan["projection"]["active_pack_count"] == 1
    plan_path = tmp_path / "stress-plan.json"
    result = migration.apply_plan(
        fixture["root"], plan_path, sha(plan_path.read_bytes()), sha(fixture["prefix"]),
    )
    assert result["idempotent"] is False
    receipt_path = fixture["root"] / plan["receipt_ref"]
    checked = migration.validate_migration(fixture["root"], receipt_path)
    assert checked["active_task_count"] == 1
    assert checked["duplicate_active_alias_count"] == 0
    assert checked["current_broken_link_count"] == 0
    assert checked["active_pack_count"] == 1
    assert checked["prefix_preserved"] is True


def test_missing_status_requires_exact_mapping_and_is_not_substring_inferred(tmp_path: Path) -> None:
    fixture = make_workspace(tmp_path, missing_status=True)
    plan = build_fixture_plan(fixture, tmp_path / "plan.json")
    assert plan["unclassified_count"] == 0
    mapping = json.loads(fixture["mapping"].read_text(encoding="utf-8"))
    del mapping["status_mappings"]["__MISSING__"]
    write_json(fixture["mapping"], mapping)
    blocked = migration.build_plan(
        fixture["root"], sha(fixture["prefix"]), fixture["task_id"], "task.md", fixture["task_sha"],
        fixture["pack_id"], fixture["pack_path"], fixture["pack_sha"], fixture["mapping"],
    )
    assert blocked["unclassified_count"] == 1


@pytest.mark.parametrize("mutation", ["unsupported_status", "unsupported_event", "unsupported_type", "future_version", "malformed_json"])
def test_unknown_or_future_rows_fail_closed_without_exact_resolution(tmp_path: Path, mutation: str) -> None:
    fixture = make_workspace(tmp_path, malformed=False)
    lines = fixture["prefix"].splitlines(keepends=True)
    if mutation == "malformed_json":
        lines.append(b"{\n")
    else:
        row = json.loads(lines[0])
        if mutation == "unsupported_status":
            row["status"] = "completed_but_pending"
        elif mutation == "unsupported_event":
            row["event"] = "future_event"
        elif mutation == "unsupported_type":
            row["type"] = "repo_private_type"
        elif mutation == "future_version":
            row["format_version"] = 99
            row["schema_version"] = 99
        lines[0] = (json.dumps(row, sort_keys=True) + "\n").encode()
    fixture["prefix"] = b"".join(lines)
    fixture["index"].write_bytes(fixture["prefix"])
    plan = build_fixture_plan(fixture, tmp_path / "plan.json")
    assert plan["unclassified_count"] >= 1
    with pytest.raises(migration.MigrationError, match="unclassified_count=0"):
        migration.apply_plan(fixture["root"], tmp_path / "plan.json", sha((tmp_path / "plan.json").read_bytes()), sha(fixture["prefix"]))


def test_affected_or_unknown_quarantine_requires_projection_correction(tmp_path: Path) -> None:
    fixture = make_workspace(tmp_path)
    mapping = json.loads(fixture["mapping"].read_text(encoding="utf-8"))
    mapping["row_resolutions"][0]["projection_impact"] = "unknown"
    mapping["row_resolutions"][0]["resolution"] = "historical_only"
    write_json(fixture["mapping"], mapping)
    plan = build_fixture_plan(fixture, tmp_path / "plan.json")
    assert plan["unclassified_count"] == 1


@pytest.mark.parametrize(
    ("axis", "token"),
    [("event_mappings", "legacy_upsert"), ("status_mappings", "old_active"), ("type_mappings", "old_task")],
)
def test_exact_mapping_manifest_requires_each_event_status_and_type_token(tmp_path: Path, axis: str, token: str) -> None:
    fixture = make_workspace(tmp_path)
    mapping = json.loads(fixture["mapping"].read_text(encoding="utf-8"))
    del mapping[axis][token]
    write_json(fixture["mapping"], mapping)
    plan = build_fixture_plan(fixture, tmp_path / "plan.json")
    assert plan["unclassified_count"] >= 1


def test_plan_and_mapping_tamper_are_rejected_before_mutation(tmp_path: Path) -> None:
    fixture = make_workspace(tmp_path)
    plan_path = tmp_path / "plan.json"
    build_fixture_plan(fixture, plan_path)
    before = fixture["index"].read_bytes()
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    plan["projection"]["active_task_count"] = 2
    write_json(plan_path, plan)
    with pytest.raises(migration.MigrationError, match="contract digest mismatch"):
        migration.apply_plan(fixture["root"], plan_path, sha(plan_path.read_bytes()), sha(before))
    assert fixture["index"].read_bytes() == before

    build_fixture_plan(fixture, plan_path)
    mapping = json.loads(fixture["mapping"].read_text(encoding="utf-8"))
    mapping["reason_codes"]["late"] = "Tampered after planning."
    write_json(fixture["mapping"], mapping)
    with pytest.raises(migration.MigrationError, match="Mapping manifest drifted"):
        migration.apply_plan(fixture["root"], plan_path, sha(plan_path.read_bytes()), sha(before))
    assert fixture["index"].read_bytes() == before


def test_mapping_manifest_rejects_pattern_inference_attestation(tmp_path: Path) -> None:
    fixture = make_workspace(tmp_path)
    mapping = json.loads(fixture["mapping"].read_text(encoding="utf-8"))
    mapping["pattern_inference_used"] = True
    write_json(fixture["mapping"], mapping)
    with pytest.raises(migration.MigrationError, match="pattern_inference_used=false"):
        migration.build_plan(
            fixture["root"], sha(fixture["prefix"]), fixture["task_id"], "task.md", fixture["task_sha"],
            fixture["pack_id"], fixture["pack_path"], fixture["pack_sha"], fixture["mapping"],
        )

def test_seal_tamper_blocks_two_pass_reader(tmp_path: Path) -> None:
    fixture = make_workspace(tmp_path)
    plan, _receipt_path, _result = apply_fixture(fixture, tmp_path)
    payload = bytearray(fixture["index"].read_bytes())
    offset = plan["seal"]["offset"]
    original = bytes(payload[offset : offset + plan["seal"]["byte_length"]])
    changed = original.replace(b"informational", b"informationaX", 1)
    assert len(changed) == len(original)
    payload[offset : offset + len(changed)] = changed
    fixture["index"].write_bytes(payload)
    with pytest.raises(ValueError, match="boundary mismatch"):
        task_index.load_events(fixture["root"])


def test_anchor_mismatch_and_source_drift_are_zero_mutation(tmp_path: Path) -> None:
    fixture = make_workspace(tmp_path)
    before = fixture["index"].read_bytes()
    with pytest.raises(migration.MigrationError, match="anchor mismatch"):
        migration.build_plan(
            fixture["root"], sha(before), fixture["task_id"], "task.md", "0" * 64,
            fixture["pack_id"], fixture["pack_path"], fixture["pack_sha"], fixture["mapping"],
        )
    plan_path = tmp_path / "plan.json"
    build_fixture_plan(fixture, plan_path)
    fixture["index"].write_bytes(before + b"{}\n")
    with pytest.raises(migration.MigrationError, match="drift"):
        migration.apply_plan(fixture["root"], plan_path, sha(plan_path.read_bytes()), sha(before), dry_run=True)
    assert fixture["index"].read_bytes() == before + b"{}\n"


def test_apply_rechecks_anchor_inside_lock_before_any_migration_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = make_workspace(tmp_path)
    plan_path = tmp_path / "plan.json"
    build_fixture_plan(fixture, plan_path)
    before = fixture["index"].read_bytes()
    original_lock = migration._index_lock

    @contextmanager
    def drifting_lock(root: Path):
        with original_lock(root):
            (fixture["root"] / "task.md").write_text("# Drifted under lock\n", encoding="utf-8")
            yield

    monkeypatch.setattr(migration, "_index_lock", drifting_lock)
    with pytest.raises(migration.MigrationError, match="anchor mismatch"):
        migration.apply_plan(
            fixture["root"], plan_path, sha(plan_path.read_bytes()), sha(before),
        )
    assert fixture["index"].read_bytes() == before
    assert not (fixture["root"] / ".task" / "migrations").exists()


def test_dry_run_rechecks_safe_anchor_sha_and_pack_id_without_mutation(tmp_path: Path) -> None:
    fixture = make_workspace(tmp_path)
    plan_path = tmp_path / "plan.json"
    plan = build_fixture_plan(fixture, plan_path)
    before = fixture["index"].read_bytes()
    (fixture["root"] / "task.md").write_text("# Drifted\n", encoding="utf-8")
    with pytest.raises(migration.MigrationError, match="anchor mismatch"):
        migration.apply_plan(
            fixture["root"], plan_path, sha(plan_path.read_bytes()), sha(before), dry_run=True,
        )
    assert fixture["index"].read_bytes() == before
    assert not (fixture["root"] / ".task" / "migrations").exists()

    pack = fixture["root"] / fixture["pack_path"]
    write_json(pack, {"schema_version": 1, "pack_id": "pack-other", "status": "active", "items": []})
    anchors = json.loads(json.dumps(plan))
    anchors["anchors"]["current_task"]["sha256"] = sha((fixture["root"] / "task.md").read_bytes())
    anchors["anchors"]["current_pack"]["sha256"] = sha(pack.read_bytes())
    with pytest.raises(migration.MigrationError, match="pack ID"):
        migration._validate_plan_anchors(fixture["root"], anchors)


@pytest.mark.parametrize("dry_run", [False, True])
def test_pack_body_drift_blocks_apply_and_dry_run_without_canonical_mutation(
    tmp_path: Path, dry_run: bool,
) -> None:
    fixture = make_workspace(tmp_path)
    plan_path = tmp_path / "plan.json"
    build_fixture_plan(fixture, plan_path)
    index_before = fixture["index"].read_bytes()
    index_md = fixture["root"] / ".task" / "index.md"
    index_md.write_text("# Existing view\n", encoding="utf-8")
    view_before = index_md.read_bytes()
    pack = fixture["root"] / fixture["pack_path"]
    write_json(pack, {
        "schema_version": 1, "pack_id": fixture["pack_id"], "status": "active",
        "items": [], "drift": True,
    })
    with pytest.raises(migration.MigrationError, match="anchor mismatch"):
        migration.apply_plan(
            fixture["root"], plan_path, sha(plan_path.read_bytes()), sha(index_before), dry_run=dry_run,
        )
    assert fixture["index"].read_bytes() == index_before
    assert index_md.read_bytes() == view_before
    assert not (fixture["root"] / ".task" / "migrations").exists()


def test_initial_apply_refuses_tail_and_recovery_refuses_nonowned_partial_tail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = make_workspace(tmp_path)
    plan_path = tmp_path / "plan.json"
    plan = build_fixture_plan(fixture, plan_path)
    before = fixture["prefix"]
    fixture["index"].write_bytes(before + b"foreign-tail")
    with pytest.raises(migration.MigrationError, match="exact planned source prefix"):
        migration.apply_plan(
            fixture["root"], plan_path, sha(plan_path.read_bytes()), sha(before),
        )
    assert fixture["index"].read_bytes() == before + b"foreign-tail"
    assert not (fixture["root"] / ".task" / "migrations").exists()

    fixture["index"].write_bytes(before)
    monkeypatch.setenv("TASK_STATE_MIGRATION_CRASH_AT", "after_partial_suffix")
    with pytest.raises(RuntimeError, match="injected crash"):
        migration.apply_plan(
            fixture["root"], plan_path, sha(plan_path.read_bytes()), sha(before),
        )
    monkeypatch.delenv("TASK_STATE_MIGRATION_CRASH_AT")
    payload = fixture["index"].read_bytes()
    tail = payload[len(before):]
    foreign = (b"X" if tail[:1] != b"X" else b"Y") + tail[1:]
    fixture["index"].write_bytes(before + foreign)
    journal_path = fixture["root"] / plan["journal_ref"]
    journal = json.loads(journal_path.read_text(encoding="utf-8"))
    journal["appended_byte_length"] = len(foreign)
    journal["appended_sha256"] = sha(foreign)
    write_json(journal_path, journal)
    corrupted = fixture["index"].read_bytes()
    with pytest.raises(migration.MigrationError, match="exact prefix"):
        migration.recover_transaction(fixture["root"], plan["migration_id"])
    assert fixture["index"].read_bytes() == corrupted


def test_recovery_fails_closed_in_append_before_journal_update_syscall_window(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = make_workspace(tmp_path)
    plan_path = tmp_path / "plan.json"
    plan = build_fixture_plan(fixture, plan_path)
    monkeypatch.setenv("TASK_STATE_MIGRATION_CRASH_AT", "after_prepare")
    with pytest.raises(RuntimeError, match="injected crash"):
        migration.apply_plan(
            fixture["root"], plan_path, sha(plan_path.read_bytes()), sha(fixture["prefix"]),
        )
    monkeypatch.delenv("TASK_STATE_MIGRATION_CRASH_AT")
    correction = (fixture["root"] / plan["correction_suffix"]["ref"]).read_bytes()
    seal = migration._canonical_bytes(plan["seal"]["event"])
    partial = (correction + seal)[:31]
    fixture["index"].write_bytes(fixture["prefix"] + partial)
    before = fixture["index"].read_bytes()
    with pytest.raises(migration.MigrationError, match="partial-suffix journal"):
        migration.recover_transaction(fixture["root"], plan["migration_id"])
    assert fixture["index"].read_bytes() == before


def test_mapped_legacy_tokens_and_exact_reason_codes_are_preserved(tmp_path: Path) -> None:
    fixture = make_workspace(tmp_path)
    mapping = json.loads(fixture["mapping"].read_text(encoding="utf-8"))
    _rows, events, _counts = migration._classify_rows(fixture["prefix"], mapping)
    current = next(event for event in events if event["id"] == fixture["task_id"])
    assert current["fields"]["legacy_original_event"] == {
        "token": "__MISSING__", "reason_code": "legacy_shape",
    }
    assert current["fields"]["legacy_original_status"] == {
        "token": "old_active", "reason_code": "exact_status",
    }
    assert current["fields"]["legacy_original_type"] == {
        "token": "old_task", "reason_code": "exact_type",
    }


def test_nonindependent_quarantine_binds_exact_correction_ids_and_hashes(tmp_path: Path) -> None:
    fixture = make_workspace(tmp_path)
    mapping = json.loads(fixture["mapping"].read_text(encoding="utf-8"))
    mapping["row_resolutions"][0]["projection_impact"] = "unknown"
    mapping["row_resolutions"][0]["resolution"] = "projection_epoch_reset"
    write_json(fixture["mapping"], mapping)
    plan_path = tmp_path / "plan.json"
    plan = build_fixture_plan(fixture, plan_path)
    row = next(item for item in plan["rows"] if item["projection_impact"] == "unknown")
    assert len(row["correction_event_ids"]) == 2
    assert len(row["correction_event_sha256s"]) == 2
    migration._validate_quarantine_correction_bindings(plan["rows"], plan["correction_events"])
    tampered = json.loads(json.dumps(plan["rows"]))
    target = next(item for item in tampered if item["projection_impact"] == "unknown")
    target["correction_event_sha256s"][0] = "0" * 64
    with pytest.raises(migration.MigrationError, match="binding mismatch"):
        migration._validate_quarantine_correction_bindings(tampered, plan["correction_events"])
    result = migration.apply_plan(
        fixture["root"], plan_path, sha(plan_path.read_bytes()), sha(fixture["prefix"]),
    )
    assert result["idempotent"] is False
    assert migration.load_sealed_events_if_present(fixture["root"]) is not None


@pytest.mark.parametrize(
    "sidecar_key",
    [
        "resolution_manifest_ref", "mapping_manifest_ref", "plan_ref", "rendered_index_ref",
        "prepare_journal_ref", "journal_ref", "completion_marker_ref",
    ],
)
def test_receipt_sidecar_tamper_blocks_strict_mutation_and_audit(tmp_path: Path, sidecar_key: str) -> None:
    fixture = make_workspace(tmp_path)
    _plan, receipt_path, _result = apply_fixture(fixture, tmp_path)
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    sidecar = fixture["root"] / receipt[sidecar_key]
    sidecar.write_bytes(sidecar.read_bytes() + b"tamper")
    with pytest.raises(ValueError, match="digest mismatch"):
        task_index.load_events(fixture["root"])
    with pytest.raises(ValueError, match="digest mismatch"):
        task_index.audit_index(fixture["root"])
    with pytest.raises(ValueError, match="digest mismatch"):
        task_index.append_event(fixture["root"], {
            "event": "link", "id": fixture["task_id"], "updated_at": "2026-07-12T00:00:01+09:00", "links": []
        })
    with pytest.raises(migration.MigrationError, match="digest mismatch"):
        migration.validate_migration(fixture["root"], receipt_path)


@pytest.mark.parametrize("operation", ["scan", "link", "rebuild"])
def test_committed_journal_tamper_blocks_all_standard_mutators_without_index_change(
    tmp_path: Path, operation: str,
) -> None:
    fixture = make_workspace(tmp_path)
    _plan, receipt_path, _result = apply_fixture(fixture, tmp_path)
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    journal = fixture["root"] / receipt["journal_ref"]
    journal.write_bytes(journal.read_bytes() + b"tamper")
    before = fixture["index"].read_bytes()
    with pytest.raises(ValueError, match="digest mismatch"):
        if operation == "scan":
            task_index.scan_artifacts(fixture["root"])
        elif operation == "link":
            task_index.link_item(
                fixture["root"], fixture["task_id"],
                [{"rel": "related_to", "id": fixture["pack_id"]}],
            )
        else:
            task_index.rebuild_markdown(fixture["root"])
    assert fixture["index"].read_bytes() == before


@pytest.mark.parametrize("sidecar_key", ["journal_ref", "completion_marker_ref"])
@pytest.mark.parametrize("mutation", ["delete", "tamper"])
@pytest.mark.parametrize("operation", ["load", "audit", "append", "scan", "link", "rebuild"])
def test_journal_and_completion_marker_loss_or_tamper_blocks_every_consumer_without_view_mutation(
    tmp_path: Path, sidecar_key: str, mutation: str, operation: str,
) -> None:
    fixture = make_workspace(tmp_path)
    _plan, receipt_path, _result = apply_fixture(fixture, tmp_path)
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    sidecar = fixture["root"] / receipt[sidecar_key]
    index_before = fixture["index"].read_bytes()
    index_md = fixture["root"] / ".task" / "index.md"
    view_before = index_md.read_bytes()
    if mutation == "delete":
        sidecar.unlink()
    else:
        sidecar.write_bytes(sidecar.read_bytes() + b"tamper")

    with pytest.raises(ValueError):
        if operation == "load":
            task_index.load_events(fixture["root"])
        elif operation == "audit":
            task_index.audit_index(fixture["root"])
        elif operation == "append":
            task_index.append_event(fixture["root"], {
                "event": "link", "id": fixture["task_id"],
                "updated_at": "2026-07-12T00:00:01+09:00", "links": [],
            })
        elif operation == "scan":
            task_index.scan_artifacts(fixture["root"])
        elif operation == "link":
            task_index.link_item(
                fixture["root"], fixture["task_id"],
                [{"rel": "related_to", "id": fixture["pack_id"]}],
            )
        else:
            task_index.rebuild_markdown(fixture["root"])
    assert fixture["index"].read_bytes() == index_before
    assert index_md.read_bytes() == view_before


def test_receipt_and_manifest_line_hash_tamper_rejected(tmp_path: Path) -> None:
    fixture = make_workspace(tmp_path)
    _plan, receipt_path, _result = apply_fixture(fixture, tmp_path)
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["active_task_count"] = 2
    write_json(receipt_path, receipt)
    with pytest.raises(migration.MigrationError, match="receipt digest mismatch"):
        migration.load_sealed_events_if_present(fixture["root"])


def test_reapply_same_plan_is_idempotent(tmp_path: Path) -> None:
    fixture = make_workspace(tmp_path)
    plan_path = tmp_path / "plan.json"
    plan = build_fixture_plan(fixture, plan_path)
    first = migration.apply_plan(fixture["root"], plan_path, sha(plan_path.read_bytes()), sha(fixture["prefix"]))
    after = fixture["index"].read_bytes()
    second = migration.apply_plan(fixture["root"], plan_path, sha(plan_path.read_bytes()), sha(fixture["prefix"]))
    assert first["idempotent"] is False
    assert second["idempotent"] is True
    assert fixture["index"].read_bytes() == after
    assert (fixture["root"] / plan["receipt_ref"]).is_file()


def test_concurrent_apply_serializes_and_only_one_commits(tmp_path: Path) -> None:
    fixture = make_workspace(tmp_path)
    plan_path = tmp_path / "plan.json"
    build_fixture_plan(fixture, plan_path)

    def run() -> dict[str, Any]:
        return migration.apply_plan(fixture["root"], plan_path, sha(plan_path.read_bytes()), sha(fixture["prefix"]))

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: run(), range(2)))
    assert sorted(result["idempotent"] for result in results) == [False, True]
    assert migration.load_sealed_events_if_present(fixture["root"]) is not None


def test_migration_lock_excludes_standard_writer_process(tmp_path: Path) -> None:
    fixture = make_workspace(tmp_path)
    apply_fixture(fixture, tmp_path)
    command = [
        sys.executable, str(INDEX_PATH), "--root", str(fixture["root"]), "link",
        "--source-id", fixture["task_id"], "--link", f"related_to:{fixture['pack_id']}",
    ]
    environment = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    with migration._index_lock(fixture["root"]):
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=environment)
        with pytest.raises(subprocess.TimeoutExpired):
            process.communicate(timeout=0.2)
    stdout, stderr = process.communicate(timeout=10)
    assert process.returncode == 0, stderr
    assert json.loads(stdout)["id"] == fixture["task_id"]


@pytest.mark.parametrize(
    "crash_point",
    [
        "after_prepare", "after_partial_suffix", "after_suffix", "after_receipt",
        "after_receipt_before_marker", "after_anchor",
        "after_completion_marker_before_render", "after_render",
    ],
)
def test_crash_recovery_forward_completes_without_prefix_rewrite(tmp_path: Path, crash_point: str, monkeypatch: pytest.MonkeyPatch) -> None:
    fixture = make_workspace(tmp_path)
    plan_path = tmp_path / "plan.json"
    plan = build_fixture_plan(fixture, plan_path)
    monkeypatch.setenv("TASK_STATE_MIGRATION_CRASH_AT", crash_point)
    with pytest.raises(RuntimeError, match="injected crash"):
        migration.apply_plan(fixture["root"], plan_path, sha(plan_path.read_bytes()), sha(fixture["prefix"]))
    monkeypatch.delenv("TASK_STATE_MIGRATION_CRASH_AT")
    result = migration.recover_transaction(fixture["root"], plan["migration_id"])
    assert result.get("recovery_status") == "forward_completed" or result.get("idempotent") is True
    assert fixture["index"].read_bytes().startswith(fixture["prefix"])
    assert migration.load_sealed_events_if_present(fixture["root"]) is not None
    journal = json.loads((fixture["root"] / plan["journal_ref"]).read_text(encoding="utf-8"))
    assert journal["state"] == "committed"
    assert (fixture["root"] / ".task" / "index.md").is_file()


def test_lock_symlink_is_rejected(tmp_path: Path) -> None:
    fixture = make_workspace(tmp_path)
    plan_path = tmp_path / "plan.json"
    build_fixture_plan(fixture, plan_path)
    target = tmp_path / "outside-lock"
    target.write_text("", encoding="utf-8")
    lock = fixture["root"] / ".task" / "index.lock"
    lock.symlink_to(target)
    with pytest.raises(migration.MigrationError, match="non-symlink"):
        migration.apply_plan(fixture["root"], plan_path, sha(plan_path.read_bytes()), sha(fixture["prefix"]))


def test_seal_less_malformed_prefix_still_fails_all_mutation_readers(tmp_path: Path) -> None:
    fixture = make_workspace(tmp_path)
    with pytest.raises(ValueError):
        task_index.load_events(fixture["root"])
    with pytest.raises(ValueError):
        task_index.append_event(fixture["root"], {
            "event": "link", "id": fixture["task_id"], "updated_at": "2026-07-12T00:00:00+09:00", "links": []
        })


def test_cli_help_and_inspect(tmp_path: Path) -> None:
    fixture = make_workspace(tmp_path)
    environment = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    help_result = subprocess.run([sys.executable, str(MIGRATION_PATH), "migrate", "--help"], capture_output=True, text=True, env=environment, check=False)
    inspect_result = subprocess.run([sys.executable, str(MIGRATION_PATH), "--root", str(fixture["root"]), "inspect"], capture_output=True, text=True, env=environment, check=False)
    assert help_result.returncode == 0
    assert inspect_result.returncode == 0
    assert json.loads(inspect_result.stdout)["mutation_performed"] is False
