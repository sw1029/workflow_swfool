from __future__ import annotations

from typing import Any

from . import metric_comparator as _metric_comparator
from . import metric_observation as _metric_observation


def build_primary_metric_packet(
    *,
    contract: dict[str, Any],
    current_value: Any,
    previous: Any,
    high_water: Any,
    expected_artifact_ref: dict[str, Any],
    source_separation_gate: dict[str, Any],
    budget_contract: dict[str, Any],
    state: dict[str, Any],
) -> dict[str, Any]:
    stalled = bool(state["stalled"])
    moved = bool(state["moved"])
    reason = state.get("not_evaluated_reason")
    observation = _metric_observation.build_metric_observation(
        contract,
        current_value,
        expected_artifact_ref,
        source_separation_gate,
        basis_migration={
            "status": state["basis_migration_status"],
            "receipt": state["basis_migration_receipt"],
            "prior_observation_sha256": state[
                "basis_migration_prior_observation_sha256"
            ],
            "prior_lineage_id": state["basis_migration_prior_lineage_id"],
            "new_lineage_id": state["basis_migration_new_lineage_id"],
        },
    )
    result = {
        "gate": "G-CHAIN-PRIMARY-METRIC",
        **contract,
        "metric_comparability_status": state["comparability"],
        "metric_comparison_relation": state["relation"],
        "primary_metric_value": current_value,
        "previous_primary_metric_value": previous,
        "primary_metric_high_water": high_water,
        "primary_metric_high_water_sha256": _metric_comparator.metric_value_sha256(
            contract, high_water
        ),
        "metric_observation": observation,
        "metric_observation_sha256": _metric_observation.metric_observation_sha256(
            observation
        ),
        "primary_metric_high_water_moved": moved,
        "raw_primary_metric_high_water_moved": state["raw_moved"],
        "evidence_provenance": state["effective_provenance"],
        "declared_evidence_provenance": state["declared_provenance"],
        "independent_source_separation_status": state["source_separation_status"],
        "verification_source_separation_gate": source_separation_gate,
        "attested_only_movement": state["attested_only"],
        "primary_metric_scope_key": state["scope_key"],
        "artifact_binding_status": "exact",
        "basis_migration_observed": state["basis_migration_observed"],
        "basis_migration_status": state["basis_migration_status"],
        "basis_migration_receipt": state["basis_migration_receipt"],
        "basis_migration_issues": state["basis_migration_issues"],
        "basis_migration_prior_observation_sha256": state[
            "basis_migration_prior_observation_sha256"
        ],
        "basis_migration_prior_lineage_id": state["basis_migration_prior_lineage_id"],
        "basis_migration_new_lineage_id": state["basis_migration_new_lineage_id"],
        "primary_metric_zero_movement_streak": state["zero_streak"],
        "primary_metric_stall_cap": state["cap_value"],
        "budget_evaluation": budget_contract,
        "budget_evaluation_status": budget_contract["budget_evaluation_status"],
        "primary_metric_stalled": stalled,
        "evaluation_status": state["evaluation_status"],
        "status": (
            "block"
            if stalled
            else "warn"
            if state["attested_only"] or reason
            else "pass"
            if moved
            else "ok"
        ),
        "constrains_disposition": stalled,
        "allowed_dispositions": [
            "goal_productive",
            "terminal_blocked",
            "user_escalation",
        ],
    }
    if reason is not None:
        result["not_evaluated_reason"] = reason
    return result
