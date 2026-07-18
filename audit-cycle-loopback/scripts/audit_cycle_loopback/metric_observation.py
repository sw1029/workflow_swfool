from __future__ import annotations

import hashlib
import json
from typing import Any

from . import metric_comparator as _metric_comparator
from . import basis_migration as _basis_migration
from .durable_projection import bounded_durable_projection


EXPLICIT_DECISION_FIELDS = (
    "decision_subject_id",
    "subject_class_id",
    "revision_id",
    "subject_digest",
    "lineage_id",
    "freshness_status",
    "body_fingerprint",
    "production_lane",
    "cohort",
    "producer_run",
)
LEGACY_DECISION_FIELDS = (
    "artifact_id",
    "artifact_class",
    "artifact_sha256",
    "production_lane_identity",
    "body_projection_fingerprint",
    "verification_input_ids",
    "input_fingerprints",
)
OBSERVATION_FIELDS = {
    "contract_version",
    "metric_contract",
    "observed_value",
    "observed_value_sha256",
    "decision_artifact_binding",
    "verification_gate_sha256",
    "evidence_provenance",
    "independent_source_separation_status",
    "high_water_value",
    "high_water_value_sha256",
    "zero_movement_streak",
    "stalled",
    "comparability_status",
    "high_water_moved",
    "decision_contribution_allowed",
    "gate_compatibility_sha256",
    "basis_migration_status",
    "basis_migration_receipt",
    "basis_migration_prior_observation_sha256",
    "basis_migration_prior_lineage_id",
    "basis_migration_new_lineage_id",
}


def _sha256(value: Any) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def decision_artifact_binding_projection(
    artifact_ref: dict[str, Any],
) -> dict[str, Any]:
    fields = (
        EXPLICIT_DECISION_FIELDS
        if any(field in artifact_ref for field in EXPLICIT_DECISION_FIELDS[:5])
        else LEGACY_DECISION_FIELDS
    )
    return {field: artifact_ref[field] for field in fields if field in artifact_ref}


def build_metric_observation(
    contract: dict[str, Any],
    value: Any,
    artifact_ref: dict[str, Any],
    source_separation_gate: dict[str, Any],
    *,
    basis_migration: dict[str, Any],
) -> dict[str, Any]:
    return {
        "contract_version": 1,
        "metric_contract": contract,
        "observed_value": value,
        "observed_value_sha256": _metric_comparator.metric_value_sha256(
            contract, value
        ),
        "decision_artifact_binding": decision_artifact_binding_projection(artifact_ref),
        "verification_gate_sha256": _sha256(
            bounded_durable_projection(source_separation_gate)
        ),
        "evidence_provenance": None,
        "independent_source_separation_status": None,
        "high_water_value": None,
        "high_water_value_sha256": None,
        "zero_movement_streak": None,
        "stalled": None,
        "comparability_status": None,
        "high_water_moved": None,
        "decision_contribution_allowed": False,
        "gate_compatibility_sha256": None,
        "basis_migration_status": basis_migration.get("status"),
        "basis_migration_receipt": basis_migration.get("receipt"),
        "basis_migration_prior_observation_sha256": basis_migration.get(
            "prior_observation_sha256"
        ),
        "basis_migration_prior_lineage_id": basis_migration.get("prior_lineage_id"),
        "basis_migration_new_lineage_id": basis_migration.get("new_lineage_id"),
    }


def metric_observation_sha256(observation: dict[str, Any]) -> str:
    return _sha256(observation)


def finalize_metric_observation(gate: dict[str, Any]) -> dict[str, Any]:
    result = dict(gate)
    observation = result.get("metric_observation")
    if not isinstance(observation, dict):
        return result
    finalized = {
        **observation,
        "evidence_provenance": result.get("evidence_provenance"),
        "independent_source_separation_status": result.get(
            "independent_source_separation_status"
        ),
        "high_water_value": result.get("primary_metric_high_water"),
        "high_water_value_sha256": result.get("primary_metric_high_water_sha256"),
        "zero_movement_streak": result.get("primary_metric_zero_movement_streak"),
        "stalled": result.get("primary_metric_stalled"),
        "comparability_status": result.get("metric_comparability_status"),
        "high_water_moved": result.get("primary_metric_high_water_moved"),
        "decision_contribution_allowed": result.get("decision_contribution_allowed")
        is True,
    }
    compatibility = result.get("gate_compatibility")
    finalized["gate_compatibility_sha256"] = (
        _sha256(bounded_durable_projection(compatibility))
        if isinstance(compatibility, dict)
        else None
    )
    result["metric_observation"] = finalized
    result["metric_observation_sha256"] = metric_observation_sha256(finalized)
    return result


def _full_sha256(value: Any) -> bool:
    normalized = str(value or "").strip().lower().removeprefix("sha256:")
    return len(normalized) == 64 and all(
        character in "0123456789abcdef" for character in normalized
    )


def _explicit_binding_valid(binding: dict[str, Any]) -> bool:
    if set(binding) != set(EXPLICIT_DECISION_FIELDS):
        return False
    opaque_fields = (
        "decision_subject_id",
        "subject_class_id",
        "revision_id",
        "lineage_id",
    )
    if not all(
        isinstance(binding.get(field), str) and bool(str(binding[field]).strip())
        for field in opaque_fields
    ):
        return False
    if not _full_sha256(binding.get("subject_digest")):
        return False
    if str(binding.get("freshness_status") or "").strip().lower() != "current":
        return False
    for name in ("body_fingerprint", "production_lane", "cohort", "producer_run"):
        row = binding.get(name)
        if not isinstance(row, dict) or set(row) != {"applicability", "value"}:
            return False
        applicability = str(row.get("applicability") or "").strip().lower()
        if applicability == "not_applicable":
            if row.get("value") is not None:
                return False
        elif applicability == "applicable":
            if row.get("value") in (None, "", [], {}):
                return False
            if name == "body_fingerprint" and not _full_sha256(row.get("value")):
                return False
        else:
            return False
    return True


