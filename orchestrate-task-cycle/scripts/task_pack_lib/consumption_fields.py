"""Completion provenance and result-gate field population."""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from .contracts import PACK_COHERENCE_VERSION
from .packet_io import preserve_verdict_axes, verify_evidence_files
from .provenance import validate_promotion_provenance
from .storage import bounded_workspace_file, now_iso


def _append_unique(target: dict[str, Any], key: str, values: list[str] | None) -> None:
    if not values:
        return
    current = target.setdefault(key, [])
    for value in values or []:
        if value not in current:
            current.append(value)


def consume_promoted_item(
    root: Path,
    item: dict[str, Any],
    args: argparse.Namespace,
) -> dict[str, Any]:
    if item.get("status") not in {"promoted", "in_progress"}:
        raise SystemExit("mark-consumed requires an item previously promoted through verified provenance.")
    promotion = item.get("promotion")
    if not isinstance(promotion, dict):
        raise SystemExit("mark-consumed requires preserved promotion provenance.")
    completed_task_id = str(promotion.get("task_id") or "").strip()
    if args.task_id and args.task_id != completed_task_id:
        raise SystemExit("mark-consumed task_id must match the promoted task identity.")
    if args.task_path:
        supplied_task_path = bounded_workspace_file(root, args.task_path, "mark-consumed task_path")
        promoted_task_path = bounded_workspace_file(root, promotion.get("task_path"), "Promotion task_path")
        if supplied_task_path != promoted_task_path:
            raise SystemExit("mark-consumed task_path must match the promoted task path.")
    completion_evidence = list(args.completion_evidence_path or [])
    completion_plan = {
        "run_report_path": args.run_report_path,
        "run_report_sha256": args.run_report_sha256,
        "validation_report_path": args.validation_report_path,
        "validation_report_sha256": args.validation_report_sha256,
        "validation_evidence_paths": list(args.validation_evidence_path or []),
        "issue_packet_path": args.issue_packet_path,
        "issue_packet_sha256": args.issue_packet_sha256,
        "evidence_paths": completion_evidence,
    }
    completion_provenance = validate_promotion_provenance(
        root,
        completion_plan,
        completed_task_id,
        str(args.validation_verdict or "").strip().lower(),
    )
    item["completion"] = {
        "completed_task_id": completed_task_id,
        "completed_at": now_iso(),
        "validation_verdict": str(args.validation_verdict or "").strip().lower(),
        "completion_evidence_paths": verify_evidence_files(root, completion_evidence, "Completion evidence_paths"),
        **completion_provenance,
    }
    item["status"] = "consumed"
    return item.setdefault("result", {})


def apply_core_result_fields(
    result: dict[str, Any],
    args: argparse.Namespace,
    verdict_payload: dict[str, Any],
    coherence: dict[str, Any],
) -> None:
    for key, value in (
        ("validation_verdict", args.validation_verdict),
        ("progress_verdict", args.progress_verdict),
        ("progress_kind", args.progress_kind),
        ("semantic_signature", args.semantic_signature),
        ("blocker_signature", args.blocker_signature),
    ):
        if value:
            result[key] = value
    preserve_verdict_axes(
        result,
        verdict_payload,
        require_current=coherence.get("contract_version") == PACK_COHERENCE_VERSION,
    )
    if args.has_supplied_input_delta:
        result.setdefault("positive_input_delta_gate", {})["has_supplied_input_delta"] = True
    if args.supplied_input_artifact_path:
        _append_unique(
            result.setdefault("positive_input_delta_gate", {}),
            "supplied_input_artifact_paths",
            args.supplied_input_artifact_path,
        )


