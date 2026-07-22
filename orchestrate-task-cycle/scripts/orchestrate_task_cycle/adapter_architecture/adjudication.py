"""Deterministic architecture outcome adjudication."""

from __future__ import annotations

from collections import Counter
from typing import Any

from .contracts import ADJUDICATOR_REVISION


STRICT_MODES = {"enforce", "enforced", "strict", "enforce_new", "enforce_all"}


def _rollout(convention: dict[str, Any] | None) -> tuple[str, dict[str, int]]:
    if not isinstance(convention, dict):
        return "missing", {}
    policy = (
        convention.get("rollout_policy")
        or convention.get("audit_policy")
        or convention.get("rollout")
    )
    policy = policy if isinstance(policy, dict) else {}
    mode = str(policy.get("mode") or convention.get("enforcement") or "warn").lower()
    raw_water = policy.get("legacy_debt_high_water")
    high_water = {
        str(key): int(value)
        for key, value in (raw_water.items() if isinstance(raw_water, dict) else [])
        if isinstance(value, int) and value >= 0
    }
    if mode == "changed_code_enforced_legacy_high_water":
        mode = "enforce_new"
    return mode, high_water


def _semantic_corroboration(receipt: dict[str, Any] | None) -> set[str]:
    assessment = receipt.get("assessment") if isinstance(receipt, dict) else None
    findings = assessment.get("findings") if isinstance(assessment, dict) else None
    return {
        str(fact_id)
        for finding in findings or []
        if isinstance(finding, dict)
        for fact_id in finding.get("evidence_fact_ids") or []
    }


def adjudicate_architecture(
    facts: dict[str, Any],
    convention: dict[str, Any] | None,
    semantic_receipt: dict[str, Any] | None,
) -> dict[str, Any]:
    modules = facts.get("modules") if isinstance(facts.get("modules"), list) else []
    pressures = facts.get("structural_pressures")
    pressures = pressures if isinstance(pressures, list) else []
    deterministic_blockers = list(facts.get("blockers") or [])
    hook_rows = facts.get("hook_owner_test_mapping") or []
    for hook in hook_rows:
        if isinstance(hook, dict) and (
            not hook.get("owner_component_exists") or not hook.get("owner_symbol_exists")
        ):
            deterministic_blockers.append(
                {
                    "code": "adapter_hook_owner_unresolved",
                    "hook_id": hook.get("hook_id"),
                }
            )
    forbidden_effects = set(
        str(item)
        for item in (
            convention.get("forbidden_import_time_effects", [])
            if isinstance(convention, dict)
            else []
        )
    )
    for module in modules:
        observed = forbidden_effects & set(module.get("top_level_effect_kinds") or [])
        if observed:
            deterministic_blockers.append(
                {
                    "code": "unsafe_import_time_effect",
                    "component_id": module.get("component_id"),
                    "effect_kinds": sorted(observed),
                }
            )
    mode, high_water = _rollout(convention)
    counts = Counter(str(item.get("axis")) for item in pressures if isinstance(item, dict))
    actionable: list[dict[str, Any]] = []
    for pressure in pressures:
        if not isinstance(pressure, dict):
            continue
        axis = str(pressure.get("axis"))
        if mode == "enforce_new" and not pressure.get("changed"):
            if axis not in high_water or counts[axis] <= high_water[axis]:
                continue
        actionable.append(pressure)
    corroborated_ids = _semantic_corroboration(semantic_receipt)
    corroborated = [
        pressure
        for pressure in actionable
        if str(pressure.get("fact_id")) in corroborated_ids
    ]
    if not modules:
        status = "not_applicable"
    elif deterministic_blockers:
        status = "blocked"
    elif not isinstance(convention, dict) or semantic_receipt is None:
        status = "not_evaluated"
    elif mode in STRICT_MODES and actionable and corroborated:
        status = "refactor_required"
    elif pressures:
        status = "warn"
    else:
        status = "pass"
    consumability = "blocked" if deterministic_blockers else "pass"
    findings = [
        {
            "code": str(item.get("axis")),
            "fact_id": item.get("fact_id"),
            "disposition": "refactor_required"
            if item in corroborated and status == "refactor_required"
            else "warn",
        }
        for item in pressures
    ]
    return {
        "adjudicator_revision": ADJUDICATOR_REVISION,
        "adapter_consumability_status": consumability,
        "adapter_architecture_status": status,
        "audit_policy_mode": mode,
        "deterministic_blockers": deterministic_blockers,
        "structural_pressure_counts": dict(sorted(counts.items())),
        "actionable_fact_ids": sorted(
            str(item.get("fact_id")) for item in actionable
        ),
        "semantic_corroborated_fact_ids": sorted(
            str(item.get("fact_id")) for item in corroborated
        ),
        "findings": findings,
        "field_origins": {
            "adapter_consumability_status": "deterministic_adjudication",
            "adapter_architecture_status": "deterministic_adjudication",
            "deterministic_blockers": "deterministic_fact",
            "structural_pressure_counts": "deterministic_fact",
            "semantic_corroborated_fact_ids": "semantic_receipt",
            "audit_policy_mode": "repo_policy",
        },
        "semantic_cannot_set_final_status": True,
        "pattern_absence_is_not_a_defect": True,
        "inheritance_audited_only_when_present": True,
    }


__all__ = ("adjudicate_architecture",)
