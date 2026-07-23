from __future__ import annotations

import json
from pathlib import Path

import pytest

from orchestrate_task_cycle import cycle_ledger, render_subskill_packet
from orchestrate_task_cycle.cycle_efficiency.analysis import analyze
from orchestrate_task_cycle.cycle_efficiency import compiler_contract_lint
from orchestrate_task_cycle.ledger.compiled_events import (
    append_compiled_stage_observation,
    append_compiled_stage_result_binding,
    append_compiled_system_stage,
    append_compiled_terminal_lifecycle,
)
from orchestrate_task_cycle.ledger import initialization as ledger_initialization
from orchestrate_task_cycle.ledger.compiler_binding import (
    CompiledEventBinding,
    compile_stage_result_binding,
    compile_system_event,
)
from orchestrate_task_cycle.ledger.semantic_seeds import (
    make_stage_observation_seed,
    make_terminal_lifecycle_seed,
)
from orchestrate_task_cycle.ledger.repository import append_compiled_binding
from orchestrate_task_cycle.stage.deterministic_dispatch import (
    dispatch_deterministic,
)
from orchestrate_task_cycle.stage import (
    deterministic_commit as deterministic_commit_module,
)
from orchestrate_task_cycle.stage.artifact_store import (
    load_stage_input,
)
from orchestrate_task_cycle.stage.builder import ResultBuilder
from orchestrate_task_cycle.stage.contracts import canonical_bytes, canonical_sha256
from orchestrate_task_cycle.stage.publication import result_path
from orchestrate_task_cycle.stage.service import (
    advance_stage,
    execute_deterministic_stage,
    prepare_stage,
)
from compiler_first_fixture_support import (
    append_fixture_event,
    create_sealed_legacy_v1_cycle,
)


def _cli_cycle(
    root: Path, cycle_id: str, capsys: pytest.CaptureFixture[str]
) -> dict:
    assert cycle_ledger.main(
        ["--root", str(root), "init", "--cycle-id", cycle_id, "--task-id", "task-1"]
    ) == 0
    return json.loads(capsys.readouterr().out)


def _context_event(event_id: str = "context-1") -> dict:
    return {
        "event_id": event_id,
        "step": "context",
        "status": "complete",
        "task_id": "task-1",
        "reason": "compiled context",
    }


def _fixture_deterministic_owner(
    root: Path, preparation: dict
) -> dict:
    prediction = dispatch_deterministic(root, preparation)
    assert prediction.get("status") != "block", prediction
    committed = deterministic_commit_module.commit_deterministic_gated(
        root,
        preparation,
        prediction,
        max_files=12,
        max_paths=40,
    )
    assert committed.get("status") != "block", committed
    return {
        **committed["owner_result_binding"],
        "deterministic_commit_binding": committed[
            "deterministic_commit_binding"
        ],
    }


def _remove_profile_to_simulate_existing_v2(root: Path, cycle_id: str) -> None:
    directory = root / ".task" / "cycle" / cycle_id
    path = directory / "initialization.json"
    metadata = json.loads(path.read_text(encoding="utf-8"))
    metadata.pop("workflow_contract_profile")
    metadata.pop("initialization_provenance_version")
    path.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (directory / "initialization.provenance.json").unlink()


