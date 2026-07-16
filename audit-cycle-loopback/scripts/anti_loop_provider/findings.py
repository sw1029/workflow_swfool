from __future__ import annotations

from .common import *

def apply_disposition_and_findings(ns: dict[str, Any]) -> dict[str, Any]:
    globals().update(ns)
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
    if bool_value(corrective_gate.get("surface_corrective_noop")):
        findings.append(
            {
                "severity": "block",
                "code": "vacuous_corrective_noop",
                "message": "corrective/backfill rows attempted work without resolving any lane; exclude those rows from produced or semantic delta evidence.",
                "evidence": corrective_gate,
            }
        )
    if bool_value(advice_gate.get("advice_metrics_stale")):
        findings.append(
            {
                "severity": "warn",
                "code": "advice_metrics_stale",
                "message": "advice declares output fingerprint claims that do not match the current adapter/output fingerprint; refresh or reclassify the advice before relying on its headline metrics.",
                "evidence": advice_gate,
            }
        )
    if bool_value(advice_gate.get("gate_result_regression_stale")):
        findings.append(
            {
                "severity": "warn",
                "code": "gate_result_regression_stale",
                "message": "a gate verdict regressed from passed to blocked under a stable environment fingerprint; route through the existing advice-freshness/self-check path before trusting stale headline gate state.",
                "evidence": advice_gate,
            }
        )
    if str(partial_progress_gate.get("status")) == "warn":
        findings.append(
            {
                "severity": "warn",
                "code": "partial_progress_axes_flatlined",
                "message": "adapter-reported partial progress axes exist while quality/substance high-water remains flat; recommend decomposing all-or-nothing gates rather than adding another detector.",
                "evidence": partial_progress_gate,
            }
        )
    if adapter_fingerprint_error:
        findings.append(
            {
                "severity": "warn",
                "code": "domain_adapter_output_fingerprint_failed",
                "message": "domain adapter output_fingerprint() failed; advice freshness can only use the quality vector fingerprint.",
                "evidence": {"error": adapter_fingerprint_error},
            }
        )
    if previous_baseline_error:
        findings.append(
            {
                "severity": "warn",
                "code": "domain_adapter_previous_accepted_fp_failed",
                "message": "domain adapter previous_accepted_fp() failed or returned an unusable baseline; registry fallback was used where available.",
                "evidence": {"error": previous_baseline_error, "baseline_source": previous_baseline_source},
            }
        )
    if bool_value(structure_gate.get("structure_consolidation_recommended")):
        findings.append(
            {
                "severity": "warn",
                "code": "structure_consolidation_recommended",
                "message": "domain adapter structure metrics recommend Class C consolidation or module-boundary work.",
                "evidence": structure_gate,
            }
        )
    if structure_error:
        findings.append(
            {
                "severity": "warn",
                "code": "domain_adapter_structure_metrics_failed",
                "message": "domain adapter structure_metrics() failed; structure consolidation signal was skipped.",
                "evidence": {"error": structure_error},
            }
        )
    if facet_map_error:
        findings.append(
            {
                "severity": "warn",
                "code": "domain_adapter_facet_root_map_failed",
                "message": "domain adapter facet_root_map() failed; terminal-outcome fallback grouped this cycle by artifact family and terminal outcome.",
                "evidence": {
                    "error": facet_map_error,
                    "terminal_outcome_key": current_terminal_outcome_key,
                    "terminal_outcome_family_key": terminal_family_key,
                },
            }
        )
    elif facet_root_map_missing:
        findings.append(
            {
                "severity": "warn",
                "code": "facet_root_map_missing",
                "message": "facet_root_map is unavailable; terminal-outcome fallback grouped this cycle by artifact family and terminal outcome so proximate blocker mutations cannot reset same-family caps.",
                "evidence": {
                    "terminal_outcome_key": current_terminal_outcome_key,
                    "terminal_outcome_family_key": terminal_family_key,
                    "raw_root_family_key": raw_root_family_key,
                    "previous_cycle_id": (latest_terminal_family or {}).get("cycle_id"),
                },
            }
        )
    orphan_advice = advice_coherence_finding(root)
    if orphan_advice:
        findings.append(orphan_advice)
    if disagreement:
        findings.append(disagreement)
        row["authoritative_semantic_progress"] = False
        row["hard_stop_required"] = True
    final_terminal_self_resolution = terminal_self_resolution_gate(
        runner_validation,
        output_delta,
        *gate_inputs,
        {
            "recommended_disposition": row.get("recommended_disposition"),
            "terminal_requested": str(row.get("recommended_disposition") or "").strip().lower()
            in {"terminal_blocked", "user_escalation", "goal_terminal"},
            "residual_classification": (
                row.get("terminal_self_resolution_gate") or {}
            ).get("residual_classification"),
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
        row["effective_allowed_dispositions"] = ["goal_productive"]
        row["recommended_disposition"] = "goal_productive"
        row["authoritative_semantic_progress"] = False
        row["hard_stop_required"] = True
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
