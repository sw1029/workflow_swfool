"""Consumed-item acceptance checks grouped by independent policy axis."""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ..acceptance_contract import acceptance_verifier_contract
from .packet_io import non_empty, truthy

FindingAdder = Callable[..., None]


def validate_verifier_acceptance(record: dict[str, Any], item: dict[str, Any], result: dict[str, Any], verifier_contract: dict[str, Any], explicit_descope: bool, item_id: str, directive_id: str, add: FindingAdder) -> None:
    verifier_gate = result.get("acceptance_verifier_gate") if isinstance(result.get("acceptance_verifier_gate"), dict) else {}
    verifier_gate = verifier_gate or acceptance_verifier_contract(result)
    verifier_required = truthy(
        verifier_contract.get("verifier_required")
        or verifier_contract.get("required")
        or verifier_gate.get("verifier_required")
        or verifier_gate.get("required")
    ) or non_empty(verifier_contract.get("required_verifier")) or non_empty(verifier_gate.get("required_verifier"))
    evaluation_status = str(
        verifier_gate.get("evaluation_status")
        or verifier_contract.get("evaluation_status")
        or ""
    ).strip().lower()
    required_hooks = (
        verifier_gate.get("required_gate_hooks")
        or verifier_contract.get("required_gate_hooks")
        or record.get("required_gate_hooks")
        or item.get("required_gate_hooks")
    )
    hook_status = str(
        verifier_gate.get("gate_hook_status")
        or verifier_contract.get("gate_hook_status")
        or record.get("gate_hook_status")
        or item.get("gate_hook_status")
        or ""
    ).strip().lower()
    pass_with_coupled_verifier = truthy(
        verifier_gate.get("pass_with_coupled_verifier")
        or verifier_contract.get("pass_with_coupled_verifier")
        or result.get("pass_with_coupled_verifier")
        or (
            result.get("coupled_verifier_gate", {}).get("pass_with_coupled_verifier")
            if isinstance(result.get("coupled_verifier_gate"), dict)
            else False
        )
    )
    if verifier_required and (evaluation_status != "pass" or pass_with_coupled_verifier) and not explicit_descope:
        add(
            "block",
            "acceptance_verifier_not_passed_item_consumed",
            "Consumed measurable pack items require each required live verifier to pass without same-changeset verifier-source coupling, or an explicit descope decision with residual scope.",
            {
                "item_id": item_id,
                "directive_id": directive_id or None,
                "evaluation_status": evaluation_status or None,
                "pass_with_coupled_verifier": pass_with_coupled_verifier,
            },
        )
    if non_empty(required_hooks) and hook_status in {"", "not_supplied", "absent", "missing", "fail_quiet", "not_evaluated"} and not explicit_descope:
        add(
            "block",
            "required_gate_hook_missing_item_consumed",
            "Consumed measurable pack items cannot depend on an acceptance-required gate hook that is absent, fail-quiet, or not_evaluated; preserve hook-supply work or residual scope.",
            {
                "item_id": item_id,
                "directive_id": directive_id or None,
                "gate_hook_status": hook_status or None,
            },
        )
    goal_axis_contract = (
        record.get("goal_axis_contract")
        if isinstance(record.get("goal_axis_contract"), dict)
        else item.get("goal_axis_contract") if isinstance(item.get("goal_axis_contract"), dict)
        else {}
    )
    goal_axis_gate = result.get("goal_axis_completeness_gate") if isinstance(result.get("goal_axis_completeness_gate"), dict) else {}
    pass_with_unobserved_axes = truthy(
        goal_axis_gate.get("pass_with_unobserved_axes")
        or goal_axis_contract.get("pass_with_unobserved_axes")
        or result.get("pass_with_unobserved_axes")
        or item.get("pass_with_unobserved_axes")
    )
    unobserved_goal_axes = (
        goal_axis_gate.get("unobserved_goal_axes")
        or goal_axis_contract.get("unobserved_goal_axes")
        or result.get("unobserved_goal_axes")
        or item.get("unobserved_goal_axes")
    )
    if (pass_with_unobserved_axes or non_empty(unobserved_goal_axes)) and not explicit_descope:
        add(
            "block",
            "unobserved_goal_axes_item_consumed",
            "Consumed review-backed measurable pack items require at least one mapped observing axis per active goal, or explicit residual/descope handling.",
            {
                "item_id": item_id,
                "directive_id": directive_id or None,
                "unobserved_goal_axes": unobserved_goal_axes or None,
            },
        )


