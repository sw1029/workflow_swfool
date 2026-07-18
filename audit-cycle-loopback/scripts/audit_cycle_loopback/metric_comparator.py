from __future__ import annotations

import hashlib
import json
import math
from typing import Any


VALUE_KINDS = {"scalar", "set", "vector", "ordered", "predicate"}
COMPARISON_BY_KIND = {
    "scalar": {"higher_is_better", "lower_is_better", "equal_required"},
    "set": {"set_relation"},
    "vector": {"pareto"},
    "ordered": {"higher_is_better", "lower_is_better", "equal_required"},
    "predicate": {"predicate_only"},
}


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _json_scalar(value: Any) -> bool:
    return (
        value is not None
        and isinstance(value, (str, int, float, bool))
        and not (isinstance(value, float) and not math.isfinite(value))
    )


def _normalized_scalar(value: Any, *, numeric: bool) -> tuple[Any | None, str | None]:
    if numeric:
        if isinstance(value, bool):
            return None, "primary_metric_value_missing_or_non_numeric"
        try:
            normalized = float(value)
        except (TypeError, ValueError):
            return None, "primary_metric_value_missing_or_non_numeric"
        if not math.isfinite(normalized):
            return None, "primary_metric_value_missing_or_non_numeric"
        return normalized, None
    if not _json_scalar(value):
        return None, "primary_metric_value_missing_or_invalid"
    return value, None


def _normalized_set(value: Any) -> tuple[list[Any] | None, str | None]:
    if not isinstance(value, (list, tuple, set, frozenset)):
        return None, "primary_metric_set_value_missing_or_invalid"
    by_token: dict[str, Any] = {}
    for item in value:
        if not _json_scalar(item):
            return None, "primary_metric_set_member_invalid"
        token = _canonical_json(item)
        if token in by_token:
            return None, "primary_metric_set_member_duplicate"
        by_token[token] = item
    return [by_token[token] for token in sorted(by_token)], None


def _normalized_vector(value: Any) -> tuple[dict[str, float] | None, str | None]:
    if not isinstance(value, dict) or not value:
        return None, "primary_metric_vector_value_missing_or_invalid"
    result: dict[str, float] = {}
    for raw_key, raw_value in value.items():
        key = str(raw_key).strip()
        if not key or key in result or isinstance(raw_value, bool):
            return None, "primary_metric_vector_axis_invalid"
        try:
            number = float(raw_value)
        except (TypeError, ValueError):
            return None, "primary_metric_vector_axis_non_numeric"
        if not math.isfinite(number):
            return None, "primary_metric_vector_axis_non_numeric"
        result[key] = number
    return {key: result[key] for key in sorted(result)}, None


def _comparison_config(
    source: dict[str, Any],
    value_kind: str,
    comparison: str,
) -> tuple[dict[str, Any] | None, str | None]:
    if comparison == "equal_required":
        target = source.get("target_value")
        if not _json_scalar(target):
            return None, "metric_target_value_missing_or_invalid"
        return {"target_value": target}, None
    if value_kind == "set":
        direction = str(source.get("set_relation_direction") or "").strip().lower()
        if direction not in {"superset_is_better", "subset_is_better"}:
            return None, "set_relation_direction_missing_or_invalid"
        return {"set_relation_direction": direction}, None
    if value_kind == "vector":
        raw = source.get("vector_directions")
        if not isinstance(raw, dict) or not raw:
            return None, "vector_directions_missing_or_invalid"
        directions = {
            str(key).strip(): str(value).strip().lower() for key, value in raw.items()
        }
        if (
            not all(directions)
            or len(directions) != len(raw)
            or any(
                value not in {"higher_is_better", "lower_is_better"}
                for value in directions.values()
            )
        ):
            return None, "vector_directions_missing_or_invalid"
        return {
            "vector_directions": {key: directions[key] for key in sorted(directions)}
        }, None
    if value_kind == "ordered":
        raw_order = source.get("ordered_values")
        if not isinstance(raw_order, list) or not raw_order:
            return None, "ordered_values_missing_or_invalid"
        tokens: set[str] = set()
        normalized: list[Any] = []
        for item in raw_order:
            if not _json_scalar(item):
                return None, "ordered_value_member_invalid"
            token = _canonical_json(item)
            if token in tokens:
                return None, "ordered_value_member_duplicate"
            tokens.add(token)
            normalized.append(item)
        return {"ordered_values": normalized}, None
    return {}, None


def normalize_contract(
    source: dict[str, Any],
    metric_id: str,
) -> tuple[dict[str, Any] | None, str | None]:
    basis_id = str(source.get("metric_basis_id") or "").strip()
    dimension_id = str(source.get("metric_dimension_id") or "").strip()
    value_kind = str(source.get("value_kind") or "scalar").strip().lower()
    comparison = str(source.get("comparison_semantics") or "").strip().lower()
    subject_id = str(source.get("metric_subject_id") or "").strip()
    provenance_id = str(source.get("metric_provenance_id") or "").strip()
    if not basis_id:
        return None, "metric_basis_id_missing"
    if not dimension_id:
        return None, "metric_dimension_id_missing"
    if value_kind not in VALUE_KINDS:
        return None, "value_kind_missing_or_invalid"
    if comparison not in COMPARISON_BY_KIND[value_kind]:
        return None, "comparison_semantics_missing_or_invalid"
    if value_kind != "scalar" and not subject_id:
        return None, "metric_subject_id_missing"
    if value_kind != "scalar" and not provenance_id:
        return None, "metric_provenance_id_missing"
    subject_id = subject_id or metric_id
    provenance_id = provenance_id or "independently_verified"
    config, config_error = _comparison_config(source, value_kind, comparison)
    if config_error is not None:
        return None, config_error
    return {
        "metric_id": metric_id,
        "metric_basis_id": basis_id,
        "metric_dimension_id": dimension_id,
        "metric_subject_id": subject_id,
        "metric_provenance_id": provenance_id,
        "value_kind": value_kind,
        "comparison_semantics": comparison,
        "comparison_config": config or {},
    }, None