def _legacy_binding_valid(binding: dict[str, Any]) -> bool:
    required = set(LEGACY_DECISION_FIELDS[:5])
    cohort_fields = set(LEGACY_DECISION_FIELDS[5:])
    supplied_cohort_fields = set(binding) & cohort_fields
    if set(binding) != required | supplied_cohort_fields:
        return False
    if not supplied_cohort_fields:
        return False
    return bool(
        all(binding.get(field) not in (None, "", [], {}) for field in required)
        and _full_sha256(binding.get("artifact_sha256"))
        and _full_sha256(binding.get("body_projection_fingerprint"))
        and (
            binding.get("verification_input_ids") not in (None, [], {})
            or binding.get("input_fingerprints") not in (None, [], {})
        )
    )


def metric_observation_valid(gate: dict[str, Any]) -> bool:
    observation = gate.get("metric_observation")
    if not isinstance(observation, dict) or set(observation) != OBSERVATION_FIELDS:
        return False
    contract = observation.get("metric_contract")
    binding = observation.get("decision_artifact_binding")
    verification = gate.get("verification_source_separation_gate")
    compatibility = gate.get("gate_compatibility")
    if not isinstance(contract, dict) or not isinstance(binding, dict):
        return False
    binding_valid = (
        _explicit_binding_valid(binding)
        if "decision_subject_id" in binding
        else _legacy_binding_valid(binding)
    )
    value_digest = _metric_comparator.metric_value_sha256
    migration_status = observation.get("basis_migration_status")
    migration_receipt = observation.get("basis_migration_receipt")
    migration_observed = gate.get("basis_migration_observed") is True
    migration_valid = bool(
        migration_observed
        and migration_status == "verified_new_baseline"
        and gate.get("basis_migration_status") == migration_status
        and isinstance(migration_receipt, dict)
        and migration_receipt == gate.get("basis_migration_receipt")
        and _basis_migration.receipt_shape_valid(migration_receipt)
        and migration_receipt.get("metric_axis_id") == contract.get("metric_id")
        and migration_receipt.get("new_metric_basis_id")
        == contract.get("metric_basis_id")
        and migration_receipt.get("old_observation_sha256")
        == observation.get("basis_migration_prior_observation_sha256")
        and migration_receipt.get("old_lineage_id")
        == observation.get("basis_migration_prior_lineage_id")
        and migration_receipt.get("new_lineage_id")
        == observation.get("basis_migration_new_lineage_id")
        and migration_receipt.get("new_lineage_id")
        == gate.get("primary_metric_scope_key")
        and migration_receipt.get("decision_binding_sha256")
        == _basis_migration.decision_binding_sha256(binding)
        and migration_receipt.get("verification_gate_sha256")
        == _basis_migration.verification_gate_sha256(verification)
        and migration_receipt.get("new_observation_input_sha256")
        == _basis_migration.new_observation_input_sha256(
            contract, observation.get("observed_value"), binding, verification
        )
    )
    migration_not_applicable = bool(
        not migration_observed
        and migration_status == "not_applicable"
        and gate.get("basis_migration_status") == "not_applicable"
        and migration_receipt is None
        and observation.get("basis_migration_prior_observation_sha256") is None
        and observation.get("basis_migration_prior_lineage_id") is None
        and observation.get("basis_migration_new_lineage_id") is None
    )
    return bool(
        observation.get("contract_version") == 1
        and _metric_comparator.gate_matches_contract(gate, contract)
        and observation.get("observed_value_sha256")
        == value_digest(contract, observation.get("observed_value"))
        and binding_valid
        and isinstance(verification, dict)
        and observation.get("verification_gate_sha256")
        == _sha256(bounded_durable_projection(verification))
        and observation.get("evidence_provenance") == gate.get("evidence_provenance")
        and observation.get("independent_source_separation_status")
        == gate.get("independent_source_separation_status")
        and observation.get("high_water_value") == gate.get("primary_metric_high_water")
        and observation.get("high_water_value_sha256")
        == gate.get("primary_metric_high_water_sha256")
        and observation.get("high_water_value_sha256")
        == value_digest(contract, observation.get("high_water_value"))
        and observation.get("zero_movement_streak")
        == gate.get("primary_metric_zero_movement_streak")
        and observation.get("stalled") == gate.get("primary_metric_stalled")
        and observation.get("comparability_status")
        == gate.get("metric_comparability_status")
        and observation.get("high_water_moved")
        == gate.get("primary_metric_high_water_moved")
        and observation.get("decision_contribution_allowed") is True
        and gate.get("decision_contribution_allowed") is True
        and isinstance(compatibility, dict)
        and str(compatibility.get("gate_compatibility_status") or "").strip().lower()
        == "compatible"
        and observation.get("gate_compatibility_sha256")
        == _sha256(bounded_durable_projection(compatibility))
        and gate.get("metric_observation_sha256")
        == metric_observation_sha256(observation)
        and (migration_valid or migration_not_applicable)
    )


__all__ = (
    "build_metric_observation",
    "decision_artifact_binding_projection",
    "finalize_metric_observation",
    "metric_observation_sha256",
    "metric_observation_valid",
)
