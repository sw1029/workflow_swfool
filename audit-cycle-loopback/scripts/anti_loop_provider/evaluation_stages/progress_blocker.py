from __future__ import annotations

from ..runtime_dependencies import (
    Any,
    BLOCKER_SIGNATURE_KEYS,
    blocker_mutation_kind,
    bool_value,
    budget_value,
    collapse_root_family,
    first_named_value,
    forward_mutation_streak,
    infer_ladder_rung,
    metric_stall_observation_allowed,
    normalize_ladder_rung,
    row_root_family,
    validator_disagreement_finding,
)

from ..evaluation_frame import _EvaluationFrame


def _evaluate_progress_blocker(frame: _EvaluationFrame) -> None:
    (
        args, budget_evaluations, coverage_gate, current_root_family_key, current_root_key,
        facet_root_map, facet_root_map_missing, family_key, gate_inputs, insufficient_reason,
        latest, latest_terminal_family, output_delta, quality, quality_delta_policy,
        registry_rows, runner_validation, substance_gate,
    ) = frame.require(
        'args', 'budget_evaluations', 'coverage_gate', 'current_root_family_key',
        'current_root_key', 'facet_root_map', 'facet_root_map_missing', 'family_key',
        'gate_inputs', 'insufficient_reason', 'latest', 'latest_terminal_family',
        'output_delta', 'quality', 'quality_delta_policy', 'registry_rows',
        'runner_validation', 'substance_gate',
    )
    blocker_sources: list[Any] = [runner_validation, output_delta, quality, gate_inputs, args.semantic_signature, args.artifact_family]
    current_blocker_signature = (
        args.blocker_signature
        or first_named_value(blocker_sources, BLOCKER_SIGNATURE_KEYS)
        or args.semantic_signature
        or "unknown"
    )
    blocker_root_family = current_root_family_key if facet_root_map_missing else collapse_root_family(facet_root_map, current_root_key, current_blocker_signature)
    latest_blocker = next((row for row in reversed(registry_rows) if row_root_family(row) == blocker_root_family), latest_terminal_family or latest)
    current_rung = normalize_ladder_rung(args.blocker_rung) or infer_ladder_rung(*blocker_sources)
    mutation_kind = blocker_mutation_kind(current_blocker_signature, current_rung, blocker_root_family, latest_blocker)
    previous_forward_count = forward_mutation_streak(registry_rows, family_key)
    current_forward_count = previous_forward_count + (1 if mutation_kind == "forward_mutation" else 0)
    forward_mutation_budget = budget_value(budget_evaluations["forward_mutation_attempts"])
    forward_budget_remaining = (
        max(0, forward_mutation_budget - current_forward_count)
        if forward_mutation_budget is not None
        else None
    )
    force_implementation_cycle = (
        mutation_kind == "forward_mutation"
        and forward_budget_remaining is not None
        and forward_budget_remaining == 0
    )
    disagreement = validator_disagreement_finding(runner_validation, output_delta)
    substance_delta_pass = bool_value(substance_gate.get("substance_delta_pass"))
    metric_evaluation_status = str(
        coverage_gate.get("metric_evaluation_status") or "not_evaluated"
    )
    producer_absence_observed = bool(
        metric_evaluation_status == "not_evaluated"
        and not quality_delta_policy.get("supplied")
        and insufficient_reason
    )
    coverage_gate["producer_absence_observed"] = producer_absence_observed
    artifact_decision_evaluated = bool_value(
        coverage_gate.get("artifact_decision_scope_allowed")
    ) and metric_stall_observation_allowed(
        metric_evaluation_status,
        policy_supplied=bool(quality_delta_policy.get("supplied")),
        producer_absence_reason=insufficient_reason,
    )
    frame.update({
        "artifact_decision_evaluated": artifact_decision_evaluated,
        "blocker_root_family": blocker_root_family,
        "current_blocker_signature": current_blocker_signature,
        "current_rung": current_rung,
        "disagreement": disagreement,
        "force_implementation_cycle": force_implementation_cycle,
        "forward_budget_remaining": forward_budget_remaining,
        "forward_mutation_budget": forward_mutation_budget,
        "mutation_kind": mutation_kind,
        "substance_delta_pass": substance_delta_pass,
    })
