from __future__ import annotations

from typing import Any

from . import registry as _registry
from . import values as _values
from . import vectors as _vectors

def row_vector_delta_passed(row: dict[str, Any]) -> bool:
    coverage_gate = row.get("coverage_quality_delta_gate")
    substance_gate = row.get("substance_delta_gate")
    return any(
        (
            _values.bool_value(row.get("semantic_progress")),
            isinstance(coverage_gate, dict) and _values.bool_value(coverage_gate.get("quality_delta_pass")),
            isinstance(substance_gate, dict) and _values.bool_value(substance_gate.get("substance_delta_pass")),
        )
    )

def adapter_contract_unmet_fields(
    *,
    facet_root_map_missing: bool,
    substance_gate: dict[str, Any],
    quality: dict[str, Any],
) -> list[str]:
    unmet: list[str] = []
    if facet_root_map_missing:
        unmet.append("facet_root_map")
    if str(substance_gate.get("status") or "").lower() == "missing" or not _vectors.numeric_vector(
        substance_gate.get("current_substance_vector")
    ):
        unmet.append("substance_metrics")
    if not _vectors.numeric_vector(quality):
        unmet.append("quality_vector")
    return sorted(dict.fromkeys(unmet))

def row_adapter_contract_unmet(row: dict[str, Any]) -> list[str]:
    if isinstance(row.get("adapter_contract_unmet"), list):
        return _values.list_values(row.get("adapter_contract_unmet"))
    substance_gate = row.get("substance_delta_gate") if isinstance(row.get("substance_delta_gate"), dict) else {}
    return adapter_contract_unmet_fields(
        facet_root_map_missing=_values.bool_value(row.get("facet_root_map_missing")),
        substance_gate=substance_gate,
        quality=row.get("quality_vector") if isinstance(row.get("quality_vector"), dict) else {},
    )

def adapter_missing_streak(
    rows: list[dict[str, Any]],
    artifact_family: str,
    current_contract_unmet: list[str],
    current_no_delta: bool,
) -> int:
    if not current_contract_unmet or not current_no_delta:
        return 0
    streak = 1
    for row in reversed(rows):
        if str(row.get("artifact_family") or "") != artifact_family:
            continue
        if row_adapter_contract_unmet(row) and not row_vector_delta_passed(row):
            streak += 1
            continue
        break
    return streak

def adapter_mandate_gate(
    rows: list[dict[str, Any]],
    *,
    artifact_family: str,
    contract_unmet: list[str],
    current_no_delta: bool,
    cap: int | None,
    adapter_hook_demand: list[dict[str, Any]] | None = None,
    hook_demand_threshold: int | None = None,
) -> dict[str, Any]:
    streak = adapter_missing_streak(rows, artifact_family, contract_unmet, current_no_delta)
    cap_contract = _values.budget_evaluation("adapter_mandate_attempts", cap, source="caller_or_repository_config")
    cap_value = _values.budget_value(cap_contract)
    required = bool(contract_unmet) and current_no_delta and cap_value is not None and streak >= cap_value
    hook_contract = _values.budget_evaluation(
        "hook_demand_attempts",
        hook_demand_threshold,
        source="adapter_or_repository_config",
    )
    threshold = _values.budget_value(hook_contract)
    demand_rows = [item for item in (adapter_hook_demand or []) if isinstance(item, dict)]
    demanded_hooks = sorted(
        _registry.normalize_hook_id(item.get("hook_id"))
        for item in demand_rows
        if _registry.normalize_hook_id(item.get("hook_id"))
        and threshold is not None
        and int(_values.float_value(item.get("decision_relevant_skip_count")) or 0) >= threshold
    )
    hook_supply_required = bool(demanded_hooks)
    result = {
        "gate": "G-ADAPTER",
        "adapter_mandate_required": required,
        "adapter_missing_streak": streak,
        "adapter_missing_streak_cap": cap_value,
        "budget_evaluation": cap_contract,
        "budget_evaluation_status": cap_contract["budget_evaluation_status"],
        "adapter_contract_unmet": contract_unmet,
        "quality_high_water_unimproved": current_no_delta,
        "status": "block" if required else ("warn" if contract_unmet or demand_rows else "ok"),
        "constrains_disposition": required,
        "allowed_dispositions": ["goal_productive", "terminal_blocked", "user_escalation"],
    }
    if demand_rows:
        result.update(
            {
                "adapter_hook_demand": demand_rows,
                "hook_demand_threshold": threshold,
                "hook_demand_budget_evaluation": hook_contract,
                "hook_demand_threshold_unverified": threshold is None,
                "hook_supply_required": hook_supply_required,
                "demanded_hooks": demanded_hooks,
            }
        )
    if len(demanded_hooks) >= 2:
        result["recommended_task_kind"] = "adapter_hook_batch_supply"
        result["allowed_task_kinds"] = ["adapter_hook_batch_supply"]
    return result

def adapter_wiring_gate(
    *,
    registered: bool,
    loaded: bool,
    expected_path: str | None,
    loaded_path: str | None,
    load_error: str | None,
) -> dict[str, Any]:
    defect = registered and not loaded
    return {
        "gate": "G-ADAPTER-WIRING",
        "adapter_registered": registered,
        "adapter_loaded": loaded,
        "adapter_expected_path": expected_path,
        "adapter_path": loaded_path or expected_path,
        "adapter_load_error": load_error,
        "adapter_wiring_defect": defect,
        "self_inflicted_gate_defect": defect,
        "local": defect,
        "in_scope": defect,
        "actionable": defect,
        "status": "block" if defect else ("ok" if loaded else "not_applicable"),
        "constrains_disposition": defect,
        "allowed_dispositions": ["goal_productive", "terminal_blocked", "user_escalation"],
        "allowed_task_kinds": ["adapter_wiring_fix", "adapter_load_fix"],
        "recommended_disposition": "self_inflicted_gate_defect" if defect else None,
    }
