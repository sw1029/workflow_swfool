from __future__ import annotations

from typing import Any

from ..base import RuleContext, TargetContractRule
from ..common import add, non_empty, value_for


ISSUE_STATUSES = {
    "blocked",
    "closed",
    "created",
    "failed",
    "not_applicable",
    "open",
    "partial",
    "reopened",
    "resolved",
    "skipped",
    "tracked",
    "updated",
}


def _has_issue_identifier(result: dict[str, Any]) -> bool:
    for field in ("issue_id", "issue_ids", "issue_path", "issue_paths", "issue_url", "issue_urls"):
        if non_empty(value_for(result, field)):
            return True
    return False


class IssueRule(TargetContractRule):
    """Require validation provenance and durable identity for issue lifecycle mutations."""

    targets = frozenset({"issue"})

    def check(self, context: RuleContext) -> None:
        result = context.result
        findings = context.findings
        task_id = str(value_for(result, "task_id") or "").strip()
        status = str(value_for(result, "issue_status") or "").strip().lower()
        provenance = value_for(result, "issue_provenance")

        if status not in ISSUE_STATUSES:
            add(
                findings,
                "block",
                "invalid_issue_status",
                "Issue status is outside the documented closed lifecycle vocabulary.",
                {"issue_status": status, "allowed": sorted(ISSUE_STATUSES)},
            )

        if not isinstance(provenance, dict):
            add(
                findings,
                "block",
                "issue_provenance_missing",
                "Issue handling must cite the validation result and task identity that authorized the lifecycle decision.",
            )
        else:
            source_task_id = str(provenance.get("source_task_id") or "").strip()
            if not source_task_id:
                add(findings, "block", "issue_source_task_id_missing", "Issue provenance must include `source_task_id`.")
            elif task_id and source_task_id != task_id:
                add(
                    findings,
                    "block",
                    "issue_task_identity_mismatch",
                    "Issue provenance belongs to a different task.",
                    {"task_id": task_id, "source_task_id": source_task_id},
                )
            if not (non_empty(provenance.get("validation_id")) or non_empty(provenance.get("validation_report_path"))):
                add(
                    findings,
                    "block",
                    "issue_validation_provenance_missing",
                    "Issue handling must cite `validation_id` or `validation_report_path` from the completed validation stage.",
                )

        mutation_statuses = {"created", "updated", "open", "tracked", "closed", "resolved", "reopened"}
        if status in mutation_statuses and not _has_issue_identifier(result):
            add(
                findings,
                "block",
                "issue_identifier_missing",
                "Issue lifecycle mutation must name a durable local or remote issue identifier/path.",
                {"issue_status": status},
            )
        if status in {"closed", "resolved"} and not (
            non_empty(value_for(result, "resolution_evidence_paths")) or non_empty(value_for(result, "resolved_by"))
        ):
            add(
                findings,
                "block",
                "issue_resolution_provenance_missing",
                "Issue closure requires resolution evidence or a `resolved_by` artifact id.",
            )
        if status in {"skipped", "not_applicable"} and not non_empty(value_for(result, "issue_skipped_reason")):
            add(
                findings,
                "block",
                "issue_skipped_reason_missing",
                "Skipped issue handling requires an explicit reason.",
            )