def validate_evidence_acceptance(item: dict[str, Any], result: dict[str, Any], explicit_descope: bool, item_id: str, directive_id: str, add: FindingAdder) -> None:
    evidence_gate = result.get("evidence_provenance_gate") if isinstance(result.get("evidence_provenance_gate"), dict) else {}
    attested_only = truthy(result.get("attested_only_movement") or evidence_gate.get("attested_only_movement"))
    producer_attested = result.get("producer_attested_fields") or evidence_gate.get("producer_attested_fields")
    independently_verified = result.get("independently_verified_fields") or evidence_gate.get("independently_verified_fields")
    if (attested_only or (producer_attested and not independently_verified)) and not explicit_descope:
        add(
            "block",
            "producer_attested_progress_item_consumed",
            "Consumed measurable pack items cannot rely on producer-attested metric movement without independently verified evidence or explicit residual descope.",
            {"item_id": item_id, "directive_id": directive_id or None},
        )
    verification_gate = result.get("verification_source_separation_gate") if isinstance(result.get("verification_source_separation_gate"), dict) else {}
    independent_source_status = str(
        result.get("independent_source_separation_status")
        or verification_gate.get("independent_source_separation_status")
        or evidence_gate.get("independent_source_separation_status")
        or ""
    ).strip().lower()
    independently_verified_downgraded = (
        result.get("independently_verified_downgraded_fields")
        or verification_gate.get("independently_verified_downgraded_fields")
        or evidence_gate.get("independently_verified_downgraded_fields")
    )
    if independently_verified and independent_source_status in {"missing", "overlap", "blocked"} and not explicit_descope:
        add(
            "block",
            "independent_verification_source_not_disjoint_item_consumed",
            "Consumed measurable pack items cannot rely on independently_verified evidence unless verification_input_paths are disjoint from verified artifacts or the axis is self_grounded.",
            {
                "item_id": item_id,
                "directive_id": directive_id or None,
                "independent_source_separation_status": independent_source_status,
            },
        )
    if non_empty(independently_verified_downgraded) and not explicit_descope:
        add(
            "block",
            "downgraded_independent_verification_item_consumed",
            "Consumed measurable pack items cannot count independently_verified fields that were auto-downgraded to attested.",
            {"item_id": item_id, "directive_id": directive_id or None, "downgraded_fields": independently_verified_downgraded},
        )
    reachability_gate = result.get("acceptance_reachability_gate") if isinstance(result.get("acceptance_reachability_gate"), dict) else {}
    envelope_thaw_required = truthy(result.get("envelope_thaw_item_required") or reachability_gate.get("envelope_thaw_item_required"))
    envelope_thaw_item = result.get("envelope_thaw_item") or reachability_gate.get("envelope_thaw_item")
    if envelope_thaw_required and not (explicit_descope or non_empty(envelope_thaw_item)):
        add(
            "block",
            "envelope_thaw_item_missing_item_consumed",
            "Consumed measurable pack items cannot close acceptance that is unreachable under a frozen envelope without a reserved envelope_thaw_item or explicit residual/descope handling.",
            {"item_id": item_id, "directive_id": directive_id or None},
        )
    diagnostics_gate = result.get("diagnostics_unavailable_gate") if isinstance(result.get("diagnostics_unavailable_gate"), dict) else {}
    instrumentation_required = truthy(result.get("instrumentation_supply_required") or diagnostics_gate.get("instrumentation_supply_required"))
    observable_without_instrumentation = truthy(
        result.get("diagnostics_observable_without_new_instrumentation")
        or result.get("existing_diagnostics_sufficient")
        or result.get("success_failure_observable_without_instrumentation")
    )
    if instrumentation_required and not observable_without_instrumentation and not explicit_descope:
        add(
            "block",
            "instrumentation_supply_missing_item_consumed",
            "Consumed measurable pack items cannot close repeated diagnostics_unavailable without instrumentation supply or an explicit observability rationale.",
            {"item_id": item_id, "directive_id": directive_id or None},
        )


