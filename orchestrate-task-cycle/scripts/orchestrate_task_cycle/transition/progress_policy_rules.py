from __future__ import annotations

from .access import first_value, list_value, truthy
from .context import ValidationContext
from .progress_core_rules import (
    PROGRESS_TRANSITIONS,
    next_progress_kind,
    terminal_blocker,
)


def validate_provider_retry_gates(state: ValidationContext) -> None:
    if not _applies(state):
        return
    reattempt_required = truthy(
        first_value(
            state.stage,
            "provider_reattempt_required",
            "packet.provider_reattempt_required",
            "provider_reattempt_gate.provider_reattempt_required",
            "packet.provider_reattempt_gate.provider_reattempt_required",
            "loop_breaker_packet.provider_reattempt_gate.provider_reattempt_required",
            "packet.loop_breaker_packet.provider_reattempt_gate.provider_reattempt_required",
        )
    )
    mitigation_required = truthy(
        first_value(
            state.stage,
            "provider_mitigation_required",
            "packet.provider_mitigation_required",
            "provider_reattempt_gate.provider_mitigation_required",
            "packet.provider_reattempt_gate.provider_mitigation_required",
            "loop_breaker_packet.provider_reattempt_gate.provider_mitigation_required",
            "packet.loop_breaker_packet.provider_reattempt_gate.provider_mitigation_required",
        )
    )
    seal_allowed = first_value(
        state.stage,
        "provider_terminal_seal_allowed",
        "packet.provider_terminal_seal_allowed",
        "provider_reattempt_gate.provider_terminal_seal_allowed",
        "packet.provider_reattempt_gate.provider_terminal_seal_allowed",
        "loop_breaker_packet.provider_reattempt_gate.provider_terminal_seal_allowed",
        "packet.loop_breaker_packet.provider_reattempt_gate.provider_terminal_seal_allowed",
    )
    terminal = terminal_blocker(state)
    if reattempt_required and terminal:
        state.add(
            "block",
            "provider_terminal_seal_before_bounded_retry",
            "Transient provider failure with retry authority must not be terminal-blocked before required mitigation retry/probe evidence.",
        )
    if mitigation_required and seal_allowed is False and terminal:
        state.add(
            "block",
            "provider_terminal_seal_before_mitigation_exhausted",
            "Transient provider failure must not be terminal-blocked while required mitigations remain unexhausted.",
        )


def validate_root_axis_gate(state: ValidationContext) -> None:
    if not _applies(state):
        return
    disabled = truthy(
        first_value(
            state.stage,
            "autonomous_retarget_disabled",
            "hard_stop_required",
            "packet.autonomous_retarget_disabled",
            "packet.hard_stop_required",
            "root_axis_gate.autonomous_retarget_disabled",
            "root_axis_gate.hard_stop_required",
            "packet.root_axis_gate.autonomous_retarget_disabled",
            "packet.root_axis_gate.hard_stop_required",
            "loop_breaker_packet.root_axis_gate.autonomous_retarget_disabled",
            "packet.loop_breaker_packet.root_axis_gate.autonomous_retarget_disabled",
        )
    )
    terminal = terminal_blocker(state)
    progress_kind = next_progress_kind(state)
    if (
        disabled
        and not terminal
        and progress_kind
        and progress_kind != "goal_productive"
    ):
        state.add(
            "block",
            "autonomous_retarget_disabled_unhandled",
            "A root-axis hard stop allows only goal-productive derivation or terminal/user-escalation state.",
            {"progress_kind": progress_kind},
        )
    elif disabled and not terminal and not progress_kind:
        state.add(
            "warn",
            "autonomous_retarget_disabled_requires_disposition",
            "Derive must handle the root-axis hard stop by selecting goal-productive work or recording terminal/user-escalation state.",
        )


def validate_gt_constraint_conflict(state: ValidationContext) -> None:
    if not _applies(state):
        return
    conflict = truthy(
        first_value(
            state.stage,
            "gt_constraint_conflict_packet.requires_conflict_resolution_task",
            "gt_constraint_conflict_packet.status",
            "packet.gt_constraint_conflict_packet.requires_conflict_resolution_task",
            "packet.gt_constraint_conflict_packet.status",
            "loop_breaker_packet.gt_constraint_conflict_packet.requires_conflict_resolution_task",
            "packet.loop_breaker_packet.gt_constraint_conflict_packet.requires_conflict_resolution_task",
        )
    )
    resolves = truthy(
        first_value(
            state.stage,
            "resolves_gt_constraint_conflict",
            "conflict_resolution_task_selected",
            "packet.resolves_gt_constraint_conflict",
            "packet.conflict_resolution_task_selected",
            "derive.resolves_gt_constraint_conflict",
            "result.resolves_gt_constraint_conflict",
        )
    )
    selected_kind = str(
        first_value(
            state.stage,
            "selected_task_kind",
            "packet.selected_task_kind",
            "derive.selected_task_kind",
            "result.selected_task_kind",
        )
        or ""
    ).lower()
    if selected_kind in {
        "gt_constraint_conflict_resolution",
        "conflict_resolution",
        "authority_conflict_resolution",
    }:
        resolves = True
    terminal = terminal_blocker(state)
    progress_kind = next_progress_kind(state)
    if conflict and not terminal and progress_kind and not resolves:
        state.add(
            "block",
            "gt_constraint_conflict_unhandled",
            "A GT/task constraint conflict requires explicit conflict-resolution, contradiction-removing work, or terminal/user-escalation state.",
            {"selected_task_kind": selected_kind or None},
        )
    elif conflict and not terminal and not progress_kind and not resolves:
        state.add(
            "warn",
            "gt_constraint_conflict_requires_disposition",
            "Derive must handle the GT/task constraint conflict before writing another task.",
        )


