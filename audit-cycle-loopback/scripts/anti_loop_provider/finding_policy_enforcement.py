from __future__ import annotations

from .runtime_dependencies import (
    Any,
    bool_value,
)

from .evaluation_frame import _require_values


def _collect_policy_enforcement(state: dict[str, Any]) -> None:
    (
        consolidation_streak_cap, evidence_provenance_error, findings, forced_retarget_gate,
        primary_metric_error, primary_metric_gate, row, streak, verifier_source_error,
    ) = _require_values(
        state,
        (
            'consolidation_streak_cap', 'evidence_provenance_error', 'findings',
            'forced_retarget_gate', 'primary_metric_error', 'primary_metric_gate', 'row',
            'streak', 'verifier_source_error',
        ),
    )
    if row["independently_verified_downgraded_fields"]:
        findings.append(
            {
                "severity": "warn",
                "code": "independent_verification_source_not_disjoint",
                "message": "independently_verified fields were downgraded because verification inputs were missing or overlapped the verified artifacts.",
                "evidence": row["verification_source_separation_gate"],
            }
        )
    if verifier_source_error:
        findings.append(
            {
                "severity": "warn",
                "code": "domain_adapter_verifier_source_paths_failed",
                "message": "domain adapter verifier_source_paths() failed; verifier-source coupling was not applied.",
                "evidence": {"error": verifier_source_error},
            }
        )
    if row["attested_only_movement"]:
        findings.append(
            {
                "severity": "warn",
                "code": "attested_only_movement",
                "message": "metric movement was producer-attested only; it did not update high-water state or reset stall counters.",
                "evidence": row["evidence_provenance_gate"],
            }
        )
    if evidence_provenance_error:
        findings.append(
            {
                "severity": "warn",
                "code": "domain_adapter_evidence_provenance_failed",
                "message": "domain adapter evidence_provenance() failed; legacy progress accounting was used where no explicit provenance packet was supplied.",
                "evidence": {"error": evidence_provenance_error},
            }
        )
    if row["primary_metric_stalled"]:
        findings.append(
            {
                "severity": "block",
                "code": "primary_metric_stalled",
                "message": "adapter-owned primary metric high-water did not move; C4 forced retargeting remains active and label churn cannot reset the stall.",
                "evidence": row["primary_metric_gate"],
            }
        )
    elif bool_value(primary_metric_gate.get("attested_only_movement")):
        findings.append(
            {
                "severity": "warn",
                "code": "primary_metric_attested_only_movement",
                "message": "primary metric movement was producer-attested only; it did not move primary-metric high-water.",
                "evidence": row["primary_metric_gate"],
            }
        )
    if primary_metric_error:
        findings.append(
            {
                "severity": "warn",
                "code": "domain_adapter_primary_metric_failed",
                "message": "domain adapter primary_metric() failed; primary-metric C4 trigger fell back to existing chain-stall behavior.",
                "evidence": {"error": primary_metric_error},
            }
        )
    if row["adapter_mandate_required"]:
        findings.append(
            {
                "severity": "block",
                "code": "adapter_mandate_required",
                "message": "domain adapter contract is unmet across the configured no-quality-delta streak; derive must select adapter registration or adapter strengthening before another domain micro-repair can count as goal-productive.",
                "evidence": row["adapter_mandate_gate"],
            }
        )
    if row.get("adapter_hook_demand"):
        findings.append(
            {
                "severity": "warn",
                "code": "hook_supply_required" if bool_value(row.get("hook_supply_required")) else "adapter_hook_demand",
                "message": "one or more adapter hooks were skipped fail-quiet; demand is ledgered for derive routing but does not by itself hard-stop this packet.",
                "evidence": {
                    "adapter_hook_demand": row.get("adapter_hook_demand"),
                    "hook_supply_required": bool_value(row.get("hook_supply_required")),
                    "demanded_hooks": row.get("demanded_hooks") or [],
                },
            }
        )
    if bool_value(row.get("cumulative_goal_distance_stalled")) and not row["adapter_mandate_required"]:
        findings.append(
            {
                "severity": "block",
                "code": "cumulative_goal_distance_stalled",
                "message": "quality/substance high-water has not improved across the configured cumulative chain cap, independent of blocker label or terminal-outcome churn.",
                "evidence": row["cumulative_goal_distance_gate"],
            }
        )
    if bool_value(forced_retarget_gate.get("chain_stall_force_retarget")):
        findings.append(
            {
                "severity": "block" if forced_retarget_gate.get("forced_selected_task") else "warn",
                "code": "chain_stall_forced_retarget",
                "message": "cumulative goal-distance stall exceeded the forced-retarget threshold; derive must select an actionable listed alternative before terminal/user escalation when one exists.",
                "evidence": forced_retarget_gate,
            }
        )
    state.update({
        "consolidation_streak_cap": consolidation_streak_cap,
        "findings": findings,
        "streak": streak,
    })
