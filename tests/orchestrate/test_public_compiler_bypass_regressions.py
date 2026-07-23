from __future__ import annotations

import copy
from pathlib import Path

import pytest

from orchestrate_task_cycle import cycle_ledger, render_subskill_packet
from orchestrate_task_cycle.ledger.compiled_events import (
    append_compiled_system_stage,
)
from orchestrate_task_cycle.ledger import repository as ledger_repository
from orchestrate_task_cycle.packet import builder as packet_builder
from orchestrate_task_cycle.packet.context import PacketBuildContext
from orchestrate_task_cycle.stage import deterministic_commit
from orchestrate_task_cycle.stage.artifact_store import (
    compiler_artifact_binding,
    load_stage_input,
)
from orchestrate_task_cycle.stage.builder import ResultBuilder
from orchestrate_task_cycle.stage.contracts import (
    canonical_sha256,
    preparation_identity,
)
from orchestrate_task_cycle.stage.deterministic_dispatch import (
    dispatch_deterministic,
)
from orchestrate_task_cycle.stage.preparation_store import publish_preparation
from orchestrate_task_cycle.stage.publication import publish_result, result_path
from orchestrate_task_cycle.stage import publication_origin
from orchestrate_task_cycle.stage.service import prepare_stage
from compiler_first_fixture_support import append_fixture_event


