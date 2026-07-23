from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

import pytest

from manage_task_state_index.state import prevalidation_compiler
from manage_task_state_index.state.scan_transition import apply_scan, prepare_scan
from orchestrate_task_cycle.cycle_ledger import (
    append_event as _public_append_event,
    init_cycle as _init_cycle,
    read_events,
    read_events_raw,
    read_current_expanded,
)
from orchestrate_task_cycle.ledger.compiled_events import (
    append_compiled_stage_observation,
    append_compiled_system_stage,
    append_compiled_terminal_lifecycle,
)
from orchestrate_task_cycle.ledger.support import read_initialization_metadata
from orchestrate_task_cycle.ledger.semantic_seeds import (
    make_stage_observation_seed,
    make_terminal_lifecycle_seed,
)
from orchestrate_task_cycle.ledger.workflow_contract import workflow_contract_state
from orchestrate_task_cycle.profile_cycle_efficiency import analyze
from orchestrate_task_cycle.ledger.result_hydration import hydrate_result_event
from orchestrate_task_cycle.ledger.repository import append_compiled_binding
from orchestrate_task_cycle.stage import publication as stage_publication
from orchestrate_task_cycle.stage import (
    deterministic_commit as deterministic_commit_module,
    deterministic_receipt as deterministic_receipt_module,
)
from orchestrate_task_cycle.stage import v2_service as stage_v2_service
from orchestrate_task_cycle.stage.artifact_store import (
    load_compiler_artifact,
    load_routing_receipt,
    load_stage_input,
    load_usage_observation,
    write_compiler_artifact,
    write_stage_input,
)
from orchestrate_task_cycle.stage.builder import ResultBuilder
from orchestrate_task_cycle.stage.input_compilers import (
    OWNER_RESULT_PRODUCER_TARGETS,
    SEMANTIC_PRODUCER_TARGETS,
    compile_routing,
    publish_owner_result,
    publish_semantic,
    publish_usage_observation,
)
from orchestrate_task_cycle.stage.preparation_store import publish_preparation
from orchestrate_task_cycle.stage.contracts import (
    canonical_bytes,
    canonical_sha256,
    preparation_identity,
)
from orchestrate_task_cycle.stage.executor_registry import EXECUTOR_REGISTRY
from orchestrate_task_cycle.stage.deterministic_dispatch import dispatch_deterministic
from orchestrate_task_cycle.stage.publication import publish_result
from orchestrate_task_cycle.stage.service import (
    advance_stage,
    execute_deterministic_stage,
    prepare_stage,
    submit_stage,
)
from orchestrate_task_cycle.stage.v2_specs import (
    DETERMINISTIC_TARGETS,
    HYBRID_TARGETS,
)
from orchestrate_task_cycle.stage.specs import TARGET_COMPILE_SPECS
from orchestrate_task_cycle.stage import v2_context
from orchestrate_task_cycle.transition.constants import ORDER
from compiler_first_fixture_support import (
    append_fixture_event,
    create_sealed_legacy_v1_cycle,
)


def init_cycle(*args, **kwargs):
    return _init_cycle(*args, **kwargs)


def append_event(root: Path, cycle_id: str, event: dict) -> dict:
    """Use real system producers and test-only synthetic owner predecessors."""

    if workflow_contract_state(read_initialization_metadata(root, cycle_id)) != "enforced":
        return _public_append_event(root, cycle_id, event)
    step = str(event.get("step") or "")
    if step in {"context", "route_plan", "result_contract", "ledger_append"}:
        return append_compiled_system_stage(root, cycle_id, step)
    elif step == "run":
        observation = dict(event)
        for field in ("step", "status", "event_id"):
            observation.pop(field, None)
        observation.setdefault("observation_kind", "test_stage_observation")
        return append_compiled_stage_observation(
            root, cycle_id, make_stage_observation_seed(observation)
        )
    elif step == "report":
        semantic = dict(event)
        for field in ("step", "status", "event_id"):
            semantic.pop(field, None)
        return append_compiled_terminal_lifecycle(
            root, cycle_id, make_terminal_lifecycle_seed(semantic)
        )
    return append_fixture_event(root, cycle_id, event)


def _write_json(root: Path, name: str, value: dict) -> tuple[str, str]:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode() + b"\n"
    path.write_bytes(payload)
    return path.relative_to(root).as_posix(), hashlib.sha256(payload).hexdigest()


