from __future__ import annotations

from typing import Any
import re
from .common import (
    DISPOSITION_UNIVERSE,
    SAFETY_VALVES,
)
from . import domain as _domain
from . import families as _families
from . import values as _values


def row_root_family(row: dict[str, Any]) -> str:
    return str(
        row.get("root_family_key")
        or row.get("blocker_root_family")
        or _families.normalize_root_family_key(row.get("root_key"), row.get("family_key"), row.get("blocker_signature"))
    )

def recent_root_rows(
    rows: list[dict[str, Any]],
    root_key: str,
    fallback_family_key: str,
    root_family_key: str | None = None,
) -> list[dict[str, Any]]:
    root_values = {str(item) for item in (root_key, fallback_family_key, root_family_key) if item}
    scoped = [
        row
        for row in rows
        if str(row.get("root_key") or row.get("family_key") or "") in root_values
        or (root_family_key and row_root_family(row) == root_family_key)
    ]
    return scoped or _domain.recent_family_rows(rows, fallback_family_key)

def measurement_progress_details(
    registry_rows: list[dict[str, Any]],
    family_key: str,
    root_key: str,
    root_family_key: str,
    current_check_ids: set[str],
    current_frontiers: set[str],
) -> dict[str, Any]:
    family_rows = recent_root_rows(registry_rows, root_key, family_key, root_family_key)
    known_check_ids: set[str] = set()
    known_frontiers: set[str] = set()
    for row in family_rows:
        known_check_ids.update(str(item) for item in row.get("measurement_check_ids") or [] if item)
        known_frontiers.update(str(item) for item in row.get("measurement_frontiers_observed") or [] if item)
        basis = row.get("measurement_progress_basis")
        if isinstance(basis, dict):
            known_check_ids.update(str(item) for item in basis.get("introduced_check_ids") or [] if item)
            known_frontiers.update(str(item) for item in basis.get("new_frontier_observations") or [] if item)

    introduced = current_check_ids - known_check_ids
    new_frontiers = current_frontiers - known_frontiers
    measurement_progress = bool(introduced or new_frontiers)
    streak = 1 if measurement_progress else 0
    if measurement_progress:
        for row in reversed(family_rows):
            if _values.bool_value(row.get("measurement_progress")):
                streak += 1
                continue
            break
    return {
        "measurement_progress": measurement_progress,
        "measurement_streak": streak,
        "measurement_progress_streak_for_root_key": streak,
        "measurement_progress_streak_for_root_family": streak,
        "measurement_progress_basis": {
            "introduced_check_ids": sorted(introduced),
            "new_frontier_observations": sorted(new_frontiers),
        },
    }

def normalize_dispositions(values: Any) -> set[str]:
    normalized = {str(item).strip().lower() for item in _values.list_values(values)}
    return {item for item in normalized if item in DISPOSITION_UNIVERSE}

def normalize_task_kind(value: Any) -> str:
    return re.sub(r"[^a-z0-9_]+", "_", str(value or "").strip().lower().replace("-", "_")).strip("_")

def normalize_task_kinds(values: Any) -> set[str]:
    return {kind for kind in (normalize_task_kind(item) for item in _values.list_values(values)) if kind}


