from __future__ import annotations

from ..base import RuleContext, TargetContractRule
from ..common import add, boolish, deep_get, list_values, non_empty, number_value, value_for


class LoopbackAuditRule(TargetContractRule):
    """Validate authoritative pre-derive progress and anti-loop disposition."""

    targets = frozenset({'loopback_audit'})

    def check(self, context: RuleContext) -> None:
        result = context.result
        mode = context.mode
        findings = context.findings
        evidence_class = str(value_for(result, "evidence_class") or "").lower()
        disposition = str(value_for(result, "recommended_disposition") or "").lower()
        semantic_progress = boolish(value_for(result, "semantic_progress"))
        hard_stop = boolish(value_for(result, "hard_stop_required"))
        measurement_progress_allowed = boolish(value_for(result, "measurement_progress_allowed"))
        substance_delta_pass = boolish(deep_get(result, "substance_delta_gate.substance_delta_pass"))
        vacuous_corrective_noop = boolish(deep_get(result, "vacuous_corrective_gate.surface_corrective_noop"))
        adapter_mandate_required = boolish(value_for(result, "adapter_mandate_required"))
        adapter_wiring_defect = boolish(value_for(result, "adapter_wiring_defect"))
        cumulative_chain_stalled = boolish(value_for(result, "cumulative_goal_distance_stalled"))
        chain_stall_streak = number_value(value_for(result, "cumulative_goal_distance_stall_streak")) or 0
        chain_stall_cap = number_value(deep_get(result, "cumulative_goal_distance_gate.cumulative_goal_distance_stall_cap")) or number_value(value_for(result, "cumulative_goal_distance_stall_cap")) or 0
        untried_veto_overridden = boolish(value_for(result, "untried_veto_overridden_by_chain_stall"))
        forced_retarget_gate = deep_get(result, "chain_stall_forced_retarget_gate")
        forced_retarget_options = deep_get(result, "forced_selected_task_options")
        acceptance_unreachable = boolish(value_for(result, "acceptance_unreachable_under_frozen_config"))
        unverifiable_acceptance = boolish(value_for(result, "unverifiable_acceptance_contract"))
        metric_goal_productive_excluded = boolish(deep_get(result, "oracle_metric_validity_gate.metric_goal_productive_excluded"))
        pass_with_coupled_verifier = boolish(value_for(result, "pass_with_coupled_verifier")) or boolish(deep_get(result, "coupled_verifier_gate.pass_with_coupled_verifier"))
        attested_only_movement = boolish(value_for(result, "attested_only_movement")) or boolish(deep_get(result, "evidence_provenance_gate.attested_only_movement")) or boolish(deep_get(result, "primary_metric_gate.attested_only_movement"))
        pass_with_unobserved_axes = boolish(value_for(result, "pass_with_unobserved_axes")) or boolish(deep_get(result, "goal_axis_completeness_gate.pass_with_unobserved_axes"))
        unobserved_goal_axes = value_for(result, "unobserved_goal_axes") or deep_get(result, "goal_axis_completeness_gate.unobserved_goal_axes")
        generation_dependent_count_key = boolish(value_for(result, "generation_dependent_count_key")) or boolish(deep_get(result, "count_key_hygiene_gate.generation_dependent_count_key"))
        effective_count_key = (
            value_for(result, "effective_count_key")
            or deep_get(result, "count_key_hygiene_gate.effective_count_key")
            or value_for(result, "root_dominant_parameter_key")
            or value_for(result, "terminal_outcome_family_key")
        )
        generation_key_novelty_claim = boolish(value_for(result, "family_novelty_claim")) or boolish(value_for(result, "stall_reset_claim")) or boolish(deep_get(result, "count_key_hygiene_gate.family_novelty_claim")) or boolish(deep_get(result, "count_key_hygiene_gate.stall_reset_claim"))
        residual_cost_below_policy = boolish(value_for(result, "residual_gap_cost_below_policy")) or boolish(value_for(result, "value_per_cycle_cost_below_policy")) or boolish(deep_get(result, "residual_gap_cost_policy.below_policy"))
        primary_metric_high_water_moved = boolish(value_for(result, "primary_metric_high_water_moved")) or boolish(deep_get(result, "primary_metric_gate.primary_metric_high_water_moved"))
        primary_metric_stalled = boolish(value_for(result, "primary_metric_stalled")) or boolish(deep_get(result, "primary_metric_gate.primary_metric_stalled"))
        c4_user_escalation = boolish(value_for(result, "c4_user_escalation_backstop_required")) or boolish(deep_get(result, "primary_metric_gate.c4_user_escalation_backstop_required"))
        terminal_stage_contradiction = boolish(value_for(result, "terminal_classification_stage_contradiction")) or boolish(deep_get(result, "failure_surface_stage_gate.terminal_classification_stage_contradiction"))
        terminal_classification_invalid_for_counting = boolish(value_for(result, "terminal_classification_invalid_for_counting")) or boolish(deep_get(result, "failure_surface_stage_gate.terminal_classification_invalid_for_counting"))
        same_input_contract_violation = boolish(value_for(result, "same_input_contract_violation")) or boolish(deep_get(result, "same_input_contract_gate.same_input_contract_violation"))
        instrumentation_supply_required = boolish(value_for(result, "instrumentation_supply_required")) or boolish(deep_get(result, "diagnostics_unavailable_gate.instrumentation_supply_required"))
        independent_source_status = str(
            value_for(result, "independent_source_separation_status")
            or deep_get(result, "verification_source_separation_gate.independent_source_separation_status")
            or deep_get(result, "evidence_provenance_gate.independent_source_separation_status")
            or ""
        ).lower()
        independently_verified_downgraded_fields = list_values(
            value_for(result, "independently_verified_downgraded_fields")
            or deep_get(result, "verification_source_separation_gate.independently_verified_downgraded_fields")
            or deep_get(result, "evidence_provenance_gate.independently_verified_downgraded_fields")
        )
        self_grounded_axes = set(
            list_values(
                value_for(result, "self_grounded_axes")
                or deep_get(result, "verification_source_separation_gate.self_grounded_axes")
                or deep_get(result, "evidence_provenance_gate.self_grounded_axes")
            )
        )
        independently_verified_fields = set(
            list_values(
                value_for(result, "independently_verified_fields")
                or deep_get(result, "evidence_provenance_gate.independently_verified_fields")
            )
        )
        self_grounded_mislabeled_independent = sorted(self_grounded_axes & independently_verified_fields)
        envelope_thaw_item_required = boolish(value_for(result, "envelope_thaw_item_required")) or boolish(deep_get(result, "acceptance_reachability_gate.envelope_thaw_item_required"))
        envelope_thaw_item = value_for(result, "envelope_thaw_item") or deep_get(result, "acceptance_reachability_gate.envelope_thaw_item")
        scenario_uncovered = boolish(value_for(result, "scenario_uncovered")) or boolish(deep_get(result, "acceptance_scenario_gate.scenario_uncovered"))
        acceptance_inversion = boolish(value_for(result, "acceptance_inversion")) or boolish(deep_get(result, "acceptance_scenario_gate.acceptance_inversion"))
        command_provenance_missing = boolish(value_for(result, "command_provenance_missing")) or boolish(deep_get(result, "command_provenance_gate.command_provenance_missing"))
        repeated_blocker_opacity = boolish(value_for(result, "repeated_blocker_opacity")) or boolish(deep_get(result, "blocker_actionability_gate.repeated_blocker_opacity"))
        predetermined_unreachable = boolish(value_for(result, "predetermined_unreachable")) or boolish(deep_get(result, "stochastic_feasibility_gate.predetermined_unreachable"))
        floor_edge_envelope = boolish(value_for(result, "floor_edge_envelope")) or boolish(deep_get(result, "stochastic_feasibility_gate.floor_edge_envelope"))
        instrumentation_first_fire = boolish(value_for(result, "instrumentation_first_fire")) or boolish(deep_get(result, "instrumentation_first_fire_gate.instrumentation_first_fire"))
        first_fire_consumed_item_id = value_for(result, "first_fire_consumed_item_id") or deep_get(result, "instrumentation_first_fire_gate.first_fire_consumed_item_id")
        first_fire_double_counted = boolish(value_for(result, "first_fire_double_counted")) or boolish(deep_get(result, "instrumentation_first_fire_gate.first_fire_double_counted"))
        blocker_mutation = str(value_for(result, "blocker_mutation_kind") or "").lower()
        forward_mutation_progress = blocker_mutation == "forward_mutation"
        terminal_outcome_value = value_for(result, "terminal_outcome_changed")
        terminal_outcome_changed = (
            boolish(terminal_outcome_value)
            if terminal_outcome_value is not None
            else boolish(value_for(result, "changed_vs_previous")) and boolish(value_for(result, "semantic_progress"))
        )
        forward_mutation_vacuous = boolish(value_for(result, "forward_mutation_vacuous"))
        count_value = value_for(result, "same_family_micro_hardening_count")
        try:
            streak_count = int(str(count_value))
        except (TypeError, ValueError):
            streak_count = None
        if evidence_class == "insufficient_evidence" and not (measurement_progress_allowed or forward_mutation_progress) and (disposition != "conservative_hold" or not hard_stop):
            add(
                findings,
                "block" if mode == "block" else "warn",
                "loopback_insufficient_not_fail_closed",
                "`loopback_audit` insufficient evidence must use conservative_hold with hard_stop_required=true.",
            )
        if streak_count is not None and streak_count >= 3 and not semantic_progress and not hard_stop and not (measurement_progress_allowed or forward_mutation_progress):
            add(
                findings,
                "block" if mode == "block" else "warn",
                "loopback_streak_without_hard_stop",
                "`loopback_audit` same-family micro-hardening count >=3 without semantic progress must hard-stop.",
                {"same_family_micro_hardening_count": streak_count},
            )
        if forward_mutation_progress and (forward_mutation_vacuous or not terminal_outcome_changed) and not hard_stop:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "loopback_forward_mutation_without_terminal_outcome_delta",
                "`loopback_audit` must not leave ladder forward mutation open without observed terminal outcome change or a hard stop.",
            )
        if forward_mutation_progress and not substance_delta_pass and not terminal_outcome_changed and not hard_stop:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "loopback_forward_mutation_without_substance_delta",
                "`loopback_audit` must not leave ladder forward mutation open without G-SUBSTANCE pass, strict terminal outcome delta, or a hard stop.",
            )
        if vacuous_corrective_noop and semantic_progress:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "loopback_vacuous_corrective_claimed_semantic_progress",
                "`loopback_audit` reported semantic_progress while G-VACUOUS found attempted corrective lanes with zero resolved items.",
            )
        if adapter_mandate_required and not hard_stop:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "loopback_adapter_mandate_without_hard_stop",
                "`loopback_audit` adapter_mandate_required=true must hard-stop ordinary domain repair and force adapter registration/strengthening or escalation.",
            )
        if adapter_wiring_defect and (adapter_mandate_required or disposition != "self_inflicted_gate_defect" or not hard_stop):
            add(
                findings,
                "block" if mode == "block" else "warn",
                "loopback_adapter_wiring_defect_misrouted",
                "`loopback_audit` must route a registered-but-unloaded adapter as self_inflicted_gate_defect, not adapter absence.",
            )
        if cumulative_chain_stalled and not adapter_mandate_required and not hard_stop:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "loopback_cumulative_chain_without_hard_stop",
                "`loopback_audit` cumulative goal-distance stall must hard-stop unless G-ADAPTER is the active preceding mandate.",
            )
        if (
            cumulative_chain_stalled
            and not adapter_mandate_required
            and chain_stall_cap > 0
            and chain_stall_streak >= chain_stall_cap * 2
            and blocker_mutation in {"facet_rename", "lateral", "repeat"}
        ):
            gate_present = isinstance(forced_retarget_gate, dict) and boolish(forced_retarget_gate.get("chain_stall_force_retarget"))
            options_present = isinstance(forced_retarget_options, list)
            if not gate_present or not options_present:
                add(
                    findings,
                    "block" if mode == "block" else "warn",
                    "loopback_chain_stall_forced_retarget_missing",
                    "`loopback_audit` must enumerate forced retarget alternatives when cumulative goal-distance stall reaches cap*2.",
                    {"cumulative_goal_distance_stall_streak": chain_stall_streak, "cumulative_goal_distance_stall_cap": chain_stall_cap},
                )
        if untried_veto_overridden and not cumulative_chain_stalled:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "loopback_untried_override_without_chain_stall",
                "`untried_veto_overridden_by_chain_stall` requires cumulative goal-distance stall evidence.",
            )
        if acceptance_unreachable and not boolish(value_for(result, "relaxation_or_escalation_required")):
            add(
                findings,
                "block" if mode == "block" else "warn",
                "loopback_unreachable_acceptance_without_relaxation_gate",
                "`acceptance_unreachable_under_frozen_config` requires `relaxation_or_escalation_required=true`.",
            )
        if unverifiable_acceptance and not hard_stop:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "loopback_unverifiable_acceptance_without_hard_stop",
                "`unverifiable_acceptance_contract=true` means a required live verifier was not evaluated; the packet must hard-stop target consumption.",
            )
        if metric_goal_productive_excluded and semantic_progress and measurement_progress_allowed:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "loopback_tautological_metric_claimed_progress",
                "Tautological oracle/metric validity must not support semantic or measurement goal-productive progress without independent output-delta evidence.",
            )
        if pass_with_coupled_verifier and (not hard_stop or disposition == "goal_productive"):
            add(
                findings,
                "block" if mode == "block" else "warn",
                "loopback_coupled_verifier_consumable_as_pass",
                "`loopback_audit` must treat pass_with_coupled_verifier as not-pass and hard-stop target consumption.",
            )
        if attested_only_movement and (primary_metric_high_water_moved or measurement_progress_allowed or disposition == "goal_productive"):
            add(
                findings,
                "block" if mode == "block" else "warn",
                "loopback_attested_only_movement_counted_as_progress",
                "`loopback_audit` must not let producer-attested movement update high-water, allow measurement progress, or route goal_productive.",
            )
        if (pass_with_unobserved_axes or non_empty(unobserved_goal_axes)) and (not hard_stop or disposition == "goal_productive"):
            add(
                findings,
                "block" if mode == "block" else "warn",
                "loopback_unobserved_axes_consumable_as_pass",
                "`loopback_audit` must treat pass_with_unobserved_axes as not-pass for measurable goals and hard-stop target consumption.",
                {"unobserved_goal_axes": unobserved_goal_axes or None},
            )
        if generation_dependent_count_key and not effective_count_key:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "loopback_generation_count_key_without_effective_key",
                "Generation-dependent count-key material is trace-only; loopback must emit an effective adapter-collapsed key or terminal-outcome fallback.",
            )
        if generation_dependent_count_key and generation_key_novelty_claim:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "loopback_generation_key_claimed_family_reset",
                "`loopback_audit` must not use task/advice/pack/cycle/run/date/hash/version key churn as family novelty, stall reset, hypothesis exhaustion, or seal escape.",
            )
        if residual_cost_below_policy and disposition == "goal_productive":
            add(
                findings,
                "block" if mode == "block" else "warn",
                "loopback_residual_cost_below_policy_goal_productive",
                "`loopback_audit` must not route below-policy residual value per cycle cost as ordinary goal_productive repair.",
            )
        if primary_metric_stalled and not hard_stop:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "loopback_primary_metric_stall_without_hard_stop",
                "`loopback_audit` primary_metric_stalled=true must hard-stop ordinary progress and route forced retargeting or user escalation.",
            )
        if c4_user_escalation and disposition != "user_escalation":
            add(
                findings,
                "block" if mode == "block" else "warn",
                "loopback_c4_user_escalation_misrouted",
                "`loopback_audit` C4 user-escalation backstop must route to user_escalation when no forced option is actionable.",
            )
        if (terminal_stage_contradiction or terminal_classification_invalid_for_counting) and (disposition == "goal_productive" or not hard_stop):
            add(
                findings,
                "block" if mode == "block" else "warn",
                "loopback_terminal_classification_stage_not_fail_closed",
                "`loopback_audit` contradictory terminal classification must be invalid for counting/close and hard-stop target consumption.",
            )
        if same_input_contract_violation and (disposition == "goal_productive" or not hard_stop):
            add(
                findings,
                "block" if mode == "block" else "warn",
                "loopback_same_input_contract_not_fail_closed",
                "`loopback_audit` same-condition input-set mismatch must hard-stop counting until the comparison contract is repaired.",
            )
        if instrumentation_supply_required and (disposition == "goal_productive" or not hard_stop):
            add(
                findings,
                "block" if mode == "block" else "warn",
                "loopback_instrumentation_supply_not_fail_closed",
                "`loopback_audit` repeated diagnostics_unavailable must force instrumentation supply or an explicit observability rationale, not ordinary goal_productive routing.",
            )
        if independent_source_status in {"missing", "overlap", "blocked"} and (primary_metric_high_water_moved or measurement_progress_allowed or disposition == "goal_productive"):
            add(
                findings,
                "block" if mode == "block" else "warn",
                "loopback_independent_verification_source_not_disjoint_counted",
                "`loopback_audit` must downgrade independently_verified evidence to attested when verification inputs are missing or overlap verified artifacts.",
                {"independent_source_separation_status": independent_source_status},
            )
        if independently_verified_downgraded_fields and (primary_metric_high_water_moved or measurement_progress_allowed or disposition == "goal_productive"):
            add(
                findings,
                "block" if mode == "block" else "warn",
                "loopback_downgraded_independent_verification_counted",
                "`loopback_audit` must not count auto-downgraded independently_verified fields as primary progress.",
                {"downgraded_fields": independently_verified_downgraded_fields},
            )
        if self_grounded_mislabeled_independent and (
            primary_metric_high_water_moved or measurement_progress_allowed or disposition == "goal_productive" or semantic_progress
        ):
            add(
                findings,
                "block" if mode == "block" else "warn",
                "loopback_self_grounded_counted_as_independent",
                "Self-grounded structural axes cannot remain in the independently-verified bucket or move semantic high-water.",
                {"axis_ids": self_grounded_mislabeled_independent},
            )
        if envelope_thaw_item_required and (disposition == "goal_productive" or not hard_stop or not non_empty(envelope_thaw_item)):
            add(
                findings,
                "block" if mode == "block" else "warn",
                "loopback_envelope_thaw_item_not_reserved",
                "`loopback_audit` must reserve an envelope_thaw_item and hard-stop when acceptance is unreachable under a frozen envelope.",
            )
        if (scenario_uncovered or acceptance_inversion) and (disposition == "goal_productive" or not hard_stop):
            add(
                findings,
                "block" if mode == "block" else "warn",
                "loopback_acceptance_scenario_not_fail_closed",
                "`loopback_audit` must fail closed on uncovered or inverted acceptance scenarios until scenario supply or code/contract repair is selected.",
            )
        if command_provenance_missing and (disposition == "goal_productive" or measurement_progress_allowed):
            add(
                findings,
                "block" if mode == "block" else "warn",
                "loopback_command_provenance_missing_counted",
                "`loopback_audit` must not count a missing-argv live run as baseline, comparison, A/B, reproduction, or measurement-progress evidence.",
            )
        if repeated_blocker_opacity and disposition == "goal_productive":
            add(
                findings,
                "block" if mode == "block" else "warn",
                "loopback_repeated_blocker_opacity_goal_productive",
                "`loopback_audit` must route repeated same-gate blocker_opacity to blocker-contract repair instead of ordinary goal_productive work.",
            )
        if (predetermined_unreachable or floor_edge_envelope) and (disposition == "goal_productive" or not hard_stop):
            add(
                findings,
                "block" if mode == "block" else "warn",
                "loopback_stochastic_contract_infeasible_not_fail_closed",
                "`loopback_audit` must treat exact-match and floor-edge stochastic findings as contract-revision blockers, not retryable goal_productive progress.",
            )
        if instrumentation_first_fire and not non_empty(first_fire_consumed_item_id):
            add(
                findings,
                "block" if mode == "block" else "warn",
                "loopback_first_fire_without_consumed_item",
                "`loopback_audit` must attach instrumentation_first_fire to exactly one consumed workflow item.",
            )
        if instrumentation_first_fire and first_fire_double_counted:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "loopback_first_fire_double_counted",
                "`loopback_audit` must not double-count instrumentation_first_fire as both first-fire evidence and goal progress or instrumentation-supply consumption.",
            )
