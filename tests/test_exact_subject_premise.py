from __future__ import annotations

import copy
import json

import pytest

from orchestrate_task_cycle.exact_subject_premise import (
    validate_exact_subject_premise,
    validate_exact_subject_premise_receipt,
)


def _subject(revision: str, digest: str) -> dict[str, object]:
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


def _terminal_binding() -> dict[str, object]:
    return {"binding_kind": "terminal_task", "terminal_task_sha256": "1" * 64}


def _context() -> dict[str, object]:
    return {
        "schema_version": 1,
        "artifact_kind": "exact_subject_premise_context",
        "current_binding": _terminal_binding(),
        "freshness_baseline": {
            "baseline_id": "baseline-A",
            "subject": _subject("revision-1", "2" * 64),
        },
        "canonical_owner": _owner(),
        "first_failing_invariant_id": "invariant-A",
    }


def _producer_evidence(digest: str) -> dict[str, object]:
    return {
        "mode": "producer_verifier_replay",
        "producer_receipt_id": "producer-A",
        "producer_receipt_sha256": "4" * 64,
        "producer_subject_sha256": digest,
        "verifier_receipt_id": "verifier-A",
        "verifier_receipt_sha256": "5" * 64,
        "verified_subject_sha256": digest,
        "replay_receipt_id": "replay-A",
        "replay_receipt_sha256": "6" * 64,
        "replayed_subject_sha256": digest,
    }


def _submission() -> dict[str, object]:
    digest = "3" * 64
    return {
        "schema_version": 1,
        "artifact_kind": "exact_subject_premise_submission",
        "premise_id": "premise-A",
        "binding": _terminal_binding(),
        "freshness_baseline_id": "baseline-A",
        "subject": _subject("revision-2", digest),
        "canonical_owner": _owner(),
        "first_failing_invariant": {
            "invariant_id": "invariant-A",
            "status": "failing",
            "evidence_id": "failure-A",
            "evidence_sha256": "7" * 64,
        },
        "evidence": _producer_evidence(digest),
    }


def test_consumes_fresh_terminal_bound_producer_verifier_premise() -> None:
    result = validate_exact_subject_premise(_submission(), context=_context())
    receipt = result["receipt"]

    assert receipt["status"] == "consumed"
    assert receipt["accepted_premise"]["subject"]["revision_id"] == "revision-2"
    assert receipt["accepted_premise"]["freshness"]["status"] == "fresh"
    assert receipt["accepted_premise"]["canonical_owner"] == _owner()
    assert result["replay"]["disposition"] == "new_consumed"
    assert validate_exact_subject_premise_receipt(receipt) == receipt


def test_accepts_selection_baseline_and_source_separated_current_body() -> None:
    context = _context()
    binding = {
        "binding_kind": "selection_baseline",
        "selection_baseline_id": "selection-tick-A",
        "selection_baseline_sha256": "8" * 64,
    }
    context["current_binding"] = binding
    submission = _submission()
    submission["binding"] = binding
    submission["evidence"] = {
        "mode": "source_separated_current_body",
        "source_channel_id": "source-channel-A",
        "source_receipt_id": "source-receipt-A",
        "source_revision_id": "source-revision-A",
        "source_content_sha256": "9" * 64,
        "current_body_channel_id": "current-channel-A",
        "current_body_receipt_id": "current-receipt-A",
        "current_body_revision_id": "revision-2",
        "current_body_content_sha256": "3" * 64,
        "comparison_receipt_id": "comparison-A",
        "comparison_receipt_sha256": "a" * 64,
    }

    receipt = validate_exact_subject_premise(submission, context=context)["receipt"]

    assert receipt["status"] == "consumed"
    assert receipt["current_binding"] == binding
    assert receipt["accepted_premise"]["evidence"]["mode"] == (
        "source_separated_current_body"
    )