def normalize_value(
    raw_value: Any,
    contract: dict[str, Any],
) -> tuple[Any | None, str | None]:
    value_kind = str(contract["value_kind"])
    comparison = str(contract["comparison_semantics"])
    if value_kind == "scalar":
        return _normalized_scalar(
            raw_value,
            numeric=comparison in {"higher_is_better", "lower_is_better"},
        )
    if value_kind == "set":
        return _normalized_set(raw_value)
    if value_kind == "vector":
        value, error = _normalized_vector(raw_value)
        directions = contract["comparison_config"]["vector_directions"]
        if error is None and set(value or {}) != set(directions):
            return None, "vector_axis_contract_mismatch"
        return value, error
    if value_kind == "ordered":
        value, error = _normalized_scalar(raw_value, numeric=False)
        if (
            error is None
            and comparison != "equal_required"
            and _canonical_json(value)
            not in {
                _canonical_json(item)
                for item in contract["comparison_config"]["ordered_values"]
            }
        ):
            return None, "ordered_value_outside_contract"
        return value, error
    if not isinstance(raw_value, bool):
        return None, "predicate_value_missing_or_invalid"
    return raw_value, None


def primary_metric_scope_key(contract: dict[str, Any], normalize_metric_id: Any) -> str:
    metric_id = str(contract["metric_id"])
    legacy_scalar = (
        contract["value_kind"] == "scalar"
        and contract["comparison_semantics"] in {"higher_is_better", "lower_is_better"}
        and contract["metric_subject_id"] == metric_id
        and contract["metric_provenance_id"] == "independently_verified"
        and not contract["comparison_config"]
    )
    if legacy_scalar:
        fields = (
            normalize_metric_id(metric_id),
            contract["metric_basis_id"],
            contract["metric_dimension_id"],
            contract["comparison_semantics"],
        )
        material = "\0".join(fields).encode("utf-8")
    else:
        material = _canonical_json(contract).encode("utf-8")
    return "primary_goal_axis:" + hashlib.sha256(material).hexdigest()


def metric_value_sha256(contract: dict[str, Any], value: Any) -> str:
    return _sha256({"contract": contract, "value": value})


def gate_matches_contract(gate: dict[str, Any], contract: dict[str, Any]) -> bool:
    return all(
        gate.get(key) == contract.get(key)
        for key in (
            "metric_id",
            "metric_basis_id",
            "metric_dimension_id",
            "metric_subject_id",
            "metric_provenance_id",
            "value_kind",
            "comparison_semantics",
            "comparison_config",
        )
    )


def _ordered_rank(value: Any, ordered_values: list[Any]) -> int:
    token = _canonical_json(value)
    return next(
        index
        for index, item in enumerate(ordered_values)
        if _canonical_json(item) == token
    )


def _directional_comparison(
    current: float, previous: float, direction: str, epsilon: float
) -> str:
    delta = (
        current - previous if direction == "higher_is_better" else previous - current
    )
    if delta > epsilon:
        return "improved"
    if delta < -epsilon:
        return "adverse"
    return "equal"


def compare_values(
    current: Any,
    previous: Any,
    contract: dict[str, Any],
    epsilon: float,
) -> dict[str, Any]:
    kind = contract["value_kind"]
    semantics = contract["comparison_semantics"]
    relation = "equal"
    if semantics == "equal_required":
        target = contract["comparison_config"]["target_value"]
        current_equal = _canonical_json(current) == _canonical_json(target)
        previous_equal = _canonical_json(previous) == _canonical_json(target)
        relation = (
            "improved"
            if current_equal and not previous_equal
            else "adverse"
            if previous_equal and not current_equal
            else "equal"
        )
    elif kind == "scalar":
        relation = _directional_comparison(current, previous, semantics, epsilon)
    elif kind == "ordered":
        ordered = contract["comparison_config"]["ordered_values"]
        relation = _directional_comparison(
            float(_ordered_rank(current, ordered)),
            float(_ordered_rank(previous, ordered)),
            semantics,
            0.0,
        )
    elif kind == "predicate":
        relation = (
            "improved"
            if current and not previous
            else "adverse"
            if previous and not current
            else "equal"
        )
    elif kind == "set":
        current_tokens = {_canonical_json(item) for item in current}
        previous_tokens = {_canonical_json(item) for item in previous}
        direction = contract["comparison_config"]["set_relation_direction"]
        improves = (
            current_tokens > previous_tokens
            if direction == "superset_is_better"
            else current_tokens < previous_tokens
        )
        adverse = (
            current_tokens < previous_tokens
            if direction == "superset_is_better"
            else current_tokens > previous_tokens
        )
        relation = (
            "improved"
            if improves
            else "adverse"
            if adverse
            else "equal"
            if current_tokens == previous_tokens
            else "incomparable"
        )
    else:
        directions = contract["comparison_config"]["vector_directions"]
        axis_relations = [
            _directional_comparison(
                current[key], previous[key], directions[key], epsilon
            )
            for key in directions
        ]
        relation = (
            "improved"
            if "improved" in axis_relations and "adverse" not in axis_relations
            else "adverse"
            if "adverse" in axis_relations and "improved" not in axis_relations
            else "equal"
            if all(item == "equal" for item in axis_relations)
            else "incomparable"
        )
    return {
        "comparison_relation": relation,
        "comparable": relation != "incomparable",
        "moved": relation == "improved",
        "high_water": current if relation == "improved" else previous,
    }