def test_cli_new_v2_cycle_enforces_typed_ledger_producers(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    created = _cli_cycle(tmp_path, "cycle-enforced", capsys)
    assert (
        created["initialization"]["workflow_contract_profile"]
        == "compiler_first_enforced_v1"
    )
    with pytest.raises(ValueError, match="rejects public direct ledger append"):
        cycle_ledger.append_event(
            tmp_path, "cycle-enforced", _context_event("public-context")
        )
    from orchestrate_task_cycle.ledger import compiled_events

    assert not hasattr(compiled_events, "append_compiled_event")
    assert not hasattr(compiled_events, "_bind_system_event")
    with pytest.raises(ValueError, match="compiler-owned event binding"):
        append_compiled_binding(
            tmp_path, "cycle-enforced", _context_event("unbound-context")
        )
    forged = CompiledEventBinding(
        canonical_event=b'{"event_kind":"compiled_system_event_ref"}',
        producer_kind="system_event_compiler",
        event_kind="compiled_system_event_ref",
        _capability=object(),
    )
    with pytest.raises(ValueError, match="compiler-owned event binding"):
        append_compiled_binding(tmp_path, "cycle-enforced", forged)
    with pytest.raises(TypeError, match="producer_kind"):
        cycle_ledger.append_event(
            tmp_path,
            "cycle-enforced",
            _context_event("producer-string-bypass"),
            producer_kind="system_event_compiler",
        )
    with pytest.raises(ValueError, match="non-derived fields"):
        compile_system_event(
            {
                **_context_event("arbitrary-context"),
                "context_fingerprint": "forged",
                "invented_mechanical_field": True,
            }
        )
    published = append_compiled_system_stage(
        tmp_path, "cycle-enforced", "context"
    )
    assert published["event"]["event_kind"] == "compiled_system_event_ref"
    assert published["event"]["producer_kind"] == "system_event_compiler"


def test_enforced_result_append_has_no_raw_compact_event_surface(
    tmp_path: Path,
) -> None:
    from orchestrate_task_cycle.ledger import compiled_events, compiler_binding

    cycle_ledger.init_cycle(
        tmp_path, "cycle-result-raw-rejected", "task-1", "raw result rejection"
    )
    append_compiled_system_stage(
        tmp_path, "cycle-result-raw-rejected", "context"
    )
    assert not hasattr(compiled_events, "append_compiled_stage_result_event")
    assert not hasattr(compiler_binding, "compile_stage_result_event")
    with pytest.raises(ValueError, match="compiler-owned event binding"):
        append_compiled_stage_result_binding(
            tmp_path,
            "cycle-result-raw-rejected",
            {
                "format_version": 2,
                "step": "authority",
                "status": "completed",
                "event_id": "caller-authored-compact-result",
            },
        )
    with pytest.raises(ValueError, match="compiler-owned semantic seed"):
        append_compiled_stage_observation(
            tmp_path,
            "cycle-result-raw-rejected",
            {"step": "run", "observation_kind": "caller-authored"},
        )
    with pytest.raises(ValueError, match="compiler-owned semantic seed"):
        append_compiled_terminal_lifecycle(
            tmp_path,
            "cycle-result-raw-rejected",
            {"step": "report", "terminal_justified": True},
        )
    with pytest.raises(ValueError, match="unsupported fields"):
        make_stage_observation_seed(
            {
                "observation_kind": "closed-seed",
                "invented_mechanical_field": True,
            }
        )
    assert [
        event["step"]
        for event in cycle_ledger.read_events_raw(
            tmp_path, "cycle-result-raw-rejected"
        )
    ] == ["context"]


def test_result_binding_reopens_inputs_and_locks_ledger_precondition(
    tmp_path: Path,
) -> None:
    cycle_id = "cycle-result-binding-closed"
    task_path = tmp_path / "task.md"
    task_body = "# Task\n\nCompiler result boundary.\n"
    task_path.write_text(task_body, encoding="utf-8")
    cycle_ledger.init_cycle(tmp_path, cycle_id, "task-1", "closed result binding")
    append_compiled_system_stage(tmp_path, cycle_id, "context")
    append_fixture_event(
        tmp_path,
        cycle_id,
        {
            "step": "authority",
            "status": "complete",
            "event_id": "fixture-authority-result-binding",
            "task_id": "task-1",
        },
    )
    preparation = prepare_stage(
        tmp_path,
        cycle_id,
        "repo_skill_adapter_scan",
        persist_compiler_artifacts=True,
    )
    owner = _fixture_deterministic_owner(tmp_path, preparation)
    judgment, exact_owner = load_stage_input(
        tmp_path,
        owner["ref"],
        owner["sha256"],
        cycle_id=cycle_id,
        target="repo_skill_adapter_scan",
        input_kind="owner_result",
    )
    result = ResultBuilder().build(preparation, judgment)
    digest = canonical_sha256(result)
    path = result_path(tmp_path, cycle_id, "repo_skill_adapter_scan", digest)
    path.write_bytes(canonical_bytes(result) + b"\n")
    relative = path.relative_to(tmp_path).as_posix()
    previous = cycle_ledger.read_events_raw(tmp_path, cycle_id)
    exact_bindings = {
        "owner_result_binding": exact_owner,
        "deterministic_commit_binding": owner[
            "deterministic_commit_binding"
        ],
    }

    with pytest.raises(ValueError, match="omits required exact input bindings"):
        compile_stage_result_binding(
            preparation,
            result,
            relative,
            digest,
            {},
            {},
            {"max_files": 12, "max_paths": 40},
            previous,
        )
    with pytest.raises(ValueError, match="collection limits differ"):
        compile_stage_result_binding(
            preparation,
            result,
            relative,
            digest,
            {},
            exact_bindings,
            {"max_files": 1, "max_paths": 1},
            previous,
        )

    fabricated = {**result, "fabricated": True}
    fabricated_digest = canonical_sha256(fabricated)
    fabricated_path = result_path(
        tmp_path,
        cycle_id,
        "repo_skill_adapter_scan",
        fabricated_digest,
    )
    fabricated_path.write_bytes(canonical_bytes(fabricated) + b"\n")
    fabricated_binding = compile_stage_result_binding(
        preparation,
        fabricated,
        fabricated_path.relative_to(tmp_path).as_posix(),
        fabricated_digest,
        {},
        exact_bindings,
        {"max_files": 12, "max_paths": 40},
        previous,
    )
    with pytest.raises(ValueError, match="exact input reconstruction"):
        append_compiled_stage_result_binding(
            tmp_path,
            cycle_id,
            fabricated_binding,
        )
    assert not [
        event
        for event in cycle_ledger.read_events_raw(tmp_path, cycle_id)
        if event.get("step") == "repo_skill_adapter_scan"
    ]

    stale_preparation = compile_stage_result_binding(
        preparation,
        result,
        relative,
        digest,
        {},
        exact_bindings,
        {"max_files": 12, "max_paths": 40},
        previous,
    )
    task_path.write_text("# Task\n\nChanged after compilation.\n", encoding="utf-8")
    with pytest.raises(ValueError, match="preparation is stale"):
        append_compiled_stage_result_binding(
            tmp_path,
            cycle_id,
            stale_preparation,
        )
    task_path.write_text(task_body, encoding="utf-8")

    stale_prefix = compile_stage_result_binding(
        preparation,
        result,
        relative,
        digest,
        {},
        exact_bindings,
        {"max_files": 12, "max_paths": 40},
        previous,
    )
    append_compiled_stage_observation(
        tmp_path,
        cycle_id,
        make_stage_observation_seed(
            {"observation_kind": "prefix-race", "task_id": "task-1"}
        ),
    )
    with pytest.raises(ValueError, match="ledger precondition changed"):
        append_compiled_stage_result_binding(
            tmp_path, cycle_id, stale_prefix
        )
    assert not [
        event
        for event in cycle_ledger.read_events_raw(tmp_path, cycle_id)
        if event.get("event_kind") == "compiled_stage_result_ref"
    ]


def test_cli_public_append_returns_bounded_contract_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _cli_cycle(tmp_path, "cycle-cli-append-rejected", capsys)
    assert (
        cycle_ledger.main(
            [
                "--root",
                str(tmp_path),
                "append",
                "--cycle-id",
                "cycle-cli-append-rejected",
                "--event-json",
                json.dumps(_context_event("public-cli-context")),
            ]
        )
        == 2
    )
    captured = capsys.readouterr()
    blocked = json.loads(captured.out)
    assert captured.err == ""
    assert blocked == {
        "error": {
            "code": "cycle_ledger_contract_rejected",
            "message": (
                "compiler-first cycle rejects public direct ledger append; "
                "use a typed internal producer"
            ),
        },
        "mutation_performed": False,
        "status": "block",
    }
    assert cycle_ledger.read_events(tmp_path, "cycle-cli-append-rejected") == []


def test_initialization_field_deletion_cannot_downgrade_enforced_cycle(
    tmp_path: Path,
) -> None:
    cycle_id = "cycle-init-field-deletion"
    created = cycle_ledger.init_cycle(
        tmp_path, cycle_id, "task-1", "tamper regression"
    )
    path = tmp_path / created["initialization_path"]
    metadata = json.loads(path.read_text(encoding="utf-8"))
    metadata.pop("workflow_contract_profile")
    metadata.pop("stage_compiler_protocol_version")
    path.write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="initialization"):
        cycle_ledger.append_event(
            tmp_path, cycle_id, _context_event("downgrade-attempt")
        )
    assert not (path.parent / "stage.jsonl").exists()


