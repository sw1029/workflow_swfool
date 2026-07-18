from __future__ import annotations

from typing import Any

from .common import add, boolish, first_present, non_empty
from .decision_gate_compatibility import validate_gate_compatibility
from .receipts import (
    _declared_values,
    _full_sha256,
    _positive_decision_claim,
)
from .decision_claims import semantic_claim
from .decision_verification import (  # noqa: F401 - compatibility re-exports
    COUPLING_STATUSES,
    EVIDENCE_PROVENANCE_STATUSES,
    INVARIANT_SEPARATION_STATUSES,
    validate_verification_axes,
)
from .decision_identity_dimensions import (
    canonical_value,
    explicit_identity_object,
    normalized_legacy_identity,
    parse_decision_identity,
)
from .legacy_revision_bridge import (
    legacy_revision_bridge_finding,
    terminal_consumption_claim,
)

DECISION_TARGETS = {
    "qualitative_review",
    "loopback_audit",
    "derive",
    "validate",
    "report",
}

__all__ = (
    "COUPLING_STATUSES",
    "DECISION_TARGETS",
    "EVIDENCE_PROVENANCE_STATUSES",
    "INVARIANT_SEPARATION_STATUSES",
    "validate_decision_identity_and_compatibility",
    "validate_verification_axes",
)


def _validate_identity_binding(
    identity: object,
    result: dict[str, Any],
    positive_claim: bool,
    severity: str,
    findings: list[dict[str, Any]],
) -> None:
    if isinstance(identity, dict):
        exact_identity = explicit_identity_object(identity)
        projection = parse_decision_identity(exact_identity or identity)
        if exact_identity is not None and projection.explicit:
            _validate_explicit_identity_binding(
                exact_identity,
                projection,
                result,
                positive_claim,
                severity,
                findings,
            )
            return
        required = (
            "artifact_id",
            "artifact_class",
            "artifact_sha256",
            "production_lane_identity",
            "discovery_basis",
        )
        missing = [field for field in required if not non_empty(identity.get(field))]
        scope_verified = boolish(identity.get("scope_verified"))
        advisory = (
            boolish(identity.get("advisory_discovery"))
            or not scope_verified
            or bool(missing)
        )
        if identity.get("artifact_sha256") and not _full_sha256(
            identity.get("artifact_sha256")
        ):
            missing.append("artifact_sha256(valid_sha256)")
            advisory = True
        if missing:
            add(
                findings,
                severity,
                "decision_artifact_identity_incomplete",
                "Decision-controlling artifact identity is incomplete and must remain advisory.",
                {"missing_fields": sorted(set(missing))},
            )
        if positive_claim and advisory:
            add(
                findings,
                severity,
                "advisory_artifact_controls_decision",
                "An advisory or scope-unverified artifact cannot control completion, progress, hard stop, terminal state, or pack consumption.",
            )

        semantic_claimed = semantic_claim(result)
        body_values = []
        if "body_projection_fingerprint" in identity:
            body_values.append(identity.get("body_projection_fingerprint"))
        body_values.extend(
            _declared_values(
                result,
                (
                    "body_projection_fingerprint",
                    "actual_artifact_truth.body_projection_fingerprint",
                    "quality_review.body_projection_fingerprint",
                    "result.body_projection_fingerprint",
                ),
            )
        )
        body_fingerprint = next(
            (value for value in body_values if non_empty(value)), None
        )
        cohort_values = []
        for field in ("verification_input_ids", "input_fingerprints"):
            if field in identity:
                cohort_values.append(identity.get(field))
        cohort_values.extend(
            _declared_values(
                result,
                (
                    "verification_input_ids",
                    "verification_source_separation_gate.verification_input_ids",
                    "input_fingerprints",
                    "verification_source_separation_gate.input_fingerprints",
                    "result.verification_input_ids",
                    "result.input_fingerprints",
                ),
            )
        )
        cohort_declared = any(non_empty(value) for value in cohort_values)
        semantic_binding_missing: list[str] = []
        if semantic_claimed and not _full_sha256(body_fingerprint):
            semantic_binding_missing.append("body_projection_fingerprint")
        if semantic_claimed and not cohort_declared:
            semantic_binding_missing.append("source_cohort")
        if semantic_binding_missing:
            add(
                findings,
                severity,
                "decision_semantic_binding_incomplete",
                "Artifact-body, semantic, or goal claims require a current body fingerprint and an explicitly declared source cohort; missing bindings remain not evaluated.",
                {"missing_fields": semantic_binding_missing},
            )


