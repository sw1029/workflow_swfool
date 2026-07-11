from __future__ import annotations

import re

from ..base import RuleContext, TargetContractRule
from ..common import add, value_for


ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
DELTA_TYPES = {"cli", "api", "workflow_artifact", "schema_contract", "dashboard", "report", "none"}


class VisibleIncrementRule(TargetContractRule):
    """Keep visible-increment records explicitly outside validation evidence."""

    targets = frozenset({"visible_increment"})

    def check(self, context: RuleContext) -> None:
        result = context.result
        severity = "block"
        for field in ("cycle_id", "task_id"):
            value = str(result.get(field) or "")
            if not ID_PATTERN.fullmatch(value):
                add(context.findings, severity, "visible_increment_id_invalid", f"Visible increment `{field}` must be one path-safe token.", {"field": field, "value": value or None})
        if str(result.get("status") or "").strip().lower() != "recorded":
            add(context.findings, severity, "visible_increment_status_invalid", "Visible increment status must be `recorded`.")
        delta_types = result.get("delta_types")
        if not isinstance(delta_types, list) or not delta_types or any(str(item) not in DELTA_TYPES for item in delta_types):
            add(context.findings, severity, "visible_increment_delta_types_invalid", "Visible increment delta_types must be a non-empty list from the closed vocabulary.", {"allowed": sorted(DELTA_TYPES)})
        elif "none" in delta_types and len(delta_types) != 1:
            add(context.findings, severity, "visible_increment_none_delta_mixed", "Delta type `none` must not be mixed with concrete delta types.")
        for field in ("changed_files", "artifacts", "blockers"):
            if not isinstance(result.get(field), list):
                add(context.findings, severity, "visible_increment_explicit_list_missing", f"Visible increment must carry explicit list `{field}`.", {"field": field})
        evidence_paths = result.get("evidence_paths")
        if not isinstance(evidence_paths, list) or not evidence_paths or any(not str(item).strip() for item in evidence_paths):
            add(context.findings, severity, "visible_increment_evidence_paths_invalid", "Visible increment requires explicit non-empty evidence_paths.")
        if value_for(result, "not_validation_evidence") is not True:
            add(
                context.findings,
                severity,
                "visible_increment_validation_evidence_boundary_missing",
                "Visible-increment records must set `not_validation_evidence: true`.",
            )
