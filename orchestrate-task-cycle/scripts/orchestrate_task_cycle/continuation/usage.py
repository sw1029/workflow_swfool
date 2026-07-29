"""Controller-owned adaptive-session budget accounting."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .contracts import ContinuationContractError


def usage_after_result(
    state: dict[str, Any],
    action: dict[str, Any],
    result: dict[str, Any],
    outcome: dict[str, Any],
) -> dict[str, Any]:
    """Apply budget accounting using verified terminal outcomes only."""

    usage = deepcopy(state["usage"])
    target = action["target"]
    commit_status = str(
        result.get("commit_status") or result.get("status") or ""
    ).lower()
    committed = commit_status in {"committed", "created", "passed", "success"}
    if target == "commit" and committed:
        raise ContinuationContractError(
            "adaptive sessions defer the normal commit to closeout"
        )
    if target == "closeout_commit" and committed:
        cycle_id = state["active_cycle_id"]
        count = usage["commits_by_cycle"].get(cycle_id, 0)
        if count >= state["budgets"]["max_commits_per_cycle"]:
            raise ContinuationContractError("cycle commit budget exhausted")
        usage["commits_by_cycle"][cycle_id] = count + 1
        usage["commits_by_cycle"] = dict(
            sorted(usage["commits_by_cycle"].items())
        )
    if target == "run":
        terminal_status = outcome.get("run_terminal_status")
        terminal_run_id = outcome.get("run_terminal_run_id")
        if terminal_status is not None and (
            action.get("kind") != "monitor_run"
            or terminal_status not in {"succeeded", "failed_closed"}
            or not terminal_run_id
        ):
            raise ContinuationContractError(
                "trusted terminal outcome is inconsistent"
            )
        run_status = str(
            terminal_status
            or result.get("execution_status")
            or result.get("status")
            or ""
        ).lower()
        run_id = terminal_run_id or result.get("run_id")
        live_statuses = {
            "launching",
            "running",
            "completed_pending_validation",
        }
        terminal_statuses = {
            "blocked_no_execution",
            "cancelled",
            "canceled",
            "complete",
            "completed",
            "failed",
            "failed_closed",
            "no_execution",
            "not_running",
            "not_applicable",
            "skipped",
            "stopped",
            "succeeded",
            "success",
            "terminated",
        }
        if run_status in live_statuses and not run_id:
            raise ContinuationContractError(
                "a live run result requires run_id"
            )
        # Unverified monitor statuses remain nonterminal.  A raw terminal
        # claim must not free a slot and permit a second long-running effect.
        terminal_verified = terminal_status is not None
        if run_id and not terminal_verified:
            identifier = str(run_id)
            active = set(usage["active_long_runs"])
            if identifier not in active:
                if (
                    len(active)
                    >= state["budgets"]["max_concurrent_long_runs"]
                ):
                    raise ContinuationContractError(
                        "concurrent long-run budget exhausted"
                    )
                active.add(identifier)
            usage["active_long_runs"] = sorted(active)
        elif run_id and run_status in terminal_statuses:
            usage["active_long_runs"] = [
                item
                for item in usage["active_long_runs"]
                if item != str(run_id)
            ]
    return usage


__all__ = ("usage_after_result",)
