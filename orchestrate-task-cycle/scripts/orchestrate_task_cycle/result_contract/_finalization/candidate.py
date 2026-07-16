from __future__ import annotations

from typing import Any

from .core import CANDIDATE_KIND, VERDICT_AXES, full_sha256, opaque_id


def candidate_errors(candidate: dict[str, Any]) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    _validate_candidate_identity(candidate, errors)
    _validate_candidate_projection(candidate, errors)
    _validate_candidate_durable_state(candidate, errors)
    return errors


def _error(
    errors: list[dict[str, Any]],
    code: str,
    message: str,
    evidence: Any = None,
) -> None:
    row: dict[str, Any] = {"code": code, "message": message}
    if evidence is not None:
        row["evidence"] = evidence
    errors.append(row)


def _validate_candidate_identity(
    candidate: dict[str, Any], errors: list[dict[str, Any]]
) -> None:
    if candidate.get("schema_version") != 1 or candidate.get("kind") != CANDIDATE_KIND:
        _error(
            errors,
            "final_candidate_schema_invalid",
            "Final candidate requires schema_version=1 and kind=cycle_final_candidate.",
        )
    if candidate.get("final_candidate") is not True:
        _error(
            errors,
            "final_candidate_marker_invalid",
            "Completion validation must mark the immutable candidate with final_candidate=true.",
        )
    for field in ("cycle_id", "attempt_id"):
        if not opaque_id(candidate.get(field)):
            _error(
                errors,
                "final_candidate_identity_invalid",
                "Final candidate identity fields must be bounded opaque strings.",
                {"field": field},
            )
    expected_fields = (
        "expected_previous_revision",
        "expected_previous_attempt_id",
        "expected_previous_finalization_token",
    )
    missing_expected = [field for field in expected_fields if field not in candidate]
    if missing_expected:
        _error(
            errors,
            "final_candidate_previous_binding_missing",
            "Final candidate must explicitly bind the previous pointer, including null first-publication values.",
            {"fields": missing_expected},
        )
    previous_revision = candidate.get("expected_previous_revision")
    if previous_revision is not None and (
        isinstance(previous_revision, bool)
        or not isinstance(previous_revision, int)
        or previous_revision < 1
    ):
        _error(
            errors,
            "final_candidate_revision_invalid",
            "Expected previous revision must be null or a positive integer.",
            {"field": "expected_previous_revision"},
        )
    previous_attempt = candidate.get("expected_previous_attempt_id")
    if previous_attempt is not None and not opaque_id(previous_attempt):
        _error(
            errors,
            "final_candidate_identity_invalid",
            "Expected previous attempt ID must be null or a bounded opaque string.",
            {"field": "expected_previous_attempt_id"},
        )
    previous_token = candidate.get("expected_previous_finalization_token")
    if previous_token is not None and not full_sha256(previous_token):
        _error(
            errors,
            "final_candidate_previous_token_invalid",
            "Expected previous finalization token must be null or a full lowercase SHA-256 digest.",
        )
    previous_fields = (previous_revision, previous_attempt, previous_token)
    if any(value is None for value in previous_fields) and not all(
        value is None for value in previous_fields
    ):
        _error(
            errors,
            "final_candidate_previous_binding_partial",
            "Previous revision, attempt, and token must be all null for the first revision or all populated.",
        )
    if candidate.get("verdict_contract_version") != 1:
        _error(
            errors,
            "final_candidate_verdict_version_invalid",
            "Final candidate must preserve verdict_contract_version=1.",
        )


def _validate_candidate_projection(
    candidate: dict[str, Any], errors: list[dict[str, Any]]
) -> None:
    producer_fields = sorted(
        {
            "authoritative_projection",
            "authoritative_projection_digest",
            "authoritative_projection_id",
            "validation_axes_digest",
        }.intersection(candidate)
    )
    nested_projection = (
        isinstance(candidate.get("finalization"), dict)
        and isinstance(candidate["finalization"].get("authoritative_projection"), dict)
    ) or (
        isinstance(candidate.get("result"), dict)
        and isinstance(candidate["result"].get("authoritative_projection"), dict)
    )
    if producer_fields or nested_projection:
        _error(
            errors,
            "final_candidate_projection_preassigned",
            "Only the existing finalization owner may construct the authoritative projection and its digests.",
            {"fields": producer_fields, "nested_projection": bool(nested_projection)},
        )
    missing_axes = [
        axis for axis in VERDICT_AXES if not isinstance(candidate.get(axis), dict)
    ]
    if missing_axes:
        _error(
            errors,
            "final_candidate_verdict_axis_missing",
            "Final candidate must preserve all six typed verdict axes.",
            {"axes": missing_axes},
        )
    alias_conflicts = _candidate_alias_conflicts(candidate)
    if alias_conflicts:
        _error(
            errors,
            "final_candidate_verdict_alias_conflict",
            "Final candidate verdict aliases disagree with the canonical top-level axes.",
            {"axes": sorted(set(alias_conflicts))},
        )
    if (
        "attempt_revision" in candidate
        or "supersedes_revision" in candidate
        or "supersedes_finalization_token" in candidate
    ):
        _error(
            errors,
            "final_candidate_revision_preassigned",
            "Only the finalization owner may assign attempt revision and supersession lineage.",
        )


def _candidate_alias_conflicts(candidate: dict[str, Any]) -> list[str]:
    result = candidate.get("result")
    alias_containers = [
        candidate.get("verdict_axes"),
        result,
        result.get("verdict_axes") if isinstance(result, dict) else None,
    ]
    conflicts: list[str] = []
    for axis in VERDICT_AXES:
        canonical = candidate.get(axis)
        canonical_status = (
            str(canonical.get("status") or canonical.get("verdict") or "")
            .strip()
            .lower()
            if isinstance(canonical, dict)
            else ""
        )
        for container in alias_containers:
            if not isinstance(container, dict) or axis not in container:
                continue
            alias = container[axis]
            alias_status = (
                str(alias.get("status") or alias.get("verdict") or "").strip().lower()
                if isinstance(alias, dict)
                else str(alias or "").strip().lower()
            )
            if alias_status != canonical_status:
                conflicts.append(axis)
                break
    return conflicts


def _validate_candidate_durable_state(
    candidate: dict[str, Any], errors: list[dict[str, Any]]
) -> None:
    durable_state = candidate.get("durable_state_candidate")
    if not isinstance(durable_state, dict) or durable_state.get("mode") not in {
        "complete_projection",
        "typed_operations",
    }:
        _error(
            errors,
            "final_candidate_durable_state_invalid",
            "Final candidate requires a typed complete_projection or typed_operations durable state candidate.",
        )
