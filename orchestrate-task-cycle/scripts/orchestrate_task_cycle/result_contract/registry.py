from __future__ import annotations

from .base import RuleRegistry
from .rules import (
    AcceptanceRule,
    CodeStructureAuditRule,
    CommitRule,
    CompletionValidationRule,
    CycleEfficiencyProfileRule,
    DashboardRule,
    DeriveRule,
    IssueRule,
    LoopbackAuditRule,
    QualitativeReviewRule,
    ReportRule,
    RunRule,
    SchemaPostDeriveRule,
    ValidationSetRule,
    ValidationScopeRule,
    VisibleIncrementRule,
)


def default_rule_registry() -> RuleRegistry:
    """Build the canonical ordered target-rule registry."""

    return RuleRegistry(
        [
            AcceptanceRule(),
            CodeStructureAuditRule(),
            RunRule(),
            ValidationSetRule(),
            VisibleIncrementRule(),
            CycleEfficiencyProfileRule(),
            ValidationScopeRule(),
            QualitativeReviewRule(),
            CommitRule(),
            DashboardRule(),
            DeriveRule(),
            SchemaPostDeriveRule(),
            LoopbackAuditRule(),
            CompletionValidationRule(),
            IssueRule(),
            ReportRule(),
        ]
    )