def normalize_portfolio_budget_gate(gate: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Require an adapter/caller-bound portfolio budget before restriction."""
    updated = dict(gate)
    budget_id = str(updated.get("portfolio_budget_id") or updated.get("budget_id") or "").strip()
    raw_status = str(
        updated.get("budget_evaluation_status")
        or updated.get("evaluation_status")
        or ""
    ).strip().lower()
    source = str(
        updated.get("budget_source")
        or updated.get("source")
        or updated.get("provided_by")
        or ""
    ).strip().lower()
    threshold_supplied = any(
        updated.get(key) is not None
        for key in (
            "threshold_ratio",
            "portfolio_threshold_ratio",
            "quota_ratio",
            "quota",
            "budget_value",
        )
    )
    evaluated = bool(
        budget_id
        and (
            raw_status in {"evaluated", "pass", "supplied", "verified"}
            or (
                threshold_supplied
                and source
                in {
                    "adapter",
                    "authority",
                    "authority_contract",
                    "caller",
                    "config",
                    "repository_config",
                    "project_contract",
                }
            )
        )
    )
    contract = {
        "budget_id": budget_id or None,
        "budget_value": next(
            (
                updated.get(key)
                for key in (
                    "budget_value",
                    "threshold_ratio",
                    "portfolio_threshold_ratio",
                    "quota_ratio",
                    "quota",
                )
                if updated.get(key) is not None
            ),
            None,
        ),
        "evaluation_status": "evaluated" if evaluated else "budget_unverified",
        "budget_evaluation_status": "evaluated" if evaluated else "budget_unverified",
        "source": source or None,
        "reason_code": None if evaluated else "portfolio_budget_not_content_bound",
    }
    updated["budget_evaluation"] = contract
    updated["budget_evaluation_status"] = contract["budget_evaluation_status"]
    if not evaluated:
        updated["observed_portfolio_quota_exceeded"] = _values.bool_value(
            updated.get("portfolio_quota_exceeded")
        )
        updated["constrains_disposition"] = False
        updated["hard_stop_required"] = False
        updated["hard_gate"] = False
        updated["status"] = "not_evaluated"
    return updated, contract

def gate_allowed_dispositions(name: str, gate: dict[str, Any]) -> set[str]:
    explicit = normalize_dispositions(gate.get("allowed_dispositions"))
    if explicit:
        return explicit
    if _values.bool_value(gate.get("requires_goal_productive_next")) or _values.bool_value(gate.get("requires_goal_productive_or_user_escalation")):
        return {"goal_productive", "terminal_blocked", "user_escalation"}
    if name == "command_surface_budget" and (_values.bool_value(gate.get("hard_gate")) or _values.bool_value(gate.get("budget_exceeded"))):
        return {"consolidation", "terminal_blocked"}
    return set(DISPOSITION_UNIVERSE)

def gate_allowed_task_kinds(gate: dict[str, Any]) -> set[str]:
    kinds = normalize_task_kinds(
        gate.get("allowed_task_kinds")
        or gate.get("goal_productive_task_kinds")
        or gate.get("required_task_kinds")
    )
    forced = gate.get("forced_selected_task")
    if isinstance(forced, dict):
        kinds.update(
            normalize_task_kinds(
                [
                    forced.get("selected_task_kind"),
                    forced.get("task_kind"),
                    forced.get("kind"),
                    forced.get("rung"),
                ]
            )
        )
    options = gate.get("forced_selected_task_options")
    if isinstance(options, list):
        for option in options:
            if isinstance(option, dict):
                kinds.update(
                    normalize_task_kinds(
                        [
                            option.get("selected_task_kind"),
                            option.get("task_kind"),
                            option.get("kind"),
                            option.get("rung"),
                        ]
                    )
                )
    return kinds

def gate_constrains_disposition(name: str, gate: dict[str, Any]) -> bool:
    return any(
        (
            _values.bool_value(gate.get("constrains_disposition")),
            _values.bool_value(gate.get("hard_stop_required")),
            _values.bool_value(gate.get("hard_gate")),
            _values.bool_value(gate.get("requires_goal_productive_next")),
            _values.bool_value(gate.get("requires_goal_productive_or_user_escalation")),
            str(gate.get("status") or "").lower() == "block",
            name == "command_surface_budget" and _values.bool_value(gate.get("budget_exceeded")),
        )
    )

def extract_disposition_gates(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        gates: list[dict[str, Any]] = []
        for item in value:
            gates.extend(extract_disposition_gates(item))
        return gates
    if not isinstance(value, dict):
        return []
    gate_names = (
        "command_surface_budget",
        "root_axis_gate",
        "goal_distance_gate",
        "feature_symbol_gate",
        "gt_constraint_conflict_gate",
        "semantic_signature_gate",
        "adapter_wiring_gate",
        "chain_stall_forced_retarget_gate",
        "portfolio_quota_gate",
    )
    gates = []
    for name in gate_names:
        child = value.get(name)
        if isinstance(child, dict):
            gate = dict(child)
            gate.setdefault("name", name)
            gates.append(gate)
    for key in ("gates", "disposition_gates"):
        raw = value.get(key)
        if isinstance(raw, list):
            for item in raw:
                if isinstance(item, dict):
                    gate = dict(item)
                    gate.setdefault("name", str(gate.get("gate") or gate.get("code") or key))
                    gates.append(gate)
    if not gates and any(key in value for key in ("allowed_dispositions", "hard_stop_required", "constrains_disposition")):
        gate = dict(value)
        gate.setdefault("name", str(value.get("name") or value.get("gate") or "gate"))
        gates.append(gate)
    return gates

def effective_allowed_dispositions(gates: list[dict[str, Any]]) -> tuple[list[str], dict[str, Any]]:
    constraining: list[set[str]] = []
    basis: dict[str, Any] = {}
    terminal_safety_valves_prohibited = False
    for index, gate in enumerate(gates):
        name = str(gate.get("name") or gate.get("gate") or f"gate_{index}")
        allowed = gate_allowed_dispositions(name, gate)
        constrains = gate_constrains_disposition(name, gate)
        basis[name] = {
            "allowed_dispositions": sorted(allowed),
            "constrains_disposition": constrains,
        }
        task_kinds = gate_allowed_task_kinds(gate)
        if task_kinds:
            basis[name]["allowed_task_kinds"] = sorted(task_kinds)
        if constrains:
            constraining.append(allowed)
        if name == "terminal_self_resolution" and _values.bool_value(gate.get("goal_terminal_prohibited")):
            terminal_safety_valves_prohibited = True
    if constraining:
        effective = set.intersection(*constraining)
        if not terminal_safety_valves_prohibited:
            effective |= SAFETY_VALVES
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
        effective = str(item.get("effective_progress_kind") or item.get("progress_kind") or "").strip().lower()
        if effective and effective != "governance_only":
            break
        streak += 1
    return streak
