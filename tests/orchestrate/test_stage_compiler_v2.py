from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from orchestrate_task_cycle.cycle_ledger import append_event, init_cycle, read_events
from orchestrate_task_cycle.repo_skill_adapter import scan_repo_skill_adapters
from orchestrate_task_cycle.stage.artifact_store import load_usage_observation
from orchestrate_task_cycle.stage.preparation_store import publish_preparation
from orchestrate_task_cycle.stage.cli import _parser as stage_parser, _run as stage_run
from orchestrate_task_cycle.stage.service import advance_stage, prepare_stage, submit_stage
from orchestrate_task_cycle.stage.specs import TARGET_COMPILE_SPECS


def _init_v2(root: Path) -> str:
    (root / "task.md").write_text("# Task\n\nCompile stages.\n", encoding="utf-8")
    cycle_id = "cycle-stage-v2"
    init_cycle(
        root,
        cycle_id,
        "task-stage-v2",
        "stage compiler v2 test",
        stage_compiler_protocol_version=2,
        stage_preparation_schema_version=2,
    )
    output = advance_stage(root, cycle_id, apply=True)
    assert output["stop_reason"] == "awaiting_authority"
    assert [event["step"] for event in read_events(root, cycle_id)] == ["context"]
    return cycle_id


def _append_completed(root: Path, cycle_id: str, step: str) -> None:
    append_event(
        root,
        cycle_id,
        {
            "step": step,
            "status": "completed",
            "event_id": f"fixture-v2-{step}",
            "reason": "v2 dependency fixture",
            "task_id": "task-stage-v2",
        },
    )


def _write_exact_json(root: Path, name: str, value: dict) -> tuple[str, str]:
    path = root / ".task" / name
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8") + b"\n"
    path.write_bytes(payload)
    return path.relative_to(root).as_posix(), hashlib.sha256(payload).hexdigest()


def test_v2_registry_has_no_implicit_semantic_fallback() -> None:
    visible = TARGET_COMPILE_SPECS["visible_increment"]
    review = TARGET_COMPILE_SPECS["qualitative_review"]
    report = TARGET_COMPILE_SPECS["report"]

    assert visible.executor_kind == "owner"
    assert visible.semantic_fields == ()
    assert "summary" in visible.owner_receipt_fields
    assert review.executor_kind == "hybrid"
    assert "quality_verdict" in review.semantic_fields
    assert "reviewed_artifacts" in review.owner_receipt_fields
    assert report.executor_kind == "deterministic"
    assert report.semantic_fields == ()


def test_v2_prepare_is_write_free_compact_and_publish_binds_cas(
    tmp_path: Path,
) -> None:
    cycle_id = _init_v2(tmp_path)

    preparation = prepare_stage(tmp_path, cycle_id, "authority")

    assert preparation["schema_version"] == 2
    assert preparation["model_call_required"] is False
    assert "model_context" not in preparation
    assert "model_packet" not in preparation
    assert not (tmp_path / ".task" / "cycle" / cycle_id / "compiler").exists()
    with pytest.raises(ValueError, match="artifact ref does not exist"):
        publish_preparation(tmp_path, preparation)

    persisted = prepare_stage(
        tmp_path,
        cycle_id,
        "authority",
        persist_compiler_artifacts=True,
    )
    publication = publish_preparation(tmp_path, persisted)

    assert persisted == preparation
    assert publication["preparation_bytes"] < 256 * 1024
    for label in ("context_binding", "work_order_binding"):
        assert (tmp_path / persisted[label]["ref"]).is_file()


def test_v2_lazy_authority_context_does_not_collect_task_inventory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cycle_id = _init_v2(tmp_path)

    def unexpected(*_args, **_kwargs):
        raise AssertionError("authority context collected task inventory")

    monkeypatch.setattr(
        "orchestrate_task_cycle.stage.v2_context.collect_task", unexpected
    )
    preparation = prepare_stage(tmp_path, cycle_id, "authority")

    assert "task_state" not in preparation["fingerprint_roles"]
    assert preparation["compiler_metrics"]["context_section_count"] < 10


