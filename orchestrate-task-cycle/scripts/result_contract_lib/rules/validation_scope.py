from __future__ import annotations

from ..base import RuleContext, TargetContractRule
from ..common import add, non_empty, value_for


class ValidationScopeRule(TargetContractRule):
    """Validate the two-pass validation-scope transaction, including explicit empty collections."""

    targets = frozenset({"validation_scope_plan", "validation_scope_finalize"})

    def check(self, context: RuleContext) -> None:
        result = context.result
        findings = context.findings
        payload = result.get("result") if isinstance(result.get("result"), dict) else result
        expected_mode = "plan" if context.target == "validation_scope_plan" else "finalize"
        expected_finalized = context.target == "validation_scope_finalize"

        if str(value_for(result, "step") or "") != context.target:
            add(
                findings,
                "block",
                "validation_scope_step_mismatch",
                "Validation-scope result must identify the exact canonical pass it completed.",
                {"expected": context.target, "observed": value_for(result, "step")},
            )
        if str(value_for(result, "mode") or "") != expected_mode:
            add(
                findings,
                "block",
                "validation_scope_mode_mismatch",
                "Validation-scope mode does not match the canonical pass.",
                {"expected": expected_mode, "observed": value_for(result, "mode")},
            )
        observed_finalized = value_for(result, "finalized")
        if observed_finalized is not expected_finalized:
            add(
                findings,
                "block",
                "validation_scope_finalized_mismatch",
                "Only the post-change validation-scope pass may set `finalized: true`.",
                {"expected": expected_finalized, "observed": observed_finalized},
            )

        structural_fields = (
            "planned_changed_files",
            "actual_changed_files",
            "changed_surfaces",
            "surface_counts",
            "required_commands",
            "reused_prerequisites",
            "escalation_reasons",
            "findings",
        )
        missing = [field for field in structural_fields if field not in payload]
        if missing:
            add(
                findings,
                "block",
                "validation_scope_structural_fields_missing",
                "Validation-scope result must preserve explicit empty collections rather than omit them.",
                {"missing_fields": missing},
            )
        if context.target == "validation_scope_finalize" and not non_empty(payload.get("required_commands")):
            add(
                findings,
                "block",
                "validation_scope_finalize_commands_missing",
                "Finalized validation scope must name at least one executable validation command.",
            )
