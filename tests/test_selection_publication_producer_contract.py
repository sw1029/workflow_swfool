from __future__ import annotations

import ast
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event, Lock

import pytest

import orchestrate_task_cycle.selection_publication_producer_manifest as manifest
from orchestrate_task_cycle.selection_publication_gc_write import (
    write_once_relative,
)
from orchestrate_task_cycle.selection_publication_producer_capability import (
    _SELECTION_PUBLICATION_GC_EXCLUSIVE_CAPABILITY,
    _SELECTION_PUBLICATION_PRODUCER_CAPABILITY,
)
from orchestrate_task_cycle.selection_publication_producer_lint import (
    ALLOWED_IMPORTERS,
    lint_registered_producers,
)
from orchestrate_task_cycle.selection_publication_producer_manifest import (
    registered_producer_inventory,
    valid_producer_inventory,
)
from orchestrate_task_cycle.selection_publication_reference_barrier import (
    reference_gc_barrier,
)
from orchestrate_task_cycle.selection_publication_store import (
    _atomic_write,
    _publication_lock,
    _write_once,
    _write_once_with_status,
)


def _store(root: Path) -> Path:
    path = root / ".task/selection_publication"
    path.mkdir(parents=True)
    return path


def test_gc_write_rejects_missing_or_unproved_capability(
    tmp_path: Path,
) -> None:
    _store(tmp_path)
    relative = ".task/selection_publication/gc/test.json"
    with pytest.raises(ValueError, match="registered producer capability"):
        write_once_relative(
            tmp_path,
            relative,
            b"{}\n",
            "test artifact",
            producer_capability=object(),
        )
    with pytest.raises(ValueError, match="held exclusive reference barrier"):
        write_once_relative(
            tmp_path,
            relative,
            b"{}\n",
            "test artifact",
            producer_capability=(
                _SELECTION_PUBLICATION_GC_EXCLUSIVE_CAPABILITY
            ),
        )
    assert not (tmp_path / relative).exists()


def test_gc_write_requires_exclusive_token_under_exclusive_barrier(
    tmp_path: Path,
) -> None:
    _store(tmp_path)
    generic_ref = ".task/selection_publication/gc/generic.json"
    exclusive_ref = ".task/selection_publication/gc/exclusive.json"
    with reference_gc_barrier(tmp_path):
        with pytest.raises(ValueError, match="GC-exclusive capability"):
            write_once_relative(
                tmp_path,
                generic_ref,
                b"generic\n",
                "generic artifact",
                producer_capability=(
                    _SELECTION_PUBLICATION_PRODUCER_CAPABILITY
                ),
            )
        digest, created = write_once_relative(
            tmp_path,
            exclusive_ref,
            b"exclusive\n",
            "exclusive artifact",
            producer_capability=(
                _SELECTION_PUBLICATION_GC_EXCLUSIVE_CAPABILITY
            ),
        )
    assert len(digest) == 64
    assert created is True
    assert (tmp_path / exclusive_ref).read_bytes() == b"exclusive\n"
    assert not (tmp_path / generic_ref).exists()


def test_publication_lock_requires_matching_held_barrier_proof(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="held shared reference barrier"):
        with _publication_lock(
            tmp_path,
            producer_capability=_SELECTION_PUBLICATION_PRODUCER_CAPABILITY,
        ):
            pass
    assert not (tmp_path / ".task").exists()

    with reference_gc_barrier(tmp_path):
        with pytest.raises(ValueError, match="held shared reference barrier"):
            with _publication_lock(
                tmp_path,
                producer_capability=(
                    _SELECTION_PUBLICATION_PRODUCER_CAPABILITY
                ),
            ):
                pass
        assert not (tmp_path / ".task").exists()
        with _publication_lock(
            tmp_path,
            producer_capability=(
                _SELECTION_PUBLICATION_GC_EXCLUSIVE_CAPABILITY
            ),
        ):
            pass
    assert (
        tmp_path / ".task/selection_publication/publication.lock"
    ).is_file()


def test_store_capability_gate_classifies_before_symlink_resolution(
    tmp_path: Path,
) -> None:
    external = tmp_path / "external"
    external.mkdir()
    task_root = tmp_path / ".task"
    task_root.mkdir()
    (task_root / "selection_publication").symlink_to(
        external, target_is_directory=True
    )
    target = task_root / "selection_publication/state.json"
    with pytest.raises(ValueError, match="registered producer capability"):
        _atomic_write(target, b"{}\n")
    with pytest.raises(ValueError, match="store root"):
        _atomic_write(
            target,
            b"{}\n",
            producer_capability=_SELECTION_PUBLICATION_PRODUCER_CAPABILITY,
        )
    assert not (external / "state.json").exists()


def test_write_once_never_replaces_a_concurrent_immutable_winner(
    tmp_path: Path,
) -> None:
    target = (
        tmp_path
        / ".task/selection_publication/races/immutable-result.json"
    )

    def publish(payload: bytes) -> tuple[str, str]:
        try:
            digest = _write_once(
                target,
                payload,
                "immutable race result",
                producer_capability=(
                    _SELECTION_PUBLICATION_PRODUCER_CAPABILITY
                ),
            )
            return "published", digest
        except ValueError as exc:
            return "conflict", str(exc)

    payloads = (b'{"winner":1}\n', b'{"winner":2}\n')
    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(publish, payloads))
    assert sorted(status for status, _detail in outcomes) == [
        "conflict",
        "published",
    ]
    assert target.read_bytes() in payloads
    assert list(target.parent.glob(f".{target.name}.*.tmp")) == []


