from __future__ import annotations

from typing import Any

from .common import add, boolish, first_present, list_values, non_empty
from .receipts import (
    _declared_values,
    _full_sha256,
    _normalized_verdict_status,
    _positive_decision_claim,
)
from .decision_verification import (  # noqa: F401 - compatibility re-exports
    COUPLING_STATUSES,
    EVIDENCE_PROVENANCE_STATUSES,
    validate_verification_axes,
)

DECISION_TARGETS = {"qualitative_review", "loopback_audit", "derive", "validate", "report"}

__all__ = (
    "COUPLING_STATUSES",
    "DECISION_TARGETS",
    "EVIDENCE_PROVENANCE_STATUSES",
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
        required = (
            "artifact_id",
            "artifact_class",
            "artifact_sha256",
            "production_lane_identity",
            "discovery_basis",
        )
        missing = [field for field in required if not non_empty(identity.get(field))]
        scope_verified = boolish(identity.get("scope_verified"))
        advisory = boolish(identity.get("advisory_discovery")) or not scope_verified or bool(missing)
        if identity.get("artifact_sha256") and not _full_sha256(identity.get("artifact_sha256")):
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

        direct_read_scope = {
            str(item).strip().lower()
            for item in list_values(
                first_present(
                    result,
                    [
                        "direct_read_scope",
                        "quality_review.direct_read_scope",
                        "qualitative_review.direct_read_scope",
                        "result.direct_read_scope",
                    ],
                )
            )
            if str(item).strip()
        }
        semantic_axis_values = [
            *_declared_values(
                result,
                (
                    "artifact_semantic_verdict",
                    "verdict_axes.artifact_semantic_verdict",
                    "result.artifact_semantic_verdict",
                    "result.verdict_axes.artifact_semantic_verdict",
                ),
            ),
            *_declared_values(
                result,
                (
                    "goal_readiness_verdict",
                    "verdict_axes.goal_readiness_verdict",
                    "result.goal_readiness_verdict",
                    "result.verdict_axes.goal_readiness_verdict",
                ),
            ),
        ]
        semantic_claim = bool(
            "artifact_body" in direct_read_scope
            or any(_normalized_verdict_status(value) == "pass" for value in semantic_axis_values)
            or boolish(first_present(result, ["semantic_progress", "authoritative_semantic_progress"]))
            or str(first_present(result, ["progress_kind", "effective_progress_kind"]) or "").strip().lower()
            == "goal_productive"
        )
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
        body_fingerprint = next((value for value in body_values if non_empty(value)), None)
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
        if semantic_claim and not _full_sha256(body_fingerprint):
            semantic_binding_missing.append("body_projection_fingerprint")
        if semantic_claim and not cohort_declared:
            semantic_binding_missing.append("source_cohort")
        if semantic_binding_missing:
            add(
                findings,
                severity,
                "decision_semantic_binding_incomplete",
                "Artifact-body, semantic, or goal claims require a current body fingerprint and an explicitly declared source cohort; missing bindings remain not evaluated.",
                {"missing_fields": semantic_binding_missing},
            )


def _validate_explicit_identity_conflict(
    identity: object,
    result: dict[str, Any],
    severity: str,
    findings: list[dict[str, Any]],
) -> None:
    explicit_identity = first_present(result, ["explicit_artifact_ref", "caller_artifact_ref"])
    default_identity = first_present(result, ["default_artifact_ref", "discovered_default_artifact_ref"])
    if isinstance(explicit_identity, dict) and isinstance(default_identity, dict):
        conflict = any(
            explicit_identity.get(field)
            and default_identity.get(field)
            and explicit_identity.get(field) != default_identity.get(field)
            for field in ("artifact_id", "artifact_sha256", "production_lane_identity")
        )
        if conflict:
            selected_id = identity.get("artifact_id") if isinstance(identity, dict) else None
            if selected_id != explicit_identity.get("artifact_id") or not _full_sha256(explicit_identity.get("artifact_sha256")):
                add(
                    findings,
                    severity,
                    "explicit_artifact_conflict_not_resolved",
                    "Exact caller artifact must win over a conflicting default discovery, and its hash must verify.",
                )


def _validate_gate_compatibility(
    contract_version: int | None,
    positive_claim: bool,
    identity: object,
    result: dict[str, Any],
    severity: str,
    findings: list[dict[str, Any]],
) -> None:
    rows = first_present(
        result,
        [
            "gate_compatibility_results",
            "gate_compatibility.rows",
            "decision_gate_compatibility",
            "result.gate_compatibility_results",
        ],
    )
    if isinstance(rows, dict):
        compatibility_rows = rows.get("rows") if isinstance(rows.get("rows"), list) else []
    else:
        compatibility_rows = rows if isinstance(rows, list) else []
    compatibility_declared = any(
        key in result
        for key in ("gate_compatibility_results", "decision_gate_compatibility")
    ) or isinstance(result.get("gate_compatibility"), dict)
    required_gate_scope_declared = "required_gate_ids" in result or isinstance(result.get("gate_compatibility"), dict) and "required_gate_ids" in result["gate_compatibility"]
    consumed_gate_scope_declared = any(
        key in result
        for key in ("decision_consumed_gate_ids", "consumed_gate_ids", "decision_gate_ids")
    )
    if contract_version == 1 and positive_claim:
        missing_surfaces = []
        if not compatibility_declared:
            missing_surfaces.append("gate_compatibility_results")
        if not required_gate_scope_declared:
            missing_surfaces.append("required_gate_ids")
        if not consumed_gate_scope_declared:
            missing_surfaces.append("decision_consumed_gate_ids")
        if missing_surfaces:
            add(
                findings,
                severity,
                "decision_gate_compatibility_scope_missing",
                "Current decision contract requires explicit applicable, required, and consumed gate scopes, including explicit empty lists.",
                {"missing_fields": missing_surfaces},
            )
    required_gate_ids = {
        str(item)
        for item in list_values(first_present(result, ["required_gate_ids", "gate_compatibility.required_gate_ids"]))
    }
    consumed_gate_ids: set[str] = set()
    for field in ("decision_consumed_gate_ids", "consumed_gate_ids", "decision_gate_ids", "residual_gate_ids", "hard_stop_gate_ids"):
        consumed_gate_ids.update(str(item) for item in list_values(first_present(result, [field, f"decision.{field}"])))
    by_id: dict[str, dict[str, Any]] = {}
    for row in compatibility_rows:
        if not isinstance(row, dict) or not non_empty(row.get("gate_id")):
            add(findings, severity, "gate_compatibility_row_invalid", "Gate compatibility rows require a gate_id.")
            continue
        gate_id = str(row.get("gate_id"))
        by_id[gate_id] = row
        status = str(row.get("gate_compatibility_status") or "").strip().lower()
        if status not in {"compatible", "incompatible", "not_evaluated"}:
            add(findings, severity, "gate_compatibility_status_invalid", "Gate compatibility status is invalid.", {"gate_id": gate_id})
        if status != "compatible" and gate_id in consumed_gate_ids:
            add(
                findings,
                severity,
                "noncompatible_gate_consumed",
                "An incompatible or unevaluated gate cannot contribute to the decision set.",
                {"gate_id": gate_id, "status": status},
            )
        if isinstance(identity, dict):
            for field in ("artifact_id", "artifact_sha256"):
                if row.get(field) and row.get(field) != identity.get(field):
                    add(
                        findings,
                        severity,
                        "gate_compatibility_artifact_identity_mismatch",
                        "Gate compatibility evidence is bound to a different artifact identity.",
                        {"gate_id": gate_id, "field": field},
                    )
    missing_required = sorted(
        gate_id
        for gate_id in required_gate_ids
        if gate_id not in by_id
        or str(by_id[gate_id].get("gate_compatibility_status") or "").strip().lower() != "compatible"
    )
    if missing_required and positive_claim:
        add(
            findings,
            severity,
            "required_gate_compatibility_not_evaluated",
            "A required decision gate is not proven compatible with the exact artifact.",
            {"gate_ids": missing_required},
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
        contract_version = int(raw_contract_version) if raw_contract_version is not None else None
    except (TypeError, ValueError):
        contract_version = None
    positive_claim = _positive_decision_claim(target, result)
    severity = (
        "block"
        if mode == "block"
        or target in {"validate", "report"}
        or positive_claim
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
        add(findings, severity, "decision_contract_version_invalid", "Decision contract version must be 1 or explicit legacy version 0.")
        return
    if contract_version == 0:
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
    if contract_version == 1 and not isinstance(identity, dict):
        add(
            findings,
            severity,
            "decision_artifact_identity_missing",
            "Current decision contract requires an exact decision artifact identity.",
        )
    _validate_identity_binding(identity, result, positive_claim, severity, findings)
    _validate_explicit_identity_conflict(identity, result, severity, findings)
    _validate_gate_compatibility(
        contract_version,
        positive_claim,
        identity,
        result,
        severity,
        findings,
    )
