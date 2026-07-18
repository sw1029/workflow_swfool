from __future__ import annotations

import copy
import json

import pytest

from orchestrate_task_cycle.exact_subject_premise import (
    MAX_CANONICAL_BYTES as LEGACY_MAX_CANONICAL_BYTES,
    validate_exact_subject_premise,
)
from orchestrate_task_cycle.exact_subject_premise_v2 import (
    ARTIFACT_VALIDATOR_POLICY_ID,
    ARTIFACT_VALIDATOR_POLICY_VERSION,
    MAX_CANONICAL_BYTES as VERIFIED_MAX_CANONICAL_BYTES,
    seal_artifact_verified_receipt,
    validate_artifact_verified_exact_subject_premise_receipt,
)


def test_verified_budget_covers_legacy_receipt_plus_attestation() -> None:
    assert VERIFIED_MAX_CANONICAL_BYTES >= 2 * LEGACY_MAX_CANONICAL_BYTES


def _subject(revision: str, digest: str) -> dict[str, str]:
    return {
        "subject_id": "subject-A",
        "revision_id": revision,
        "content_sha256": digest,
    }


def _owner() -> dict[str, object]:
    return {
        "owner_id": "owner-A",
        "writable_surface_id": "surface-A",
        "authority_scope_id": "authority-A",
        "writable": True,
    }


def _binding(kind: str) -> dict[str, str]:
    if kind == "terminal_task":
        return {"binding_kind": kind, "terminal_task_sha256": "1" * 64}
    return {
        "binding_kind": kind,
        "selection_baseline_id": "selection-tick-A",
        "selection_baseline_sha256": "8" * 64,
    }


def _legacy_receipt(
    mode: str = "producer_verifier_replay",
    *,
    artifact_receipt_hashes: bool = True,
    subject_digest: str = "3" * 64,
) -> dict[str, object]:
    kind = (
        "terminal_task" if mode == "producer_verifier_replay" else "selection_baseline"
    )
    binding = _binding(kind)
    context = {
        "schema_version": 1,
        "artifact_kind": "exact_subject_premise_context",
        "current_binding": binding,
        "freshness_baseline": {
            "baseline_id": "baseline-A",
            "subject": _subject("revision-1", "2" * 64),
        },
        "canonical_owner": _owner(),
        "first_failing_invariant_id": "invariant-A",
    }
    evidence: dict[str, object]
    if mode == "producer_verifier_replay":
        evidence = {
            "mode": mode,
            "producer_receipt_id": "producer-A",
            "producer_receipt_sha256": "4" * 64,
            "producer_subject_sha256": subject_digest,
            "verifier_receipt_id": "verifier-A",
            "verifier_receipt_sha256": "5" * 64,
            "verified_subject_sha256": subject_digest,
            "replay_receipt_id": "replay-A",
            "replay_receipt_sha256": "6" * 64,
            "replayed_subject_sha256": subject_digest,
        }
    else:
        evidence = {
            "mode": mode,
            "source_channel_id": "source-channel-A",
            "source_receipt_id": "source-receipt-A",
            "source_revision_id": "source-revision-A",
            "source_content_sha256": "9" * 64,
            "current_body_channel_id": "current-channel-A",
            "current_body_receipt_id": "current-receipt-A",
            "current_body_revision_id": "revision-2",
            "current_body_content_sha256": subject_digest,
            "comparison_receipt_id": "comparison-A",
            "comparison_receipt_sha256": "6" * 64,
        }
        if artifact_receipt_hashes:
            evidence["source_receipt_sha256"] = "4" * 64
            evidence["current_body_receipt_sha256"] = "5" * 64
    submission = {
        "schema_version": 1,
        "artifact_kind": "exact_subject_premise_submission",
        "premise_id": "premise-A",
        "binding": binding,
        "freshness_baseline_id": "baseline-A",
        "subject": _subject("revision-2", subject_digest),
        "canonical_owner": _owner(),
        "first_failing_invariant": {
            "invariant_id": "invariant-A",
            "status": "failing",
            "evidence_id": "failure-A",
            "evidence_sha256": "7" * 64,
        },
        "evidence": evidence,
    }
    return validate_exact_subject_premise(submission, context=context)["receipt"]


def _verification(mode: str = "producer_verifier_replay") -> dict[str, object]:
    terminal = mode == "producer_verifier_replay"
    binding = {
        "artifact_kind": "terminal_task" if terminal else "selection_baseline",
        "artifact_id": "terminal-task" if terminal else "selection-tick-A",
        "digest_mode": "raw_sha256" if terminal else "canonical_json_sha256",
        "binding_sha256": "1" * 64 if terminal else "8" * 64,
        "raw_sha256": "1" * 64 if terminal else "b" * 64,
    }
    if terminal:
        evidence_receipts = [
            {"role": "producer", "receipt_id": "producer-A", "raw_sha256": "4" * 64},
            {"role": "verifier", "receipt_id": "verifier-A", "raw_sha256": "5" * 64},
            {"role": "replay", "receipt_id": "replay-A", "raw_sha256": "6" * 64},
        ]
        source_subject = None
    else:
        evidence_receipts = [
            {
                "role": "source",
                "receipt_id": "source-receipt-A",
                "raw_sha256": "4" * 64,
            },
            {
                "role": "current_body",
                "receipt_id": "current-receipt-A",
                "raw_sha256": "5" * 64,
            },
            {
                "role": "comparison",
                "receipt_id": "comparison-A",
                "raw_sha256": "6" * 64,
            },
        ]
        source_subject = {
            "source_identity": "source-channel-A",
            "revision_id": "source-revision-A",
            "raw_sha256": "9" * 64,
        }
    return {
        "schema_version": 1,
        "artifact_kind": "exact_subject_premise_artifact_verification",
        "validator_policy": {
            "policy_id": ARTIFACT_VALIDATOR_POLICY_ID,
            "policy_version": ARTIFACT_VALIDATOR_POLICY_VERSION,
        },
        "workspace_file_validation": {
            "status": "verified",
            "workspace_local": True,
            "regular_non_symlink": True,
        },
        "current_binding_artifact": binding,
        "current_subject": {
            "subject_id": "subject-A",
            "revision_id": "revision-2",
            "raw_sha256": "3" * 64,
        },
        "freshness_baseline_subject": {
            "subject_id": "subject-A",
            "revision_id": "revision-1",
            "raw_sha256": "2" * 64,
        },
        "source_subject": source_subject,
        "invariant_evidence": {
            "evidence_id": "failure-A",
            "raw_sha256": "7" * 64,
        },
        "evidence_receipts": evidence_receipts,
        "source_body_persisted": False,
        "source_path_persisted": False,
    }