def _tree(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


def _scan_preparation(root: Path, cycle_id: str) -> dict:
    (root / "task.md").write_text("# Task\n\nPublic boundary.\n", encoding="utf-8")
    cycle_ledger.init_cycle(root, cycle_id, "task-public", "public boundary")
    append_compiled_system_stage(root, cycle_id, "context")
    append_fixture_event(
        root,
        cycle_id,
        {
            "step": "authority",
            "status": "completed",
            "event_id": f"fixture-authority-{cycle_id}",
            "task_id": "task-public",
        },
    )
    return prepare_stage(
        root,
        cycle_id,
        "repo_skill_adapter_scan",
        persist_compiler_artifacts=True,
    )


def _packet_context(
    root: Path, cycle_id: str
) -> PacketBuildContext:
    context = {
        "workspace": str(root),
        "cycle_state": {"latest_cycle_id": cycle_id},
    }
    stage = {"cycle_id": cycle_id}
    return PacketBuildContext(
        context=context,
        stage=stage,
        model_effort_policy=render_subskill_packet.MODEL_EFFORT_POLICY,
        model_effort_profile_path=(
            render_subskill_packet.MODEL_EFFORT_PROFILE_PATH
        ),
        routing_reference_path=render_subskill_packet.ROUTING_REFERENCE_PATH,
        route_selector=render_subskill_packet.routing_profile,
        output_delta_contract_candidates=(
            render_subskill_packet.OUTPUT_DELTA_CONTRACT_CANDIDATES
        ),
    )


def test_new_protocol_v1_api_and_cli_reject_without_writes(
    tmp_path: Path,
) -> None:
    before = _tree(tmp_path)
    with pytest.raises(ValueError, match="requires compiler-first protocol v2"):
        cycle_ledger.init_cycle(
            tmp_path,
            "cycle-new-v1-api",
            "task-v1",
            "forbidden v1",
            stage_compiler_protocol_version=1,
            stage_preparation_schema_version=1,
        )
    assert _tree(tmp_path) == before
    assert (
        cycle_ledger.main(
            [
                "--root",
                str(tmp_path),
                "init",
                "--cycle-id",
                "cycle-new-v1-cli",
                "--task-id",
                "task-v1",
                "--stage-compiler-protocol-version",
                "1",
                "--stage-preparation-schema-version",
                "1",
            ]
        )
        == 2
    )
    assert _tree(tmp_path) == before


def test_forged_preparation_and_origin_are_write_free(
    tmp_path: Path,
) -> None:
    preparation = _scan_preparation(tmp_path, "cycle-forged-preparation")
    forged = copy.deepcopy(preparation)
    forged["next_action"]["command"] = "forged direct publisher"
    forged["preparation_id"] = (
        "stageprep-" + canonical_sha256(preparation_identity(forged))[:32]
    )
    before = _tree(tmp_path)

    with pytest.raises(ValueError, match="preparation_tampered"):
        publish_preparation(tmp_path, forged)
    assert _tree(tmp_path) == before
    assert not hasattr(publication_origin, "publish_origin_object")
    binding = forged["machine_input_binding"]
    target = tmp_path / str(binding["ref"])
    with pytest.raises(ValueError, match="preparation_tampered"):
        publication_origin.publish_compiler_artifact_origin(
            tmp_path,
            forged,
            "machine_input",
            target,
            target.read_bytes(),
        )
    assert _tree(tmp_path) == before


def test_enforced_artifact_and_current_projection_bypasses_are_write_free(
    tmp_path: Path,
) -> None:
    cycle_id = "cycle-direct-projection-bypass"
    _scan_preparation(tmp_path, cycle_id)
    before = _tree(tmp_path)

    with pytest.raises(ValueError, match="exact origin preparation"):
        compiler_artifact_binding(
            tmp_path,
            cycle_id,
            "machine_input",
            {"schema_version": 1, "artifact_kind": "forged"},
            persist=True,
        )
    with pytest.raises(TypeError):
        cycle_ledger.write_current(
            tmp_path,
            cycle_id,
            [{"step": "forged", "status": "completed"}],
        )
    assert not hasattr(cycle_ledger, "write_current_unlocked")
    assert not hasattr(ledger_repository, "write_current_unlocked")
    assert _tree(tmp_path) == before


def test_direct_publish_result_runs_full_gate_before_result_cas(
    tmp_path: Path,
) -> None:
    cycle_id = "cycle-direct-result-full-gate"
    preparation = _scan_preparation(tmp_path, cycle_id)
    prediction = dispatch_deterministic(tmp_path, preparation)
    committed = deterministic_commit.commit_deterministic_gated(
        tmp_path,
        preparation,
        prediction,
    )
    assert committed.get("status") != "block", committed
    binding = committed["owner_result_binding"]
    judgment, exact_owner = load_stage_input(
        tmp_path,
        binding["ref"],
        binding["sha256"],
        cycle_id=cycle_id,
        target="repo_skill_adapter_scan",
        input_kind="owner_result",
        preparation_id=preparation["preparation_id"],
        state_fingerprint=preparation["state_fingerprint"],
    )
    result = ResultBuilder().build(preparation, judgment)
    digest = canonical_sha256(result)
    path = result_path(
        tmp_path, cycle_id, "repo_skill_adapter_scan", digest
    )
    (tmp_path / "task.md").write_text(
        "# Task\n\nChanged after deterministic commit.\n",
        encoding="utf-8",
    )
    before = _tree(tmp_path)

    with pytest.raises(ValueError):
        publish_result(
            tmp_path,
            cycle_id,
            preparation,
            result,
            digest,
            input_bindings={
                "owner_result_binding": exact_owner,
                "deterministic_commit_binding": committed[
                    "deterministic_commit_binding"
                ],
            },
        )
    assert not path.exists()
    assert _tree(tmp_path) == before


def test_direct_deterministic_commit_repeats_fixed_gates_write_free(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    preparation = _scan_preparation(
        tmp_path, "cycle-direct-deterministic-gate"
    )
    prediction = dispatch_deterministic(tmp_path, preparation)
    assert not hasattr(deterministic_commit, "_mint_commit_permit")
    assert not hasattr(deterministic_commit, "_commit_deterministic")
    monkeypatch.setattr(
        "orchestrate_task_cycle.stage.gates.validate_submission_transition",
        lambda *_args, **_kwargs: {
            "status": "block",
            "findings": [{"code": "fixed_gate_rechecked"}],
        },
    )
    before = _tree(tmp_path)

    output = deterministic_commit.commit_deterministic_gated(
        tmp_path,
        preparation,
        prediction,
    )

    assert output["status"] == "block"
    assert output["effect_committed"] is False
    assert _tree(tmp_path) == before


def test_direct_packet_state_and_default_pipeline_bypass_are_closed(
    tmp_path: Path,
) -> None:
    cycle_id = "cycle-direct-packet-state"
    _scan_preparation(tmp_path, cycle_id)
    context = _packet_context(tmp_path, cycle_id)
    before = _tree(tmp_path)

    assert not hasattr(packet_builder, "DEFAULT_PIPELINE")
    assert packet_builder.__all__ == ["PacketBuilder"]
    with pytest.raises(ValueError):
        packet_builder.PacketState(
            target="governance",
            workflow_mode="normal",
            build_context=context,
            _legacy_v1_permit=object(),
        )
    forged_state = type(
        "ForgedPacketState",
        (),
        {
            "target": "governance",
            "workflow_mode": "normal",
            "build_context": context,
            "packet": {},
        },
    )()
    with pytest.raises(ValueError, match="authorized PacketState"):
        packet_builder.BasePacketStage().apply(forged_state)
    assert _tree(tmp_path) == before
