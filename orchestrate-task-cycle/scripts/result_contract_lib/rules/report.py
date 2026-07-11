from __future__ import annotations

from ..base import RuleContext, TargetContractRule
from ..common import add, task_pack_in_scope, value_for


SUCCESSFUL_CLOSURE_STATUSES = {
    "issue": {"closed", "complete", "completed", "created", "not_applicable", "open", "reopened", "resolved", "skipped", "tracked", "updated"},
    "derive": {"complete", "completed", "not_applicable", "ok", "pass", "passed", "skipped", "success"},
    "commit": {"committed", "complete", "completed", "created", "not_applicable", "pass", "passed", "skipped", "success"},
    "dashboard": {"complete", "completed", "ok", "pass", "passed", "rendered", "success", "warn"},
}


def command_passed(value: object) -> bool:
    lowered = str(value).strip().lower()
    if any(token in lowered for token in ("failed", "failure", "error", "blocked", "not passed", "not_run", "unknown", "exit_code=1", "exit 1")):
        return False
    return any(
        token in lowered
        for token in (": pass", ": passed", ": ok", ": success", ": complete", ": completed", " exit_code=0", " exit 0", " passed")
    )


class ReportRule(TargetContractRule):
    """Validate report-only context that becomes required in task-pack scope."""

    targets = frozenset({'report'})

    def check(self, context: RuleContext) -> None:
        result = context.result
        findings = context.findings
        require_context_field = context.require_context_field
        completion_status = str(value_for(result, "completion_status") or "").lower()
        validation_verdict = str(value_for(result, "validation_verdict") or "").lower()
        progress_verdict = str(value_for(result, "progress_verdict") or "").lower()
        task_id = str(value_for(result, "task_id") or "").lower()
        next_task_id = str(value_for(result, "next_task_id") or "").lower()
        selected_task_source = str(value_for(result, "selected_task_source") or "").lower()
        commands = value_for(result, "commands")
        progress_axes = value_for(result, "progress_axes")
        evidence_paths = value_for(result, "evidence_paths")
        closure_steps = value_for(result, "closure_steps")
        closure_records = value_for(result, "closure_records")
        blockers = value_for(result, "blockers")
        report_findings = value_for(result, "report_findings")
        if completion_status not in {"complete_verified", "not_complete"}:
            add(findings, "block", "invalid_report_completion_status", "Report completion status must be complete_verified or not_complete.")
        if not isinstance(blockers, list):
            add(findings, "block", "report_blockers_not_list", "Report blockers must be an explicit JSON list, including [] when clear.")
        if report_findings is not None and not isinstance(report_findings, list):
            add(findings, "block", "report_findings_not_list", "Report findings must be a JSON list when supplied.")
        elif isinstance(report_findings, list):
            for finding in report_findings:
                if isinstance(finding, dict) and finding.get("severity") == "block":
                    add(
                        findings,
                        "block",
                        str(finding.get("code") or "report_input_blocked"),
                        str(finding.get("message") or "Report assembly input contract is blocked."),
                        finding.get("missing") or finding.get("evidence"),
                    )
        if completion_status == "complete_verified" and (
            validation_verdict not in {"complete", "passed", "pass", "success"}
            or progress_verdict != "advanced"
            or not isinstance(blockers, list)
            or bool(blockers)
        ):
            add(
                findings,
                "block",
                "report_complete_verified_inconsistent",
                "complete_verified requires a complete/pass validation verdict, advanced progress, and an empty blocker list.",
            )
        if completion_status == "complete_verified":
            incomplete: list[str] = []
            if task_id in {"", "unknown-task", "none", "null"}:
                incomplete.append("task_id")
            if next_task_id in {"", "unknown-task", "none", "null"} and selected_task_source not in {
                "terminal_blocked",
                "user_escalation",
                "final_goal_complete",
            }:
                incomplete.append("next_task_id_or_terminal_disposition")
            if not isinstance(commands, list) or not commands or not all(command_passed(item) for item in commands):
                incomplete.append("commands")
            if not isinstance(progress_axes, (list, dict)) or not progress_axes or progress_axes == ["not_recorded"]:
                incomplete.append("progress_axes")
            if not isinstance(evidence_paths, list) or not any(str(path) != "stdout:assemble_cycle_report" for path in evidence_paths):
                incomplete.append("validation_evidence_paths")
            required_closure = {"issue", "derive", "commit", "dashboard"}
            if not isinstance(closure_steps, list) or not required_closure <= {str(step) for step in closure_steps}:
                incomplete.append("closure_steps")
            if not isinstance(closure_records, list):
                incomplete.append("closure_records")
            else:
                for step in sorted(required_closure):
                    candidates = [record for record in closure_records if isinstance(record, dict) and record.get("step") == step]
                    if step == "commit" and any(record.get("source") == "commit_input" for record in candidates):
                        candidates = [record for record in candidates if record.get("source") == "commit_input"]
                    bound = [
                        record
                        for record in candidates
                        if str(record.get("task_id") or "").strip().lower() == task_id
                    ]
                    if not bound:
                        incomplete.append(f"{step}_closure_task_binding")
                    elif not any(
                        str(record.get("status") or "").strip().lower() in SUCCESSFUL_CLOSURE_STATUSES[step]
                        for record in bound
                    ):
                        incomplete.append(f"{step}_closure_status")
                    elif step == "commit" and any(
                        str(record.get("status") or "").strip().lower() in {"skipped", "not_applicable"}
                        and not str(record.get("reason") or "").strip()
                        for record in bound
                    ):
                        incomplete.append("commit_closure_reason")
            if incomplete:
                add(
                    findings,
                    "block",
                    "report_complete_verified_evidence_missing",
                    "complete_verified requires substantive task, validation, and close-phase evidence.",
                    {"missing": incomplete},
                )
        if task_pack_in_scope(result):
            require_context_field("task_pack_status", "report_task_pack_status_missing", "`report` result references task-pack evidence but lacks `task_pack_status`.")
            require_context_field("task_pack_path", "report_task_pack_path_missing", "`report` result references task-pack evidence but lacks `task_pack_path`.")
            require_context_field("task_pack_item_id", "report_task_pack_item_id_missing", "`report` result references task-pack evidence but lacks `task_pack_item_id` or `promoted_item_id`.")
