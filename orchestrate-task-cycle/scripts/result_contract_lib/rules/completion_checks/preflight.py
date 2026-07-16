from __future__ import annotations

from .shared import (
    add,
    first_present,
    value_for,
)
from .state import CompletionFacts


def check_preflight(facts: CompletionFacts) -> None:
    context = facts.context
    result = facts.result
    mode = facts.mode
    findings = facts.findings
    result = context.result
    mode = context.mode
    findings = context.findings
    validation_verdict = str(value_for(result, "validation_verdict") or "").strip().lower()
    progress_verdict = str(value_for(result, "progress_verdict") or "").strip().lower()
    pending_long_runs = context.get("pending_long_runs", [])
    completion_claimed = validation_verdict in {"complete", "completed", "passed", "pass", "success"} or progress_verdict == "advanced"
    index_status = str(
        first_present(
            result,
            [
                "index_status",
                "pre_validation_index.index_status",
                "task_state_index.index_status",
                "result.pre_validation_index.index_status",
            ],
        )
        or ""
    ).strip().lower()
    projection_status = str(
        first_present(
            result,
            [
                "current_projection_status",
                "pre_validation_index.current_projection_status",
                "task_state_index.current_projection_status",
                "result.pre_validation_index.current_projection_status",
            ],
        )
        or ""
    ).strip().lower()
    projection_completeness = str(
        first_present(
            result,
            [
                "projection_completeness",
                "pre_validation_index.projection_completeness",
                "task_state_index.projection_completeness",
                "result.pre_validation_index.projection_completeness",
            ],
        )
        or ""
    ).strip().lower()
    historical_axis = first_present(result, ["historical_index_verdict", "verdict_axes.historical_index_verdict"])
    historical_status = str(
        historical_axis.get("status") or historical_axis.get("verdict") or ""
        if isinstance(historical_axis, dict)
        else historical_axis or ""
    ).strip().lower()
    projection_not_evaluated = projection_status in {"not_evaluated", "missing", "unknown"} or projection_completeness in {"incomplete", "not_evaluated", "missing", "unknown"}
    if projection_not_evaluated and (index_status in {"pass", "passed", "ok"} or historical_status == "pass" or completion_claimed):
        add(
            findings,
            "block" if mode == "block" else "warn",
            "historical_index_projection_not_evaluated",
            "Index pass, goal readiness, or completion cannot consume a malformed/incomplete current projection; preserve historical identity as not_evaluated.",
            {
                "index_status": index_status or None,
                "current_projection_status": projection_status or None,
                "projection_completeness": projection_completeness or None,
            },
        )
    if completion_claimed and not context.get("long_run_state_checked", False):
        add(
            findings,
            "block",
            "long_run_state_not_checked",
            "Pass/advanced validation requires explicit proof that current long-run state was checked.",
        )
    if pending_long_runs and completion_claimed:
        add(
            findings,
            "block",
            "pending_long_run_validate_overclaim",
            "Pending long-running execution can support only partial/not-complete validation until terminal artifacts are harvested and validated.",
            {
                "pending_long_runs": pending_long_runs,
                "validation_verdict": validation_verdict or None,
                "progress_verdict": progress_verdict or None,
            },
        )
    
    facts.validation_verdict = validation_verdict
    facts.progress_verdict = progress_verdict
