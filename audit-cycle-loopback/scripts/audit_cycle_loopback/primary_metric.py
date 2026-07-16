from __future__ import annotations

import math
import re
from typing import Any

from . import families as _families
from . import quality as _quality
from . import values as _values
from . import vectors as _vectors
from . import verification as _verification

def semantic_progress_from_high_water(
    quality: dict[str, Any],
    prev_high: dict[str, Any],
    provider_request_count: int,
    epsilon: float,
    quality_delta_policy: Any = None,
) -> bool:
    if quality.get("quality_signal_confidence") == "low":
        return False
    return bool(
        _quality.coverage_quality_delta_gate(
            quality,
            prev_high,
            provider_request_count,
            epsilon,
            quality_delta_policy,
        )["quality_delta_pass"]
    )

def updated_high_water(
    quality: dict[str, Any],
    prev_high: dict[str, Any],
    provider_request_count: int,
    allowed_quality_keys: set[str] | None = None,
    quality_delta_policy: Any = None,
) -> dict[str, Any]:
    policy = _quality.normalize_quality_delta_policy(quality_delta_policy)

    def updated(key: str) -> bool:
        return allowed_quality_keys is None or key in allowed_quality_keys

    result: dict[str, Any] = {}
    for key in policy["keys"]:
        previous = _quality.high_water_metric_value(prev_high, key, policy["aliases"])
        current = _quality.quality_metric_value(quality, key, policy["aliases"])
        result[key] = max(previous, current) if updated(key) else previous
    result["ever_provider_dispatch"] = _values.bool_value(prev_high.get("ever_provider_dispatch")) or provider_request_count > 0
    return result

def previous_primary_metric_value(latest: dict[str, Any] | None) -> float:
    if not isinstance(latest, dict):
        return 0.0
    gate = latest.get("primary_metric_gate")
    if isinstance(gate, dict):
        for key in ("primary_metric_high_water", "primary_metric_value", "value"):
            if key in gate:
                return _values.float_value(gate.get(key))
    for key in ("primary_metric_high_water", "primary_metric_value"):
        if key in latest:
            return _values.float_value(latest.get(key))
    return 0.0

def primary_metric_zero_movement_streak(
    rows: list[dict[str, Any]],
    scope_key: str,
    moved: bool,
    comparable: bool,
) -> int:
    if moved:
        return 0
    if not comparable:
        return 0
    streak = 1
    for row in reversed(rows):
        gate = row.get("primary_metric_gate")
        if not isinstance(gate, dict):
            continue
        row_scope = str(gate.get("primary_metric_scope_key") or row.get("cumulative_goal_distance_scope_key") or "")
        if row_scope != scope_key:
            continue
        if _values.bool_value(gate.get("primary_metric_high_water_moved")):
            break
        if gate.get("previous_primary_metric_value") is None:
            break
        streak += 1
    return streak

def primary_metric_registry_high_water(
    rows: list[dict[str, Any]],
    scope_key: str,
) -> float | None:
    values: list[float] = []
    for row in rows:
        gate = row.get("primary_metric_gate")
        if not isinstance(gate, dict):
            continue
        if str(gate.get("primary_metric_scope_key") or "") != scope_key:
            continue
        if gate.get("artifact_binding_status") != "exact":
            continue
        if gate.get("evidence_provenance") != "independently_verified":
            continue
        if gate.get("independent_source_separation_status") != "pass":
            continue
        if not _values.bool_value(gate.get("decision_contribution_allowed")):
            continue
        if gate.get("primary_metric_high_water") is not None:
            values.append(_values.float_value(gate.get("primary_metric_high_water")))
    return max(values) if values else None

