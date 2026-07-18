from __future__ import annotations

import math
import re
from typing import Any

from .payload_schema_common import (
    exact_object,
    require_digest,
    require_non_negative_int,
)


_OPAQUE_ENUM_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_METRIC_VALUE_KINDS = {"scalar", "set", "vector", "ordered", "predicate"}
_METRIC_VALUE_REFERENCE_FIELDS = frozenset(
    {"contract_version", "value_ref", "full_content_sha256", "summary"}
)
_METRIC_VALUE_SUMMARY_FIELDS = frozenset({"summary_kind", "value_kind", "member_count"})


def validate_primary_metric_gate_privacy(value: object) -> None:
    if not isinstance(value, dict):
        raise ValueError("family progress primary_metric_gate must be an object")
    value_kind = str(value.get("value_kind") or "").strip().lower()
    for field in (
        "primary_metric_value",
        "previous_primary_metric_value",
        "primary_metric_high_water",
    ):
        if field in value:
            _validate_metric_value_projection(
                value[field],
                value_kind=value_kind,
                label=f"primary_metric_gate.{field}",
            )
    _validate_metric_comparison_config(
        value.get("comparison_config"),
        value_kind=value_kind,
        label="primary_metric_gate.comparison_config",
    )
    observation = value.get("metric_observation")
    if observation is None:
        return
    if not isinstance(observation, dict):
        raise ValueError("primary_metric_gate.metric_observation must be an object")
    contract = observation.get("metric_contract")
    observation_kind = value_kind
    if isinstance(contract, dict):
        observation_kind = (
            str(contract.get("value_kind") or observation_kind).strip().lower()
        )
        _validate_metric_comparison_config(
            contract.get("comparison_config"),
            value_kind=observation_kind,
            label="primary_metric_gate.metric_observation.metric_contract.comparison_config",
        )
    for field in ("observed_value", "high_water_value"):
        if field in observation:
            _validate_metric_value_projection(
                observation[field],
                value_kind=observation_kind,
                label=f"primary_metric_gate.metric_observation.{field}",
            )


def _validate_metric_comparison_config(
    value: object,
    *,
    value_kind: str,
    label: str,
) -> None:
    if value is None:
        return
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    for field in ("ordered_values", "target_value", "vector_directions"):
        if field in value:
            _validate_metric_value_projection(
                value[field],
                value_kind=value_kind,
                label=f"{label}.{field}",
            )


def _validate_metric_value_projection(
    value: object,
    *,
    value_kind: str,
    label: str,
) -> None:
    if value is None:
        return
    if isinstance(value, dict) and set(value) == _METRIC_VALUE_REFERENCE_FIELDS:
        _validate_metric_value_reference(value, label=label)
        return
    if value_kind in {"set", "vector"}:
        raise ValueError(f"{label} raw non-scalar value is not durable-safe")
    if isinstance(value, bool):
        return
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError(f"{label} scalar value must be finite")
        return
    if isinstance(value, str) and _OPAQUE_ENUM_PATTERN.fullmatch(value):
        return
    raise ValueError(
        f"{label} raw non-scalar or unbounded string value is not durable-safe"
    )


def _validate_metric_value_reference(value: dict[str, Any], *, label: str) -> None:
    if value.get("contract_version") != 1:
        raise ValueError(f"{label} value reference contract_version must be 1")
    digest = require_digest(
        value.get("full_content_sha256"),
        label=f"{label} full_content_sha256",
    )
    if value.get("value_ref") != f"metric-value-{digest}":
        raise ValueError(f"{label} value_ref/digest relation mismatch")
    summary = exact_object(
        value.get("summary"),
        allowed=_METRIC_VALUE_SUMMARY_FIELDS,
        required=_METRIC_VALUE_SUMMARY_FIELDS,
        label=f"{label} summary",
    )
    if summary["summary_kind"] not in {"scalar", "enum", "collection", "vector"}:
        raise ValueError(f"{label} summary_kind is invalid")
    if summary["value_kind"] not in _METRIC_VALUE_KINDS:
        raise ValueError(f"{label} value_kind is invalid")
    require_non_negative_int(
        summary["member_count"],
        label=f"{label} member_count",
    )


__all__ = ["validate_primary_metric_gate_privacy"]
