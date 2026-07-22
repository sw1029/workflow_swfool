from __future__ import annotations

import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from pathlib import Path

import pytest

from manage_task_state_index.index import audit_index
from manage_task_state_index.state import events as task_events
from manage_task_state_index.state import storage as task_storage
from manage_task_state_index.state.storage import index_lock
from orchestrate_task_cycle.dashboard.io import (
    load_current as load_dashboard_current,
    load_events as load_dashboard_events,
)
from orchestrate_task_cycle.ledger import repository as ledger_repository
from orchestrate_task_cycle.ledger import support as ledger_support
from orchestrate_task_cycle.ledger.support import ledger_lock


def _tree_image(root: Path) -> list[tuple[str, str, bytes]]:
    image: list[tuple[str, str, bytes]] = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            image.append((relative, "symlink", os.readlink(path).encode()))
        elif path.is_dir():
            image.append((relative, "directory", b""))
        else:
            image.append((relative, "file", path.read_bytes()))
    return image


def _ledger_event(cycle_id: str, *, versioned: bool) -> dict[str, object]:
    event: dict[str, object] = {
        "cycle_id": cycle_id,
        "event_id": f"{cycle_id}-context",
        "step": "context",
        "status": "complete",
    }
    if versioned:
        event["format_version"] = 1
    return event


