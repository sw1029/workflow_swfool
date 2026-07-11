from __future__ import annotations

from ..base import RuleContext, TargetContractRule
from ..common import (
    ADOPTION_AXIS_TASK_KINDS,
    BLOCKER_CONTRACT_REPAIR_TASK_KINDS,
    CLASSIFICATION_REPAIR_TASK_KINDS,
    COLLECTION_CONSUMPTION_TASK_KINDS,
    COMMAND_PROVENANCE_TASK_KINDS,
    CONTRACT_SATISFIABILITY_TASK_KINDS,
    CURRENT_LANE_TASK_KINDS,
    CYCLE_REACHABILITY_TASK_KINDS,
    DECISION_FRESHNESS_TASK_KINDS,
    ENVELOPE_THAW_TASK_KINDS,
    EXPECTATION_REBASELINE_TASK_KINDS,
    HARVEST_GATE_TASK_KINDS,
    INSTRUMENTATION_TASK_KINDS,
    METRIC_BASIS_TASK_KINDS,
    PACK_DISPOSITIONS,
    PACK_MUTATION_DISPOSITIONS,
    PARITY_AXIS_TASK_KINDS,
    PORTFOLIO_QUOTA_TASK_KINDS,
    PRODUCER_SUPPLY_TASK_KINDS,
    REHARVEST_TASK_KINDS,
    REPORT_KEY_REPAIR_TASK_KINDS,
    RESOLUTION_REPAIR_TASK_KINDS,
    SCENARIO_REPAIR_TASK_KINDS,
    SCENARIO_SUPPLY_TASK_KINDS,
    STOCHASTIC_CONTRACT_TASK_KINDS,
    SURFACE_FIELD_TASK_KINDS,
    active_task_pack_present,
    add,
    advice_handling_rationale_present,
    allowed_task_kinds_from_basis,
    boolish,
    first_present,
    float_value,
    forced_task_kind,
    has_value,
    list_values,
    non_empty,
    nonzero_scalar,
    number_value,
    selected_disposition,
    selected_task_kind_value,
    task_pack_in_scope,
    value_for,
)


