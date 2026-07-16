from __future__ import annotations

from .runtime_dependencies import (
    Any,
    bool_value,
    budget_value,
)

from .evaluation_frame import _require_values


def _collect_acceptance_findings(state: dict[str, Any]) -> None:
    (
        acceptance_error, budget_evaluations, envelope_thaw_streak, findings,
        measurement_progress, metric_validity_error, metric_validity_gate, reachability_gate,
        row, target_required_verifier_error,
    ) = _require_values(
        state,
        (
            'acceptance_error', 'budget_evaluations', 'envelope_thaw_streak', 'findings',
            'measurement_progress', 'metric_validity_error', 'metric_validity_gate',
            'reachability_gate', 'row', 'target_required_verifier_error',
        ),
    )
    if row["acceptance_unreachable_under_frozen_config"]:
        findings.append(
            {
                "severity": "block",
                "code": "acceptance_unreachable_under_frozen_config",
                "message": "acceptance minimum output is unreachable under the frozen envelope; derive must choose constraint relaxation or user escalation instead of envelope-internal micro-repair.",
                "evidence": reachability_gate,
            }
        )
    envelope_thaw_cap = budget_value(budget_evaluations["envelope_thaw_attempts"])
    if row["envelope_thaw_item_required"]:
        findings.append(
            {
                "severity": (
                    "block"
                    if envelope_thaw_cap is not None
                    and envelope_thaw_streak >= envelope_thaw_cap
                    else "warn"
                ),
                "code": "envelope_thaw_item_required",
                "message": "acceptance is unreachable under a frozen envelope and no thaw item is reserved; preserve a thaw condition or staged thaw schedule before another envelope-internal task.",
                "evidence": {
                    "acceptance_reachability_gate": reachability_gate,
                    "envelope_thaw_streak": envelope_thaw_streak,
                    "cap": envelope_thaw_cap,
                },
            }
        )
    if row["unverifiable_acceptance_contract"]:
        findings.append(
            {
                "severity": "block",
                "code": "unverifiable_acceptance_contract",
                "message": "a measurable acceptance target requires a live verifier, but the verifier was not evaluated; not_evaluated is not a pass.",
                "evidence": reachability_gate,
            }
        )
    if bool_value(metric_validity_gate.get("metric_goal_productive_excluded")):
        findings.append(
            {
                "severity": "block",
                "code": "metric_validity_tautological",
                "message": "oracle or metric validity self-check is tautological; exclude that metric pass from goal-productive evidence and require metric correction or independent output-delta evidence.",
                "evidence": metric_validity_gate,
            }
        )
    elif measurement_progress and not bool_value(metric_validity_gate.get("metric_validity_self_check_provided")):
        findings.append(
            {
                "severity": "warn",
                "code": "metric_validity_self_check_missing",
                "message": "measurement or oracle progress was observed without an adapter metric_validity_self_check; treat metric validity as warning-only unless another gate blocks.",
                "evidence": metric_validity_gate,
            }
        )
    if acceptance_error:
        findings.append(
            {
                "severity": "warn",
                "code": "domain_adapter_acceptance_reachability_failed",
                "message": "domain adapter acceptance_reachability() failed; G-REACH remained indeterminate unless explicit reachability input was supplied.",
                "evidence": {"error": acceptance_error},
            }
        )
    if target_required_verifier_error:
        findings.append(
            {
                "severity": "warn",
                "code": "domain_adapter_target_required_verifier_failed",
                "message": "domain adapter target_required_verifier() failed; measurable acceptance verifier mapping was not applied.",
                "evidence": {"error": target_required_verifier_error},
            }
        )
    if metric_validity_error:
        findings.append(
            {
                "severity": "warn",
                "code": "domain_adapter_metric_validity_failed",
                "message": "domain adapter metric_validity_self_check() failed; G-OENV remained warning-only unless explicit metric validity input was supplied.",
                "evidence": {"error": metric_validity_error},
            }
        )
