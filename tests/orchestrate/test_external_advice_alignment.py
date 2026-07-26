from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from manage_external_advice import rendering
from orchestrate_task_cycle.collect_cycle_context import collect_external_advice
from orchestrate_task_cycle.model_context import project_model_context


def _packet(
    paths: list[Any],
    *,
    incomplete: list[str] | None = None,
) -> dict[str, Any]:
    items = [
        {
            "advice_id": f"advice-{index}",
            "path": path,
            "source_digest": f"{index + 1:064x}",
            "content_sha256": f"{index + 101:064x}",
            "fields": {
                "fidelity_status": "ok",
                "raw_direct_reference_required": False,
                "directives": [],
            },
        }
        for index, path in enumerate(paths)
    ]
    return {
        "used_advice": items,
        "not_goal_truth": True,
        "execution_plan_eligible": False,
        "normalized_packet_use": "direction_evidence_only",
        "incomplete_normalization_advice_ids": incomplete or [],
        "canonical_clause_ids": [],
        "actionable_clause_ids": [],
        "source_digests": {},
        "clause_source_digests": {},
        "duplicate_actionable_clause_ids": [],
        "advice_packet_digest": "f" * 64,
    }


def _install_packet(
    root: Path,
    monkeypatch: pytest.MonkeyPatch,
    packet: dict[str, Any],
) -> None:
    index = root / ".agent_advice" / "index.jsonl"
    index.parent.mkdir(parents=True, exist_ok=True)
    index.write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr(rendering, "advice_packet", lambda _root: packet)


def _write_active(root: Path, name: str, body: str | None = None) -> Path:
    path = root / ".agent_advice" / "active" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        body or "# Canonical Advice\n\n- status: active\n",
        encoding="utf-8",
    )
    return path


def _project(root: Path, advice: dict[str, Any], max_paths: int = 10) -> dict[str, Any]:
    return project_model_context(
        {"workspace": str(root), "external_advice": advice},
        max_paths=max_paths,
        collect_git_worktree_identity=False,
    )


def test_registry_packet_owns_active_identity_and_excludes_pointer_and_journal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    canonical = ".agent_advice/active/canonical.md"
    _write_active(
        tmp_path,
        "canonical.md",
        "# Canonical Advice\n\n- status: `active`\n\nSECRET_BODY_MUST_NOT_SURVIVE\n",
    )
    pointer = _write_active(
        tmp_path,
        "compatibility-pointer.md",
        "# Compatibility Pointer\n\n"
        "- status: `deferred`\n"
        "- not_active_record: `true`\n"
        "- canonical_normalized_path: `.agent_advice/deferred/old.md`\n",
    )
    snapshot = (
        tmp_path
        / ".agent_advice"
        / "journal"
        / "intake"
        / "source_snapshots"
        / "source.md"
    )
    snapshot.parent.mkdir(parents=True)
    snapshot.write_text(
        "# Intake Source\n\n- status: pending_intake\n\nJOURNAL_BODY\n",
        encoding="utf-8",
    )
    _install_packet(tmp_path, monkeypatch, _packet([canonical]))

    advice = collect_external_advice(tmp_path, 20, max_paths=5)
    alignment = advice["registry_filesystem_alignment"]

    assert advice["active_count"] == 1
    assert advice["registry_active_count"] == 1
    assert advice["filesystem_active_count"] == 1
    assert [item["path"] for item in advice["active_files"]] == [canonical]
    assert advice["status_counts"] == {"active": 1, "deferred": 1, "journal": 1}
    assert alignment["status"] == "aligned"
    assert alignment["ignored_nonactive_count"] == 1
    assert alignment["ignored_nonactive_paths"] == [
        pointer.relative_to(tmp_path).as_posix()
    ]

    model = _project(tmp_path, advice)
    assert model["projection_status"] == "ready"
    assert model["advice"]["status"] == "available"
    assert model["advice"]["active_count"] == 1
    assert model["advice"]["item_count"] == 1
    encoded = json.dumps(model, ensure_ascii=False, sort_keys=True)
    assert "SECRET_BODY_MUST_NOT_SURVIVE" not in encoded
    assert "JOURNAL_BODY" not in encoded


def test_journal_snapshot_without_registry_is_not_active_advice(
    tmp_path: Path,
) -> None:
    snapshot = tmp_path / ".agent_advice" / "journal" / "source.md"
    snapshot.parent.mkdir(parents=True)
    snapshot.write_text("# Source\n\n- status: pending_intake\n", encoding="utf-8")

    advice = collect_external_advice(tmp_path, 10)
    model = _project(tmp_path, advice)

    assert advice["active_count"] == 0
    assert advice["filesystem_active_count"] == 0
    assert advice["normalized_packet_status"] == "not_applicable"
    assert advice["registry_filesystem_alignment"]["status"] == "not_applicable"
    assert advice["status_counts"] == {"journal": 1}
    assert model["projection_status"] == "ready"
    assert model["advice"]["status"] == "not_applicable"