def test_v2_cycle_protocol_mismatch_is_rejected(tmp_path: Path) -> None:
    cycle_id = _init_v2(tmp_path)

    with pytest.raises(ValueError, match="must match cycle initialization protocol"):
        prepare_stage(
            tmp_path,
            cycle_id,
            "authority",
            preparation_schema_version=1,
        )


def test_stage_cli_infers_v2_from_cycle_initialization(tmp_path: Path) -> None:
    cycle_id = _init_v2(tmp_path)
    args = stage_parser().parse_args(
        [
            "prepare",
            "--root",
            str(tmp_path),
            "--cycle-id",
            cycle_id,
            "--target",
            "authority",
        ]
    )

    output = stage_run(args)

    assert args.preparation_schema_version is None
    assert output["schema_version"] == 2
    assert not (tmp_path / ".task" / "cycle" / cycle_id / "compiler").exists()


def test_v2_advance_materializes_canonical_system_stage(tmp_path: Path) -> None:
    cycle_id = _init_v2(tmp_path)
    for step in ("authority", "repo_skill_adapter_scan", "acceptance"):
        _append_completed(tmp_path, cycle_id, step)

    output = advance_stage(tmp_path, cycle_id, apply=True, max_steps=3)

    assert output["status"] == "waiting"
    assert output["stop_reason"] == "awaiting_owner_result"
    assert output["preparation"]["target"] == "validation_scope_plan"
    route = next(event for event in read_events(tmp_path, cycle_id) if event["step"] == "route_plan")
    assert route["compiler_protocol_version"] == 2
    assert output["actions"][0]["kind"] == "append_system_stage"


def test_v2_exact_owner_input_keeps_large_body_out_of_output(tmp_path: Path) -> None:
    cycle_id = _init_v2(tmp_path)
    for step in ("authority", "repo_skill_adapter_scan"):
        _append_completed(tmp_path, cycle_id, step)
    preparation = prepare_stage(
        tmp_path,
        cycle_id,
        "acceptance",
        persist_compiler_artifacts=True,
    )
    publish_preparation(tmp_path, preparation)
    sentinel = "large-owner-body-sentinel-" + ("x" * 50_000)
    owner_ref, owner_sha = _write_exact_json(
        tmp_path,
        "owner-acceptance.json",
        {
            "acceptance_id": "acceptance-v2",
            "task_id": "task-stage-v2",
            "acceptance_status": "normalized",
            "acceptance_provenance": {
                "source_task_id": "task-stage-v2",
                "source_task_path": "task.md",
                "source_task_fingerprint": "a" * 64,
                "owner_detail": sentinel,
            },
            "acceptance_criteria": ["The compiler preserves exact bindings."],
            "blockers": [],
            "evidence_paths": ["task.md"],
        },
    )
    usage_ref, usage_sha = _write_exact_json(
        tmp_path,
        "usage-acceptance.json",
        {
            "schema_version": 1,
            "artifact_kind": "model_usage_observation",
            "cycle_id": cycle_id,
            "target": "acceptance",
            "input_tokens": 1200,
            "cached_input_tokens": 900,
            "output_tokens": 80,
        },
    )

    output = submit_stage(
        tmp_path,
        preparation,
        owner_result_ref=owner_ref,
        owner_result_sha256=owner_sha,
        usage_ref=usage_ref,
        usage_sha256=usage_sha,
    )
    encoded = json.dumps(output, ensure_ascii=False, sort_keys=True)

    assert output["input_bindings"]["owner_result_binding"]["sha256"] == owner_sha
    assert "result" not in output
    assert "large-owner-body-sentinel" not in encoded
    assert output["compiler_metrics"]["model_authored_mechanical_bytes"] == 0
    assert output["compiler_metrics"]["inline_payload_bytes"] == 0
    assert output["compiler_metrics"]["input_tokens"] == 1200
    assert output["compiler_metrics"]["cached_input_tokens"] == 900
    assert output["compiler_metrics"]["output_tokens"] == 80
    assert output["input_bindings"]["usage_binding"]["sha256"] == usage_sha


