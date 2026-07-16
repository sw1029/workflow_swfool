from __future__ import annotations

from .access import deep_get
from .context import ValidationContext
from .evidence import (
    context_active_advice,
    context_goal_truth,
    stage_advice_handling_rationale,
    stage_authority_policy,
    stage_goal_truth,
    stage_used_advice,
)


def validate_authority_and_advice(state: ValidationContext) -> None:
    goal_truth = context_goal_truth(state.context)
    authority = stage_authority_policy(state.stage)
    if goal_truth and not authority:
        state.add(
            "warn",
            "authority_policy_missing",
            "Goal-truth files exist but the stage packet has no authority policy. Use `.agent_goal/agent_authority.md` or `default_current_agent_permissions`.",
        )
    if authority and "default_current_agent_permissions" in str(authority):
        agent_authority = deep_get(
            state.context,
            "agent_goal",
            "goal_truth_files",
            "agent_authority.md",
            "exists",
        )
        if not agent_authority:
            state.add(
                "warn",
                "authority_default_fallback",
                "Using `default_current_agent_permissions` because `.agent_goal/agent_authority.md` is absent.",
                {"authority_policy": authority},
            )
    stage_truth = stage_goal_truth(state.stage)
    if goal_truth and not stage_truth:
        state.add(
            "warn",
            "goal_truth_usage_missing",
            "The stage packet does not list `.agent_goal` GT files used.",
        )
    elif goal_truth:
        missing = sorted(set(goal_truth) - set(stage_truth))
        if missing:
            state.add(
                "warn",
                "goal_truth_usage_incomplete",
                "The stage packet omits some available `.agent_goal` GT files.",
                {"missing": missing},
            )
    _validate_advice(state, stage_truth)


def _validate_advice(state: ValidationContext, stage_truth: list[str]) -> None:
    active = context_active_advice(state.context)
    used = stage_used_advice(state.stage)
    if active and not used:
        rationale = stage_advice_handling_rationale(state.stage)
        if rationale:
            state.add(
                "warn",
                "external_advice_deferred_with_rationale",
                "Active `.agent_advice/active` documents exist and the stage records an explicit advice handling rationale instead of `used_advice`.",
                {"rationale": rationale},
            )
        else:
            state.add(
                "block",
                "external_advice_usage_missing",
                "Active `.agent_advice/active` documents exist but the stage packet does not list `used_advice` or an explicit advice defer/reject/not-applicable rationale.",
            )
    if used:
        advice_in_truth = [path for path in used if path in stage_truth]
        if advice_in_truth or any(".agent_advice/" in path for path in stage_truth):
            state.add(
                "warn",
                "external_advice_misclassified_as_gt",
                "External advice must be reported separately from `.agent_goal` GT.",
                {"used_advice": used, "used_goal_truth": stage_truth},
            )
