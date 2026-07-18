"""Self-contained applicability-aware decision-identity contract."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any


DIMENSION_NAMES = (
    "body_fingerprint",
    "production_lane",
    "cohort",
    "producer_run",
)
SUBJECT_FIELDS = (
    "decision_subject_id",
    "subject_class_id",
    "revision_id",
    "subject_digest",
    "lineage_id",
)
LEGACY_FIELDS = (
    "cycle_id",
    "task_id",
    "attempt_id",
    "artifact_id",
    "artifact_sha256",
    "body_projection_fingerprint",
    "production_lane_identity",
    "input_state_fingerprint",
)
APPLICABILITY_VALUES = {"applicable", "not_applicable"}
FRESHNESS_VALUES = {"current", "stale", "conflicted", "unverified"}
EXPLICIT_FIELDS = {*SUBJECT_FIELDS, "freshness_status", *DIMENSION_NAMES}
DIMENSION_ROW_FIELDS = {"applicability", "value"}
IDENTITY_ENVELOPE_FIELDS = {
    "advisory_discovery",
    "decision_identity",
    "decision_identity_echo",
    "decision_identity_kind",
    "identity_status",
    "scope_verified",
}
OPAQUE_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:@+-]{0,255}")
SOURCE_LIKE_SUFFIXES = (
    ".csv",
    ".json",
    ".jsonl",
    ".md",
    ".parquet",
    ".py",
    ".txt",
)
CONTRACT_SPEC_SHA256 = hashlib.sha256(
    json.dumps(
        {
            "applicability": sorted(APPLICABILITY_VALUES),
            "dimensions": DIMENSION_NAMES,
            "dimension_row_fields": sorted(DIMENSION_ROW_FIELDS),
            "explicit_fields": sorted(EXPLICIT_FIELDS),
            "freshness": sorted(FRESHNESS_VALUES),
            "legacy_fields": LEGACY_FIELDS,
            "opaque_pattern": OPAQUE_ID_PATTERN.pattern,
            "source_like_suffixes": SOURCE_LIKE_SUFFIXES,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
).hexdigest()


@dataclass(frozen=True)
class DecisionIdentityProjection:
    explicit: bool
    subject_values: dict[str, Any]
    dimension_statuses: dict[str, str]
    dimension_values: dict[str, Any]
    issues: tuple[str, ...]

    @property
    def applicable_dimensions(self) -> tuple[str, ...]:
        return tuple(
            name
            for name in DIMENSION_NAMES
            if self.dimension_statuses.get(name) == "applicable"
        )


def _full_sha256(value: Any) -> bool:
    normalized = str(value or "").strip().lower().removeprefix("sha256:")
    return len(normalized) == 64 and all(
        character in "0123456789abcdef" for character in normalized
    )


def _opaque_scalar(value: Any, *, max_length: int = 256) -> bool:
    if not isinstance(value, str) or value != value.strip():
        return False
    if not 0 < len(value) <= max_length or OPAQUE_ID_PATTERN.fullmatch(value) is None:
        return False
    return not value.lower().endswith(SOURCE_LIKE_SUFFIXES)


def _cohort_value_valid(value: Any) -> bool:
    if _opaque_scalar(value):
        return True
    if isinstance(value, list):
        return bool(value) and all(_opaque_scalar(item) for item in value)
    if isinstance(value, dict):
        return bool(value) and all(
            _opaque_scalar(key) and (_opaque_scalar(child) or _full_sha256(child))
            for key, child in value.items()
        )
    return False


def _dimension_value_valid(name: str, value: Any) -> bool:
    if name == "body_fingerprint":
        return _full_sha256(value)
    if name == "cohort":
        return _cohort_value_valid(value)
    return _opaque_scalar(value)


def canonical_value(value: Any) -> str:
    try:
        return json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
    except (TypeError, ValueError):
        return f"!invalid:{type(value).__name__}"


def parse_decision_identity(identity: object) -> DecisionIdentityProjection:
    if not isinstance(identity, dict):
        return DecisionIdentityProjection(False, {}, {}, {}, ("identity",))
    nested = identity.get("decision_identity")
    if isinstance(nested, dict):
        projection = parse_decision_identity(nested)
        if set(identity) <= IDENTITY_ENVELOPE_FIELDS:
            return projection
        return DecisionIdentityProjection(
            projection.explicit,
            projection.subject_values,
            projection.dimension_statuses,
            projection.dimension_values,
            tuple(sorted({*projection.issues, "identity.envelope_closed_schema"})),
        )
    explicit = any(name in identity for name in DIMENSION_NAMES)
    if not explicit:
        return DecisionIdentityProjection(False, {}, {}, {}, ())
    issues: list[str] = []
    if set(identity) != EXPLICIT_FIELDS:
        issues.append("identity.closed_schema")
    subject_values = {field: identity.get(field) for field in SUBJECT_FIELDS}
    for field, value in subject_values.items():
        if field == "subject_digest":
            if not _full_sha256(value):
                issues.append(field)
        elif not _opaque_scalar(value):
            issues.append(field)
    freshness_status = str(identity.get("freshness_status") or "").strip().lower()
    if freshness_status not in FRESHNESS_VALUES:
        issues.append("freshness_status")
    subject_values["freshness_status"] = freshness_status

    statuses: dict[str, str] = {}
    values: dict[str, Any] = {}
    for name in DIMENSION_NAMES:
        row = identity.get(name)
        if not isinstance(row, dict) or set(row) != DIMENSION_ROW_FIELDS:
            issues.append(f"{name}.schema")
            statuses[name] = ""
            values[name] = None
            if not isinstance(row, dict):
                continue
        status = str(row.get("applicability") or "").strip().lower()
        value = row.get("value")
        statuses[name] = status
        values[name] = value
        if status not in APPLICABILITY_VALUES:
            issues.append(f"{name}.applicability")
        elif status == "applicable" and not _dimension_value_valid(name, value):
            issues.append(f"{name}.value")
        elif status == "not_applicable" and value is not None:
            issues.append(f"{name}.not_applicable_value")
    return DecisionIdentityProjection(
        True,
        subject_values,
        statuses,
        values,
        tuple(sorted(set(issues))),
    )


def expected_dimension_echo(identity: object) -> dict[str, Any]:
    projection = parse_decision_identity(identity)
    if not projection.explicit:
        return {}
    return {
        name: projection.dimension_values[name]
        for name in projection.applicable_dimensions
    }


def expected_subject_echo(identity: object) -> dict[str, Any]:
    projection = parse_decision_identity(identity)
    if not projection.explicit:
        return {}
    return {field: projection.subject_values.get(field) for field in SUBJECT_FIELDS} | {
        "freshness_status": projection.subject_values.get("freshness_status")
    }


__all__ = [
    "APPLICABILITY_VALUES",
    "CONTRACT_SPEC_SHA256",
    "DIMENSION_NAMES",
    "DecisionIdentityProjection",
    "EXPLICIT_FIELDS",
    "IDENTITY_ENVELOPE_FIELDS",
    "LEGACY_FIELDS",
    "FRESHNESS_VALUES",
    "SUBJECT_FIELDS",
    "canonical_value",
    "expected_dimension_echo",
    "expected_subject_echo",
    "parse_decision_identity",
]