def _write_lockless_cycle(root: Path, cycle_id: str, *, versioned: bool) -> Path:
    directory = root / ".task" / "cycle" / cycle_id
    directory.mkdir(parents=True)
    event = _ledger_event(cycle_id, versioned=versioned)
    (directory / "stage.jsonl").write_text(
        json.dumps(event, sort_keys=True) + "\n", encoding="utf-8"
    )
    if versioned:
        (directory / "current_stage.json").write_text(
            json.dumps(
                {
                    "format_version": 1,
                    "cycle_id": cycle_id,
                    "status": "complete",
                    "latest_event": event,
                    "steps": {"context": event},
                    "malformed_event_count": 0,
                    "malformed_events": [],
                    "event_count": 1,
                },
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
    return directory


@pytest.mark.parametrize("versioned", [False, True])
def test_lockless_ledger_and_dashboard_reads_preserve_file_tree(
    tmp_path: Path, versioned: bool
) -> None:
    cycle_id = "cycle-current" if versioned else "cycle-legacy"
    directory = _write_lockless_cycle(tmp_path, cycle_id, versioned=versioned)
    before = _tree_image(tmp_path)

    raw = ledger_repository.read_events_raw(tmp_path, cycle_id)
    hydrated = ledger_repository.read_events(tmp_path, cycle_id)
    dashboard = load_dashboard_events(directory / "stage.jsonl")
    current = ledger_repository.read_current_expanded(tmp_path, cycle_id)
    dashboard_current, current_status = load_dashboard_current(
        directory / "current_stage.json"
    )

    assert raw == hydrated == dashboard
    assert len(raw) == 1
    assert current.get("event_count") == (1 if versioned else None)
    assert dashboard_current.get("event_count") == (1 if versioned else None)
    assert current_status == ("loaded" if versioned else "missing")
    assert not (directory / ".ledger.lock").exists()
    assert _tree_image(tmp_path) == before


def test_ledger_reader_shares_existing_writer_lock(tmp_path: Path) -> None:
    cycle_id = "cycle-shared-lock"
    directory = _write_lockless_cycle(tmp_path, cycle_id, versioned=True)
    entered = threading.Event()
    release = threading.Event()
    reader_started = threading.Event()

    def hold_writer() -> None:
        with ledger_lock(tmp_path, cycle_id, exclusive=True):
            entered.set()
            assert release.wait(5)

    def read() -> list[dict[str, object]]:
        reader_started.set()
        return ledger_repository.read_events_raw(tmp_path, cycle_id)

    with ThreadPoolExecutor(max_workers=2) as executor:
        writer = executor.submit(hold_writer)
        assert entered.wait(5)
        reader = executor.submit(read)
        assert reader_started.wait(5)
        with pytest.raises(FutureTimeout):
            reader.result(timeout=0.05)
        release.set()
        writer.result(timeout=5)
        assert len(reader.result(timeout=5)) == 1
    assert (directory / ".ledger.lock").is_file()


def test_ledger_reader_reenters_same_thread_writer_without_shared_flock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cycle_id = "cycle-writer-reentry"
    _write_lockless_cycle(tmp_path, cycle_id, versioned=True)
    real_flock = ledger_support.fcntl.flock

    with ledger_lock(tmp_path, cycle_id, exclusive=True):

        def reject_shared(descriptor: int, operation: int) -> None:
            if operation == ledger_support.fcntl.LOCK_SH:
                pytest.fail("same-thread ledger reader tried to reacquire LOCK_SH")
            real_flock(descriptor, operation)

        monkeypatch.setattr(ledger_support.fcntl, "flock", reject_shared)
        assert len(ledger_repository.read_events_raw(tmp_path, cycle_id)) == 1


def test_generic_shared_ledger_lock_does_not_create_state(tmp_path: Path) -> None:
    with ledger_lock(tmp_path, "cycle-missing", exclusive=False):
        pass
    assert not (tmp_path / ".task").exists()


def test_lockless_ledger_race_fails_closed_without_creating_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cycle_id = "cycle-racing"
    directory = _write_lockless_cycle(tmp_path, cycle_id, versioned=False)
    ledger = directory / "stage.jsonl"
    original = ledger_repository.read_events_unlocked

    def racing_read(root: Path, selected_cycle_id: str) -> list[dict[str, object]]:
        result = original(root, selected_cycle_id)
        with ledger.open("ab") as handle:
            handle.write(b"\n")
        return result

    monkeypatch.setattr(ledger_repository, "read_events_unlocked", racing_read)
    with pytest.raises(ValueError, match="changed during read-only snapshot"):
        ledger_repository.read_events_raw(tmp_path, cycle_id)
    assert not (directory / ".ledger.lock").exists()


def _write_lockless_index(root: Path) -> Path:
    task = root / ".task"
    task.mkdir()
    path = task / "index.jsonl"
    path.write_text(
        json.dumps(
            {
                "id": "task-legacy",
                "updated_at": "2026-01-01T00:00:00Z",
                "type": "task",
                "status": "active",
                "path": "task.md",
                "title": "Legacy task",
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def test_fresh_and_legacy_task_index_reads_do_not_create_state(tmp_path: Path) -> None:
    before = _tree_image(tmp_path)
    assert task_events.load_events_read_only(tmp_path) == ([], None)
    assert audit_index(tmp_path)["event_count"] == 0
    assert _tree_image(tmp_path) == before
    assert not (tmp_path / ".task").exists()

    index = _write_lockless_index(tmp_path)
    before = _tree_image(tmp_path)
    events, digest = task_events.load_events_read_only(tmp_path)
    audit = audit_index(tmp_path)
    assert len(events) == 1
    assert isinstance(digest, str) and len(digest) == 64
    assert audit["raw_row_count"] == 1
    assert not (index.parent / "index.lock").exists()
    assert _tree_image(tmp_path) == before


def test_task_index_reader_shares_existing_writer_lock(tmp_path: Path) -> None:
    _write_lockless_index(tmp_path)
    entered = threading.Event()
    release = threading.Event()
    reader_started = threading.Event()

    def hold_writer() -> None:
        with index_lock(tmp_path):
            entered.set()
            assert release.wait(5)

    def read() -> tuple[list[dict[str, object]], str | None]:
        reader_started.set()
        return task_events.load_events_read_only(tmp_path)

    with ThreadPoolExecutor(max_workers=2) as executor:
        writer = executor.submit(hold_writer)
        assert entered.wait(5)
        reader = executor.submit(read)
        assert reader_started.wait(5)
        with pytest.raises(FutureTimeout):
            reader.result(timeout=0.05)
        release.set()
        writer.result(timeout=5)
        events, _digest = reader.result(timeout=5)
    assert len(events) == 1


def test_task_index_reader_reenters_same_thread_writer_without_shared_flock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_lockless_index(tmp_path)
    assert task_storage.fcntl is not None
    real_flock = task_storage.fcntl.flock

    with index_lock(tmp_path):

        def reject_shared(descriptor: int, operation: int) -> None:
            if operation == task_storage.fcntl.LOCK_SH:
                pytest.fail("same-thread task-index reader tried to reacquire LOCK_SH")
            real_flock(descriptor, operation)

        monkeypatch.setattr(task_storage.fcntl, "flock", reject_shared)
        events, digest = task_events.load_events_read_only(tmp_path)
        assert len(events) == 1
        assert digest


def test_lockless_task_index_race_fails_closed_without_creating_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    index = _write_lockless_index(tmp_path)
    original = task_events._read_existing_events

    def racing_read(root: Path) -> list[dict[str, object]]:
        result = original(root)
        with index.open("ab") as handle:
            handle.write(b"\n")
        return result

    monkeypatch.setattr(task_events, "_read_existing_events", racing_read)
    with pytest.raises(ValueError, match="changed during read-only snapshot"):
        task_events.load_events_read_only(tmp_path)
    assert not (index.parent / "index.lock").exists()
