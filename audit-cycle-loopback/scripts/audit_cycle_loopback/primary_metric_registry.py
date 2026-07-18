from __future__ import annotations

import math
from typing import Any

from . import metric_comparator as _metric_comparator
from . import metric_observation as _metric_observation
from . import values as _values


def primary_metric_zero_movement_streak(
    rows: list[dict[str, Any]],
    scope_key: str,
    moved: bool,
    comparable: bool,
) -> int:
    if moved:
        return 0
    prior_streak: int | None = None
    for row in reversed(rows):
        gate = row.get("primary_metric_gate")
        if not isinstance(gate, dict) or not eligible_metric_gate(gate):
            continue
        row_scope = str(
            gate.get("primary_metric_scope_key")
            or row.get("cumulative_goal_distance_scope_key")
            or ""
        )
        if row_scope != scope_key:
            continue
        raw_streak = gate.get("primary_metric_zero_movement_streak")
        if (
            isinstance(raw_streak, int)
            and not isinstance(raw_streak, bool)
            and raw_streak >= 0
        ):
            prior_streak = raw_streak
        break
    if not comparable:
        return prior_streak or 0
    if prior_streak is not None:
        return prior_streak + 1
    streak = 1
    for row in reversed(rows):
        gate = row.get("primary_metric_gate")
        if not isinstance(gate, dict) or not eligible_metric_gate(gate):
            continue
        row_scope = str(
            gate.get("primary_metric_scope_key")
            or row.get("cumulative_goal_distance_scope_key")
            or ""
        )
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
    comparison_semantics: str = "higher_is_better",
) -> float | None:
    values: list[float] = []
    for row in rows:
        gate = row.get("primary_metric_gate")
        if not isinstance(gate, dict) or not eligible_metric_gate(gate):
            continue
        if str(gate.get("primary_metric_scope_key") or "") != scope_key:
            continue
        high_water = gate.get("primary_metric_high_water")
        contract = _contract_from_gate(gate)
        value, error = _metric_comparator.normalize_value(high_water, contract)
        if (
            error is None
            and gate.get("primary_metric_high_water_sha256")
            == _metric_comparator.metric_value_sha256(contract, value)
            and isinstance(value, (int, float))
            and not isinstance(value, bool)
        ):
            normalized = float(value)
            if math.isfinite(normalized):
                values.append(normalized)
    if not values:
        return None
    return min(values) if comparison_semantics == "lower_is_better" else max(values)


def eligible_metric_gate(gate: dict[str, Any]) -> bool:
    migration_eligible = bool(
        not gate.get("basis_migration_observed")
        or gate.get("basis_migration_status") == "verified_new_baseline"
    )
    return bool(
        gate.get("artifact_binding_status") == "exact"
        and gate.get("evidence_provenance") == "independently_verified"
        and gate.get("independent_source_separation_status") == "pass"
        and _values.bool_value(gate.get("decision_contribution_allowed"))
        and migration_eligible
        and _metric_observation.metric_observation_valid(gate)
    )


def _contract_from_gate(gate: dict[str, Any]) -> dict[str, Any]:
    return {
        key: gate.get(key)
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
    }


def latest_metric_gate(
    rows: list[dict[str, Any]],
    scope_key: str,
) -> dict[str, Any] | None:
    for row in reversed(rows):
        gate = row.get("primary_metric_gate")
        if (
            isinstance(gate, dict)
            and str(gate.get("primary_metric_scope_key") or "") == scope_key
            and eligible_metric_gate(gate)
        ):
            return gate
    return None


def registry_metric_observation(
    rows: list[dict[str, Any]],
    contract: dict[str, Any],
) -> dict[str, Any] | None:
    scope_key = str(contract["primary_metric_scope_key"])
    digest_contract = {
        key: value
        for key, value in contract.items()
        if key != "primary_metric_scope_key"
    }
    for row in reversed(rows):
        gate = row.get("primary_metric_gate")
        if not isinstance(gate, dict) or not eligible_metric_gate(gate):
            continue
        if str(gate.get("primary_metric_scope_key") or "") != scope_key:
            continue
        if not _metric_comparator.gate_matches_contract(gate, digest_contract):
            continue
        value, error = _metric_comparator.normalize_value(
            gate.get("primary_metric_high_water"),
            digest_contract,
        )
        if error is not None:
            continue
        expected_digest = _metric_comparator.metric_value_sha256(digest_contract, value)
        if gate.get("primary_metric_high_water_sha256") != expected_digest:
            continue
        return {"value": value, "gate": gate}
    return None


def basis_migration_gate(
    rows: list[dict[str, Any]],
    contract: dict[str, Any],
) -> dict[str, Any] | None:
    identity_keys = (
        "metric_id",
        "metric_dimension_id",
        "metric_subject_id",
        "metric_provenance_id",
        "value_kind",
        "comparison_semantics",
        "comparison_config",
    )
    for row in reversed(rows):
        gate = row.get("primary_metric_gate")
        if not isinstance(gate, dict) or not eligible_metric_gate(gate):
            continue
        if all(gate.get(key) == contract.get(key) for key in identity_keys) and (
            gate.get("metric_basis_id") != contract.get("metric_basis_id")
        ):
            return gate
    return None
