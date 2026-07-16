from __future__ import annotations

from typing import Any

from ..result_contract.finalization import (
    extract_finalization_receipt,
    projection_from_result,
    verified_projection,
)
from .events import stage_events


def finalization_source(
    stage: dict[str, Any], validation: dict[str, Any]
) -> dict[str, Any] | None:
    if extract_finalization_receipt(validation) is not None:
        return validation
    candidates = [
        event for event in stage_events(stage) if event.get("step") == "validate"
    ]
    for event in reversed(candidates):
        if extract_finalization_receipt(event) is not None:
            return event
    if extract_finalization_receipt(stage) is not None:
        return stage
    return None


def finalization_projection(
    context: dict[str, Any],
    stage: dict[str, Any],
    validation: dict[str, Any],
) -> tuple[dict[str, Any] | None, dict[str, Any] | None, list[dict[str, Any]]]:
    source = finalization_source(stage, validation)
    if source is None:
        return None, None, []
    projection, receipt, errors = verified_projection(source, context)
    declared_projection = projection_from_result(source)
    if (
        projection is not None
        and declared_projection is not None
        and declared_projection != projection
    ):
        errors.append(
            {
                "code": "authoritative_projection_report_input_mismatch",
                "message": "Report input projection differs from the current immutable finalization snapshot.",
            }
        )
    findings = [
        {
            "severity": "block",
            "code": str(error["code"]),
            "message": str(error["message"]),
            **(
                {"evidence": error["evidence"]}
                if error.get("evidence") is not None
                else {}
            ),
        }
        for error in errors
    ]
    return projection, receipt, findings


def finalization_consumption(receipt: dict[str, Any]) -> dict[str, Any]:
    return {
        field: receipt[field]
        for field in (
            "finalization_token",
            "attempt_id",
            "attempt_revision",
            "authoritative_projection_id",
            "authoritative_projection_digest",
            "receipt_hash",
        )
    }
