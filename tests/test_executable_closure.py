from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from manage_agent_authority import operation_batch as operation_batch_module
from manage_agent_authority.canonical import object_sha256, write_immutable_json
from manage_agent_authority.evaluator import effective_authority_fingerprint
from manage_task_state_index import index as task_index
from orchestrate_task_cycle import cycle_ledger
from orchestrate_task_cycle.executable_closure import (
    _topology_has_exact_allowed_decisions,
    main,
    preflight_executable_closure,
)
from orchestrate_task_cycle.selected_successor import (
    load_selected_successor_bundle,
    prepare_selected_successor_bundle,
)
from orchestrate_task_cycle.selected_successor_authority import (
    prepare_selected_successor_authority,
)
from orchestrate_task_cycle.selected_successor_authority_artifacts import load_packet
from selected_successor_authority_support import (
    AT,
    SKILLS_ROOT,
    prepare_authority_inputs,
)
from test_selection_publication_external_transaction import (
    _binding,
    _initialize_active_task,
    _selected_receipt,
)


BATCH_BINDING = {
    "ref": ".task/authorization/operation_batches/sha256/batch.json",
    "sha256": "a" * 64,
}


def _tree(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _task(
    root: Path,
    *,
    task_id: str,
    status: str,
) -> None:
    path = root / "task.md"
    path.write_text(f"# Task\n\n- Task ID: `{task_id}`\n", encoding="utf-8")
    fields = (
        {"record_class": "mutable_alias", "canonical_id": task_id}
        if status in {"complete", "completed"}
        else None
    )
    event = {
        "event": "upsert",
        "id": task_id,
        "type": "task",
        "status": status,
        "path": "task.md",
        "title": "Task",
        "content_sha256": task_index.sha256_file(path),
        "updated_at": "2026-07-24T01:00:00+09:00",
    }
    if fields is not None:
        event["fields"] = fields
    task_index.append_event(root, event)


def _unrelated_active_task(root: Path, *, task_id: str = "task-unrelated") -> None:
    path = root / "other.md"
    path.write_text(f"# Other\n\n- Task ID: `{task_id}`\n", encoding="utf-8")
    task_index.upsert_item(
        root,
        "task",
        "other.md",
        "active",
        item_id=task_id,
        replace_existing=False,
    )


def _batch(
    cycle_id: str,
    task_id: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    request = {
        "skill_id": "run-task-code-and-log",
        "skill_version": "2.0.0",
        "operation_id": "run_long",
        "operation_version": "1",
        "cycle_id": cycle_id,
        "task_id": task_id,
        "subject": {
            "kind": "task_execution",
            "ref": "task.md",
            "digest": "b" * 64,
            "revision": task_id,
        },
        "idempotency_key": f"run-{task_id}",
    }
    compilations = [{"request": request, "request_sha256": "c" * 64}]
    return {
        "schema_version": 1,
        "artifact_kind": "authority_operation_batch",
        "operation_count": 1,
    }, compilations


def _install_batch(
    monkeypatch: Any,
    *,
    cycle_id: str,
    task_id: str,
) -> None:
    batch, compilations = _batch(cycle_id, task_id)

    def load(
        _root: Path,
        binding: dict[str, str],
        *,
        skills_root: Path | None = None,
    ) -> tuple[dict[str, str], dict[str, Any], list[dict[str, Any]]]:
        assert binding == BATCH_BINDING
        assert skills_root is None
        return dict(BATCH_BINDING), batch, compilations

    monkeypatch.setattr(operation_batch_module, "load_operation_batch", load)


def _topology_fixture(
    root: Path,
    monkeypatch: Any,
    capsys: pytest.CaptureFixture[str],
    *,
    predecessor_status: str = "active",
) -> tuple[
    dict[str, str],
    dict[str, str],
    list[dict[str, Any]],
    list[dict[str, str]],
]:
    """Prepare one real bundle and its exact three compiled authority chains."""

    _initialize_active_task(root)
    if predecessor_status in {"complete", "completed"}:
        _task(root, task_id="task-old", status=predecessor_status)
    else:
        assert predecessor_status == "active"
    source_decision = _selected_receipt(root, capsys)
    candidate = root / ".task/candidates/task-next.md"
    candidate.parent.mkdir(parents=True, exist_ok=True)
    candidate.write_text("# Task\n\n- Task ID: `task-next`\n", encoding="utf-8")
    prepared = prepare_selected_successor_bundle(
        root,
        source_decision=source_decision,
        task_source=_binding(root, candidate),
        at=AT,
    )
    bundle = load_selected_successor_bundle(root, prepared["bundle"])
    inputs = prepare_authority_inputs(root, bundle, prepared["bundle"])
    authority = prepare_selected_successor_authority(
        root,
        bundle_binding=prepared["bundle"],
        request_context_binding=inputs["request_context"],
        evaluation_context_binding=inputs["evaluation_context"],
        grants=inputs["grants"],
        at=AT,
        skills_root=SKILLS_ROOT,
    )
    _packet_binding, packet = load_packet(root, authority["authority_packet"])
    compilations = [
        json.loads((root / row["compilation"]["ref"]).read_text(encoding="utf-8"))
        for row in packet["operations"]
    ]
    decision_bindings = [row["decision"] for row in packet["operations"]]
    batch_binding = {
        "ref": ".task/authorization/operation_batches/sha256/topology.json",
        "sha256": "d" * 64,
    }
    batch = {
        "schema_version": 1,
        "artifact_kind": "authority_operation_batch",
        "operation_count": len(compilations),
    }

    def load(
        _root: Path,
        binding: dict[str, str],
        *,
        skills_root: Path | None = None,
    ) -> tuple[dict[str, str], dict[str, Any], list[dict[str, Any]]]:
        assert binding == batch_binding
        assert skills_root is None
        return dict(batch_binding), batch, compilations

    monkeypatch.setattr(operation_batch_module, "load_operation_batch", load)
    return prepared["bundle"], batch_binding, compilations, decision_bindings


def test_historical_completed_task_requires_successor_topology_without_mutation(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    cycle_id = "cycle-historical-completed"
    task_id = "task-completed"
    _task(tmp_path, task_id=task_id, status="completed")
    cycle_dir = tmp_path / ".task/cycle" / cycle_id
    cycle_dir.mkdir(parents=True)
    (cycle_dir / "initialization.json").write_text(
        json.dumps(
            {
                "format_version": 1,
                "cycle_id": cycle_id,
                "initialized_at": "2026-07-23T01:00:00+09:00",
                "task_id": task_id,
                "reason": "historical fixture",
                "storage_bootstrap_only": True,
                "first_canonical_step": "context",
                "allow_missing_task_for_bootstrap": False,
                "stage_compiler_protocol_version": 2,
                "stage_preparation_schema_version": 2,
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    _install_batch(monkeypatch, cycle_id=cycle_id, task_id=task_id)
    before = _tree(tmp_path)

    result = preflight_executable_closure(tmp_path, BATCH_BINDING)

    assert result["status"] == "blocked_prerequisite"
    assert result["route"] == "selected_successor_topology"
    assert result["mutation_performed"] is False
    assert result["reason_codes"] == sorted(
        [
            "current_task_completed_non_executable",
            "selected_successor_topology_bundle_missing",
            "selected_successor_topology_required",
            "source_cycle_historical_v2_read_only",
        ]
    )
    assert _tree(tmp_path) == before


def test_sealed_active_task_and_cycle_are_executable_without_mutation(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    cycle_id = "cycle-active-sealed"
    task_id = "task-active"
    _task(tmp_path, task_id=task_id, status="active")
    cycle_ledger.init_cycle(
        tmp_path,
        cycle_id,
        task_id,
        "executable closure fixture",
        stage_compiler_protocol_version=2,
    )
    _install_batch(monkeypatch, cycle_id=cycle_id, task_id=task_id)
    before = _tree(tmp_path)

    result = preflight_executable_closure(tmp_path, BATCH_BINDING)

    assert result["status"] == "ready"
    assert result["route"] == "current_cycle"
    assert result["cycle_contract_state"] == "enforced"
    assert result["reason_codes"] == ["executable_closure_ready"]
    assert result["current_task"]["task_id"] == task_id
    assert result["current_task"]["executable"] is True
    assert result["mutation_performed"] is False
    assert _tree(tmp_path) == before


def test_current_cycle_rejects_unrelated_global_active_task(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    cycle_id = "cycle-active-cardinality"
    task_id = "task-active-cardinality"
    _task(tmp_path, task_id=task_id, status="active")
    cycle_ledger.init_cycle(
        tmp_path,
        cycle_id,
        task_id,
        "active task cardinality fixture",
        stage_compiler_protocol_version=2,
    )
    _install_batch(monkeypatch, cycle_id=cycle_id, task_id=task_id)
    _unrelated_active_task(tmp_path)
    before = _tree(tmp_path)

    result = preflight_executable_closure(tmp_path, BATCH_BINDING)

    assert result["status"] == "invalid"
    assert result["route"] == "current_cycle"
    assert result["current_task"] is None
    assert result["reason_codes"] == [
        "current_task_alias_missing_or_ambiguous",
        "operation_batch_task_not_executable",
    ]
    assert result["mutation_performed"] is False
    assert _tree(tmp_path) == before


def test_exact_selected_successor_topology_is_ready_without_mutation(
    tmp_path: Path,
    monkeypatch: Any,
    capsys: pytest.CaptureFixture[str],
) -> None:
    bundle, batch, _compilations, decisions = _topology_fixture(
        tmp_path, monkeypatch, capsys
    )
    before = _tree(tmp_path)

    result = preflight_executable_closure(
        tmp_path,
        batch,
        selected_successor_bundle_binding=bundle,
        decision_bindings=decisions,
    )

    assert result["status"] == "ready"
    assert result["route"] == "selected_successor_topology"
    assert result["operation_count"] == 3
    assert result["reason_codes"] == ["executable_closure_ready"]
    assert result["next_action"] == "execute_selected_successor_topology"
    assert result["closure_epoch"]["current_alias_id"] == "task-old"
    bundle_value = load_selected_successor_bundle(tmp_path, bundle)
    plan = json.loads(
        (tmp_path / bundle_value["task_state_plan"]["ref"]).read_text(encoding="utf-8")
    )
    predecessor = next(
        event for event in plan["events"] if event["status"] == "superseded"
    )
    assert result["closure_epoch"]["selected_successor_predecessor"] == {
        "task_id": "task-old",
        "task_state_plan": bundle_value["task_state_plan"],
        "selection_prepare": bundle_value["selection_prepare"],
        "snapshot": {
            "ref": predecessor["fields"]["snapshot_path"],
            "sha256": predecessor["fields"]["snapshot_digest"],
        },
    }
    assert result["mutation_performed"] is False
    assert _tree(tmp_path) == before


def test_exact_completed_predecessor_topology_is_ready_without_mutation(
    tmp_path: Path,
    monkeypatch: Any,
    capsys: pytest.CaptureFixture[str],
) -> None:
    bundle, batch, _compilations, decisions = _topology_fixture(
        tmp_path,
        monkeypatch,
        capsys,
        predecessor_status="complete",
    )
    bundle_value = load_selected_successor_bundle(tmp_path, bundle)
    plan = json.loads(
        (tmp_path / bundle_value["task_state_plan"]["ref"]).read_text(encoding="utf-8")
    )
    predecessor, successor = plan["events"]
    assert predecessor["fields"]["record_class"] == "immutable_snapshot"
    assert predecessor["fields"]["canonical_id"] == "task-old"
    predecessor_snapshot = tmp_path / predecessor["fields"]["snapshot_path"]
    assert predecessor_snapshot.is_file()
    assert not predecessor_snapshot.is_symlink()
    assert predecessor_snapshot.read_bytes() == (tmp_path / "task.md").read_bytes()
    assert successor["fields"]["record_class"] == "mutable_alias"
    assert successor["fields"]["canonical_id"] == "task-next"
    assert (tmp_path / successor["fields"]["snapshot_path"]).read_bytes() == (
        tmp_path / bundle_value["task_source"]["ref"]
    ).read_bytes()
    before = _tree(tmp_path)

    result = preflight_executable_closure(
        tmp_path,
        batch,
        selected_successor_bundle_binding=bundle,
        decision_bindings=decisions,
    )

    assert result["status"] == "ready"
    assert result["route"] == "selected_successor_topology"
    assert result["current_task"]["task_id"] == "task-old"
    assert result["current_task"]["status"] == "complete"
    assert result["current_task"]["executable"] is False
    assert result["closure_epoch"]["current_alias_id"] == "task-old"
    assert result["reason_codes"] == ["executable_closure_ready"]
    assert _tree(tmp_path) == before


def test_bundle_preparation_rejects_unrelated_active_task_without_writes(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _initialize_active_task(tmp_path)
    _unrelated_active_task(tmp_path)
    source_decision = _selected_receipt(tmp_path, capsys)
    candidate = tmp_path / ".task/candidates/task-next.md"
    candidate.parent.mkdir(parents=True, exist_ok=True)
    candidate.write_text("# Task\n\n- Task ID: `task-next`\n", encoding="utf-8")
    before = _tree(tmp_path)

    with pytest.raises(
        ValueError,
        match="Global active task set differs from the current task predecessor",
    ):
        prepare_selected_successor_bundle(
            tmp_path,
            source_decision=source_decision,
            task_source=_binding(tmp_path, candidate),
            at=AT,
        )

    assert _tree(tmp_path) == before
    assert not (tmp_path / ".task/selection_publication/successor_bundles").exists()
    assert not (tmp_path / ".task/authorization").exists()


def test_selected_successor_topology_rejects_coherent_alias_epoch_swap(
    tmp_path: Path,
    monkeypatch: Any,
    capsys: pytest.CaptureFixture[str],
) -> None:
    bundle, batch, _compilations, decisions = _topology_fixture(
        tmp_path, monkeypatch, capsys
    )
    _task(tmp_path, task_id="task-old", status="superseded")
    _task(tmp_path, task_id="task-other", status="active")
    before = _tree(tmp_path)

    result = preflight_executable_closure(
        tmp_path,
        batch,
        selected_successor_bundle_binding=bundle,
        decision_bindings=decisions,
    )

    assert result["status"] == "invalid"
    assert result["route"] == "selected_successor_topology"
    assert result["current_task"]["task_id"] == "task-other"
    assert result["reason_codes"] == [
        "operation_batch_task_not_executable",
        "selected_successor_topology_predecessor_mismatch",
    ]
    assert result["mutation_performed"] is False
    assert _tree(tmp_path) == before


def test_selected_successor_topology_rejects_unrelated_active_task_drift(
    tmp_path: Path,
    monkeypatch: Any,
    capsys: pytest.CaptureFixture[str],
) -> None:
    bundle, batch, _compilations, decisions = _topology_fixture(
        tmp_path, monkeypatch, capsys
    )
    _unrelated_active_task(tmp_path)
    before = _tree(tmp_path)

    result = preflight_executable_closure(
        tmp_path,
        batch,
        selected_successor_bundle_binding=bundle,
        decision_bindings=decisions,
    )

    assert result["status"] == "invalid"
    assert result["route"] == "selected_successor_topology"
    assert result["current_task"] is None
    assert result["reason_codes"] == [
        "current_task_alias_missing_or_ambiguous",
        "operation_batch_task_not_executable",
        "selected_successor_topology_predecessor_mismatch",
    ]
    assert result["mutation_performed"] is False
    assert _tree(tmp_path) == before


def test_current_task_swap_after_descriptor_open_fails_closed(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    cycle_id = "cycle-task-snapshot-race"
    task_id = "task-snapshot-race"
    _task(tmp_path, task_id=task_id, status="active")
    cycle_ledger.init_cycle(
        tmp_path,
        cycle_id,
        task_id,
        "task snapshot race fixture",
        stage_compiler_protocol_version=2,
    )
    _install_batch(monkeypatch, cycle_id=cycle_id, task_id=task_id)
    replacement = tmp_path / "replacement-task.md"
    replacement.write_text("# Replacement\n", encoding="utf-8")
    import orchestrate_task_cycle.executable_closure_snapshot as snapshot

    swapped = False

    def replace_visible_task(stage: str, root: Path) -> None:
        nonlocal swapped
        assert stage == "after_task_open"
        if swapped:
            return
        swapped = True
        task_path = root / "task.md"
        task_path.unlink()
        task_path.symlink_to(replacement.name)

    monkeypatch.setattr(snapshot, "_task_snapshot_hook", replace_visible_task)

    with pytest.raises(ValueError, match="changed during executable-closure read"):
        preflight_executable_closure(tmp_path, BATCH_BINDING)

    assert swapped is True
    assert (tmp_path / "task.md").is_symlink()


@pytest.mark.parametrize(
    "decision_projection",
    [
        lambda values: values[:-1],
        lambda values: [values[0], values[0], values[2]],
    ],
    ids=("one-missing", "one-duplicate"),
)
def test_selected_successor_topology_requires_three_distinct_exact_decisions(
    tmp_path: Path,
    monkeypatch: Any,
    capsys: pytest.CaptureFixture[str],
    decision_projection: Any,
) -> None:
    bundle, batch, _compilations, decisions = _topology_fixture(
        tmp_path, monkeypatch, capsys
    )
    before = _tree(tmp_path)

    result = preflight_executable_closure(
        tmp_path,
        batch,
        selected_successor_bundle_binding=bundle,
        decision_bindings=decision_projection(decisions),
    )

    assert result["status"] == "blocked_prerequisite"
    assert result["route"] == "selected_successor_topology"
    assert result["reason_codes"] == ["selected_successor_topology_grants_required"]
    assert result["mutation_performed"] is False
    assert _tree(tmp_path) == before


def test_selected_successor_topology_rejects_allowed_context_drift(
    tmp_path: Path,
    monkeypatch: Any,
    capsys: pytest.CaptureFixture[str],
) -> None:
    bundle, batch, _compilations, decisions = _topology_fixture(
        tmp_path, monkeypatch, capsys
    )
    original = json.loads((tmp_path / decisions[0]["ref"]).read_text(encoding="utf-8"))
    drifted = json.loads(json.dumps(original))
    drifted["evaluation_context"]["session_ceiling"]["evidence_id"] = (
        "selected-successor-context-drift"
    )
    drifted["evaluation_context_sha256"] = object_sha256(drifted["evaluation_context"])
    drifted["effective_authority_fingerprint"] = effective_authority_fingerprint(
        drifted["request"],
        drifted["evaluation_context"],
        drifted["operation_manifest"],
        drifted["selected_grants"],
        drifted["lineage_grants"],
    )
    core = {key: value for key, value in drifted.items() if key != "decision_id"}
    drifted["decision_id"] = f"authd-{object_sha256(core)[:24]}"
    path = tmp_path / ".task/authorization/decisions" / f"{drifted['decision_id']}.json"
    digest = write_immutable_json(
        path, drifted, "drifted selected-successor test decision"
    )
    decisions[0] = {
        "ref": path.relative_to(tmp_path).as_posix(),
        "sha256": digest,
    }
    before = _tree(tmp_path)

    result = preflight_executable_closure(
        tmp_path,
        batch,
        selected_successor_bundle_binding=bundle,
        decision_bindings=decisions,
    )

    assert result["status"] == "blocked_prerequisite"
    assert result["route"] == "selected_successor_topology"
    assert result["reason_codes"] == ["selected_successor_topology_grants_required"]
    assert result["mutation_performed"] is False
    assert _tree(tmp_path) == before


def test_selected_successor_topology_rejects_invalid_source_cycle_contract(
    tmp_path: Path,
    monkeypatch: Any,
    capsys: pytest.CaptureFixture[str],
) -> None:
    bundle, batch, compilations, decisions = _topology_fixture(
        tmp_path, monkeypatch, capsys
    )
    cycle_id = compilations[0]["request"]["cycle_id"]
    initialization = tmp_path / ".task/cycle" / cycle_id / "initialization.json"
    value = json.loads(initialization.read_text(encoding="utf-8"))
    value["workflow_contract_profile"] = "unknown-contract-profile"
    initialization.write_text(
        json.dumps(value, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    before = _tree(tmp_path)

    result = preflight_executable_closure(
        tmp_path,
        batch,
        selected_successor_bundle_binding=bundle,
        decision_bindings=decisions,
    )

    assert result["status"] == "invalid"
    assert result["route"] == "selected_successor_topology"
    assert result["reason_codes"] == ["source_cycle_contract_invalid"]
    assert result["mutation_performed"] is False
    assert _tree(tmp_path) == before


def test_cli_blocks_completed_task_before_reservation(
    tmp_path: Path,
    monkeypatch: Any,
    capsys: Any,
) -> None:
    cycle_id = "cycle-historical-cli"
    task_id = "task-completed-cli"
    _task(tmp_path, task_id=task_id, status="complete")
    cycle_dir = tmp_path / ".task/cycle" / cycle_id
    cycle_dir.mkdir(parents=True)
    (cycle_dir / "initialization.json").write_text(
        json.dumps(
            {
                "format_version": 1,
                "cycle_id": cycle_id,
                "initialized_at": "2026-07-23T01:00:00+09:00",
                "task_id": task_id,
                "reason": "historical fixture",
                "storage_bootstrap_only": True,
                "first_canonical_step": "context",
                "allow_missing_task_for_bootstrap": False,
                "stage_compiler_protocol_version": 2,
                "stage_preparation_schema_version": 2,
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    _install_batch(monkeypatch, cycle_id=cycle_id, task_id=task_id)
    before = _tree(tmp_path)

    code = main(
        [
            "--root",
            str(tmp_path),
            "--operation-batch-ref",
            BATCH_BINDING["ref"],
            "--operation-batch-sha256",
            BATCH_BINDING["sha256"],
        ]
    )

    assert code == 2
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "blocked_prerequisite"
    assert output["next_action"] == "prepare_selected_successor_topology"
    assert _tree(tmp_path) == before


def test_topology_decisions_require_exact_compiled_evaluation_context() -> None:
    request = {"cycle_id": "cycle-A", "task_id": "task-A"}
    context = {"context_kind": "authority_evaluation_context", "session": "A"}
    manifest = {"operation_id": "topology"}
    compilations = [
        {
            "request": request,
            "request_sha256": "a" * 64,
            "evaluation_context": context,
            "evaluation_context_sha256": "b" * 64,
            "operation_manifest": manifest,
        }
    ]
    decision = {
        "decision": "allowed",
        "request": request,
        "request_sha256": "a" * 64,
        "evaluation_context": context,
        "evaluation_context_sha256": "b" * 64,
        "operation_manifest": manifest,
    }

    assert _topology_has_exact_allowed_decisions([decision], compilations)

    drifted = {
        **decision,
        "evaluation_context": {**context, "session": "different"},
    }
    assert not _topology_has_exact_allowed_decisions([drifted], compilations)


def test_cli_normalizes_owner_system_exit_to_invalid_json(
    tmp_path: Path,
    monkeypatch: Any,
    capsys: Any,
) -> None:
    def fail(*_args: Any, **_kwargs: Any) -> Any:
        raise SystemExit("operation batch is unavailable")

    monkeypatch.setattr(operation_batch_module, "load_operation_batch", fail)

    code = main(
        [
            "--root",
            str(tmp_path),
            "--operation-batch-ref",
            BATCH_BINDING["ref"],
            "--operation-batch-sha256",
            BATCH_BINDING["sha256"],
        ]
    )

    assert code == 2
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "invalid"
    assert output["error"] == "operation batch is unavailable"
    assert output["mutation_performed"] is False
