"""Content-bound metric-basis migration receipts.

A verified migration establishes the first baseline in a new lineage.  It never
compares unlike bases and never reports movement or resets prior stall memory.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any

from .durable_projection import bounded_durable_projection


OPAQUE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,511}$")
RECEIPT_FIELDS = frozenset(
    {
        "contract_version",
        "receipt_id",
        "basis_class_id",
        "metric_axis_id",
        "old_metric_basis_id",
        "new_metric_basis_id",
        "old_observation_sha256",
        "new_observation_input_sha256",
        "old_lineage_id",
        "new_lineage_id",
        "mapping_ref",
        "mapping_sha256",
        "basis_mapping",
        "comparability_verdict",
        "provenance_status",
        "verifier_receipt_id",
        "independent_verification_receipt",
        "decision_binding_sha256",
        "verification_gate_sha256",
        "receipt_sha256",
    }
)
MAPPING_FIELDS = frozenset(
    {
        "contract_version",
        "mapping_id",
        "old_metric_basis_id",
        "new_metric_basis_id",
        "mapping_kind",
        "basis_relation",
        "mapping_evidence_id",
        "mapping_evidence_sha256",
        "mapping_contract_sha256",
    }
)
VERIFICATION_FIELDS = frozenset(
    {
        "contract_version",
        "verifier_receipt_id",
        "verifier_id",
        "verifier_revision_sha256",
        "migration_receipt_id",
        "mapping_contract_sha256",
        "old_observation_sha256",
        "new_observation_input_sha256",
        "decision_binding_sha256",
        "verification_gate_sha256",
        "verdict",
        "provenance_status",
        "producer_input_ids",
        "verification_input_ids",
        "source_overlap_status",
        "producer_invariant_owner_id",
        "verifier_invariant_owner_id",
        "invariant_separation_status",
        "evidence_ref",
        "evidence_sha256",
        "receipt_sha256",
    }
)


@dataclass(frozen=True, slots=True)
class BasisMigrationAssessment:
    valid: bool
    issues: tuple[str, ...]
    receipt: dict[str, Any] | None


def _canonical_sha256(value: Any) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _full_sha256(value: Any) -> bool:
    normalized = str(value or "").strip().lower().removeprefix("sha256:")
    return len(normalized) == 64 and all(
        character in "0123456789abcdef" for character in normalized
    )


def _opaque(value: Any) -> bool:
    return isinstance(value, str) and OPAQUE_ID.fullmatch(value.strip()) is not None


def _lineage(value: Any) -> bool:
    return bool(
        isinstance(value, str)
        and value.strip()
        and len(value.strip()) <= 512
        and "/" not in value
        and "\\" not in value
    )


def decision_binding_sha256(binding: dict[str, Any]) -> str:
    return _canonical_sha256(binding)


def verification_gate_sha256(gate: dict[str, Any]) -> str:
    return _canonical_sha256(bounded_durable_projection(gate))


def new_observation_input_sha256(
    contract: dict[str, Any],
    value: Any,
    decision_binding: dict[str, Any],
    verification_gate: dict[str, Any],
) -> str:
    return _canonical_sha256(
        {
            "metric_contract": contract,
            "observed_value": value,
            "decision_artifact_binding": decision_binding,
            "verification_gate_sha256": verification_gate_sha256(verification_gate),
        }
    )


def canonical_basis_migration_receipt_sha256(receipt: dict[str, Any]) -> str:
    return _canonical_sha256(
        {key: value for key, value in receipt.items() if key != "receipt_sha256"}
    )


def canonical_basis_mapping_sha256(mapping: dict[str, Any]) -> str:
    return _canonical_sha256(
        {
            key: value
            for key, value in mapping.items()
            if key != "mapping_contract_sha256"
        }
    )


def canonical_migration_verification_sha256(receipt: dict[str, Any]) -> str:
    return _canonical_sha256(
        {key: value for key, value in receipt.items() if key != "receipt_sha256"}
    )


def _basis_mapping_valid(mapping: Any) -> bool:
    return bool(
        isinstance(mapping, dict)
        and set(mapping) == MAPPING_FIELDS
        and mapping.get("contract_version") == 1
        and all(
            _opaque(mapping.get(field))
            for field in (
                "mapping_id",
                "old_metric_basis_id",
                "new_metric_basis_id",
                "mapping_evidence_id",
            )
        )
        and mapping.get("mapping_kind") == "new_baseline_lineage"
        and mapping.get("basis_relation") == "not_directly_comparable"
        and _full_sha256(mapping.get("mapping_evidence_sha256"))
        and _full_sha256(mapping.get("mapping_contract_sha256"))
        and mapping.get("mapping_contract_sha256")
        == canonical_basis_mapping_sha256(mapping)
    )


def _verification_receipt_valid(receipt: Any) -> bool:
    producer_inputs = (
        receipt.get("producer_input_ids") if isinstance(receipt, dict) else None
    )
    verification_inputs = (
        receipt.get("verification_input_ids") if isinstance(receipt, dict) else None
    )
    return bool(
        isinstance(receipt, dict)
        and set(receipt) == VERIFICATION_FIELDS
        and receipt.get("contract_version") == 1
        and all(
            _opaque(receipt.get(field))
            for field in (
                "verifier_receipt_id",
                "verifier_id",
                "migration_receipt_id",
                "evidence_ref",
                "producer_invariant_owner_id",
                "verifier_invariant_owner_id",
            )
        )
        and all(
            _full_sha256(receipt.get(field))
            for field in (
                "mapping_contract_sha256",
                "old_observation_sha256",
                "new_observation_input_sha256",
                "decision_binding_sha256",
                "verification_gate_sha256",
                "evidence_sha256",
                "receipt_sha256",
                "verifier_revision_sha256",
            )
        )
        and isinstance(producer_inputs, list)
        and bool(producer_inputs)
        and isinstance(verification_inputs, list)
        and bool(verification_inputs)
        and all(_opaque(item) for item in [*producer_inputs, *verification_inputs])
        and len(set(producer_inputs)) == len(producer_inputs)
        and len(set(verification_inputs)) == len(verification_inputs)
        and not set(producer_inputs) & set(verification_inputs)
        and receipt.get("source_overlap_status") == "disjoint"
        and receipt.get("producer_invariant_owner_id")
        != receipt.get("verifier_invariant_owner_id")
        and receipt.get("invariant_separation_status") == "independent"
        and receipt.get("verdict") == "pass"
        and receipt.get("provenance_status") == "independently_verified"
        and receipt.get("receipt_sha256")
        == canonical_migration_verification_sha256(receipt)
    )


def receipt_shape_valid(receipt: dict[str, Any]) -> bool:
    mapping = receipt.get("basis_mapping")
    verification_receipt = receipt.get("independent_verification_receipt")
    return bool(
        set(receipt) == RECEIPT_FIELDS
        and receipt.get("contract_version") == 1
        and all(
            _opaque(receipt.get(field))
            for field in (
                "receipt_id",
                "basis_class_id",
                "metric_axis_id",
                "old_metric_basis_id",
                "new_metric_basis_id",
                "mapping_ref",
                "verifier_receipt_id",
            )
        )
        and _lineage(receipt.get("old_lineage_id"))
        and _lineage(receipt.get("new_lineage_id"))
        and all(
            _full_sha256(receipt.get(field))
            for field in (
                "old_observation_sha256",
                "new_observation_input_sha256",
                "mapping_sha256",
                "decision_binding_sha256",
                "verification_gate_sha256",
                "receipt_sha256",
            )
        )
        and receipt.get("comparability_verdict") == "new_baseline_required"
        and receipt.get("provenance_status") == "independently_verified"
        and receipt.get("old_metric_basis_id") != receipt.get("new_metric_basis_id")
        and _basis_mapping_valid(mapping)
        and mapping.get("mapping_id") == receipt.get("mapping_ref")
        and mapping.get("mapping_contract_sha256") == receipt.get("mapping_sha256")
        and mapping.get("old_metric_basis_id") == receipt.get("old_metric_basis_id")
        and mapping.get("new_metric_basis_id") == receipt.get("new_metric_basis_id")
        and _verification_receipt_valid(verification_receipt)
        and verification_receipt.get("verifier_receipt_id")
        == receipt.get("verifier_receipt_id")
        and verification_receipt.get("migration_receipt_id")
        == receipt.get("receipt_id")
        and verification_receipt.get("mapping_contract_sha256")
        == receipt.get("mapping_sha256")
        and verification_receipt.get("old_observation_sha256")
        == receipt.get("old_observation_sha256")
        and verification_receipt.get("new_observation_input_sha256")
        == receipt.get("new_observation_input_sha256")
        and verification_receipt.get("decision_binding_sha256")
        == receipt.get("decision_binding_sha256")
        and verification_receipt.get("verification_gate_sha256")
        == receipt.get("verification_gate_sha256")
        and receipt.get("receipt_sha256")
        == canonical_basis_migration_receipt_sha256(receipt)
    )


def assess_basis_migration_receipt(
    value: Any,
    *,
    prior_gate: dict[str, Any],
    contract: dict[str, Any],
    current_value: Any,
    decision_binding: dict[str, Any],
    verification_gate: dict[str, Any],
    new_lineage_id: str,
    independently_verified: bool,
) -> BasisMigrationAssessment:
    if not isinstance(value, dict):
        return BasisMigrationAssessment(False, ("receipt_missing",), None)
    issues: list[str] = []
    if not receipt_shape_valid(value):
        issues.append("receipt_shape_or_digest_invalid")
    expected = {
        "metric_axis_id": contract.get("metric_id"),
        "old_metric_basis_id": prior_gate.get("metric_basis_id"),
        "new_metric_basis_id": contract.get("metric_basis_id"),
        "old_observation_sha256": prior_gate.get("metric_observation_sha256"),
        "new_observation_input_sha256": new_observation_input_sha256(
            contract, current_value, decision_binding, verification_gate
        ),
        "old_lineage_id": prior_gate.get("primary_metric_scope_key"),
        "new_lineage_id": new_lineage_id,
        "decision_binding_sha256": decision_binding_sha256(decision_binding),
        "verification_gate_sha256": verification_gate_sha256(verification_gate),
    }
    for field, expected_value in expected.items():
        if value.get(field) != expected_value:
            issues.append(f"{field}_mismatch")
    if not independently_verified:
        issues.append("independent_verification_missing")
    return BasisMigrationAssessment(
        valid=not issues,
        issues=tuple(sorted(set(issues))),
        receipt=dict(value) if not issues else None,
    )


__all__ = (
    "BasisMigrationAssessment",
    "assess_basis_migration_receipt",
    "canonical_basis_migration_receipt_sha256",
    "canonical_basis_mapping_sha256",
    "canonical_migration_verification_sha256",
    "decision_binding_sha256",
    "new_observation_input_sha256",
    "receipt_shape_valid",
    "verification_gate_sha256",
)
