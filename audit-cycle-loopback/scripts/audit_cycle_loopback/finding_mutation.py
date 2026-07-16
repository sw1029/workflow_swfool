from __future__ import annotations

from .runtime_dependencies import (
    Any,
)

from .evaluation_frame import _require_values


def _collect_mutation_findings(state: dict[str, Any]) -> None:
    (
        coverage_reconciliation_blocks, coverage_reconciliation_gate,
        current_blocker_signature, current_rung, delta_class, disagreement, findings,
        force_implementation_cycle, forward_budget_remaining, mutation_kind, outcome_changed,
        row, substance_gate,
    ) = _require_values(
        state,
        (
            'coverage_reconciliation_blocks', 'coverage_reconciliation_gate',
            'current_blocker_signature', 'current_rung', 'delta_class', 'disagreement',
            'findings', 'force_implementation_cycle', 'forward_budget_remaining',
            'mutation_kind', 'outcome_changed', 'row', 'substance_gate',
        ),
    )
    if mutation_kind == "forward_mutation" and not disagreement and outcome_changed and not coverage_reconciliation_blocks:
        if "goal_productive" not in row["effective_allowed_dispositions"]:
            row["effective_allowed_dispositions"] = sorted(set(row["effective_allowed_dispositions"]) | {"goal_productive"})
        findings.append(
            {
                "severity": "info" if not force_implementation_cycle else "warn",
                "code": "blocker_forward_mutation",
                "message": "blocker moved forward within the capability ladder and strict output-delta evidence changed the terminal outcome; treat it as changed rather than a same-family repeat.",
                "evidence": {
                    "blocker_signature": current_blocker_signature,
                    "blocker_ladder_rung": current_rung,
                    "terminal_outcome_changed": outcome_changed,
                    "observed_delta_class": delta_class,
                    "forward_mutation_budget_remaining": forward_budget_remaining,
                    "force_implementation_cycle": force_implementation_cycle,
                },
            }
        )
    elif mutation_kind == "forward_mutation" and (not outcome_changed or coverage_reconciliation_blocks):
        if not outcome_changed:
            row["force_substance_progress"] = True
        if coverage_reconciliation_blocks:
            row["force_gcov_reconciliation"] = True
        reason = "forward_mutation_vacuous"
        message = "capability-ladder movement cannot be promoted when the observed terminal outcome did not change; require strict changed-and-semantic primary-output evidence."
        if coverage_reconciliation_blocks:
            reason = "forward_mutation_with_gcov_disagreement"
            message = "capability-ladder movement cannot be promoted while output_delta and loopback G-COV disagree."
        findings.append(
            {
                "severity": "block",
                "code": reason,
                "message": message,
                "evidence": {
                    "blocker_signature": current_blocker_signature,
                    "blocker_ladder_rung": current_rung,
                    "terminal_outcome_changed": outcome_changed,
                    "observed_delta_class": delta_class,
                    "coverage_quality_delta_reconciliation_gate": coverage_reconciliation_gate,
                    "substance_delta_gate": substance_gate,
                },
            }
        )
    if coverage_reconciliation_blocks:
        row["hard_stop_required"] = True
        findings.append(
            {
                "severity": "block",
                "code": "coverage_quality_delta_gate_disagreement",
                "message": "output_delta and loopback G-COV disagree or expose conflicting values for the same metric key; use the conservative block verdict.",
                "evidence": coverage_reconciliation_gate,
            }
        )
