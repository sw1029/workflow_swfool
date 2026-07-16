from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..result_contract.finalization import (
    VERDICT_AXES,
    extract_finalization_receipt,
    load_current_projection,
    projection_conclusions,
    projection_from_result,
    verified_projection,
)


@dataclass(frozen=True)
class FinalizationInputs:
    valid_events: list[dict[str, Any]]
    cycle_id: str
    workspace_root: Path | None
    observed_validation: str
    normalized_observed_validation: str
    observed_progress: str


@dataclass
class FinalizationResult:
    validation_verdict: str
    progress_verdict: str
    authoritative_projection: dict[str, Any] | None = None
    receipt: dict[str, Any] | None = None
    errors: list[dict[str, Any]] = field(default_factory=list)
    verdict_axes: list[dict[str, Any]] = field(default_factory=list)


def _load_projection(
    inputs: FinalizationInputs,
    receipt_source: dict[str, Any] | None,
    finalization_required: bool,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None, list[dict[str, Any]]]:
    root = inputs.workspace_root
    pointer_path = (
        root / ".task" / "cycle" / inputs.cycle_id / "current_finalization.json"
        if root is not None
        else None
    )
    if root is not None and (
        finalization_required
        or receipt_source is not None
        or (pointer_path is not None and pointer_path.is_file())
    ):
        projection, receipt, errors = load_current_projection(root, inputs.cycle_id)
        if receipt is not None and receipt_source is not None:
            if extract_finalization_receipt(receipt_source) != receipt:
                errors.append(
                    {
                        "code": "dashboard_event_receipt_not_current",
                        "message": (
                            "Ledger-event receipt does not match the verified current "
                            "finalization pointer."
                        ),
                    }
                )
            event_projection = projection_from_result(receipt_source)
            if event_projection is not None and event_projection != projection:
                errors.append(
                    {
                        "code": "dashboard_event_projection_not_current",
                        "message": (
                            "Ledger-event projection does not match the verified current "
                            "finalization pointer."
                        ),
                    }
                )
        return projection, receipt, errors
    if receipt_source is not None:
        return verified_projection(receipt_source, {})
    return None, None, []


def resolve_finalization(
    inputs: FinalizationInputs,
    verdict_axis_history: list[dict[str, Any]],
) -> FinalizationResult:
    receipt_source = next(
        (
            event
            for event in reversed(inputs.valid_events)
            if extract_finalization_receipt(event) is not None
        ),
        None,
    )
    finalization_required = any(
        event.get("step") == "validate"
        and (
            event.get("final_candidate") is True
            or str(event.get("finalization_applicability") or "").strip().lower()
            == "required"
        )
        for event in inputs.valid_events
    )
    projection, receipt, errors = _load_projection(
        inputs, receipt_source, finalization_required
    )
    result = FinalizationResult(
        validation_verdict=inputs.observed_validation,
        progress_verdict=inputs.observed_progress,
        authoritative_projection=projection,
        receipt=receipt,
        errors=errors,
    )
    if projection is not None:
        result.validation_verdict, result.progress_verdict = projection_conclusions(
            projection
        )
        if inputs.normalized_observed_validation not in {
            "not_run",
            result.validation_verdict,
        } or inputs.observed_progress not in {"not_run", result.progress_verdict}:
            result.errors.append(
                {
                    "code": "authoritative_projection_dashboard_divergence",
                    "message": (
                        "Dashboard event verdicts disagree with the current finalization projection."
                    ),
                    "evidence": {
                        "observed_validation_verdict": inputs.observed_validation,
                        "observed_progress_verdict": inputs.observed_progress,
                        "projected_validation_verdict": result.validation_verdict,
                        "projected_progress_verdict": result.progress_verdict,
                    },
                }
            )
    elif finalization_required:
        result.errors.append(
            {
                "code": "dashboard_finalization_receipt_missing",
                "message": (
                    "A finalized validation event cannot be rendered as canonical truth "
                    "without its current receipt."
                ),
            }
        )
        result.validation_verdict = "not_finalized"
        result.progress_verdict = "not_finalized"
    result.verdict_axes = (
        [
            {"step": "finalization", "axis": field, "verdict": projection[field]}
            for field in VERDICT_AXES
        ]
        if projection is not None
        else verdict_axis_history
    )
    return result
