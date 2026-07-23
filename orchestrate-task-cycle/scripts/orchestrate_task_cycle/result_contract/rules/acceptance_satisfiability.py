from __future__ import annotations

from ..acceptance_satisfiability import assess_contract_satisfiability
from ..base import RuleContext
from ..common import add
from ..task_routing import selected_task_kind_value


UNVERIFIABLE_ACCEPTANCE_TASK_KINDS = frozenset(
    {
        "acceptance_contract_repair",
        "adapter_hook_supply",
        "descope_with_residual",
        "gate_hook_supply",
        "residual_descope",
        "terminal_blocked",
        "terminal_blocker",
        "user_escalation",
        "verifier_contract_supply",
        "verifier_hook_supply",
    }
)


def validate_acceptance_satisfiability(context: RuleContext) -> None:
    """Reject caller-authored replacements for normalized satisfiability facts."""

    severity = "block" if context.mode == "block" else "warn"
    unverifiable = context.result.get("unverifiable_acceptance_contract") is True
    status = str(context.result.get("acceptance_status") or "").strip().lower()
    if context.target == "acceptance" and status == "normalized" and unverifiable:
        add(
            context.findings,
            severity,
            "normalized_acceptance_contract_unverifiable",
            "Normalized acceptance cannot depend on a required verifier or gate hook that was not evaluated.",
        )
    if context.target == "derive" and unverifiable:
        selected_kind = selected_task_kind_value(context.result)
        if selected_kind not in UNVERIFIABLE_ACCEPTANCE_TASK_KINDS:
            add(
                context.findings,
                severity,
                "derive_unverifiable_acceptance_unhandled",
                "Derive must preserve verifier or gate-hook supply work, explicit residual descope, terminal state, or user escalation before consuming unverifiable acceptance.",
                {"selected_task_kind": selected_kind or None},
            )
    assessment = assess_contract_satisfiability(context.result)
    if not assessment.present:
        return
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
