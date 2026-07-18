from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = SKILL_ROOT / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from audit_cycle_loopback import normalize_primary_metric_gate  # noqa: E402
from audit_cycle_loopback.metric_observation import (  # noqa: E402
    decision_artifact_binding_projection,
    finalize_metric_observation,
    metric_observation_sha256,
)
from audit_cycle_loopback.basis_migration import (  # noqa: E402
    canonical_basis_mapping_sha256,
    canonical_basis_migration_receipt_sha256,
    canonical_migration_verification_sha256,
    decision_binding_sha256,
    new_observation_input_sha256,
    verification_gate_sha256,
)
from audit_cycle_loopback.families import normalize_root_family_key  # noqa: E402
from audit_cycle_loopback.metric_comparator import (  # noqa: E402
    normalize_contract,
    normalize_value,
    primary_metric_scope_key,
)


ARTIFACT_REF = {
    "artifact_id": "artifact_A",
    "artifact_class": "artifact_class_A",
    "artifact_sha256": "a" * 64,
    "production_lane_identity": "lane_L",
    "body_projection_fingerprint": "b" * 64,
    "verification_input_ids": ["cohort_C"],
}
SOURCE_SEPARATION = {
    "independent_source_separation_status": "pass",
    "verification_axes": [
        {"axis_id": "axis_G", "evidence_provenance": "independently_verified"}
    ],
}


