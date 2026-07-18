from __future__ import annotations

import os
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "manage-agent-authority" / "scripts"))

from manage_agent_authority import stable_store  # noqa: E402
from manage_agent_authority.artifact_store import snapshot_file  # noqa: E402
from manage_agent_authority.canonical import write_immutable_json  # noqa: E402
from manage_agent_authority.canonical import write_json_atomic  # noqa: E402


def test_atomic_state_write_cannot_escape_replaced_parent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / ".task/authorization/state/current_policy.json"
    target.parent.mkdir(parents=True)
    outside = tmp_path / "outside-state"
    outside.mkdir()
    detached = tmp_path / ".task/authorization/state-detached"
    swapped = False

    def swap(stage: str, path: Path) -> None:
        nonlocal swapped
        if stage == "before_replace" and path == target and not swapped:
            swapped = True
            target.parent.rename(detached)
            os.symlink(outside, target.parent)

    monkeypatch.setattr(stable_store, "_race_hook", swap)
    with pytest.raises(SystemExit, match="Authority artifact ancestor"):
        write_json_atomic(target, {"version": 1})

    assert swapped is True
    assert list(outside.iterdir()) == []
    assert not list(detached.glob(".*.tmp"))


def test_snapshot_publication_cannot_escape_replaced_target_parent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / ".agent_goal/agent_authority.md"
    source.parent.mkdir(parents=True)
    source.write_text("bounded authority policy\n", encoding="utf-8")
    snapshot_parent = tmp_path / ".task/authorization/policy_snapshots"
    detached = tmp_path / ".task/authorization/policy-snapshots-detached"
    outside = tmp_path / "outside-snapshots"
    outside.mkdir()
    swapped = False

    def swap(stage: str, path: Path) -> None:
        nonlocal swapped
        if (
            stage == "before_link"
            and path.parent == snapshot_parent
            and not swapped
        ):
            swapped = True
            snapshot_parent.rename(detached)
            os.symlink(outside, snapshot_parent)

    monkeypatch.setattr(stable_store, "_race_hook", swap)
    with pytest.raises(SystemExit, match="Authority artifact ancestor"):
        snapshot_file(tmp_path, str(source.relative_to(tmp_path)), "policy")

    assert swapped is True
    assert list(outside.iterdir()) == []
    assert not list(detached.glob("policy-*"))
    assert not list(detached.glob(".*.tmp"))


def test_snapshot_source_read_fails_closed_on_ancestor_swap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / ".agent_goal/agent_authority.md"
    source.parent.mkdir(parents=True)
    source.write_text("trusted policy bytes\n", encoding="utf-8")
    detached = tmp_path / ".agent_goal-detached"
    outside = tmp_path / "outside-source"
    outside.mkdir()
    (outside / source.name).write_text("foreign policy bytes\n", encoding="utf-8")
    swapped = False

    def swap(stage: str, path: Path) -> None:
        nonlocal swapped
        if stage == "after_read" and path == source and not swapped:
            swapped = True
            source.parent.rename(detached)
            os.symlink(outside, source.parent)

    monkeypatch.setattr(stable_store, "_race_hook", swap)
    with pytest.raises(SystemExit, match="Authority artifact ancestor"):
        snapshot_file(tmp_path, str(source.relative_to(tmp_path)), "policy")

    assert swapped is True
    snapshots = tmp_path / ".task/authorization/policy_snapshots"
    assert not snapshots.exists() or list(snapshots.iterdir()) == []


def test_immutable_replay_does_not_hide_replaced_parent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / ".task/authorization/decisions/decision-a.json"
    value = {"schema_version": 2, "artifact_kind": "test_decision"}
    write_immutable_json(target, value, "test decision")
    detached = tmp_path / ".task/authorization/decisions-detached"
    outside = tmp_path / "outside-decisions"
    outside.mkdir()
    swapped = False

    def swap(stage: str, path: Path) -> None:
        nonlocal swapped
        if stage == "after_existing_read" and path == target and not swapped:
            swapped = True
            target.parent.rename(detached)
            os.symlink(outside, target.parent)

    monkeypatch.setattr(stable_store, "_race_hook", swap)
    with pytest.raises(SystemExit, match="Conflicting test decision"):
        write_immutable_json(target, value, "test decision")

    assert swapped is True
    assert list(outside.iterdir()) == []
    assert (detached / target.name).is_file()
