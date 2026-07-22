from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from manage_task_state_index.state.selected_successor import (
    MAX_SELECTED_SUCCESSOR_TASK_BYTES,
    MAX_SELECTION_DECISION_BYTES,
    prepare_selected_successor,
)
from orchestrate_task_cycle.selected_successor import (
    MAX_BUNDLE_BYTES,
    prepare_selected_successor_bundle,
)
from orchestrate_task_cycle.selected_successor_authority import (
    prepare_selected_successor_authority,
)
from orchestrate_task_cycle.selected_successor_index import (
    MAX_PREPARE_INDEX_BYTES,
    load_prepare_index,
    prepare_input_identity,
    write_prepare_index,
)
from selected_successor_authority_support import AT, SKILLS_ROOT
from test_selected_successor_authority_preparation import _prepared


def _tree_state(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file() and not path.is_symlink()
    }


def _write_binding(root: Path, name: str, payload: bytes) -> dict[str, str]:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return {
        "ref": path.relative_to(root).as_posix(),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


def _prepare_index_path(root: Path, input_sha256: str) -> Path:
    return (
        root
        / ".task/selection_publication/successor_prepare_indexes/sha256"
        / f"{input_sha256}.json"
    )


def _prepare_with_bundle(
    root: Path,
    bundle: dict[str, str],
    inputs: dict[str, object],
) -> None:
    prepare_selected_successor_authority(
        root,
        bundle_binding=bundle,
        request_context_binding=inputs["request_context"],
        evaluation_context_binding=inputs["evaluation_context"],
        grants=inputs["grants"],
        at=AT,
        skills_root=SKILLS_ROOT,
    )


def test_authority_prepare_rejects_bundle_symlink_alias_without_effect(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    prepared, _bundle, inputs = _prepared(tmp_path, capsys)
    target = tmp_path / prepared["bundle"]["ref"]
    alias = tmp_path / ".task/selection_publication/bundle-alias.json"
    alias.symlink_to(target)
    binding = {
        "ref": alias.relative_to(tmp_path).as_posix(),
        "sha256": prepared["bundle"]["sha256"],
    }
    before = _tree_state(tmp_path)

    with pytest.raises(ValueError, match="cannot traverse a symlink"):
        _prepare_with_bundle(tmp_path, binding, inputs)

    assert _tree_state(tmp_path) == before
    assert not (tmp_path / ".task/authorization/operation_compilations").exists()


def test_authority_prepare_rejects_oversized_bundle_without_read_or_effect(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    prepared, _bundle, inputs = _prepared(tmp_path, capsys)
    path = tmp_path / prepared["bundle"]["ref"]
    path.write_bytes(b"{" + b" " * MAX_BUNDLE_BYTES + b"}")
    binding = {
        "ref": prepared["bundle"]["ref"],
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }
    before = _tree_state(tmp_path)

    with pytest.raises(ValueError, match="artifact size limit"):
        _prepare_with_bundle(tmp_path, binding, inputs)

    assert _tree_state(tmp_path) == before
    assert not (tmp_path / ".task/authorization/operation_compilations").exists()


@pytest.mark.parametrize(
    ("oversized_input", "limit"),
    (
        ("decision", MAX_SELECTION_DECISION_BYTES),
        ("task", MAX_SELECTED_SUCCESSOR_TASK_BYTES),
    ),
)
def test_task_state_successor_inputs_are_bounded_before_plan_publication(
    tmp_path: Path, oversized_input: str, limit: int
) -> None:
    decision_payload = b"{}\n"
    task_payload = b"# Candidate\n\n- Task ID: `task-next`\n"
    if oversized_input == "decision":
        decision_payload = b"x" * (limit + 1)
    else:
        task_payload = b"x" * (limit + 1)
    decision = _write_binding(tmp_path, "decision.json", decision_payload)
    task = _write_binding(tmp_path, "candidate.md", task_payload)

    with pytest.raises(ValueError, match=rf"exceeds {limit // 1024} KiB limit"):
        prepare_selected_successor(
            tmp_path,
            source_decision=decision,
            task_source=task,
            at=AT,
        )

    assert not (tmp_path / ".task").exists()


@pytest.mark.parametrize(
    ("oversized_input", "limit"),
    (
        ("decision", MAX_SELECTION_DECISION_BYTES),
        ("task", MAX_SELECTED_SUCCESSOR_TASK_BYTES),
    ),
)
def test_bundle_prepare_rejects_oversized_inputs_before_any_owner_write(
    tmp_path: Path, oversized_input: str, limit: int
) -> None:
    decision_payload = b"{}\n"
    task_payload = b"# Candidate\n\n- Task ID: `task-next`\n"
    if oversized_input == "decision":
        decision_payload = b"x" * (limit + 1)
    else:
        task_payload = b"x" * (limit + 1)
    decision = _write_binding(tmp_path, "decision.json", decision_payload)
    task = _write_binding(tmp_path, "candidate.md", task_payload)

    with pytest.raises(ValueError, match="artifact size limit"):
        prepare_selected_successor_bundle(
            tmp_path,
            source_decision=decision,
            task_source=task,
            at=AT,
        )

    assert not (tmp_path / ".task").exists()


def test_prepare_index_read_rejects_oversized_leaf_at_64_kib(
    tmp_path: Path,
) -> None:
    decision = _write_binding(tmp_path, "decision.json", b"{}\n")
    task = _write_binding(
        tmp_path, "candidate.md", b"# Candidate\n\n- Task ID: `task-next`\n"
    )
    _identity, input_sha256 = prepare_input_identity(decision, task, AT)
    index_path = _prepare_index_path(tmp_path, input_sha256)
    index_path.parent.mkdir(parents=True)
    index_path.write_bytes(b"x" * (MAX_PREPARE_INDEX_BYTES + 1))
    before = _tree_state(tmp_path)

    with pytest.raises(ValueError, match="exceeds the 64 KiB limit"):
        load_prepare_index(tmp_path, decision, task, AT)

    assert _tree_state(tmp_path) == before


def test_prepare_index_write_conflict_does_not_scan_or_replace_oversized_leaf(
    tmp_path: Path,
) -> None:
    decision = _write_binding(tmp_path, "decision.json", b"{}\n")
    task = _write_binding(
        tmp_path, "candidate.md", b"# Candidate\n\n- Task ID: `task-next`\n"
    )
    bundle = _write_binding(tmp_path, "bundle.json", b"{}\n")
    _identity, input_sha256 = prepare_input_identity(decision, task, AT)
    index_path = _prepare_index_path(tmp_path, input_sha256)
    index_path.parent.mkdir(parents=True)
    oversized = b"x" * (MAX_PREPARE_INDEX_BYTES + 1)
    index_path.write_bytes(oversized)
    before = _tree_state(tmp_path)

    with pytest.raises(ValueError, match="conflicts with immutable"):
        write_prepare_index(tmp_path, decision, task, AT, bundle)

    assert _tree_state(tmp_path) == before