class DeriveRule(TargetContractRule):
    """Validate next-task selection against active routing and evidence gates."""

    targets = frozenset({'derive'})

    def check(self, context: RuleContext) -> None:
        result = context.result
        mode = context.mode
        findings = context.findings
        require_context_field = context.require_context_field
        explicit_report_key_divergence = context.get("explicit_report_key_divergence", False)
        auto_report_key_divergences = context.get("auto_report_key_divergences", [])
        pending_long_runs = context.get("pending_long_runs", [])
        pending_selected_kind = selected_task_kind_value(result)
        pending_selected_source = str(value_for(result, "selected_task_source") or "").strip().lower()
        pending_allowed_kinds = {
            "long_run_monitor",
            "long_run_harvest",
            "long_run_finalize",
            "terminal_blocked",
            "terminal_blocker",
            "user_escalation",
        }
        derive_mode = str(first_present(result, ["derive_mode", "mode", "derive.mode", "result.derive_mode"]) or "").strip().lower()
        ordinary_derive = derive_mode != "initial_init" and not (
            pending_selected_kind in pending_allowed_kinds or pending_selected_source == "terminal_blocked"
        )
        if ordinary_derive and not context.get("long_run_state_checked", False):
            add(
                findings,
                "block",
                "long_run_state_not_checked",
                "Ordinary derivation requires explicit proof that current long-run state was checked.",
            )
        if pending_long_runs and ordinary_derive:
            add(
                findings,
                "block",
                "pending_long_run_ordinary_derive",
                "Pending long-running execution permits only monitor/harvest/finalize or terminal/user-escalation derivation.",
                {
                    "pending_long_runs": pending_long_runs,
                    "selected_task_kind": pending_selected_kind or None,
                    "selected_task_source": pending_selected_source or None,
                },
            )
        status = str(value_for(result, "status") or "").lower()
        if status in {"deferred", "pending", "blocked", "failed"} and not has_value(result, "derive_pending_reason") and not has_value(result, "blockers"):
            add(findings, "block" if mode == "block" else "warn", "derive_pending_reason_missing", "Deferred or blocked derivation requires a pending/blocker reason.")
        selected_source = str(value_for(result, "selected_task_source") or "").lower()
        pack_disposition = str(
            first_present(
                result,
                [
                    "pack_disposition",
                    "derive.pack_disposition",
                    "result.pack_disposition",
                    "task_pack_packet.pack_disposition",
                    "task_pack.disposition",
                ],
            )
            or ""
        ).lower()
        pack_scope = task_pack_in_scope(result) or bool(pack_disposition)
        if active_task_pack_present(result) and selected_source != "task_pack" and not has_value(result, "task_pack_status"):
            add(findings, "block" if mode == "block" else "warn", "task_pack_status_missing", "Active task pack in scope requires `task_pack_status` in derive result.")
        if pack_scope and not pack_disposition:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "pack_disposition_missing",
                "`derive` with task-pack scope requires exactly one `pack_disposition`.",
                {"allowed": sorted(PACK_DISPOSITIONS)},
            )
        if pack_disposition and pack_disposition not in PACK_DISPOSITIONS:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "pack_disposition_invalid",
                "`pack_disposition` is not an allowed task-pack transaction.",
                {"pack_disposition": pack_disposition, "allowed": sorted(PACK_DISPOSITIONS)},
            )
        if selected_source and selected_source not in {"task_pack", "candidate_task", "standalone", "terminal_blocked"}:
            add(findings, "warn", "selected_task_source_invalid", "`selected_task_source` should be task_pack, candidate_task, standalone, or terminal_blocked.", {"selected_task_source": selected_source})
        if selected_source == "task_pack":
            require_context_field("task_pack_status", "task_pack_status_missing", "`selected_task_source: task_pack` requires `task_pack_status`.")
            require_context_field("task_pack_path", "task_pack_path_missing", "`selected_task_source: task_pack` requires `task_pack_path`.")
            require_context_field("task_pack_item_id", "task_pack_item_id_missing", "`selected_task_source: task_pack` requires `task_pack_item_id` or `promoted_item_id`.")
            require_context_field("pack_disposition", "pack_disposition_missing", "`selected_task_source: task_pack` requires `pack_disposition`.")
        if pack_disposition in PACK_MUTATION_DISPOSITIONS:
            require_context_field("pack_mutation_plan", "pack_mutation_plan_missing", "Pack mutation dispositions require `pack_mutation_plan`.")
            require_context_field("task_pack_path", "task_pack_path_missing", "Pack mutation dispositions require `task_pack_path`.")
            require_context_field("task_pack_render_path", "task_pack_render_path_missing", "Pack mutation dispositions require a refreshed Markdown render path.")
            if not has_value(result, "pack_mutation_log") and not has_value(result, "pack_mutation_plan"):
                add(
                    findings,
                    "block" if mode == "block" else "warn",
                    "pack_mutation_evidence_missing",
                    "Pack mutation dispositions should carry mutation-log evidence or a durable mutation plan.",
                )
        if pack_disposition in {"skip_items", "exclude_items"}:
            require_context_field("skipped_item_ids", "skipped_item_ids_missing", "Skipping/excluding pack items requires `skipped_item_ids` or `exclude_item_ids`.")
        if pack_disposition == "derive_standalone":
            require_context_field("derive_standalone_rationale", "derive_standalone_rationale_missing", "`derive_standalone` with an active pack requires a rationale.")
        if pack_disposition == "terminal_blocked" and selected_source not in {"", "terminal_blocked"}:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "pack_terminal_selected_source_mismatch",
                "`pack_disposition: terminal_blocked` should use `selected_task_source: terminal_blocked`.",
                {"selected_task_source": selected_source},
            )
        if selected_source == "terminal_blocked" and not has_value(result, "terminal_blocker"):
            add(findings, "block", "terminal_blocker_missing", "`selected_task_source: terminal_blocked` requires `terminal_blocker`.")
        if selected_source == "terminal_blocked" and not has_value(result, "semantic_signature"):
            add(findings, "block" if mode == "block" else "warn", "terminal_semantic_signature_missing", "`selected_task_source: terminal_blocked` should include `semantic_signature` so the family can be sealed.")
        if selected_source != "terminal_blocked" and not has_value(result, "next_task_id"):
            add(findings, "block" if mode == "block" else "warn", "next_task_id_missing", "Non-terminal derive result requires `next_task_id`.")
        progress_kind = str(
            first_present(
                result,
                [
                    "progress_kind",
                    "selected_progress_kind",
                    "expected_progress_kind",
                    "derive.progress_kind",
                    "derive.selected_progress_kind",
                    "result.progress_kind",
                    "result.selected_progress_kind",
                ],
            )
            or ""
        ).lower()
        if progress_kind and progress_kind not in {"goal_productive", "governance_only"}:
            add(findings, "warn", "progress_kind_invalid", "`derive` progress_kind should be `goal_productive` or `governance_only`.", {"progress_kind": progress_kind})
        if progress_kind == "governance_only" and selected_source != "terminal_blocked":
            add(
                findings,
                "warn",
                "derive_governance_only_selected",
                "`derive` selected a governance-only task; ensure this is not another sidecar/narrowing loop.",
            )
        effective_allowed = list_values(
            first_present(
                result,
                [
                    "effective_allowed_dispositions",
                    "anti_loop_progress_gate.effective_allowed_dispositions",
                    "loop_breaker_packet.effective_allowed_dispositions",
                    "result.anti_loop_progress_gate.effective_allowed_dispositions",
                    "result.loop_breaker_packet.effective_allowed_dispositions",
                ],
            )
        )
        if effective_allowed:
            disposition = selected_disposition(result, selected_source, progress_kind)
            if disposition and disposition not in {item.lower() for item in effective_allowed}:
                add(
                    findings,
                    "block" if mode == "block" else "warn",
                    "disposition_not_effectively_allowed",
                    "Derive selected a disposition outside `effective_allowed_dispositions`; active gates must be consumed as an intersection, not a union.",
                    {"selected_disposition": disposition, "effective_allowed_dispositions": effective_allowed},
                )
        disposition_basis = first_present(
            result,
            [
                "disposition_intersection_basis",
                "anti_loop_progress_gate.disposition_intersection_basis",
                "loop_breaker_packet.disposition_intersection_basis",
                "result.anti_loop_progress_gate.disposition_intersection_basis",
                "result.loop_breaker_packet.disposition_intersection_basis",
            ],
        )
        allowed_task_kinds = allowed_task_kinds_from_basis(disposition_basis)
        selected_kind = selected_task_kind_value(result)
        terminal_selected = selected_source == "terminal_blocked" or has_value(result, "terminal_blocker")
        scenario_uncovered = boolish(
            first_present(
                result,
                [
                    "scenario_uncovered",
                    "acceptance_scenario_gate.scenario_uncovered",
                    "anti_loop_progress_gate.scenario_uncovered",
                    "result.anti_loop_progress_gate.acceptance_scenario_gate.scenario_uncovered",
                ],
            )
        )
        acceptance_inversion = boolish(
            first_present(
                result,
                [
                    "acceptance_inversion",
                    "acceptance_inversion_candidate",
                    "acceptance_scenario_gate.acceptance_inversion",
                    "anti_loop_progress_gate.acceptance_inversion",
                    "result.anti_loop_progress_gate.acceptance_scenario_gate.acceptance_inversion",
                ],
            )
        )
        command_provenance_missing = boolish(
            first_present(
                result,
                [
                    "command_provenance_missing",
                    "command_provenance_gate.command_provenance_missing",
                    "anti_loop_progress_gate.command_provenance_missing",
                    "result.anti_loop_progress_gate.command_provenance_gate.command_provenance_missing",
                ],
            )
        )
        repeated_blocker_opacity = boolish(
            first_present(
                result,
                [
                    "repeated_blocker_opacity",
                    "blocker_opacity_repeated",
                    "blocker_actionability_gate.repeated_blocker_opacity",
                    "anti_loop_progress_gate.repeated_blocker_opacity",
                    "result.anti_loop_progress_gate.blocker_actionability_gate.repeated_blocker_opacity",
                ],
            )
        )
        authorization_contract_repair_candidate = boolish(
            first_present(
                result,
                [
                    "authorization_contract_repair_candidate",
                    "blocker_actionability_gate.authorization_contract_repair_candidate",
                    "anti_loop_progress_gate.authorization_contract_repair_candidate",
                    "result.anti_loop_progress_gate.blocker_actionability_gate.authorization_contract_repair_candidate",
                ],
            )
        )
        stochastic_contract_infeasible = boolish(
            first_present(
                result,
                [
                    "predetermined_unreachable",
                    "floor_edge_envelope",
                    "stochastic_feasibility_gate.predetermined_unreachable",
                    "stochastic_feasibility_gate.floor_edge_envelope",
                    "anti_loop_progress_gate.predetermined_unreachable",
                    "anti_loop_progress_gate.floor_edge_envelope",
                    "result.anti_loop_progress_gate.stochastic_feasibility_gate.predetermined_unreachable",
                    "result.anti_loop_progress_gate.stochastic_feasibility_gate.floor_edge_envelope",
                ],
            )
        )
        if scenario_uncovered and not terminal_selected and selected_kind not in SCENARIO_SUPPLY_TASK_KINDS:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "derive_scenario_uncovered_unhandled",
                "`derive` must route scenario_uncovered to validation-set planning, fixture supply, live-run supply, terminal state, or user escalation.",
                {"selected_task_kind": selected_kind or None},
            )
        if acceptance_inversion and not terminal_selected and selected_kind not in SCENARIO_REPAIR_TASK_KINDS:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "derive_acceptance_inversion_unhandled",
                "`derive` must route acceptance_inversion to code or acceptance/test contract repair, not another green-test confirmation task.",
                {"selected_task_kind": selected_kind or None},
            )
        if command_provenance_missing and not terminal_selected and selected_kind not in COMMAND_PROVENANCE_TASK_KINDS:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "derive_command_provenance_missing_unhandled",
                "`derive` must repair or rerun missing command provenance before using that run for baseline, comparison, A/B, or reproduction evidence.",
                {"selected_task_kind": selected_kind or None},
            )
        if (repeated_blocker_opacity or authorization_contract_repair_candidate) and not terminal_selected and selected_kind not in BLOCKER_CONTRACT_REPAIR_TASK_KINDS:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "derive_repeated_blocker_opacity_unhandled",
                "`derive` must route repeated same-gate blocker_opacity or hidden multi-input authorization contracts to blocker/gate contract repair or terminal/user escalation.",
                {"selected_task_kind": selected_kind or None},
            )
        if stochastic_contract_infeasible and not terminal_selected and selected_kind not in STOCHASTIC_CONTRACT_TASK_KINDS:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "derive_stochastic_contract_infeasible_unhandled",
                "`derive` must route predetermined_unreachable or floor_edge_envelope to contract revision, envelope expansion, residual descope, terminal state, or user escalation rather than retry.",
                {"selected_task_kind": selected_kind or None},
            )
        expectation_lineage_stale = boolish(
            first_present(
                result,
                [
                    "expectation_lineage_stale",
                    "expectation_lineage_gate.expectation_lineage_stale",
                    "anti_loop_progress_gate.expectation_lineage_stale",
                    "result.anti_loop_progress_gate.expectation_lineage_gate.expectation_lineage_stale",
                ],
            )
        )
        expectation_anchor_missing = boolish(
            first_present(
                result,
                [
                    "expectation_anchor_missing",
                    "expectation_lineage_gate.expectation_anchor_missing",
                    "anti_loop_progress_gate.expectation_anchor_missing",
                    "result.anti_loop_progress_gate.expectation_lineage_gate.expectation_anchor_missing",
                ],
            )
        )
        parity_unverified = boolish(
            first_present(
                result,
                [
                    "parity_unverified",
                    "comparison_parity_gate.parity_unverified",
                    "anti_loop_progress_gate.parity_unverified",
                    "result.anti_loop_progress_gate.comparison_parity_gate.parity_unverified",
                ],
            )
        )
        unknown_parity_axes = boolish(
            first_present(
                result,
                [
                    "unknown_parity_axes",
                    "comparison_parity_gate.unknown_parity_axes",
                    "anti_loop_progress_gate.unknown_parity_axes",
                    "result.anti_loop_progress_gate.comparison_parity_gate.unknown_parity_axes",
                ],
            )
        )
        majority_vote_adoption = boolish(
            first_present(
                result,
                [
                    "majority_vote_adoption",
                    "adoption_axis_gate.majority_vote_adoption",
                    "anti_loop_progress_gate.majority_vote_adoption",
                    "result.anti_loop_progress_gate.adoption_axis_gate.majority_vote_adoption",
                ],
            )
        )
        adoption_axis_classification = first_present(
            result,
            [
                "adoption_axis_classification",
                "adoption_axis_gate.adoption_axis_classification",
                "anti_loop_progress_gate.adoption_axis_classification",
                "result.anti_loop_progress_gate.adoption_axis_gate.adoption_axis_classification",
            ],
        )
        measured_but_disqualified = boolish(
            first_present(
                result,
                [
                    "measured_but_disqualified",
                    "adoption_axis_gate.measured_but_disqualified",
                    "anti_loop_progress_gate.measured_but_disqualified",
                    "result.anti_loop_progress_gate.adoption_axis_gate.measured_but_disqualified",
                ],
            )
        )
        failed_gating_axis = boolish(
            first_present(
                result,
                [
                    "failed_gating_axis",
                    "adoption_axis_gate.failed_gating_axis",
                    "anti_loop_progress_gate.failed_gating_axis",
                    "result.anti_loop_progress_gate.adoption_axis_gate.failed_gating_axis",
                ],
            )
        )
        resolution_downgrade = boolish(
            first_present(
                result,
                [
                    "resolution_downgrade",
                    "resolution_downgrade_gate.resolution_downgrade",
                    "anti_loop_progress_gate.resolution_downgrade",
                    "result.anti_loop_progress_gate.resolution_downgrade_gate.resolution_downgrade",
                ],
            )
        )
        repeated_resolution_downgrade = boolish(
            first_present(
                result,
                [
                    "repeated_resolution_downgrade",
                    "resolution_downgrade_gate.repeated_resolution_downgrade",
                    "anti_loop_progress_gate.repeated_resolution_downgrade",
                    "result.anti_loop_progress_gate.resolution_downgrade_gate.repeated_resolution_downgrade",
                ],
            )
        )
        if expectation_lineage_stale and not terminal_selected and selected_kind not in EXPECTATION_REBASELINE_TASK_KINDS:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "derive_expectation_lineage_stale_unhandled",
                "`derive` must route stale output-derived expectations to rebaseline, explicit residual descope, terminal state, or user escalation before dependent live execution.",
                {"selected_task_kind": selected_kind or None},
            )
        if expectation_anchor_missing and not expectation_lineage_stale and progress_kind == "goal_productive" and selected_kind not in EXPECTATION_REBASELINE_TASK_KINDS:
            add(
                findings,
                "warn",
                "derive_expectation_anchor_missing_unhandled",
                "`derive` selected goal_productive work with an output-derived expectation missing an anchor; ensure the task does not claim lineage-verified expectation evidence.",
                {"selected_task_kind": selected_kind or None},
            )
        if (parity_unverified or unknown_parity_axes) and not terminal_selected and selected_kind not in PARITY_AXIS_TASK_KINDS:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "derive_parity_unverified_unhandled",
                "`derive` must route parity-unverified comparison/adoption to axis resolution, provisional comparison, residual descope, terminal state, or user escalation.",
                {"selected_task_kind": selected_kind or None},
            )
        if majority_vote_adoption and not non_empty(adoption_axis_classification) and not terminal_selected and selected_kind not in ADOPTION_AXIS_TASK_KINDS:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "derive_majority_vote_adoption_unhandled",
                "`derive` must not finalize majority-vote adoption without gating/tradable axis classification.",
                {"selected_task_kind": selected_kind or None},
            )
        if (measured_but_disqualified or failed_gating_axis) and not terminal_selected and selected_kind not in ADOPTION_AXIS_TASK_KINDS:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "derive_gating_axis_failure_unhandled",
                "`derive` must not promote a candidate with failed gating axes; preserve measured_but_disqualified evidence or route gating-axis repair/contract revision.",
                {"selected_task_kind": selected_kind or None},
            )
        if repeated_resolution_downgrade and not terminal_selected and selected_kind not in RESOLUTION_REPAIR_TASK_KINDS:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "derive_resolution_downgrade_unhandled",
                "`derive` must route repeated same-contract resolution_downgrade to resolution restoration, contract revision, residual descope, terminal state, or user escalation.",
                {"selected_task_kind": selected_kind or None},
            )
        if resolution_downgrade and not repeated_resolution_downgrade and progress_kind == "goal_productive":
            add(
                findings,
                "warn",
                "derive_resolution_downgrade_goal_productive",
                "`derive` selected goal_productive work while evidence resolution is downgraded; keep the decision provisional or preserve residual high-resolution scope.",
                {"selected_task_kind": selected_kind or None},
            )
        if (explicit_report_key_divergence or auto_report_key_divergences) and not terminal_selected and selected_kind not in REPORT_KEY_REPAIR_TASK_KINDS:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "derive_report_key_divergence_unhandled",
                "`derive` must route report_key_divergence to report/schema/sync repair, terminal state, or user escalation before consuming that report.",
                {"selected_task_kind": selected_kind or None},
            )
        pass_on_stale_lane = boolish(
            first_present(
                result,
                [
                    "pass_on_stale_lane",
                    "lane_identity_gate.pass_on_stale_lane",
                    "anti_loop_progress_gate.pass_on_stale_lane",
                    "anti_loop_progress_gate.lane_identity_gate.pass_on_stale_lane",
                    "result.anti_loop_progress_gate.pass_on_stale_lane",
                    "result.lane_identity_gate.pass_on_stale_lane",
                ],
            )
        )
        decision_metadata_revision = boolish(
            first_present(
                result,
                [
                    "decision_metadata_revision",
                    "stale_measurement_artifact",
                    "decision_freshness_gate.decision_metadata_revision",
                    "decision_freshness_gate.stale_measurement_artifact",
                    "anti_loop_progress_gate.decision_metadata_revision",
                    "anti_loop_progress_gate.stale_measurement_artifact",
                    "result.decision_freshness_gate.decision_metadata_revision",
                ],
            )
        )
        axis_starved_by_missing_producer = boolish(
            first_present(
                result,
                [
                    "axis_starved_by_missing_producer",
                    "gating_axis_producer_gate.axis_starved_by_missing_producer",
                    "anti_loop_progress_gate.axis_starved_by_missing_producer",
                    "anti_loop_progress_gate.gating_axis_producer_gate.axis_starved_by_missing_producer",
                    "result.gating_axis_producer_gate.axis_starved_by_missing_producer",
                ],
            )
        )
        portfolio_quota_exceeded = boolish(
            first_present(
                result,
                [
                    "portfolio_quota_exceeded",
                    "portfolio_quota_gate.portfolio_quota_exceeded",
                    "anti_loop_progress_gate.portfolio_quota_exceeded",
                    "anti_loop_progress_gate.portfolio_quota_gate.portfolio_quota_exceeded",
                    "result.portfolio_quota_gate.portfolio_quota_exceeded",
                ],
            )
        )
        portfolio_quota_mode = str(
            first_present(
                result,
                [
                    "portfolio_quota_mode",
                    "portfolio_quota_gate.portfolio_quota_mode",
                    "portfolio_quota_gate.mode",
                    "anti_loop_progress_gate.portfolio_quota_mode",
                    "anti_loop_progress_gate.portfolio_quota_gate.mode",
                    "result.portfolio_quota_gate.portfolio_quota_mode",
                ],
            )
            or ""
        ).lower()
        portfolio_quota_restrictive = portfolio_quota_mode in {"restrict", "restricted", "block", "blocking"}
        unreachable_within_cycle = boolish(
            first_present(
                result,
                [
                    "unreachable_within_cycle",
                    "cycle_reachability_gate.unreachable_within_cycle",
                    "acceptance_reachability_gate.unreachable_within_cycle",
                    "anti_loop_progress_gate.unreachable_within_cycle",
                    "anti_loop_progress_gate.cycle_reachability_gate.unreachable_within_cycle",
                    "result.cycle_reachability_gate.unreachable_within_cycle",
                ],
            )
        )
        basis_overclaim = boolish(
            first_present(
                result,
                [
                    "basis_overclaim",
                    "metric_basis_gate.basis_overclaim",
                    "anti_loop_progress_gate.basis_overclaim",
                    "anti_loop_progress_gate.metric_basis_gate.basis_overclaim",
                    "result.metric_basis_gate.basis_overclaim",
                ],
            )
        )
        surface_field_defect_matrix = first_present(
            result,
            [
                "surface_field_defect_matrix",
                "surface_field_review_gate.surface_field_defect_matrix",
                "qualitative_review_packet.surface_field_defect_matrix",
                "anti_loop_progress_gate.surface_field_defect_matrix",
                "result.surface_field_review_gate.surface_field_defect_matrix",
            ],
        )
        surface_field_defects = nonzero_scalar(surface_field_defect_matrix)
        if pass_on_stale_lane and not terminal_selected and selected_kind not in CURRENT_LANE_TASK_KINDS:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "derive_pass_on_stale_lane_unhandled",
                "`derive` must route pass_on_stale_lane to current-lane rerun/revalidation, residual descope, terminal state, or user escalation before consuming the pass.",
                {"selected_task_kind": selected_kind or None},
            )
        if decision_metadata_revision and not terminal_selected and selected_kind not in DECISION_FRESHNESS_TASK_KINDS:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "derive_decision_metadata_revision_unhandled",
                "`derive` must route stale decision updates to fresh current-lane measurement, no-impact proof, residual descope, terminal state, or user escalation.",
                {"selected_task_kind": selected_kind or None},
            )
        if axis_starved_by_missing_producer and not terminal_selected and selected_kind not in PRODUCER_SUPPLY_TASK_KINDS:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "derive_axis_starved_by_missing_producer_unhandled",
                "`derive` must route a producer-starved gating axis to producer-supply work before another verifier, guard, report, or metadata task can count as progress.",
                {"selected_task_kind": selected_kind or None},
            )
        if portfolio_quota_exceeded and portfolio_quota_restrictive and not terminal_selected and selected_kind not in PORTFOLIO_QUOTA_TASK_KINDS:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "derive_portfolio_quota_restriction_unhandled",
                "`derive` must honor restrictive portfolio_quota_exceeded by selecting producer, envelope, long-run, descope, terminal, or escalation work.",
                {"selected_task_kind": selected_kind or None},
            )
        elif portfolio_quota_exceeded and not portfolio_quota_restrictive:
            add(
                findings,
                "warn",
                "derive_portfolio_quota_warn_only",
                "`portfolio_quota_exceeded` is warn-only unless the adapter supplies restrict mode; preserve it without restricting selection.",
                {"portfolio_quota_mode": portfolio_quota_mode or None},
            )
        if unreachable_within_cycle and not terminal_selected and selected_kind not in CYCLE_REACHABILITY_TASK_KINDS:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "derive_unreachable_within_cycle_unhandled",
                "`derive` must route unreachable_within_cycle to long-run launch/monitor/harvest, throughput improvement, descope, terminal state, or user escalation.",
                {"selected_task_kind": selected_kind or None},
            )
        if basis_overclaim and not terminal_selected and selected_kind not in METRIC_BASIS_TASK_KINDS:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "derive_basis_overclaim_unhandled",
                "`derive` must route basis_overclaim to basis-compatible measurement, metric-basis repair, downgrade-aware contract work, residual descope, terminal state, or user escalation.",
                {"selected_task_kind": selected_kind or None},
            )
        if surface_field_defects and not terminal_selected and selected_kind not in SURFACE_FIELD_TASK_KINDS:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "derive_surface_field_defects_unhandled",
                "`derive` must route nonzero surface_field_defect_matrix to producer/field repair, residual descope, terminal state, or user escalation before consuming the review pass.",
                {"selected_task_kind": selected_kind or None},
            )
        harvest_gate_unaudited = boolish(
            first_present(
                result,
                [
                    "harvest_gate_unaudited",
                    "harvest_contract_preflight.harvest_gate_unaudited",
                    "harvest_contract_preflight_gate.harvest_gate_unaudited",
                    "anti_loop_progress_gate.harvest_gate_unaudited",
                    "anti_loop_progress_gate.harvest_contract_preflight.harvest_gate_unaudited",
                    "result.harvest_contract_preflight_gate.harvest_gate_unaudited",
                ],
            )
        )
        harvest_preflight_required = boolish(
            first_present(
                result,
                [
                    "harvest_preflight_required",
                    "harvest_contract_preflight.required",
                    "harvest_contract_preflight_gate.required",
                    "acceptance.harvest_preflight_required",
                    "result.harvest_contract_preflight_gate.required",
                ],
            )
        )
        harvest_risk_accepted = boolish(
            first_present(
                result,
                [
                    "harvest_risk_accepted",
                    "harvest_contract_preflight.harvest_risk_accepted",
                    "harvest_contract_preflight_gate.harvest_risk_accepted",
                    "anti_loop_progress_gate.harvest_risk_accepted",
                    "result.harvest_contract_preflight_gate.harvest_risk_accepted",
                ],
            )
        )
        harvest_preflight_incompatible = any(
            boolish(
                first_present(
                    result,
                    [
                        field,
                        f"harvest_contract_preflight.{field}",
                        f"harvest_contract_preflight_gate.{field}",
                        f"anti_loop_progress_gate.{field}",
                        f"anti_loop_progress_gate.harvest_contract_preflight.{field}",
                        f"result.harvest_contract_preflight_gate.{field}",
                    ],
                )
            )
            for field in ("lane_incompatible", "scale_incompatible", "contract_conflict")
        )
        if harvest_gate_unaudited and harvest_preflight_required and selected_kind in {"long_run_launch", "long_run_harvest"}:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "derive_required_harvest_preflight_unaudited",
                "`derive` cannot silently select long-run launch/harvest when a required harvest preflight is unaudited; supply the inventory, record explicit risk acceptance, or choose terminal/user escalation.",
                {"selected_task_kind": selected_kind or None},
            )
        elif harvest_gate_unaudited:
            add(
                findings,
                "warn",
                "derive_harvest_gate_unaudited",
                "`harvest_gate_unaudited` is fail-quiet warning evidence; preserve it without inventing repository-specific harvest checks.",
            )
        if harvest_preflight_incompatible and not harvest_risk_accepted and not terminal_selected and selected_kind not in HARVEST_GATE_TASK_KINDS:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "derive_harvest_preflight_incompatible_unhandled",
                "`derive` must route non-degradable harvest-gate incompatibility to repair/mitigation before long-run launch unless `harvest_risk_accepted=true` is explicit.",
                {"selected_task_kind": selected_kind or None},
            )
        high_cost_artifact = boolish(
            first_present(
                result,
                [
                    "high_cost_artifact",
                    "disposal_proportionality_gate.high_cost_artifact",
                    "run_disposition_gate.high_cost_artifact",
                    "anti_loop_progress_gate.high_cost_artifact",
                    "result.disposal_proportionality_gate.high_cost_artifact",
                ],
            )
        )
        destructive_disposition_requested = boolish(
            first_present(
                result,
                [
                    "destructive_disposition_requested",
                    "destructive_disposition",
                    "disposal_proportionality_gate.destructive_disposition_requested",
                    "run_disposition_gate.destructive_disposition_requested",
                    "result.disposal_proportionality_gate.destructive_disposition_requested",
                ],
            )
        )
        destructive_disposition_blocked = boolish(
            first_present(
                result,
                [
                    "destructive_disposition_blocked",
                    "disposal_proportionality_gate.destructive_disposition_blocked",
                    "anti_loop_progress_gate.destructive_disposition_blocked",
                    "result.disposal_proportionality_gate.destructive_disposition_blocked",
                ],
            )
        )
        safety_violation = boolish(
            first_present(
                result,
                [
                    "safety_violation",
                    "safety_policy_violation",
                    "disposal_proportionality_gate.safety_violation",
                    "run_disposition_gate.safety_violation",
                ],
            )
        )
        reharvest_required = boolish(
            first_present(
                result,
                [
                    "reharvest_before_rerun_required",
                    "disposal_proportionality_gate.reharvest_before_rerun_required",
                    "anti_loop_progress_gate.reharvest_before_rerun_required",
                    "result.disposal_proportionality_gate.reharvest_before_rerun_required",
                ],
            )
        )
        rerun_before_reharvest = boolish(
            first_present(
                result,
                [
                    "rerun_before_reharvest",
                    "disposal_proportionality_gate.rerun_before_reharvest",
                    "anti_loop_progress_gate.rerun_before_reharvest",
                    "result.disposal_proportionality_gate.rerun_before_reharvest",
                ],
            )
        )
        destructive_high_cost = (destructive_disposition_blocked or (high_cost_artifact and destructive_disposition_requested)) and not safety_violation
        if (destructive_high_cost or reharvest_required or rerun_before_reharvest) and not terminal_selected and selected_kind not in REHARVEST_TASK_KINDS:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "derive_reharvest_or_quarantine_unhandled",
                "`derive` must preserve high-cost non-safety artifacts through quarantine and route available reharvest or gate repair before a new full rerun.",
                {"selected_task_kind": selected_kind or None},
            )
        mutually_unsatisfiable_contract = boolish(
            first_present(
                result,
                [
                    "mutually_unsatisfiable_contract",
                    "contract_satisfiability_gate.mutually_unsatisfiable_contract",
                    "validation_predicate_contract.mutually_unsatisfiable_contract",
                    "anti_loop_progress_gate.mutually_unsatisfiable_contract",
                    "result.contract_satisfiability_gate.mutually_unsatisfiable_contract",
                ],
            )
        )
        if mutually_unsatisfiable_contract and not terminal_selected and selected_kind not in CONTRACT_SATISFIABILITY_TASK_KINDS:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "derive_mutually_unsatisfiable_contract_unhandled",
                "`derive` must reconcile predicate/directive contracts, preserve residual scope, terminal-block, or user-escalate before consuming either side as valid.",
                {"selected_task_kind": selected_kind or None},
            )
        sample_as_universe_misuse = boolish(
            first_present(
                result,
                [
                    "sample_as_universe_misuse",
                    "collection_consumption_gate.sample_as_universe_misuse",
                    "closed_world_collection_consumption.sample_as_universe_misuse",
                    "anti_loop_progress_gate.sample_as_universe_misuse",
                    "result.collection_consumption_gate.sample_as_universe_misuse",
                ],
            )
        )
        if sample_as_universe_misuse and not terminal_selected and selected_kind not in COLLECTION_CONSUMPTION_TASK_KINDS:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "derive_sample_as_universe_misuse_unhandled",
                "`derive` must supply a full untruncated collection or revise the consumer to sample-only consistency before pass/close consumption.",
                {"selected_task_kind": selected_kind or None},
            )
        terminal_stage_contradiction = boolish(
            first_present(
                result,
                [
                    "terminal_classification_stage_contradiction",
                    "failure_surface_stage_gate.terminal_classification_stage_contradiction",
                    "anti_loop_progress_gate.terminal_classification_stage_contradiction",
                    "anti_loop_progress_gate.failure_surface_stage_gate.terminal_classification_stage_contradiction",
                    "loopback_audit.terminal_classification_stage_contradiction",
                    "result.anti_loop_progress_gate.terminal_classification_stage_contradiction",
                ],
            )
        )
        terminal_classification_invalid_for_counting = boolish(
            first_present(
                result,
                [
                    "terminal_classification_invalid_for_counting",
                    "failure_surface_stage_gate.terminal_classification_invalid_for_counting",
                    "anti_loop_progress_gate.terminal_classification_invalid_for_counting",
                    "result.anti_loop_progress_gate.terminal_classification_invalid_for_counting",
                ],
            )
        )
        same_input_contract_violation = boolish(
            first_present(
                result,
                [
                    "same_input_contract_violation",
                    "same_input_contract_gate.same_input_contract_violation",
                    "anti_loop_progress_gate.same_input_contract_violation",
                    "anti_loop_progress_gate.same_input_contract_gate.same_input_contract_violation",
                    "result.anti_loop_progress_gate.same_input_contract_violation",
                ],
            )
        )
        instrumentation_supply_required = boolish(
            first_present(
                result,
                [
                    "instrumentation_supply_required",
                    "diagnostics_unavailable_gate.instrumentation_supply_required",
                    "anti_loop_progress_gate.instrumentation_supply_required",
                    "anti_loop_progress_gate.diagnostics_unavailable_gate.instrumentation_supply_required",
                    "result.anti_loop_progress_gate.instrumentation_supply_required",
                ],
            )
        )
        diagnostics_unavailable_streak = number_value(
            first_present(
                result,
                [
                    "diagnostics_unavailable_streak",
                    "diagnostics_unavailable_gate.diagnostics_unavailable_streak",
                    "anti_loop_progress_gate.diagnostics_unavailable_streak",
                    "result.anti_loop_progress_gate.diagnostics_unavailable_streak",
                ],
            )
        )
        diagnostics_observable_without_new_instrumentation = boolish(
            first_present(
                result,
                [
                    "diagnostics_observable_without_new_instrumentation",
                    "success_failure_observable_without_instrumentation",
                    "existing_diagnostics_sufficient",
                    "hypothesis_repair_observability_rationale",
                    "derive.diagnostics_observable_without_new_instrumentation",
                    "result.existing_diagnostics_sufficient",
                ],
            )
        )
        independent_source_status = str(
            first_present(
                result,
                [
                    "independent_source_separation_status",
                    "verification_source_separation_gate.independent_source_separation_status",
                    "evidence_provenance_gate.independent_source_separation_status",
                    "anti_loop_progress_gate.independent_source_separation_status",
                    "anti_loop_progress_gate.verification_source_separation_gate.independent_source_separation_status",
                    "result.anti_loop_progress_gate.independent_source_separation_status",
                ],
            )
            or ""
        ).lower()
        independently_verified_downgraded_fields = list_values(
            first_present(
                result,
                [
                    "independently_verified_downgraded_fields",
                    "verification_source_separation_gate.independently_verified_downgraded_fields",
                    "evidence_provenance_gate.independently_verified_downgraded_fields",
                    "anti_loop_progress_gate.independently_verified_downgraded_fields",
                    "result.anti_loop_progress_gate.independently_verified_downgraded_fields",
                ],
            )
        )
        envelope_thaw_item_required = boolish(
            first_present(
                result,
                [
                    "envelope_thaw_item_required",
                    "acceptance_reachability_gate.envelope_thaw_item_required",
                    "anti_loop_progress_gate.envelope_thaw_item_required",
                    "anti_loop_progress_gate.acceptance_reachability_gate.envelope_thaw_item_required",
                    "result.anti_loop_progress_gate.envelope_thaw_item_required",
                ],
            )
        )
        envelope_thaw_item = first_present(
            result,
            [
                "envelope_thaw_item",
                "acceptance_reachability_gate.envelope_thaw_item",
                "anti_loop_progress_gate.envelope_thaw_item",
                "anti_loop_progress_gate.acceptance_reachability_gate.envelope_thaw_item",
                "selected_task.envelope_thaw_item",
                "result.anti_loop_progress_gate.envelope_thaw_item",
            ],
        )
        if progress_kind == "goal_productive" and allowed_task_kinds and selected_source != "terminal_blocked":
            if not selected_kind:
                add(
                    findings,
                    "block" if mode == "block" else "warn",
                    "selected_task_kind_missing_for_constrained_goal_productive",
                    "`derive` must provide `selected_task_kind` when active gates restrict goal_productive to specific task kinds.",
                    {"allowed_task_kinds": sorted(allowed_task_kinds)},
                )
            elif selected_kind not in allowed_task_kinds:
                add(
                    findings,
                    "block" if mode == "block" else "warn",
                    "goal_productive_task_kind_not_allowed",
                    "`derive` selected goal_productive by label but the task kind is outside the gate-constrained allowed set.",
                    {"selected_task_kind": selected_kind, "allowed_task_kinds": sorted(allowed_task_kinds)},
                )
        classification_repair_selected = selected_kind in CLASSIFICATION_REPAIR_TASK_KINDS or selected_disposition(result, selected_source, progress_kind) in {
            "classification_stage_repair",
            "input_contract_repair",
        }
        if (terminal_stage_contradiction or terminal_classification_invalid_for_counting) and not terminal_selected and not classification_repair_selected:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "derive_terminal_classification_stage_repair_missing",
                "`derive` cannot count or close a contradictory terminal classification; select a classification-stage repair/input-contract repair, terminal block, or user escalation.",
            )
        if same_input_contract_violation and not terminal_selected and not classification_repair_selected:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "derive_same_input_contract_repair_missing",
                "`derive` cannot compare same-family failures across mismatched input sets; select same-input contract repair before counting progress.",
            )
        if instrumentation_supply_required and not terminal_selected and selected_kind not in INSTRUMENTATION_TASK_KINDS and not diagnostics_observable_without_new_instrumentation:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "derive_missing_instrumentation_supply",
                "`derive` must enumerate/select instrumentation supply after repeated diagnostics_unavailable, or record why success/failure is already observable without new instrumentation.",
                {"diagnostics_unavailable_streak": diagnostics_unavailable_streak},
            )
        if progress_kind == "goal_productive" and independent_source_status in {"missing", "overlap", "blocked"} and not terminal_selected:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "derive_goal_productive_from_non_disjoint_independent_verification",
                "`derive` cannot treat independently_verified evidence as goal_productive when verification inputs overlap verified artifacts or are missing; consume it as attested or repair the source separation.",
                {"independent_source_separation_status": independent_source_status},
            )
        if progress_kind == "goal_productive" and independently_verified_downgraded_fields and not terminal_selected:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "derive_goal_productive_from_downgraded_independent_verification",
                "`derive` cannot use auto-downgraded independently_verified fields as progress without new disjoint verification input.",
                {"downgraded_fields": independently_verified_downgraded_fields},
            )
        if envelope_thaw_item_required and not terminal_selected and selected_kind not in ENVELOPE_THAW_TASK_KINDS and not non_empty(envelope_thaw_item):
            add(
                findings,
                "block" if mode == "block" else "warn",
                "derive_envelope_thaw_item_missing",
                "`derive` must reserve an envelope_thaw_item when acceptance is unreachable under a frozen envelope, before ordinary repair continues.",
            )
        coupled_verifier = boolish(
            first_present(
                result,
                [
                    "pass_with_coupled_verifier",
                    "anti_loop_progress_gate.pass_with_coupled_verifier",
                    "loopback_audit.pass_with_coupled_verifier",
                    "coupled_verifier_gate.pass_with_coupled_verifier",
                    "anti_loop_progress_gate.coupled_verifier_gate.pass_with_coupled_verifier",
                    "result.anti_loop_progress_gate.pass_with_coupled_verifier",
                    "result.anti_loop_progress_gate.coupled_verifier_gate.pass_with_coupled_verifier",
                ],
            )
        )
        attested_only_movement = boolish(
            first_present(
                result,
                [
                    "attested_only_movement",
                    "anti_loop_progress_gate.attested_only_movement",
                    "evidence_provenance_gate.attested_only_movement",
                    "anti_loop_progress_gate.evidence_provenance_gate.attested_only_movement",
                    "primary_metric_gate.attested_only_movement",
                    "anti_loop_progress_gate.primary_metric_gate.attested_only_movement",
                    "result.anti_loop_progress_gate.attested_only_movement",
                    "result.anti_loop_progress_gate.evidence_provenance_gate.attested_only_movement",
                ],
            )
        )
        primary_metric_stalled = boolish(
            first_present(
                result,
                [
                    "primary_metric_stalled",
                    "anti_loop_progress_gate.primary_metric_stalled",
                    "primary_metric_gate.primary_metric_stalled",
                    "anti_loop_progress_gate.primary_metric_gate.primary_metric_stalled",
                    "result.anti_loop_progress_gate.primary_metric_stalled",
                    "result.anti_loop_progress_gate.primary_metric_gate.primary_metric_stalled",
                ],
            )
        )
        c4_user_escalation = boolish(
            first_present(
                result,
                [
                    "c4_user_escalation_backstop_required",
                    "anti_loop_progress_gate.c4_user_escalation_backstop_required",
                    "primary_metric_gate.c4_user_escalation_backstop_required",
                    "anti_loop_progress_gate.primary_metric_gate.c4_user_escalation_backstop_required",
                    "result.anti_loop_progress_gate.c4_user_escalation_backstop_required",
                    "result.anti_loop_progress_gate.primary_metric_gate.c4_user_escalation_backstop_required",
                ],
            )
        )
        marginal_repair = boolish(
            first_present(
                result,
                [
                    "marginal_repair",
                    "residual_gap_policy.marginal_repair",
                    "anti_loop_progress_gate.marginal_repair",
                    "anti_loop_progress_gate.residual_gap_policy.marginal_repair",
                    "result.anti_loop_progress_gate.marginal_repair",
                ],
            )
        )
        descope_with_residual = boolish(
            first_present(
                result,
                [
                    "descope_with_residual",
                    "explicit_descope_decision",
                    "residual_gap_policy.descope_with_residual",
                    "anti_loop_progress_gate.descope_with_residual",
                    "result.anti_loop_progress_gate.descope_with_residual",
                ],
            )
        )
        next_capability_rung = first_present(
            result,
            [
                "next_capability_rung",
                "capability_ladder.next_capability_rung",
                "residual_gap_policy.next_capability_rung",
                "anti_loop_progress_gate.next_capability_rung",
                "result.anti_loop_progress_gate.next_capability_rung",
            ],
        )
        marginal_repair_override = boolish(
            first_present(
                result,
                [
                    "marginal_repair_higher_value",
                    "residual_gap_policy.marginal_repair_higher_value",
                    "anti_loop_progress_gate.marginal_repair_higher_value",
                    "result.anti_loop_progress_gate.marginal_repair_higher_value",
                ],
            )
        )
        pass_with_unobserved_axes = boolish(
            first_present(
                result,
                [
                    "pass_with_unobserved_axes",
                    "goal_axis_completeness_gate.pass_with_unobserved_axes",
                    "qualitative_review_packet.pass_with_unobserved_axes",
                    "anti_loop_progress_gate.pass_with_unobserved_axes",
                    "result.goal_axis_completeness_gate.pass_with_unobserved_axes",
                    "result.anti_loop_progress_gate.pass_with_unobserved_axes",
                ],
            )
        )
        unobserved_goal_axes = first_present(
            result,
            [
                "unobserved_goal_axes",
                "goal_axis_completeness_gate.unobserved_goal_axes",
                "qualitative_review_packet.unobserved_goal_axes",
                "anti_loop_progress_gate.unobserved_goal_axes",
                "result.goal_axis_completeness_gate.unobserved_goal_axes",
                "result.anti_loop_progress_gate.unobserved_goal_axes",
            ],
        )
        goal_axis_failed = boolish(
            first_present(
                result,
                [
                    "goal_axis_completeness_failed",
                    "goal_axis_completeness_gate.failed",
                    "goal_axis_completeness_gate.evaluation_failed",
                    "anti_loop_progress_gate.goal_axis_completeness_gate.failed",
                    "result.goal_axis_completeness_gate.failed",
                ],
            )
        ) or str(
            first_present(
                result,
                [
                    "goal_axis_completeness_gate.evaluation_status",
                    "anti_loop_progress_gate.goal_axis_completeness_gate.evaluation_status",
                    "result.goal_axis_completeness_gate.evaluation_status",
                ],
            )
            or ""
        ).lower() == "fail"
        generation_dependent_count_key = boolish(
            first_present(
                result,
                [
                    "generation_dependent_count_key",
                    "count_key_hygiene_gate.generation_dependent_count_key",
                    "anti_loop_progress_gate.generation_dependent_count_key",
                    "anti_loop_progress_gate.count_key_hygiene_gate.generation_dependent_count_key",
                    "result.anti_loop_progress_gate.generation_dependent_count_key",
                    "result.anti_loop_progress_gate.count_key_hygiene_gate.generation_dependent_count_key",
                ],
            )
        )
        effective_count_key = first_present(
            result,
            [
                "effective_count_key",
                "count_key_hygiene_gate.effective_count_key",
                "root_dominant_parameter_key",
                "anti_loop_progress_gate.effective_count_key",
                "anti_loop_progress_gate.root_dominant_parameter_key",
                "anti_loop_progress_gate.terminal_outcome_family_key",
                "result.anti_loop_progress_gate.effective_count_key",
                "result.anti_loop_progress_gate.terminal_outcome_family_key",
            ],
        )
        generation_key_novelty_claim = boolish(
            first_present(
                result,
                [
                    "family_novelty_claim",
                    "new_family_claim",
                    "stall_reset_claim",
                    "count_key_hygiene_gate.family_novelty_claim",
                    "count_key_hygiene_gate.stall_reset_claim",
                    "anti_loop_progress_gate.count_key_hygiene_gate.family_novelty_claim",
                    "result.anti_loop_progress_gate.count_key_hygiene_gate.stall_reset_claim",
                ],
            )
        )
        cycle_fixed_cost_present = first_present(
            result,
            [
                "cycle_fixed_cost",
                "residual_gap_cost_policy.cycle_fixed_cost",
                "cycle_efficiency_profile.cycle_fixed_cost",
                "anti_loop_progress_gate.cycle_fixed_cost",
                "result.anti_loop_progress_gate.cycle_fixed_cost",
            ],
        ) is not None
        marginal_value_per_cycle_cost = float_value(
            first_present(
                result,
                [
                    "marginal_value_per_cycle_cost",
                    "residual_gap_cost_policy.marginal_value_per_cycle_cost",
                    "anti_loop_progress_gate.marginal_value_per_cycle_cost",
                    "result.anti_loop_progress_gate.marginal_value_per_cycle_cost",
                ],
            )
        )
        residual_cost_below_policy = boolish(
            first_present(
                result,
                [
                    "residual_gap_cost_below_policy",
                    "value_per_cycle_cost_below_policy",
                    "cost_disproportionate_residual",
                    "residual_gap_cost_policy.below_policy",
                    "residual_gap_cost_policy.cost_disproportionate",
                    "anti_loop_progress_gate.residual_gap_cost_policy.below_policy",
                    "result.anti_loop_progress_gate.residual_gap_cost_policy.below_policy",
                ],
            )
        )
        if progress_kind == "goal_productive" and coupled_verifier and selected_source != "terminal_blocked":
            add(
                findings,
                "block" if mode == "block" else "warn",
                "derive_goal_productive_from_coupled_verifier",
                "`derive` cannot classify work as goal_productive from pass_with_coupled_verifier; select non-coupled revalidation, independent recalculation, residual descope, terminal block, or user escalation.",
            )
        if progress_kind == "goal_productive" and attested_only_movement and selected_source != "terminal_blocked":
            add(
                findings,
                "block" if mode == "block" else "warn",
                "derive_goal_productive_from_attested_only_movement",
                "`derive` cannot classify producer-attested metric movement as goal_productive or high-water progress.",
            )
        if progress_kind == "goal_productive" and (pass_with_unobserved_axes or non_empty(unobserved_goal_axes) or goal_axis_failed) and selected_source != "terminal_blocked":
            add(
                findings,
                "block" if mode == "block" else "warn",
                "derive_goal_productive_from_unobserved_axes",
                "`derive` cannot consume a qualitative review pass as goal_productive for measurable goals with zero mapped observing axes; select axis supply, residual descope, terminal block, or user escalation.",
                {"unobserved_goal_axes": unobserved_goal_axes or None},
            )
        if generation_dependent_count_key and not effective_count_key:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "derive_generation_count_key_without_effective_key",
                "Generation-dependent family/count keys are trace-only; derive must carry an effective adapter-collapsed key or terminal-outcome family fallback.",
            )
        if generation_dependent_count_key and generation_key_novelty_claim and not terminal_selected:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "derive_family_novelty_from_generation_key",
                "`derive` must not treat task/advice/pack/cycle/run/date/hash/version churn as a new family or stall reset.",
            )
        if c4_user_escalation and selected_source != "terminal_blocked" and selected_disposition(result, selected_source, progress_kind) != "user_escalation" and not forced_task_kind(result):
            add(
                findings,
                "block" if mode == "block" else "warn",
                "derive_c4_user_escalation_not_selected",
                "`derive` must select user escalation when the primary-metric C4 backstop is required and no actionable forced task is present.",
            )
        if primary_metric_stalled and progress_kind == "goal_productive" and not forced_task_kind(result) and not terminal_selected:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "derive_primary_metric_stall_without_forced_task",
                "`derive` cannot choose ordinary goal_productive work during primary-metric stall without selecting an emitted forced-retarget task.",
            )
        if marginal_repair and progress_kind == "goal_productive" and not (descope_with_residual and next_capability_rung) and not marginal_repair_override and selected_source != "terminal_blocked":
            add(
                findings,
                "block" if mode == "block" else "warn",
                "derive_marginal_repair_without_descope_or_value_case",
                "`derive` must rank below-threshold residual-gap repair behind explicit descope-with-residual plus the next capability rung unless higher marginal value is recorded.",
            )
        if marginal_repair and cycle_fixed_cost_present and marginal_value_per_cycle_cost is None:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "derive_residual_cycle_cost_missing_ratio",
                "Residual repair with cycle-cost evidence must carry `marginal_value_per_cycle_cost`, or explicitly fall back to denominator 1 when cost evidence is absent.",
            )
        if progress_kind == "goal_productive" and residual_cost_below_policy and not (descope_with_residual and next_capability_rung) and not marginal_repair_override and selected_source != "terminal_blocked":
            add(
                findings,
                "block" if mode == "block" else "warn",
                "derive_residual_cost_below_policy_goal_productive",
                "`derive` cannot select another same-gap goal_productive repair when value per cycle cost is below policy without explicit residual descope, next rung, or a higher value case.",
            )
        forced_kind = forced_task_kind(result)
        if forced_kind and selected_source != "terminal_blocked" and selected_kind and selected_kind != forced_kind:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "forced_selected_task_kind_mismatch",
                "`derive` must select the forced task kind emitted by the anti-loop chain-stall gate before choosing another goal-productive task.",
                {"selected_task_kind": selected_kind, "forced_selected_task_kind": forced_kind},
            )
        output_delta_status = str(
            first_present(
                result,
                [
                    "output_delta_status",
                    "output_delta.output_delta_status",
                    "output_delta_gate.output_delta_status",
                    "result.output_delta.output_delta_status",
                ],
            )
            or ""
        ).lower()
        produced_domain_delta = first_present(
            result,
            [
                "produced_domain_delta",
                "output_delta.produced_domain_delta",
                "output_delta_gate.produced_domain_delta",
                "result.output_delta.produced_domain_delta",
            ],
        )
        metadata_only = first_present(
            result,
            [
                "metadata_only",
                "output_delta.metadata_only",
                "output_delta_gate.metadata_only",
                "result.output_delta.metadata_only",
            ],
        )
        effective_progress_kind = str(
            first_present(
                result,
                [
                    "effective_progress_kind",
                    "output_delta.effective_progress_kind",
                    "output_delta_gate.effective_progress_kind",
                    "result.output_delta.effective_progress_kind",
                ],
            )
            or ""
        ).lower()
        changed_vs_previous = first_present(
            result,
            [
                "changed_vs_previous",
                "output_delta.changed_vs_previous",
                "output_delta_gate.changed_vs_previous",
                "result.output_delta.changed_vs_previous",
            ],
        )
        semantic_progress = first_present(
            result,
            [
                "semantic_progress",
                "output_delta.semantic_progress",
                "output_delta_gate.semantic_progress",
                "result.output_delta.semantic_progress",
            ],
        )
        measurement_progress_allowed = boolish(
            first_present(
                result,
                [
                    "measurement_progress_allowed",
                    "anti_loop_progress_gate.measurement_progress_allowed",
                    "result.anti_loop_progress_gate.measurement_progress_allowed",
                ],
            )
        )
        measurement_progress = boolish(
            first_present(
                result,
                [
                    "measurement_progress",
                    "anti_loop_progress_gate.measurement_progress",
                    "result.anti_loop_progress_gate.measurement_progress",
                ],
            )
        )
        substance_delta_pass = boolish(
            first_present(
                result,
                [
                    "substance_delta_pass",
                    "substance_delta_gate.substance_delta_pass",
                    "anti_loop_progress_gate.substance_delta_gate.substance_delta_pass",
                    "result.anti_loop_progress_gate.substance_delta_gate.substance_delta_pass",
                ],
            )
        )
        vacuous_corrective_noop = boolish(
            first_present(
                result,
                [
                    "surface_corrective_noop",
                    "vacuous_corrective_gate.surface_corrective_noop",
                    "anti_loop_progress_gate.vacuous_corrective_gate.surface_corrective_noop",
                    "result.anti_loop_progress_gate.vacuous_corrective_gate.surface_corrective_noop",
                ],
            )
        )
        advice_metrics_stale = boolish(
            first_present(
                result,
                [
                    "advice_metrics_stale",
                    "advice_freshness_gate.advice_metrics_stale",
                    "anti_loop_progress_gate.advice_freshness_gate.advice_metrics_stale",
                    "result.anti_loop_progress_gate.advice_freshness_gate.advice_metrics_stale",
                ],
            )
        )
        measurement_streak = number_value(
            first_present(
                result,
                [
                    "measurement_streak",
                    "anti_loop_progress_gate.measurement_streak",
                    "result.anti_loop_progress_gate.measurement_streak",
                ],
            )
        )
        measurement_streak_cap = number_value(
            first_present(
                result,
                [
                    "measurement_streak_cap",
                    "anti_loop_progress_gate.measurement_streak_cap",
                    "result.anti_loop_progress_gate.measurement_streak_cap",
                ],
            )
        )
        blocker_mutation_kind = str(
            first_present(
                result,
                [
                    "blocker_mutation_kind",
                    "anti_loop_progress_gate.blocker_mutation_kind",
                    "result.anti_loop_progress_gate.blocker_mutation_kind",
                ],
            )
            or ""
        ).lower()
        forward_mutation_progress = blocker_mutation_kind == "forward_mutation"
        terminal_outcome_value = first_present(
            result,
            [
                "terminal_outcome_changed",
                "anti_loop_progress_gate.terminal_outcome_changed",
                "result.anti_loop_progress_gate.terminal_outcome_changed",
            ],
        )
        terminal_outcome_changed = (
            boolish(terminal_outcome_value)
            if terminal_outcome_value is not None
            else boolish(changed_vs_previous) and boolish(semantic_progress)
        )
        forward_mutation_vacuous = boolish(
            first_present(
                result,
                [
                    "forward_mutation_vacuous",
                    "anti_loop_progress_gate.forward_mutation_vacuous",
                    "result.anti_loop_progress_gate.forward_mutation_vacuous",
                ],
            )
        )
        force_implementation_cycle = boolish(
            first_present(
                result,
                [
                    "force_implementation_cycle",
                    "anti_loop_progress_gate.force_implementation_cycle",
                    "result.anti_loop_progress_gate.force_implementation_cycle",
                ],
            )
        )
        command_surface_class = str(
            first_present(
                result,
                [
                    "command_surface_class",
                    "selected_task.command_surface_class",
                    "command_surface_budget.command_surface_class",
                    "result.command_surface_class",
                ],
            )
            or ""
        ).strip().lower()
        allowed_force_impl_class = command_surface_class in {"b", "class_b", "c", "class_c"}
        output_delta_applies = output_delta_status == "complete" or produced_domain_delta is not None or metadata_only is not None
        if progress_kind == "goal_productive" and output_delta_applies and (
            boolish(metadata_only)
            or (produced_domain_delta is not None and not boolish(produced_domain_delta))
            or (produced_domain_delta is not None and boolish(produced_domain_delta) and not (boolish(changed_vs_previous) and boolish(semantic_progress)))
        ) and not (measurement_progress_allowed or forward_mutation_progress):
            add(
                findings,
                "block" if mode == "block" else "warn",
                "goal_productive_without_output_delta",
                "`derive` cannot classify work as goal_productive without produced_domain_delta=true backed by changed_vs_previous=true and semantic_progress=true.",
                {
                    "progress_kind": progress_kind,
                    "effective_progress_kind": effective_progress_kind or None,
                    "output_delta_status": output_delta_status or None,
                    "produced_domain_delta": produced_domain_delta,
                    "changed_vs_previous": changed_vs_previous,
                    "semantic_progress": semantic_progress,
                    "metadata_only": metadata_only,
                },
            )
        if progress_kind == "goal_productive" and (measurement_progress or blocker_mutation_kind == "forward_mutation") and not (substance_delta_pass or boolish(changed_vs_previous) and boolish(semantic_progress)):
            add(
                findings,
                "block" if mode == "block" else "warn",
                "goal_productive_without_substance_delta",
                "`derive` cannot promote measurement or ladder-rung movement from tool/oracle existence alone; require G-SUBSTANCE pass or strict changed-and-semantic primary-output evidence.",
                {
                    "measurement_progress": measurement_progress,
                    "blocker_mutation_kind": blocker_mutation_kind or None,
                    "substance_delta_pass": substance_delta_pass,
                    "changed_vs_previous": changed_vs_previous,
                    "semantic_progress": semantic_progress,
                },
            )
        if progress_kind == "goal_productive" and forward_mutation_progress and (forward_mutation_vacuous or not terminal_outcome_changed):
            add(
                findings,
                "block" if mode == "block" else "warn",
                "goal_productive_forward_mutation_without_terminal_outcome_delta",
                "`derive` cannot promote capability-ladder forward mutation when the observed terminal outcome did not change.",
                {
                    "blocker_mutation_kind": blocker_mutation_kind,
                    "terminal_outcome_changed": terminal_outcome_changed,
                    "forward_mutation_vacuous": forward_mutation_vacuous,
                },
            )
        if progress_kind == "goal_productive" and vacuous_corrective_noop and not (boolish(changed_vs_previous) and boolish(semantic_progress)):
            add(
                findings,
                "block" if mode == "block" else "warn",
                "goal_productive_from_vacuous_corrective",
                "`derive` cannot count corrective/backfill rows as goal_productive when attempted lanes resolved zero items.",
            )
        if advice_metrics_stale and has_value(result, "used_advice") and not advice_handling_rationale_present(result):
            add(
                findings,
                "warn",
                "stale_advice_used_without_rationale",
                "`derive` used advice whose headline fingerprint/metric claims are stale without a defer/reject/refresh rationale.",
            )
        if measurement_streak is not None and measurement_streak_cap is not None and measurement_streak > measurement_streak_cap and selected_source != "terminal_blocked" and not has_value(result, "terminal_blocker"):
            add(
                findings,
                "block" if mode == "block" else "warn",
                "measurement_streak_cap_exceeded",
                "Measurement progress exemption is capped; derive must not continue non-terminal measurement/governance work after the cap.",
                {"measurement_streak": measurement_streak, "measurement_streak_cap": measurement_streak_cap},
            )
        if force_implementation_cycle and not has_value(result, "terminal_blocker") and progress_kind != "goal_productive":
            add(
                findings,
                "block" if mode == "block" else "warn",
                "force_implementation_cycle_unhandled",
                "Forward-mutation budget is exhausted; derive must select implementation work or terminal/user escalation.",
                {"progress_kind": progress_kind or None},
            )
        if force_implementation_cycle and command_surface_class and not allowed_force_impl_class and not has_value(result, "terminal_blocker"):
            add(
                findings,
                "block" if mode == "block" else "warn",
                "force_implementation_command_surface_class_blocked",
                "Forced implementation under command-surface pressure may use only Class B in-place expansion or Class C surface reduction.",
                {"command_surface_class": command_surface_class},
            )

        cycles_since_goal_productive = number_value(
            first_present(
                result,
                [
                    "cycles_since_goal_productive_output",
                    "goal_distance_gate.cycles_since_goal_productive_output",
                    "loop_breaker_packet.cycles_since_goal_productive_output",
                    "packet.goal_distance_gate.cycles_since_goal_productive_output",
                    "result.goal_distance_gate.cycles_since_goal_productive_output",
                ],
            )
        )
        goal_threshold = number_value(
            first_present(result, ["goal_productive_threshold", "goal_distance_gate.threshold", "result.goal_distance_gate.threshold"])
        ) or 5
        goal_distance_required = boolish(
            first_present(
                result,
                [
                    "requires_goal_productive_next",
                    "goal_distance_gate.requires_goal_productive_next",
                    "loop_breaker_packet.requires_goal_productive_next",
                    "result.goal_distance_gate.requires_goal_productive_next",
                ],
            )
        ) or (cycles_since_goal_productive is not None and cycles_since_goal_productive > goal_threshold)
        governance_only_streak = number_value(
            first_present(
                result,
                [
                    "governance_only_streak",
                    "previous_governance_only_count",
                    "loop_breaker_packet.governance_only_streak",
                    "goal_distance_gate.governance_only_streak",
                    "result.goal_distance_gate.governance_only_streak",
                ],
            )
        )
        new_input_kinds = list_values(
            first_present(
                result,
                [
                    "new_input_kinds",
                    "introduced_input_kinds",
                    "positive_input_delta_gate.new_input_kinds",
                    "loop_breaker_packet.new_input_kinds",
                    "result.positive_input_delta_gate.new_input_kinds",
                ],
            )
        )
        supplied_input_paths = list_values(
            first_present(
                result,
                [
                    "supplied_input_artifact_paths",
                    "positive_input_delta_gate.supplied_input_artifact_paths",
                    "loop_breaker_packet.supplied_input_artifact_paths",
                    "loop_breaker_packet.positive_input_delta_gate.supplied_input_artifact_paths",
                    "result.positive_input_delta_gate.supplied_input_artifact_paths",
                ],
            )
        )
        strict_positive_output_delta = boolish(produced_domain_delta) and boolish(changed_vs_previous) and boolish(semantic_progress)
        has_supplied_input_delta = boolish(
            first_present(
                result,
                [
                    "has_supplied_input_delta",
                    "positive_input_delta_gate.has_supplied_input_delta",
                    "loop_breaker_packet.has_supplied_input_delta",
                    "loop_breaker_packet.positive_input_delta_gate.has_supplied_input_delta",
                    "result.positive_input_delta_gate.has_supplied_input_delta",
                ],
            )
        ) or bool(supplied_input_paths) or strict_positive_output_delta
        provider_reattempt_required = boolish(
            first_present(
                result,
                [
                    "provider_reattempt_required",
                    "provider_reattempt_gate.provider_reattempt_required",
                    "loop_breaker_packet.provider_reattempt_gate.provider_reattempt_required",
                    "failure_autopsy_packet.provider_reattempt_required",
                    "result.provider_reattempt_gate.provider_reattempt_required",
                ],
            )
        )
        provider_mitigation_required = boolish(
            first_present(
                result,
                [
                    "provider_mitigation_required",
                    "provider_reattempt_gate.provider_mitigation_required",
                    "loop_breaker_packet.provider_reattempt_gate.provider_mitigation_required",
                    "failure_autopsy_packet.provider_mitigation_required",
                    "result.provider_reattempt_gate.provider_mitigation_required",
                ],
            )
        )
        provider_terminal_seal_allowed = first_present(
            result,
            [
                "provider_terminal_seal_allowed",
                "provider_reattempt_gate.provider_terminal_seal_allowed",
                "loop_breaker_packet.provider_reattempt_gate.provider_terminal_seal_allowed",
                "result.provider_reattempt_gate.provider_terminal_seal_allowed",
            ],
        )
        provider_reattempt_disposition = str(
            first_present(
                result,
                [
                    "provider_reattempt_disposition",
                    "derive.provider_reattempt_disposition",
                    "result.provider_reattempt_disposition",
                    "selected_task.provider_reattempt_disposition",
                ],
            )
            or ""
        ).lower()
        loop_detector_status = str(
            first_present(
                result,
                [
                    "detect_progress_loop_status",
                    "loop_detector_status",
                    "loop_breaker_packet.status",
                    "result.loop_breaker_packet.status",
                ],
            )
            or ""
        ).lower()
        sealed_match = boolish(
            first_present(
                result,
                [
                    "sealed_semantic_family_match",
                    "semantic_signature_gate.sealed_match",
                    "semantic_signature_gate.sealed_matches",
                    "loop_breaker_packet.sealed_semantic_family_match",
                    "result.semantic_signature_gate.sealed_matches",
                ],
            )
        )
        terminal_selected = selected_source == "terminal_blocked" or has_value(result, "terminal_blocker")
        seal_requested_value = first_present(
            result,
            [
                "sealing_blocker_family",
                "seal_family_path",
                "terminal_blocker.seal_family_path",
                "terminal_blocker.sealing_blocker_family",
                "result.terminal_blocker.seal_family_path",
            ],
        )
        seal_requested = boolish(seal_requested_value) or (
            seal_requested_value is not None and str(seal_requested_value).strip().lower() not in {"false", "no", "0", "none"}
        )
        terminal_or_seal = terminal_selected or seal_requested
        root_cause_attempted = boolish(
            first_present(
                result,
                [
                    "root_cause_attempted_for_family",
                    "terminal_blocker.root_cause_attempted_for_family",
                    "loop_breaker_packet.root_cause_attempted_for_family",
                    "result.root_cause_attempted_for_family",
                ],
            )
        )
        root_cause_required = not boolish(
            first_present(
                result,
                [
                    "root_cause_not_required_for_family",
                    "terminal_blocker.root_cause_not_required_for_family",
                    "result.root_cause_not_required_for_family",
                ],
            )
        )
        if terminal_or_seal and root_cause_required and not root_cause_attempted:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "sealed_family_without_root_cause_attempt",
                "Sealing a blocker family requires at least one prior root-cause/autopsy repair attempt or an explicit not-required rationale.",
            )
        untried_root_cause_exists = boolish(
            first_present(
                result,
                [
                    "untried_actionable_root_cause_exists",
                    "anti_loop_progress_gate.untried_actionable_root_cause_exists",
                    "anti_loop_progress_gate.terminal_blocked_invalid_due_to_untried_root_cause",
                    "loop_breaker_packet.untried_actionable_root_cause_exists",
                    "terminal_blocker.untried_actionable_root_cause_exists",
                    "result.anti_loop_progress_gate.untried_actionable_root_cause_exists",
                    "result.terminal_blocker.untried_actionable_root_cause_exists",
                ],
            )
        )
        hypothesis_exhausted = boolish(
            first_present(
                result,
                [
                    "hypothesis_exhausted",
                    "anti_loop_progress_gate.hypothesis_exhausted",
                    "loop_breaker_packet.hypothesis_exhausted",
                    "terminal_blocker.hypothesis_exhausted",
                    "result.anti_loop_progress_gate.hypothesis_exhausted",
                    "result.terminal_blocker.hypothesis_exhausted",
                ],
            )
        )
        untried_veto_overridden_by_chain_stall = boolish(
            first_present(
                result,
                [
                    "untried_veto_overridden_by_chain_stall",
                    "cumulative_untried_chain_without_quality_delta",
                    "anti_loop_progress_gate.untried_veto_overridden_by_chain_stall",
                    "anti_loop_progress_gate.cumulative_untried_chain_without_quality_delta",
                    "loop_breaker_packet.untried_veto_overridden_by_chain_stall",
                    "terminal_blocker.untried_veto_overridden_by_chain_stall",
                    "result.anti_loop_progress_gate.untried_veto_overridden_by_chain_stall",
                    "result.terminal_blocker.untried_veto_overridden_by_chain_stall",
                ],
            )
        )
        if (
            terminal_or_seal
            and untried_root_cause_exists
            and not hypothesis_exhausted
            and not untried_veto_overridden_by_chain_stall
        ):
            add(
                findings,
                "block" if mode == "block" else "warn",
                "terminal_blocked_with_untried_actionable_root_cause",
                "terminal_blocked is invalid while a local, bounded, provider-free, in-scope, authority-allowed root-cause hypothesis remains untried.",
            )
        authorized_alternative_exists = boolish(
            first_present(
                result,
                [
                    "authorized_alternative_path_exists",
                    "sealing_direction_guard.authorized_alternative_path_exists",
                    "terminal_blocker.authorized_alternative_path_exists",
                    "result.sealing_direction_guard.authorized_alternative_path_exists",
                ],
            )
        )
        authorized_alternative_path = first_present(
            result,
            [
                "authorized_alternative_path",
                "sealing_direction_guard.authorized_alternative_path",
                "terminal_blocker.authorized_alternative_path",
                "result.sealing_direction_guard.authorized_alternative_path",
                "result.terminal_blocker.authorized_alternative_path",
            ],
        )
        alternative_in_gt_allowed_value = first_present(
            result,
            [
                "alternative_in_gt_allowed",
                "sealing_direction_guard.alternative_in_gt_allowed",
                "terminal_blocker.alternative_in_gt_allowed",
                "result.sealing_direction_guard.alternative_in_gt_allowed",
                "result.terminal_blocker.alternative_in_gt_allowed",
            ],
        )
        alternative_in_gt_allowed = boolish(alternative_in_gt_allowed_value)
        gt_allowed_alternative_attempted = boolish(
            first_present(
                result,
                [
                    "gt_allowed_alternative_attempted",
                    "sealing_direction_guard.gt_allowed_alternative_attempted",
                    "terminal_blocker.gt_allowed_alternative_attempted",
                    "result.sealing_direction_guard.gt_allowed_alternative_attempted",
                    "result.terminal_blocker.gt_allowed_alternative_attempted",
                ],
            )
        )
        gt_allowed_evidence_paths = list_values(
            first_present(
                result,
                [
                    "gt_allowed_alternative_evidence_paths",
                    "sealing_direction_guard.gt_allowed_alternative_evidence_paths",
                    "terminal_blocker.gt_allowed_alternative_evidence_paths",
                    "result.sealing_direction_guard.gt_allowed_alternative_evidence_paths",
                    "result.terminal_blocker.gt_allowed_alternative_evidence_paths",
                ],
            )
        )
        alternative_attempted = boolish(
            first_present(
                result,
                [
                    "authorized_alternative_path_attempted",
                    "sealing_direction_guard.authorized_alternative_path_attempted",
                    "terminal_blocker.authorized_alternative_path_attempted",
                    "result.sealing_direction_guard.authorized_alternative_path_attempted",
                ],
            )
        )
        if terminal_or_seal and authorized_alternative_exists and not alternative_attempted:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "seal_denied_authorized_alternative_unattempted",
                "A blocker family cannot be sealed while an authority-permitted productive alternative path remains unattempted.",
            )
        if terminal_or_seal and authorized_alternative_exists and not authorized_alternative_path:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "seal_authorized_alternative_path_missing",
                "Sealing with an authorized alternative requires naming the concrete `authorized_alternative_path`.",
            )
        if terminal_or_seal and authorized_alternative_exists and not alternative_in_gt_allowed:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "seal_alternative_not_gt_allowed",
                "The `authorized_alternative_path` must be derived from `.agent_goal` authority/convention allowed actions before it can justify sealing.",
                {
                    "authorized_alternative_path": authorized_alternative_path,
                    "alternative_in_gt_allowed": alternative_in_gt_allowed_value,
                },
            )
        if terminal_or_seal and authorized_alternative_exists and alternative_in_gt_allowed and not gt_allowed_alternative_attempted:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "seal_gt_allowed_alternative_unattempted",
                "A GT-allowed productive alternative must be actually attempted before sealing.",
                {"authorized_alternative_path": authorized_alternative_path},
            )
        if (
            terminal_or_seal
            and authorized_alternative_exists
            and alternative_in_gt_allowed
            and gt_allowed_alternative_attempted
            and not gt_allowed_evidence_paths
        ):
            add(
                findings,
                "block" if mode == "block" else "warn",
                "seal_gt_allowed_alternative_evidence_missing",
                "A GT-allowed alternative attempt must cite non-empty evidence paths before sealing.",
                {"authorized_alternative_path": authorized_alternative_path},
            )
        next_capability_actionable = boolish(
            first_present(
                result,
                [
                    "next_capability_actionable",
                    "capability_ladder_next.actionable",
                    "terminal_blocked_exit_guard.actionable",
                    "terminal_blocker.terminal_blocked_exit_guard.actionable",
                    "result.terminal_blocked_exit_guard.actionable",
                    "result.terminal_blocker.terminal_blocked_exit_guard.actionable",
                ],
            )
        )
        if terminal_selected and next_capability_actionable:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "terminal_blocked_exit_guard_refused",
                "Terminal blocker is invalid while the next capability rung is actionable with current authority/local/bounded inputs.",
            )
        if provider_reattempt_required and (terminal_selected or seal_requested):
            add(
                findings,
                "block" if mode == "block" else "warn",
                "provider_terminal_seal_before_bounded_retry",
                "A transient provider failure with retry authority cannot be terminal-sealed before required mitigation retry/probe evidence.",
            )
        if provider_mitigation_required and provider_terminal_seal_allowed is False and (terminal_selected or seal_requested):
            add(
                findings,
                "block" if mode == "block" else "warn",
                "provider_terminal_seal_before_mitigation_exhausted",
                "A transient provider failure cannot justify terminal sealing while required mitigations remain unexhausted.",
            )
        if provider_reattempt_required and not terminal_selected and provider_reattempt_disposition not in {"selected_bounded_retry", "selected_bounded_provider_retry", "selected_probe_retry"}:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "provider_reattempt_disposition_missing",
                "`derive` must record that it selected a bounded provider retry/probe task or explain why the provider reattempt gate no longer applies.",
                {"provider_reattempt_disposition": provider_reattempt_disposition or None},
            )
        if goal_distance_required and not terminal_selected and progress_kind != "goal_productive":
            add(
                findings,
                "block" if mode == "block" else "warn",
                "goal_distance_gate_unmet",
                "Goal-distance gate requires a goal-productive selected task or terminal blocker state.",
                {"cycles_since_goal_productive_output": cycles_since_goal_productive, "threshold": goal_threshold, "progress_kind": progress_kind or None},
            )
        if loop_detector_status == "block" and not terminal_selected and progress_kind != "goal_productive":
            add(
                findings,
                "block" if mode == "block" else "warn",
                "loop_detector_block_unhandled",
                "`detect_progress_loop status=block` allows only a goal-productive selected task or terminal blocker state.",
                {"progress_kind": progress_kind or None},
            )
        if terminal_selected and (goal_distance_required or loop_detector_status == "block"):
            dual_track_attempted = boolish(
                first_present(
                    result,
                    [
                        "dual_track_attempt_evidence",
                        "terminal_blocker.dual_track_attempt_evidence",
                        "terminal_blocker.dual_track_attempted",
                        "result.terminal_blocker.dual_track_attempt_evidence",
                    ],
                )
            )
            provider_track_attempted = boolish(first_present(result, ["provider_track_attempted", "terminal_blocker.provider_track_attempted"]))
            quality_track_attempted = boolish(
                first_present(
                    result,
                    [
                        "provider_neutral_or_quality_track_attempted",
                        "quality_or_provider_neutral_track_attempted",
                        "terminal_blocker.provider_neutral_or_quality_track_attempted",
                        "terminal_blocker.quality_or_provider_neutral_track_attempted",
                    ],
                )
            )
            if not (dual_track_attempted or (provider_track_attempted and quality_track_attempted)):
                add(
                    findings,
                    "block" if mode == "block" else "warn",
                    "terminal_blocker_missing_dual_track_attempt_evidence",
                    "Terminal blocker after a hard progress-loop gate must cite provider-track and provider-neutral/quality-track attempt evidence.",
                )
        if governance_only_streak is not None and governance_only_streak >= 2 and not terminal_selected and progress_kind != "goal_productive":
            add(
                findings,
                "block" if mode == "block" else "warn",
                "governance_only_streak_unmet",
                "After two governance-only cycles, derive must select goal-productive work or terminal blocker state.",
                {"governance_only_streak": governance_only_streak, "progress_kind": progress_kind or None},
            )
        autonomous_retarget_disabled = boolish(
            first_present(
                result,
                [
                    "autonomous_retarget_disabled",
                    "hard_stop_required",
                    "root_axis_gate.autonomous_retarget_disabled",
                    "root_axis_gate.hard_stop_required",
                    "loop_breaker_packet.autonomous_retarget_disabled",
                    "loop_breaker_packet.hard_stop_required",
                    "loop_breaker_packet.root_axis_gate.autonomous_retarget_disabled",
                    "result.root_axis_gate.autonomous_retarget_disabled",
                ],
            )
        )
        if autonomous_retarget_disabled and not terminal_selected and progress_kind != "goal_productive":
            add(
                findings,
                "block" if mode == "block" else "warn",
                "autonomous_retarget_disabled_unhandled",
                "A root-axis hard stop allows only goal-productive derivation or terminal/user-escalation state.",
                {"progress_kind": progress_kind or None},
            )
        gt_conflict_blocked = boolish(
            first_present(
                result,
                [
                    "gt_constraint_conflict_packet.requires_conflict_resolution_task",
                    "gt_constraint_conflict_packet.status",
                    "loop_breaker_packet.gt_constraint_conflict_packet.requires_conflict_resolution_task",
                    "result.gt_constraint_conflict_packet.requires_conflict_resolution_task",
                    "result.gt_constraint_conflict_packet.status",
                ],
            )
        )
        resolves_gt_conflict = boolish(
            first_present(
                result,
                [
                    "resolves_gt_constraint_conflict",
                    "conflict_resolution_task_selected",
                    "selected_task.resolves_gt_constraint_conflict",
                    "derive.resolves_gt_constraint_conflict",
                    "result.resolves_gt_constraint_conflict",
                ],
            )
        )
        selected_task_kind = str(
            first_present(
                result,
                [
                    "selected_task_kind",
                    "selected_task.task_kind",
                    "derive.selected_task_kind",
                    "result.selected_task_kind",
                ],
            )
            or ""
        ).lower()
        if selected_task_kind in {"gt_constraint_conflict_resolution", "conflict_resolution", "authority_conflict_resolution"}:
            resolves_gt_conflict = True
        if gt_conflict_blocked and not terminal_selected and not resolves_gt_conflict:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "gt_constraint_conflict_unhandled",
                "A GT/task constraint conflict requires explicit conflict-resolution, contradiction-removing work, or terminal/user-escalation state.",
                {"progress_kind": progress_kind or None, "selected_task_kind": selected_task_kind or None},
            )
        if new_input_kinds and not has_supplied_input_delta:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "named_only_input_delta",
                "`new_input_kinds` alone is not a positive input delta; provide non-empty artifact paths or produced_domain_delta=true.",
                {"new_input_kinds": new_input_kinds},
            )
        if sealed_match and not terminal_selected and not has_supplied_input_delta:
            add(
                findings,
                "block",
                "sealed_semantic_family_without_input_delta",
                "A sealed semantic blocker family cannot produce another non-terminal derive result without a supplied input artifact or positive output delta.",
            )
        command_budget_required = boolish(
            first_present(
                result,
                [
                    "command_surface_budget.consolidation_candidate_required",
                    "loop_breaker_packet.command_surface_budget.consolidation_candidate_required",
                    "result.command_surface_budget.consolidation_candidate_required",
                ],
            )
        )
        consolidation_registered = boolish(
            first_present(
                result,
                [
                    "consolidation_candidate_registered",
                    "command_surface_budget.consolidation_candidate_registered",
                    "result.consolidation_candidate_registered",
                ],
            )
        )
        if (
            command_budget_required
            and not consolidation_registered
            and not terminal_selected
            and not strict_positive_output_delta
            and not (force_implementation_cycle and allowed_force_impl_class)
        ):
            add(
                findings,
                "block" if mode == "block" else "warn",
                "command_surface_budget_unhandled",
                "Command-surface budget requires consolidation, terminal state, or strict changed-and-semantic output-delta evidence.",
            )
