from __future__ import annotations

from .common import *
from .registry import normalize_hook_id

def row_vector_delta_passed(row: dict[str, Any]) -> bool:
    coverage_gate = row.get("coverage_quality_delta_gate")
    substance_gate = row.get("substance_delta_gate")
    return any(
        (
            bool_value(row.get("semantic_progress")),
            isinstance(coverage_gate, dict) and bool_value(coverage_gate.get("quality_delta_pass")),
            isinstance(substance_gate, dict) and bool_value(substance_gate.get("substance_delta_pass")),
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
    if str(substance_gate.get("status") or "").lower() == "missing" or not numeric_vector(
        substance_gate.get("current_substance_vector")
    ):
        unmet.append("substance_metrics")
    if not numeric_vector(quality):
        unmet.append("quality_vector")
    return sorted(dict.fromkeys(unmet))

def row_adapter_contract_unmet(row: dict[str, Any]) -> list[str]:
    if isinstance(row.get("adapter_contract_unmet"), list):
        return list_values(row.get("adapter_contract_unmet"))
    substance_gate = row.get("substance_delta_gate") if isinstance(row.get("substance_delta_gate"), dict) else {}
    return adapter_contract_unmet_fields(
        facet_root_map_missing=bool_value(row.get("facet_root_map_missing")),
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
    cap: int,
    adapter_hook_demand: list[dict[str, Any]] | None = None,
    hook_demand_threshold: int = HOOK_DEMAND_THRESHOLD_DEFAULT,
) -> dict[str, Any]:
    streak = adapter_missing_streak(rows, artifact_family, contract_unmet, current_no_delta)
    required = bool(contract_unmet) and current_no_delta and streak >= max(1, cap)
    threshold = max(1, int(hook_demand_threshold or HOOK_DEMAND_THRESHOLD_DEFAULT))
    demand_rows = [item for item in (adapter_hook_demand or []) if isinstance(item, dict)]
    demanded_hooks = sorted(
        normalize_hook_id(item.get("hook_id"))
        for item in demand_rows
        if normalize_hook_id(item.get("hook_id"))
        and int(float_value(item.get("decision_relevant_skip_count")) or 0) >= threshold
    )
    hook_supply_required = bool(demanded_hooks)
    result = {
        "gate": "G-ADAPTER",
        "adapter_mandate_required": required,
        "adapter_missing_streak": streak,
        "adapter_missing_streak_cap": max(1, cap),
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


def consumer_context_conformance_gate(*values: Any) -> dict[str, Any]:
    required_ids = list_values(first_field_value(list(values), {"required_consumer_ids"}))
    rows_value = first_field_value(list(values), {"consumer_context_conformance", "adapter_consumer_conformance"})
    if isinstance(rows_value, dict):
        rows = rows_value.get("rows") or []
    else:
        rows = rows_value if isinstance(rows_value, list) else []
    by_id = {
        str(row.get("consumer_context_id")): row
        for row in rows
        if isinstance(row, dict) and row.get("consumer_context_id")
    }
    missing: list[str] = []
    normalized: list[dict[str, Any]] = []
    for consumer_id in required_ids:
        row = by_id.get(str(consumer_id)) or {}
        valid = bool(row) and all(
            bool_value(row.get(field))
            for field in ("adapter_loaded", "required_hook_callable", "hook_signature_compatible", "return_contract_valid")
        ) and bool(str(row.get("probe_evidence_id") or "").strip())
        normalized.append({
            "consumer_context_id": str(consumer_id),
            "adapter_loaded": bool_value(row.get("adapter_loaded")),
            "required_hook_callable": bool_value(row.get("required_hook_callable")),
            "hook_signature_compatible": bool_value(row.get("hook_signature_compatible")),
            "return_contract_valid": bool_value(row.get("return_contract_valid")),
            "probe_evidence_id": row.get("probe_evidence_id"),
            "status": "pass" if valid else "not_evaluated",
        })
        if not valid:
            missing.append(str(consumer_id))
    return {
        "required_consumer_ids": required_ids,
        "rows": normalized,
        "missing_consumer_context_ids": missing,
        "status": "pass" if required_ids and not missing else ("not_evaluated" if required_ids else "not_applicable"),
    }

def cumulative_goal_distance_scope_key(artifact_family: str, root_family_key: str, facet_root_map_missing: bool) -> str:
    if facet_root_map_missing:
        return f"artifact_family:{normalize_root_family_key(artifact_family)}"
    return f"root_family:{normalize_root_family_key(root_family_key)}"

def row_goal_distance_scope(row: dict[str, Any], artifact_family: str, root_family_key: str, facet_root_map_missing: bool) -> str:
    existing = str(row.get("cumulative_goal_distance_scope_key") or "").strip()
    if existing:
        return existing
    if facet_root_map_missing:
        return f"artifact_family:{normalize_root_family_key(row.get('artifact_family') or artifact_family)}"
    return f"root_family:{normalize_root_family_key(row.get('root_family_key') or row.get('blocker_root_family') or root_family_key)}"

def cumulative_goal_distance_gate(
    rows: list[dict[str, Any]],
    *,
    artifact_family: str,
    root_family_key: str,
    facet_root_map_missing: bool,
    current_no_delta: bool,
    high_water: dict[str, Any],
    current_cycle_id: str,
    cap: int,
) -> dict[str, Any]:
    scope_key = cumulative_goal_distance_scope_key(artifact_family, root_family_key, facet_root_map_missing)
    if not current_no_delta:
        return {
            "gate": "G-CHAIN",
            "cumulative_goal_distance_scope_key": scope_key,
            "cumulative_goal_distance_stall_streak": 0,
            "cumulative_goal_distance_stall_cap": max(1, cap),
            "cumulative_goal_distance_stalled": False,
            "high_water_vector": numeric_vector(high_water),
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
    stalled = current_no_delta and streak >= max(1, cap)
    return {
        "gate": "G-CHAIN",
        "cumulative_goal_distance_scope_key": scope_key,
        "cumulative_goal_distance_stall_streak": streak,
        "cumulative_goal_distance_stall_cap": max(1, cap),
        "cumulative_goal_distance_stalled": stalled,
        "high_water_vector": numeric_vector(high_water),
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
        if bool_value(item.get("satisfied") or item.get("complete") or item.get("blocked")):
            continue
        actionable_value = item.get("actionable")
        if actionable_value is not None and not bool_value(actionable_value):
            continue
        kind = normalize_task_kind(
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
    stalled = bool_value(chain_gate.get("cumulative_goal_distance_stalled"))
    streak = int_metric(chain_gate.get("cumulative_goal_distance_stall_streak"))
    cap = max(1, int_metric(chain_gate.get("cumulative_goal_distance_stall_cap")) or 1)
    lateral = blocker_mutation in {"facet_rename", "lateral", "repeat"}
    force = stalled and lateral and streak >= cap * 2
    options: list[dict[str, Any]] = []
    if force and bool_value(adapter_gate.get("adapter_wiring_defect")):
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

def semantic_progress_from_high_water(
    quality: dict[str, Any],
    prev_high: dict[str, Any],
    provider_request_count: int,
    epsilon: float,
) -> bool:
    if quality.get("quality_signal_confidence") == "low":
        return False
    return bool(coverage_quality_delta_gate(quality, prev_high, provider_request_count, epsilon)["quality_delta_pass"])

def updated_high_water(
    quality: dict[str, Any],
    prev_high: dict[str, Any],
    provider_request_count: int,
    allowed_quality_keys: set[str] | None = None,
) -> dict[str, Any]:
    def updated(key: str) -> bool:
        return allowed_quality_keys is None or key in allowed_quality_keys

    return {
        "event_named_ratio": (
            max(high_water_metric_value(prev_high, "event_named_ratio"), quality_metric_value(quality, "event_named_ratio"))
            if updated("event_named_ratio")
            else high_water_metric_value(prev_high, "event_named_ratio")
        ),
        "proper_noun_character_ratio": max(
            high_water_metric_value(prev_high, "proper_noun_character_ratio"),
            quality_metric_value(quality, "proper_noun_character_ratio"),
        )
        if updated("proper_noun_character_ratio")
        else high_water_metric_value(prev_high, "proper_noun_character_ratio"),
        "coreference_resolved_ratio": max(
            high_water_metric_value(prev_high, "coreference_resolved_ratio"),
            quality_metric_value(quality, "coreference_resolved_ratio"),
        )
        if updated("coreference_resolved_ratio")
        else high_water_metric_value(prev_high, "coreference_resolved_ratio"),
        "causal_edge_count": max(
            int_metric(high_water_metric_value(prev_high, "causal_edge_count")),
            int_metric(quality_metric_value(quality, "causal_edge_count")),
        )
        if updated("causal_edge_count")
        else int_metric(high_water_metric_value(prev_high, "causal_edge_count")),
        "windows_covered": max(
            int_metric(high_water_metric_value(prev_high, "windows_covered")),
            int_metric(quality_metric_value(quality, "windows_covered")),
        )
        if updated("windows_covered")
        else int_metric(high_water_metric_value(prev_high, "windows_covered")),
        "ever_causal_edge": bool_value(prev_high.get("ever_causal_edge"))
        or (updated("causal_edge_count") and bool_value(quality.get("causal_edge_present"))),
        "ever_provider_dispatch": bool_value(prev_high.get("ever_provider_dispatch")) or provider_request_count > 0,
    }

def previous_primary_metric_value(latest: dict[str, Any] | None) -> float:
    if not isinstance(latest, dict):
        return 0.0
    gate = latest.get("primary_metric_gate")
    if isinstance(gate, dict):
        for key in ("primary_metric_high_water", "primary_metric_value", "value"):
            if key in gate:
                return float_value(gate.get(key))
    for key in ("primary_metric_high_water", "primary_metric_value"):
        if key in latest:
            return float_value(latest.get(key))
    return 0.0

def primary_metric_zero_movement_streak(
    rows: list[dict[str, Any]],
    scope_key: str,
    moved: bool,
) -> int:
    if moved:
        return 0
    streak = 1
    for row in reversed(rows):
        gate = row.get("primary_metric_gate")
        if not isinstance(gate, dict):
            continue
        row_scope = str(gate.get("primary_metric_scope_key") or row.get("cumulative_goal_distance_scope_key") or "")
        if row_scope != scope_key:
            continue
        if bool_value(gate.get("primary_metric_high_water_moved")):
            break
        streak += 1
    return streak

def normalize_primary_metric_gate(
    value: Any,
    *,
    previous_value: float,
    rows: list[dict[str, Any]],
    scope_key: str,
    cap: int,
    epsilon: float,
    provenance: dict[str, str],
    provenance_hook_provided: bool,
) -> dict[str, Any]:
    if value is None:
        return {
            "gate": "G-CHAIN-PRIMARY-METRIC",
            "evaluation_status": "not_evaluated",
            "status": "not_evaluated",
            "constrains_disposition": False,
        }
    source = value
    if isinstance(value, dict) and isinstance(value.get("primary_metric"), dict):
        source = value["primary_metric"]
    if not isinstance(source, dict):
        source = {"value": value}
    metric_id = str(source.get("metric_id") or source.get("name") or "primary_metric")
    current_value = float_value(
        source.get("value")
        if "value" in source
        else source.get("primary_metric_value")
        if "primary_metric_value" in source
        else source.get("current")
    )
    previous = float_value(source.get("previous_value") or source.get("previous_primary_metric") or previous_value)
    raw_moved = (
        bool_value(source.get("primary_metric_high_water_moved"))
        if "primary_metric_high_water_moved" in source
        else current_value > previous + epsilon
    )
    metric_provenance = normalize_provenance_label(
        source.get("evidence_provenance")
        or source.get("provenance")
        or provenance_for_metric(metric_id, provenance, provenance_hook_provided)
        or provenance_for_metric("primary_metric", provenance, provenance_hook_provided)
    )
    independent = not provenance_hook_provided or metric_provenance == "independently_verified"
    moved = raw_moved and independent
    attested_only = raw_moved and not independent
    zero_streak = primary_metric_zero_movement_streak(rows, scope_key, moved)
    adapter_stalled = bool_value(
        source.get("primary_metric_stalled")
        or (value.get("primary_metric_stalled") if isinstance(value, dict) else False)
    )
    stalled = adapter_stalled or (not moved and zero_streak >= max(1, cap))
    return {
        "gate": "G-CHAIN-PRIMARY-METRIC",
        "metric_id": metric_id,
        "primary_metric_value": current_value,
        "previous_primary_metric_value": previous,
        "primary_metric_high_water": max(previous, current_value) if moved else previous,
        "primary_metric_high_water_moved": moved,
        "raw_primary_metric_high_water_moved": raw_moved,
        "evidence_provenance": metric_provenance,
        "attested_only_movement": attested_only,
        "primary_metric_scope_key": scope_key,
        "primary_metric_zero_movement_streak": zero_streak,
        "primary_metric_stall_cap": max(1, cap),
        "primary_metric_stalled": stalled,
        "evaluation_status": "pass" if moved else "fail",
        "status": "block" if stalled else ("warn" if attested_only else ("pass" if moved else "ok")),
        "constrains_disposition": stalled,
        "allowed_dispositions": ["goal_productive", "terminal_blocked", "user_escalation"],
    }