def apply_acceptance_result_fields(result: dict[str, Any], args: argparse.Namespace) -> None:
    if (
        args.acceptance_target_met
        or args.acceptance_diluted
        or args.explicit_descope_decision
        or args.acceptance_provenance_evidence_path
        or args.residual_item_id
    ):
        gate = result.setdefault("acceptance_provenance_gate", {})
        if args.acceptance_target_met:
            gate["target_met"] = True
        if args.acceptance_diluted:
            gate["acceptance_diluted"] = True
        if args.explicit_descope_decision:
            gate["explicit_descope_decision"] = True
        if args.residual_item_id:
            gate["residual_item_id"] = args.residual_item_id
        if args.acceptance_provenance_evidence_path:
            _append_unique(gate, "evidence_paths", args.acceptance_provenance_evidence_path)
    if args.required_verifier or args.acceptance_verifier_status or args.acceptance_verifier_evidence_path:
        gate = result.setdefault("acceptance_verifier_gate", {})
        if args.required_verifier:
            gate["required_verifier"] = args.required_verifier
            gate["verifier_required"] = True
        if args.acceptance_verifier_status:
            gate["evaluation_status"] = args.acceptance_verifier_status
            gate["acceptance_verifier_not_evaluated"] = args.acceptance_verifier_status == "not_evaluated"
            gate["unverifiable_acceptance_contract"] = args.acceptance_verifier_status == "not_evaluated"
        if args.acceptance_verifier_evidence_path:
            _append_unique(gate, "evidence_paths", args.acceptance_verifier_evidence_path)
    if args.required_gate_hook or args.gate_hook_status:
        gate = result.setdefault("acceptance_verifier_gate", {})
        if args.required_gate_hook:
            _append_unique(gate, "required_gate_hooks", args.required_gate_hook)
        if args.gate_hook_status:
            gate["gate_hook_status"] = args.gate_hook_status
            if args.gate_hook_status in {"not_supplied", "absent", "fail_quiet", "not_evaluated"}:
                gate["unverifiable_acceptance_contract"] = True


def apply_evidence_result_fields(result: dict[str, Any], args: argparse.Namespace) -> None:
    if args.pass_with_unobserved_axes or args.unobserved_goal_axis:
        gate = result.setdefault("goal_axis_completeness_gate", {})
        if args.pass_with_unobserved_axes:
            gate["pass_with_unobserved_axes"] = True
        if args.unobserved_goal_axis:
            _append_unique(gate, "unobserved_goal_axes", args.unobserved_goal_axis)
    if (
        args.independently_verified_field
        or args.producer_attested_field
        or args.independent_source_separation_status
        or args.independently_verified_downgraded_field
        or args.verification_input_path
        or args.verified_artifact_path
    ):
        gate = result.setdefault("evidence_provenance_gate", {})
        _append_unique(gate, "independently_verified_fields", args.independently_verified_field)
        _append_unique(gate, "producer_attested_fields", args.producer_attested_field)
        if args.independent_source_separation_status:
            gate["independent_source_separation_status"] = args.independent_source_separation_status
        _append_unique(gate, "independently_verified_downgraded_fields", args.independently_verified_downgraded_field)
        _append_unique(gate, "verification_input_paths", args.verification_input_path)
        _append_unique(gate, "verified_artifact_paths", args.verified_artifact_path)


def apply_policy_result_fields(result: dict[str, Any], args: argparse.Namespace) -> None:
    if args.generation_dependent_count_key or args.effective_count_key:
        gate = result.setdefault("count_key_hygiene_gate", {})
        if args.generation_dependent_count_key:
            gate["generation_dependent_count_key"] = True
            gate["count_key_trace_only"] = True
        if args.effective_count_key:
            gate["effective_count_key"] = args.effective_count_key
    if args.envelope_thaw_item_required or args.envelope_thaw_item or args.thaw_condition or args.thaw_schedule:
        gate = result.setdefault("acceptance_reachability_gate", {})
        if args.envelope_thaw_item_required:
            gate["envelope_thaw_item_required"] = True
        if args.envelope_thaw_item:
            gate["envelope_thaw_item"] = args.envelope_thaw_item
        if args.thaw_condition:
            gate["thaw_condition"] = args.thaw_condition
        if args.thaw_schedule:
            gate["thaw_schedule"] = args.thaw_schedule
    if args.instrumentation_supply_required or args.diagnostics_unavailable_streak is not None or args.existing_diagnostics_sufficient:
        gate = result.setdefault("diagnostics_unavailable_gate", {})
        if args.instrumentation_supply_required:
            gate["instrumentation_supply_required"] = True
        if args.diagnostics_unavailable_streak is not None:
            gate["diagnostics_unavailable_streak"] = args.diagnostics_unavailable_streak
        if args.existing_diagnostics_sufficient:
            result["existing_diagnostics_sufficient"] = True
    if (
        args.cycle_fixed_cost is not None
        or args.marginal_value_per_cycle_cost is not None
        or args.residual_gap_cost_below_policy
        or args.marginal_repair_higher_value
    ):
        policy = result.setdefault("residual_gap_cost_policy", {})
        if args.cycle_fixed_cost is not None:
            policy["cycle_fixed_cost"] = args.cycle_fixed_cost
        if args.marginal_value_per_cycle_cost is not None:
            policy["marginal_value_per_cycle_cost"] = args.marginal_value_per_cycle_cost
        if args.residual_gap_cost_below_policy:
            policy["below_policy"] = True
        if args.marginal_repair_higher_value:
            policy["marginal_repair_higher_value"] = True
