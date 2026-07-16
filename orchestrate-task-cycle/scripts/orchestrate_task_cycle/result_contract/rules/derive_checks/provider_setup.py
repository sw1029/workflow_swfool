from __future__ import annotations

from .shared import (
    add,
    boolish,
    first_present,
    has_value,
    list_values,
    number_value,
)
from .state import DeriveFacts


def _check_provider_setup_part_01(facts: DeriveFacts) -> None:
    result = facts.result
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
    )
    goal_threshold_status = str(
        first_present(
            result,
            [
                "goal_distance_gate.evaluation_status",
                "goal_distance_gate.budget_evaluation_status",
                "loop_breaker_packet.goal_distance_gate.evaluation_status",
                "result.goal_distance_gate.evaluation_status",
            ],
        )
        or ""
    ).strip().lower()
    goal_threshold_evaluated = goal_threshold is not None and goal_threshold_status == "evaluated"
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
    ) or (
        goal_threshold_evaluated
        and cycles_since_goal_productive is not None
        and cycles_since_goal_productive > goal_threshold
    )
    number_value(
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
    facts.cycles_since_goal_productive = cycles_since_goal_productive
    facts.goal_distance_required = goal_distance_required
    facts.goal_threshold = goal_threshold


def _check_provider_setup_part_02(facts: DeriveFacts) -> None:
    changed_vs_previous = facts.changed_vs_previous
    produced_domain_delta = facts.produced_domain_delta
    result = facts.result
    semantic_progress = facts.semantic_progress
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
    facts.has_supplied_input_delta = has_supplied_input_delta
    facts.new_input_kinds = new_input_kinds
    facts.provider_reattempt_required = provider_reattempt_required
    facts.strict_positive_output_delta = strict_positive_output_delta


def _check_provider_setup_part_03(facts: DeriveFacts) -> None:
    result = facts.result
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
    facts.loop_detector_status = loop_detector_status
    facts.provider_mitigation_required = provider_mitigation_required
    facts.provider_reattempt_disposition = provider_reattempt_disposition
    facts.provider_terminal_seal_allowed = provider_terminal_seal_allowed


def _check_provider_setup_part_04(facts: DeriveFacts) -> None:
    findings = facts.findings
    mode = facts.mode
    result = facts.result
    selected_source = facts.selected_source
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
    facts.seal_requested = seal_requested
    facts.sealed_match = sealed_match
    facts.terminal_or_seal = terminal_or_seal
    facts.terminal_selected = terminal_selected


def _check_provider_setup_part_05(facts: DeriveFacts) -> None:
    findings = facts.findings
    mode = facts.mode
    result = facts.result
    terminal_or_seal = facts.terminal_or_seal
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


def _check_provider_setup_part_06(facts: DeriveFacts) -> None:
    result = facts.result
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
    facts.alternative_in_gt_allowed = alternative_in_gt_allowed
    facts.alternative_in_gt_allowed_value = alternative_in_gt_allowed_value
    facts.authorized_alternative_exists = authorized_alternative_exists
    facts.authorized_alternative_path = authorized_alternative_path
    facts.gt_allowed_alternative_attempted = gt_allowed_alternative_attempted


def check_provider_setup(facts: DeriveFacts) -> None:
    _check_provider_setup_part_01(facts)
    _check_provider_setup_part_02(facts)
    _check_provider_setup_part_03(facts)
    _check_provider_setup_part_04(facts)
    _check_provider_setup_part_05(facts)
    _check_provider_setup_part_06(facts)

