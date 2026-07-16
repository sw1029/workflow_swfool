from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..base import RuleContext
from ..common import add, boolish, first_present
from .qualitative_common import nonzero_scalar, opaque_id, scalar_counts_valid


SURFACE_REQUIRED_PATHS = (
    "surface_field_review_required",
    "surface_field_review_gate.required_for_acceptance",
    "surface_field_review_gate.decision_contribution_allowed",
    "quality_review.surface_field_review_required",
    "quality_review.surface_field_review_gate.required_for_acceptance",
    "quality_review.surface_field_review_gate.decision_contribution_allowed",
    "qualitative_review.surface_field_review_required",
    "qualitative_review.surface_field_review_gate.required_for_acceptance",
    "qualitative_review.surface_field_review_gate.decision_contribution_allowed",
    "result.surface_field_review_required",
    "result.surface_field_review_gate.required_for_acceptance",
    "result.surface_field_review_gate.decision_contribution_allowed",
    "result.quality_review.surface_field_review_required",
    "result.quality_review.surface_field_review_gate.required_for_acceptance",
    "result.quality_review.surface_field_review_gate.decision_contribution_allowed",
)


@dataclass
class SurfaceInventory:
    classes: list[str]
    rows_by_id: dict[str, dict[str, Any]]
    unresolved: list[dict[str, object]]


def validate_surface_review(context: RuleContext) -> None:
    result = context.result
    gate = first_present(
        result,
        [
            "surface_field_review_gate",
            "quality_review.surface_field_review_gate",
            "qualitative_review.surface_field_review_gate",
            "result.surface_field_review_gate",
            "result.quality_review.surface_field_review_gate",
        ],
    )
    required = any(
        boolish(first_present(result, [path])) for path in SURFACE_REQUIRED_PATHS
    )
    if required and not isinstance(gate, dict):
        add(
            context.findings,
            "block" if context.mode == "block" else "warn",
            "qualitative_review_surface_required_missing",
            "A required active-surface review gate must be present before an acceptance decision.",
        )
    if isinstance(gate, dict):
        _validate_surface_gate(context, gate, required)


def _validate_surface_gate(
    context: RuleContext,
    gate: dict[str, Any],
    required: bool,
) -> None:
    status_value = gate.get("surface_field_review_status")
    status = (
        status_value.strip().lower()
        if isinstance(status_value, str)
        else "invalid_contract"
    )
    if status not in {
        "pass",
        "fail",
        "not_applicable",
        "not_evaluated",
        "invalid_contract",
    }:
        status = "invalid_contract"
    claim_relevant = status == "pass" or required
    if required and status not in {"pass", "not_applicable"}:
        add(
            context.findings,
            "block" if context.mode == "block" else "warn",
            "qualitative_review_surface_required_not_passed",
            "A required active-surface review must pass or be explicitly not_applicable before acceptance.",
            {
                "surface_field_review_status": "invalid_contract"
                if status == "invalid_contract"
                else status
            },
        )
    inventory = _surface_inventory(gate, status, claim_relevant)
    matrix, malformed = _defect_matrix(context.result, gate)
    if malformed:
        inventory.unresolved.append(
            {"field_class_id": None, "reason": "defect_matrix_malformed"}
        )
    for field_class_id in inventory.classes:
        reason = _unresolved_class_reason(
            field_class_id,
            inventory.rows_by_id.get(field_class_id),
            matrix,
            matrix is not None,
        )
        if reason:
            inventory.unresolved.append(
                {"field_class_id": field_class_id, "reason": reason}
            )
    if inventory.unresolved:
        add(
            context.findings,
            ("block" if context.mode == "block" else "warn")
            if claim_relevant
            else "warn",
            "qualitative_review_surface_class_bypass",
            "An aggregate or required surface review cannot hide an active field class that was not observed and referentially reviewed.",
            {"unresolved_field_classes": inventory.unresolved},
        )


