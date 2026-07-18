from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from orchestrate_task_cycle.collect_cycle_context import collect_task


def _item(
    item_id: str,
    order: int,
    *,
    status: str = "planned",
    dependencies: list[str] | None = None,
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "item_id": item_id,
        "order": order,
        "status": status,
        "title": item_id,
        "objective": "Perform bounded work.",
        "validation_profile": "current_only",
        "progress_target": "advanced",
    }
    if dependencies is not None:
        item["dependencies"] = dependencies
    return item


def _write_pack(
    root: Path,
    pack_id: str,
    *,
    status: str,
    current_item_id: str | None,
    items: list[dict[str, Any]],
) -> Path:
    path = root / ".task" / "task_pack" / f"{pack_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "pack_id": pack_id,
                "status": status,
                "goal": "Exercise the operational projection.",
                "current_item_id": current_item_id,
                "items": items,
                "mutation_log": [],
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return path


def test_collect_task_selects_only_a_coherent_operationally_live_pack(
    tmp_path: Path,
) -> None:
    _write_pack(
        tmp_path,
        "pack-ready",
        status="active",
        current_item_id="item-a",
        items=[_item("item-a", 1), _item("item-b", 2, dependencies=["item-a"])],
    )

    task = collect_task(tmp_path, max_files=20)["task_pack"]

    assert task["selection_status"] == "ready"
    assert task["repair_required_count"] == 0
    assert task["selectable_live_count"] == 1
    assert task["active_pack"]["pack_id"] == "pack-ready"
    assert task["active_pack"]["next_item"]["item_id"] == "item-a"


def test_collect_task_routes_declared_completed_residual_to_repair(
    tmp_path: Path,
) -> None:
    _write_pack(
        tmp_path,
        "pack-residual",
        status="completed",
        current_item_id=None,
        items=[
            _item("item-a", 1, status="skipped"),
            _item("item-b", 2, dependencies=["item-a"]),
        ],
    )

    task = collect_task(tmp_path, max_files=20)["task_pack"]

    assert task["declared_status_counts"] == {"completed": 1}
    assert task["operational_status_counts"] == {"blocked": 1}
    assert task["operational_live_count"] == 1
    assert task["selection_status"] == "repair_required"
    assert task["active_pack"] is None
    repair = task["repair_required_packs"][0]
    assert repair["declared_status"] == "completed"
    assert repair["operational_status"] == "blocked"
    assert {
        "completed_pack_has_noncompleted_items",
        "pack_operational_status_mismatch",
    } <= set(repair["blocking_finding_codes"])


def test_collect_task_does_not_arbitrarily_choose_between_live_packs(
    tmp_path: Path,
) -> None:
    for pack_id in ("pack-a", "pack-b"):
        _write_pack(
            tmp_path,
            pack_id,
            status="active",
            current_item_id="item-a",
            items=[_item("item-a", 1)],
        )

    task = collect_task(tmp_path, max_files=20)["task_pack"]

    assert task["selection_status"] == "multiple_live_packs"
    assert task["selectable_live_count"] == 2
    assert task["active_pack"] is None
