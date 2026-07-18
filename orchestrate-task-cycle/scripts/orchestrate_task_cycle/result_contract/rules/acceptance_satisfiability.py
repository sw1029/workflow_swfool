from __future__ import annotations

from ..acceptance_satisfiability import assess_contract_satisfiability
from ..base import RuleContext
from ..common import add


def validate_acceptance_satisfiability(context: RuleContext) -> None:
    """Reject caller-authored replacements for normalized satisfiability facts."""

    assessment = assess_contract_satisfiability(context.result)
    if not assessment.present:
        return
    severity = "block" if context.mode == "block" else "warn"
    mismatches: list[str] = []
    if not assessment.supplied_rows_match:
        mismatches.append("validation_predicate_contract.satisfiability_rows")
    if not assessment.supplied_conflict_matches:
        mismatches.append("mutually_unsatisfiable_contract")
    if not assessment.supplied_unverifiable_matches:
        mismatches.append("unverifiable_acceptance_contract")
    if mismatches:
        add(
            context.findings,
            severity,
            "acceptance_satisfiability_claim_mismatch",
            "Predicate/directive satisfiability claims must equal an independent recomputation from the raw bound contracts.",
            {
                "mismatched_fields": mismatches,
                "derived_mutually_unsatisfiable": assessment.mutually_unsatisfiable,
                "derived_unverifiable": assessment.unverifiable,
            },
        )
    status = str(context.result.get("acceptance_status") or "").strip().lower()
    if (
        context.target == "acceptance"
        and status == "normalized"
        and (assessment.mutually_unsatisfiable or assessment.unverifiable)
    ):
        add(
            context.findings,
            severity,
            "normalized_acceptance_contract_not_satisfiable",
            "Normalized acceptance requires every bound predicate/directive row to be independently reproducible and satisfiable.",
            {
                "derived_mutually_unsatisfiable": assessment.mutually_unsatisfiable,
                "derived_unverifiable": assessment.unverifiable,
            },
        )


__all__ = ("validate_acceptance_satisfiability",)
