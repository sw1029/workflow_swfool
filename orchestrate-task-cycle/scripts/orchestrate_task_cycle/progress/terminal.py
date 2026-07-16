from __future__ import annotations

import json
from typing import Any

from .values import boolish

def terminal_progress_item(item: dict[str, Any]) -> bool:
    for key in ("selected_task_source", "selected_task_kind", "disposition", "progress_target", "recommended_disposition"):
        value = str(item.get(key) or "").strip().lower()
        if "terminal" in value:
            return True
    observed = item.get("observed_output")
    if isinstance(observed, dict) and str(observed.get("observed_output_class") or "").lower() == "terminal_record":
        return True
    return False


def untried_root_cause_repair_item(item: dict[str, Any]) -> bool:
    disposition_values = [
        item.get("selected_task_source"),
        item.get("selected_task_kind"),
        item.get("disposition"),
        item.get("progress_target"),
        item.get("recommended_disposition"),
    ]
    if any("untried_root_cause_repair_required" in str(value or "").lower() for value in disposition_values):
        return True
    return boolish(item.get("untried_actionable_root_cause_exists"))


def quiescence_progress_item(item: dict[str, Any]) -> bool:
    if terminal_progress_item(item):
        return True
    if not untried_root_cause_repair_item(item):
        return False
    terminal_outcome = item.get("terminal_outcome_changed")
    produced = (item.get("output_delta_gate") or {}).get("produced_domain_delta")
    semantic = (item.get("output_delta_gate") or {}).get("semantic_progress")
    return not (boolish(terminal_outcome) or (boolish(produced) and boolish(semantic)))


def untried_quiescence_reconcile(progress_items: list[dict[str, Any]], raw_quiescence_required: bool) -> dict[str, Any]:
    untried_exists = any(boolish(item.get("untried_actionable_root_cause_exists")) for item in progress_items)
    exhausted = any(boolish(item.get("hypothesis_exhausted")) for item in progress_items)
    unverified_count = sum(int(item.get("root_cause_unverified_count") or 0) for item in progress_items)
    actionable_verified = untried_exists and not exhausted and unverified_count == 0
    override = bool(raw_quiescence_required and actionable_verified)
    return {
        "raw_quiescence_required": raw_quiescence_required,
        "untried_actionable_root_cause_exists": untried_exists,
        "hypothesis_exhausted": exhausted,
        "actionability_unverified_count": unverified_count,
        "overridden_by_untried_root_cause": override,
        "quiescence_required": raw_quiescence_required and not override,
        "override_rule": "verified_untried_root_cause_can_override_quiescence_until_budget_exhaustion",
    }


def terminal_quiescence_gate(
    progress_items: list[dict[str, Any]],
    has_supplied_input_delta: bool,
    threshold: int | None,
) -> dict[str, Any]:
    if threshold is None:
        reconcile = untried_quiescence_reconcile(progress_items, False)
        return {
            "gate": "T-QUIESCENCE",
            "status": "budget_unverified",
            "evaluation_status": "budget_unverified",
            "threshold": None,
            "terminal_streak": 0,
            "quiescence_required": False,
            "raw_quiescence_required": False,
            "commit_skipped_reason": None,
            "terminal_root_key": None,
            "has_supplied_input_delta": has_supplied_input_delta,
            "overridden_by_untried_root_cause": False,
            "quiescence_untried_reconcile": reconcile,
        }
    first_terminal = next((item for item in progress_items if quiescence_progress_item(item)), None)
    if not first_terminal:
        reconcile = untried_quiescence_reconcile(progress_items, False)
        return {
            "gate": "T-QUIESCENCE",
            "status": "not_applicable",
            "evaluation_status": "not_applicable",
            "threshold": threshold,
            "terminal_streak": 0,
            "quiescence_required": False,
            "raw_quiescence_required": False,
            "commit_skipped_reason": None,
            "terminal_root_key": None,
            "has_supplied_input_delta": has_supplied_input_delta,
            "overridden_by_untried_root_cause": False,
            "quiescence_untried_reconcile": reconcile,
        }
    root_key_value = str(first_terminal.get("root_key") or first_terminal.get("semantic_signature") or first_terminal.get("blocker_signature") or "unknown")
    streak = 0
    untried_repair_streak = 0
    evidence_paths: list[str] = []
    streak_item_kinds: list[str] = []
    for item in progress_items:
        item_root = str(item.get("root_key") or item.get("semantic_signature") or item.get("blocker_signature") or "unknown")
        if item_root != root_key_value or not quiescence_progress_item(item):
            break
        streak += 1
        if untried_root_cause_repair_item(item):
            untried_repair_streak += 1
            streak_item_kinds.append("untried_root_cause_repair_required")
        else:
            streak_item_kinds.append("terminal")
        if item.get("path"):
            evidence_paths.append(str(item["path"]))
    raw_required = streak >= threshold and not has_supplied_input_delta
    reconcile = untried_quiescence_reconcile(progress_items, raw_required)
    required = bool(reconcile["quiescence_required"])
    return {
        "gate": "T-QUIESCENCE",
        "status": "block" if required else "ok",
        "evaluation_status": "evaluated",
        "threshold": threshold,
        "terminal_streak": streak,
        "untried_repair_required_streak": untried_repair_streak,
        "streak_item_kinds": streak_item_kinds[:10],
        "terminal_root_key": root_key_value,
        "quiescence_required": required,
        "raw_quiescence_required": raw_required,
        "has_supplied_input_delta": has_supplied_input_delta,
        "commit_skipped_reason": "terminal_quiescence" if required else None,
        "allowed_dispositions": ["terminal_blocked", "user_escalation"] if required else ["goal_productive", "terminal_blocked", "user_escalation"],
        "evidence_paths": evidence_paths[:10],
        "handoff_only": required,
        "closeout_reproduction_allowed": not required,
        "overridden_by_untried_root_cause": reconcile["overridden_by_untried_root_cause"],
        "quiescence_untried_reconcile": reconcile,
    }


