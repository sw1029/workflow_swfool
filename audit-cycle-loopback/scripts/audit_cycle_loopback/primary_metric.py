from __future__ import annotations

import re
from typing import Any

from .decision_identity_dimensions import (
    parse_decision_identity,
)

from . import families as _families
from . import metric_comparator as _metric_comparator
from . import primary_metric_evaluation as _metric_evaluation
from . import quality as _quality
from . import values as _values
from . import vectors as _vectors
from .primary_metric_registry import (
    primary_metric_registry_high_water as _primary_metric_registry_high_water,
    primary_metric_zero_movement_streak as primary_metric_zero_movement_streak,
)
from .decision_identity_binding import explicit_identity, explicit_identity_mismatches

primary_metric_registry_high_water = _primary_metric_registry_high_water


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
    result["ever_provider_dispatch"] = (
        _values.bool_value(prev_high.get("ever_provider_dispatch"))
        or provider_request_count > 0
    )
    return result


def previous_primary_metric_value(latest: dict[str, Any] | None) -> Any:
    if not isinstance(latest, dict):
        return 0.0
    gate = latest.get("primary_metric_gate")
    if isinstance(gate, dict):
        for key in ("primary_metric_high_water", "primary_metric_value", "value"):
            if key in gate:
                return gate.get(key)
    for key in ("primary_metric_high_water", "primary_metric_value"):
        if key in latest:
            return latest.get(key)
    return 0.0


def primary_metric_artifact_binding(
    source: dict[str, Any],
    expected: dict[str, Any],
) -> tuple[bool, list[str]]:
    echoed = source.get("decision_artifact_ref")
    if not isinstance(echoed, dict):
        echoed = source
    exact_identity = explicit_identity(expected)
    projection = parse_decision_identity(exact_identity or expected)
    if projection.explicit:
        mismatches = explicit_identity_mismatches(source, expected)
        if not _values.bool_value(expected.get("scope_verified")):
            mismatches.append("scope_verified")
        return not mismatches, sorted(set(mismatches))
    mismatches: list[str] = []
    expected_body = (
        str(expected.get("body_projection_fingerprint") or "").strip().lower()
    )
    expected_cohort_present = bool(
        _vectors.string_list(expected.get("verification_input_ids"))
    ) or bool(
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
    for field in (
        "body_projection_fingerprint",
        "verification_input_ids",
        "input_fingerprints",
    ):
        observed = echoed.get(field)
        expected_value = expected.get(field)
        if field == "verification_input_ids":
            observed = sorted(str(item) for item in _vectors.string_list(observed))
            expected_value = sorted(
                str(item) for item in _vectors.string_list(expected_value)
            )
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


def _metric_contract_gate(
    source: dict[str, Any],
    metric_id: str,
    trace_scope_key: str,
) -> tuple[dict[str, Any] | None, Any, dict[str, Any] | None]:
    contract, reason = _metric_comparator.normalize_contract(source, metric_id)
    current_value: Any = None
    if contract is not None:
        raw_value = source.get(
            "value",
            source.get("primary_metric_value", source.get("current")),
        )
        current_value, reason = _metric_comparator.normalize_value(raw_value, contract)
    if contract is not None and reason is None:
        contract["primary_metric_scope_key"] = (
            _metric_comparator.primary_metric_scope_key(
                contract,
                _families.normalize_root_family_key,
            )
        )
        return contract, current_value, None
    return (
        None,
        None,
        {
            "gate": "G-CHAIN-PRIMARY-METRIC",
            "metric_id": metric_id,
            "metric_basis_id": str(source.get("metric_basis_id") or "").strip() or None,
            "metric_dimension_id": str(source.get("metric_dimension_id") or "").strip()
            or None,
            "metric_subject_id": str(source.get("metric_subject_id") or "").strip()
            or None,
            "metric_provenance_id": str(
                source.get("metric_provenance_id") or ""
            ).strip()
            or None,
            "value_kind": str(source.get("value_kind") or "scalar").strip().lower(),
            "comparison_semantics": str(source.get("comparison_semantics") or "")
            .strip()
            .lower()
            or None,
            "primary_metric_scope_key": trace_scope_key,
            "artifact_binding_status": "exact",
            "metric_comparability_status": "not_evaluated",
            "evaluation_status": "not_evaluated",
            "status": "not_evaluated",
            "not_evaluated_reason": reason,
            "constrains_disposition": False,
        },
    )


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
    if source is None:
        result = {
            "gate": "G-CHAIN-PRIMARY-METRIC",
            "evaluation_status": "not_evaluated",
            "status": "not_evaluated",
            "constrains_disposition": False,
        }
        if source_error is not None:
            result["not_evaluated_reason"] = source_error
        return result
    metric_id = str(
        source.get("goal_axis_id")
        or source.get("axis_id")
        or source.get("metric_id")
        or ""
    ).strip()
    if not metric_id:
        return {
            "gate": "G-CHAIN-PRIMARY-METRIC",
            "evaluation_status": "not_evaluated",
            "status": "not_evaluated",
            "not_evaluated_reason": "adapter_stable_goal_axis_missing",
            "constrains_disposition": False,
        }
    trace_scope_key = (
        f"primary_goal_axis:{_families.normalize_root_family_key(metric_id)}"
    )
    binding_exact, binding_mismatches = primary_metric_artifact_binding(
        source, expected_artifact_ref
    )
    if not binding_exact:
        return {
            "gate": "G-CHAIN-PRIMARY-METRIC",
            "metric_id": metric_id,
            "primary_metric_scope_key": trace_scope_key,
            "artifact_binding_status": "not_evaluated",
            "artifact_binding_mismatches": binding_mismatches,
            "evaluation_status": "not_evaluated",
            "status": "not_evaluated",
            "not_evaluated_reason": "exact_decision_artifact_binding_missing",
            "constrains_disposition": False,
        }
    contract, current_value, contract_gate = _metric_contract_gate(
        source, metric_id, trace_scope_key
    )
    if contract_gate is not None:
        return contract_gate
    assert contract is not None
    return _metric_evaluation.normalized_metric_result(
        source=source,
        wrapper_value=value,
        contract=contract,
        current_value=current_value,
        rows=rows,
        cap=cap,
        epsilon=epsilon,
        provenance=provenance,
        provenance_hook_provided=provenance_hook_provided,
        source_separation_gate=source_separation_gate,
        expected_artifact_ref=expected_artifact_ref,
    )
