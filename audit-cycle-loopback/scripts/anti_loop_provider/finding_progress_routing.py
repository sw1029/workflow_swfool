from __future__ import annotations

from .runtime_dependencies import (
    Any,
    bool_value,
)

from .evaluation_frame import _require_values


def _collect_progress_routing_findings(state: dict[str, Any]) -> None:
    (
        blocker_root_family, coverage_gate, coverage_reconciliation_blocks,
        coverage_reconciliation_gate, current_root_key, detection_streak, detection_streak_cap,
        disagreement, dispatch_gate, findings, measurement_progress,
        measurement_progress_allowed, measurement_streak_cap, measurement_streak_value,
        requires_correction_or_terminal, row, substance_delta_pass, substance_gate,
        task_correction_class, validator_gate,
    ) = _require_values(
        state,
        (
            'blocker_root_family', 'coverage_gate', 'coverage_reconciliation_blocks',
            'coverage_reconciliation_gate', 'current_root_key', 'detection_streak',
            'detection_streak_cap', 'disagreement', 'dispatch_gate', 'findings',
            'measurement_progress', 'measurement_progress_allowed', 'measurement_streak_cap',
            'measurement_streak_value', 'requires_correction_or_terminal', 'row',
            'substance_delta_pass', 'substance_gate', 'task_correction_class',
            'validator_gate',
        ),
    )
    if bool_value(dispatch_gate.get("dispatch_required")):
        row["hard_stop_required"] = True
        if row["recommended_disposition"] in {"open", "prefer_provider_or_semantic"}:
            row["recommended_disposition"] = "provider_scale_dispatch_required"
        findings.append(
            {
                "severity": "block",
                "code": "provider_scale_dispatch_required",
                "message": "no provider dispatch and all coverage high-water marks are zero; derive must select bounded extraction/scale work if authority permits, or terminal/user-escalate with the missing authority/input.",
                "evidence": dispatch_gate,
            }
        )
    if measurement_progress and not measurement_progress_allowed:
        row["measurement_goal_productive_allowed"] = False
        row["requires_non_measurement_goal_productive"] = True
        reason = "measurement_without_coverage_quality_delta"
        if measurement_streak_cap is None:
            reason = "measurement_budget_unverified"
        elif measurement_streak_value > measurement_streak_cap:
            reason = "measurement_streak_capped"
        elif coverage_reconciliation_blocks:
            reason = "coverage_quality_delta_reconciliation_failed"
        elif not substance_delta_pass:
            reason = "measurement_without_substance_delta"
        findings.append(
            {
                "severity": "block",
                "code": reason,
                "message": (
                    "measurement/oracle work cannot be promoted to goal_productive without both G-COV and G-SUBSTANCE deltas, "
                    "and needs an explicit repository-owned budget before any measurement-only credit."
                ),
                "evidence": {
                    "root_key": current_root_key,
                    "measurement_streak": measurement_streak_value,
                    "cap": measurement_streak_cap,
                    "coverage_quality_delta_gate": coverage_gate,
                    "coverage_quality_delta_reconciliation_gate": coverage_reconciliation_gate,
                    "substance_delta_gate": substance_gate,
                },
            }
        )
    if measurement_progress_allowed and not disagreement:
        if "goal_productive" not in row["effective_allowed_dispositions"]:
            row["effective_allowed_dispositions"] = sorted(set(row["effective_allowed_dispositions"]) | {"goal_productive"})
        findings.append(
            {
                "severity": "info",
                "code": "measurement_progress_allowed",
                "message": "new measurement/oracle coverage is allowed because G-COV also observed a coverage or quality delta.",
                "evidence": {
                    "measurement_progress_basis": row["measurement_progress_basis"],
                    "coverage_quality_delta_gate": coverage_gate,
                },
            }
        )
    if bool_value(validator_gate.get("hard_stop_required")):
        findings.append(
            {
                "severity": "block",
                "code": "validator_integrity_or_coverage_failed",
                "message": "validator top-level result disagrees with embedded sub-results, or declared population coverage is incomplete; do not count the validator pass as goal-productive progress.",
                "evidence": validator_gate,
            }
        )
    if requires_correction_or_terminal:
        findings.append(
            {
                "severity": "block",
                "code": "detection_only_streak_capped",
                "message": "detection-only work repeated for the same root blocker family while semantic progress remains false; the next task must be correction, terminal_blocked, or user_escalation.",
                "evidence": {
                    "blocker_root_family": blocker_root_family,
                    "task_correction_class": task_correction_class,
                    "detection_only_streak": detection_streak,
                    "cap": detection_streak_cap,
                },
            }
        )