def observe(
    metric: dict[str, Any], rows: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    gate = normalize_primary_metric_gate(
        {**metric, **ARTIFACT_REF},
        rows=rows or [],
        cap=3,
        epsilon=0.0,
        provenance={"axis_g": "independently_verified"},
        provenance_hook_provided=True,
        source_separation_gate=SOURCE_SEPARATION,
        expected_artifact_ref=ARTIFACT_REF,
    )
    gate["gate_compatibility"] = {
        "gate_id": "primary_metric_gate",
        "gate_compatibility_status": "compatible",
        "compatibility_basis": "test-owner-contract",
    }
    gate["gate_compatibility_status"] = "compatible"
    gate["decision_contribution_allowed"] = True
    return finalize_metric_observation(gate)


def contract(**overrides: Any) -> dict[str, Any]:
    return {
        "goal_axis_id": "axis_G",
        "metric_basis_id": "basis_A",
        "metric_dimension_id": "dimension_A",
        "metric_subject_id": "subject_A",
        "metric_provenance_id": "provenance_A",
        **overrides,
    }


def basis_migration_receipt(
    prior_gate: dict[str, Any], metric: dict[str, Any]
) -> dict[str, Any]:
    normalized_contract, error = normalize_contract(metric, str(metric["goal_axis_id"]))
    assert error is None
    assert normalized_contract is not None
    current_value, value_error = normalize_value(metric["value"], normalized_contract)
    assert value_error is None
    new_lineage = primary_metric_scope_key(
        normalized_contract, normalize_root_family_key
    )
    binding = decision_artifact_binding_projection(ARTIFACT_REF)
    mapping: dict[str, Any] = {
        "contract_version": 1,
        "mapping_id": "mapping_A",
        "old_metric_basis_id": prior_gate["metric_basis_id"],
        "new_metric_basis_id": normalized_contract["metric_basis_id"],
        "mapping_kind": "new_baseline_lineage",
        "basis_relation": "not_directly_comparable",
        "mapping_evidence_id": "mapping_evidence_A",
        "mapping_evidence_sha256": "c" * 64,
    }
    mapping["mapping_contract_sha256"] = canonical_basis_mapping_sha256(mapping)
    observation_input_sha256 = new_observation_input_sha256(
        normalized_contract,
        current_value,
        binding,
        SOURCE_SEPARATION,
    )
    verification: dict[str, Any] = {
        "contract_version": 1,
        "verifier_receipt_id": "verifier_receipt_A",
        "verifier_id": "verifier_A",
        "verifier_revision_sha256": "e" * 64,
        "migration_receipt_id": "migration_receipt_A",
        "mapping_contract_sha256": mapping["mapping_contract_sha256"],
        "old_observation_sha256": prior_gate["metric_observation_sha256"],
        "new_observation_input_sha256": observation_input_sha256,
        "decision_binding_sha256": decision_binding_sha256(binding),
        "verification_gate_sha256": verification_gate_sha256(SOURCE_SEPARATION),
        "verdict": "pass",
        "provenance_status": "independently_verified",
        "producer_input_ids": ["producer_input_A"],
        "verification_input_ids": ["verification_input_A"],
        "source_overlap_status": "disjoint",
        "producer_invariant_owner_id": "producer_invariant_A",
        "verifier_invariant_owner_id": "verifier_invariant_A",
        "invariant_separation_status": "independent",
        "evidence_ref": "migration_evidence_A",
        "evidence_sha256": "d" * 64,
    }
    verification["receipt_sha256"] = canonical_migration_verification_sha256(
        verification
    )
    receipt: dict[str, Any] = {
        "contract_version": 1,
        "receipt_id": "migration_receipt_A",
        "basis_class_id": "basis_class_A",
        "metric_axis_id": normalized_contract["metric_id"],
        "old_metric_basis_id": prior_gate["metric_basis_id"],
        "new_metric_basis_id": normalized_contract["metric_basis_id"],
        "old_observation_sha256": prior_gate["metric_observation_sha256"],
        "new_observation_input_sha256": observation_input_sha256,
        "old_lineage_id": prior_gate["primary_metric_scope_key"],
        "new_lineage_id": new_lineage,
        "mapping_ref": "mapping_A",
        "mapping_sha256": mapping["mapping_contract_sha256"],
        "basis_mapping": mapping,
        "comparability_verdict": "new_baseline_required",
        "provenance_status": "independently_verified",
        "verifier_receipt_id": "verifier_receipt_A",
        "independent_verification_receipt": verification,
        "decision_binding_sha256": decision_binding_sha256(binding),
        "verification_gate_sha256": verification_gate_sha256(SOURCE_SEPARATION),
    }
    receipt["receipt_sha256"] = canonical_basis_migration_receipt_sha256(receipt)
    return receipt


def test_set_superset_moves_content_bound_high_water() -> None:
    baseline = observe(
        contract(
            value_kind="set",
            comparison_semantics="set_relation",
            set_relation_direction="superset_is_better",
            value=["item_A", "item_B"],
        )
    )
    moved = observe(
        contract(
            value_kind="set",
            comparison_semantics="set_relation",
            set_relation_direction="superset_is_better",
            value=["item_C", "item_B", "item_A"],
        ),
        [{"primary_metric_gate": baseline}],
    )

    assert moved["evaluation_status"] == "pass"
    assert moved["metric_comparison_relation"] == "improved"
    assert moved["primary_metric_high_water"] == ["item_A", "item_B", "item_C"]
    assert moved["primary_metric_high_water_moved"] is True
    assert len(moved["metric_observation_sha256"]) == 64
    assert len(moved["primary_metric_high_water_sha256"]) == 64

    subset_contract = contract(
        value_kind="set",
        comparison_semantics="set_relation",
        set_relation_direction="subset_is_better",
        value=["item_A", "item_B"],
    )
    subset_baseline = observe(subset_contract)
    subset_moved = observe(
        {**subset_contract, "value": ["item_A"]},
        [{"primary_metric_gate": subset_baseline}],
    )
    assert subset_moved["primary_metric_high_water_moved"] is True
    assert subset_moved["primary_metric_high_water"] == ["item_A"]


def test_incomparable_set_preserves_high_water_streak_and_stall() -> None:
    baseline = observe(
        contract(
            value_kind="set",
            comparison_semantics="set_relation",
            set_relation_direction="superset_is_better",
            value=["item_A", "item_B"],
        )
    )
    baseline["primary_metric_zero_movement_streak"] = 3
    baseline["primary_metric_stalled"] = True
    baseline = finalize_metric_observation(baseline)
    incomparable = observe(
        contract(
            value_kind="set",
            comparison_semantics="set_relation",
            set_relation_direction="superset_is_better",
            value=["item_B", "item_C"],
        ),
        [{"primary_metric_gate": baseline}],
    )

    assert incomparable["metric_comparability_status"] == "incomparable"
    assert incomparable["not_evaluated_reason"] == "metric_values_incomparable"
    assert incomparable["primary_metric_high_water"] == ["item_A", "item_B"]
    assert (
        incomparable["primary_metric_high_water_sha256"]
        == baseline["primary_metric_high_water_sha256"]
    )
    assert incomparable["primary_metric_zero_movement_streak"] == 3
    assert incomparable["primary_metric_stalled"] is True
    assert incomparable["primary_metric_high_water_moved"] is False


def test_pareto_dominance_moves_but_tradeoff_is_incomparable() -> None:
    base_metric = contract(
        value_kind="vector",
        comparison_semantics="pareto",
        vector_directions={"coverage": "higher_is_better", "errors": "lower_is_better"},
        value={"coverage": 0.5, "errors": 4},
    )
    baseline = observe(base_metric)
    moved = observe(
        {**base_metric, "value": {"coverage": 0.6, "errors": 4}},
        [{"primary_metric_gate": baseline}],
    )
    tradeoff = observe(
        {**base_metric, "value": {"coverage": 0.6, "errors": 5}},
        [{"primary_metric_gate": baseline}],
    )

    assert moved["primary_metric_high_water_moved"] is True
    assert moved["primary_metric_high_water"] == {"coverage": 0.6, "errors": 4.0}
    assert tradeoff["metric_comparability_status"] == "incomparable"
    assert (
        tradeoff["primary_metric_high_water"] == baseline["primary_metric_high_water"]
    )
    assert tradeoff["primary_metric_zero_movement_streak"] == 0


def test_ordered_predicate_and_equal_required_semantics() -> None:
    ordered = contract(
        value_kind="ordered",
        comparison_semantics="higher_is_better",
        ordered_values=["low", "medium", "high"],
        value="low",
    )
    ordered_baseline = observe(ordered)
    ordered_moved = observe(
        {**ordered, "value": "high"},
        [{"primary_metric_gate": ordered_baseline}],
    )
    predicate = contract(
        value_kind="predicate",
        comparison_semantics="predicate_only",
        value=False,
    )
    predicate_baseline = observe(predicate)
    predicate_moved = observe(
        {**predicate, "value": True},
        [{"primary_metric_gate": predicate_baseline}],
    )
    equality = contract(
        value_kind="scalar",
        comparison_semantics="equal_required",
        target_value="accepted",
        value="pending",
    )
    equality_baseline = observe(equality)
    equality_moved = observe(
        {**equality, "value": "accepted"},
        [{"primary_metric_gate": equality_baseline}],
    )

    assert ordered_moved["primary_metric_high_water_moved"] is True
    assert predicate_moved["primary_metric_high_water"] is True
    assert predicate_moved["primary_metric_high_water_moved"] is True
    assert equality_moved["primary_metric_high_water_moved"] is True


@pytest.mark.parametrize(
    ("field", "replacement", "expected_status"),
    (
        ("metric_basis_id", "basis_B", "basis_migration_no_comparable_baseline"),
        ("metric_dimension_id", "dimension_B", "no_comparable_baseline"),
        ("metric_subject_id", "subject_B", "no_comparable_baseline"),
        ("metric_provenance_id", "provenance_B", "no_comparable_baseline"),
    ),
)
def test_identity_mismatch_never_counts_progress(
    field: str,
    replacement: str,
    expected_status: str,
) -> None:
    base = contract(
        value_kind="set",
        comparison_semantics="set_relation",
        set_relation_direction="superset_is_better",
        value=["item_A"],
    )
    baseline = observe(base)
    baseline["primary_metric_zero_movement_streak"] = 2
    baseline = finalize_metric_observation(baseline)
    changed = observe(
        {**base, field: replacement, "value": ["item_A", "item_B"]},
        [{"primary_metric_gate": baseline}],
    )

    assert changed["metric_comparability_status"] == expected_status
    assert changed["primary_metric_high_water_moved"] is False
    if field == "metric_basis_id":
        assert changed["basis_migration_observed"] is True
        assert changed["primary_metric_zero_movement_streak"] == 2


def test_verified_basis_migration_starts_new_lineage_without_progress() -> None:
    basis_a = contract(
        value_kind="set",
        comparison_semantics="set_relation",
        set_relation_direction="superset_is_better",
        value=["item_A"],
    )
    baseline = observe(basis_a)
    baseline["primary_metric_zero_movement_streak"] = 2
    baseline["primary_metric_stalled"] = True
    baseline = finalize_metric_observation(baseline)
    basis_b = {**basis_a, "metric_basis_id": "basis_B", "value": ["item_A", "item_B"]}
    basis_b["basis_migration_receipt"] = basis_migration_receipt(baseline, basis_b)

    migrated = observe(basis_b, [{"primary_metric_gate": baseline}])

    assert migrated["basis_migration_observed"] is True
    assert migrated["basis_migration_status"] == "verified_new_baseline"
    assert migrated["metric_comparability_status"] == "basis_migration_new_baseline"
    assert migrated["primary_metric_high_water_moved"] is False
    assert migrated["primary_metric_zero_movement_streak"] == 2
    assert migrated["primary_metric_stalled"] is True
    assert (
        migrated["basis_migration_prior_lineage_id"]
        == baseline["primary_metric_scope_key"]
    )
    assert (
        migrated["basis_migration_new_lineage_id"]
        != baseline["primary_metric_scope_key"]
    )

    next_b = observe(
        {**basis_b, "value": ["item_A", "item_B", "item_C"]},
        [
            {"primary_metric_gate": baseline},
            {"primary_metric_gate": migrated},
        ],
    )
    assert next_b["metric_comparability_status"] == "comparable"
    assert next_b["primary_metric_high_water_moved"] is True
    assert next_b["primary_metric_high_water"] == ["item_A", "item_B", "item_C"]

    next_a = observe(
        {**basis_a, "value": ["item_A", "item_Z"]},
        [
            {"primary_metric_gate": baseline},
            {"primary_metric_gate": migrated},
        ],
    )
    assert next_a["metric_comparability_status"] == "comparable"
    assert next_a["primary_metric_high_water_moved"] is True


@pytest.mark.parametrize(
    "tamper",
    [
        "mapping_digest",
        "fabricated_mapping",
        "axis",
        "provenance",
        "coupled_verifier",
    ],
)
def test_invalid_basis_migration_receipt_cannot_seed_new_baseline(
    tamper: str,
) -> None:
    basis_a = contract(
        value_kind="set",
        comparison_semantics="set_relation",
        set_relation_direction="superset_is_better",
        value=["item_A"],
    )
    baseline = observe(basis_a)
    basis_b = {**basis_a, "metric_basis_id": "basis_B", "value": ["item_A", "item_B"]}
    receipt = basis_migration_receipt(baseline, basis_b)
    if tamper == "mapping_digest":
        receipt["mapping_sha256"] = "d" * 64
    elif tamper == "fabricated_mapping":
        mapping = receipt["basis_mapping"]
        mapping["mapping_evidence_sha256"] = "e" * 64
        mapping["mapping_contract_sha256"] = canonical_basis_mapping_sha256(mapping)
        receipt["mapping_sha256"] = mapping["mapping_contract_sha256"]
        receipt["receipt_sha256"] = canonical_basis_migration_receipt_sha256(receipt)
    elif tamper == "axis":
        receipt["metric_axis_id"] = "axis_other"
        receipt["receipt_sha256"] = canonical_basis_migration_receipt_sha256(receipt)
    elif tamper == "provenance":
        receipt["provenance_status"] = "producer_attested"
        receipt["receipt_sha256"] = canonical_basis_migration_receipt_sha256(receipt)
    else:
        verification = receipt["independent_verification_receipt"]
        verification["verification_input_ids"] = verification["producer_input_ids"]
        verification["receipt_sha256"] = canonical_migration_verification_sha256(
            verification
        )
        receipt["receipt_sha256"] = canonical_basis_migration_receipt_sha256(receipt)
    basis_b["basis_migration_receipt"] = receipt

    rejected = observe(basis_b, [{"primary_metric_gate": baseline}])
    follow_up = observe(
        {**basis_b, "value": ["item_A", "item_B", "item_C"]},
        [
            {"primary_metric_gate": baseline},
            {"primary_metric_gate": rejected},
        ],
    )

    assert rejected["basis_migration_status"] == "unverified"
    assert rejected["primary_metric_high_water_moved"] is False
    assert rejected["metric_comparability_status"] == (
        "basis_migration_no_comparable_baseline"
    )
    assert follow_up["metric_comparability_status"] == (
        "basis_migration_no_comparable_baseline"
    )
    assert follow_up["primary_metric_high_water_moved"] is False


def test_tampered_non_scalar_high_water_is_not_a_baseline() -> None:
    base = contract(
        value_kind="set",
        comparison_semantics="set_relation",
        set_relation_direction="superset_is_better",
        value=["item_A"],
    )
    baseline = observe(base)
    baseline["primary_metric_high_water"] = ["item_A", "tampered"]
    result = observe(
        {**base, "value": ["item_A", "item_B"]},
        [{"primary_metric_gate": baseline}],
    )

    assert result["metric_comparability_status"] == "no_comparable_baseline"
    assert result["primary_metric_high_water_moved"] is False


@pytest.mark.parametrize(
    "tamper",
    ["observation_digest", "observation_material", "high_water_digest"],
)
def test_tampered_observation_cannot_be_reloaded_as_baseline(tamper: str) -> None:
    base = contract(
        value_kind="set",
        comparison_semantics="set_relation",
        set_relation_direction="superset_is_better",
        value=["item_A"],
    )
    baseline = observe(base)
    if tamper == "observation_digest":
        baseline["metric_observation_sha256"] = "0" * 64
    elif tamper == "observation_material":
        baseline["metric_observation"]["decision_artifact_binding"]["artifact_id"] = (
            "artifact-tampered"
        )
    else:
        baseline["primary_metric_high_water_sha256"] = "0" * 64

    result = observe(
        {**base, "value": ["item_A", "item_B"]},
        [{"primary_metric_gate": baseline}],
    )

    assert result["metric_comparability_status"] == "no_comparable_baseline"
    assert result["primary_metric_high_water_moved"] is False


def test_legacy_observation_binding_rejects_extra_raw_metadata_after_rehash() -> None:
    base = contract(
        value_kind="set",
        comparison_semantics="set_relation",
        set_relation_direction="superset_is_better",
        value=["item_A"],
    )
    baseline = observe(base)
    observation = baseline["metric_observation"]
    observation["decision_artifact_binding"]["raw_source_path"] = "source/raw.txt"
    baseline["metric_observation_sha256"] = metric_observation_sha256(observation)

    result = observe(
        {**base, "value": ["item_A", "item_B"]},
        [{"primary_metric_gate": baseline}],
    )

    assert result["metric_comparability_status"] == "no_comparable_baseline"
    assert result["primary_metric_high_water_moved"] is False


def test_self_asserted_exact_scalar_without_observation_is_trace_only() -> None:
    scalar = contract(
        value_kind="scalar",
        comparison_semantics="higher_is_better",
        value=2,
    )
    current = observe(scalar)
    self_asserted = {
        key: current[key]
        for key in (
            "metric_id",
            "metric_basis_id",
            "metric_dimension_id",
            "metric_subject_id",
            "metric_provenance_id",
            "value_kind",
            "comparison_semantics",
            "comparison_config",
            "primary_metric_scope_key",
            "primary_metric_high_water",
            "primary_metric_high_water_sha256",
        )
    }
    self_asserted.update(
        artifact_binding_status="exact",
        evidence_provenance="independently_verified",
        independent_source_separation_status="pass",
        decision_contribution_allowed=True,
    )

    result = observe(
        {**scalar, "value": 3},
        [{"primary_metric_gate": self_asserted}],
    )

    assert result["metric_comparability_status"] == "no_comparable_baseline"
    assert result["primary_metric_high_water_moved"] is False


def test_vector_axes_must_exactly_match_the_direction_contract() -> None:
    result = observe(
        contract(
            value_kind="vector",
            comparison_semantics="pareto",
            vector_directions={"axis_A": "higher_is_better"},
            value={"axis_A": 1, "axis_B": 2},
        )
    )

    assert result["evaluation_status"] == "not_evaluated"
    assert result["not_evaluated_reason"] == "vector_axis_contract_mismatch"


@pytest.mark.parametrize(
    ("metric", "reason"),
    (
        (
            {
                "value_kind": "set",
                "comparison_semantics": "set_relation",
                "set_relation_direction": "superset_is_better",
                "value": ["item_A"],
            },
            "metric_subject_id_missing",
        ),
        (
            {
                "metric_subject_id": "subject_A",
                "value_kind": "vector",
                "comparison_semantics": "pareto",
                "vector_directions": {"axis_A": "higher_is_better"},
                "value": {"axis_A": 1, "axis_B": 2},
            },
            "metric_provenance_id_missing",
        ),
    ),
)
def test_non_scalar_contract_fails_closed(metric: dict[str, Any], reason: str) -> None:
    result = observe(
        {
            "goal_axis_id": "axis_G",
            "metric_basis_id": "basis_A",
            "metric_dimension_id": "dimension_A",
            **metric,
        }
    )

    assert result["evaluation_status"] == "not_evaluated"
    assert result["not_evaluated_reason"] == reason