def primary_metric_artifact_binding(
    source: dict[str, Any],
    expected: dict[str, Any],
) -> tuple[bool, list[str]]:
    echoed = source.get("decision_artifact_ref")
    if not isinstance(echoed, dict):
        echoed = source
    mismatches: list[str] = []
    expected_body = str(expected.get("body_projection_fingerprint") or "").strip().lower()
    expected_cohort_present = bool(_vectors.string_list(expected.get("verification_input_ids"))) or bool(
        expected.get("input_fingerprints")
        if isinstance(expected.get("input_fingerprints"), dict)
        else None
    )
    if not re.fullmatch(r"[0-9a-f]{64}", expected_body):
        mismatches.append("body_projection_fingerprint")
    if not expected_cohort_present:
        mismatches.append("source_cohort")
    for field in ("artifact_id", "artifact_sha256", "production_lane_identity"):
        if not expected.get(field) or echoed.get(field) != expected.get(field):
            mismatches.append(field)
    for field in ("body_projection_fingerprint", "verification_input_ids", "input_fingerprints"):
        observed = echoed.get(field)
        expected_value = expected.get(field)
        if field == "verification_input_ids":
            observed = sorted(str(item) for item in _vectors.string_list(observed))
            expected_value = sorted(str(item) for item in _vectors.string_list(expected_value))
        if expected_value is not None and observed != expected_value:
            mismatches.append(field)
    return not mismatches, sorted(set(mismatches))

def _primary_metric_source(value: Any) -> tuple[dict[str, Any] | None, str | None]:
    if value is None:
        return None, None
    source = value.get("primary_metric") if isinstance(value, dict) else None
    source = source if isinstance(source, dict) else value
    if not isinstance(source, dict):
        return None, "adapter_primary_metric_contract_missing"
    return source, None


def _primary_metric_provenance(
    metric_id: str,
    provenance: dict[str, str],
    provenance_hook_provided: bool,
    source_separation_gate: dict[str, Any],
) -> tuple[str, str, bool, str]:
    declared = _vectors.normalize_provenance_label(
        (
            provenance.get(_verification.normalize_gate_key(metric_id))
            or provenance.get(_verification.normalize_gate_key("primary_metric"))
        )
        if provenance_hook_provided
        else "legacy_unclassified"
    )
    source_axis = next(
        (
            row
            for row in source_separation_gate.get("verification_axes") or []
            if isinstance(row, dict)
            and _verification.normalize_gate_key(row.get("axis_id"))
            == _verification.normalize_gate_key(metric_id)
        ),
        {},
    )
    separation_status = str(
        source_separation_gate.get("independent_source_separation_status")
        or "not_evaluated"
    ).strip().lower()
    axis_provenance = _vectors.normalize_provenance_label(
        source_axis.get("evidence_provenance")
    )
    independent = bool(
        provenance_hook_provided
        and declared == "independently_verified"
        and separation_status == "pass"
        and axis_provenance == "independently_verified"
    )
    effective = (
        "independently_verified"
        if independent
        else axis_provenance
        if declared == "independently_verified"
        and axis_provenance in {"producer_attested", "self_grounded"}
        else "not_evaluated"
        if declared == "independently_verified"
        else declared
    )
    return declared, separation_status, independent, effective