def _validate_explicit_identity_binding(
    identity: dict[str, Any],
    projection: Any,
    result: dict[str, Any],
    positive_claim: bool,
    severity: str,
    findings: list[dict[str, Any]],
) -> None:
    if projection.issues:
        add(
            findings,
            severity,
            "decision_identity_applicability_invalid",
            "Explicit decision identity requires exact subject/revision/digest fields and four valid applicability objects.",
            {"fields": list(projection.issues)},
        )
    freshness = projection.subject_values.get("freshness_status")
    if positive_claim and freshness != "current":
        add(
            findings,
            severity,
            "decision_identity_not_current",
            "A stale, conflicted, or unverified decision subject cannot support a positive decision.",
            {"freshness_status": freshness},
        )

    subject_aliases = {
        "decision_subject_id": ("artifact_id", "current_artifact_id"),
        "subject_class_id": ("artifact_class",),
        "subject_digest": ("artifact_sha256",),
        "revision_id": ("artifact_revision_id", "subject_revision_id"),
    }
    conflicts: list[str] = []
    for subject_field, aliases in subject_aliases.items():
        expected = projection.subject_values.get(subject_field)
        for alias in aliases:
            if (
                alias in identity
                and non_empty(identity.get(alias))
                and identity.get(alias) != expected
            ):
                conflicts.append(alias)
    if conflicts:
        add(
            findings,
            severity,
            "decision_subject_alias_mismatch",
            "Legacy artifact aliases must identify the same exact subject, revision, and digest as the explicit decision identity.",
            {"fields": sorted(set(conflicts))},
        )

    dimension_paths = {
        "body_fingerprint": (
            "body_projection_fingerprint",
            "actual_artifact_truth.body_projection_fingerprint",
            "quality_review.body_projection_fingerprint",
            "result.body_projection_fingerprint",
        ),
        "production_lane": (
            "production_lane_identity",
            "actual_artifact_truth.production_lane_identity",
            "result.production_lane_identity",
        ),
        "cohort": (
            "cohort_identity",
            "verification_input_ids",
            "input_fingerprints",
            "result.cohort_identity",
        ),
        "producer_run": (
            "producer_run_id",
            "measurement_run_id",
            "result.producer_run_id",
        ),
    }
    mismatch: list[str] = []
    forbidden_echo: list[str] = []
    for dimension, paths in dimension_paths.items():
        declared = _declared_values(result, paths)
        status = projection.dimension_statuses.get(dimension)
        expected = projection.dimension_values.get(dimension)
        if status == "applicable":
            if any(
                canonical_value(value) != canonical_value(expected)
                for value in declared
            ):
                mismatch.append(dimension)
        elif status == "not_applicable" and declared:
            forbidden_echo.append(dimension)
    claim_severity = severity if positive_claim or semantic_claim(result) else "warn"
    if mismatch:
        add(
            findings,
            claim_severity,
            "decision_applicable_dimension_mismatch",
            "An applicable decision dimension does not match the exact current subject binding.",
            {"dimensions": sorted(mismatch)},
        )
    if forbidden_echo:
        add(
            findings,
            claim_severity,
            "decision_nonapplicable_dimension_echoed",
            "A not-applicable dimension must be bypassed rather than echoed into a consuming decision.",
            {"dimensions": sorted(forbidden_echo)},
        )


