from __future__ import annotations

from typing import Any

from . import families as _families
from . import measurement as _measurement
from . import values as _values
from . import vectors as _vectors
from .chain_adapter import row_vector_delta_passed

def cumulative_goal_distance_scope_key(artifact_family: str, root_family_key: str, facet_root_map_missing: bool) -> str:
    if facet_root_map_missing:
        return f"artifact_family:{_families.normalize_root_family_key(artifact_family)}"
    return f"root_family:{_families.normalize_root_family_key(root_family_key)}"

def row_goal_distance_scope(row: dict[str, Any], artifact_family: str, root_family_key: str, facet_root_map_missing: bool) -> str:
    existing = str(row.get("cumulative_goal_distance_scope_key") or "").strip()
    if existing:
        return existing
    if facet_root_map_missing:
        return f"artifact_family:{_families.normalize_root_family_key(row.get('artifact_family') or artifact_family)}"
    return f"root_family:{_families.normalize_root_family_key(row.get('root_family_key') or row.get('blocker_root_family') or root_family_key)}"

def cumulative_goal_distance_gate(
    rows: list[dict[str, Any]],
    *,
    artifact_family: str,
    root_family_key: str,
    facet_root_map_missing: bool,
    current_no_delta: bool,
    high_water: dict[str, Any],
    current_cycle_id: str,
    cap: int | None,
) -> dict[str, Any]:
    scope_key = cumulative_goal_distance_scope_key(artifact_family, root_family_key, facet_root_map_missing)
    budget_contract = _values.budget_evaluation(
        "cumulative_stall_attempts",
        cap,
        source="caller_or_repository_config",
    )
    cap_value = _values.budget_value(budget_contract)
    if not current_no_delta:
        return {
            "gate": "G-CHAIN",
            "cumulative_goal_distance_scope_key": scope_key,
            "cumulative_goal_distance_stall_streak": 0,
            "cumulative_goal_distance_stall_cap": cap_value,
            "budget_evaluation": budget_contract,
            "budget_evaluation_status": budget_contract["budget_evaluation_status"],
            "cumulative_goal_distance_stalled": False,
            "high_water_vector": _vectors.numeric_vector(high_water),
            "high_water_last_improved_cycle": current_cycle_id,
            "status": "ok",
            "constrains_disposition": False,
            "allowed_dispositions": ["terminal_blocked", "user_escalation"],
        }
    streak = 1 if current_no_delta else 0
    last_improved_cycle = current_cycle_id if not current_no_delta else None
    for row in reversed(rows):
        if row_goal_distance_scope(row, artifact_family, root_family_key, facet_root_map_missing) != scope_key:
            continue
        if row_vector_delta_passed(row):
            last_improved_cycle = str(row.get("cycle_id") or "") or None
            break
        streak += 1
    stalled = current_no_delta and cap_value is not None and streak >= cap_value
    return {
        "gate": "G-CHAIN",
        "cumulative_goal_distance_scope_key": scope_key,
        "cumulative_goal_distance_stall_streak": streak,
        "cumulative_goal_distance_stall_cap": cap_value,
        "budget_evaluation": budget_contract,
        "budget_evaluation_status": budget_contract["budget_evaluation_status"],
        "cumulative_goal_distance_stalled": stalled,
        "high_water_vector": _vectors.numeric_vector(high_water),
        "high_water_last_improved_cycle": last_improved_cycle,
        "status": "block" if stalled else "ok",
        "constrains_disposition": stalled,
        "allowed_dispositions": ["terminal_blocked", "user_escalation"],
    }

def first_actionable_capability_ladder_option(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    items: list[Any]
    if isinstance(value, dict):
        raw_items = (
            value.get("rungs")
            or value.get("items")
            or value.get("options")
            or value.get("capability_ladder")
            or value.get("next_rungs")
        )
        items = raw_items if isinstance(raw_items, list) else [value]
    elif isinstance(value, list):
        items = value
    else:
        return None
    for item in items:
        if not isinstance(item, dict):
            continue
        if _values.bool_value(item.get("satisfied") or item.get("complete") or item.get("blocked")):
            continue
        actionable_value = item.get("actionable")
        if actionable_value is not None and not _values.bool_value(actionable_value):
            continue
        kind = _measurement.normalize_task_kind(
            item.get("selected_task_kind")
            or item.get("task_kind")
            or item.get("kind")
            or item.get("rung")
            or item.get("name")
        )
        if not kind:
            continue
        return {
            "selected_task_kind": kind,
            "task_kind": kind,
            "rung": item.get("rung") or item.get("name") or kind,
            "provider_dependency": item.get("provider_dependency"),
            "authority_allowed": item.get("authority_allowed"),
            "uses_only_local_data": item.get("uses_only_local_data"),
            "source": "capability_ladder",
        }
    return None

def chain_stall_forced_retarget_gate(
    chain_gate: dict[str, Any],
    *,
    blocker_mutation: str,
    adapter_gate: dict[str, Any],
    capability_ladder_option: dict[str, Any] | None,
) -> dict[str, Any]:
    stalled = _values.bool_value(chain_gate.get("cumulative_goal_distance_stalled"))
    streak = _values.int_metric(chain_gate.get("cumulative_goal_distance_stall_streak"))
    cap = _values.positive_int_or_none(chain_gate.get("cumulative_goal_distance_stall_cap"))
    lateral = blocker_mutation in {"facet_rename", "lateral", "repeat"}
    # The repository-supplied stall cap is the sole numeric policy boundary.
    # Do not derive a second generic threshold from it.
    force = stalled and lateral and cap is not None and streak >= cap
    options: list[dict[str, Any]] = []
    if force and _values.bool_value(adapter_gate.get("adapter_wiring_defect")):
        options.append(
            {
                "selected_task_kind": "adapter_wiring_fix",
                "task_kind": "adapter_wiring_fix",
                "source": "adapter_wiring_gate",
                "actionable": True,
            }
        )
    if force and capability_ladder_option:
        options.append({**capability_ladder_option, "actionable": True})
    return {
        "gate": "G-CHAIN-FORCED-RETARGET",
        "chain_stall_force_retarget": force,
        "cumulative_goal_distance_stall_streak": streak,
        "cumulative_goal_distance_stall_cap": cap,
        "blocker_mutation_kind": blocker_mutation,
        "forced_selected_task_options": options,
        "forced_selected_task": options[0] if options else None,
        "status": "block" if force and options else ("warn" if force else "ok"),
        "constrains_disposition": force and bool(options),
        "allowed_dispositions": ["goal_productive", "terminal_blocked", "user_escalation"],
        "allowed_task_kinds": [option["selected_task_kind"] for option in options if option.get("selected_task_kind")],
    }
