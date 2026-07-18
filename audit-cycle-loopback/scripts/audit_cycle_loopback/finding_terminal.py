from __future__ import annotations

from .runtime_dependencies import (
    Any,
    advice_coherence_finding,
    bool_value,
    terminal_self_resolution_gate,
)

from .evaluation_frame import _require_values


def _collect_terminal_findings(state: dict[str, Any]) -> dict[str, Any]:
    (
        disagreement, findings, gate_inputs, output_delta, root, row, runner_validation,
    ) = _require_values(
        state,
        (
            'disagreement', 'findings', 'gate_inputs', 'output_delta', 'root', 'row',
            'runner_validation',
        ),
    )
    orphan_advice = advice_coherence_finding(root)
    if orphan_advice:
        findings.append(orphan_advice)
    if disagreement:
        findings.append(disagreement)
        row["authoritative_semantic_progress"] = False
        row["hard_stop_required"] = True
    existing_residuals = (row.get("terminal_self_resolution_gate") or {}).get(
        "residual_classification"
    )
    if not existing_residuals and bool_value(
        row.get("untried_actionable_root_cause_exists")
    ):
        existing_residuals = [
            {
                "residual_id": "untried_actionable_root_cause",
                "classification": "local_deterministic_repair_possible",
            }
        ]
    final_terminal_self_resolution = terminal_self_resolution_gate(
        runner_validation,
        output_delta,
        *gate_inputs,
        {
            "recommended_disposition": row.get("recommended_disposition"),
            "terminal_requested": str(row.get("recommended_disposition") or "").strip().lower()
            in {"terminal_blocked", "user_escalation", "goal_terminal"},
            "residual_classification": existing_residuals,
        },
    )
    row["terminal_self_resolution_gate"] = final_terminal_self_resolution
    row["offline_scope_unverified"] = bool_value(
        final_terminal_self_resolution.get("offline_scope_unverified")
    )
    row["goal_terminal_prohibited"] = bool_value(
        final_terminal_self_resolution.get("goal_terminal_prohibited")
    )
    if row["goal_terminal_prohibited"]:
        allowed = final_terminal_self_resolution.get("allowed_resolution_dispositions")
        if not isinstance(allowed, list) or not allowed:
            allowed = ["classification_repair"]
        row["effective_allowed_dispositions"] = allowed
        row["recommended_disposition"] = allowed[0]
        row["authoritative_semantic_progress"] = False
        row["hard_stop_required"] = False
        findings.append(
            {
                "severity": "block",
                "code": "goal_terminal_prohibited_by_self_resolvable_residual",
                "message": "current-envelope mutation, local diagnosis/repair, bounded producer execution, or unverified residual classification remains; terminal and user-escalation dispositions are unavailable until it is resolved or classified.",
                "evidence": final_terminal_self_resolution,
            }
        )
    if findings:
        row["findings"] = findings
    return row