def _validate_explicit_identity_conflict(
    identity: object,
    result: dict[str, Any],
    severity: str,
    findings: list[dict[str, Any]],
) -> None:
    explicit_identity = first_present(
        result, ["explicit_artifact_ref", "caller_artifact_ref"]
    )
    default_identity = first_present(
        result, ["default_artifact_ref", "discovered_default_artifact_ref"]
    )
    if isinstance(explicit_identity, dict) and isinstance(default_identity, dict):
        conflict = any(
            explicit_identity.get(field)
            and default_identity.get(field)
            and explicit_identity.get(field) != default_identity.get(field)
            for field in ("artifact_id", "artifact_sha256", "production_lane_identity")
        )
        if conflict:
            selected_id = normalized_legacy_identity(identity).get("artifact_id")
            if selected_id != explicit_identity.get("artifact_id") or not _full_sha256(
                explicit_identity.get("artifact_sha256")
            ):
                add(
                    findings,
                    severity,
                    "explicit_artifact_conflict_not_resolved",
                    "Exact caller artifact must win over a conflicting default discovery, and its hash must verify.",
                )


def validate_decision_identity_and_compatibility(
    target: str,
    result: dict[str, Any],
    mode: str,
    findings: list[dict[str, Any]],
) -> None:
    if target not in DECISION_TARGETS:
        return
    raw_contract_version = first_present(
        result,
        [
            "decision_contract_version",
            "result.decision_contract_version",
            "anti_loop_progress_gate.decision_contract_version",
            "handoff_contract_version",
        ],
    )
    try:
        contract_version = (
            int(raw_contract_version) if raw_contract_version is not None else None
        )
    except (TypeError, ValueError):
        contract_version = None
    positive_claim = _positive_decision_claim(target, result)
    terminal_claim = terminal_consumption_claim(result)
    severity = (
        "block"
        if mode == "block" or target in {"validate", "report"} or positive_claim
        else "warn"
    )
    contract_required = positive_claim
    if contract_required and raw_contract_version is None:
        add(
            findings,
            severity,
            "decision_contract_version_missing",
            "Current decision claims require decision_contract_version=1; legacy consumption requires explicit version 0.",
        )
        return
    if raw_contract_version is not None and contract_version not in {0, 1}:
        add(
            findings,
            severity,
            "decision_contract_version_invalid",
            "Decision contract version must be 1 or explicit legacy version 0.",
        )
        return
    identity = first_present(
        result,
        [
            "decision_input_identity",
            "decision_artifact_ref",
            "selected_artifact_ref",
            "artifact_ref",
            "actual_artifact_ref",
            "result.decision_input_identity",
        ],
    )
    exact_identity = explicit_identity_object(identity)
    identity_projection = parse_decision_identity(exact_identity or identity)
    bridge_finding = legacy_revision_bridge_finding(
        result,
        identity,
        required=bool(
            contract_version in {0, 1}
            and (positive_claim or terminal_claim)
            and (contract_version == 0 or not identity_projection.explicit)
        ),
    )
    if bridge_finding is not None:
        bridge_code, bridge_issues = bridge_finding
        add(
            findings,
            "block",
            bridge_code,
            "Legacy v0/v1 identity cannot control semantic progress, completion, terminal state, hard stop, or pack consumption without a current revision-bound bridge receipt.",
            {"fields": bridge_issues},
        )
    if contract_version == 0:
        return
    if contract_version == 1 and not isinstance(identity, dict):
        add(
            findings,
            severity,
            "decision_artifact_identity_missing",
            "Current decision contract requires an exact decision artifact identity.",
        )
    _validate_identity_binding(identity, result, positive_claim, severity, findings)
    _validate_explicit_identity_conflict(identity, result, severity, findings)
    validate_gate_compatibility(
        contract_version,
        positive_claim,
        identity,
        result,
        severity,
        findings,
    )
