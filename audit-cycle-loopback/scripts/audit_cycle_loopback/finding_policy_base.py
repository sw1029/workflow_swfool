from __future__ import annotations

from .runtime_dependencies import (
    Any,
    budget_value,
    consolidation_streak,
    effective_allowed_dispositions,
    load_json_value,
)

from .evaluation_frame import _require_values


def _collect_policy_base(state: dict[str, Any]) -> None:
    (
        args, budget_evaluations, gate_inputs, ledger_entries, root, row,
    ) = _require_values(
        state,
        (
            'args', 'budget_evaluations', 'gate_inputs', 'ledger_entries', 'root', 'row',
        ),
    )
    effective_allowed, basis = effective_allowed_dispositions(gate_inputs)
    recent_progress = load_json_value(root, getattr(args, "recent_progress_json", None))
    if isinstance(recent_progress, dict):
        recent_progress = recent_progress.get("progress_items") or recent_progress.get("evidence") or recent_progress.get("items")
    if not isinstance(recent_progress, list):
        recent_progress = []
    streak = consolidation_streak([item for item in recent_progress if isinstance(item, dict)])
    row["effective_allowed_dispositions"] = effective_allowed
    row["disposition_intersection_basis"] = basis
    row["consolidation_streak"] = streak
    row["consolidation_reduces_goal_distance"] = False
    consolidation_streak_cap = budget_value(
        budget_evaluations["consolidation_nonsemantic_attempts"]
    )
    row["consolidation_streak_cap"] = consolidation_streak_cap
    row["consolidation_budget_evaluation"] = budget_evaluations[
        "consolidation_nonsemantic_attempts"
    ]
    findings = list(row.get("findings") or [])
    if row.get("budget_unverified"):
        findings.append(
            {
                "severity": "warn",
                "code": "policy_budget_unverified",
                "message": "one or more replay/nonsemantic decision budgets were not supplied; counters remain observations, grant no budget-based progress credit, and create no threshold hard stop.",
                "evidence": {"budget_ids": row["budget_unverified"]},
            }
        )
    rejected_self_reports = [
        {
            "hypothesized_root_cause": entry.get("hypothesized_root_cause"),
            "self_report_rejected_fields": entry.get("self_report_rejected_fields"),
            "repo_owned_source_refs": entry.get("repo_owned_source_refs"),
            "target_surface": entry.get("target_surface"),
        }
        for entry in ledger_entries
        if isinstance(entry, dict) and entry.get("self_report_rejected_fields")
    ]
    if rejected_self_reports:
        findings.append(
            {
                "severity": "warn",
                "code": "repo_owned_source_self_report_rejected",
                "message": "root-cause actionability was derived from repo-owned source provenance; conflicting producer self-report fields were ignored.",
                "evidence": {"root_cause_ledger_entries": rejected_self_reports[:5]},
            }
        )
    decision_ref = row.get("decision_artifact_ref")
    conformance = row.get("consumer_context_conformance")
    consumer_wiring_defect = bool(
        isinstance(decision_ref, dict)
        and (
            decision_ref.get("identity_status") == "consumer_wiring_defect"
            or (
                decision_ref.get("decision_identity_kind") == "explicit_v2"
                and isinstance(conformance, dict)
                and bool(conformance.get("missing_consumer_context_ids"))
            )
        )
    )
    if consumer_wiring_defect:
        findings.append(
            {
                "severity": "block",
                "code": "consumer_wiring_defect",
                "message": "an explicit-v2 decision identity was downgraded or not echoed by the actual consumer; repair the existing consumer wiring before dependent decisions run.",
                "evidence": {
                    "decision_artifact_ref": decision_ref,
                    "consumer_context_conformance": conformance,
                },
            }
        )
    if row["adapter_wiring_defect"]:
        findings.append(
            {
                "severity": "block",
                "code": "adapter_wiring_defect",
                "message": "a registered repository domain adapter did not load; treat this as a self-inflicted workflow wiring/load defect, not adapter absence.",
                "evidence": row["adapter_wiring_gate"],
            }
        )
    if row["pass_with_coupled_verifier"]:
        findings.append(
            {
                "severity": "block",
                "code": "pass_with_coupled_verifier",
                "message": "a passing verifier gate was modified in the same change set; do not read this pass as completion or goal-productive evidence until a non-coupled revalidation or independent evidence recalculation exists.",
                "evidence": row["coupled_verifier_gate"],
            }
        )
    if row["terminal_classification_stage_contradiction"]:
        findings.append(
            {
                "severity": "block",
                "code": "terminal_classification_stage_contradiction",
                "message": "terminal classification contradicts the adapter-owned execution stage observation; do not use that classification for counting or close.",
                "evidence": row["failure_surface_stage_gate"],
            }
        )
    if row["same_input_contract_violation"]:
        findings.append(
            {
                "severity": "block",
                "code": "same_input_contract_violation",
                "message": "a same-condition comparison changed the input set size; the comparison conclusion is not valid close evidence.",
                "evidence": row["same_input_contract_gate"],
            }
        )
    if row["instrumentation_supply_required"]:
        findings.append(
            {
                "severity": "block",
                "code": "instrumentation_supply_required",
                "message": "diagnostics were unavailable for the same failure surface across the configured threshold; derive must enumerate instrumentation supply before another hypothesis repair can count.",
                "evidence": row["diagnostics_unavailable_gate"],
            }
        )
    elif row["diagnostics_unavailable"]:
        findings.append(
            {
                "severity": "warn",
                "code": "diagnostics_unavailable",
                "message": "failure autopsy explicitly reported missing post-failure scalar diagnostics; this is trace evidence for instrumentation-first derivation if it repeats.",
                "evidence": row["diagnostics_unavailable_gate"],
            }
        )
    state.update({
        "consolidation_streak_cap": consolidation_streak_cap,
        "findings": findings,
        "streak": streak,
    })
