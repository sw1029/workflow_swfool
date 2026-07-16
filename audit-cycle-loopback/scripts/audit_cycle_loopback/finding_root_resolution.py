from __future__ import annotations

from .runtime_dependencies import (
    Any,
)

from .evaluation_frame import _require_values


def _collect_root_resolution_findings(state: dict[str, Any]) -> None:
    (
        chain_untried_override, consolidation_streak_cap, findings, row, streak, untried,
    ) = _require_values(
        state,
        (
            'chain_untried_override', 'consolidation_streak_cap', 'findings', 'row', 'streak',
            'untried',
        ),
    )
    if row["hypothesis_exhausted"]:
        row["hard_stop_required"] = True
        row["recommended_disposition"] = "terminal_blocked"
        findings.append(
            {
                "severity": "block",
                "code": "root_cause_hypothesis_exhausted",
                "message": "root-cause untried promotion budget is exhausted without terminal_outcome_changed; derive must not promote another same-family untried repair without supplied input delta.",
                "evidence": {
                    "root_cause_ledger_path": row["root_cause_ledger_path"],
                    "untried_promotion_budget": row["untried_promotion_budget"],
                    "vacuous_untried_attempt_count": row["vacuous_untried_attempt_count"],
                    "hypothesis_exhaustion_seal_path": row.get("hypothesis_exhaustion_seal_path"),
                },
            }
        )
    elif chain_untried_override:
        row["hard_stop_required"] = True
        row["recommended_disposition"] = "terminal_blocked"
        findings.append(
            {
                "severity": "block",
                "code": "cumulative_untried_chain_without_quality_delta",
                "message": "distinct untried root-cause hypotheses no longer override terminal/user escalation because the same goal-distance scope has not improved its quality or substance high-water vector across the configured chain cap.",
                "evidence": {
                    "cumulative_goal_distance_gate": row.get("cumulative_goal_distance_gate"),
                    "root_cause_ledger_path": row["root_cause_ledger_path"],
                    "untried_root_cause_hypotheses": untried[:5],
                },
            }
        )
    elif untried:
        row["hard_stop_required"] = True
        row["recommended_disposition"] = "untried_root_cause_repair_required"
        if "goal_productive" not in row["effective_allowed_dispositions"]:
            row["effective_allowed_dispositions"] = sorted(set(row["effective_allowed_dispositions"]) | {"goal_productive"})
        findings.append(
            {
                "severity": "block",
                "code": "untried_actionable_root_cause",
                "message": "terminal_blocked is invalid while an actionable root-cause hypothesis remains untried; derive must promote that hypothesis as the next goal-productive repair task.",
                "evidence": {
                    "root_cause_ledger_path": row["root_cause_ledger_path"],
                    "untried_root_cause_hypotheses": untried[:5],
                },
            }
        )
    if row["root_cause_unverified_hypotheses"]:
        findings.append(
            {
                "severity": "warn",
                "code": "root_cause_actionability_unverified",
                "message": "root-cause hypotheses with only self-asserted actionability were excluded from untried promotion.",
                "evidence": {"root_cause_unverified_hypotheses": row["root_cause_unverified_hypotheses"][:5]},
            }
        )
    if row["root_cause_duplicate_hypotheses"]:
        findings.append(
            {
                "severity": "warn",
                "code": "root_cause_duplicate_or_rename",
                "message": "root-cause hypotheses equivalent to prior attempted hypotheses were excluded from untried promotion.",
                "evidence": {"root_cause_duplicate_hypotheses": row["root_cause_duplicate_hypotheses"][:5]},
            }
        )
    if (
        consolidation_streak_cap is not None
        and streak >= consolidation_streak_cap
        and "consolidation" in row["effective_allowed_dispositions"]
    ):
        row["effective_allowed_dispositions"] = [item for item in row["effective_allowed_dispositions"] if item != "consolidation"]
        findings.append(
            {
                "severity": "block",
                "code": "consolidation_streak_capped",
                "message": "consolidation is governance-only and does not reduce goal distance; repeated consolidation is capped.",
                "evidence": {"consolidation_streak": streak, "cap": consolidation_streak_cap},
            }
        )