def _file_tree(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


def _cycle(root: Path, cycle_id: str = "cycle-v3") -> str:
    (root / "task.md").write_text("# Task\n\nCompiler v3.\n", encoding="utf-8")
    initialized = init_cycle(root, cycle_id, "task-v3", "compiler v3")
    assert initialized["initialization"]["stage_compiler_protocol_version"] == 2
    assert initialized["initialization"]["stage_preparation_schema_version"] == 3
    advance_stage(root, cycle_id, apply=True, max_steps=1)
    return cycle_id


def _prime(root: Path, cycle_id: str, target: str) -> None:
    existing = {event["step"] for event in read_events(root, cycle_id)}
    for step in ORDER:
        if step == target:
            break
        if step in existing:
            continue
        append_event(
            root,
            cycle_id,
            {
                "step": step,
                "status": "completed",
                "event_id": f"fixture-v3-{target}-{step}",
                "task_id": "task-v3",
                "reason": "v3 dependency fixture",
            },
        )


def _init_git_workspace(root: Path) -> None:
    (root / "source.py").write_text("VALUE = 1\n", encoding="utf-8")
    for arguments in (
        ("init", "-q"),
        ("config", "user.email", "compiler-test@example.invalid"),
        ("config", "user.name", "Compiler Test"),
        ("add", "task.md", "source.py"),
        ("commit", "-qm", "base"),
    ):
        subprocess.run(["git", *arguments], cwd=root, check=True)


def _routing_receipt(
    root: Path, cycle_id: str, target: str, preparation: dict
) -> tuple[str, str]:
    del cycle_id, target
    published = publish_preparation(root, preparation)
    compiled = compile_routing(
        root,
        published["preparation_ref"],
        published["preparation_sha256"],
        "code_worker",
    )
    binding = compiled["routing_binding"]
    return binding["ref"], binding["sha256"]


def _deterministic_owner_binding(
    root: Path,
    preparation: dict,
    *,
    commit: bool = False,
) -> dict:
    prediction = dispatch_deterministic(root, preparation)
    assert prediction.get("status") != "block", prediction
    if commit:
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
    return write_stage_input(
        root,
        str(preparation["cycle_id"]),
        str(preparation["target"]),
        "owner_result",
        prediction["raw_owner_result"],
        preparation=preparation,
    )


def _deterministic_commit_args(owner: dict) -> dict[str, str]:
    binding = owner["deterministic_commit_binding"]
    return {
        "deterministic_commit_ref": binding["ref"],
        "deterministic_commit_sha256": binding["sha256"],
    }


def _index_submission_inputs(
    root: Path, cycle_id: str
) -> tuple[dict, dict, dict]:
    target = "index"
    _prime(root, cycle_id, target)
    scan_preparation = prepare_scan(
        root, at="2026-07-23T12:00:00+09:00"
    )
    scan = apply_scan(root, scan_preparation["compilation_binding"])
    preparation = prepare_stage(
        root, cycle_id, target, persist_compiler_artifacts=True
    )
    published = publish_preparation(root, preparation)
    source = scan["owner_result_binding"]
    owner = publish_owner_result(
        root,
        published["preparation_ref"],
        published["preparation_sha256"],
        source_ref=source["ref"],
        source_sha256=source["sha256"],
    )["owner_result_binding"]
    routing = compile_routing(
        root,
        published["preparation_ref"],
        published["preparation_sha256"],
        "id_index",
    )["routing_binding"]
    return preparation, owner, routing


def test_executor_registry_is_closed_for_exact_7_16_4_partition() -> None:
    deterministic = {
        target
        for target, spec in EXECUTOR_REGISTRY.items()
        if spec.executor_kind == "deterministic"
    }
    hybrid = {
        target
        for target, spec in EXECUTOR_REGISTRY.items()
        if spec.executor_kind == "hybrid"
    }
    owner = set(EXECUTOR_REGISTRY) - deterministic - hybrid

    assert deterministic == set(DETERMINISTIC_TARGETS)
    assert hybrid == set(HYBRID_TARGETS)
    assert (len(deterministic), len(owner), len(hybrid)) == (7, 16, 4)
    for spec in EXECUTOR_REGISTRY.values():
        assert spec.command_id
        assert spec.input_selector_id
        assert spec.output_adapter_id
        assert spec.side_effect_class
        if spec.executor_kind == "deterministic":
            assert spec.routing_policy_id is None
            assert spec.allowed_routing_profiles == ()
        elif spec.routing_required:
            assert spec.routing_policy_id == "configured-tiered-routing-v3"
            assert spec.allowed_routing_profiles


def test_preparation_bound_producer_registry_covers_all_20_model_targets() -> None:
    model_targets = {
        target
        for target, registered in EXECUTOR_REGISTRY.items()
        if registered.executor_kind != "deterministic"
    }
    assert OWNER_RESULT_PRODUCER_TARGETS == model_targets
    assert len(OWNER_RESULT_PRODUCER_TARGETS) == 20
    assert SEMANTIC_PRODUCER_TARGETS == set(HYBRID_TARGETS)
    assert len(SEMANTIC_PRODUCER_TARGETS) == 4
    assert all(
        TARGET_COMPILE_SPECS[target].owner_receipt_fields
        for target in OWNER_RESULT_PRODUCER_TARGETS
    )


def test_owner_and_hybrid_semantic_publishers_derive_exact_v2_wrappers(
    tmp_path: Path,
) -> None:
    owner_root = tmp_path / "owner"
    owner_root.mkdir()
    owner_cycle = _cycle(owner_root, "cycle-owner-producer")
    owner_target = "validation_scope_plan"
    _prime(owner_root, owner_cycle, owner_target)
    owner_preparation = prepare_stage(
        owner_root,
        owner_cycle,
        owner_target,
        persist_compiler_artifacts=True,
    )
    owner_publication = publish_preparation(owner_root, owner_preparation)
    owner_body = {
        field: f"owner-{field}"
        for field in TARGET_COMPILE_SPECS[
            owner_target
        ].owner_receipt_fields
    }
    owner_output = publish_owner_result(
        owner_root,
        owner_publication["preparation_ref"],
        owner_publication["preparation_sha256"],
        owner_body,
    )
    owner_binding = owner_output["owner_result_binding"]
    loaded_owner, _ = load_stage_input(
        owner_root,
        owner_binding["ref"],
        owner_binding["sha256"],
        cycle_id=owner_cycle,
        target=owner_target,
        input_kind="owner_result",
        preparation_id=owner_preparation["preparation_id"],
        state_fingerprint=owner_preparation["state_fingerprint"],
    )
    owner_wrapper = json.loads(
        (owner_root / owner_binding["ref"]).read_text(encoding="utf-8")
    )
    assert loaded_owner["owner_result"] == owner_body
    assert owner_wrapper["schema_version"] == 2
    assert owner_wrapper["preparation_id"] == owner_preparation["preparation_id"]

    semantic_root = tmp_path / "semantic"
    semantic_root.mkdir()
    semantic_cycle = _cycle(semantic_root, "cycle-semantic-producer")
    semantic_target = "qualitative_review"
    _prime(semantic_root, semantic_cycle, semantic_target)
    semantic_preparation = prepare_stage(
        semantic_root,
        semantic_cycle,
        semantic_target,
        persist_compiler_artifacts=True,
    )
    semantic_publication = publish_preparation(
        semantic_root, semantic_preparation
    )
    semantic_body = {
        field: f"semantic-{field}"
        for field in TARGET_COMPILE_SPECS[
            semantic_target
        ].semantic_fields
    }
    semantic_output = publish_semantic(
        semantic_root,
        semantic_publication["preparation_ref"],
        semantic_publication["preparation_sha256"],
        semantic_body,
    )
    semantic_binding = semantic_output["semantic_binding"]
    loaded_semantic, _ = load_stage_input(
        semantic_root,
        semantic_binding["ref"],
        semantic_binding["sha256"],
        cycle_id=semantic_cycle,
        target=semantic_target,
        input_kind="semantic",
        preparation_id=semantic_preparation["preparation_id"],
        state_fingerprint=semantic_preparation["state_fingerprint"],
    )
    assert loaded_semantic == {
        "semantic": semantic_body,
        "reasoned_not_applicable": {},
    }


def test_routing_and_usage_producers_are_bound_but_usage_stays_unverified(
    tmp_path: Path,
) -> None:
    cycle_id = _cycle(tmp_path, "cycle-routing-producer")
    target = "validation_set_plan"
    _prime(tmp_path, cycle_id, target)
    preparation = prepare_stage(
        tmp_path, cycle_id, target, persist_compiler_artifacts=True
    )
    published = publish_preparation(tmp_path, preparation)
    routing_output = compile_routing(
        tmp_path,
        published["preparation_ref"],
        published["preparation_sha256"],
        "validation_set",
    )
    routing_binding = routing_output["routing_binding"]
    route, _ = load_routing_receipt(
        tmp_path,
        routing_binding["ref"],
        routing_binding["sha256"],
        cycle_id=cycle_id,
        target=target,
        preparation_id=preparation["preparation_id"],
        state_fingerprint=preparation["state_fingerprint"],
    )
    assert route["schema_version"] == 2
    assert route["policy_id"] == "configured-tiered-routing-v3"
    assert route["model_configuration_status"] == "reference_only"

    usage_output = publish_usage_observation(
        tmp_path,
        published["preparation_ref"],
        published["preparation_sha256"],
        {
            "provider_id": "provider",
            "runtime_id": "runtime",
            "model_id": "model_ref:balanced",
            "request_id": "request",
            "input_tokens": 100,
            "cached_input_tokens": 20,
            "output_tokens": 10,
        },
    )
    usage_binding = usage_output["usage_binding"]
    usage, _ = load_usage_observation(
        tmp_path,
        usage_binding["ref"],
        usage_binding["sha256"],
        cycle_id=cycle_id,
        target=target,
        preparation_id=preparation["preparation_id"],
        state_fingerprint=preparation["state_fingerprint"],
    )
    assert usage_output["usage_aggregate_eligible"] is False
    assert usage["usage_aggregate_eligible"] is False
    assert usage["usage_provenance_status"] == "caller_asserted_unverified"


def test_enforced_input_loaders_reject_tamper_and_byte_identical_copy(
    tmp_path: Path,
) -> None:
    cycle_id = _cycle(tmp_path, "cycle-routing-copy")
    target = "validation_set_plan"
    _prime(tmp_path, cycle_id, target)
    preparation = prepare_stage(
        tmp_path, cycle_id, target, persist_compiler_artifacts=True
    )
    published = publish_preparation(tmp_path, preparation)
    output = compile_routing(
        tmp_path,
        published["preparation_ref"],
        published["preparation_sha256"],
        "validation_set",
    )
    binding = output["routing_binding"]
    source = tmp_path / binding["ref"]
    copied = tmp_path / ".task/copied-routing.json"
    copied.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, copied)
    with pytest.raises(ValueError, match="producer CAS"):
        load_routing_receipt(
            tmp_path,
            copied.relative_to(tmp_path).as_posix(),
            binding["sha256"],
            cycle_id=cycle_id,
            target=target,
            preparation_id=preparation["preparation_id"],
            state_fingerprint=preparation["state_fingerprint"],
        )
    source.write_text("{}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="digest"):
        load_routing_receipt(
            tmp_path,
            binding["ref"],
            binding["sha256"],
            cycle_id=cycle_id,
            target=target,
            preparation_id=preparation["preparation_id"],
            state_fingerprint=preparation["state_fingerprint"],
        )


def test_invalid_stage_producer_inputs_do_not_write(tmp_path: Path) -> None:
    cycle_id = _cycle(tmp_path, "cycle-producer-no-write")
    target = "qualitative_review"
    _prime(tmp_path, cycle_id, target)
    preparation = prepare_stage(
        tmp_path, cycle_id, target, persist_compiler_artifacts=True
    )
    published = publish_preparation(tmp_path, preparation)
    before = {
        path.relative_to(tmp_path).as_posix(): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }
    invalid_calls = (
        lambda: publish_owner_result(
            tmp_path,
            published["preparation_ref"],
            published["preparation_sha256"],
            {},
        ),
        lambda: publish_semantic(
            tmp_path,
            published["preparation_ref"],
            published["preparation_sha256"],
            {"invented": True},
        ),
        lambda: compile_routing(
            tmp_path,
            published["preparation_ref"],
            published["preparation_sha256"],
            "not-a-profile",
        ),
        lambda: publish_usage_observation(
            tmp_path,
            published["preparation_ref"],
            published["preparation_sha256"],
            {},
        ),
    )
    for invalid in invalid_calls:
        with pytest.raises(ValueError):
            invalid()
        after = {
            path.relative_to(tmp_path).as_posix(): path.read_bytes()
            for path in tmp_path.rglob("*")
            if path.is_file()
        }
        assert after == before


def test_sealed_protocol_v1_keeps_raw_path_diagnostics(tmp_path: Path) -> None:
    (tmp_path / "task.md").write_text("# Legacy task\n", encoding="utf-8")
    cycle_id = "cycle-v1-stage-input-diagnostic"
    create_sealed_legacy_v1_cycle(
        tmp_path,
        cycle_id,
        "task-v1",
        "sealed v1 diagnostic",
    )
    ref, digest = _write_json(
        tmp_path,
        ".task/legacy-owner.json",
        {
            "schema_version": 1,
            "artifact_kind": "stage_owner_result",
            "cycle_id": cycle_id,
            "target": "governance",
            "result": {"changed_files": [], "evidence_paths": []},
        },
    )
    loaded, _ = load_stage_input(
        tmp_path,
        ref,
        digest,
        cycle_id=cycle_id,
        target="governance",
        input_kind="owner_result",
    )
    assert loaded["owner_result"]["changed_files"] == []


def test_index_submit_dry_run_never_publishes_post_audit_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cycle_id = _cycle(tmp_path, "cycle-index-dry-run")
    target = "index"
    preparation, owner, routing = _index_submission_inputs(
        tmp_path, cycle_id
    )
    lock = (
        tmp_path / ".task" / "cycle" / cycle_id / ".ledger.lock"
    )
    lock.unlink()
    before = {
        path.relative_to(tmp_path).as_posix(): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }

    def forbidden_writer(*_args, **_kwargs):
        raise AssertionError("dry-run reached the post-audit writer")

    monkeypatch.setattr(
        prevalidation_compiler, "publish_immutable", forbidden_writer
    )
    output = submit_stage(
        tmp_path,
        preparation,
        owner_result_ref=owner["ref"],
        owner_result_sha256=owner["sha256"],
        routing_ref=routing["ref"],
        routing_sha256=routing["sha256"],
        apply=False,
    )
    after = {
        path.relative_to(tmp_path).as_posix(): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }
    loaded, _ = load_stage_input(
        tmp_path,
        owner["ref"],
        owner["sha256"],
        cycle_id=cycle_id,
        target=target,
        input_kind="owner_result",
        preparation_id=preparation["preparation_id"],
        state_fingerprint=preparation["state_fingerprint"],
    )
    assert output["applied"] is False
    assert loaded["owner_result"]["post_audit_owner_result_binding"] is None
    assert before == after


@pytest.mark.parametrize("late_gate", ("transition", "result"))
def test_index_apply_late_gate_failure_publishes_no_auxiliary_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    late_gate: str,
) -> None:
    cycle_id = _cycle(tmp_path, f"cycle-index-late-{late_gate}")
    preparation, owner, routing = _index_submission_inputs(
        tmp_path, cycle_id
    )
    if late_gate == "transition":
        monkeypatch.setattr(
            stage_v2_service,
            "validate_submission_transition",
            lambda *_args, **_kwargs: {
                "status": "block",
                "findings": [{"code": "forced_transition_block"}],
            },
        )
    else:
        monkeypatch.setattr(
            stage_v2_service,
            "validate_submission_transition",
            lambda *_args, **_kwargs: {"status": "ok", "findings": []},
        )
        monkeypatch.setattr(
            stage_v2_service,
            "validate_result",
            lambda target, _result, mode, _context: {
                "status": "block",
                "target": target,
                "mode": mode,
                "findings": [{"code": "forced_result_block"}],
                "missing_fields": [],
            },
        )

    def forbidden_writer(*_args, **_kwargs):
        raise AssertionError("late gate failure reached auxiliary publication")

    monkeypatch.setattr(
        prevalidation_compiler, "publish_immutable", forbidden_writer
    )
    before = {
        path.relative_to(tmp_path).as_posix(): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }
    output = submit_stage(
        tmp_path,
        preparation,
        owner_result_ref=owner["ref"],
        owner_result_sha256=owner["sha256"],
        routing_ref=routing["ref"],
        routing_sha256=routing["sha256"],
        apply=True,
    )
    after = {
        path.relative_to(tmp_path).as_posix(): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }
    assert output["status"] == "block"
    assert output["applied"] is False
    assert before == after


