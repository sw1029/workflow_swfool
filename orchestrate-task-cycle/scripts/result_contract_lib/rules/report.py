from __future__ import annotations

from ..base import RuleContext, TargetContractRule
from ..common import task_pack_in_scope


class ReportRule(TargetContractRule):
    """Validate report-only context that becomes required in task-pack scope."""

    targets = frozenset({'report'})

    def check(self, context: RuleContext) -> None:
        result = context.result
        require_context_field = context.require_context_field
        if not task_pack_in_scope(result):
            return
        require_context_field("task_pack_status", "report_task_pack_status_missing", "`report` result references task-pack evidence but lacks `task_pack_status`.")
        require_context_field("task_pack_path", "report_task_pack_path_missing", "`report` result references task-pack evidence but lacks `task_pack_path`.")
        require_context_field("task_pack_item_id", "report_task_pack_item_id_missing", "`report` result references task-pack evidence but lacks `task_pack_item_id` or `promoted_item_id`.")
