from __future__ import annotations

import re

from ..base import RuleContext, TargetContractRule
from ..common import add


ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
STATUSES = {"ok", "warn", "blocked"}
RECOMMENDATIONS = {
    "continue",
    "batch_micro_contracts",
    "supply_evidence_path",
    "bounded_preflight",
    "supply_evidence_path_or_bounded_preflight",
    "resume_primary_output",
    "root_cause_repair_or_stop_with_blocker",
    "narrow_scope",
    "register_consolidation_candidate",
    "stop_with_blocker",
    "consume_or_reorder_task_pack_or_terminal_block",
    "route_validation_set_plan_or_build",
}
BASIS_LIST_FIELDS = {"unique_new_artifact_ids", "unique_unchanged_artifact_ids", "fresh_stage_event_ids"}


class CycleEfficiencyProfileRule(TargetContractRule):
    """Reject fabricated or structurally empty efficiency-profile envelopes."""

    targets = frozenset({"cycle_efficiency_profile"})

    def check(self, context: RuleContext) -> None:
        result = context.result
        severity = "block"
        task_id = str(result.get("task_id") or "")
        if not ID_PATTERN.fullmatch(task_id):
            add(context.findings, severity, "cycle_efficiency_task_id_invalid", "Cycle-efficiency task_id must be one path-safe token.", {"task_id": task_id or None})
        status = str(result.get("status") or "").strip().lower()
        if status not in STATUSES:
            add(context.findings, severity, "cycle_efficiency_status_invalid", "Cycle-efficiency status is outside the closed vocabulary.", {"status": status or None, "allowed": sorted(STATUSES)})
        cost = result.get("cycle_fixed_cost")
        if isinstance(cost, bool) or not isinstance(cost, (int, float)) or cost < 0:
            add(context.findings, severity, "cycle_efficiency_cost_invalid", "cycle_fixed_cost must be a nonnegative number.", {"cycle_fixed_cost": cost})
        basis = result.get("cycle_cost_basis")
        if not isinstance(basis, dict) or any(not isinstance(basis.get(field), list) for field in BASIS_LIST_FIELDS) or not str(basis.get("denominator") or "").strip():
            add(
                context.findings,
                severity,
                "cycle_efficiency_cost_basis_invalid",
                "cycle_cost_basis must include the three identity lists and a non-empty denominator description.",
                {"required_list_fields": sorted(BASIS_LIST_FIELDS)},
            )
        recommendation = str(result.get("recommendation") or "").strip()
        if recommendation not in RECOMMENDATIONS:
            add(context.findings, severity, "cycle_efficiency_recommendation_invalid", "Cycle-efficiency recommendation is outside the closed vocabulary.", {"recommendation": recommendation or None, "allowed": sorted(RECOMMENDATIONS)})
        blockers = result.get("blockers")
        if not isinstance(blockers, list):
            add(context.findings, severity, "cycle_efficiency_blockers_missing", "Cycle-efficiency profile requires an explicit blockers list.")
        evidence_paths = result.get("evidence_paths")
        if not isinstance(evidence_paths, list) or not evidence_paths or any(not str(item).strip() for item in evidence_paths):
            add(context.findings, severity, "cycle_efficiency_evidence_paths_invalid", "Cycle-efficiency profile requires explicit non-empty evidence_paths.")
