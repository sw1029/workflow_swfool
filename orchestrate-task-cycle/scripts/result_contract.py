#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from result_contract_lib.base import RuleContext, RuleRegistry  # noqa: E402
from result_contract_lib.common import (  # noqa: E402
    ADVICE_REQUIRED_TARGETS,
    AGENT_ROUTING_TARGETS,
    CANONICAL_LEDGER_STEPS,
    COMMON_FIELDS,
    MODEL_EFFORT_POLICY,
    MODEL_EFFORT_ROUTER,
    ROUTING_ENFORCEMENT_VALUES,
    SUPPORTED_AGENT_EFFORTS,
    SUPPORTED_AGENT_MODELS,
    TARGETS,
    active_advice_present,
    actual_report_body_divergences,
    add,
    advice_handling_rationale_present,
    boolish,
    first_present,
    has_value,
    list_values,
    load_json,
    non_empty,
    report_key_divergences,
    report_key_duplicate_matches,
    value_for,
)
from result_contract_lib.registry import default_rule_registry  # noqa: E402
from result_contract_lib.rules.session_audit import SessionAuditRule  # noqa: E402


PENDING_LONG_RUN_STATUSES = {"launching", "running", "completed_pending_validation", "stale", "not_running"}
SESSION_AUDIT_RULE = SessionAuditRule()


def has_explicit_empty(result: dict[str, Any], field: str, expected_type: type[list[Any]] | type[dict[str, Any]]) -> bool:
    containers = [result]
    for key in ("result", "packet"):
        nested = result.get(key)
        if isinstance(nested, dict):
            containers.append(nested)
    return any(field in container and isinstance(container.get(field), expected_type) and not container[field] for container in containers)


def reasoned_na_allows_explicit_empty(target: str, field: str, result: dict[str, Any]) -> bool:
    if target == "qualitative_review":
        status = str(value_for(result, "review_status") or value_for(result, "status") or "").strip().lower()
        reason = first_present(
            result,
            ["reason", "review_skipped_reason", "qualitative_review_pending_reason", "reviewer_delegation_unavailable_reason", "blockers"],
        )
        if status in {"not_applicable", "blocked"} and non_empty(reason):
            if field == "reviewer_routing":
                return has_explicit_empty(result, field, dict)
            if field == "evidence_paths":
                return has_explicit_empty(result, field, list)
    if target == "validation_set_build":
        status = str(value_for(result, "validation_set_status") or value_for(result, "status") or "").strip().lower()
        reason = first_present(
            result,
            ["validation_set_not_applicable_reason", "validation_set_skipped_reason", "validation_set_blocked_reason", "reason", "blockers"],
        )
        return status == "not_applicable" and non_empty(reason) and field == "evidence_paths" and has_explicit_empty(result, field, list)
    if target == "schema_post_derive":
        status = str(value_for(result, "schema_status") or value_for(result, "status") or "").strip().lower()
        reason = first_present(
            result,
            ["schema_skipped_reason", "schema_terminal_reason", "schema_blocked_reason", "reason", "blockers"],
        )
        terminal = {"terminal", "terminal_blocked", "skipped", "not_applicable", "blocked", "deferred"}
        return status in terminal and non_empty(reason) and field == "evidence_paths" and has_explicit_empty(result, field, list)
    return False


def long_run_state_checked(contract_context: dict[str, Any] | None, result: dict[str, Any]) -> bool:
    markers: list[Any] = [result.get("long_run_state_checked")]
    if isinstance(contract_context, dict):
        markers.append(contract_context.get("long_run_state_checked"))
        cycle_state = contract_context.get("cycle_state")
        if isinstance(cycle_state, dict):
            markers.append(cycle_state.get("long_run_state_checked"))
        long_run_state = contract_context.get("long_run_state")
        if isinstance(long_run_state, dict):
            markers.append(long_run_state.get("checked"))
    return any(value is True for value in markers)