def test_initialization_retry_repairs_exact_metadata_only_provenance_crash(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cycle_id = "cycle-init-provenance-crash"
    actual_publish = ledger_initialization.publish_initialization_provenance

    def fail_before_provenance(*_args, **_kwargs):
        raise RuntimeError("injected provenance publication crash")

    monkeypatch.setattr(
        ledger_initialization,
        "publish_initialization_provenance",
        fail_before_provenance,
    )
    with pytest.raises(RuntimeError, match="provenance publication crash"):
        cycle_ledger.init_cycle(
            tmp_path,
            cycle_id,
            "task-1",
            "provenance crash recovery",
        )
    directory = tmp_path / ".task" / "cycle" / cycle_id
    assert (directory / "initialization.json").is_file()
    assert not (directory / "initialization.provenance.json").exists()
    assert not (directory / "stage.jsonl").exists()
    assert not (directory / "current_stage.json").exists()

    monkeypatch.setattr(
        ledger_initialization,
        "publish_initialization_provenance",
        actual_publish,
    )
    recovered = cycle_ledger.init_cycle(
        tmp_path,
        cycle_id,
        "task-1",
        "provenance crash recovery",
    )

    assert recovered["cycle_existing"] is True
    assert (directory / "initialization.provenance.json").is_file()
    assert (directory / "current_stage.json").is_file()
    assert cycle_ledger.read_initialization_metadata(tmp_path, cycle_id) == (
        recovered["initialization"]
    )


@pytest.mark.parametrize("blocker", ["different_request", "ledger", "current"])
def test_initialization_retry_does_not_seal_nonexact_or_advanced_residue(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    blocker: str,
) -> None:
    cycle_id = f"cycle-init-provenance-blocked-{blocker}"

    def fail_before_provenance(*_args, **_kwargs):
        raise RuntimeError("injected provenance publication crash")

    with monkeypatch.context() as crash:
        crash.setattr(
            ledger_initialization,
            "publish_initialization_provenance",
            fail_before_provenance,
        )
        with pytest.raises(RuntimeError, match="provenance publication crash"):
            cycle_ledger.init_cycle(
                tmp_path,
                cycle_id,
                "task-1",
                "exact request",
            )
    directory = tmp_path / ".task" / "cycle" / cycle_id
    retry_reason = "different request" if blocker == "different_request" else (
        "exact request"
    )
    if blocker == "ledger":
        (directory / "stage.jsonl").write_text("{}\n", encoding="utf-8")
    elif blocker == "current":
        (directory / "current_stage.json").write_text("{}\n", encoding="utf-8")

    with pytest.raises(ValueError, match="provenance"):
        cycle_ledger.init_cycle(
            tmp_path,
            cycle_id,
            "task-1",
            retry_reason,
        )
    assert not (directory / "initialization.provenance.json").exists()


def test_deleted_seal_and_protocol1_rewrite_is_historical_read_only(
    tmp_path: Path,
) -> None:
    cycle_id = "cycle-init-seal-deletion"
    created = cycle_ledger.init_cycle(
        tmp_path, cycle_id, "task-1", "seal deletion regression"
    )
    path = tmp_path / created["initialization_path"]
    metadata = json.loads(path.read_text(encoding="utf-8"))
    metadata.pop("workflow_contract_profile")
    metadata.pop("initialization_provenance_version")
    metadata["stage_compiler_protocol_version"] = 1
    metadata["stage_preparation_schema_version"] = 1
    path.write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (path.parent / "initialization.provenance.json").unlink()

    with pytest.raises(ValueError, match="historical unsealed protocol-v1"):
        cycle_ledger.append_event(
            tmp_path, cycle_id, _context_event("legacy-forgery")
        )
    assert not (path.parent / "stage.jsonl").exists()


def test_existing_unmarked_v2_cycle_is_historical_read_only(
    tmp_path: Path,
) -> None:
    cycle_ledger.init_cycle(tmp_path, "cycle-compat", "task-1", "compatibility")
    _remove_profile_to_simulate_existing_v2(tmp_path, "cycle-compat")
    with pytest.raises(ValueError, match="historical unmarked protocol-v2"):
        cycle_ledger.append_event(
            tmp_path, "cycle-compat", _context_event("legacy-context")
        )
    with pytest.raises(ValueError, match="historical unmarked protocol-v2"):
        append_compiled_system_stage(tmp_path, "cycle-compat", "context")
    with pytest.raises(ValueError, match="`init` requires a new compiler-first cycle"):
        cycle_ledger.init_cycle(
            tmp_path, "cycle-compat", "task-1", "compatibility"
        )


def test_historical_v2_reinit_cli_returns_bounded_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cycle_ledger.init_cycle(
        tmp_path, "cycle-historical-cli", "task-1", "historical"
    )
    _remove_profile_to_simulate_existing_v2(tmp_path, "cycle-historical-cli")
    assert cycle_ledger.main(
        [
            "--root",
            str(tmp_path),
            "init",
            "--cycle-id",
            "cycle-historical-cli",
            "--task-id",
            "task-1",
            "--reason",
            "historical",
        ]
    ) == 2
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "block"
    assert output["mutation_performed"] is False
    assert output["error"]["code"] == "cycle_ledger_contract_rejected"


def test_precreated_historical_v2_reinit_creates_no_files(tmp_path: Path) -> None:
    cycle_id = "cycle-precreated-historical"
    directory = tmp_path / ".task" / "cycle" / cycle_id
    directory.mkdir(parents=True)
    metadata_path = directory / "initialization.json"
    metadata_path.write_text(
        json.dumps(
            {
                "format_version": 2,
                "cycle_id": cycle_id,
                "task_id": "task-1",
                "reason": "precreated",
                "stage_compiler_protocol_version": 2,
                "stage_preparation_schema_version": 3,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    before = sorted(path.relative_to(directory) for path in directory.rglob("*"))

    with pytest.raises(ValueError, match="`init` requires a new compiler-first cycle"):
        cycle_ledger.init_cycle(
            tmp_path,
            cycle_id,
            "task-1",
            "precreated",
        )

    assert sorted(path.relative_to(directory) for path in directory.rglob("*")) == before
    assert not (directory / "packets").exists()
    assert not (directory / ".ledger.lock").exists()


def test_protocol_v1_write_contract_is_unchanged(tmp_path: Path) -> None:
    create_sealed_legacy_v1_cycle(
        tmp_path,
        "cycle-v1",
        "task-1",
        "v1",
    )
    result = cycle_ledger.append_event(
        tmp_path, "cycle-v1", _context_event("v1-context")
    )
    assert "workflow_contract_warning" not in result


def test_protocol_v1_system_shape_and_historical_v2_advance_rejection(
    tmp_path: Path,
) -> None:
    create_sealed_legacy_v1_cycle(
        tmp_path,
        "cycle-v1-system",
        "task-1",
        "v1 system event",
    )
    result = advance_stage(
        tmp_path,
        "cycle-v1-system",
        apply=True,
        max_steps=1,
        preparation_schema_version=1,
    )
    event = cycle_ledger.read_events(tmp_path, "cycle-v1-system")[0]
    assert result["status"] == "waiting"
    assert "event_kind" not in event
    assert "producer_kind" not in event

    cycle_ledger.init_cycle(
        tmp_path, "cycle-v2-system-compat", "task-1", "v2 system compatibility"
    )
    _remove_profile_to_simulate_existing_v2(tmp_path, "cycle-v2-system-compat")
    with pytest.raises(ValueError, match="cannot advance"):
        advance_stage(
            tmp_path,
            "cycle-v2-system-compat",
            apply=True,
            max_steps=1,
        )
    with pytest.raises(ValueError, match="cannot advance"):
        advance_stage(
            tmp_path,
            "cycle-v2-system-compat",
            apply=False,
            max_steps=1,
        )
    assert cycle_ledger.read_events(tmp_path, "cycle-v2-system-compat") == []


def test_historical_v2_dashboard_dispatch_has_no_pre_guard_write(
    tmp_path: Path,
) -> None:
    cycle_id = "cycle-dashboard-read-only"
    cycle_ledger.init_cycle(
        tmp_path, cycle_id, "task-1", "dashboard prewrite regression"
    )
    _remove_profile_to_simulate_existing_v2(tmp_path, cycle_id)
    lock = tmp_path / ".task" / "cycle" / cycle_id / ".ledger.lock"
    lock.unlink()
    dashboard = (
        tmp_path / ".task" / "cycle" / cycle_id / "dashboard.md"
    )
    before = {
        path.relative_to(tmp_path).as_posix(): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }

    with pytest.raises(ValueError, match="historical unmarked protocol-v2"):
        dispatch_deterministic(
            tmp_path,
            {"cycle_id": cycle_id, "target": "dashboard"},
        )
    with pytest.raises(ValueError, match="historical unmarked protocol-v2"):
        execute_deterministic_stage(
            tmp_path,
            cycle_id,
            "dashboard",
            apply=True,
        )
    assert not dashboard.exists()
    assert {
        path.relative_to(tmp_path).as_posix(): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    } == before


def test_enforced_typed_producer_rejects_cross_task_event(
    tmp_path: Path,
) -> None:
    cycle_ledger.init_cycle(
        tmp_path, "cycle-task-binding", "task-1", "typed task binding"
    )
    forged = compile_system_event(
        {
            **_context_event("wrong-task-context"),
            "task_id": "task-2",
            "task_absent": False,
            "task_md": None,
            "used_goal_truth": [],
            "used_advice": [],
            "context_fingerprint": "forged",
        }
    )
    with pytest.raises(ValueError, match="differs from cycle initialization"):
        append_compiled_binding(
            tmp_path, "cycle-task-binding", forged
        )


def test_generic_packet_rejects_enforced_and_historical_v2_cycles(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _cli_cycle(tmp_path, "cycle-packet-enforced", capsys)
    context = {
        "workspace": str(tmp_path),
        "cycle_state": {"latest_cycle_id": "cycle-packet-enforced"},
    }
    with pytest.raises(ValueError, match="generic full packet rendering is disabled"):
        render_subskill_packet.packet_for("acceptance", context, {})
    cycle_ledger.init_cycle(
        tmp_path, "cycle-packet-compat", "task-1", "packet compatibility"
    )
    _remove_profile_to_simulate_existing_v2(tmp_path, "cycle-packet-compat")
    context["cycle_state"]["latest_cycle_id"] = "cycle-packet-compat"
    with pytest.raises(ValueError, match="historical unmarked v2 cycles are read-only"):
        render_subskill_packet.packet_for(
            "acceptance", context, {}
        )
    context["cycle_state"]["latest_cycle_id"] = "cycle-does-not-exist"
    with pytest.raises(ValueError, match="explicitly bound legacy cycle"):
        render_subskill_packet.packet_for(
            "acceptance", context, {}
        )


def test_sealed_v1_packet_requires_exact_cycle_and_task_binding(
    tmp_path: Path,
) -> None:
    for cycle_id, task_id in (
        ("cycle-packet-v1-a", "task-v1-a"),
        ("cycle-packet-v1-b", "task-v1-b"),
    ):
            create_sealed_legacy_v1_cycle(
                tmp_path,
                cycle_id,
                task_id,
                "sealed v1 packet binding",
            )
    context = {
        "workspace": str(tmp_path),
        "cycle_state": {"latest_cycle_id": "cycle-packet-v1-a"},
    }
    exact = render_subskill_packet.packet_cycle_contract(
        context,
        {"cycle_id": "cycle-packet-v1-a", "task_id": "task-v1-a"},
    )
    assert exact == {
        "status": "protocol_v1_unchanged",
        "cycle_id": "cycle-packet-v1-a",
    }

    cross_cycle = render_subskill_packet.packet_cycle_contract(
        context,
        {"cycle_id": "cycle-packet-v1-b", "task_id": "task-v1-b"},
    )
    assert cross_cycle == {"status": "invalid_cycle_context"}
    with pytest.raises(ValueError, match="explicitly bound legacy cycle"):
        render_subskill_packet.packet_for(
            "acceptance",
            context,
            {"cycle_id": "cycle-packet-v1-b", "task_id": "task-v1-b"},
        )

    cross_task = render_subskill_packet.packet_cycle_contract(
        context,
        {"cycle_id": "cycle-packet-v1-a", "task_id": "task-v1-b"},
    )
    assert cross_task == {
        "status": "invalid_cycle_context",
        "cycle_id": "cycle-packet-v1-a",
    }
    with pytest.raises(ValueError, match="explicitly bound legacy cycle"):
        render_subskill_packet.packet_for(
            "acceptance",
            context,
            {"cycle_id": "cycle-packet-v1-a", "task_id": "task-v1-b"},
        )


def test_cli_generic_packet_returns_bounded_contract_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _cli_cycle(tmp_path, "cycle-cli-packet-rejected", capsys)
    context = json.dumps(
        {
            "workspace": str(tmp_path),
            "cycle_state": {"latest_cycle_id": "cycle-cli-packet-rejected"},
        }
    )
    assert (
        render_subskill_packet.main(
            ["--target", "acceptance", "--context", context, "--format", "json"]
        )
        == 2
    )
    captured = capsys.readouterr()
    blocked = json.loads(captured.out)
    assert captured.err == ""
    assert blocked == {
        "error": {
            "code": "generic_packet_contract_rejected",
            "message": (
                "generic full packet rendering is disabled for protocol-v2 cycles; "
                "new cycles must use `stage prepare` and historical unmarked v2 "
                "cycles are read-only; invalid cycle contracts also fail closed"
            ),
        },
        "mutation_performed": False,
        "status": "block",
    }


def test_terminal_lifecycle_observation_keeps_a_typed_envelope(
    tmp_path: Path,
) -> None:
    cycle_ledger.init_cycle(
        tmp_path, "cycle-terminal-enforced", "task-1", "terminal contract"
    )
    append_compiled_system_stage(
        tmp_path, "cycle-terminal-enforced", "context"
    )
    terminal = {
        "terminal_justified": True,
        "terminal_outcome_family_key": "family-a",
        "input_state_fingerprint": "input-a",
        "authority_state_fingerprint": "authority-a",
    }
    append_compiled_terminal_lifecycle(
        tmp_path,
        "cycle-terminal-enforced",
        make_terminal_lifecycle_seed(terminal),
    )
    restart = cycle_ledger.init_cycle(
        tmp_path,
        "cycle-terminal-not-created",
        "task-1",
        "terminal restart",
        {
            key: value
            for key, value in terminal.items()
            if key not in {"event_id", "step", "status"}
        },
    )
    assert restart["cycle_suppressed"] is True
    observation = restart["observation_result"]["event"]
    assert observation["event_kind"] == "compiled_terminal_lifecycle_ref"
    assert observation["producer_kind"] == "terminal_lifecycle_compiler"
    assert observation["terminal_lifecycle_kind"] == "terminal_latch_observation"


@pytest.mark.parametrize("protocol_version", [None, 2])
def test_python_initializer_marks_every_new_protocol_v2_cycle(
    tmp_path: Path,
    protocol_version: int | None,
) -> None:
    created = cycle_ledger.init_cycle(
        tmp_path,
        "cycle-python-enforced",
        "task-1",
        "python default",
        stage_compiler_protocol_version=protocol_version,
    )
    assert (
        created["initialization"]["workflow_contract_profile"]
        == "compiler_first_enforced_v1"
    )


def test_system_compiler_rejects_unattested_runtime_metrics(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _cli_cycle(tmp_path, "cycle-metrics", capsys)
    with pytest.raises(ValueError, match="non-derived fields"):
        compile_system_event(
            {
                **_context_event("metrics-context"),
                "context_fingerprint": "forged",
                "compiler_metrics": {"model_call_count": 1},
            }
        )
    append_compiled_system_stage(tmp_path, "cycle-metrics", "context")
    projection = analyze(
        tmp_path,
        cycle_ledger.read_events(tmp_path, "cycle-metrics"),
        [],
        "task-1",
    )["compiler_efficiency"]
    assert projection["compiler_owner_totals"]["files_opened_count"] == 0
    assert projection["coordinator_transport_totals"]["work_order_bytes"] == 0
    assert projection["potential_model_work"]["model_visible_bytes"] == 0
    assert projection["actual_runtime"]["model_call_count"] == 0
    assert projection["contract_lint"]["unattested_runtime_claim_count"] == 0


def test_compiler_contract_lint_reads_each_cycle_contract_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def fake_cycle_contract(_root: Path, cycle_id: str) -> str:
        calls.append(cycle_id)
        return "enforced"

    monkeypatch.setattr(
        compiler_contract_lint,
        "_cycle_contract",
        fake_cycle_contract,
    )
    events = [
        {
            **_context_event(f"context-{index}"),
            "cycle_id": "cycle-cached",
            "event_kind": "compiled_system_event_ref",
            "producer_kind": "system_event_compiler",
        }
        for index in range(2)
    ]
    result = compiler_contract_lint.lint_compiler_contract(tmp_path, events)
    assert result["status"] == "pass"
    assert calls == ["cycle-cached"]


def test_compiler_contract_lint_reports_unmarked_v2_cycle_even_if_typed(
    tmp_path: Path,
) -> None:
    cycle_ledger.init_cycle(
        tmp_path, "cycle-typed-compat-debt", "task-1", "compat debt"
    )
    _remove_profile_to_simulate_existing_v2(tmp_path, "cycle-typed-compat-debt")
    events = [
        {
            **_context_event("typed-compat-context"),
            "cycle_id": "cycle-typed-compat-debt",
            "event_kind": "compiled_system_event_ref",
            "producer_kind": "system_event_compiler",
        },
        {
            "event_id": "typed-compat-route",
            "cycle_id": "cycle-typed-compat-debt",
            "step": "route_plan",
            "status": "complete",
            "task_id": "task-1",
            "event_kind": "compiled_system_event_ref",
            "producer_kind": "system_event_compiler",
        },
    ]
    result = compiler_contract_lint.lint_compiler_contract(tmp_path, events)
    assert result["status"] == "warn"
    assert result["historical_v2_read_only_debt_count"] == 1
    assert result["findings"][0]["code"] == "historical_v2_read_only_debt"
