"""Evaluate normalized primary-metric observations and migration state."""

from __future__ import annotations

from typing import Any

from . import basis_migration
from . import metric_comparator
from . import metric_observation
from . import primary_metric_packet
from . import values
from . import vectors
from . import verification
from .primary_metric_registry import (
    basis_migration_gate,
    primary_metric_zero_movement_streak,
    registry_metric_observation,
)


def _provenance(
    metric_id: str,
    provenance: dict[str, str],
    provenance_hook_provided: bool,
    source_separation_gate: dict[str, Any],
) -> tuple[str, str, bool, str]:
    declared = vectors.normalize_provenance_label(
        (
            provenance.get(verification.normalize_gate_key(metric_id))
            or provenance.get(verification.normalize_gate_key("primary_metric"))
        )
        if provenance_hook_provided
        else "legacy_unclassified"
    )
    source_axis = next(
        (
            row
            for row in source_separation_gate.get("verification_axes") or []
            if isinstance(row, dict)
            and verification.normalize_gate_key(row.get("axis_id"))
            == verification.normalize_gate_key(metric_id)
        ),
        {},
    )
    separation_status = (
        str(
            source_separation_gate.get("independent_source_separation_status")
            or "not_evaluated"
        )
        .strip()
        .lower()
    )
    axis_provenance = vectors.normalize_provenance_label(
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


def _nonnegative_int(value: Any) -> int:
    return (
        value
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0
        else 0
    )


def _not_evaluated_reason(
    baseline: dict[str, Any] | None,
    comparison: dict[str, Any] | None,
    independent: bool,
    migration_observed: bool,
    migration_verified: bool,
) -> str | None:
    if migration_observed:
        return (
            "metric_basis_migration_started_new_baseline"
            if migration_verified
            else "metric_basis_migration_receipt_missing_or_invalid"
        )
    if baseline is None:
        return "no_comparable_baseline"
    if comparison is not None and not comparison["comparable"]:
        return "metric_values_incomparable"
    if not independent:
        return "independent_metric_provenance_missing"
    return None


def _digest_contract(contract: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in contract.items()
        if key != "primary_metric_scope_key"
    }


def _outcome_labels(
    *,
    baseline: dict[str, Any] | None,
    comparison: dict[str, Any] | None,
    independent: bool,
    moved: bool,
    prior_basis_gate: dict[str, Any] | None,
    migration_verified: bool,
) -> tuple[str, str, str | None]:
    comparability = (
        "basis_migration_new_baseline"
        if migration_verified
        else "basis_migration_no_comparable_baseline"
        if prior_basis_gate is not None
        else "no_comparable_baseline"
        if baseline is None
        else "comparable"
        if comparison and comparison["comparable"]
        else "incomparable"
    )
    comparison_comparable = bool(
        comparison and comparison["comparable"] and independent
    )
    evaluation_status = (
        "pass" if moved else "fail" if comparison_comparable else "not_evaluated"
    )
    reason = (
        _not_evaluated_reason(
            baseline,
            comparison,
            independent,
            prior_basis_gate is not None,
            migration_verified,
        )
        if evaluation_status == "not_evaluated"
        else None
    )
    return comparability, evaluation_status, reason


def _migration_packet_fields(
    *,
    prior_basis_gate: dict[str, Any] | None,
    migration: basis_migration.BasisMigrationAssessment | None,
    migration_verified: bool,
    scope_key: str,
) -> dict[str, Any]:
    return {
        "basis_migration_observed": prior_basis_gate is not None,
        "basis_migration_status": (
            "verified_new_baseline"
            if migration_verified
            else "unverified"
            if prior_basis_gate is not None
            else "not_applicable"
        ),
        "basis_migration_receipt": (
            migration.receipt if migration_verified and migration else None
        ),
        "basis_migration_issues": (
            list(migration.issues) if migration and not migration.valid else []
        ),
        "basis_migration_prior_observation_sha256": (
            prior_basis_gate.get("metric_observation_sha256")
            if prior_basis_gate is not None
            else None
        ),
        "basis_migration_prior_lineage_id": (
            prior_basis_gate.get("primary_metric_scope_key")
            if prior_basis_gate is not None
            else None
        ),
        "basis_migration_new_lineage_id": (
            scope_key if prior_basis_gate is not None else None
        ),
    }


def normalized_metric_result(
    *,
    source: dict[str, Any],
    wrapper_value: Any,
    contract: dict[str, Any],
    current_value: Any,
    rows: list[dict[str, Any]],
    cap: int | None,
    epsilon: float,
    provenance: dict[str, str],
    provenance_hook_provided: bool,
    source_separation_gate: dict[str, Any],
    expected_artifact_ref: dict[str, Any],
) -> dict[str, Any]:
    metric_id = str(contract["metric_id"])
    scope_key = str(contract["primary_metric_scope_key"])
    digest_contract = _digest_contract(contract)
    baseline = registry_metric_observation(rows, contract)
    previous = baseline["value"] if baseline is not None else None
    comparison = (
        metric_comparator.compare_values(
            current_value, previous, digest_contract, epsilon
        )
        if baseline is not None
        else None
    )
    raw_moved = bool(comparison and comparison["moved"])
    declared, separation, independent, effective = _provenance(
        metric_id, provenance, provenance_hook_provided, source_separation_gate
    )
    moved = raw_moved and independent
    attested_only = raw_moved and not independent
    comparison_comparable = bool(
        comparison and comparison["comparable"] and independent
    )
    prior_basis_gate = (
        basis_migration_gate(rows, contract) if baseline is None else None
    )
    migration = None
    if prior_basis_gate is not None:
        migration = basis_migration.assess_basis_migration_receipt(
            source.get("basis_migration_receipt"),
            prior_gate=prior_basis_gate,
            contract=digest_contract,
            current_value=current_value,
            decision_binding=metric_observation.decision_artifact_binding_projection(
                expected_artifact_ref
            ),
            verification_gate=source_separation_gate,
            new_lineage_id=scope_key,
            independently_verified=independent,
        )
    migration_verified = bool(migration and migration.valid)
    prior_gate = (
        baseline.get("gate")
        if baseline is not None and isinstance(baseline.get("gate"), dict)
        else prior_basis_gate
    )
    zero_streak = primary_metric_zero_movement_streak(
        rows, scope_key, moved, comparison_comparable
    )
    if not comparison_comparable and isinstance(prior_gate, dict):
        zero_streak = _nonnegative_int(
            prior_gate.get("primary_metric_zero_movement_streak")
        )
    adapter_stalled = values.bool_value(
        source.get("primary_metric_stalled")
        or (
            wrapper_value.get("primary_metric_stalled")
            if isinstance(wrapper_value, dict)
            else False
        )
    )
    budget_contract = values.budget_evaluation(
        "primary_metric_stall_attempts",
        cap,
        source="caller_or_repository_config",
    )
    cap_value = values.budget_value(budget_contract)
    prior_stalled = bool(
        isinstance(prior_gate, dict)
        and values.bool_value(prior_gate.get("primary_metric_stalled"))
    )
    stalled = (
        independent
        and comparison_comparable
        and (
            adapter_stalled
            or (not moved and cap_value is not None and zero_streak >= cap_value)
        )
        if comparison_comparable
        else prior_stalled
    )
    high_water = current_value if baseline is None else comparison["high_water"]
    if baseline is not None and raw_moved and not independent:
        high_water = previous
    relation = (
        comparison["comparison_relation"] if comparison is not None else "no_baseline"
    )
    comparability, evaluation_status, reason = _outcome_labels(
        baseline=baseline,
        comparison=comparison,
        independent=independent,
        moved=moved,
        prior_basis_gate=prior_basis_gate,
        migration_verified=migration_verified,
    )
    return primary_metric_packet.build_primary_metric_packet(
        contract=digest_contract,
        current_value=current_value,
        previous=previous,
        high_water=high_water,
        expected_artifact_ref=expected_artifact_ref,
        source_separation_gate=source_separation_gate,
        budget_contract=budget_contract,
        state={
            "comparability": comparability,
            "relation": relation,
            "moved": moved,
            "raw_moved": raw_moved,
            "effective_provenance": effective,
            "declared_provenance": declared,
            "source_separation_status": separation,
            "attested_only": attested_only,
            "scope_key": scope_key,
            **_migration_packet_fields(
                prior_basis_gate=prior_basis_gate,
                migration=migration,
                migration_verified=migration_verified,
                scope_key=scope_key,
            ),
            "zero_streak": zero_streak,
            "cap_value": cap_value,
            "stalled": stalled,
            "evaluation_status": evaluation_status,
            "not_evaluated_reason": reason,
        },
    )


__all__ = ("normalized_metric_result",)