def terminal_recheck_item(item: dict[str, Any]) -> bool:
    if not terminal_progress_item(item):
        return False
    text = " ".join(
        str(item.get(key) or "")
        for key in (
            "selected_task_source",
            "selected_task_kind",
            "disposition",
            "recommended_disposition",
            "progress_target",
            "path",
        )
    ).lower()
    return any(token in text for token in ("terminal", "recheck", "blocked", "handoff", "quiescence"))


def terminal_escalation_missing_input(item: dict[str, Any] | None) -> dict[str, str]:
    text = json.dumps(item or {}, ensure_ascii=False, sort_keys=True).lower()
    if "self_inflicted_gate_defect" in text or "gate_defect" in text or "unsatisfiable" in text:
        return {
            "kind": "gate_contract_fix_approval",
            "description": "Approve or supply a gate contract/source change that makes the fail-closed gate satisfiable.",
        }
    if "authority" in text or "permission" in text or "approval" in text:
        return {
            "kind": "authority_change",
            "description": "Provide an authority or permission change that permits the blocked transition.",
        }
    if "external" in text or "provider" in text or "runtime" in text or "service" in text:
        return {
            "kind": "external_state_change",
            "description": "Change the external runtime/provider/service state required for the blocked transition.",
        }
    return {
        "kind": "new_input_kind",
        "description": "Provide one new material input artifact or input kind that changes the sealed family.",
    }


def terminal_escalation_gate(
    progress_items: list[dict[str, Any]],
    has_supplied_input_delta: bool,
    threshold: int | None,
) -> dict[str, Any]:
    if threshold is None:
        return {
            "gate": "G2-TERMINAL-ESCALATION",
            "status": "budget_unverified",
            "evaluation_status": "budget_unverified",
            "threshold": None,
            "terminal_recheck_streak": 0,
            "root_family": None,
            "escalation_required": False,
            "forced_disposition": None,
            "has_supplied_input_delta": has_supplied_input_delta,
            "missing_input": None,
            "seal_required": False,
            "seal_family_path": ".task/sealed_blocker_families.json",
            "hard_stop_required": False,
            "evidence_paths": [],
        }
    first_terminal = next((item for item in progress_items if terminal_recheck_item(item)), None)
    if not first_terminal:
        return {
            "gate": "G2-TERMINAL-ESCALATION",
            "status": "not_applicable",
            "evaluation_status": "not_applicable",
            "threshold": threshold,
            "terminal_recheck_streak": 0,
            "root_family": None,
            "escalation_required": False,
            "forced_disposition": None,
            "has_supplied_input_delta": has_supplied_input_delta,
            "missing_input": None,
            "seal_required": False,
            "seal_family_path": ".task/sealed_blocker_families.json",
            "hard_stop_required": False,
            "evidence_paths": [],
        }
    root_family = str(
        first_terminal.get("blocker_root_family")
        or first_terminal.get("root_key")
        or first_terminal.get("semantic_signature")
        or first_terminal.get("blocker_signature")
        or "unknown"
    )
    streak = 0
    evidence_paths: list[str] = []
    for item in progress_items:
        item_family = str(
            item.get("blocker_root_family")
            or item.get("root_key")
            or item.get("semantic_signature")
            or item.get("blocker_signature")
            or "unknown"
        )
        if item_family != root_family or not terminal_recheck_item(item):
            break
        streak += 1
        if item.get("path"):
            evidence_paths.append(str(item["path"]))
    required = streak >= threshold and not has_supplied_input_delta
    return {
        "gate": "G2-TERMINAL-ESCALATION",
        "status": "block" if required else "ok",
        "evaluation_status": "evaluated",
        "threshold": threshold,
        "terminal_recheck_streak": streak,
        "root_family": root_family,
        "escalation_required": required,
        "forced_disposition": "user_escalation" if required else None,
        "has_supplied_input_delta": has_supplied_input_delta,
        "missing_input": terminal_escalation_missing_input(first_terminal) if required else None,
        "missing_input_count": 1 if required else 0,
        "seal_required": required,
        "seal_family_path": ".task/sealed_blocker_families.json",
        "allowed_dispositions": ["user_escalation"] if required else ["goal_productive", "terminal_blocked", "user_escalation"],
        "constrains_disposition": required,
        "hard_stop_required": required,
        "evidence_paths": evidence_paths[:10],
        "recheck_counts_as_progress": False,
    }
