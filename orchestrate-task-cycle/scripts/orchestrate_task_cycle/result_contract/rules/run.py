from __future__ import annotations

from ..base import RuleContext, TargetContractRule
from ..common import (
    LONG_RUN_REQUIRED_FIELDS,
    LONG_RUN_ROLES,
    LONG_RUN_STATUSES,
    RUNNING_FIELDS,
    add,
    boolish,
    command_summary_omitted,
    first_present,
    has_value,
    non_empty,
    recursive_key_present,
    value_for,
)
from ..scenario_receipts import assess_scenario_receipts
from .run_cycle_reachability import check_cycle_reachability_run


def _check_scenario_receipts(context: RuleContext) -> None:
    for issue in assess_scenario_receipts(context.result).receipt_issues:
        add(
            context.findings,
            "block" if context.mode == "block" else "warn",
            "run_scenario_receipt_malformed",
            "A declared scenario premise receipt must preserve a structured actual invocation; coverage booleans are not receipt evidence.",
            issue.evidence(),
        )


def _check_running_and_long_run(context: RuleContext, execution_status: str) -> None:
    result = context.result
    findings = context.findings
    if execution_status == "running":
        for field in (item for item in RUNNING_FIELDS if not has_value(result, item)):
            add(
                findings,
                "block",
                "running_detail_missing",
                f"`running` execution requires `{field}`.",
                {"field": field},
            )
    long_run_branch = boolish(
        first_present(
            result,
            [
                "long_run_branch",
                "run.long_run_branch",
                "monitor_result.long_run_branch",
            ],
        )
    )
    if not long_run_branch:
        return
    long_run_role = str(
        first_present(
            result,
            ["long_run_role", "run.long_run_role", "monitor_result.long_run_role"],
        )
        or ""
    ).lower()
    event_kind = str(
        first_present(
            result, ["event_kind", "run.event_kind", "monitor_result.event_kind"]
        )
        or ""
    ).lower()
    for field in (
        item for item in LONG_RUN_REQUIRED_FIELDS if not has_value(result, item)
    ):
        add(
            findings,
            "block",
            "long_run_detail_missing",
            f"`long_run_branch=true` requires `{field}`.",
            {"field": field},
        )
    if long_run_role not in LONG_RUN_ROLES:
        add(
            findings,
            "block",
            "long_run_role_invalid",
            "`long_run_branch=true` requires long_run_role launch|monitor|harvest|finalize.",
            {"long_run_role": long_run_role or None},
        )
    if execution_status and execution_status not in LONG_RUN_STATUSES:
        add(
            findings,
            "block",
            "long_run_execution_status_invalid",
            "`long_run_branch=true` execution_status must be launching, running, completed_pending_validation, stale, not_running, failed, or success.",
            {"execution_status": execution_status},
        )
    if event_kind and event_kind not in {
        "long_run_launch",
        "long_run_monitor",
        "long_run_harvest",
        "long_run_finalize",
    }:
        add(
            findings,
            "warn",
            "long_run_event_kind_noncanonical",
            "Long-running run events should use event_kind long_run_launch|long_run_monitor|long_run_harvest|long_run_finalize while keeping step=run.",
            {"event_kind": event_kind},
        )
    if execution_status in {
        "running",
        "launching",
        "completed_pending_validation",
        "stale",
        "not_running",
    }:
        validation_verdict = str(value_for(result, "validation_verdict") or "").lower()
        progress_verdict = str(value_for(result, "progress_verdict") or "").lower()
        if (
            validation_verdict in {"complete", "passed", "success"}
            or progress_verdict == "advanced"
        ):
            add(
                findings,
                "block",
                "long_run_incomplete_claimed_complete",
                "Long-running launch/monitor/completed-pending-validation evidence cannot consume completion or advanced progress before harvest validation.",
                {
                    "execution_status": execution_status,
                    "validation_verdict": validation_verdict or None,
                    "progress_verdict": progress_verdict or None,
                },
            )


def _check_command_provenance(context: RuleContext, execution_status: str) -> None:
    result = context.result
    live_execution = boolish(
        first_present(
            result,
            [
                "live_execution",
                "live_execution_required",
                "live_run",
                "run.live_execution",
                "run.live_execution_required",
            ],
        )
    )
    if not live_execution:
        live_execution = execution_status not in {
            "",
            "not_applicable",
            "skipped",
            "blocked_no_execution",
            "no_execution",
        }
    command_argv = first_present(
        result,
        [
            "command_argv",
            "run.command_argv",
            "execution.command_argv",
            "command_provenance_gate.command_argv",
            "result.command_argv",
        ],
    )
    missing = boolish(
        first_present(
            result,
            [
                "command_provenance_missing",
                "command_provenance_gate.command_provenance_missing",
                "run.command_provenance_missing",
                "result.command_provenance_gate.command_provenance_missing",
            ],
        )
    )
    if live_execution and not non_empty(command_argv) and not missing:
        add(
            context.findings,
            "block" if context.mode == "block" else "warn",
            "run_command_argv_or_missing_flag_required",
            "`run` must preserve full body-free command_argv for live execution, or explicitly set command_provenance_missing=true.",
        )
    if live_execution and command_summary_omitted(result) and not missing:
        add(
            context.findings,
            "block" if context.mode == "block" else "warn",
            "run_command_summary_ellipsis_without_missing_provenance",
            "`run` command evidence contains an ellipsis or summarized command; set command_provenance_missing=true unless full argv is also preserved.",
        )


def _check_blocker_actionability(context: RuleContext) -> None:
    result = context.result
    blocker_reason_present = recursive_key_present(
        first_present(
            result, ["blockers", "blocking_findings", "run.blockers", "result.blockers"]
        )
        or result,
        {"reason_code", "blocker_reason_code", "blocker_reason"},
    )
    actionable_present = recursive_key_present(
        result,
        {
            "blocker_actionability",
            "violated_relation",
            "observed_values",
            "expected_relation",
            "minimum_input_delta",
        },
    )
    blocker_opacity = boolish(
        first_present(
            result,
            [
                "blocker_opacity",
                "blocker_actionability_gate.blocker_opacity",
                "run.blocker_opacity",
                "result.blocker_actionability_gate.blocker_opacity",
            ],
        )
    )
    if blocker_reason_present and not actionable_present and not blocker_opacity:
        add(
            context.findings,
            "block" if context.mode == "block" else "warn",
            "run_blocker_reason_without_actionability_or_opacity",
            "`run` blocker reason codes must include violated relation, observed scalar values, expected relation, or minimum input delta; otherwise preserve blocker_opacity=true.",
        )


class RunRule(TargetContractRule):
    """Validate execution, command provenance, and long-run handoff evidence."""

    targets = frozenset({"run"})

    def check(self, context: RuleContext) -> None:
        check_cycle_reachability_run(context)
        execution_status = context.get("execution_status", "")
        _check_running_and_long_run(context, execution_status)
        _check_command_provenance(context, execution_status)
        _check_blocker_actionability(context)
        _check_scenario_receipts(context)
