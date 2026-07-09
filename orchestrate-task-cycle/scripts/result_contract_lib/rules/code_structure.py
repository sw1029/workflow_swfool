from __future__ import annotations

from ..base import RuleContext, TargetContractRule
from ..common import add, boolish, first_present, list_values, value_for


class CodeStructureAuditRule(TargetContractRule):
    """Validate structure-audit status, plans, and source-persistence safety."""

    targets = frozenset({'code_structure_audit'})

    def check(self, context: RuleContext) -> None:
        result = context.result
        mode = context.mode
        findings = context.findings
        audit_status = str(value_for(result, "audit_status") or value_for(result, "status") or "").lower()
        if audit_status and audit_status not in {"pass", "warn", "refactor_required", "blocked", "not_applicable"}:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "code_structure_audit_status_invalid",
                "`code_structure_audit` audit_status should be pass, warn, refactor_required, blocked, or not_applicable.",
                {"audit_status": audit_status},
            )
        moduleization_required = boolish(value_for(result, "moduleization_required"))
        split_plan = list_values(value_for(result, "responsibility_split_plan"))
        existing_debt_exemptions = list_values(
            first_present(
                result,
                [
                    "existing_debt_exemptions",
                    "existing_debt_exemption",
                    "code_structure_audit.existing_debt_exemptions",
                ],
            )
        )
        if moduleization_required and not split_plan and not existing_debt_exemptions:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "moduleization_required_without_split_plan",
                "`code_structure_audit` with moduleization_required=true requires a responsibility_split_plan or existing-debt exemption.",
            )
        raw_source_persisted = boolish(
            first_present(
                result,
                [
                    "raw_source_persisted",
                    "source_body_persisted",
                    "code_structure_audit.raw_source_persisted",
                    "code_structure_audit.source_body_persisted",
                ],
            )
        )
        forbidden_raw_source_persisted = first_present(
            result,
            [
                "forbidden_raw_source_persisted",
                "code_structure_audit.forbidden_raw_source_persisted",
            ],
        )
        if raw_source_persisted or forbidden_raw_source_persisted is False:
            add(
                findings,
                "block",
                "raw_source_persisted",
                "`code_structure_audit` must not persist raw source bodies; emit scalar metrics and symbol names only.",
            )