def test_goal_and_selection_context_are_loaded_only_by_declared_selectors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cycle_id = _cycle(tmp_path, "cycle-lazy-selectors")
    calls = {"goal": 0, "selection": 0}
    collect_goal = v2_context.collect_agent_goal
    collect_selection = v2_context.publication_status

    def observed_goal(*args, **kwargs):
        calls["goal"] += 1
        return collect_goal(*args, **kwargs)

    def observed_selection(*args, **kwargs):
        calls["selection"] += 1
        return collect_selection(*args, **kwargs)

    monkeypatch.setattr(v2_context, "collect_agent_goal", observed_goal)
    monkeypatch.setattr(v2_context, "publication_status", observed_selection)

    v2_context.collect_selected_context(
        tmp_path,
        cycle_id,
        TARGET_COMPILE_SPECS["authority"],
        max_files=12,
        max_paths=40,
    )
    assert calls == {"goal": 0, "selection": 0}

    v2_context.collect_selected_context(
        tmp_path,
        cycle_id,
        TARGET_COMPILE_SPECS["derive"],
        max_files=12,
        max_paths=40,
    )
    assert calls == {"goal": 1, "selection": 1}


@pytest.mark.parametrize("target", sorted(DETERMINISTIC_TARGETS))
def test_v3_deterministic_preparations_have_no_model_context_or_work_order(
    tmp_path: Path, target: str
) -> None:
    cycle_id = _cycle(tmp_path, f"cycle-{target}")
    _prime(tmp_path, cycle_id, target)

    preparation = prepare_stage(tmp_path, cycle_id, target)

    assert preparation["schema_version"] == 3
    assert preparation["executor_kind"] == "deterministic"
    assert preparation["model_call_required"] is False
    assert preparation["compiler_metrics"]["model_visible_bytes"] == 0
    assert preparation["compiler_metrics"]["model_authored_mechanical_bytes"] == 0
    assert "machine_input_binding" in preparation
    assert "context_binding" not in preparation
    assert "work_order_binding" not in preparation


@pytest.mark.parametrize("target", sorted(DETERMINISTIC_TARGETS))
def test_every_registered_deterministic_renderer_emits_exact_owner_binding(
    tmp_path: Path, target: str
) -> None:
    cycle_id = _cycle(tmp_path, f"cycle-dispatch-{target}")
    _prime(tmp_path, cycle_id, target)
    preparation = prepare_stage(
        tmp_path,
        cycle_id,
        target,
        persist_compiler_artifacts=True,
    )

    dispatched = dispatch_deterministic(tmp_path, preparation)
    binding = _deterministic_owner_binding(tmp_path, preparation)
    owner, reopened = load_stage_input(
        tmp_path,
        binding["ref"],
        binding["sha256"],
        cycle_id=cycle_id,
        target=target,
        input_kind="owner_result",
        preparation_id=preparation["preparation_id"],
        state_fingerprint=preparation["state_fingerprint"],
    )

    assert isinstance(owner["owner_result"], dict)
    assert reopened["sha256"] == binding["sha256"]
    assert dispatched["model_call_count"] == 0
    assert dispatched["model_visible_bytes"] == 0
    if target == "cycle_efficiency_profile":
        assert "compiler_efficiency" in owner["owner_result"]


def test_v3_advance_auto_executes_deterministic_scan_and_compacts_ledger(
    tmp_path: Path,
) -> None:
    cycle_id = _cycle(tmp_path)
    append_event(
        tmp_path,
        cycle_id,
        {
            "step": "authority",
            "status": "completed",
            "event_id": "authority-v3",
            "task_id": "task-v3",
            "reason": "authority fixture",
        },
    )

    output = advance_stage(tmp_path, cycle_id, apply=True, max_steps=2)
    raw = read_events_raw(tmp_path, cycle_id)
    hydrated = read_events(tmp_path, cycle_id)
    raw_scan = next(event for event in raw if event["step"] == "repo_skill_adapter_scan")
    scan = next(event for event in hydrated if event["step"] == "repo_skill_adapter_scan")

    assert output["actions"][0]["kind"] == "execute_deterministic"
    assert output["actions"][0]["execution"]["model_call_count"] == 0
    assert raw_scan["format_version"] == 2
    assert raw_scan["event_kind"] == "compiled_stage_result_ref"
    assert raw_scan["deterministic_commit_binding"]["ref"].startswith(
        f".task/cycle/{cycle_id}/compiler/"
        "deterministic_commit_receipt/sha256/"
    )
    assert raw_scan["compiler_metrics"]["compact_payload_bytes"] > 0
    assert "repo_skill_adapter_packet" not in raw_scan
    assert len(json.dumps(raw_scan, ensure_ascii=False).encode()) < 16 * 1024
    assert scan["hydrated_from_compact_result"] is True
    assert scan["adapter_scan_status"] in {"pass", "block"}
    profile = analyze(tmp_path, hydrated, [], "task-v3")
    assert profile["compiler_efficiency"]["structural_totals"][
        "compact_payload_bytes"
    ] == sum(
        int((event.get("compiler_metrics") or {}).get("compact_payload_bytes") or 0)
        for event in raw
    )


def test_deterministic_execute_dry_run_writes_nothing(tmp_path: Path) -> None:
    cycle_id = _cycle(tmp_path)
    append_event(
        tmp_path,
        cycle_id,
        {
            "step": "authority",
            "status": "completed",
            "event_id": "authority-dry-run",
            "task_id": "task-v3",
            "reason": "authority fixture",
        },
    )
    before = {
        path.relative_to(tmp_path).as_posix(): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }

    output = execute_deterministic_stage(
        tmp_path,
        cycle_id,
        "repo_skill_adapter_scan",
        apply=False,
    )
    after = {
        path.relative_to(tmp_path).as_posix(): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }

    assert output["status"] == "ready"
    assert output["applied"] is False
    assert output["model_call_count"] == 0
    assert before == after


@pytest.mark.parametrize("target", sorted(DETERMINISTIC_TARGETS))
def test_deterministic_late_gate_block_is_tree_write_free(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    target: str,
) -> None:
    cycle_id = _cycle(tmp_path, f"cycle-deterministic-block-{target}")
    _prime(tmp_path, cycle_id, target)
    lock = tmp_path / ".task" / "cycle" / cycle_id / ".ledger.lock"
    lock.unlink()
    monkeypatch.setattr(
        "orchestrate_task_cycle.stage.gates.validate_submission_transition",
        lambda *_args, **_kwargs: {
            "status": "block",
            "findings": [{"code": "forced_transition_block"}],
        },
    )

    def forbidden_effect(*_args, **_kwargs):
        raise AssertionError("blocked deterministic stage committed an effect")

    monkeypatch.setattr(
        deterministic_commit_module, "atomic_write", forbidden_effect
    )
    before = _file_tree(tmp_path)

    output = execute_deterministic_stage(
        tmp_path,
        cycle_id,
        target,
        apply=True,
    )

    assert output["status"] == "block"
    assert output["applied"] is False
    assert _file_tree(tmp_path) == before


def test_deterministic_commit_has_no_mint_or_callback_bypass(
    tmp_path: Path,
) -> None:
    cycle_id = _cycle(tmp_path, "cycle-deterministic-permit")
    target = "dashboard"
    _prime(tmp_path, cycle_id, target)
    preparation = prepare_stage(
        tmp_path,
        cycle_id,
        target,
        persist_compiler_artifacts=True,
    )
    prediction = dispatch_deterministic(tmp_path, preparation)
    before = _file_tree(tmp_path)

    assert not hasattr(deterministic_commit_module, "_CommitPermit")
    assert not hasattr(deterministic_commit_module, "_mint_commit_permit")
    assert not hasattr(deterministic_commit_module, "_commit_deterministic")
    with pytest.raises(TypeError, match="unexpected keyword"):
        deterministic_commit_module.commit_deterministic_gated(
            tmp_path,
            preparation,
            prediction,
            transition_validator=lambda *_args: {"status": "ok"},
        )
    changed_prediction = copy.deepcopy(prediction)
    changed_prediction["effect_plan"]["content"] += "\nforged\n"
    with pytest.raises(ValueError, match="prediction changed"):
        deterministic_commit_module.commit_deterministic_gated(
            tmp_path,
            preparation,
            changed_prediction,
        )

    assert _file_tree(tmp_path) == before
    assert deterministic_commit_module.__all__ == [
        "commit_deterministic_gated"
    ]


@pytest.mark.parametrize("target", sorted(DETERMINISTIC_TARGETS))
def test_deterministic_generic_submit_without_receipt_is_tree_write_free(
    tmp_path: Path,
    target: str,
) -> None:
    cycle_id = _cycle(tmp_path, f"cycle-receipt-missing-{target}")
    _prime(tmp_path, cycle_id, target)
    preparation = prepare_stage(
        tmp_path,
        cycle_id,
        target,
        persist_compiler_artifacts=True,
    )
    prediction = dispatch_deterministic(tmp_path, preparation)
    owner = write_stage_input(
        tmp_path,
        cycle_id,
        target,
        "owner_result",
        prediction["raw_owner_result"],
        preparation=preparation,
    )
    lock = tmp_path / ".task" / "cycle" / cycle_id / ".ledger.lock"
    lock.unlink()
    before = _file_tree(tmp_path)

    output = submit_stage(
        tmp_path,
        preparation,
        owner_result_ref=owner["ref"],
        owner_result_sha256=owner["sha256"],
        apply=True,
    )

    assert output["status"] == "block"
    assert output["stop_reason"] == "deterministic_commit_receipt_missing"
    assert _file_tree(tmp_path) == before


