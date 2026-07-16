from __future__ import annotations

from ..runtime_dependencies import (
    bool_value,
    budget_value,
    observed_delta_class,
    previous_micro_hardening_count_for_count_key,
    terminal_outcome_changed,
    updated_high_water,
)

from ..evaluation_frame import _EvaluationFrame


def _evaluate_progress_semantics(frame: _EvaluationFrame) -> None:
    (
        artifact_decision_evaluated, budget_evaluations, changed_vs_previous, coverage_gate,
        coverage_reconciliation_blocks, disagreement, effective_count_key,
        evidence_provenance_provided, insufficient_reason, measurement_progress_allowed,
        mutation_kind, output_delta, prev_high, provider_request_count, quality,
        quality_delta_policy, registry_rows, validator_gate,
    ) = frame.require(
        'artifact_decision_evaluated', 'budget_evaluations', 'changed_vs_previous',
        'coverage_gate', 'coverage_reconciliation_blocks', 'disagreement',
        'effective_count_key', 'evidence_provenance_provided', 'insufficient_reason',
        'measurement_progress_allowed', 'mutation_kind', 'output_delta', 'prev_high',
        'provider_request_count', 'quality', 'quality_delta_policy', 'registry_rows',
        'validator_gate',
    )
    if not artifact_decision_evaluated:
        semantic_progress = False
        evidence_class = "not_evaluated"
        high_water = prev_high
        count = previous_micro_hardening_count_for_count_key(registry_rows, effective_count_key)
        disposition = "artifact_gate_not_evaluated"
        hard_stop = False
    elif insufficient_reason:
        semantic_progress = False
        evidence_class = "insufficient_evidence"
        high_water = prev_high
        count = previous_micro_hardening_count_for_count_key(registry_rows, effective_count_key) + 1
        disposition = "conservative_hold"
        hard_stop = True
    else:
        semantic_progress = bool_value(coverage_gate.get("quality_delta_pass"))
        evidence_class = "computed"
        allowed_high_water_keys = set(coverage_gate.get("improved_fields") or []) if evidence_provenance_provided else None
        high_water = (
            updated_high_water(
                quality,
                prev_high,
                provider_request_count,
                allowed_high_water_keys,
                quality_delta_policy,
            )
            if semantic_progress
            else prev_high
        )
        previous_family_count = previous_micro_hardening_count_for_count_key(registry_rows, effective_count_key)
        count = 0 if semantic_progress else previous_family_count + 1
        if semantic_progress:
            disposition = "open"
            hard_stop = False
        elif (
            budget_value(budget_evaluations["same_family_nonsemantic_attempts"])
            is not None
            and count
            >= budget_value(budget_evaluations["same_family_nonsemantic_attempts"])
        ):
            disposition = "provider_or_semantic_transition_or_terminal"
            hard_stop = True
        else:
            disposition = "prefer_provider_or_semantic"
            hard_stop = False

    outcome_changed = terminal_outcome_changed(output_delta, changed_vs_previous, semantic_progress)
    delta_class = observed_delta_class(output_delta, changed_vs_previous, semantic_progress)
    forward_mutation_vacuous = artifact_decision_evaluated and mutation_kind == "forward_mutation" and not outcome_changed
    if forward_mutation_vacuous:
        hard_stop = True
    if artifact_decision_evaluated and mutation_kind == "forward_mutation" and outcome_changed and not disagreement and not coverage_reconciliation_blocks:
        changed_vs_previous = True
        count = 0
        hard_stop = False
        if disposition in {"conservative_hold", "provider_or_semantic_transition_or_terminal"}:
            disposition = "forward_mutation_goal_productive_candidate"
    if artifact_decision_evaluated and measurement_progress_allowed:
        hard_stop = False
        if disposition in {"conservative_hold", "provider_or_semantic_transition_or_terminal"}:
            disposition = "measurement_progress_goal_productive_candidate"
    if coverage_reconciliation_blocks:
        hard_stop = True
    if disagreement:
        hard_stop = True
    if bool_value(validator_gate.get("hard_stop_required")):
        hard_stop = True
    frame.update({
        "changed_vs_previous": changed_vs_previous,
        "count": count,
        "delta_class": delta_class,
        "disposition": disposition,
        "evidence_class": evidence_class,
        "forward_mutation_vacuous": forward_mutation_vacuous,
        "hard_stop": hard_stop,
        "high_water": high_water,
        "outcome_changed": outcome_changed,
        "semantic_progress": semantic_progress,
    })
