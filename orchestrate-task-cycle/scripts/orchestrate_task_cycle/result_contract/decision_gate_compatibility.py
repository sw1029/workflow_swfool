from __future__ import annotations

from typing import Any

from .common import add, first_present, list_values, non_empty
from .decision_identity_dimensions import (
    expected_dimension_echo,
    expected_subject_echo,
    explicit_identity_object,
    normalized_legacy_identity,
    parse_decision_identity,
)


def _compatibility_surface(
    result: dict[str, Any],
) -> tuple[list[Any], bool, bool, bool]:
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
        compatibility_rows = (
            rows.get("rows") if isinstance(rows.get("rows"), list) else []
        )
    else:
        compatibility_rows = rows if isinstance(rows, list) else []
    compatibility_declared = any(
        key in result
        for key in ("gate_compatibility_results", "decision_gate_compatibility")
    ) or isinstance(result.get("gate_compatibility"), dict)
    required_scope_declared = (
        "required_gate_ids" in result
        or isinstance(result.get("gate_compatibility"), dict)
        and "required_gate_ids" in result["gate_compatibility"]
    )
    consumed_scope_declared = any(
        key in result
        for key in (
            "decision_consumed_gate_ids",
            "consumed_gate_ids",
            "decision_gate_ids",
        )
    )
    return (
        compatibility_rows,
        compatibility_declared,
        required_scope_declared,
        consumed_scope_declared,
    )


def _gate_id_sets(result: dict[str, Any]) -> tuple[set[str], set[str]]:
    required_gate_ids = {
        str(item)
        for item in list_values(
            first_present(
                result,
                ["required_gate_ids", "gate_compatibility.required_gate_ids"],
            )
        )
    }
    consumed_gate_ids: set[str] = set()
    for field in (
        "decision_consumed_gate_ids",
        "consumed_gate_ids",
        "decision_gate_ids",
        "residual_gate_ids",
        "hard_stop_gate_ids",
    ):
        consumed_gate_ids.update(
            str(item)
            for item in list_values(first_present(result, [field, f"decision.{field}"]))
        )
    return required_gate_ids, consumed_gate_ids


def _validate_compatibility_row(
    row: Any,
    *,
    identity: object,
    required_gate_ids: set[str],
    consumed_gate_ids: set[str],
    severity: str,
    findings: list[dict[str, Any]],
) -> tuple[str, dict[str, Any]] | None:
    if not isinstance(row, dict) or not non_empty(row.get("gate_id")):
        add(
            findings,
            severity,
            "gate_compatibility_row_invalid",
            "Gate compatibility rows require a gate_id.",
        )
        return None
    gate_id = str(row.get("gate_id"))
    status = str(row.get("gate_compatibility_status") or "").strip().lower()
    if status not in {"compatible", "incompatible", "not_evaluated"}:
        add(
            findings,
            severity,
            "gate_compatibility_status_invalid",
            "Gate compatibility status is invalid.",
            {"gate_id": gate_id},
        )
    if status != "compatible" and gate_id in consumed_gate_ids:
        add(
            findings,
            severity,
            "noncompatible_gate_consumed",
            "An incompatible or unevaluated gate cannot contribute to the decision set.",
            {"gate_id": gate_id, "status": status},
        )
    if not isinstance(identity, dict):
        return gate_id, row
    normalized_identity = normalized_legacy_identity(identity)
    for field in ("artifact_id", "artifact_sha256"):
        if row.get(field) and row.get(field) != normalized_identity.get(field):
            add(
                findings,
                severity,
                "gate_compatibility_artifact_identity_mismatch",
                "Gate compatibility evidence is bound to a different artifact identity.",
                {"gate_id": gate_id, "field": field},
            )
    exact_identity = explicit_identity_object(identity)
    projection = parse_decision_identity(exact_identity or identity)
    identity_echo_required = (
        exact_identity is not None
        and projection.explicit
        and (
            gate_id in consumed_gate_ids
            or (gate_id in required_gate_ids and status == "compatible")
        )
    )
    if identity_echo_required:
        echo = row.get("decision_identity_echo")
        expected_echo = {
            **expected_subject_echo(exact_identity),
            "dimension_values": expected_dimension_echo(exact_identity),
        }
        if echo != expected_echo:
            add(
                findings,
                severity,
                "gate_compatibility_decision_identity_echo_mismatch",
                "Gate compatibility evidence must echo the exact subject and only applicable decision dimensions.",
                {"gate_id": gate_id},
            )
    return gate_id, row


def validate_gate_compatibility(
    contract_version: int | None,
    positive_claim: bool,
    identity: object,
    result: dict[str, Any],
    severity: str,
    findings: list[dict[str, Any]],
) -> None:
    (
        compatibility_rows,
        compatibility_declared,
        required_scope_declared,
        consumed_scope_declared,
    ) = _compatibility_surface(result)
    if contract_version == 1 and positive_claim:
        missing_surfaces = []
        if not compatibility_declared:
            missing_surfaces.append("gate_compatibility_results")
        if not required_scope_declared:
            missing_surfaces.append("required_gate_ids")
        if not consumed_scope_declared:
            missing_surfaces.append("decision_consumed_gate_ids")
        if missing_surfaces:
            add(
                findings,
                severity,
                "decision_gate_compatibility_scope_missing",
                "Current decision contract requires explicit applicable, required, and consumed gate scopes, including explicit empty lists.",
                {"missing_fields": missing_surfaces},
            )
    required_gate_ids, consumed_gate_ids = _gate_id_sets(result)
    by_id: dict[str, dict[str, Any]] = {}
    for row in compatibility_rows:
        validated = _validate_compatibility_row(
            row,
            identity=identity,
            required_gate_ids=required_gate_ids,
            consumed_gate_ids=consumed_gate_ids,
            severity=severity,
            findings=findings,
        )
        if validated is not None:
            gate_id, valid_row = validated
            by_id[gate_id] = valid_row
    missing_required = sorted(
        gate_id
        for gate_id in required_gate_ids
        if gate_id not in by_id
        or str(by_id[gate_id].get("gate_compatibility_status") or "").strip().lower()
        != "compatible"
    )
    if missing_required and positive_claim:
        add(
            findings,
            severity,
            "required_gate_compatibility_not_evaluated",
            "A required decision gate is not proven compatible with the exact artifact.",
            {"gate_ids": missing_required},
        )


__all__ = ["validate_gate_compatibility"]