def validate_residual_acceptance(record: dict[str, Any], item: dict[str, Any], result: dict[str, Any], explicit_descope: bool, item_id: str, directive_id: str, add: FindingAdder) -> None:
    marginal_repair = truthy(record.get("marginal_repair") or item.get("marginal_repair"))
    next_rung = record.get("next_capability_rung") or item.get("next_capability_rung")
    higher_value = truthy(record.get("marginal_repair_higher_value") or item.get("marginal_repair_higher_value"))
    cost_policy = result.get("residual_gap_cost_policy") if isinstance(result.get("residual_gap_cost_policy"), dict) else {}
    residual_cost_below_policy = truthy(
        record.get("residual_gap_cost_below_policy")
        or item.get("residual_gap_cost_below_policy")
        or result.get("residual_gap_cost_below_policy")
        or cost_policy.get("below_policy")
        or cost_policy.get("cost_disproportionate")
    )
    cycle_fixed_cost = record.get("cycle_fixed_cost") or item.get("cycle_fixed_cost") or result.get("cycle_fixed_cost") or cost_policy.get("cycle_fixed_cost")
    marginal_value_per_cycle_cost = (
        record.get("marginal_value_per_cycle_cost")
        or item.get("marginal_value_per_cycle_cost")
        or result.get("marginal_value_per_cycle_cost")
        or cost_policy.get("marginal_value_per_cycle_cost")
    )
    if marginal_repair and item.get("status") == "consumed" and not (explicit_descope and non_empty(next_rung)) and not higher_value:
        add(
            "block",
            "marginal_repair_item_consumed_without_value_case",
            "Consumed below-threshold residual-gap repairs require explicit descope plus the next capability rung, or recorded higher marginal value.",
            {"item_id": item_id, "directive_id": directive_id or None},
        )
    if cycle_fixed_cost is not None and marginal_repair and not non_empty(marginal_value_per_cycle_cost):
        add(
            "block",
            "residual_cycle_cost_ratio_missing_item_consumed",
            "Consumed residual-gap repairs with cycle-cost evidence require `marginal_value_per_cycle_cost`.",
            {"item_id": item_id, "directive_id": directive_id or None},
        )
    if residual_cost_below_policy and not (explicit_descope and non_empty(next_rung)) and not higher_value:
        add(
            "block",
            "residual_cost_below_policy_item_consumed",
            "Consumed residual-gap repairs below value-per-cycle-cost policy require residual descope plus the next capability rung, or recorded higher value.",
            {"item_id": item_id, "directive_id": directive_id or None},
        )
    count_key_gate = result.get("count_key_hygiene_gate") if isinstance(result.get("count_key_hygiene_gate"), dict) else {}
    generation_dependent_count_key = truthy(
        result.get("generation_dependent_count_key")
        or count_key_gate.get("generation_dependent_count_key")
        or item.get("generation_dependent_count_key")
    )
    generation_key_reset_claim = truthy(
        result.get("family_novelty_claim")
        or result.get("stall_reset_claim")
        or count_key_gate.get("family_novelty_claim")
        or count_key_gate.get("stall_reset_claim")
    )
    effective_count_key = result.get("effective_count_key") or count_key_gate.get("effective_count_key") or result.get("terminal_outcome_family_key")
    if generation_dependent_count_key and not non_empty(effective_count_key):
        add(
            "block",
            "generation_count_key_without_effective_key_item_consumed",
            "Consumed pack items with generation-dependent raw keys must preserve an effective adapter-collapsed count key or terminal-outcome fallback.",
            {"item_id": item_id, "directive_id": directive_id or None},
        )
    if generation_dependent_count_key and generation_key_reset_claim:
        add(
            "block",
            "generation_key_reset_claim_item_consumed",
            "Consumed pack items cannot treat task/advice/pack/cycle/run/date/hash/version churn as a new family or stall reset.",
            {"item_id": item_id, "directive_id": directive_id or None},
        )