def test_self_hashed_forged_deterministic_receipt_is_tree_write_free(
    tmp_path: Path,
) -> None:
    cycle_id = _cycle(tmp_path, "cycle-forged-deterministic-receipt")
    target = "repo_skill_adapter_scan"
    _prime(tmp_path, cycle_id, target)
    preparation = prepare_stage(
        tmp_path,
        cycle_id,
        target,
        persist_compiler_artifacts=True,
    )
    forged = copy.deepcopy(dispatch_deterministic(tmp_path, preparation))
    forged_packet = forged["raw_owner_result"]
    forged_packet["adapter_count"] = 999
    body = {
        key: item
        for key, item in forged_packet.items()
        if key != "scan_packet_sha256"
    }
    forged_packet["scan_packet_sha256"] = hashlib.sha256(
        canonical_bytes(body) + b"\n"
    ).hexdigest()
    owner = write_stage_input(
        tmp_path,
        cycle_id,
        target,
        "owner_result",
        forged_packet,
        preparation=preparation,
    )
    judgment, exact_owner = load_stage_input(
        tmp_path,
        owner["ref"],
        owner["sha256"],
        cycle_id=cycle_id,
        target=target,
        input_kind="owner_result",
        preparation_id=preparation["preparation_id"],
        state_fingerprint=preparation["state_fingerprint"],
    )
    result = ResultBuilder().build(preparation, judgment)
    receipt = deterministic_receipt_module._render_receipt(
        preparation,
        forged,
        canonical_sha256(result),
        exact_owner,
    )
    forged_receipt = write_compiler_artifact(
        tmp_path,
        cycle_id,
        deterministic_receipt_module.RECEIPT_ARTIFACT_TYPE,
        receipt,
    )
    lock = tmp_path / ".task" / "cycle" / cycle_id / ".ledger.lock"
    lock.unlink()
    before = _file_tree(tmp_path)

    output = submit_stage(
        tmp_path,
        preparation,
        owner_result_ref=owner["ref"],
        owner_result_sha256=owner["sha256"],
        deterministic_commit_ref=forged_receipt["ref"],
        deterministic_commit_sha256=forged_receipt["sha256"],
        apply=True,
    )

    assert output["status"] == "block"
    assert output["stop_reason"] == "deterministic_commit_receipt_invalid"
    assert _file_tree(tmp_path) == before


def test_deterministic_receipt_scope_mutations_are_tree_write_free(
    tmp_path: Path,
) -> None:
    cycle_id = _cycle(tmp_path, "cycle-deterministic-receipt-scope")
    target = "repo_skill_adapter_scan"
    _prime(tmp_path, cycle_id, target)
    preparation = prepare_stage(
        tmp_path,
        cycle_id,
        target,
        persist_compiler_artifacts=True,
    )
    owner = _deterministic_owner_binding(
        tmp_path,
        preparation,
        commit=True,
    )
    original_binding = owner["deterministic_commit_binding"]
    original = json.loads(
        (tmp_path / original_binding["ref"]).read_text(encoding="utf-8")
    )
    variants: list[dict] = []
    for mutate in (
        lambda row: row.update({"cycle_id": "other-cycle"}),
        lambda row: row.update({"target": "report"}),
        lambda row: row.update({"preparation_id": "stageprep-forged"}),
        lambda row: row.update({"state_fingerprint": "0" * 64}),
        lambda row: row["machine_input_binding"].update(
            {"sha256": "1" * 64}
        ),
        lambda row: row["executor_spec"].update(
            {"command_id": "forged.command.v1"}
        ),
        lambda row: row.update({"prediction_sha256": "2" * 64}),
        lambda row: row.update({"result_sha256": "3" * 64}),
        lambda row: row["owner_result_binding"].update(
            {"sha256": "4" * 64}
        ),
        lambda row: row.update(
            {
                "effect_plan": {
                    "kind": "write_text",
                    "ref": "forged",
                    "encoding": "utf-8",
                    "content_sha256": "5" * 64,
                    "size_bytes": 1,
                }
            }
        ),
    ):
        value = copy.deepcopy(original)
        mutate(value)
        variants.append(
            write_compiler_artifact(
                tmp_path,
                cycle_id,
                deterministic_receipt_module.RECEIPT_ARTIFACT_TYPE,
                value,
            )
        )
    copied = tmp_path / ".task" / "copied-deterministic-receipt.json"
    shutil.copyfile(tmp_path / original_binding["ref"], copied)
    variants.append(
        {
            "ref": copied.relative_to(tmp_path).as_posix(),
            "sha256": original_binding["sha256"],
        }
    )
    lock = tmp_path / ".task" / "cycle" / cycle_id / ".ledger.lock"
    lock.unlink()
    before = _file_tree(tmp_path)

    for variant in variants:
        output = submit_stage(
            tmp_path,
            preparation,
            owner_result_ref=owner["ref"],
            owner_result_sha256=owner["sha256"],
            deterministic_commit_ref=variant["ref"],
            deterministic_commit_sha256=variant["sha256"],
            apply=True,
        )
        assert output["status"] == "block"
        assert (
            output["stop_reason"]
            == "deterministic_commit_receipt_invalid"
        )
        assert _file_tree(tmp_path) == before


def test_non_deterministic_stage_forbids_commit_receipt_prelock(
    tmp_path: Path,
) -> None:
    cycle_id = _cycle(tmp_path, "cycle-inapplicable-commit-receipt")
    preparation = prepare_stage(
        tmp_path,
        cycle_id,
        "authority",
        persist_compiler_artifacts=True,
    )
    lock = tmp_path / ".task" / "cycle" / cycle_id / ".ledger.lock"
    lock.unlink()
    before = _file_tree(tmp_path)

    output = submit_stage(
        tmp_path,
        preparation,
        deterministic_commit_ref=".task/forged.json",
        deterministic_commit_sha256="0" * 64,
        apply=True,
    )

    assert output["status"] == "block"
    assert (
        output["stop_reason"]
        == "deterministic_commit_receipt_inapplicable"
    )
    assert _file_tree(tmp_path) == before


def test_dashboard_effect_tamper_blocks_replay_before_any_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cycle_id = _cycle(tmp_path, "cycle-dashboard-effect-tamper")
    target = "dashboard"
    _prime(tmp_path, cycle_id, target)
    preparation = prepare_stage(
        tmp_path,
        cycle_id,
        target,
        persist_compiler_artifacts=True,
    )
    monkeypatch.setattr(
        stage_v2_service,
        "validate_submission_transition",
        lambda *_args, **_kwargs: {"status": "ok", "findings": []},
    )
    monkeypatch.setattr(
        "orchestrate_task_cycle.stage.gates.validate_submission_transition",
        lambda *_args, **_kwargs: {"status": "ok", "findings": []},
    )
    owner = _deterministic_owner_binding(
        tmp_path,
        preparation,
        commit=True,
    )
    published = submit_stage(
        tmp_path,
        preparation,
        owner_result_ref=owner["ref"],
        owner_result_sha256=owner["sha256"],
        **_deterministic_commit_args(owner),
        apply=True,
    )
    assert published["applied"] is True
    dashboard = tmp_path / ".task" / "cycle" / cycle_id / "dashboard.md"
    dashboard.write_text("tampered dashboard\n", encoding="utf-8")
    lock = tmp_path / ".task" / "cycle" / cycle_id / ".ledger.lock"
    lock.unlink()
    before = _file_tree(tmp_path)

    output = submit_stage(
        tmp_path,
        preparation,
        owner_result_ref=owner["ref"],
        owner_result_sha256=owner["sha256"],
        **_deterministic_commit_args(owner),
        apply=True,
    )

    assert output["status"] == "block"
    assert output["stop_reason"] == "deterministic_commit_receipt_invalid"
    assert _file_tree(tmp_path) == before


def test_direct_result_publication_requires_deterministic_receipt_prewrite(
    tmp_path: Path,
) -> None:
    cycle_id = _cycle(tmp_path, "cycle-direct-result-no-receipt")
    target = "repo_skill_adapter_scan"
    _prime(tmp_path, cycle_id, target)
    preparation = prepare_stage(
        tmp_path,
        cycle_id,
        target,
        persist_compiler_artifacts=True,
    )
    prediction = dispatch_deterministic(tmp_path, preparation)
    owner = write_stage_input(
        tmp_path,
        cycle_id,
        target,
        "owner_result",
        prediction["raw_owner_result"],
        preparation=preparation,
    )
    judgment, exact_owner = load_stage_input(
        tmp_path,
        owner["ref"],
        owner["sha256"],
        cycle_id=cycle_id,
        target=target,
        input_kind="owner_result",
        preparation_id=preparation["preparation_id"],
        state_fingerprint=preparation["state_fingerprint"],
    )
    result = ResultBuilder().build(preparation, judgment)
    before = _file_tree(tmp_path)

    with pytest.raises(
        ValueError,
        match="omits required exact input bindings",
    ):
        publish_result(
            tmp_path,
            cycle_id,
            preparation,
            result,
            canonical_sha256(result),
            input_bindings={"owner_result_binding": exact_owner},
        )

    assert _file_tree(tmp_path) == before


