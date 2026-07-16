from __future__ import annotations

from typing import Any

from .constants import DISPOSITION_UNIVERSE, SAFETY_VALVES
from .values import boolish, first_value, list_values

def normalize_dispositions(value: Any) -> set[str]:
    return {item.strip().lower() for item in list_values(value) if item.strip().lower() in DISPOSITION_UNIVERSE}


def gate_allowed_dispositions(name: str, gate: dict[str, Any]) -> set[str]:
    if (
        name == "command_surface_budget"
        and str(gate.get("decision_scope") or "").strip().lower() == "global_dashboard"
        and not boolish(gate.get("constrains_current_family"))
    ):
        return set(DISPOSITION_UNIVERSE)
    explicit = normalize_dispositions(gate.get("allowed_dispositions"))
    if explicit:
        return explicit
    if boolish(gate.get("requires_goal_productive_next")) or boolish(gate.get("requires_goal_productive_or_user_escalation")):
        return {"goal_productive", "terminal_blocked", "user_escalation"}
    if name == "command_surface_budget" and (boolish(gate.get("hard_gate")) or boolish(gate.get("budget_exceeded"))):
        return {"consolidation", "terminal_blocked"}
    return set(DISPOSITION_UNIVERSE)


def gate_constrains_disposition(name: str, gate: dict[str, Any]) -> bool:
    if (
        name == "command_surface_budget"
        and str(gate.get("decision_scope") or "").strip().lower() == "global_dashboard"
        and not boolish(gate.get("constrains_current_family"))
    ):
        return False
    return any(
        (
            boolish(gate.get("constrains_disposition")),
            boolish(gate.get("hard_stop_required")),
            boolish(gate.get("hard_gate")),
            boolish(gate.get("requires_goal_productive_next")),
            boolish(gate.get("requires_goal_productive_or_user_escalation")),
            str(gate.get("status") or "").lower() == "block",
            name == "command_surface_budget" and boolish(gate.get("budget_exceeded")),
        )
    )


def effective_allowed_dispositions(gates: list[tuple[str, dict[str, Any]]]) -> tuple[list[str], dict[str, Any]]:
    constraining: list[set[str]] = []
    basis: dict[str, Any] = {}
    for name, gate in gates:
        allowed = gate_allowed_dispositions(name, gate)
        constrains = gate_constrains_disposition(name, gate)
        basis[name] = {
            "allowed_dispositions": sorted(allowed),
            "constrains_disposition": constrains,
        }
        if constrains:
            constraining.append(allowed)
    if constraining:
        effective = set.intersection(*constraining) | SAFETY_VALVES
    else:
        effective = set(DISPOSITION_UNIVERSE)
    return sorted(effective), basis


def item_disposition(item: dict[str, Any]) -> str:
    for key in ("disposition", "selected_disposition", "progress_target", "selected_task_source", "selected_task_kind"):
        value = str(item.get(key) or "").strip().lower()
        if value in DISPOSITION_UNIVERSE:
            return value
        if "consolidation" in value:
            return "consolidation"
        if "goal_productive" in value:
            return "goal_productive"
        if "terminal" in value:
            return "terminal_blocked"
        if "user_escalation" in value or "user-escalation" in value:
            return "user_escalation"
    return ""


def consolidation_streak(items: list[dict[str, Any]]) -> int:
    streak = 0
    for item in items:
        if item_disposition(item) != "consolidation":
            break
        effective = str(first_value(item, ("effective_progress_kind", "progress_kind")) or "").strip().lower()
        if effective and effective != "governance_only":
            break
        streak += 1
    return streak