def test_v2_imports_native_deterministic_repo_scan_packet(tmp_path: Path) -> None:
    cycle_id = _init_v2(tmp_path)
    _append_completed(tmp_path, cycle_id, "authority")
    preparation = prepare_stage(
        tmp_path,
        cycle_id,
        "repo_skill_adapter_scan",
        persist_compiler_artifacts=True,
    )
    publish_preparation(tmp_path, preparation)
    native = scan_repo_skill_adapters(tmp_path, cycle_id=cycle_id)
    owner_ref, owner_sha = _write_exact_json(
        tmp_path, "native-repo-adapter-scan.json", native
    )

    output = submit_stage(
        tmp_path,
        preparation,
        owner_result_ref=owner_ref,
        owner_result_sha256=owner_sha,
        apply=True,
    )

    assert output["status"] == "ok"
    assert output["applied"] is True
    result_path = tmp_path / output["result_artifact_ref"]
    result = json.loads(result_path.read_text(encoding="utf-8"))
    assert result["step"] == "repo_skill_adapter_scan"
    assert result["cycle_id"] == cycle_id
    assert result["evidence_paths"] == [owner_ref]
    assert "artifact_kind" not in result
    assert "scan_packet_sha256" not in result


def test_v2_rejects_tampered_native_deterministic_packet(tmp_path: Path) -> None:
    cycle_id = _init_v2(tmp_path)
    _append_completed(tmp_path, cycle_id, "authority")
    preparation = prepare_stage(
        tmp_path,
        cycle_id,
        "repo_skill_adapter_scan",
        persist_compiler_artifacts=True,
    )
    native = scan_repo_skill_adapters(tmp_path, cycle_id=cycle_id)
    native["scan_packet_sha256"] = "0" * 64
    owner_ref, owner_sha = _write_exact_json(
        tmp_path, "tampered-native-repo-adapter-scan.json", native
    )

    with pytest.raises(ValueError, match="packet integrity failed"):
        submit_stage(
            tmp_path,
            preparation,
            owner_result_ref=owner_ref,
            owner_result_sha256=owner_sha,
        )


def test_v2_hybrid_requires_exact_semantic_binding(tmp_path: Path) -> None:
    cycle_id = _init_v2(tmp_path)
    preceding = (
        "authority",
        "repo_skill_adapter_scan",
        "acceptance",
        "route_plan",
        "validation_scope_plan",
        "validation_set_plan",
        "governance",
        "result_contract",
        "repo_skill_adapter_validate",
        "ledger_append",
        "code_structure_audit",
        "run",
    )
    for step in preceding:
        _append_completed(tmp_path, cycle_id, step)
    preparation = prepare_stage(
        tmp_path,
        cycle_id,
        "qualitative_review",
        persist_compiler_artifacts=True,
    )

    with pytest.raises(ValueError, match="exact owner result binding"):
        submit_stage(tmp_path, preparation)


def test_usage_observation_rejects_price_or_estimate_fields(tmp_path: Path) -> None:
    (tmp_path / ".task").mkdir()
    ref, digest = _write_exact_json(
        tmp_path,
        "usage-invalid.json",
        {
            "schema_version": 1,
            "artifact_kind": "model_usage_observation",
            "cycle_id": "cycle-stage-v2",
            "target": "acceptance",
            "input_tokens": 10,
            "cached_input_tokens": 2,
            "output_tokens": 1,
            "estimated_cost_usd": 0.01,
        },
    )

    with pytest.raises(ValueError, match="unsupported fields"):
        load_usage_observation(
            tmp_path,
            ref,
            digest,
            cycle_id="cycle-stage-v2",
            target="acceptance",
        )
