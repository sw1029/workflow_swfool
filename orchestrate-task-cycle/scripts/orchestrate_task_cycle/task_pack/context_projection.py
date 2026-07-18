"""Read-only task-pack projection for cycle selection context."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .state_machine import derived_operational_status, earliest_ready_item
from .validation import validate_pack


def _relative(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _load(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _selectable_projection(
    root: Path, path: Path, data: dict[str, Any], operational_status: str
) -> dict[str, Any]:
    items = data.get("items") if isinstance(data.get("items"), list) else []
    next_item = earliest_ready_item(data)
    return {
        "path": _relative(root, path),
        "render_path": _relative(root, path.with_suffix(".md"))
        if path.with_suffix(".md").is_file()
        else None,
        "pack_id": data.get("pack_id"),
        "status": str(data.get("status") or "unknown"),
        "operational_status": operational_status,
        "goal": data.get("goal"),
        "current_item_id": data.get("current_item_id"),
        "next_item": next_item,
        "queue_disposition": "ready"
        if next_item
        else "waiting_blocked"
        if operational_status == "blocked"
        else "in_flight",
        "planned_item_count": sum(
            1
            for item in items
            if isinstance(item, dict)
            and item.get("status") in {"planned", "inserted", "reordered"}
        ),
        "terminal_blocker": data.get("terminal_blocker"),
    }


def collect_task_pack_projection(
    root: Path, paths: list[Path], max_files: int
) -> dict[str, Any]:
    """Return declared, operational, repair, and unambiguous selection state."""

    declared_counts: dict[str, int] = {}
    operational_counts: dict[str, int] = {}
    selectable: list[dict[str, Any]] = []
    repairs: list[dict[str, Any]] = []
    for path in paths:
        data = _load(path)
        declared = str(data.get("status") if isinstance(data, dict) else "unknown")
        declared_counts[declared] = declared_counts.get(declared, 0) + 1
        if data is None:
            operational_counts["invalid"] = operational_counts.get("invalid", 0) + 1
            repairs.append(
                {
                    "path": _relative(root, path),
                    "declared_status": declared,
                    "operational_status": "invalid",
                    "blocking_finding_count": 1,
                    "blocking_finding_codes": ["pack_json_invalid"],
                }
            )
            continue

        operational = derived_operational_status(data)
        operational_counts[operational] = operational_counts.get(operational, 0) + 1
        blocking_codes = sorted(
            {
                str(finding.get("code") or "unknown_pack_finding")
                for finding in validate_pack(data, path)
                if finding.get("severity") == "block"
            }
        )
        if blocking_codes:
            repairs.append(
                {
                    "path": _relative(root, path),
                    "pack_id": data.get("pack_id"),
                    "declared_status": declared,
                    "operational_status": operational,
                    "blocking_finding_count": len(blocking_codes),
                    "blocking_finding_codes": blocking_codes[:24],
                }
            )
        elif operational in {"active", "blocked"}:
            selectable.append(_selectable_projection(root, path, data, operational))

    selection_status = (
        "repair_required"
        if repairs
        else "multiple_live_packs"
        if len(selectable) > 1
        else "ready"
        if selectable
        else "none"
    )
    return {
        "status_counts": declared_counts,
        "declared_status_counts": declared_counts,
        "operational_status_counts": operational_counts,
        "active_count": declared_counts.get("active", 0),
        "live_count": declared_counts.get("active", 0)
        + declared_counts.get("blocked", 0),
        "operational_live_count": operational_counts.get("active", 0)
        + operational_counts.get("blocked", 0),
        "selectable_live_count": len(selectable),
        "selection_status": selection_status,
        "repair_required_count": len(repairs),
        "repair_required_packs": repairs[:max_files],
        "active_pack": selectable[0] if selection_status == "ready" else None,
    }
