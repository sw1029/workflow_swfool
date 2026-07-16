from __future__ import annotations

from .access import first_value, status_for_step, step_event, text_blob
from .context import ValidationContext
from .evidence import active_long_run_events


def validate_execution_status(state: ValidationContext) -> None:
    execution_status = str(
        first_value(state.stage, "execution_status", "run_log.status") or ""
    ).lower()
    verdict = validation_verdict(state)
    startup_sufficient = bool(
        first_value(
            state.stage,
            "startup_evidence_satisfies_success",
            "run_log.startup_evidence_satisfies_success",
        )
    )
    if state.transition == "pre_issue" and not verdict:
        state.add(
            "block",
            "pre_issue_missing_validation_verdict",
            "Issue lifecycle handling requires the current-task completion validation verdict.",
        )
    if execution_status != "running" or startup_sufficient:
        return
    blob = text_blob(state.stage)
    if verdict in {"complete", "passed", "success"} or any(
        word in blob for word in ("running success", "execution success")
    ):
        state.add(
            "block",
            "running_misclassified_success",
            "`running` execution was classified as success without explicit startup/heartbeat success criteria.",
        )
    elif state.transition in {"pre_commit", "pre_report", "pre_closeout_commit"}:
        state.add(
            "warn",
            "running_execution_incomplete",
            "`running` execution is in-progress evidence and normally supports only partial validation.",
        )


def validate_pending_long_runs(state: ValidationContext) -> None:
    pending = active_long_run_events(state.stage)
    if not pending:
        return
    summary = [
        {
            "run_id": event.get("run_id"),
            "task_id": event.get("task_id") or event.get("owner_task_id"),
            "execution_status": event.get("execution_status")
            or event.get("source_status")
            or event.get("status"),
            "event_kind": event.get("event_kind"),
            "remaining_validation": event.get("remaining_validation"),
        }
        for event in pending[-3:]
    ]
    final_output_dependent = {
        "pre_qualitative_review",
        "pre_loopback_audit",
        "pre_validation_set_build",
        "pre_schema_pre_derive",
        "pre_derive",
    }
    if state.transition in final_output_dependent:
        state.add(
            "block",
            "long_run_pending_final_output_phase",
            "Pending long-running execution cannot advance to final-output-dependent review, loopback, validation-set build, schema refresh, or derive; record a partial handoff and resume through monitor/harvest.",
            {"pending_long_runs": summary},
        )
    if state.transition == "pre_validate":
        state.add(
            "warn",
            "long_run_pending_partial_validation_only",
            "Pending long-running execution permits only a partial handoff validation; pass/advanced and downstream derive or promotion remain blocked until harvest validation.",
            {"pending_long_runs": summary},
        )
    if state.transition in {
        "pre_issue",
        "pre_commit",
        "pre_report",
        "pre_closeout_commit",
    }:
        verdict = validation_verdict(state)
        progress = str(first_value(state.stage, "progress_verdict") or "").lower()
        if verdict in {"complete", "passed", "success"} or progress == "advanced":
            state.add(
                "block",
                "long_run_pending_claimed_complete",
                "Pending long-running execution can support only partial/not_complete reporting until harvest validation consumes terminal artifacts.",
                {
                    "pending_long_runs": summary,
                    "validation_verdict": verdict or None,
                },
            )


def validate_commit_readiness(state: ValidationContext) -> None:
    if state.transition != "pre_commit":
        return
    verdict = validation_verdict(state)
    if not verdict:
        state.add(
            "block",
            "pre_commit_missing_validation",
            "`$repo-change-commit` cannot run before `$validate-task-completion` returns a verdict.",
        )
    issue_status = status_for_step(state.stage, "issue")
    if issue_status is None:
        state.add(
            "warn",
            "issue_tracking_not_recorded",
            "Issue tracking status is not recorded before commit.",
        )
    elif issue_status in {"skipped", "not_applicable"}:
        issue_event = step_event(state.stage, "issue")
        if not (issue_event.get("reason") or issue_event.get("issue_skipped_reason")):
            state.add(
                "block",
                "issue_skipped_reason_missing",
                "Skipped issue tracking requires a reason before commit.",
            )
    intent = str(
        first_value(state.stage, "commit_intent", "commit.intent") or ""
    ).lower()
    if verdict == "partial" and "partial" not in intent and "checkpoint" not in intent:
        state.add(
            "block",
            "partial_commit_intent_missing",
            "Partial validation requires explicit partial/checkpoint commit intent.",
        )
    if verdict in {"failed", "block", "blocked"} and "force" not in intent:
        state.add(
            "block",
            "failed_commit_blocked",
            "Failed or blocked validation cannot be committed without explicit user authorization.",
        )


def validate_report_readiness(state: ValidationContext) -> None:
    if state.transition in {"pre_report", "pre_closeout_commit"}:
        status = (
            status_for_step(state.stage, "commit")
            or str(
                first_value(state.stage, "commit_status", "commit.status") or ""
            ).lower()
        )
        event = step_event(state.stage, "commit")
        skipped_reason = (
            first_value(
                state.stage,
                "commit_skipped_reason",
                "commit.commit_skipped_reason",
            )
            or event.get("reason")
            or event.get("commit_skipped_reason")
        )
        if (
            status in {"skipped", "not_applicable", "blocked", "failed"}
            and not skipped_reason
        ):
            state.add(
                "block",
                "commit_skipped_reason_missing",
                "Skipped/blocked/failed commit finalization requires a concrete reason in the report packet.",
            )
        if not status:
            state.add(
                "warn",
                "commit_status_missing",
                "Commit finalization status is missing before final report.",
            )
    if state.transition == "pre_closeout_commit":
        artifacts = first_value(
            state.stage,
            "tracked_artifacts",
            "closeout_artifacts",
            "closeout_commit.tracked_artifacts",
            "report.tracked_artifacts",
        )
        if not artifacts:
            state.add(
                "warn",
                "closeout_artifacts_missing",
                "Closeout commit should name report/dashboard/current_stage/commit-result/advice artifacts or record why they are local-only.",
            )


def validation_verdict(state: ValidationContext) -> str:
    return str(
        first_value(state.stage, "validation_verdict", "validation.verdict") or ""
    ).lower()