def test_compact_result_hydrates_exact_cas_and_rejects_tamper(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    cycle_id = _cycle(tmp_path)
    append_event(
        tmp_path,
        cycle_id,
        {"step": "authority", "status": "completed", "event_id": "auth-cas"},
    )
    preparation = prepare_stage(
        tmp_path,
        cycle_id,
        "repo_skill_adapter_scan",
        persist_compiler_artifacts=True,
    )
    owner = _deterministic_owner_binding(
        tmp_path, preparation, commit=True
    )
    submitted = submit_stage(
        tmp_path,
        preparation,
        apply=True,
        owner_result_ref=owner["ref"],
        owner_result_sha256=owner["sha256"],
        **_deterministic_commit_args(owner),
    )
    assert submitted["applied"] is True

    ledger = tmp_path / ".task" / "cycle" / cycle_id / "stage.jsonl"
    assert b"repo_skill_adapter_packet" not in ledger.read_bytes()
    hydrated = read_events(tmp_path, cycle_id)[-1]
    assert hydrated["adapter_scan_status"] in {"pass", "block"}
    assert isinstance(hydrated["repo_skill_adapter_packet"], dict)
    with monkeypatch.context() as relative_root:
        relative_root.chdir(tmp_path)
        relative = read_events(Path("."), cycle_id)[-1]
    assert relative["repo_skill_adapter_packet"] == hydrated[
        "repo_skill_adapter_packet"
    ]
    compact = read_events_raw(tmp_path, cycle_id)[-1]
    result_path = tmp_path / compact["result_artifact_ref"]

    for unsafe_ref in (
        compact["result_artifact_ref"].replace(".task/", ".task//", 1),
        compact["result_artifact_ref"].replace(".task/", ".task/./", 1),
        compact["result_artifact_ref"].replace("/", "\\", 1),
        compact["result_artifact_ref"].replace("cycle/", "cycle/\x00", 1),
    ):
        noncanonical = json.loads(json.dumps(compact))
        noncanonical["result_artifact_ref"] = unsafe_ref
        noncanonical["result_artifact_binding"]["ref"] = unsafe_ref
        noncanonical["artifacts"] = [unsafe_ref]
        with pytest.raises(ValueError, match="binding fields are invalid"):
            hydrate_result_event(tmp_path, cycle_id, noncanonical)

    forged_scalar = json.loads(json.dumps(compact))
    forged_scalar["quality_verdict"] = "forged-pass"
    forged_scalar["result_projection"] = {"quality_verdict": "forged-pass"}
    with pytest.raises(ValueError, match="scalar projection mismatch"):
        hydrate_result_event(tmp_path, cycle_id, forged_scalar)

    substituted = json.loads(json.dumps(compact))
    wrong_ref = result_path.with_name("result-repo_skill_adapter_scan-wrong.json")
    wrong_ref.write_bytes(result_path.read_bytes())
    wrong_relative = wrong_ref.relative_to(tmp_path).as_posix()
    substituted["result_artifact_ref"] = wrong_relative
    substituted["result_artifact_binding"]["ref"] = wrong_relative
    substituted["artifacts"] = [wrong_relative]
    with pytest.raises(ValueError, match="binding fields are invalid"):
        hydrate_result_event(tmp_path, cycle_id, substituted)

    wrong_scope_result = {"step": "dashboard", "dashboard_status": "rendered"}
    wrong_body_sha = canonical_sha256(wrong_scope_result)
    wrong_scope_payload = json.dumps(
        wrong_scope_result,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode() + b"\n"
    wrong_scope_path = result_path.with_name(
        f"result-repo_skill_adapter_scan-{wrong_body_sha}.json"
    )
    wrong_scope_path.write_bytes(wrong_scope_payload)
    wrong_scope_ref = wrong_scope_path.relative_to(tmp_path).as_posix()
    wrong_scope = json.loads(json.dumps(compact))
    wrong_scope.update(
        {
            "result_artifact_ref": wrong_scope_ref,
            "result_artifact_sha256": wrong_body_sha,
            "result_artifact_raw_sha256": hashlib.sha256(
                wrong_scope_payload
            ).hexdigest(),
            "result_projection": {},
            "artifacts": [wrong_scope_ref],
        }
    )
    wrong_scope["result_artifact_binding"] = {
        "ref": wrong_scope_ref,
        "sha256": wrong_scope["result_artifact_raw_sha256"],
        "size_bytes": len(wrong_scope_payload),
        "body_sha256": wrong_body_sha,
    }
    with pytest.raises(ValueError, match="body step does not match"):
        hydrate_result_event(tmp_path, cycle_id, wrong_scope)

    result_path.write_text("{}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="digest mismatch|size binding mismatch"):
        read_events(tmp_path, cycle_id)


def test_agent_target_requires_current_exact_routing_receipt(tmp_path: Path) -> None:
    cycle_id = _cycle(tmp_path)
    target = "validation_set_plan"
    _prime(tmp_path, cycle_id, target)
    preparation = prepare_stage(
        tmp_path, cycle_id, target, persist_compiler_artifacts=True
    )
    owner = write_stage_input(
        tmp_path,
        cycle_id,
        target,
        "owner_result",
        {},
        preparation=preparation,
    )

    with pytest.raises(ValueError, match="routing receipt presence"):
        submit_stage(
            tmp_path,
            preparation,
            owner_result_ref=owner["ref"],
            owner_result_sha256=owner["sha256"],
        )

    routing_ref, routing_sha = _write_json(
        tmp_path,
        ".task/routing.json",
        {
            "schema_version": 1,
            "artifact_kind": "stage_routing_receipt",
            "cycle_id": cycle_id,
            "target": target,
            "preparation_id": preparation["preparation_id"],
            "state_fingerprint": "0" * 64,
            "policy_id": "policy-v1",
            "profile_id": "model-effort-v1",
            "routing_tier": 3,
            "requested_model_ref": "balanced-profile",
            "requested_model": "gpt-5",
            "requested_reasoning_effort": "medium",
            "routing_reason_codes": ["routine_owner"],
        },
    )
    with pytest.raises(ValueError, match="producer CAS"):
        submit_stage(
            tmp_path,
            preparation,
            owner_result_ref=owner["ref"],
            owner_result_sha256=owner["sha256"],
            routing_ref=routing_ref,
            routing_sha256=routing_sha,
        )
    wrong_profile_ref, wrong_profile_sha = _write_json(
        tmp_path,
        ".task/routing-wrong-profile.json",
        {
            "schema_version": 1,
            "artifact_kind": "stage_routing_receipt",
            "cycle_id": cycle_id,
            "target": target,
            "preparation_id": preparation["preparation_id"],
            "state_fingerprint": preparation["state_fingerprint"],
            "policy_id": "configured-tiered-routing-v3",
            "profile_id": "commit",
            "routing_tier": 1,
            "requested_model_ref": "model_ref:balanced",
            "requested_model": "model_ref:balanced",
            "requested_reasoning_effort": "low",
            "routing_reason_codes": ["profile_default"],
        },
    )
    with pytest.raises(ValueError, match="producer CAS"):
        submit_stage(
            tmp_path,
            preparation,
            owner_result_ref=owner["ref"],
            owner_result_sha256=owner["sha256"],
            routing_ref=wrong_profile_ref,
            routing_sha256=wrong_profile_sha,
        )


def test_routed_usage_replay_rejects_a_different_exact_receipt(
    tmp_path: Path,
) -> None:
    cycle_id = _cycle(tmp_path)
    target = "validation_set_plan"
    _prime(tmp_path, cycle_id, target)
    preparation = prepare_stage(
        tmp_path, cycle_id, target, persist_compiler_artifacts=True
    )
    owner = write_stage_input(
        tmp_path,
        cycle_id,
        target,
        "owner_result",
        {
            "validation_set_need": "plan",
            "task_family": "compiler-efficiency",
            "oracle_strategy": "deterministic-contract-tests",
            "split_strategy": "not_applicable",
            "evidence_paths": ["task.md"],
        },
        preparation=preparation,
    )
    published = publish_preparation(tmp_path, preparation)
    routing_output = compile_routing(
        tmp_path,
        published["preparation_ref"],
        published["preparation_sha256"],
        "validation_set",
    )
    routing = routing_output["routing_binding"]
    routing_ref, routing_sha = routing["ref"], routing["sha256"]

    def usage(request_id: str, tokens: int) -> tuple[str, str]:
        output = publish_usage_observation(
            tmp_path,
            published["preparation_ref"],
            published["preparation_sha256"],
            {
                "provider_id": "openai",
                "runtime_id": "runtime-1",
                "model_id": "model_ref:balanced",
                "request_id": request_id,
                "input_tokens": tokens,
                "cached_input_tokens": 2,
                "output_tokens": 1,
            },
        )
        binding = output["usage_binding"]
        return binding["ref"], binding["sha256"]

    usage_a = usage("request-a", 10)
    first = submit_stage(
        tmp_path,
        preparation,
        owner_result_ref=owner["ref"],
        owner_result_sha256=owner["sha256"],
        routing_ref=routing_ref,
        routing_sha256=routing_sha,
        usage_ref=usage_a[0],
        usage_sha256=usage_a[1],
        apply=True,
    )
    assert first["applied"] is True
    assert first["compiler_metrics"]["usage_aggregate_eligible"] is False
    assert (
        first["compiler_metrics"]["usage_provenance_status"]
        == "caller_asserted_unverified"
    )
    assert "actual_model" not in first["event"]

    usage_b = usage("request-b", 11)
    with pytest.raises(ValueError, match="exact stage input bindings"):
        submit_stage(
            tmp_path,
            preparation,
            owner_result_ref=owner["ref"],
            owner_result_sha256=owner["sha256"],
            routing_ref=routing_ref,
            routing_sha256=routing_sha,
            usage_ref=usage_b[0],
            usage_sha256=usage_b[1],
            apply=True,
        )


def test_efficiency_profile_excludes_unattested_and_forged_usage_v2(
    tmp_path: Path,
) -> None:
    cycle_id = "cycle-metrics"
    v2_ref, v2_sha = _write_json(
        tmp_path,
        ".task/metrics-usage-v2.json",
        {
            "schema_version": 2,
            "artifact_kind": "model_usage_observation",
            "cycle_id": cycle_id,
            "target": "acceptance",
            "provider_id": "provider-a",
            "runtime_id": "runtime-a",
            "model_id": "model-a",
            "request_id": "request-a",
            "input_tokens": 100,
            "cached_input_tokens": 40,
            "output_tokens": 20,
        },
    )
    events = [
        {
            "cycle_id": cycle_id,
            "event_id": "compiler-metric-v2",
            "step": "acceptance",
            "status": "completed",
            "compiler_metrics": {
                "files_opened_count": 4,
                "files_written_count": 3,
                "context_bytes": 120,
                "work_order_bytes": 80,
                "model_visible_bytes": 80,
                "model_call_count": 1,
                "model_authored_mechanical_bytes": 0,
                "cas_newly_written_bytes": 200,
                "cas_reused_bytes": 50,
                "compact_payload_bytes": 300,
                "usage_receipt_ref": v2_ref,
                "usage_receipt_sha256": v2_sha,
                "usage_receipt_schema_version": 2,
                "usage_aggregate_eligible": True,
                "usage_provenance_status": "runtime_receipt_verified",
                "provider_id": "provider-a",
                "runtime_id": "runtime-a",
                "model_id": "model-a",
                "request_id": "request-a",
                "input_tokens": 100,
                "cached_input_tokens": 40,
                "output_tokens": 20,
            },
        },
        {
            "cycle_id": cycle_id,
            "event_id": "compiler-metric-v2-unattested",
            "step": "acceptance",
            "status": "completed",
            "compiler_metrics": {
                "usage_receipt_ref": v2_ref,
                "usage_receipt_sha256": v2_sha,
                "usage_receipt_schema_version": 2,
                "usage_aggregate_eligible": False,
                "usage_provenance_status": "caller_asserted_unverified",
                "provider_id": "provider-a",
                "runtime_id": "runtime-a",
                "model_id": "model-a",
                "request_id": "request-a",
                "input_tokens": 100,
                "cached_input_tokens": 40,
                "output_tokens": 20,
            },
        },
        {
            "cycle_id": cycle_id,
            "event_id": "compiler-metric-v1",
            "step": "governance",
            "status": "completed",
            "compiler_metrics": {
                "files_opened_count": 2,
                "model_visible_bytes": 500,
                "model_call_count": 1,
                "usage_receipt_schema_version": 1,
                "usage_aggregate_eligible": False,
                "usage_provenance_status": "legacy_unverified",
                "input_tokens": 999,
                "cached_input_tokens": 0,
                "output_tokens": 999,
            },
        },
        {
            "cycle_id": cycle_id,
            "event_id": "compiler-metric-forged",
            "step": "run",
            "status": "completed",
            "compiler_metrics": {
                "usage_receipt_ref": ".task/missing-usage.json",
                "usage_receipt_sha256": "f" * 64,
                "usage_receipt_schema_version": 2,
                "usage_aggregate_eligible": True,
                "provider_id": "forged-provider",
                "runtime_id": "forged-runtime",
                "model_id": "forged-model",
                "request_id": "forged-request",
                "input_tokens": 5000,
                "cached_input_tokens": 0,
                "output_tokens": 5000,
            },
        },
    ]

    projection = analyze(tmp_path, events, [], "task-v3")["compiler_efficiency"]

    assert projection["structural_totals"]["files_opened_count"] == 6
    assert projection["structural_totals"]["files_written_count"] == 3
    assert projection["structural_totals"]["model_visible_bytes"] == 580
    assert projection["structural_totals"]["model_call_count"] == 2
    assert projection["structural_totals"]["cas_newly_written_bytes"] == 200
    assert projection["structural_totals"]["compact_payload_bytes"] == 300
    assert projection["usage"]["verified_receipt_count"] == 0
    assert projection["usage"]["legacy_v1_excluded_count"] == 1
    assert projection["usage"]["unattested_v2_excluded_count"] == 1
    assert projection["usage"]["invalid_v2_excluded_count"] == 2
    assert projection["usage"]["aggregate_eligible"] is False
    assert projection["usage"]["input_tokens"] == 0
    assert projection["usage"]["cached_input_tokens"] == 0
    assert projection["usage"]["output_tokens"] == 0
    assert projection["runtime_comparison"]["status"] == "not_evaluated"
    assert (
        projection["runtime_comparison"]["reason"]
        == "trusted_runtime_attestation_not_available"
    )
    assert "saving" not in json.dumps(projection, sort_keys=True).lower()


def test_protocol_v1_result_keeps_full_format_v1_current_parity(
    tmp_path: Path,
) -> None:
    (tmp_path / "task.md").write_text("# Task\n\nLegacy.\n", encoding="utf-8")
    cycle_id = "cycle-v1-result"
    create_sealed_legacy_v1_cycle(
        tmp_path,
        cycle_id,
        "task-v1",
        "legacy result",
    )
    advance_stage(tmp_path, cycle_id, apply=True, max_steps=1)
    _prime(tmp_path, cycle_id, "repo_skill_adapter_scan")
    preparation = prepare_stage(tmp_path, cycle_id, "repo_skill_adapter_scan")
    result = {
        "step": "repo_skill_adapter_scan",
        "adapter_scan_status": "pass",
        "legacy_marker": "full-event-preserved",
    }

    publish_result(
        tmp_path,
        cycle_id,
        preparation,
        result,
        canonical_sha256(result),
    )

    assert read_events_raw(tmp_path, cycle_id)[-1]["format_version"] == 1
    assert read_events(tmp_path, cycle_id)[-1]["legacy_marker"] == "full-event-preserved"
    assert (
        read_current_expanded(tmp_path, cycle_id)["steps"][
            "repo_skill_adapter_scan"
        ]["legacy_marker"]
        == "full-event-preserved"
    )


def test_semantic_input_is_capped_at_exact_64kib(tmp_path: Path) -> None:
    cycle_id = _cycle(tmp_path)
    ref, digest = _write_json(
        tmp_path,
        ".task/oversize-semantic.json",
        {
            "schema_version": 1,
            "artifact_kind": "stage_semantic",
            "cycle_id": cycle_id,
            "target": "qualitative_review",
            "semantic": {"quality_verdict": "x" * (64 * 1024)},
        },
    )
    with pytest.raises(ValueError, match="byte budget exceeded"):
        load_stage_input(
            tmp_path,
            ref,
            digest,
            cycle_id=cycle_id,
            target="qualitative_review",
            input_kind="semantic",
        )


def test_semantic_wrapper_rejects_noncanonical_or_extra_top_level_fields(
    tmp_path: Path,
) -> None:
    cycle_id = "cycle-semantic-canonical"
    path = tmp_path / ".task" / "noncanonical-semantic.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (
        json.dumps(
            {
                "schema_version": 1,
                "artifact_kind": "stage_semantic",
                "cycle_id": cycle_id,
                "target": "qualitative_review",
                "semantic": {"quality_verdict": "pass"},
                "extra": "forbidden",
            },
            ensure_ascii=False,
            indent=2,
        ).encode()
        + b"\n"
    )
    path.write_bytes(payload)

    with pytest.raises(ValueError, match="canonical immutable JSON"):
        load_stage_input(
            tmp_path,
            path.relative_to(tmp_path).as_posix(),
            hashlib.sha256(payload).hexdigest(),
            cycle_id=cycle_id,
            target="qualitative_review",
            input_kind="semantic",
        )
    canonical_ref, canonical_sha = _write_json(
        tmp_path,
        ".task/extra-semantic.json",
        {
            "schema_version": 1,
            "artifact_kind": "stage_semantic",
            "cycle_id": cycle_id,
            "target": "qualitative_review",
            "semantic": {"quality_verdict": "pass"},
            "extra": "forbidden",
        },
    )
    with pytest.raises(ValueError, match="unsupported fields"):
        load_stage_input(
            tmp_path,
            canonical_ref,
            canonical_sha,
            cycle_id=cycle_id,
            target="qualitative_review",
            input_kind="semantic",
        )


def test_usage_v2_caller_provenance_remains_unattested_and_unaggregateable(
    tmp_path: Path,
) -> None:
    cycle_id = "cycle-usage"
    v1_ref, v1_sha = _write_json(
        tmp_path,
        ".task/usage-v1.json",
        {
            "schema_version": 1,
            "artifact_kind": "model_usage_observation",
            "cycle_id": cycle_id,
            "target": "acceptance",
            "input_tokens": 10,
            "cached_input_tokens": 2,
            "output_tokens": 1,
        },
    )
    v2_ref, v2_sha = _write_json(
        tmp_path,
        ".task/usage-v2.json",
        {
            "schema_version": 2,
            "artifact_kind": "model_usage_observation",
            "cycle_id": cycle_id,
            "target": "acceptance",
            "provider_id": "openai",
            "runtime_id": "runtime-1",
            "model_id": "gpt-5",
            "request_id": "request-1",
            "input_tokens": 10,
            "cached_input_tokens": 2,
            "output_tokens": 1,
        },
    )

    v1, _ = load_usage_observation(
        tmp_path, v1_ref, v1_sha, cycle_id=cycle_id, target="acceptance"
    )
    v2, binding = load_usage_observation(
        tmp_path, v2_ref, v2_sha, cycle_id=cycle_id, target="acceptance"
    )

    assert v1["usage_aggregate_eligible"] is False
    assert v2["usage_aggregate_eligible"] is False
    assert v2["usage_provenance_status"] == "caller_asserted_unverified"
    assert v2["model_id"] == "gpt-5"
    assert binding["schema_version"] == 2


def test_deterministic_submission_rejects_model_usage_without_writes(
    tmp_path: Path,
) -> None:
    cycle_id = _cycle(tmp_path, "cycle-no-model-usage")
    append_event(
        tmp_path,
        cycle_id,
        {
            "step": "authority",
            "status": "completed",
            "event_id": "authority-no-model-usage",
        },
    )
    target = "repo_skill_adapter_scan"
    preparation = prepare_stage(
        tmp_path,
        cycle_id,
        target,
        persist_compiler_artifacts=True,
    )
    owner = _deterministic_owner_binding(
        tmp_path, preparation, commit=True
    )
    usage_ref, usage_sha = _write_json(
        tmp_path,
        ".task/forbidden-deterministic-usage.json",
        {
            "schema_version": 2,
            "artifact_kind": "model_usage_observation",
            "cycle_id": cycle_id,
            "target": target,
            "provider_id": "provider-a",
            "runtime_id": "runtime-a",
            "model_id": "model-a",
            "request_id": "request-a",
            "input_tokens": 1,
            "cached_input_tokens": 0,
            "output_tokens": 1,
        },
    )
    before = {
        path.relative_to(tmp_path).as_posix(): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }

    with pytest.raises(ValueError, match="must not supply model usage"):
        submit_stage(
            tmp_path,
            preparation,
            owner_result_ref=owner["ref"],
            owner_result_sha256=owner["sha256"],
            **_deterministic_commit_args(owner),
            usage_ref=usage_ref,
            usage_sha256=usage_sha,
            apply=True,
        )
    after = {
        path.relative_to(tmp_path).as_posix(): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }
    assert after == before


def test_v3_preparation_closedness_rejects_forgery_without_writes(
    tmp_path: Path,
) -> None:
    cycle_id = _cycle(tmp_path, "cycle-closed-preparation")
    append_event(
        tmp_path,
        cycle_id,
        {
            "step": "authority",
            "status": "completed",
            "event_id": "authority-closed-preparation",
        },
    )
    target = "repo_skill_adapter_scan"
    preparation = prepare_stage(
        tmp_path,
        cycle_id,
        target,
        persist_compiler_artifacts=True,
    )
    owner = _deterministic_owner_binding(
        tmp_path, preparation, commit=True
    )

    extra_top_level = copy.deepcopy(preparation)
    extra_top_level["model_hint"] = "forbidden"

    extra_binding_field = copy.deepcopy(preparation)
    extra_binding_field["machine_input_binding"]["model_hint"] = "forbidden"
    extra_binding_field["preparation_id"] = (
        "stageprep-"
        + canonical_sha256(preparation_identity(extra_binding_field))[:32]
    )

    forged_spec = copy.deepcopy(preparation)
    forged_spec["executor_spec"]["command_id"] = "forged.command.v1"
    forged_spec["preparation_id"] = (
        "stageprep-"
        + canonical_sha256(preparation_identity(forged_spec))[:32]
    )
    before = {
        path.relative_to(tmp_path).as_posix(): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }

    for supplied, message in (
        (extra_top_level, "top-level fields are not closed"),
        (extra_binding_field, "binding fields are not closed"),
        (forged_spec, "does not match the registered projection"),
    ):
        with pytest.raises(ValueError, match=message):
            submit_stage(
                tmp_path,
                supplied,
                owner_result_ref=owner["ref"],
                owner_result_sha256=owner["sha256"],
                **_deterministic_commit_args(owner),
                apply=True,
            )

    after = {
        path.relative_to(tmp_path).as_posix(): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }
    assert after == before


def test_fresh_git_deterministic_dispatch_ignores_cycle_compiler_outputs(
    tmp_path: Path,
) -> None:
    cycle_id = _cycle(tmp_path, "cycle-fresh-git-dispatch")
    target = "repo_skill_adapter_scan"
    _prime(tmp_path, cycle_id, target)
    _init_git_workspace(tmp_path)
    (tmp_path / "source.py").write_text("VALUE = 2\n", encoding="utf-8")
    preparation = prepare_stage(
        tmp_path,
        cycle_id,
        target,
        persist_compiler_artifacts=True,
    )
    machine = load_compiler_artifact(
        tmp_path,
        cycle_id,
        preparation["machine_input_binding"],
        "machine_input",
    )
    changed = list(machine["git"]["changed_paths"]["items"])

    assert "source.py" in changed
    assert not any(
        path == ".task/cycle" or path.startswith(".task/cycle/")
        for path in changed
    )

    dispatched = dispatch_deterministic(tmp_path, preparation)
    assert dispatched.get("status") != "block"
    binding = _deterministic_owner_binding(
        tmp_path, preparation, commit=True
    )
    output = submit_stage(
        tmp_path,
        preparation,
        owner_result_ref=binding["ref"],
        owner_result_sha256=binding["sha256"],
        **_deterministic_commit_args(binding),
        apply=True,
    )

    assert output["applied"] is True
    assert output["compiler_metrics"]["precondition_validation_status"] == (
        "exact_precondition"
    )
    assert output["compiler_metrics"]["model_call_count"] == 0


def test_stale_deterministic_dashboard_dispatch_writes_no_projection_or_result(
    tmp_path: Path,
) -> None:
    cycle_id = _cycle(tmp_path, "cycle-stale-dashboard")
    target = "dashboard"
    _prime(tmp_path, cycle_id, target)
    _init_git_workspace(tmp_path)
    preparation = prepare_stage(
        tmp_path,
        cycle_id,
        target,
        persist_compiler_artifacts=True,
    )
    (tmp_path / "source.py").write_text("VALUE = 2\n", encoding="utf-8")
    before = {
        path.relative_to(tmp_path).as_posix(): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }

    output = dispatch_deterministic(tmp_path, preparation)
    after = {
        path.relative_to(tmp_path).as_posix(): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }

    assert output["status"] == "block"
    assert output["stop_reason"] == "stale_preparation"
    assert output["changed_precondition_selectors"] == ["git_worktree"]
    assert output["model_call_count"] == 0
    assert output["files_written_count"] == 0
    assert before == after
    assert not (tmp_path / ".task" / "cycle" / cycle_id / "dashboard.md").exists()


def test_same_dirty_path_content_mutation_invalidates_preparation(
    tmp_path: Path,
) -> None:
    cycle_id = _cycle(tmp_path, "cycle-same-dirty-path-stale")
    target = "dashboard"
    _prime(tmp_path, cycle_id, target)
    _init_git_workspace(tmp_path)
    (tmp_path / "source.py").write_text("VALUE = 2\n", encoding="utf-8")
    preparation = prepare_stage(
        tmp_path,
        cycle_id,
        target,
        persist_compiler_artifacts=True,
    )
    machine = load_compiler_artifact(
        tmp_path,
        cycle_id,
        preparation["machine_input_binding"],
        "machine_input",
    )
    before_git = machine["git"]

    (tmp_path / "source.py").write_text("VALUE = 3\n", encoding="utf-8")
    _full, current, _metrics = v2_context.collect_selected_context(
        tmp_path,
        cycle_id,
        TARGET_COMPILE_SPECS[target],
        max_files=12,
        max_paths=40,
    )
    output = dispatch_deterministic(tmp_path, preparation)

    assert before_git["changed_paths"] == current["git"]["changed_paths"]
    assert before_git["worktree_identity"]["inventory_sha256"] != (
        current["git"]["worktree_identity"]["inventory_sha256"]
    )
    assert output["status"] == "block"
    assert output["stop_reason"] == "stale_preparation"
    assert output["changed_precondition_selectors"] == ["git_worktree"]
    assert output["files_written_count"] == 0


def test_git_worktree_identity_handles_missing_untracked_and_symlink_without_following(
    tmp_path: Path,
) -> None:
    cycle_id = _cycle(tmp_path, "cycle-worktree-entry-kinds")
    target = "repo_skill_adapter_scan"
    _prime(tmp_path, cycle_id, target)
    _init_git_workspace(tmp_path)
    (tmp_path / "deleted.txt").write_text("tracked deletion\n", encoding="utf-8")
    (tmp_path / "link.txt").symlink_to("source.py")
    subprocess.run(
        ["git", "add", "deleted.txt", "link.txt"], cwd=tmp_path, check=True
    )
    subprocess.run(
        ["git", "commit", "-qm", "identity fixtures"], cwd=tmp_path, check=True
    )
    (tmp_path / "deleted.txt").unlink()
    (tmp_path / "link.txt").unlink()
    link_target = "outside-looking-but-unfollowed.txt"
    (tmp_path / "link.txt").symlink_to(link_target)
    (tmp_path / "untracked.txt").write_text("untracked body\n", encoding="utf-8")

    preparation = prepare_stage(
        tmp_path,
        cycle_id,
        target,
        persist_compiler_artifacts=True,
    )
    machine = load_compiler_artifact(
        tmp_path,
        cycle_id,
        preparation["machine_input_binding"],
        "machine_input",
    )
    git = machine["git"]
    entries = dict(
        zip(
            git["changed_paths"]["items"],
            git["worktree_identity"]["items"],
            strict=True,
        )
    )

    assert git["worktree_identity"]["binding_status"] == "exact"
    assert entries["deleted.txt"]["kind"] == "missing"
    assert entries["deleted.txt"]["content_sha256"] is None
    assert entries["untracked.txt"]["kind"] == "regular_file"
    assert entries["link.txt"]["kind"] == "symlink"
    assert entries["link.txt"]["content_sha256"] == hashlib.sha256(
        link_target.encode("utf-8")
    ).hexdigest()
    assert all(len(entry["index_identity_sha256"]) == 64 for entry in entries.values())


def test_git_worktree_scan_limit_blocks_exact_selector_binding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cycle_id = _cycle(tmp_path, "cycle-worktree-limit")
    _init_git_workspace(tmp_path)
    (tmp_path / "first.txt").write_text("first\n", encoding="utf-8")
    (tmp_path / "second.txt").write_text("second\n", encoding="utf-8")
    from orchestrate_task_cycle import git_worktree_identity

    monkeypatch.setattr(git_worktree_identity, "MAX_GIT_IDENTITY_PATHS", 1)
    _full, projected, _metrics = v2_context.collect_selected_context(
        tmp_path,
        cycle_id,
        TARGET_COMPILE_SPECS["visible_increment"],
        max_files=12,
        max_paths=40,
    )

    assert projected["projection_status"] == "block"
    assert projected["stop_reason"] == "git_worktree_binding_incomplete"
    assert projected["git"]["worktree_identity"]["binding_status"] == "incomplete"
    assert projected["git"]["worktree_identity"]["inventory_sha256"] is None


def test_owner_git_mutation_is_validated_as_visible_increment_post_effect(
    tmp_path: Path,
) -> None:
    cycle_id = _cycle(tmp_path, "cycle-owner-post-effect")
    target = "visible_increment"
    _prime(tmp_path, cycle_id, target)
    _init_git_workspace(tmp_path)
    preparation = prepare_stage(
        tmp_path,
        cycle_id,
        target,
        persist_compiler_artifacts=True,
    )
    (tmp_path / "source.py").write_text("VALUE = 2\n", encoding="utf-8")
    owner = write_stage_input(
        tmp_path,
        cycle_id,
        target,
        "owner_result",
        {
            "status": "recorded",
            "summary": "Recorded the owner-applied source change.",
            "delta_types": ["workflow_artifact"],
            "changed_files": ["source.py"],
            "artifacts": [],
            "not_validation_evidence": True,
            "blockers": [],
            "evidence_paths": ["source.py"],
        },
        preparation=preparation,
    )

    output = submit_stage(
        tmp_path,
        preparation,
        owner_result_ref=owner["ref"],
        owner_result_sha256=owner["sha256"],
        apply=True,
    )
    event = next(
        item for item in read_events_raw(tmp_path, cycle_id) if item["step"] == target
    )

    assert output["applied"] is True
    assert output["compiler_metrics"]["precondition_validation_status"] == (
        "owner_validated_post_effect"
    )
    assert output["compiler_metrics"]["post_effect_changed_selector_count"] == 1
    assert event["compiler_metrics"]["precondition_validation_status"] == (
        "owner_validated_post_effect"
    )


def test_owner_same_dirty_path_mutation_requires_content_bound_post_effect_claim(
    tmp_path: Path,
) -> None:
    cycle_id = _cycle(tmp_path, "cycle-owner-same-dirty-path")
    target = "visible_increment"
    _prime(tmp_path, cycle_id, target)
    _init_git_workspace(tmp_path)
    (tmp_path / "source.py").write_text("VALUE = 2\n", encoding="utf-8")
    preparation = prepare_stage(
        tmp_path,
        cycle_id,
        target,
        persist_compiler_artifacts=True,
    )
    (tmp_path / "source.py").write_text("VALUE = 3\n", encoding="utf-8")
    owner = write_stage_input(
        tmp_path,
        cycle_id,
        target,
        "owner_result",
        {
            "status": "recorded",
            "summary": "Recorded a second mutation of the already dirty source.",
            "delta_types": ["workflow_artifact"],
            "changed_files": ["source.py"],
            "artifacts": [],
            "not_validation_evidence": True,
            "blockers": [],
            "evidence_paths": ["source.py"],
        },
        preparation=preparation,
    )

    output = submit_stage(
        tmp_path,
        preparation,
        owner_result_ref=owner["ref"],
        owner_result_sha256=owner["sha256"],
        apply=True,
    )

    assert output["applied"] is True
    assert output["compiler_metrics"]["precondition_validation_status"] == (
        "owner_validated_post_effect"
    )
    assert output["compiler_metrics"]["post_effect_changed_selector_count"] == 1


def test_owner_post_effect_truncated_identity_fails_closed(
    tmp_path: Path,
) -> None:
    cycle_id = _cycle(tmp_path, "cycle-owner-truncated-worktree")
    target = "visible_increment"
    _prime(tmp_path, cycle_id, target)
    _init_git_workspace(tmp_path)
    preparation = prepare_stage(
        tmp_path,
        cycle_id,
        target,
        max_paths=1,
        persist_compiler_artifacts=True,
    )
    (tmp_path / "first.txt").write_text("first\n", encoding="utf-8")
    (tmp_path / "second.txt").write_text("second\n", encoding="utf-8")
    owner = write_stage_input(
        tmp_path,
        cycle_id,
        target,
        "owner_result",
        {
            "changed_files": ["first.txt", "second.txt"],
            "evidence_paths": ["first.txt", "second.txt"],
        },
        preparation=preparation,
    )
    before = {
        path.relative_to(tmp_path).as_posix(): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }

    output = submit_stage(
        tmp_path,
        preparation,
        owner_result_ref=owner["ref"],
        owner_result_sha256=owner["sha256"],
        max_paths=1,
        apply=True,
    )
    after = {
        path.relative_to(tmp_path).as_posix(): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }

    assert output["status"] == "block"
    assert output["freshness_status"] == "post_effect_owner_claim_mismatch"
    assert output["post_effect_claim_mismatches"] == ["git_effect_scope_truncated"]
    assert after == before


def test_governance_allows_exact_task_effect_without_hiding_other_core_state(
    tmp_path: Path,
) -> None:
    cycle_id = _cycle(tmp_path, "cycle-governance-task-effect")
    target = "governance"
    _prime(tmp_path, cycle_id, target)
    _init_git_workspace(tmp_path)
    preparation = prepare_stage(
        tmp_path, cycle_id, target, persist_compiler_artifacts=True
    )
    routing_ref, routing_sha = _routing_receipt(
        tmp_path, cycle_id, target, preparation
    )
    (tmp_path / "task.md").write_text("# Task\n\nGoverned revision.\n", encoding="utf-8")
    owner = write_stage_input(
        tmp_path,
        cycle_id,
        target,
        "owner_result",
        {"changed_files": ["task.md"], "evidence_paths": ["task.md"]},
        preparation=preparation,
    )

    output = submit_stage(
        tmp_path,
        preparation,
        owner_result_ref=owner["ref"],
        owner_result_sha256=owner["sha256"],
        routing_ref=routing_ref,
        routing_sha256=routing_sha,
        apply=True,
    )

    assert output["applied"] is True
    assert output["compiler_metrics"]["precondition_validation_status"] == (
        "owner_validated_post_effect"
    )
    assert output["compiler_metrics"]["post_effect_changed_selector_count"] == 2


def test_governance_task_effect_does_not_mask_concurrent_cycle_or_authority_state(
    tmp_path: Path,
) -> None:
    cycle_id = _cycle(tmp_path, "cycle-governance-concurrent-core")
    target = "governance"
    _prime(tmp_path, cycle_id, target)
    _init_git_workspace(tmp_path)
    preparation = prepare_stage(
        tmp_path, cycle_id, target, persist_compiler_artifacts=True
    )
    routing_ref, routing_sha = _routing_receipt(
        tmp_path, cycle_id, target, preparation
    )
    (tmp_path / "task.md").write_text("# Task\n\nGoverned revision.\n", encoding="utf-8")
    append_event(
        tmp_path,
        cycle_id,
        {
            "step": "authority",
            "status": "completed",
            "event_id": "concurrent-authority-replacement",
            "task_id": "task-v3",
        },
    )
    owner = write_stage_input(
        tmp_path,
        cycle_id,
        target,
        "owner_result",
        {"changed_files": ["task.md"], "evidence_paths": ["task.md"]},
        preparation=preparation,
    )
    before = {
        path.relative_to(tmp_path).as_posix(): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }

    output = submit_stage(
        tmp_path,
        preparation,
        owner_result_ref=owner["ref"],
        owner_result_sha256=owner["sha256"],
        routing_ref=routing_ref,
        routing_sha256=routing_sha,
        apply=True,
    )
    after = {
        path.relative_to(tmp_path).as_posix(): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }

    assert output["status"] == "block"
    assert output["stop_reason"] == "stale_preparation"
    assert {"authority", "cycle"} <= set(output["disallowed_post_effect_selectors"])
    assert before == after


def test_governance_owner_claim_rejects_unclaimed_git_effect_without_writes(
    tmp_path: Path,
) -> None:
    cycle_id = _cycle(tmp_path, "cycle-governance-unclaimed-git")
    target = "governance"
    _prime(tmp_path, cycle_id, target)
    _init_git_workspace(tmp_path)
    preparation = prepare_stage(
        tmp_path, cycle_id, target, persist_compiler_artifacts=True
    )
    routing_ref, routing_sha = _routing_receipt(
        tmp_path, cycle_id, target, preparation
    )
    (tmp_path / "task.md").write_text("# Task\n\nGoverned revision.\n", encoding="utf-8")
    (tmp_path / "unclaimed.py").write_text("VALUE = 9\n", encoding="utf-8")
    owner = write_stage_input(
        tmp_path,
        cycle_id,
        target,
        "owner_result",
        {"changed_files": ["task.md"], "evidence_paths": ["task.md"]},
        preparation=preparation,
    )
    before = {
        path.relative_to(tmp_path).as_posix(): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }

    output = submit_stage(
        tmp_path,
        preparation,
        owner_result_ref=owner["ref"],
        owner_result_sha256=owner["sha256"],
        routing_ref=routing_ref,
        routing_sha256=routing_sha,
        apply=True,
    )
    after = {
        path.relative_to(tmp_path).as_posix(): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }

    assert output["status"] == "block"
    assert output["freshness_status"] == "post_effect_owner_claim_mismatch"
    assert output["post_effect_claim_mismatches"] == [
        "git_effect_paths_differ_from_owner_claim"
    ]
    assert before == after


def test_owner_post_effect_rejects_disallowed_core_mutation_without_publication(
    tmp_path: Path,
) -> None:
    cycle_id = _cycle(tmp_path, "cycle-owner-core-stale")
    target = "visible_increment"
    _prime(tmp_path, cycle_id, target)
    _init_git_workspace(tmp_path)
    preparation = prepare_stage(
        tmp_path,
        cycle_id,
        target,
        persist_compiler_artifacts=True,
    )
    (tmp_path / "task.md").write_text("# Replaced task\n", encoding="utf-8")
    owner = write_stage_input(
        tmp_path,
        cycle_id,
        target,
        "owner_result",
        {
            "status": "recorded",
            "summary": "This result cannot authorize a task replacement.",
            "delta_types": ["workflow_artifact"],
            "changed_files": ["task.md"],
            "artifacts": [],
            "not_validation_evidence": True,
            "blockers": [],
            "evidence_paths": ["task.md"],
        },
        preparation=preparation,
    )

    output = submit_stage(
        tmp_path,
        preparation,
        owner_result_ref=owner["ref"],
        owner_result_sha256=owner["sha256"],
        apply=True,
    )

    assert output["status"] == "block"
    assert output["stop_reason"] == "stale_preparation"
    assert "task" in output["disallowed_post_effect_selectors"]
    assert not [
        event for event in read_events_raw(tmp_path, cycle_id) if event["step"] == target
    ]


def test_submit_retry_recovers_result_cas_without_ledger_event(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cycle_id = _cycle(tmp_path, "cycle-result-cas-repair")
    append_event(
        tmp_path,
        cycle_id,
        {
            "step": "authority",
            "status": "completed",
            "event_id": "authority-result-cas-repair",
        },
    )
    target = "repo_skill_adapter_scan"
    preparation = prepare_stage(
        tmp_path,
        cycle_id,
        target,
        persist_compiler_artifacts=True,
    )
    owner = _deterministic_owner_binding(
        tmp_path, preparation, commit=True
    )

    def fail_before_append(*_args, **_kwargs):
        raise RuntimeError("injected crash after result CAS write")

    actual_append = stage_publication._append_compiled_result_binding
    monkeypatch.setattr(
        stage_publication, "_append_compiled_result_binding", fail_before_append
    )
    with pytest.raises(RuntimeError, match="result CAS write"):
        submit_stage(
            tmp_path,
            preparation,
            owner_result_ref=owner["ref"],
            owner_result_sha256=owner["sha256"],
            **_deterministic_commit_args(owner),
            apply=True,
        )

    assert not [
        event
        for event in read_events_raw(tmp_path, cycle_id)
        if event.get("step") == target
    ]
    assert len(
        list(
            (
                tmp_path / ".task" / "cycle" / cycle_id / "packets"
            ).glob(f"result-{target}-*.json")
        )
    ) == 1

    monkeypatch.setattr(
        stage_publication, "_append_compiled_result_binding", actual_append
    )
    replay = submit_stage(
        tmp_path,
        preparation,
        owner_result_ref=owner["ref"],
        owner_result_sha256=owner["sha256"],
        **_deterministic_commit_args(owner),
        apply=True,
    )

    assert replay["applied"] is True
    assert replay["compiler_metrics"]["cas_reused_bytes"] > 0
    assert len(
        [
            event
            for event in read_events_raw(tmp_path, cycle_id)
            if event.get("step") == target
        ]
    ) == 1


def test_submit_retry_repairs_current_after_ledger_append_crash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cycle_id = _cycle(tmp_path, "cycle-publication-repair")
    append_event(
        tmp_path,
        cycle_id,
        {
            "step": "authority",
            "status": "completed",
            "event_id": "authority-publication-repair",
        },
    )
    target = "repo_skill_adapter_scan"
    preparation = prepare_stage(
        tmp_path,
        cycle_id,
        target,
        persist_compiler_artifacts=True,
    )
    owner = _deterministic_owner_binding(
        tmp_path, preparation, commit=True
    )

    def append_then_crash(root, selected_cycle, binding):
        def fail_current(_path, _text):
            raise RuntimeError("injected current projection crash")

        return append_compiled_binding(
            root,
            selected_cycle,
            binding,
            atomic_writer=fail_current,
        )

    actual_append = stage_publication._append_compiled_result_binding
    monkeypatch.setattr(
        stage_publication, "_append_compiled_result_binding", append_then_crash
    )
    with pytest.raises(RuntimeError, match="projection crash"):
        submit_stage(
            tmp_path,
            preparation,
            owner_result_ref=owner["ref"],
            owner_result_sha256=owner["sha256"],
            **_deterministic_commit_args(owner),
            apply=True,
        )
    raw_after_crash = read_events_raw(tmp_path, cycle_id)
    published = [event for event in raw_after_crash if event.get("step") == target]
    assert len(published) == 1
    original_metrics = published[0]["compiler_metrics"]

    monkeypatch.setattr(
        stage_publication,
        "_append_compiled_result_binding",
        actual_append,
    )
    replay = submit_stage(
        tmp_path,
        preparation,
        owner_result_ref=owner["ref"],
        owner_result_sha256=owner["sha256"],
        **_deterministic_commit_args(owner),
        apply=True,
    )

    assert replay["event_duplicate"] is True
    assert replay["compiler_metrics"] == original_metrics
    assert len(
        [event for event in read_events_raw(tmp_path, cycle_id) if event.get("step") == target]
    ) == 1
    assert read_current_expanded(tmp_path, cycle_id)["latest_event"]["step"] == target
