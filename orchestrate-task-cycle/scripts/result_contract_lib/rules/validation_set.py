from __future__ import annotations

from ..base import RuleContext, TargetContractRule
from ..common import add, boolish, first_present, non_empty, positive_count, value_for


class ValidationSetRule(TargetContractRule):
    """Validate validation-set planning, build, and scenario evidence."""

    targets = frozenset({'validation_set_plan', 'validation_set_build'})

    def check(self, context: RuleContext) -> None:
        target = context.target
        result = context.result
        mode = context.mode
        findings = context.findings
        acceptance_scenarios = first_present(
            result,
            [
                "acceptance_scenarios",
                "acceptance_scenario_contract.acceptance_scenarios",
                "validation_set.acceptance_scenarios",
                "result.acceptance_scenarios",
            ],
        )
        scenario_required = boolish(
            first_present(
                result,
                [
                    "acceptance_scenario_required",
                    "acceptance_scenario_gate.required",
                    "scenario_coverage_required",
                    "result.acceptance_scenario_gate.required",
                ],
            )
        )
        scenario_coverage = first_present(
            result,
            [
                "scenario_coverage",
                "acceptance_scenario_gate.scenario_coverage",
                "validation_set.scenario_coverage",
                "result.acceptance_scenario_gate.scenario_coverage",
            ],
        )
        scenario_gate = first_present(
            result,
            [
                "acceptance_scenario_gate",
                "scenario_coverage_gate",
                "result.acceptance_scenario_gate",
            ],
        )
        scenario_uncovered = boolish(
            first_present(
                result,
                [
                    "scenario_uncovered",
                    "acceptance_scenario_gate.scenario_uncovered",
                    "result.acceptance_scenario_gate.scenario_uncovered",
                ],
            )
        )
        missing_premise_reason = first_present(
            result,
            [
                "missing_premise_satisfying_input_reason",
                "scenario_uncovered_reason",
                "acceptance_scenario_gate.missing_premise_satisfying_input_reason",
                "result.acceptance_scenario_gate.scenario_uncovered_reason",
            ],
        )
        if (non_empty(acceptance_scenarios) or scenario_required) and not (non_empty(scenario_coverage) or scenario_uncovered or non_empty(scenario_gate)):
            add(
                findings,
                "block" if mode == "block" else "warn",
                f"{target}_scenario_coverage_missing",
                f"`{target}` received scenario-shaped acceptance but did not record scenario coverage or scenario_uncovered.",
            )
        if scenario_uncovered and not non_empty(missing_premise_reason):
            add(
                findings,
                "block" if mode == "block" else "warn",
                f"{target}_scenario_uncovered_without_reason",
                f"`{target}` scenario_uncovered=true requires the missing premise-satisfying input condition.",
            )
        if target == "validation_set_build":
            build_status = str(value_for(result, "validation_set_status") or "").strip().lower()
            if build_status in {"not_applicable", "skipped"}:
                reason = first_present(
                    result,
                    [
                        "validation_set_not_applicable_reason",
                        "validation_set_skipped_reason",
                        "reason",
                        "blockers",
                    ],
                )
                if not non_empty(reason):
                    add(
                        findings,
                        "block" if mode == "block" else "warn",
                        "validation_set_build_na_reason_missing",
                        "N/A or skipped validation-set build requires a concrete reason; artifact paths must remain absent rather than fabricated.",
                    )
                return
            for field in (
                "validation_set_id",
                "quality_tier",
                "not_gold",
                "item_count",
                "oracle_manifest_path",
                "split_manifest_path",
                "leakage_report_path",
                "validation_set_root_path",
            ):
                context.require_context_field(
                    field,
                    "validation_set_build_artifact_field_missing",
                    f"Non-N/A validation-set build requires `{field}`.",
                )
            quality_tier = str(value_for(result, "quality_tier") or "").lower()
            if quality_tier == "gold":
                human_reviewed = positive_count(value_for(result, "human_reviewed_count"))
                deterministic_authoritative = bool(value_for(result, "fully_deterministic_authoritative_oracle"))
                if not human_reviewed and not deterministic_authoritative:
                    add(
                        findings,
                        "block",
                        "gold_without_authoritative_evidence",
                        "`validation_set_build` cannot report `quality_tier: gold` without human-reviewed or fully deterministic authoritative evidence.",
                    )
            guard_fields = {
                "raw_body_persisted": "raw_body_persistence_forbidden",
                "durable_raw_body_persisted": "raw_body_persistence_forbidden",
                "source_class_promotion_violation": "source_class_promotion_forbidden",
                "sealed_holdout_labels_exposed": "sealed_holdout_label_exposure_forbidden",
            }
            for field, code in guard_fields.items():
                value = value_for(result, field)
                if value is True or str(value).lower() in {"true", "yes", "1"}:
                    add(findings, "block", code, f"`validation_set_build` reported forbidden guard violation `{field}`.")
