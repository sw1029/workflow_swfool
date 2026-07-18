"""Applicability-aware decision-identity projection and exact echo checks."""

from __future__ import annotations

from typing import Any

from .decision_identity_dimensions import (
    DIMENSION_NAMES,
    SUBJECT_FIELDS,
    expected_dimension_echo,
    expected_subject_echo,
    parse_decision_identity,
)


DIMENSION_ALIASES = {
    "body_fingerprint": ("body_projection_fingerprint",),
    "production_lane": ("production_lane_identity",),
    "cohort": ("cohort_identity", "verification_input_ids", "input_fingerprints"),
    "producer_run": ("producer_run_id", "measurement_run_id"),
}


def explicit_identity(value: Any) -> dict[str, Any] | None:
    """Return the raw explicit identity nested in a packet-like value."""
    if not isinstance(value, dict):
        return None
    for field in (
        "decision_identity",
        "decision_artifact_ref",
        "selected_artifact_ref",
        "artifact_ref",
    ):
        nested = value.get(field)
        extracted = explicit_identity(nested)
        if extracted is not None:
            return extracted
    return value if parse_decision_identity(value).explicit else None


def decision_identity_echo(value: Any) -> dict[str, Any] | None:
    """Normalize either a raw explicit identity or its closed post-use echo."""
    if not isinstance(value, dict):
        return None
    declared_echo = value.get("decision_identity_echo")
    if isinstance(declared_echo, dict):
        return declared_echo
    identity = explicit_identity(value)
    if identity is None:
        return None
    projection = parse_decision_identity(identity)
    if projection.issues:
        return None
    return {
        **expected_subject_echo(identity),
        "dimension_values": expected_dimension_echo(identity),
    }


def _observed_identity_containers(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, dict):
        return []
    containers = [value]
    for field in (
        "decision_artifact_ref",
        "decision_identity",
        "selected_artifact_ref",
        "artifact_ref",
    ):
        nested = value.get(field)
        if isinstance(nested, dict):
            containers.append(nested)
    return containers


def explicit_identity_mismatches(
    observed: Any,
    expected: dict[str, Any],
) -> list[str]:
    """Compare an observed echo to the exact current explicit identity."""
    expected_identity = explicit_identity(expected)
    if expected_identity is None:
        return ["decision_identity_kind"]
    projection = parse_decision_identity(expected_identity)
    mismatches = [f"expected.{field}" for field in projection.issues]
    if projection.subject_values.get("freshness_status") != "current":
        mismatches.append("freshness_status")

    expected_echo = {
        **expected_subject_echo(expected_identity),
        "dimension_values": expected_dimension_echo(expected_identity),
    }
    observed_echo = decision_identity_echo(observed)
    if observed_echo is None:
        mismatches.append("decision_identity_echo")
    elif observed_echo != expected_echo:
        for field in (*SUBJECT_FIELDS, "freshness_status"):
            if observed_echo.get(field) != expected_echo.get(field):
                mismatches.append(field)
        observed_dimensions = observed_echo.get("dimension_values")
        if observed_dimensions != expected_echo["dimension_values"]:
            mismatches.append("dimension_values")

    observed_identity = explicit_identity(observed)
    if observed_identity is not None:
        observed_projection = parse_decision_identity(observed_identity)
        mismatches.extend(f"observed.{field}" for field in observed_projection.issues)
    for dimension in DIMENSION_NAMES:
        status = projection.dimension_statuses.get(dimension)
        expected_value = projection.dimension_values.get(dimension)
        for container in _observed_identity_containers(observed):
            for alias in DIMENSION_ALIASES[dimension]:
                observed_value = container.get(alias)
                if observed_value is None:
                    continue
                if status == "not_applicable":
                    mismatches.append(f"{dimension}.nonapplicable_alias")
                elif status == "applicable" and observed_value != expected_value:
                    mismatches.append(f"{dimension}.alias_mismatch")
    return sorted(set(mismatches))


def explicit_legacy_aliases(identity: dict[str, Any]) -> dict[str, Any]:
    """Project interoperability aliases without inventing values for N/A dimensions."""
    projection = parse_decision_identity(identity)
    cohort = (
        projection.dimension_values.get("cohort")
        if projection.dimension_statuses.get("cohort") == "applicable"
        else None
    )
    return {
        "artifact_id": projection.subject_values.get("decision_subject_id"),
        "artifact_class": projection.subject_values.get("subject_class_id"),
        "artifact_sha256": projection.subject_values.get("subject_digest"),
        "body_projection_fingerprint": (
            projection.dimension_values.get("body_fingerprint")
            if projection.dimension_statuses.get("body_fingerprint") == "applicable"
            else None
        ),
        "production_lane_identity": (
            projection.dimension_values.get("production_lane")
            if projection.dimension_statuses.get("production_lane") == "applicable"
            else None
        ),
        "cohort_identity": cohort,
        "verification_input_ids": cohort if isinstance(cohort, list) else None,
        "input_fingerprints": cohort if isinstance(cohort, dict) else None,
        "producer_run_id": (
            projection.dimension_values.get("producer_run")
            if projection.dimension_statuses.get("producer_run") == "applicable"
            else None
        ),
    }


__all__ = [
    "DIMENSION_ALIASES",
    "decision_identity_echo",
    "explicit_identity",
    "explicit_identity_mismatches",
    "explicit_legacy_aliases",
]
