from __future__ import annotations

from .runtime_dependencies import (
    Any,
    bool_value,
    budget_value,
)

from .evaluation_frame import _require_values


def _progress_fields(state: dict[str, Any]) -> dict[str, Any]:
    (
        authoritative_progress, blocker_root_family, body_divergence, budget_evaluations,
        c4_user_escalation_backstop_required, changed_vs_previous, count,
        current_blocker_signature, current_check_ids, current_frontiers, current_rung,
        delta_class, detection_only, detection_streak, detection_streak_cap, dispatch_gate,
        disposition, evidence_class, evidence_gate, force_implementation_cycle,
        forward_budget_remaining, forward_mutation_budget, forward_mutation_vacuous, hard_stop,
        insufficient_reason, measurement_details, measurement_progress,
        measurement_progress_allowed, measurement_streak_cap, measurement_streak_value,
        mutation_kind, outcome_changed, primary_metric_gate, requires_correction_or_terminal,
        semantic_progress, source_separation_gate, task_correction_class, truth_basis,
        truth_required, validator_gate,
    ) = _require_values(
        state,
        (
            'authoritative_progress', 'blocker_root_family', 'body_divergence',
            'budget_evaluations', 'c4_user_escalation_backstop_required',
            'changed_vs_previous', 'count', 'current_blocker_signature', 'current_check_ids',
            'current_frontiers', 'current_rung', 'delta_class', 'detection_only',
            'detection_streak', 'detection_streak_cap', 'dispatch_gate', 'disposition',
            'evidence_class', 'evidence_gate', 'force_implementation_cycle',
            'forward_budget_remaining', 'forward_mutation_budget', 'forward_mutation_vacuous',
            'hard_stop', 'insufficient_reason', 'measurement_details', 'measurement_progress',
            'measurement_progress_allowed', 'measurement_streak_cap',
            'measurement_streak_value', 'mutation_kind', 'outcome_changed',
            'primary_metric_gate', 'requires_correction_or_terminal', 'semantic_progress',
            'source_separation_gate', 'task_correction_class', 'truth_basis', 'truth_required',
            'validator_gate',
        ),
    )
    return {
        "provider_scale_dispatch_gate": dispatch_gate,
        "changed_vs_previous": changed_vs_previous,
        "semantic_progress": semantic_progress,
        "authoritative_semantic_progress": authoritative_progress,
        "truth_basis": truth_basis or ("not_evaluated" if truth_required else None),
        "report_body_divergence": body_divergence,
        "same_family_micro_hardening_count": count,
        "micro_hardening_count": count,
        "same_family_nonsemantic_budget": budget_value(
            budget_evaluations["same_family_nonsemantic_attempts"]
        ),
        "same_family_budget_evaluation": budget_evaluations[
            "same_family_nonsemantic_attempts"
        ],
        "recommended_disposition": disposition,
        "hard_stop_required": hard_stop,
        "evidence_class": evidence_class,
        "insufficient_evidence_reason": insufficient_reason,
        "measurement_progress": measurement_progress,
        "measurement_progress_allowed": measurement_progress_allowed,
        "measurement_streak": measurement_streak_value,
        "measurement_progress_streak_for_root_key": measurement_details["measurement_progress_streak_for_root_key"],
        "measurement_progress_streak_for_root_family": measurement_details["measurement_progress_streak_for_root_family"],
        "measurement_streak_cap": measurement_streak_cap,
        "measurement_budget_evaluation": budget_evaluations[
            "measurement_nonsemantic_attempts"
        ],
        "measurement_check_ids": sorted(current_check_ids),
        "measurement_frontiers_observed": sorted(current_frontiers),
        "measurement_progress_basis": measurement_details["measurement_progress_basis"],
        "blocker_signature": current_blocker_signature,
        "blocker_root_family": blocker_root_family,
        "blocker_ladder_rung": current_rung,
        "blocker_mutation_kind": mutation_kind,
        "forward_mutation_budget": forward_mutation_budget,
        "forward_mutation_budget_remaining": forward_budget_remaining,
        "terminal_outcome_changed": outcome_changed,
        "observed_delta_class": delta_class,
        "forward_mutation_vacuous": forward_mutation_vacuous,
        "force_implementation_cycle": force_implementation_cycle,
        "task_correction_class": task_correction_class,
        "detection_only": detection_only,
        "detection_only_streak_for_root_family": detection_streak,
        "detection_only_streak_cap": detection_streak_cap,
        "detection_budget_evaluation": budget_evaluations[
            "detection_nonsemantic_attempts"
        ],
        "requires_correction_or_terminal": requires_correction_or_terminal,
        "validator_integrity_gate": validator_gate,
        "evidence_provenance_gate": evidence_gate,
        "producer_attested_fields": evidence_gate.get("producer_attested_fields") or [],
        "independently_verified_fields": evidence_gate.get("independently_verified_fields") or [],
        "self_grounded_fields": evidence_gate.get("self_grounded_fields") or [],
        "verification_axes": source_separation_gate.get("verification_axes") or [],
        "attested_only_movement": bool_value(evidence_gate.get("attested_only_movement")),
        "primary_metric_gate": primary_metric_gate,
        "primary_metric_high_water_moved": bool_value(primary_metric_gate.get("primary_metric_high_water_moved")),
        "primary_metric_zero_movement_streak": primary_metric_gate.get("primary_metric_zero_movement_streak"),
        "primary_metric_stalled": bool_value(primary_metric_gate.get("primary_metric_stalled")),
        "c4_user_escalation_backstop_required": c4_user_escalation_backstop_required,
    }