def pending_long_run_context(contract_context: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Extract scalar pending-run evidence from a caller-supplied cycle context."""

    if not isinstance(contract_context, dict):
        return []
    candidates: list[dict[str, Any]] = []
    seen_objects: set[int] = set()

    def append(value: Any) -> None:
        if isinstance(value, dict) and id(value) not in seen_objects:
            candidates.append(value)
            seen_objects.add(id(value))

    append(contract_context)
    for key in ("latest_event", "run", "monitor_result"):
        append(contract_context.get(key))
    steps = contract_context.get("steps")
    if isinstance(steps, dict):
        for value in steps.values():
            append(value)
    events = contract_context.get("events")
    if isinstance(events, list):
        for value in events:
            append(value)
    latest_events = contract_context.get("latest_events")
    if isinstance(latest_events, list):
        for value in latest_events:
            append(value)
    cycle_state = contract_context.get("cycle_state")
    if isinstance(cycle_state, dict):
        append(cycle_state)
        append(cycle_state.get("latest_event"))
        nested_latest_events = cycle_state.get("latest_events")
        if isinstance(nested_latest_events, list):
            for value in nested_latest_events:
                append(value)
        nested_events = cycle_state.get("events")
        if isinstance(nested_events, list):
            for value in nested_events:
                append(value)

    pending: list[dict[str, Any]] = []
    seen_runs: set[tuple[str, str, str]] = set()
    for candidate in candidates:
        status = str(
            candidate.get("execution_status")
            or candidate.get("source_status")
            or candidate.get("status")
            or ""
        ).strip().lower()
        event_kind = str(candidate.get("event_kind") or "").strip().lower()
        role = str(candidate.get("long_run_role") or "").strip().lower()
        run_id = str(candidate.get("run_id") or "").strip()
        is_long_run = bool(candidate.get("long_run_branch")) or event_kind.startswith("long_run_") or role in {
            "launch",
            "monitor",
            "harvest",
            "finalize",
        }
        if status not in PENDING_LONG_RUN_STATUSES or not (is_long_run or run_id):
            continue
        task_id = str(candidate.get("owner_task_id") or candidate.get("task_id") or "").strip()
        identity = (run_id, task_id, status)
        if identity in seen_runs:
            continue
        seen_runs.add(identity)
        pending.append(
            {
                "run_id": run_id or None,
                "task_id": task_id or None,
                "execution_status": status,
                "event_kind": event_kind or None,
                "remaining_validation": candidate.get("remaining_validation"),
            }
        )
    return pending


def _validate(
    target: str,
    result: dict[str, Any],
    mode: str,
    rule_registry: RuleRegistry,
    contract_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    derive_mode = str(first_present(result, ["derive_mode", "mode", "derive.mode", "result.derive_mode"]) or "").strip().lower()
    if target == "derive" and derive_mode == "initial_init":
        required_fields = [
            "next_task_id",
            "selected_task_source",
            "progress_kind",
            "semantic_signature",
            "evidence_paths",
        ]
    else:
        required_fields = COMMON_FIELDS[target]
    missing = [
        field
        for field in required_fields
        if not has_value(result, field) and not reasoned_na_allows_explicit_empty(target, field, result)
    ]
    severity = "block" if mode == "block" or target == "report" else "warn"
    for field in missing:
        add(findings, severity, "missing_required_field", f"`{target}` result is missing `{field}`.", {"field": field})

    if target in AGENT_ROUTING_TARGETS:
        applicability = str(value_for(result, "agent_routing_applicability") or "").lower()
        if applicability not in {"delegated", "deterministic_only", "delegation_unavailable"}:
            add(
                findings,
                severity,
                "agent_routing_applicability_missing",
                "Agent-bearing phase must declare whether work was delegated, deterministic-only, or unavailable.",
            )
        elif applicability == "delegated":
            for field in ("policy_id", "profile_id", "routing_tier", "requested_model", "requested_reasoning_effort", "routing_reason_codes", "routing_enforcement"):
                if not has_value(result, field):
                    add(findings, severity, "delegated_routing_evidence_missing", f"Delegated result is missing `{field}`.", {"field": field})
            if value_for(result, "routing_violations") is None:
                add(findings, severity, "delegated_routing_evidence_missing", "Delegated result is missing `routing_violations`.", {"field": "routing_violations"})
            requested_model = str(value_for(result, "requested_model") or "")
            requested_effort = str(value_for(result, "requested_reasoning_effort") or "")
            enforcement = str(value_for(result, "routing_enforcement") or "")
            claim = {
                "policy_id": value_for(result, "policy_id"),
                "profile_id": value_for(result, "profile_id"),
                "routing_tier": value_for(result, "routing_tier"),
                "requested_model": requested_model,
                "requested_reasoning_effort": requested_effort,
                "routing_reason_codes": value_for(result, "routing_reason_codes"),
                "routing_signals": value_for(result, "routing_signals") or {},
                "routing_signal_evidence": value_for(result, "routing_signal_evidence") or {},
                "routing_violations": value_for(result, "routing_violations") or [],
                "final_direction_ownership": value_for(result, "final_direction_ownership"),
                "max_escalation_reason": value_for(result, "max_escalation_reason"),
                "prior_tier5_unresolved": value_for(result, "prior_tier5_unresolved"),
                "prior_tier5_evidence": value_for(result, "prior_tier5_evidence"),
                "agent_count": value_for(result, "agent_count"),
            }
            hard_routing_codes = {
                "unknown_model_effort_profile",
                "target_profile_mismatch",
                "routing_policy_id_mismatch",
                "reported_routing_violations",
                "routing_tier_missing_or_invalid",
                "unknown_routing_tier",
                "profile_tier_mismatch",
                "dynamic_tier_not_justified",
                "dynamic_tier_reason_missing",
                "unknown_routing_signals",
                "tier5_signal_evidence_missing",
                "direction_ownership_unclassified",
                "direction_signal_conflicts_with_ownership",
                "direction_signal_missing_for_owned_decision",
                "tier_model_mismatch",
                "tier_effort_mismatch",
                "max_not_allowed_for_profile_or_tier",
                "max_prior_tier5_evidence_missing",
                "max_escalation_reason_missing",
                "max_agent_count_invalid",
                "delegated_ultra_prohibited",
            }
            for routing_finding in MODEL_EFFORT_ROUTER.validate_claim(claim, MODEL_EFFORT_POLICY, target):
                code = str(routing_finding.get("code") or "model_effort_routing_invalid")
                add(
                    findings,
                    "block" if code in hard_routing_codes else severity,
                    code,
                    "Delegated model/effort claim violates the tier routing policy.",
                    routing_finding,
                )
            if requested_model and requested_model not in SUPPORTED_AGENT_MODELS:
                add(findings, "block", "unsupported_requested_model", "Requested model is outside the tier routing policy.", {"requested_model": requested_model})
            if requested_effort and requested_effort not in SUPPORTED_AGENT_EFFORTS:
                add(findings, "block", "unsupported_requested_effort", "Requested effort is outside the tier routing policy.", {"requested_reasoning_effort": requested_effort})
            if enforcement and enforcement not in ROUTING_ENFORCEMENT_VALUES:
                add(findings, "block", "invalid_routing_enforcement", "Delegated result has invalid routing enforcement.", {"routing_enforcement": enforcement})
            if enforcement == "enforced" and (not has_value(result, "actual_model") or not has_value(result, "actual_reasoning_effort")):
                add(findings, severity, "enforced_routing_actual_evidence_missing", "Enforced routing requires actual model and effort evidence.")
            if enforcement in {"prompt_only", "inherited_unverified"} and not has_value(result, "routing_limitation"):
                add(findings, severity, "routing_limitation_missing", "Non-enforced routing requires a concrete limitation note.")
            actual_model = str(value_for(result, "actual_model") or "")
            actual_effort = str(value_for(result, "actual_reasoning_effort") or "")
            if actual_model and actual_model not in SUPPORTED_AGENT_MODELS:
                add(findings, "block", "actual_model_outside_policy", "Actual model is outside the tier routing policy.", {"actual_model": actual_model})
            if actual_effort and actual_effort not in SUPPORTED_AGENT_EFFORTS:
                add(findings, "block", "unsupported_actual_effort", "Actual effort is outside the tier routing policy.", {"actual_reasoning_effort": actual_effort})
            if actual_model and requested_model and actual_model != requested_model:
                add(findings, "block", "actual_model_route_mismatch", "Actual model does not match the validated requested route.", {"requested_model": requested_model, "actual_model": actual_model})
            if actual_effort and requested_effort and actual_effort != requested_effort:
                add(findings, "block", "actual_effort_route_mismatch", "Actual effort does not match the validated requested route.", {"requested_reasoning_effort": requested_effort, "actual_reasoning_effort": actual_effort})
        elif applicability == "delegation_unavailable" and not has_value(result, "routing_limitation"):
            add(findings, severity, "routing_limitation_missing", "Unavailable delegation requires a concrete routing limitation.")

    def require_context_field(field: str, code: str, message: str) -> None:
        if has_value(result, field):
            return
        if field not in missing:
            missing.append(field)
        add(findings, "block" if mode == "block" or target == "report" else "warn", code, message, {"field": field})

    raw_step = result.get("step")
    step = str(raw_step).strip() if raw_step is not None else ""
    if not step:
        if "step" not in missing:
            missing.append("step")
        add(
            findings,
            "block" if mode == "block" else "warn",
            "ledger_step_missing",
            f"`{target}` result lacks top-level canonical `step`; direct ledger append must pass `--step {target}` or use an event envelope.",
            {"expected_step": target},
        )
    elif step not in CANONICAL_LEDGER_STEPS:
        add(
            findings,
            "block" if mode == "block" else "warn",
            "ledger_step_noncanonical",
            f"`{target}` result has noncanonical ledger `step`.",
            {"step": step, "expected_step": target},
        )
    elif step != target:
        add(
            findings,
            "block" if mode == "block" else "warn",
            "ledger_step_mismatch",
            f"`{target}` result has `step: {step}`; expected `step: {target}` for direct ledger append.",
            {"step": step, "expected_step": target},
        )

    if target in ADVICE_REQUIRED_TARGETS and active_advice_present(result) and not has_value(result, "used_advice"):
        if not advice_handling_rationale_present(result):
            add(
                findings,
                "block",
                "active_advice_unhandled",
                f"`{target}` result has active external advice in scope but lacks `used_advice` or an explicit advice defer/reject/not-applicable rationale.",
                {"required": ["used_advice", "advice_deferred_reason|advice_rejected_reason|advice_not_applicable_reason|advice_handling_rationale"]},
            )

    explicit_report_key_divergence = boolish(
        first_present(
            result,
            [
                "report_key_divergence",
                "report_key_integrity_gate.report_key_divergence",
                "validation.report_key_integrity_gate.report_key_divergence",
                "result.report_key_integrity_gate.report_key_divergence",
            ],
        )
    )
    auto_report_key_divergences = report_key_divergences(result)
    auto_report_key_duplicate_matches = report_key_duplicate_matches(result)
    if explicit_report_key_divergence or auto_report_key_divergences:
        report_key_severity = "block" if mode == "block" or target in {"validate", "report"} else "warn"
        add(
            findings,
            report_key_severity,
            "report_key_divergence",
            "`report_key_divergence` means one report contains duplicate terminal keys with divergent values; pass/close/adoption/baseline/comparison consumption is invalid until the report is repaired.",
            {"auto_detected": auto_report_key_divergences[:20], "explicit_report_key_divergence": explicit_report_key_divergence},
        )
    if auto_report_key_duplicate_matches:
        add(
            findings,
            "warn",
            "report_key_duplicate_schema_debt",
            "Matching duplicate terminal report keys are schema debt; consumption may continue, but the report should be normalized to one authoritative copy.",
            {"auto_detected": auto_report_key_duplicate_matches[:20]},
        )

    auto_report_body_divergences = actual_report_body_divergences(result)
    report_body_divergence = boolish(
        first_present(
            result,
            [
                "report_body_divergence",
                "actual_artifact_truth.report_body_divergence",
                "validation.actual_artifact_truth.report_body_divergence",
                "result.report_body_divergence",
            ],
        )
    ) or bool(auto_report_body_divergences)
    actual_truth_required = boolish(
        first_present(
            result,
            [
                "actual_body_truth_required",
                "acceptance_required_actual_body_truth",
                "target_metric_delta.actual_body_truth_required",
                "acceptance.actual_body_truth_required",
            ],
        )
    )
    truth_basis = str(
        first_present(
            result,
            [
                "truth_basis",
                "actual_body_truth_basis",
                "actual_artifact_truth.truth_basis",
                "target_metric_delta.truth_basis",
            ],
        )
        or ""
    ).strip().lower()
    if report_body_divergence:
        add(
            findings,
            "block" if mode == "block" or target in {"validate", "report"} else "warn",
            "report_body_divergence",
            "The canonical actual-artifact body projection disagrees with the consumed report; this is distinct from duplicate report-key divergence.",
            {"auto_detected": auto_report_body_divergences[:20]},
        )
    if actual_truth_required and truth_basis in {"", "not_evaluated", "missing", "unknown"}:
        add(
            findings,
            "block" if mode == "block" or target == "validate" else "warn",
            "actual_body_truth_not_evaluated",
            "Acceptance-required actual-artifact body truth was not independently evaluated.",
        )

    required_consumer_ids = list_values(
        first_present(
            result,
            [
                "required_consumer_ids",
                "adapter_contract.required_consumer_ids",
                "consumer_context_conformance.required_consumer_ids",
            ],
        )
    )
    conformance_rows_value = first_present(
        result,
        [
            "consumer_context_conformance.rows",
            "consumer_context_conformance",
            "adapter_consumer_conformance",
        ],
    )
    if isinstance(conformance_rows_value, dict):
        conformance_rows = conformance_rows_value.get("rows") or []
    else:
        conformance_rows = conformance_rows_value or []
    conformance_by_id = {
        str(row.get("consumer_context_id")): row
        for row in conformance_rows
        if isinstance(row, dict) and row.get("consumer_context_id")
    }
    invalid_consumers: list[str] = []
    for consumer_id in required_consumer_ids:
        row = conformance_by_id.get(str(consumer_id))
        if not row or not all(
            boolish(row.get(field))
            for field in ("adapter_loaded", "required_hook_callable", "hook_signature_compatible", "return_contract_valid")
        ) or not non_empty(row.get("probe_evidence_id")):
            invalid_consumers.append(str(consumer_id))
    if invalid_consumers:
        add(
            findings,
            "block" if mode == "block" or target == "validate" else "warn",
            "required_consumer_context_not_evaluated",
            "Required adapter consumer contexts lack external loader probe evidence; root import or adapter self-attestation is insufficient.",
            {"consumer_context_ids": invalid_consumers},
        )

    if target == "validate":
        validation_verdict_early = str(value_for(result, "validation_verdict") or "").strip().lower()
        required_artifact_class_early = str(first_present(result, ["required_artifact_class", "acceptance.required_artifact_class"]) or "").strip()
        observed_artifact_class_early = str(first_present(result, ["observed_artifact_class", "artifact_class", "target_metric_delta.artifact_class"]) or "").strip()
        if (
            validation_verdict_early in {"complete", "passed", "pass", "success"}
            and required_artifact_class_early
            and observed_artifact_class_early
            and required_artifact_class_early != observed_artifact_class_early
        ):
            add(
                findings,
                "block" if mode == "block" else "warn",
                "validate_complete_required_artifact_class_mismatch",
                "Completion is invalid when the observed artifact class differs from the acceptance-required artifact class, regardless of progress verdict.",
                {"required_artifact_class": required_artifact_class_early, "observed_artifact_class": observed_artifact_class_early},
            )
    execution_status = str(value_for(result, "execution_status") or "").lower()
    pending_long_runs = pending_long_run_context(contract_context)
    checked_long_run_state = long_run_state_checked(contract_context, result)
    context = RuleContext(
        target=target,
        result=result,
        mode=mode,
        findings=findings,
        missing=missing,
        require_context_field=require_context_field,
        metadata={
            "contract_context": contract_context,
            "execution_status": execution_status,
            "explicit_report_key_divergence": explicit_report_key_divergence,
            "auto_report_key_divergences": auto_report_key_divergences,
            "pending_long_runs": pending_long_runs,
            "long_run_state_checked": checked_long_run_state,
        },
    )
    SESSION_AUDIT_RULE.validate(context)
    rule_registry.validate(context)

    status = "ok"
    if any(item["severity"] == "block" for item in findings):
        status = "block"
    elif findings:
        status = "warn"
    return {"status": status, "target": target, "mode": mode, "findings": findings, "missing_fields": missing}


class ResultContractValidator:
    """Reusable validator with an injectable target-rule registry."""

    def __init__(self, rule_registry: RuleRegistry | None = None) -> None:
        self.rule_registry = rule_registry or default_rule_registry()

    def validate(
        self,
        target: str,
        result: dict[str, Any],
        mode: str = "warn",
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if target not in TARGETS:
            raise ValueError(f"unsupported result-contract target: {target}")
        if mode not in {"warn", "block"}:
            raise ValueError(f"unsupported result-contract mode: {mode}")
        return _validate(target, result, mode, self.rule_registry, context)


DEFAULT_VALIDATOR = ResultContractValidator()


def validate(
    target: str,
    result: dict[str, Any],
    mode: str,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Backward-compatible functional facade."""

    return DEFAULT_VALIDATOR.validate(target, result, mode, context)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate a subskill result contract for orchestrate-task-cycle.")
    parser.add_argument("--target", required=True, choices=sorted(TARGETS))
    parser.add_argument("--result", default="-", help="Result JSON path, JSON string, or '-' for stdin.")
    parser.add_argument("--context", help="Optional cycle/long-run context JSON path or JSON string.")
    parser.add_argument("--mode", choices=("warn", "block"), default="warn")
    args = parser.parse_args(argv)

    contract_context = load_json(args.context) if args.context else None
    output = validate(args.target, load_json(args.result), args.mode, contract_context)
    json.dump(output, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0 if output["status"] != "block" else 2


if __name__ == "__main__":
    raise SystemExit(main())
