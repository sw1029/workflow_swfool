from __future__ import annotations

from typing import Any

from .common import add, boolish, first_present
from .receipts import _opaque_scalar, _opaque_string_items, _positive_decision_claim


COUPLING_STATUSES = {"disjoint", "overlapping", "same_artifact", "unknown"}
INVARIANT_SEPARATION_STATUSES = {"independent", "coupled", "unknown"}
EVIDENCE_PROVENANCE_STATUSES = {
    "independently_verified",
    "self_grounded",
    "producer_attested",
    "not_evaluated",
}


def _validate_axis_lineage(
    axis: dict[str, Any],
    axis_id: str,
    provenance: str,
    invariant_separation: str,
    severity: str,
    findings: list[dict[str, Any]],
) -> None:
    scalar_fields = (
        "producer_function_id",
        "verifier_function_id",
        "producer_invariant_owner_id",
        "verifier_invariant_owner_id",
        "producer_input_fingerprint",
        "verifier_input_fingerprint",
    )
    scalars: dict[str, str] = {}
    lineage_valid = True
    for field in scalar_fields:
        value = axis.get(field)
        if value is None:
            scalars[field] = ""
        elif _opaque_scalar(value):
            scalars[field] = value.strip()
        else:
            scalars[field] = ""
            lineage_valid = False
    producer_items, producer_ids_valid = _opaque_string_items(axis.get("producer_input_ids"))
    verifier_items, verifier_ids_valid = _opaque_string_items(axis.get("verifier_input_ids"))
    lineage_valid = lineage_valid and producer_ids_valid and verifier_ids_valid
    if not lineage_valid:
        add(
            findings,
            severity if provenance == "independently_verified" else "warn",
            "verification_axis_lineage_invalid",
            "Verification lineage requires bounded opaque function, fingerprint, owner, and input IDs.",
            {"axis_id": axis_id},
        )
    producer_inputs, verifier_inputs = set(producer_items), set(verifier_items)
    comparable = bool(
        scalars["producer_function_id"]
        and scalars["verifier_function_id"]
        and (
            (scalars["producer_input_fingerprint"] and scalars["verifier_input_fingerprint"])
            or (producer_inputs and verifier_inputs)
        )
    )
    coupled = bool(
        scalars["producer_function_id"] == scalars["verifier_function_id"] != ""
        or scalars["producer_input_fingerprint"] == scalars["verifier_input_fingerprint"] != ""
        or (producer_inputs and verifier_inputs and producer_inputs & verifier_inputs)
    )
    producer_owner = scalars["producer_invariant_owner_id"]
    verifier_owner = scalars["verifier_invariant_owner_id"]
    owners_separated = bool(producer_owner and verifier_owner and producer_owner != verifier_owner)
    owners_coupled = bool(producer_owner and producer_owner == verifier_owner)
    if provenance == "independently_verified" and (coupled or not lineage_valid):
        add(
            findings,
            severity,
            "verification_axis_independent_with_coupled_lineage",
            "Independent evidence cannot reuse the producer function or decision inputs.",
            {"axis_id": axis_id},
        )
    if provenance == "independently_verified" and not comparable:
        add(
            findings,
            severity,
            "verification_axis_independent_without_lineage_basis",
            "Independent evidence requires a comparable producer/verifier lineage pair.",
            {"axis_id": axis_id},
        )
    if provenance == "independently_verified" and (
        invariant_separation != "independent" or not owners_separated
    ):
        add(
            findings,
            severity,
            "verification_axis_independent_without_invariant_separation",
            "Independent evidence requires a separately owned decisive invariant in addition to disjoint sources.",
            {"axis_id": axis_id, "invariant_separation_status": invariant_separation},
        )
    if invariant_separation == "independent" and owners_coupled:
        add(
            findings,
            severity,
            "verification_axis_false_invariant_separation",
            "A shared invariant owner cannot be declared independent even when verifier files differ.",
            {"axis_id": axis_id},
        )


