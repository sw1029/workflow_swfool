from __future__ import annotations

from .shared import add, selected_task_kind_value
from .state import DeriveFacts


RECOVERY_TASK_KINDS = {
    "finalization_conflict_recovery",
    "finalization_state_reconcile",
}


def check_finalization_recovery(facts: DeriveFacts) -> None:
    result = facts.result
    pending = result.get("pending_finalization_conflicts")
    recovery = result.get("finalization_recovery")
    recovery_required = bool(isinstance(pending, list) and pending) or bool(
        isinstance(recovery, dict)
        and recovery.get("state_commit_status") == "recovery_required"
    )
    if not recovery_required:
        return
    outcome = str(result.get("selection_outcome") or "selected")
    if outcome != "selected":
        return
    selected_kind = selected_task_kind_value(result)
    if selected_kind not in RECOVERY_TASK_KINDS:
        add(
            facts.findings,
            "block" if facts.mode == "block" else "warn",
            "derive_pending_finalization_conflict_bypassed",
            "Pending finalization attempt memory allows only bounded conflict recovery/reconciliation before a normal successor.",
            {"selected_task_kind": selected_kind or None},
        )
