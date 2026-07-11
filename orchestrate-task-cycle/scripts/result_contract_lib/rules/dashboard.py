from __future__ import annotations

from ..base import RuleContext, TargetContractRule
from ..common import add, value_for


DASHBOARD_STATUSES = {"rendered", "warn", "partial", "block"}
SNAPSHOT_STATUSES = {"current", "stale", "missing", "malformed"}


class DashboardRule(TargetContractRule):
    """Validate dashboard snapshot accounting without turning it into completion truth."""

    targets = frozenset({"dashboard"})

    def check(self, context: RuleContext) -> None:
        result = context.result
        findings = context.findings
        status = str(value_for(result, "dashboard_status") or "").lower()
        snapshot_status = str(value_for(result, "snapshot_status") or "").lower()
        event_count = value_for(result, "event_count")
        current_count = value_for(result, "current_stage_event_count")
        ledger_latest_event_id = str(value_for(result, "ledger_latest_event_id") or "").strip()
        current_latest_event_id = str(value_for(result, "current_stage_latest_event_id") or "").strip()

        if status not in DASHBOARD_STATUSES:
            add(findings, "block", "invalid_dashboard_status", "Dashboard status is outside the closed lifecycle vocabulary.", {"dashboard_status": status})
        if snapshot_status not in SNAPSHOT_STATUSES:
            add(findings, "block", "invalid_dashboard_snapshot_status", "Dashboard snapshot status is invalid.", {"snapshot_status": snapshot_status})
        if isinstance(event_count, bool) or not isinstance(event_count, int) or event_count < 0:
            add(findings, "block", "invalid_dashboard_event_count", "Dashboard event_count must be a non-negative integer.")
        if "current_stage_event_count" not in result:
            add(findings, "block", "dashboard_current_count_omitted", "Dashboard must preserve current_stage_event_count explicitly, including null when unavailable.")
        elif current_count is not None and (isinstance(current_count, bool) or not isinstance(current_count, int) or current_count < 0):
            add(findings, "block", "invalid_dashboard_current_count", "current_stage_event_count must be a non-negative integer or null.")
        if snapshot_status == "current" and event_count != current_count:
            add(findings, "block", "dashboard_snapshot_count_mismatch", "A current dashboard snapshot must match the ledger event count.")
        if snapshot_status == "current" and (ledger_latest_event_id or current_latest_event_id) and ledger_latest_event_id != current_latest_event_id:
            add(findings, "block", "dashboard_snapshot_latest_event_mismatch", "A current dashboard snapshot must match the ledger's latest event ID.")
        if status == "rendered" and snapshot_status != "current":
            add(findings, "block", "dashboard_rendered_from_noncurrent_snapshot", "A non-current snapshot must use warn/partial status.")
        if status == "rendered" and isinstance(event_count, int) and event_count == 0:
            add(findings, "block", "dashboard_empty_rendered", "An empty ledger cannot produce an unqualified rendered dashboard.")