def test_seals_and_validates_path_free_producer_receipt() -> None:
    legacy = _legacy_receipt()
    verification = _verification()

    sealed = seal_artifact_verified_receipt(legacy, verification)

    assert sealed["schema_version"] == 2
    assert sealed["status"] == "consumed"
    assert sealed["legacy_receipt"]["receipt_id"] == legacy["receipt_id"]
    assert sealed == seal_artifact_verified_receipt(legacy, verification)
    assert validate_artifact_verified_exact_subject_premise_receipt(sealed) == sealed
    assert sealed["source_body_persisted"] is False
    assert sealed["source_path_persisted"] is False
    assert "/private/source.txt" not in json.dumps(sealed)

    legacy["accepted_premise"]["premise_id"] = "mutated-after-seal"
    assert sealed["legacy_receipt"]["accepted_premise"]["premise_id"] == "premise-A"


def test_seals_source_separated_receipt_with_distinct_binding_digests() -> None:
    legacy = _legacy_receipt("source_separated_current_body")
    verification = _verification("source_separated_current_body")

    sealed = seal_artifact_verified_receipt(legacy, verification)
    validated = validate_artifact_verified_exact_subject_premise_receipt(sealed)

    binding = validated["artifact_verification"]["current_binding_artifact"]
    assert binding["digest_mode"] == "canonical_json_sha256"
    assert binding["binding_sha256"] == "8" * 64
    assert binding["raw_sha256"] == "b" * 64
    assert validated["artifact_verification"]["source_subject"] == {
        "source_identity": "source-channel-A",
        "revision_id": "source-revision-A",
        "raw_sha256": "9" * 64,
    }
    assert [
        row["role"] for row in validated["artifact_verification"]["evidence_receipts"]
    ] == ["source", "current_body", "comparison"]


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (
            lambda row: row["validator_policy"].update(policy_version="2"),
            "policy binding",
        ),
        (
            lambda row: row["workspace_file_validation"].update(workspace_local=False),
            "regular-file validation",
        ),
        (
            lambda row: row["current_binding_artifact"].update(
                artifact_id="another-task"
            ),
            "binding artifact differs",
        ),
        (
            lambda row: row["current_subject"].update(raw_sha256="a" * 64),
            "current subject artifact differs",
        ),
        (
            lambda row: row["freshness_baseline_subject"].update(
                revision_id="revision-0"
            ),
            "freshness baseline artifact differs",
        ),
        (
            lambda row: row["invariant_evidence"].update(evidence_id="failure-B"),
            "invariant artifact differs",
        ),
        (
            lambda row: row["evidence_receipts"][0].update(role="verifier"),
            "evidence receipt artifacts differ",
        ),
    ],
)
def test_rejects_attestation_that_does_not_match_v1(mutation, message: str) -> None:
    verification = _verification()
    mutation(verification)

    with pytest.raises(ValueError, match=message):
        seal_artifact_verified_receipt(_legacy_receipt(), verification)


def test_rejects_source_separation_without_artifact_receipt_hashes() -> None:
    legacy = _legacy_receipt(
        "source_separated_current_body", artifact_receipt_hashes=False
    )
    assert legacy["status"] == "consumed"

    with pytest.raises(ValueError, match="requires source/current receipt"):
        seal_artifact_verified_receipt(
            legacy, _verification("source_separated_current_body")
        )


def test_rejects_paths_extra_fields_rejected_v1_and_v2_tampering() -> None:
    verification = _verification()
    verification["source_path"] = "/private/source.txt"
    with pytest.raises(ValueError, match="exact fields"):
        seal_artifact_verified_receipt(_legacy_receipt(), verification)

    rejected = _legacy_receipt(subject_digest="2" * 64)
    assert rejected["status"] == "rejected"
    with pytest.raises(ValueError, match="requires a consumed"):
        seal_artifact_verified_receipt(rejected, _verification())

    sealed = seal_artifact_verified_receipt(_legacy_receipt(), _verification())
    tampered = copy.deepcopy(sealed)
    tampered["artifact_verification_sha256"] = "f" * 64
    with pytest.raises(ValueError, match="verification digest"):
        validate_artifact_verified_exact_subject_premise_receipt(tampered)

    extra = copy.deepcopy(sealed)
    extra["source_body"] = "sensitive"
    with pytest.raises(ValueError, match="exact fields"):
        validate_artifact_verified_exact_subject_premise_receipt(extra)
