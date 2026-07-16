from __future__ import annotations

from ..base import RuleContext, TargetContractRule
from ..common import add, first_present, has_value, non_empty, value_for


class SchemaPostDeriveRule(TargetContractRule):
    """Allow honest terminal/skip reconciliation without inventing a next task."""

    targets = frozenset({"schema_post_derive"})

    def check(self, context: RuleContext) -> None:
        result = context.result
        status = str(value_for(result, "schema_status") or value_for(result, "status") or "").strip().lower()
        terminal_statuses = {"terminal", "terminal_blocked", "skipped", "not_applicable", "blocked", "deferred"}
        if status in terminal_statuses:
            if has_value(result, "next_task_id"):
                add(
                    context.findings,
                    "block",
                    "schema_post_derive_terminal_next_task_forbidden",
                    "Terminal/skipped post-derive schema reconciliation must omit next_task_id rather than fabricate a successor.",
                    {"next_task_id": value_for(result, "next_task_id")},
                )
            reason = first_present(
                result,
                [
                    "schema_skipped_reason",
                    "schema_terminal_reason",
                    "schema_blocked_reason",
                    "reason",
                    "blockers",
                ],
            )
            if not non_empty(reason):
                add(
                    context.findings,
                    "block" if context.mode == "block" else "warn",
                    "schema_post_derive_terminal_reason_missing",
                    "Terminal/skipped post-derive schema reconciliation requires a concrete reason and no fabricated next_task_id.",
                )
            return
        if not has_value(result, "next_task_id"):
            context.require_context_field(
                "next_task_id",
                "schema_post_derive_next_task_missing",
                "Non-terminal post-derive schema reconciliation requires the real next_task_id.",
            )