def _verification_axis_rows(
    axes: list[object],
    severity: str,
    findings: list[dict[str, Any]],
) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    observed: dict[str, dict[str, Any]] = {}
    observed_provenance: dict[str, str] = {}
    for axis in axes:
        if not isinstance(axis, dict) or not _opaque_scalar(axis.get("axis_id")):
            add(findings, severity, "verification_axis_identity_missing", "Verification axis rows require axis_id.")
            continue
        axis_id = axis["axis_id"].strip()
        observed[axis_id] = axis
        coupling_value = axis.get("coupling_status")
        provenance_value = axis.get("evidence_provenance")
        invariant_value = axis.get("invariant_separation_status")
        coupling = coupling_value.strip().lower() if isinstance(coupling_value, str) else "unknown"
        provenance = provenance_value.strip().lower() if isinstance(provenance_value, str) else "not_evaluated"
        invariant_separation = invariant_value.strip().lower() if isinstance(invariant_value, str) else "unknown"
        observed_provenance[axis_id] = provenance if provenance in EVIDENCE_PROVENANCE_STATUSES else "not_evaluated"
        if coupling not in COUPLING_STATUSES:
            add(findings, severity, "verification_axis_coupling_invalid", "Verification coupling status is invalid.", {"axis_id": axis_id})
        if provenance not in EVIDENCE_PROVENANCE_STATUSES:
            add(findings, severity, "verification_axis_provenance_invalid", "Verification evidence provenance is invalid.", {"axis_id": axis_id})
        if invariant_separation not in INVARIANT_SEPARATION_STATUSES:
            add(findings, severity, "verification_axis_invariant_separation_invalid", "Invariant-separation status is invalid.", {"axis_id": axis_id})
        if provenance == "independently_verified" and coupling != "disjoint":
            add(
                findings,
                severity,
                "verification_axis_independent_without_disjoint_inputs",
                "Independently verified evidence requires disjoint verification inputs.",
                {"axis_id": axis_id, "coupling_status": coupling},
            )
        _validate_axis_lineage(
            axis, axis_id, provenance, invariant_separation, severity, findings
        )
        semantic_axis = boolish(axis.get("semantic_axis")) or str(axis.get("axis_kind") or "").lower() in {
            "semantic",
            "source_semantic",
        }
        if semantic_axis and provenance == "self_grounded":
            add(
                findings,
                severity,
                "self_grounded_semantic_axis_overclaim",
                "Same-artifact structural verification cannot establish a source-independent semantic axis.",
                {"axis_id": axis_id},
            )
        axis_scope = str(axis.get("axis_scope") or "").strip().lower()
        if provenance == "self_grounded" and axis_scope != "root_local":
            add(
                findings,
                severity,
                "self_grounded_scope_invalid",
                "Self-grounded evidence is allowed only for an explicit root-local structural axis.",
                {"axis_id": axis_id, "axis_scope": axis_scope or "missing"},
            )
    return observed, observed_provenance


def validate_verification_axes(
    target: str,
    result: dict[str, Any],
    mode: str,
    findings: list[dict[str, Any]],
) -> None:
    axes_value = first_present(
        result,
        ["verification_axes", "evidence_provenance_gate.verification_axes", "verification_source_separation_gate.verification_axes"],
    )
    axes = axes_value if isinstance(axes_value, list) else []
    severity = "block" if mode == "block" or target in {"validate", "report"} else "warn"
    required_values = first_present(result, ["required_verification_axis_ids", "verification_axis_contract.required_axis_ids"])
    required_items, required_ids_valid = _opaque_string_items(required_values)
    required_ids = set(required_items)
    positive_claim = _positive_decision_claim(target, result)
    required_contract_consumed = boolish(
        first_present(
            result,
            [
                "verification_axis_contract.required_for_acceptance",
                "verification_axis_contract.decision_contribution_allowed",
                "verification_axes_required",
            ],
        )
    )
    if not required_ids_valid:
        add(
            findings,
            severity if positive_claim or required_contract_consumed else "warn",
            "verification_axis_required_ids_invalid",
            "Required verification-axis IDs must be bounded opaque strings.",
        )
    if required_contract_consumed and (not required_ids or not axes):
        add(
            findings,
            severity if positive_claim else "warn",
            "verification_axis_contract_missing",
            "A required verification-axis contract needs bounded required IDs and axis rows before decision consumption.",
        )
    if not axes:
        if required_ids and positive_claim:
            add(
                findings,
                severity,
                "required_verification_axis_not_evaluated",
                "A required verification axis is not evaluated and cannot be consumed as pass.",
                {"axis_ids": sorted(required_ids)},
            )
        return
    observed, observed_provenance = _verification_axis_rows(axes, severity, findings)
    not_evaluated = sorted(
        axis_id
        for axis_id in required_ids
        if axis_id not in observed
        or observed_provenance.get(axis_id, "not_evaluated") == "not_evaluated"
    )
    if not_evaluated and positive_claim:
        add(
            findings,
            severity,
            "required_verification_axis_not_evaluated",
            "A required verification axis is not evaluated and cannot be consumed as pass.",
            {"axis_ids": not_evaluated},
        )


__all__ = (
    "COUPLING_STATUSES",
    "EVIDENCE_PROVENANCE_STATUSES",
    "INVARIANT_SEPARATION_STATUSES",
    "validate_verification_axes",
)
