from __future__ import annotations

from ...authority_boundary import project_authority_packet
from ...authority_artifacts import (
    validate_authority_artifacts,
    workspace_root_from_metadata,
)
from ..base import RuleContext, TargetContractRule
from ..common import add


class AuthorityRule(TargetContractRule):
    """Validate the closed packet at the existing authority phase boundary."""

    targets = frozenset({"authority"})

    def check(self, context: RuleContext) -> None:
        projection = project_authority_packet(context.result)
        for finding in projection.findings:
            add(
                context.findings,
                "block" if context.mode == "block" else "warn",
                str(finding["code"]),
                str(finding["message"]),
                finding.get("evidence"),
            )
        if projection.status != "legacy_unverified":
            for finding in validate_authority_artifacts(
                context.result, workspace_root_from_metadata(context.metadata)
            ):
                add(
                    context.findings,
                    "block",
                    str(finding["code"]),
                    str(finding["message"]),
                    finding.get("evidence"),
                )


__all__ = ("AuthorityRule",)