def normalize_primary_metric_gate(
    value: Any,
    *,
    rows: list[dict[str, Any]],
    cap: int | None,
    epsilon: float,
    provenance: dict[str, str],
    provenance_hook_provided: bool,
    source_separation_gate: dict[str, Any],
    expected_artifact_ref: dict[str, Any],
) -> dict[str, Any]:
    source, source_error = _primary_metric_source(value)
    if source is None and source_error is None:
        return {
            "gate": "G-CHAIN-PRIMARY-METRIC",
            "evaluation_status": "not_evaluated",
            "status": "not_evaluated",
            "constrains_disposition": False,
        }
    if source is None:
        return {
            "gate": "G-CHAIN-PRIMARY-METRIC",
            "evaluation_status": "not_evaluated",
            "status": "not_evaluated",
            "not_evaluated_reason": source_error,
            "constrains_disposition": False,
        }
    metric_id = str(source.get("goal_axis_id") or source.get("axis_id") or source.get("metric_id") or "").strip()
    if not metric_id:
        return {
            "gate": "G-CHAIN-PRIMARY-METRIC",
            "evaluation_status": "not_evaluated",
            "status": "not_evaluated",
            "not_evaluated_reason": "adapter_stable_goal_axis_missing",
            "constrains_disposition": False,
        }
    stable_scope_key = f"primary_goal_axis:{_families.normalize_root_family_key(metric_id)}"
    binding_exact, binding_mismatches = primary_metric_artifact_binding(
        source,
        expected_artifact_ref,
    )
    if not binding_exact:
        return {
            "gate": "G-CHAIN-PRIMARY-METRIC",
            "metric_id": metric_id,
            "primary_metric_scope_key": stable_scope_key,
            "artifact_binding_status": "not_evaluated",
            "artifact_binding_mismatches": binding_mismatches,
            "evaluation_status": "not_evaluated",
            "status": "not_evaluated",
            "not_evaluated_reason": "exact_decision_artifact_binding_missing",
            "constrains_disposition": False,
        }
    raw_current_value = (
        source.get("value")
        if "value" in source
        else source.get("primary_metric_value")
        if "primary_metric_value" in source
        else source.get("current")
    )
    try:
        current_value = float(raw_current_value)
    except (TypeError, ValueError):
        current_value = float("nan")
    if isinstance(raw_current_value, bool) or not math.isfinite(current_value):
        return {
            "gate": "G-CHAIN-PRIMARY-METRIC",
            "metric_id": metric_id,
            "primary_metric_scope_key": stable_scope_key,
            "artifact_binding_status": "exact",
            "evaluation_status": "not_evaluated",
            "status": "not_evaluated",
            "not_evaluated_reason": "primary_metric_value_missing_or_non_numeric",
            "constrains_disposition": False,
        }
    registry_previous = primary_metric_registry_high_water(rows, stable_scope_key)
    comparable = registry_previous is not None
    previous = registry_previous
    raw_moved = comparable and current_value > float(previous) + epsilon
    (
        declared_metric_provenance,
        source_separation_status,
        independent,
        metric_provenance,
    ) = _primary_metric_provenance(
        metric_id,
        provenance,
        provenance_hook_provided,
        source_separation_gate,
    )
    moved = raw_moved and independent
    attested_only = raw_moved and not independent
    zero_streak = primary_metric_zero_movement_streak(rows, stable_scope_key, moved, comparable)
    adapter_stalled = _values.bool_value(
        source.get("primary_metric_stalled")
        or (value.get("primary_metric_stalled") if isinstance(value, dict) else False)
    )
    budget_contract = _values.budget_evaluation(
        "primary_metric_stall_attempts",
        cap,
        source="caller_or_repository_config",
    )
    cap_value = _values.budget_value(budget_contract)
    stalled = independent and comparable and (
        adapter_stalled or (not moved and cap_value is not None and zero_streak >= cap_value)
    )
    high_water = max(float(previous), current_value) if comparable else current_value
    evaluation_status = "pass" if moved else ("fail" if comparable and independent else "not_evaluated")
    return {
        "gate": "G-CHAIN-PRIMARY-METRIC",
        "metric_id": metric_id,
        "primary_metric_value": current_value,
        "previous_primary_metric_value": previous,
        "primary_metric_high_water": high_water,
        "primary_metric_high_water_moved": moved,
        "raw_primary_metric_high_water_moved": raw_moved,
        "evidence_provenance": metric_provenance,
        "declared_evidence_provenance": declared_metric_provenance,
        "independent_source_separation_status": source_separation_status,
        "verification_source_separation_gate": source_separation_gate,
        "attested_only_movement": attested_only,
        "primary_metric_scope_key": stable_scope_key,
        "artifact_binding_status": "exact",
        "primary_metric_zero_movement_streak": zero_streak,
        "primary_metric_stall_cap": cap_value,
        "budget_evaluation": budget_contract,
        "budget_evaluation_status": budget_contract["budget_evaluation_status"],
        "primary_metric_stalled": stalled,
        "evaluation_status": evaluation_status,
        "status": "block" if stalled else ("warn" if attested_only else ("pass" if moved else "ok")),
        "constrains_disposition": stalled,
        "allowed_dispositions": ["goal_productive", "terminal_blocked", "user_escalation"],
    }
