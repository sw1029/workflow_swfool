from __future__ import annotations

import json
from pathlib import Path

import pytest

import orchestrate_task_cycle.selection_tick as selection_tick
import orchestrate_task_cycle.selection_tick_io as selection_tick_io
from orchestrate_task_cycle.selection_tick import build_selection_tick
from orchestrate_task_cycle.selection_tick_contract import validate_selection_tick_v2
from orchestrate_task_cycle.selection_tick_limits import (
    MAX_AUTHORITY_PACKETS,
    MAX_AUTHORITY_SCOPES,
    MAX_CALLER_WATCH_PATHS,
    MAX_CARRIED_WATCH_IDS,
    MAX_CHANGE_ENTRIES,
    MAX_PENDING_PUBLICATIONS,
    MAX_POLICY_IDS,
    MAX_WATCH_ENTRIES,
)


def _repo(root: Path) -> Path:
    (root / ".agent_goal").mkdir(parents=True, exist_ok=True)
    (root / "task.md").write_text("# Task\n", encoding="utf-8")
    (root / ".agent_goal/final_goal.md").write_text("# Goal\n", encoding="utf-8")
    return root


@pytest.mark.parametrize("store", ["adapter", "task_pack", "retirement"])
def test_discovery_never_reads_through_parent_symlinks(
    tmp_path: Path, store: str
) -> None:
    root = _repo(tmp_path)
    outside = tmp_path.parent / f"{tmp_path.name}-{store}"
    outside.mkdir()
    (outside / "artifact.json").write_text("{}", encoding="utf-8")
    if store == "adapter":
        adapter_root = root / ".codex/skills"
        adapter_root.mkdir(parents=True)
        (outside / "adapter.manifest.json").write_text("{}", encoding="utf-8")
        (adapter_root / "linked").symlink_to(outside, target_is_directory=True)
    elif store == "task_pack":
        (root / ".task").mkdir()
        (root / ".task/task_pack").symlink_to(outside, target_is_directory=True)
    else:
        retirement = root / ".task/task_pack_retirement"
        retirement.mkdir(parents=True)
        (retirement / "linked").symlink_to(outside, target_is_directory=True)

    with pytest.raises(ValueError, match="symlink watch path"):
        build_selection_tick(root)


def test_discovered_json_and_streamed_hash_are_bounded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repo(tmp_path)
    manifest = root / ".codex/skills/example/adapter.manifest.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(json.dumps({"body": "x" * 64}), encoding="utf-8")
    monkeypatch.setattr(selection_tick_io, "MAX_FILE_BYTES", 32)

    with pytest.raises(ValueError, match="exceeds 32 bytes"):
        build_selection_tick(root)

    payload = root / "growing.bin"
    payload.write_bytes(b"x" * 33)
    with pytest.raises(ValueError, match="exceeds 32 bytes"):
        selection_tick_io.sha256_and_size(payload)


@pytest.mark.parametrize(
    ("store", "constant_name"),
    [
        ("task_pack", "MAX_TASK_PACK_FILES"),
        ("task_pack_retirement", "MAX_RETIREMENT_FILES"),
    ],
)
def test_discovery_file_counts_are_bounded_before_full_materialization(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    store: str,
    constant_name: str,
) -> None:
    root = _repo(tmp_path)
    directory = root / ".task" / store
    if store == "task_pack":
        directory.mkdir(parents=True)
        for index in range(2):
            (directory / f"pack-{index}.json").write_text("{}", encoding="utf-8")
    else:
        for index in range(2):
            path = directory / f"retired-{index}" / "record.json"
            path.parent.mkdir(parents=True)
            path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(selection_tick, constant_name, 1)

    with pytest.raises(ValueError, match="count exceeds 1"):
        build_selection_tick(root)


def test_producer_rejects_caller_and_policy_cardinality_overflow(
    tmp_path: Path,
) -> None:
    root = _repo(tmp_path)
    with pytest.raises(ValueError, match="watch path count"):
        build_selection_tick(
            root,
            watch_paths=["task.md"] * (MAX_CALLER_WATCH_PATHS + 1),
        )
    with pytest.raises(ValueError, match="authority packet count"):
        build_selection_tick(root, authority_packets=[{}] * (MAX_AUTHORITY_PACKETS + 1))
    with pytest.raises(ValueError, match="count exceeds"):
        build_selection_tick(
            root,
            wake_predicates=[f"wake-{index}" for index in range(MAX_POLICY_IDS + 1)],
        )


@pytest.mark.parametrize(
    ("field", "count"),
    [
        ("watch_entries", MAX_WATCH_ENTRIES + 1),
        ("changed_watch_entries", MAX_CHANGE_ENTRIES + 1),
        ("material_changed_watch_entries", MAX_CHANGE_ENTRIES + 1),
        ("carried_forward_watch_ids", MAX_CARRIED_WATCH_IDS + 1),
        ("authority_scope_ids", MAX_AUTHORITY_SCOPES + 1),
        ("wake_predicates", MAX_POLICY_IDS + 1),
        ("watched_evidence_classes", MAX_POLICY_IDS + 1),
        ("pending_selection_publication_ids", MAX_PENDING_PUBLICATIONS + 1),
    ],
)
def test_validator_rejects_each_bounded_collection_overflow(
    tmp_path: Path, field: str, count: int
) -> None:
    packet = build_selection_tick(_repo(tmp_path))
    if field in {
        "watch_entries",
        "changed_watch_entries",
        "material_changed_watch_entries",
    }:
        packet[field] = [{}] * count
    else:
        packet[field] = [f"id-{index}" for index in range(count)]

    with pytest.raises(ValueError):
        validate_selection_tick_v2(packet)
