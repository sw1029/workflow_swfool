from __future__ import annotations

from .common import *

def normalize_stage_name(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip().lower().replace(" ", "_").replace("-", "_")
    return text or None

def normalize_execution_stage_ladder(value: Any) -> tuple[list[str], dict[str, set[str]], bool]:
    if value is None:
        return [], {}, False
    source = value
    classification_map_value: Any = None
    if isinstance(value, dict):
        classification_map_value = (
            value.get("terminal_classification_stage_map")
            or value.get("classification_stage_map")
            or value.get("terminal_stage_map")
        )
        for key in ("execution_stage_ladder", "stage_ladder", "stages", "ladder"):
            if key in value:
                source = value.get(key)
                break
    stages: list[str] = []
    if isinstance(source, list):
        for item in source:
            stage = item.get("name") if isinstance(item, dict) else item
            normalized = normalize_stage_name(stage)
            if normalized and normalized not in stages:
                stages.append(normalized)
    elif isinstance(source, dict):
        raw_stages = source.get("stages") or source.get("execution_stage_ladder") or source.get("stage_ladder")
        if isinstance(raw_stages, list):
            stages, _, _ = normalize_execution_stage_ladder(raw_stages)
        else:
            for key in source:
                if key in {"terminal_classification_stage_map", "classification_stage_map", "terminal_stage_map"}:
                    continue
                normalized = normalize_stage_name(key)
                if normalized and normalized not in stages:
                    stages.append(normalized)
    elif isinstance(source, str):
        for item in re.split(r"[,>\s]+", source):
            normalized = normalize_stage_name(item)
            if normalized and normalized not in stages:
                stages.append(normalized)
    return stages, normalize_classification_stage_map(classification_map_value), bool(stages)

def normalize_classification_stage_map(value: Any) -> dict[str, set[str]]:
    mapping: dict[str, set[str]] = {}
    if value is None:
        return mapping

    def add(classification: Any, stages: Any) -> None:
        key = normalize_root_family_key(classification)
        if not key:
            return
        stage_values = string_list(stages)
        if isinstance(stages, dict):
            for child_key in ("stages", "failure_stages", "allowed_failure_stages", "stage"):
                stage_values.extend(string_list(stages.get(child_key)))
        normalized_stages = {stage for item in stage_values if (stage := normalize_stage_name(item))}
        if normalized_stages:
            mapping.setdefault(key, set()).update(normalized_stages)

    if isinstance(value, dict):
        for classification, stages in value.items():
            add(classification, stages)
    elif isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                add(
                    item.get("classification") or item.get("terminal_classification") or item.get("name"),
                    item.get("stages") or item.get("failure_stages") or item.get("stage"),
                )
    return mapping

def next_failure_surface_stage(stages: list[str], last_successful_stage: str | None) -> str | None:
    if not stages or not last_successful_stage or last_successful_stage not in stages:
        return None
    index = stages.index(last_successful_stage)
    return stages[index + 1] if index + 1 < len(stages) else None


LAST_STAGE_KEYS = {"last_successful_stage", "last_completed_stage", "last_stage_reached"}
FAILURE_STAGE_KEYS = {"failure_surface_stage", "failed_stage", "failure_stage"}
TERMINAL_CLASSIFICATION_KEYS = {
    "terminal_classification",
    "terminal_outcome_classification",
    "classification",
    "failure_class",
    "recommended_disposition",
}


def terminal_stage_resolution_gate(
    *,
    ladder_value: Any,
    classification_map_value: Any,
    contexts: list[Any],
    root_family_key: str,
    dominant_parameter: str,
) -> dict[str, Any]:
    stages, embedded_map, ladder_provided = normalize_execution_stage_ladder(ladder_value)
    explicit_map = normalize_classification_stage_map(classification_map_value)
    classification_map = {**embedded_map, **explicit_map}
    last_stage = normalize_stage_name(first_field_value(contexts, LAST_STAGE_KEYS))
    failure_stage = normalize_stage_name(first_field_value(contexts, FAILURE_STAGE_KEYS)) or next_failure_surface_stage(stages, last_stage)
    terminal_classification = first_field_value(contexts, TERMINAL_CLASSIFICATION_KEYS)
    terminal_key = normalize_root_family_key(terminal_classification) if terminal_classification is not None else None
    mapped_stages = classification_map.get(terminal_key or "")
    contradiction = bool(failure_stage and mapped_stages and failure_stage not in mapped_stages)
    failure_surface_count_key = normalize_root_family_key(root_family_key, dominant_parameter, failure_stage) if failure_stage else None
    return {
        "gate": "H2-FAILURE-SURFACE-STAGE",
        "execution_stage_ladder_status": "provided" if ladder_provided else "not_provided",
        "execution_stage_ladder": stages,
        "terminal_classification_stage_map_status": "provided" if classification_map else "not_provided",
        "last_successful_stage": last_stage,
        "failure_surface_stage": failure_stage,
        "failure_surface_count_key": failure_surface_count_key,
        "terminal_classification": terminal_classification,
        "terminal_classification_key": terminal_key,
        "terminal_classification_allowed_stages": sorted(mapped_stages or []),
        "terminal_classification_stage_contradiction": contradiction,
        "terminal_classification_invalid_for_counting": contradiction,
        "root_dominant_parameter_key": dominant_parameter,
        "status": "block" if contradiction else ("pass" if failure_stage else "not_evaluated"),
        "constrains_disposition": contradiction,
        "allowed_dispositions": ["goal_productive", "terminal_blocked", "user_escalation"],
        "allowed_task_kinds": ["terminal_classification_stage_repair", "instrumentation_supply"],
    }

def same_input_contract_gate(contexts: list[Any]) -> dict[str, Any]:
    for value in contexts:
        for item in iter_dicts(value):
            match_value = (
                item.get("same_input_set_match")
                if "same_input_set_match" in item
                else item.get("same_window_window_count_match")
                if "same_window_window_count_match" in item
                else item.get("same_condition_input_set_match")
            )
            expected = (
                item.get("expected_input_set_size")
                or item.get("expected_window_count")
                or item.get("baseline_window_count")
                or item.get("target_input_set_size")
            )
            actual = (
                item.get("actual_input_set_size")
                or item.get("runtime_input_set_size")
                or item.get("runtime_window_count")
                or item.get("actual_window_count")
            )
            declared = bool_value(
                item.get("same_input_set_contract")
                or item.get("same_condition_contract")
                or item.get("same_window_contract")
            ) or match_value is not None or (expected is not None and actual is not None)
            if not declared:
                continue
            mismatch = (match_value is not None and not bool_value(match_value))
            if expected is not None and actual is not None:
                mismatch = mismatch or str(expected) != str(actual)
            return {
                "gate": "H2-SAME-INPUT-CONTRACT",
                "same_input_contract_declared": True,
                "expected_input_set_size": expected,
                "actual_input_set_size": actual,
                "same_input_set_match": not mismatch,
                "same_input_contract_violation": mismatch,
                "status": "block" if mismatch else "pass",
                "constrains_disposition": mismatch,
                "allowed_dispositions": ["goal_productive", "terminal_blocked", "user_escalation"],
                "allowed_task_kinds": ["input_set_contract_repair", "instrumentation_supply"],
            }
    return {
        "gate": "H2-SAME-INPUT-CONTRACT",
        "same_input_contract_declared": False,
        "same_input_contract_violation": False,
        "status": "not_evaluated",
        "constrains_disposition": False,
    }

def diagnostics_unavailable_gate(
    *,
    registry_rows: list[dict[str, Any]],
    failure_surface_count_key: str | None,
    contexts: list[Any],
    threshold: int,
) -> dict[str, Any]:
    diagnostics_unavailable = any(bool_value(first_field_value([context], {"diagnostics_unavailable"})) for context in contexts)
    streak = 1 if diagnostics_unavailable else 0
    if diagnostics_unavailable and failure_surface_count_key:
        for row in reversed(registry_rows):
            if row.get("failure_surface_count_key") != failure_surface_count_key:
                continue
            if bool_value(row.get("diagnostics_unavailable")):
                streak += 1
                continue
            break
    required = diagnostics_unavailable and streak >= max(1, threshold)
    return {
        "gate": "H3-DIAGNOSTICS-UNAVAILABLE",
        "diagnostics_unavailable": diagnostics_unavailable,
        "diagnostics_unavailable_streak": streak,
        "instrumentation_trigger_threshold": max(1, threshold),
        "instrumentation_supply_required": required,
        "status": "block" if required else ("warn" if diagnostics_unavailable else "not_applicable"),
        "constrains_disposition": required,
        "allowed_dispositions": ["goal_productive", "terminal_blocked", "user_escalation"],
        "allowed_task_kinds": ["instrumentation_supply", "execution_diagnostics_supply"],
    }