def test_normalization_failure_blocks_even_when_active_count_is_zero(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    index = tmp_path / ".agent_advice" / "index.jsonl"
    index.parent.mkdir(parents=True)
    index.write_text("{invalid}\n", encoding="utf-8")

    def fail(_root: Path) -> dict[str, Any]:
        raise ValueError("invalid registry")

    monkeypatch.setattr(rendering, "advice_packet", fail)
    advice = collect_external_advice(tmp_path, 10)
    model = _project(tmp_path, advice)

    assert advice["active_count"] == 0
    assert advice["normalized_packet_status"] == "unavailable"
    assert advice["normalization_error_class"] == "ValueError"
    assert advice["registry_filesystem_alignment"]["status"] == "unavailable"
    assert model["advice"]["status"] == "unavailable"
    assert model["projection_status"] == "block"
    assert model["stop_reason"] == "awaiting_advice_normalization"


@pytest.mark.parametrize(
    ("registry_paths", "filesystem_names", "missing", "unexpected"),
    [
        ([".agent_advice/active/a.md"], [], 1, 0),
        (
            [".agent_advice/active/a.md"],
            ["a.md", "orphan.md"],
            0,
            1,
        ),
        ([".agent_advice/active/a.md"], ["b.md"], 1, 1),
    ],
)
def test_exact_path_set_mismatch_blocks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    registry_paths: list[str],
    filesystem_names: list[str],
    missing: int,
    unexpected: int,
) -> None:
    for name in filesystem_names:
        _write_active(tmp_path, name)
    _install_packet(tmp_path, monkeypatch, _packet(registry_paths))

    advice = collect_external_advice(tmp_path, 10)
    alignment = advice["registry_filesystem_alignment"]
    model = _project(tmp_path, advice)

    assert alignment["status"] == "mismatch"
    assert alignment["missing_count"] == missing
    assert alignment["unexpected_count"] == unexpected
    assert model["advice"]["status"] == "registry_filesystem_mismatch"
    assert model["projection_status"] == "block"


def test_invalid_duplicate_registry_paths_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    canonical = ".agent_advice/active/a.md"
    _write_active(tmp_path, "a.md")
    _install_packet(
        tmp_path,
        monkeypatch,
        _packet([canonical, canonical, "/outside/private.md"]),
    )

    advice = collect_external_advice(tmp_path, 10)
    alignment = advice["registry_filesystem_alignment"]
    model = _project(tmp_path, advice)

    assert advice["active_count"] == 3
    assert alignment["status"] == "mismatch"
    assert alignment["invalid_registry_path_count"] == 1
    assert alignment["duplicate_registry_path_count"] == 1
    assert "/outside/private.md" not in json.dumps(alignment)
    assert model["projection_status"] == "block"


def test_alignment_uses_full_sets_but_bounds_diagnostic_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry_paths = [f".agent_advice/active/missing-{index}.md" for index in range(5)]
    for index in range(5):
        _write_active(tmp_path, f"orphan-{index}.md")
    _install_packet(tmp_path, monkeypatch, _packet(registry_paths))

    advice = collect_external_advice(tmp_path, 10, max_paths=2)
    alignment = advice["registry_filesystem_alignment"]
    model = _project(tmp_path, advice, max_paths=1)

    assert alignment["missing_count"] == 5
    assert alignment["unexpected_count"] == 5
    assert len(alignment["missing_paths"]) == 2
    assert len(alignment["unexpected_paths"]) == 2
    assert alignment["paths_truncated"] is True
    assert len(model["advice"]["registry_filesystem_alignment"]["missing_paths"]) == 1
    assert model["advice"]["registry_filesystem_alignment"]["paths_truncated"] is True
    assert model["projection_status"] == "block"


def test_conflicting_nonactive_marker_blocks_even_when_path_sets_match(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    canonical = ".agent_advice/active/a.md"
    _write_active(
        tmp_path,
        "a.md",
        "# Advice\n\n- status: active\n- not_active_record: true\n",
    )
    _install_packet(tmp_path, monkeypatch, _packet([canonical]))

    advice = collect_external_advice(tmp_path, 10)
    alignment = advice["registry_filesystem_alignment"]

    assert alignment["missing_count"] == 0
    assert alignment["unexpected_count"] == 0
    assert alignment["active_metadata_conflict_count"] == 1
    assert alignment["status"] == "mismatch"
    assert _project(tmp_path, advice)["projection_status"] == "block"


def test_zero_active_count_is_not_replaced_by_packet_item_count() -> None:
    advice = {
        "active_count": 0,
        "normalized_packet_status": "available",
        "normalized_packet": _packet([".agent_advice/active/a.md"]),
    }

    model = _project(Path("/workspace"), advice)

    assert model["advice"]["active_count"] == 0
    assert model["advice"]["item_count"] == 1
    assert model["advice"]["status"] == "registry_filesystem_mismatch"
    assert model["projection_status"] == "block"


def test_incomplete_normalization_remains_a_distinct_block(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    canonical = ".agent_advice/active/a.md"
    _write_active(tmp_path, "a.md")
    _install_packet(
        tmp_path,
        monkeypatch,
        _packet([canonical], incomplete=["advice-0"]),
    )

    model = _project(tmp_path, collect_external_advice(tmp_path, 10))

    assert model["advice"]["status"] == "incomplete"
    assert model["advice"]["registry_filesystem_alignment"]["status"] == "aligned"
    assert model["projection_status"] == "block"