def _surface_inventory(
    gate: dict[str, Any], aggregate_status: str, claim_relevant: bool
) -> SurfaceInventory:
    classes_value = gate.get("surface_field_classes")
    malformed = False
    classes: list[str] = []
    if isinstance(classes_value, list):
        for item in classes_value:
            normalized = opaque_id(item)
            if normalized is None:
                malformed = True
            else:
                classes.append(normalized)
    elif classes_value is not None:
        malformed = True
    rows_value = gate.get("field_class_results")
    if isinstance(rows_value, dict):
        rows: list[Any] = []
        for key, value in rows_value.items():
            field_class_id = opaque_id(key)
            if field_class_id is None or not isinstance(value, dict):
                malformed = True
                continue
            rows.append(dict(value, field_class_id=field_class_id))
    else:
        rows = rows_value if isinstance(rows_value, list) else []
        if rows_value is not None and not isinstance(rows_value, list):
            malformed = True
    if any(not isinstance(row, dict) for row in rows):
        malformed = True
        rows = [row for row in rows if isinstance(row, dict)]
    row_ids = [
        normalized
        for row in rows
        if (normalized := opaque_id(row.get("field_class_id"))) is not None
    ]
    if any(opaque_id(row.get("field_class_id")) is None for row in rows):
        malformed = True
    rows_by_id = {
        normalized: row
        for row in rows
        if (normalized := opaque_id(row.get("field_class_id"))) is not None
    }
    unresolved: list[dict[str, object]] = []
    if malformed:
        unresolved.append(
            {"field_class_id": None, "reason": "field_class_id_malformed"}
        )
    if boolish(gate.get("field_class_map_missing")):
        unresolved.append({"field_class_id": None, "reason": "field_class_map_missing"})
    inventory_na = (
        str(
            gate.get("surface_field_inventory_status")
            or gate.get("surface_field_review_status")
            or ""
        )
        .strip()
        .lower()
        == "not_applicable"
    )
    if claim_relevant and not classes and not inventory_na:
        unresolved.append(
            {"field_class_id": None, "reason": "field_class_inventory_empty"}
        )
    if aggregate_status == "pass" and inventory_na:
        unresolved.append(
            {
                "field_class_id": None,
                "reason": "not_applicable_inventory_marked_pass",
            }
        )
    duplicate_ids = sorted(
        {
            field_id
            for field_id in {*classes, *row_ids}
            if classes.count(field_id) > 1 or row_ids.count(field_id) > 1
        }
    )
    unresolved.extend(
        {"field_class_id": field_id, "reason": "duplicate_or_conflicting_rows"}
        for field_id in duplicate_ids
    )
    return SurfaceInventory(classes, rows_by_id, unresolved)


def _defect_matrix(
    result: dict[str, Any], gate: dict[str, Any]
) -> tuple[dict[str, dict[str, object]] | None, bool]:
    value = gate.get("surface_field_defect_matrix")
    if value is None:
        value = first_present(
            result,
            [
                "surface_field_defect_matrix",
                "quality_review.surface_field_defect_matrix",
                "qualitative_review.surface_field_defect_matrix",
            ],
        )
    if value is None:
        return None, False
    if not isinstance(value, dict):
        return {}, True
    matrix: dict[str, dict[str, object]] = {}
    malformed = False
    for key, counts in value.items():
        field_class_id = opaque_id(key)
        if field_class_id is None or not scalar_counts_valid(counts):
            malformed = True
            continue
        matrix[field_class_id] = counts
    return matrix, malformed


def _unresolved_class_reason(
    field_class_id: str,
    row: dict[str, Any] | None,
    matrix: dict[str, dict[str, object]] | None,
    matrix_supplied: bool,
) -> str | None:
    if not row:
        return "row_missing"
    applicability = str(row.get("applicability_status") or "applicable").strip().lower()
    review_status = str(row.get("review_status") or "not_evaluated").strip().lower()
    substance = str(row.get("referential_substance_status") or "").strip().lower()
    if (
        applicability
        not in {
            "applicable",
            "not_applicable",
            "insufficient_evidence",
            "invalid_contract",
        }
        or review_status not in {"pass", "fail", "not_observed", "not_evaluated"}
        or (
            substance
            and substance
            not in {
                "meaningful",
                "not_meaningful",
                "not_applicable",
                "insufficient_evidence",
                "invalid_contract",
            }
        )
    ):
        return "invalid_status"
    if applicability == "not_applicable":
        return None
    counts = row.get("defect_counts")
    counts_valid = scalar_counts_valid(counts)
    matrix_counts = matrix.get(field_class_id) if isinstance(matrix, dict) else None
    matrix_conflict = matrix_supplied and (
        matrix_counts is None or not counts_valid or matrix_counts != counts
    )
    locator_status = str(row.get("locator_status") or "").strip().lower()
    referential_na = (
        locator_status == "not_applicable" and substance == "not_applicable"
    )
    referential_unresolved = not referential_na and (
        locator_status != "present" or substance != "meaningful"
    )
    observed_count = row.get("observed_count")
    if (
        applicability != "applicable"
        or review_status != "pass"
        or not isinstance(observed_count, int)
        or isinstance(observed_count, bool)
        or observed_count <= 0
        or referential_unresolved
        or not counts_valid
        or nonzero_scalar(counts)
        or matrix_conflict
    ):
        if matrix_conflict:
            return "defect_projection_conflict"
        if referential_unresolved:
            return "not_substantively_reviewed"
        return "not_fully_reviewed"
    return None
