"""Conditional recurrence audit for finalized advice-clause state."""

from __future__ import annotations

from typing import Any

from .common import add, boolish, first_present
from .receipts import _opaque_scalar


FINALIZED_CLAUSE_STATES = {"pending", "wired", "verified", "retired", "residual"}


def _finalized_rows(result: dict[str, Any]) -> tuple[list[dict[str, Any]], bool]:
    raw = first_present(
        result,
        [
            "finalized_advice_clause_states",
            "advice_recurrence_clause_state",
            "result.finalized_advice_clause_states",
        ],
    )
    if raw is None:
        return [], False
    if isinstance(raw, dict):
        raw = raw.get("rows") if "rows" in raw else [raw]
    if not isinstance(raw, list):
        return [], True
    return [row for row in raw if isinstance(row, dict)], any(
        not isinstance(row, dict) for row in raw
    )


def validate_unconsumed_regression(
    result: dict[str, Any],
    state_by_clause: dict[str, str],
    findings: list[dict[str, Any]],
) -> None:
    rows, malformed = _finalized_rows(result)
    if malformed:
        add(
            findings,
            "warn",
            "finalized_advice_clause_state_malformed",
            "The optional recurrence audit requires finalized clause-state rows; malformed input creates no regression claim.",
        )
    for row in rows:
        clause_id = str(row.get("clause_id") or "").strip()
        recurrence_id = str(row.get("recurrence_id") or "").strip()
        finalized_state = str(row.get("finalized_clause_state") or "").strip().lower()
        recurrence_declared = "recurrence_observed" in row
        if (
            not _opaque_scalar(clause_id)
            or not _opaque_scalar(recurrence_id)
            or finalized_state not in FINALIZED_CLAUSE_STATES
            or not recurrence_declared
        ):
            add(
                findings,
                "warn",
                "finalized_advice_clause_state_malformed",
                "Finalized recurrence rows require opaque recurrence/clause IDs, a known clause state, and recurrence_observed.",
                {"clause_id": clause_id or None},
            )
            continue
        if not boolish(row.get("recurrence_observed")) or finalized_state == "retired":
            continue
        current_state = state_by_clause.get(clause_id, "pending")
        if current_state != "verified":
            add(
                findings,
                "warn",
                "unconsumed_advice_regression",
                "A finalized blocker recurrence names an advice clause that is not currently verified; retain it as non-GT consumption debt.",
                {
                    "clause_id": clause_id,
                    "recurrence_id": recurrence_id,
                    "finalized_clause_state": finalized_state,
                    "current_clause_state": current_state,
                },
            )


__all__ = ("FINALIZED_CLAUSE_STATES", "validate_unconsumed_regression")