def test_preserves_source_and_current_receipt_digests_for_verified_upgrade() -> None:
    submission = _submission()
    submission["evidence"] = {
        "mode": "source_separated_current_body",
        "source_channel_id": "source-channel-A",
        "source_receipt_id": "source-receipt-A",
        "source_receipt_sha256": "8" * 64,
        "source_revision_id": "source-revision-A",
        "source_content_sha256": "9" * 64,
        "current_body_channel_id": "current-channel-A",
        "current_body_receipt_id": "current-receipt-A",
        "current_body_receipt_sha256": "b" * 64,
        "current_body_revision_id": "revision-2",
        "current_body_content_sha256": "3" * 64,
        "comparison_receipt_id": "comparison-A",
        "comparison_receipt_sha256": "a" * 64,
    }

    receipt = validate_exact_subject_premise(submission, context=_context())["receipt"]

    assert receipt["status"] == "consumed"
    assert receipt["accepted_premise"]["evidence"]["source_receipt_sha256"] == (
        "8" * 64
    )
    assert receipt["accepted_premise"]["evidence"]["current_body_receipt_sha256"] == (
        "b" * 64
    )
    assert validate_exact_subject_premise_receipt(receipt) == receipt


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        (
            lambda row: row["binding"].update(terminal_task_sha256="b" * 64),
            "current_binding_mismatch",
        ),
        (
            lambda row: row.update(freshness_baseline_id="baseline-B"),
            "freshness_baseline_mismatch",
        ),
        (
            lambda row: row["subject"].update(content_sha256="2" * 64),
            "premise_not_fresh",
        ),
        (
            lambda row: row["subject"].update(revision_id="revision-1"),
            "premise_revision_not_advanced",
        ),
        (
            lambda row: row["canonical_owner"].update(owner_id="owner-B"),
            "canonical_writable_owner_mismatch",
        ),
        (
            lambda row: row["first_failing_invariant"].update(
                invariant_id="invariant-B"
            ),
            "first_failing_invariant_mismatch",
        ),
        (
            lambda row: row["evidence"].update(replayed_subject_sha256="c" * 64),
            "premise_evidence_invalid",
        ),
    ],
)
def test_rejects_first_failed_contract_rule(mutation, reason: str) -> None:
    submission = _submission()
    mutation(submission)

    receipt = validate_exact_subject_premise(submission, context=_context())["receipt"]

    assert receipt["status"] == "rejected"
    assert receipt["reason_code"] == reason
    assert receipt["accepted_premise"] is None


def test_rejects_extra_body_or_path_fields_without_persisting_them() -> None:
    submission = _submission()
    submission["source_body"] = "sensitive-source-body"
    submission["source_path"] = "/sensitive/source/path"

    result = validate_exact_subject_premise(submission, context=_context())
    serialized = json.dumps(result, ensure_ascii=False)

    assert result["receipt"]["reason_code"] == "submission_schema_invalid"
    assert "sensitive-source-body" not in serialized
    assert "/sensitive/source/path" not in serialized
    assert result["receipt"]["source_body_persisted"] is False
    assert result["receipt"]["source_path_persisted"] is False


def test_consumed_and_rejected_exact_replays_reuse_the_immutable_receipt() -> None:
    consumed = validate_exact_subject_premise(_submission(), context=_context())
    consumed_replay = validate_exact_subject_premise(
        _submission(), context=_context(), prior_receipts=[consumed["receipt"]]
    )
    assert consumed_replay["receipt"] == consumed["receipt"]
    assert consumed_replay["replay"]["disposition"] == "exact_consumed_replay"

    rejected_submission = _submission()
    rejected_submission["subject"]["content_sha256"] = "2" * 64
    rejected = validate_exact_subject_premise(rejected_submission, context=_context())
    rejected_replay = validate_exact_subject_premise(
        rejected_submission,
        context=_context(),
        prior_receipts=[rejected["receipt"]],
    )
    assert rejected_replay["receipt"] == rejected["receipt"]
    assert rejected_replay["replay"]["disposition"] == "exact_rejected_replay"
    assert (
        consumed["receipt"]["replay_identity_sha256"]
        != rejected["receipt"]["replay_identity_sha256"]
    )


def test_rejects_tampered_or_ambiguous_prior_replay_receipts() -> None:
    first = validate_exact_subject_premise(_submission(), context=_context())
    tampered = copy.deepcopy(first["receipt"])
    tampered["accepted_premise"]["premise_id"] = "premise-tampered"

    with pytest.raises(ValueError, match="integrity"):
        validate_exact_subject_premise(
            _submission(), context=_context(), prior_receipts=[tampered]
        )
    with pytest.raises(ValueError, match="ambiguous"):
        validate_exact_subject_premise(
            _submission(),
            context=_context(),
            prior_receipts=[first["receipt"], first["receipt"]],
        )

    unsafe = copy.deepcopy(first["receipt"])
    unsafe["accepted_premise"]["source_body"] = "must-not-persist"
    with pytest.raises(ValueError, match="incomplete"):
        validate_exact_subject_premise_receipt(unsafe)

    stale = copy.deepcopy(first["receipt"])
    stale["accepted_premise"]["freshness"]["baseline_subject"] = stale[
        "accepted_premise"
    ]["subject"]
    with pytest.raises(ValueError, match="incomplete"):
        validate_exact_subject_premise_receipt(stale)


def test_rejects_malformed_context_instead_of_treating_it_as_premise_evidence() -> None:
    context = _context()
    context["canonical_owner"] = [_owner(), _owner()]

    with pytest.raises(ValueError, match="context values"):
        validate_exact_subject_premise(_submission(), context=context)
