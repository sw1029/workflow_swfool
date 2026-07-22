from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import subprocess

import pytest

from orchestrate_task_cycle.cycle_ledger import (
    append_event,
    init_cycle,
    read_events,
    read_events_raw,
    read_current_expanded,
)
from orchestrate_task_cycle.profile_cycle_efficiency import analyze
from orchestrate_task_cycle.ledger.result_hydration import hydrate_result_event
from orchestrate_task_cycle.ledger.repository import append_event as repository_append
from orchestrate_task_cycle.stage import publication as stage_publication
from orchestrate_task_cycle.stage.artifact_store import (
    load_compiler_artifact,
    load_stage_input,
    load_usage_observation,
    write_stage_input,
)
from orchestrate_task_cycle.stage.contracts import (
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


def _write_json(root: Path, name: str, value: dict) -> tuple[str, str]:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode() + b"\n"
    path.write_bytes(payload)
    return path.relative_to(root).as_posix(), hashlib.sha256(payload).hexdigest()


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
    return _write_json(
        root,
        f".task/cycle/{cycle_id}/compiler/routing-{target}.json",
        {
            "schema_version": 1,
            "artifact_kind": "stage_routing_receipt",
            "cycle_id": cycle_id,
            "target": target,
            "preparation_id": preparation["preparation_id"],
            "state_fingerprint": preparation["state_fingerprint"],
            "policy_id": "configured-tiered-routing-v3",
            "profile_id": "code_worker",
            "routing_tier": 2,
            "requested_model_ref": "model_ref:balanced",
            "requested_model": "model_ref:balanced",
            "requested_reasoning_effort": "medium",
            "routing_reason_codes": ["profile_default"],
        },
    )


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
    binding = dispatched["owner_result_binding"]
    owner, reopened = load_stage_input(
        tmp_path,
        binding["ref"],
        binding["sha256"],
        cycle_id=cycle_id,
        target=target,
        input_kind="owner_result",
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
    assert raw_scan["compiler_metrics"]["compact_payload_bytes"] > 0
    assert "repo_skill_adapter_packet" not in raw_scan
    assert len(json.dumps(raw_scan, ensure_ascii=False).encode()) < 16 * 1024
    assert scan["hydrated_from_compact_result"] is True
    assert scan["adapter_scan_status"] in {"pass", "block"}
    profile = analyze(tmp_path, hydrated, [], "task-v3")
    assert profile["compiler_efficiency"]["structural_totals"][
        "compact_payload_bytes"
    ] == raw_scan["compiler_metrics"]["compact_payload_bytes"]


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
    sentinel = "body-only-sentinel-" + "x" * 200_000
    result = {
        "step": "repo_skill_adapter_scan",
        "large_body": sentinel,
        "blockers": ["body-only-blocker"],
        "changed_files": ["body-only-change.txt"],
    }
    publish_result(tmp_path, cycle_id, preparation, result, canonical_sha256(result))

    ledger = tmp_path / ".task" / "cycle" / cycle_id / "stage.jsonl"
    assert b"body-only-sentinel" not in ledger.read_bytes()
    hydrated = read_events(tmp_path, cycle_id)[-1]
    assert hydrated["large_body"] == sentinel
    assert hydrated["blockers"] == ["body-only-blocker"]
    assert hydrated["changed_files"] == ["body-only-change.txt"]
    with monkeypatch.context() as relative_root:
        relative_root.chdir(tmp_path)
        relative = read_events(Path("."), cycle_id)[-1]
    assert relative["large_body"] == sentinel
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

    wrong_scope_result = {"step": "dashboard", "large_body": sentinel}
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
    owner = write_stage_input(tmp_path, cycle_id, target, "owner_result", {})

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
    with pytest.raises(ValueError, match="stale or invalid"):
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
    with pytest.raises(ValueError, match="registered policy/profile set"):
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
    )
    routing_ref, routing_sha = _write_json(
        tmp_path,
        ".task/routing-current.json",
        {
            "schema_version": 1,
            "artifact_kind": "stage_routing_receipt",
            "cycle_id": cycle_id,
            "target": target,
            "preparation_id": preparation["preparation_id"],
            "state_fingerprint": preparation["state_fingerprint"],
            "policy_id": "configured-tiered-routing-v3",
            "profile_id": "validation_set",
            "routing_tier": 3,
            "requested_model_ref": "model_ref:balanced",
            "requested_model": "model_ref:balanced",
            "requested_reasoning_effort": "high",
            "routing_reason_codes": ["profile_default"],
        },
    )

    def usage(request_id: str, tokens: int) -> tuple[str, str]:
        return _write_json(
            tmp_path,
            f".task/{request_id}.json",
            {
                "schema_version": 2,
                "artifact_kind": "model_usage_observation",
                "cycle_id": cycle_id,
                "target": target,
                "provider_id": "openai",
                "runtime_id": "runtime-1",
                "model_id": "model_ref:balanced",
                "request_id": request_id,
                "input_tokens": tokens,
                "cached_input_tokens": 2,
                "output_tokens": 1,
            },
        )

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
    init_cycle(
        tmp_path,
        cycle_id,
        "task-v1",
        "legacy result",
        stage_compiler_protocol_version=1,
        stage_preparation_schema_version=1,
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
    owner = dispatch_deterministic(tmp_path, preparation)["owner_result_binding"]
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
    owner = dispatch_deterministic(tmp_path, preparation)["owner_result_binding"]

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
    binding = dispatched["owner_result_binding"]
    output = submit_stage(
        tmp_path,
        preparation,
        owner_result_ref=binding["ref"],
        owner_result_sha256=binding["sha256"],
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
    (tmp_path / "task.md").write_text("# Task\n\nGoverned revision.\n", encoding="utf-8")
    owner = write_stage_input(
        tmp_path,
        cycle_id,
        target,
        "owner_result",
        {"changed_files": ["task.md"], "evidence_paths": ["task.md"]},
    )
    routing_ref, routing_sha = _routing_receipt(
        tmp_path, cycle_id, target, preparation
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
    )
    routing_ref, routing_sha = _routing_receipt(
        tmp_path, cycle_id, target, preparation
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
    (tmp_path / "task.md").write_text("# Task\n\nGoverned revision.\n", encoding="utf-8")
    (tmp_path / "unclaimed.py").write_text("VALUE = 9\n", encoding="utf-8")
    owner = write_stage_input(
        tmp_path,
        cycle_id,
        target,
        "owner_result",
        {"changed_files": ["task.md"], "evidence_paths": ["task.md"]},
    )
    routing_ref, routing_sha = _routing_receipt(
        tmp_path, cycle_id, target, preparation
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
    owner = dispatch_deterministic(tmp_path, preparation)["owner_result_binding"]

    def fail_before_append(*_args, **_kwargs):
        raise RuntimeError("injected crash after result CAS write")

    monkeypatch.setattr(stage_publication, "append_event", fail_before_append)
    with pytest.raises(RuntimeError, match="result CAS write"):
        submit_stage(
            tmp_path,
            preparation,
            owner_result_ref=owner["ref"],
            owner_result_sha256=owner["sha256"],
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

    monkeypatch.setattr(stage_publication, "append_event", append_event)
    replay = submit_stage(
        tmp_path,
        preparation,
        owner_result_ref=owner["ref"],
        owner_result_sha256=owner["sha256"],
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
    owner = dispatch_deterministic(tmp_path, preparation)["owner_result_binding"]

    def append_then_crash(root, selected_cycle, event):
        def fail_current(_path, _text):
            raise RuntimeError("injected current projection crash")

        return repository_append(
            root,
            selected_cycle,
            event,
            atomic_writer=fail_current,
        )

    monkeypatch.setattr(stage_publication, "append_event", append_then_crash)
    with pytest.raises(RuntimeError, match="projection crash"):
        submit_stage(
            tmp_path,
            preparation,
            owner_result_ref=owner["ref"],
            owner_result_sha256=owner["sha256"],
            apply=True,
        )
    raw_after_crash = read_events_raw(tmp_path, cycle_id)
    published = [event for event in raw_after_crash if event.get("step") == target]
    assert len(published) == 1
    original_metrics = published[0]["compiler_metrics"]

    monkeypatch.setattr(
        stage_publication,
        "append_event",
        append_event,
    )
    replay = submit_stage(
        tmp_path,
        preparation,
        owner_result_ref=owner["ref"],
        owner_result_sha256=owner["sha256"],
        apply=True,
    )

    assert replay["event_duplicate"] is True
    assert replay["compiler_metrics"] == original_metrics
    assert len(
        [event for event in read_events_raw(tmp_path, cycle_id) if event.get("step") == target]
    ) == 1
    assert read_current_expanded(tmp_path, cycle_id)["latest_event"]["step"] == target
