from __future__ import annotations

from ..runtime_dependencies import (
    budget_evaluation,
)

from ..evaluation_frame import _EvaluationFrame


def _prepare_budget_state(frame: _EvaluationFrame) -> None:
    args = frame.require('args')
    budget_evaluations = {
        "same_family_nonsemantic_attempts": budget_evaluation(
            "same_family_nonsemantic_attempts",
            getattr(args, "threshold", None),
            source="caller_or_repository_config",
        ),
        "measurement_nonsemantic_attempts": budget_evaluation(
            "measurement_nonsemantic_attempts",
            getattr(args, "measurement_streak_cap", None),
            source="caller_or_repository_config",
        ),
        "detection_nonsemantic_attempts": budget_evaluation(
            "detection_nonsemantic_attempts",
            getattr(args, "detection_only_streak_cap", None),
            source="caller_or_repository_config",
        ),
        "adapter_mandate_attempts": budget_evaluation(
            "adapter_mandate_attempts",
            getattr(args, "adapter_mandate_streak_cap", None),
            source="caller_or_repository_config",
        ),
        "cumulative_stall_attempts": budget_evaluation(
            "cumulative_stall_attempts",
            getattr(args, "cumulative_chain_streak_cap", None),
            source="caller_or_repository_config",
        ),
        "envelope_thaw_attempts": budget_evaluation(
            "envelope_thaw_attempts",
            getattr(args, "envelope_thaw_streak_cap", None),
            source="caller_or_repository_config",
        ),
        "forward_mutation_attempts": budget_evaluation(
            "forward_mutation_attempts",
            getattr(args, "max_forward_mutations", None),
            source="caller_or_repository_config",
        ),
        "consolidation_nonsemantic_attempts": budget_evaluation(
            "consolidation_nonsemantic_attempts",
            getattr(args, "consolidation_streak_cap", None),
            source="caller_or_repository_config",
        ),
        "root_cause_repair_attempts": budget_evaluation(
            "root_cause_repair_attempts",
            getattr(args, "untried_promotion_budget", None),
            source="caller_or_repository_config",
        ),
        "portfolio_nonsemantic_work": budget_evaluation(
            "portfolio_nonsemantic_work",
            None,
            source=None,
            applicable=False,
        ),
    }
    frame.update({
        "budget_evaluations": budget_evaluations,
    })