def validate_sealing_direction(state: ValidationContext) -> None:
    if not _applies(state):
        return
    terminal = terminal_blocker(state)
    alternative_exists = _alternative_truth(state, "authorized_alternative_path_exists")
    alternative_path = _alternative_value(state, "authorized_alternative_path")
    gt_allowed = _alternative_truth(state, "alternative_in_gt_allowed")
    attempted = _alternative_truth(state, "gt_allowed_alternative_attempted")
    evidence_paths = list_value(
        _alternative_value(state, "gt_allowed_alternative_evidence_paths")
    )
    if terminal and alternative_exists and not alternative_path:
        state.add(
            "block",
            "seal_authorized_alternative_path_missing",
            "Terminal/seal state with an authorized alternative must name `authorized_alternative_path`.",
        )
    if terminal and alternative_exists and not gt_allowed:
        state.add(
            "block",
            "seal_alternative_not_gt_allowed",
            "The authorized alternative must be derived from `.agent_goal` allowed/required actions before terminal/seal state is accepted.",
            {"authorized_alternative_path": alternative_path},
        )
    if terminal and alternative_exists and gt_allowed and not attempted:
        state.add(
            "block",
            "seal_gt_allowed_alternative_unattempted",
            "A GT-allowed productive alternative must be attempted before terminal/seal state is accepted.",
            {"authorized_alternative_path": alternative_path},
        )
    if (
        terminal
        and alternative_exists
        and gt_allowed
        and attempted
        and not evidence_paths
    ):
        state.add(
            "block",
            "seal_gt_allowed_alternative_evidence_missing",
            "A GT-allowed alternative attempt must cite evidence paths before terminal/seal state is accepted.",
            {"authorized_alternative_path": alternative_path},
        )


def validate_command_surface_budget(state: ValidationContext) -> None:
    if not _applies(state):
        return
    required = truthy(
        first_value(
            state.stage,
            "command_surface_budget.consolidation_candidate_required",
            "packet.command_surface_budget.consolidation_candidate_required",
            "loop_breaker_packet.command_surface_budget.consolidation_candidate_required",
            "packet.loop_breaker_packet.command_surface_budget.consolidation_candidate_required",
        )
    )
    scope = (
        str(
            first_value(
                state.stage,
                "command_surface_budget.decision_scope",
                "packet.command_surface_budget.decision_scope",
                "global_aggregate.decision_scope",
                "packet.global_aggregate.decision_scope",
            )
            or ""
        )
        .strip()
        .lower()
    )
    hard_gate = first_value(
        state.stage,
        "command_surface_budget.hard_gate",
        "packet.command_surface_budget.hard_gate",
        "global_aggregate.hard_gate",
        "packet.global_aggregate.hard_gate",
    )
    constrains = first_value(
        state.stage,
        "command_surface_budget.constrains_current_family",
        "packet.command_surface_budget.constrains_current_family",
        "global_aggregate.constrains_current_family",
        "packet.global_aggregate.constrains_current_family",
    )
    constrains_current = (
        scope != "global_dashboard"
        and (hard_gate is None or truthy(hard_gate))
        and (constrains is None or truthy(constrains))
    )
    registered = truthy(
        first_value(
            state.stage,
            "consolidation_candidate_registered",
            "packet.consolidation_candidate_registered",
            "command_surface_budget.consolidation_candidate_registered",
            "packet.command_surface_budget.consolidation_candidate_registered",
        )
    )
    if (
        required
        and constrains_current
        and not registered
        and not terminal_blocker(state)
        and next_progress_kind(state) != "goal_productive"
    ):
        state.add(
            "block",
            "command_surface_budget_unhandled",
            "Command-surface budget requires a consolidation candidate/task unless derive selects goal-productive work or terminal state.",
        )


def _alternative_value(state: ValidationContext, field: str):
    return first_value(
        state.stage,
        field,
        f"terminal_blocker.{field}",
        f"packet.{field}",
        f"packet.terminal_blocker.{field}",
        f"sealing_direction_guard.{field}",
        f"packet.sealing_direction_guard.{field}",
    )


def _alternative_truth(state: ValidationContext, field: str) -> bool:
    return truthy(_alternative_value(state, field))


def _applies(state: ValidationContext) -> bool:
    return state.transition in PROGRESS_TRANSITIONS
