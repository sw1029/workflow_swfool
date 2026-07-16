from __future__ import annotations

from .shared import (
    add,
    boolish,
    first_present,
    list_values,
)
from .state import DeriveFacts


def _check_provider_outcomes_part_01(facts: DeriveFacts) -> None:
    alternative_in_gt_allowed = facts.alternative_in_gt_allowed
    alternative_in_gt_allowed_value = facts.alternative_in_gt_allowed_value
    authorized_alternative_exists = facts.authorized_alternative_exists
    authorized_alternative_path = facts.authorized_alternative_path
    findings = facts.findings
    mode = facts.mode
    result = facts.result
    terminal_or_seal = facts.terminal_or_seal
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
    facts.gt_allowed_evidence_paths = gt_allowed_evidence_paths


def _check_provider_outcomes_part_02(facts: DeriveFacts) -> None:
    alternative_in_gt_allowed = facts.alternative_in_gt_allowed
    authorized_alternative_exists = facts.authorized_alternative_exists
    authorized_alternative_path = facts.authorized_alternative_path
    findings = facts.findings
    gt_allowed_alternative_attempted = facts.gt_allowed_alternative_attempted
    gt_allowed_evidence_paths = facts.gt_allowed_evidence_paths
    mode = facts.mode
    provider_reattempt_required = facts.provider_reattempt_required
    result = facts.result
    seal_requested = facts.seal_requested
    terminal_or_seal = facts.terminal_or_seal
    terminal_selected = facts.terminal_selected
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


def _check_provider_outcomes_part_03(facts: DeriveFacts) -> None:
    cycles_since_goal_productive = facts.cycles_since_goal_productive
    findings = facts.findings
    goal_distance_required = facts.goal_distance_required
    goal_threshold = facts.goal_threshold
    loop_detector_status = facts.loop_detector_status
    mode = facts.mode
    progress_kind = facts.progress_kind
    provider_mitigation_required = facts.provider_mitigation_required
    provider_reattempt_disposition = facts.provider_reattempt_disposition
    provider_reattempt_required = facts.provider_reattempt_required
    provider_terminal_seal_allowed = facts.provider_terminal_seal_allowed
    seal_requested = facts.seal_requested
    terminal_selected = facts.terminal_selected
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


def _check_provider_outcomes_part_04(facts: DeriveFacts) -> None:
    findings = facts.findings
    goal_distance_required = facts.goal_distance_required
    loop_detector_status = facts.loop_detector_status
    mode = facts.mode
    progress_kind = facts.progress_kind
    result = facts.result
    terminal_selected = facts.terminal_selected
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


def _check_provider_outcomes_part_05(facts: DeriveFacts) -> None:
    findings = facts.findings
    has_supplied_input_delta = facts.has_supplied_input_delta
    mode = facts.mode
    new_input_kinds = facts.new_input_kinds
    progress_kind = facts.progress_kind
    result = facts.result
    terminal_selected = facts.terminal_selected
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


def _check_provider_outcomes_part_06(facts: DeriveFacts) -> None:
    findings = facts.findings
    has_supplied_input_delta = facts.has_supplied_input_delta
    result = facts.result
    sealed_match = facts.sealed_match
    terminal_selected = facts.terminal_selected
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
    command_budget_scope = str(
        first_present(
            result,
            [
                "command_surface_budget.decision_scope",
                "global_aggregate.decision_scope",
                "result.command_surface_budget.decision_scope",
            ],
        )
        or ""
    ).strip().lower()
    command_budget_hard_gate_value = first_present(
        result,
        ["command_surface_budget.hard_gate", "global_aggregate.hard_gate", "result.command_surface_budget.hard_gate"],
    )
    command_budget_constrains_value = first_present(
        result,
        [
            "command_surface_budget.constrains_current_family",
            "global_aggregate.constrains_current_family",
            "result.command_surface_budget.constrains_current_family",
        ],
    )
    command_budget_constrains_current = (
        command_budget_scope != "global_dashboard"
        and (command_budget_hard_gate_value is None or boolish(command_budget_hard_gate_value))
        and (command_budget_constrains_value is None or boolish(command_budget_constrains_value))
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
    facts.command_budget_constrains_current = command_budget_constrains_current
    facts.command_budget_required = command_budget_required
    facts.consolidation_registered = consolidation_registered


def _check_provider_outcomes_part_07(facts: DeriveFacts) -> None:
    allowed_force_impl_class = facts.allowed_force_impl_class
    command_budget_constrains_current = facts.command_budget_constrains_current
    command_budget_required = facts.command_budget_required
    consolidation_registered = facts.consolidation_registered
    findings = facts.findings
    force_implementation_cycle = facts.force_implementation_cycle
    mode = facts.mode
    strict_positive_output_delta = facts.strict_positive_output_delta
    terminal_selected = facts.terminal_selected
    if (
        command_budget_required
        and command_budget_constrains_current
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


def check_provider_outcomes(facts: DeriveFacts) -> None:
    _check_provider_outcomes_part_01(facts)
    _check_provider_outcomes_part_02(facts)
    _check_provider_outcomes_part_03(facts)
    _check_provider_outcomes_part_04(facts)
    _check_provider_outcomes_part_05(facts)
    _check_provider_outcomes_part_06(facts)
    _check_provider_outcomes_part_07(facts)