def test_write_once_status_reports_only_the_actual_link_winner(
    tmp_path: Path,
) -> None:
    target = tmp_path / ".task/selection_publication/races/status.json"
    payload = b'{"same":true}\n'

    def publish(_index: int) -> tuple[str, bool]:
        return _write_once_with_status(
            target,
            payload,
            "immutable status race",
            producer_capability=_SELECTION_PUBLICATION_PRODUCER_CAPABILITY,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(publish, range(2)))

    assert len({digest for digest, _created in outcomes}) == 1
    assert sorted(created for _digest, created in outcomes) == [False, True]
    assert target.read_bytes() == payload


def test_exact_replay_republishes_if_gc_deletes_after_preflight(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import orchestrate_task_cycle.selection_publication_store_immutable as immutable

    target = tmp_path / ".task/selection_publication/races/exact-replay.json"
    target.parent.mkdir(parents=True)
    payload = b'{"exact":true}\n'
    target.write_bytes(payload)
    preflight_complete = Event()
    resume = Event()
    call_lock = Lock()
    calls = 0
    original = immutable._verify_exact

    def pause_after_first_exact(*args: object, **kwargs: object) -> str:
        nonlocal calls
        result = original(*args, **kwargs)
        with call_lock:
            calls += 1
            first = calls == 1
        if first:
            preflight_complete.set()
            assert resume.wait(timeout=5)
        return result

    monkeypatch.setattr(immutable, "_verify_exact", pause_after_first_exact)
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(
            _write_once,
            target,
            payload,
            "exact replay race",
            producer_capability=_SELECTION_PUBLICATION_PRODUCER_CAPABILITY,
        )
        assert preflight_complete.wait(timeout=5)
        with reference_gc_barrier(tmp_path):
            target.unlink()
        resume.set()
        digest = future.result(timeout=5)

    assert len(digest) == 64
    assert target.read_bytes() == payload


def test_mutation_reporting_producers_use_actual_write_status_api() -> None:
    source_root = Path(manifest.__file__).parent
    reporters = (
        "selected_successor.py",
        "selected_successor_authority_artifacts.py",
        "selected_successor_authority_context_compiler.py",
        "selected_successor_execution_lease.py",
        "selected_successor_index.py",
        "selection_decision_receipt_cli.py",
        "selection_publication_payload.py",
    )
    for filename in reporters:
        tree = ast.parse((source_root / filename).read_bytes(), filename=filename)
        called = {
            node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        assert "_write_once_with_status" in called
        assert "_write_once" not in called


def test_lint_uses_exact_symbol_allowlist_for_registered_module(
    tmp_path: Path,
) -> None:
    source = tmp_path / "selection_publication_state.py"
    source.write_text(
        "from .selection_publication_store import _write_once\n",
        encoding="utf-8",
    )
    registered = {
        filename
        for filenames in ALLOWED_IMPORTERS.values()
        for filename in filenames
    }
    with pytest.raises(ValueError, match="selection_publication_store._write_once"):
        lint_registered_producers(tmp_path, registered)


def test_lint_recursively_rejects_nested_package_bypass(
    tmp_path: Path,
) -> None:
    nested = tmp_path / "stage"
    nested.mkdir()
    (nested / "rogue.py").write_text(
        "from ..selection_publication_store import _atomic_write_unlocked\n",
        encoding="utf-8",
    )
    registered = {
        filename
        for filenames in ALLOWED_IMPORTERS.values()
        for filename in filenames
    }
    with pytest.raises(ValueError, match="stage/rogue.py"):
        lint_registered_producers(tmp_path, registered)


def test_registered_producer_manifest_binds_entrypoints_and_lint() -> None:
    inventory = registered_producer_inventory()
    assert valid_producer_inventory(inventory)
    lease_writer = next(
        row
        for row in inventory["producers"]
        if row["producer_id"] == "selected-successor-execution-lease"
    )
    assert lease_writer["source_file"] == "selected_successor_execution_lease.py"
    assert lease_writer["entrypoints"] == [
        "authority_gate",
        "publish_execution_lease",
    ]
    assert (
        inventory["contract_lint"]["policy"]
        == "protected_mutation_imports_require_exact_symbol_allowlist"
    )
    assert all(row["entrypoints"] for row in inventory["producers"])
    assert inventory["contract_lint"]["scanned_file_count"] > len(
        inventory["producers"]
    )


def test_registered_producer_manifest_rejects_missing_entrypoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    invalid = {
        **manifest.PRODUCER_SPECS[0],
        "producer_id": "invalid-missing-entrypoint",
        "entrypoints": ["entrypoint_that_does_not_exist"],
    }
    monkeypatch.setattr(
        manifest, "PRODUCER_SPECS", (*manifest.PRODUCER_SPECS, invalid)
    )
    with pytest.raises(ValueError, match="entrypoint is absent"):
        manifest.registered_producer_inventory()
