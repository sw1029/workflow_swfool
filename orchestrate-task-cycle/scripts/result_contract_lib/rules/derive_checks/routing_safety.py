from __future__ import annotations

from .shared import (
    ADOPTION_AXIS_TASK_KINDS,
    CURRENT_LANE_TASK_KINDS,
    CYCLE_REACHABILITY_TASK_KINDS,
    DECISION_FRESHNESS_TASK_KINDS,
    METRIC_BASIS_TASK_KINDS,
    PORTFOLIO_QUOTA_TASK_KINDS,
    PRODUCER_SUPPLY_TASK_KINDS,
    REPORT_KEY_REPAIR_TASK_KINDS,
    RESOLUTION_REPAIR_TASK_KINDS,
    SURFACE_FIELD_TASK_KINDS,
    add,
    boolish,
    first_present,
    nonzero_scalar,
)
from .state import DeriveFacts


def _check_routing_safety_part_01(facts: DeriveFacts) -> None:
    auto_report_key_divergences = facts.auto_report_key_divergences
    explicit_report_key_divergence = facts.explicit_report_key_divergence
    failed_gating_axis = facts.failed_gating_axis
    findings = facts.findings
    measured_but_disqualified = facts.measured_but_disqualified
    mode = facts.mode
    progress_kind = facts.progress_kind
    repeated_resolution_downgrade = facts.repeated_resolution_downgrade
    resolution_downgrade = facts.resolution_downgrade
    result = facts.result
    selected_kind = facts.selected_kind
    terminal_selected = facts.terminal_selected
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
    facts.pass_on_stale_lane = pass_on_stale_lane


def _check_routing_safety_part_02(facts: DeriveFacts) -> None:
    result = facts.result
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
    facts.axis_starved_by_missing_producer = axis_starved_by_missing_producer
    facts.decision_metadata_revision = decision_metadata_revision
    facts.portfolio_quota_exceeded = portfolio_quota_exceeded
    facts.portfolio_quota_mode = portfolio_quota_mode
    facts.portfolio_quota_restrictive = portfolio_quota_restrictive


def _check_routing_safety_part_03(facts: DeriveFacts) -> None:
    decision_metadata_revision = facts.decision_metadata_revision
    findings = facts.findings
    mode = facts.mode
    pass_on_stale_lane = facts.pass_on_stale_lane
    result = facts.result
    selected_kind = facts.selected_kind
    terminal_selected = facts.terminal_selected
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
    facts.basis_overclaim = basis_overclaim
    facts.surface_field_defects = surface_field_defects
    facts.unreachable_within_cycle = unreachable_within_cycle


def _check_routing_safety_part_04(facts: DeriveFacts) -> None:
    axis_starved_by_missing_producer = facts.axis_starved_by_missing_producer
    basis_overclaim = facts.basis_overclaim
    findings = facts.findings
    mode = facts.mode
    portfolio_quota_exceeded = facts.portfolio_quota_exceeded
    portfolio_quota_mode = facts.portfolio_quota_mode
    portfolio_quota_restrictive = facts.portfolio_quota_restrictive
    selected_kind = facts.selected_kind
    surface_field_defects = facts.surface_field_defects
    terminal_selected = facts.terminal_selected
    unreachable_within_cycle = facts.unreachable_within_cycle
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


def _check_routing_safety_part_05(facts: DeriveFacts) -> None:
    result = facts.result
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
    facts.harvest_gate_unaudited = harvest_gate_unaudited
    facts.harvest_preflight_required = harvest_preflight_required


def check_routing_safety(facts: DeriveFacts) -> None:
    _check_routing_safety_part_01(facts)
    _check_routing_safety_part_02(facts)
    _check_routing_safety_part_03(facts)
    _check_routing_safety_part_04(facts)
    _check_routing_safety_part_05(facts)

