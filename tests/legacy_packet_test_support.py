"""Test-only helper that exercises the sealed protocol-v1 packet facade."""

from __future__ import annotations

import copy
from pathlib import Path
import tempfile
from typing import Any

from orchestrate_task_cycle import render_subskill_packet as facade
from historical_cycle_test_support import create_sealed_legacy_v1_cycle


def build_unbound_legacy_packet(
    target: str,
    context: dict[str, Any],
    stage: dict[str, Any],
    workflow_mode: str = "normal",
) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(
        prefix="orchestrate-legacy-packet-"
    ) as temporary:
        root = Path(temporary)
        cycle_id = "cycle-legacy-packet-unit"
        supplied_task_ids = {
            str(value)
            for value in (
                context.get("task_id"),
                stage.get("task_id"),
            )
            if value is not None and str(value).strip()
        }
        if len(supplied_task_ids) > 1:
            raise ValueError("legacy packet test inputs contain conflicting tasks")
        task_id = next(
            iter(supplied_task_ids), "task-legacy-packet-unit"
        )
        create_sealed_legacy_v1_cycle(
            root,
            cycle_id,
            task_id,
            "legacy packet unit rendering",
        )
        exact_context = copy.deepcopy(context)
        exact_stage = copy.deepcopy(stage)
        exact_context["workspace"] = str(root)
        cycle_state = (
            exact_context.get("cycle_state")
            if isinstance(exact_context.get("cycle_state"), dict)
            else {}
        )
        current_stage = (
            cycle_state.get("current_stage")
            if isinstance(cycle_state.get("current_stage"), dict)
            else {}
        )
        cycle_state.update(
            {
                "latest_cycle_id": cycle_id,
                "current_stage": {
                    **current_stage,
                    "cycle_id": cycle_id,
                },
            }
        )
        exact_context["cycle_state"] = cycle_state
        exact_stage["cycle_id"] = cycle_id
        return facade.packet_for(
            target,
            exact_context,
            exact_stage,
            workflow_mode,
        )
