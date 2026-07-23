from __future__ import annotations

from pathlib import Path

import pytest

from orchestrate_task_cycle import cycle_ledger
from orchestrate_task_cycle import render_subskill_packet
from orchestrate_task_cycle.packet.builder import PacketBuilder
from orchestrate_task_cycle.packet.context import PacketBuildContext
from compiler_first_fixture_support import create_sealed_legacy_v1_cycle


def _packet_inputs(
    root: Path, cycle_id: str
) -> tuple[dict[str, object], dict[str, object]]:
    return (
        {
            "workspace": str(root),
            "cycle_state": {"latest_cycle_id": cycle_id},
        },
        {"cycle_id": cycle_id},
    )


def _build_context(
    context: dict[str, object], stage: dict[str, object]
) -> PacketBuildContext:
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


def test_direct_packet_builder_rejects_missing_or_forged_permit(
    tmp_path: Path,
) -> None:
    cycle_id = "cycle-direct-packet-builder-v2"
    cycle_ledger.init_cycle(
        tmp_path,
        cycle_id,
        "task-1",
        "compiler-first direct builder rejection",
    )
    context, stage = _packet_inputs(tmp_path, cycle_id)
    build_context = _build_context(context, stage)

    with pytest.raises(ValueError, match="opaque verified protocol-v1 permit"):
        PacketBuilder().build("governance", build_context, "normal")
    with pytest.raises(ValueError, match="opaque verified protocol-v1 permit"):
        PacketBuilder().build(
            "governance",
            build_context,
            "normal",
            _legacy_v1_permit=object(),
        )
    with pytest.raises(
        ValueError, match="generic full packet rendering is disabled"
    ):
        render_subskill_packet.packet_for(
            "governance", context, stage, "normal"
        )


def test_sealed_legacy_facade_remains_the_full_packet_path(
    tmp_path: Path,
) -> None:
    cycle_id = "cycle-sealed-packet-builder-v1"
    create_sealed_legacy_v1_cycle(
        tmp_path,
        cycle_id,
        "task-1",
        "sealed legacy packet rendering",
    )
    context, stage = _packet_inputs(tmp_path, cycle_id)

    packet = render_subskill_packet.packet_for(
        "governance", context, stage, "normal"
    )

    assert packet["target"] == "governance"
    assert packet["routing"]["code_worker"]["profile_id"] == "code_worker"
