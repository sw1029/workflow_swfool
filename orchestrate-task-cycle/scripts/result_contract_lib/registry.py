from __future__ import annotations

from .base import RuleRegistry
from .rules import (
    CodeStructureAuditRule,
    CommitRule,
    CompletionValidationRule,
    DeriveRule,
    LoopbackAuditRule,
    QualitativeReviewRule,
    ReportRule,
    RunRule,
    ValidationSetRule,
)


def default_rule_registry() -> RuleRegistry:
    """Build the canonical ordered target-rule registry."""

    return RuleRegistry(
        [
            CodeStructureAuditRule(),
            RunRule(),
            ValidationSetRule(),
            QualitativeReviewRule(),
            CommitRule(),
            DeriveRule(),
            LoopbackAuditRule(),
            CompletionValidationRule(),
            ReportRule(),
        ]
    )
