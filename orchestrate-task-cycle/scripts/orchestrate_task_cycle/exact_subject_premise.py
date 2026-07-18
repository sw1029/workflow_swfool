"""Validate bounded exact-subject premises without retaining source bodies or paths."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from typing import Any


CONTRACT_VERSION = 1
MAX_CANONICAL_BYTES = 64 * 1024
MAX_PRIOR_RECEIPTS = 64
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
OPAQUE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")

_CONTEXT_KEYS = set(
    "schema_version artifact_kind current_binding freshness_baseline canonical_owner "
    "first_failing_invariant_id".split()
)
_SUBMISSION_KEYS = set(
    "schema_version artifact_kind premise_id binding freshness_baseline_id subject "
    "canonical_owner first_failing_invariant evidence".split()
)
_SUBJECT_KEYS = {"subject_id", "revision_id", "content_sha256"}
_OWNER_KEYS = set("owner_id writable_surface_id authority_scope_id writable".split())
_INVARIANT_KEYS = set("invariant_id status evidence_id evidence_sha256".split())
_PRODUCER_VERIFIER_KEYS = set(
    "mode producer_receipt_id producer_receipt_sha256 producer_subject_sha256 "
    "verifier_receipt_id verifier_receipt_sha256 verified_subject_sha256 "
    "replay_receipt_id replay_receipt_sha256 replayed_subject_sha256".split()
)
_SOURCE_SEPARATED_LEGACY_KEYS = set(
    "mode source_channel_id source_receipt_id source_revision_id "
    "source_content_sha256 current_body_channel_id current_body_receipt_id "
    "current_body_revision_id current_body_content_sha256 comparison_receipt_id "
    "comparison_receipt_sha256".split()
)
_SOURCE_SEPARATED_VERIFIED_KEYS = _SOURCE_SEPARATED_LEGACY_KEYS | set(
    "source_receipt_sha256 current_body_receipt_sha256".split()
)
_RECEIPT_KEYS = set(
    "schema_version artifact_kind status reason_code context_sha256 submission_sha256 "
    "replay_identity_sha256 outcome_identity current_binding accepted_premise "
    "source_body_persisted source_path_persisted receipt_id receipt_sha256".split()
)
_REJECTION_REASONS = set(
    "submission_schema_invalid current_binding_mismatch freshness_baseline_mismatch "
    "premise_not_fresh premise_revision_not_advanced canonical_writable_owner_mismatch "
    "first_failing_invariant_mismatch premise_evidence_invalid".split()
)


def _canonical_bytes(value: object) -> bytes:
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError("premise contract values must be canonical JSON") from exc
    if len(encoded) > MAX_CANONICAL_BYTES:
        raise ValueError(
            f"premise contract exceeds {MAX_CANONICAL_BYTES} canonical bytes"
        )
    return encoded


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _mapping(value: object, keys: set[str]) -> dict[str, Any] | None:
    if not isinstance(value, Mapping) or set(value) != keys:
        return None
    return {str(key): child for key, child in value.items()}


def _opaque(value: object) -> bool:
    return isinstance(value, str) and OPAQUE_ID_RE.fullmatch(value) is not None


def _digest(value: object) -> bool:
    return isinstance(value, str) and SHA256_RE.fullmatch(value) is not None


def _subject(value: object) -> dict[str, Any] | None:
    row = _mapping(value, _SUBJECT_KEYS)
    if row is None:
        return None
    if not _opaque(row["subject_id"]) or not _opaque(row["revision_id"]):
        return None
    if not _digest(row["content_sha256"]):
        return None
    return row


def _binding(value: object) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    kind = value.get("binding_kind")
    if kind == "terminal_task":
        row = _mapping(value, {"binding_kind", "terminal_task_sha256"})
        return row if row is not None and _digest(row["terminal_task_sha256"]) else None
    if kind == "selection_baseline":
        row = _mapping(
            value,
            {
                "binding_kind",
                "selection_baseline_id",
                "selection_baseline_sha256",
            },
        )
        if (
            row is not None
            and _opaque(row["selection_baseline_id"])
            and _digest(row["selection_baseline_sha256"])
        ):
            return row
    return None


def _owner(value: object) -> dict[str, Any] | None:
    row = _mapping(value, _OWNER_KEYS)
    if row is None or row["writable"] is not True:
        return None
    if not all(
        _opaque(row[field])
        for field in ("owner_id", "writable_surface_id", "authority_scope_id")
    ):
        return None
    return row


def _invariant(value: object) -> dict[str, Any] | None:
    row = _mapping(value, _INVARIANT_KEYS)
    if row is None or row["status"] != "failing":
        return None
    if not _opaque(row["invariant_id"]) or not _opaque(row["evidence_id"]):
        return None
    return row if _digest(row["evidence_sha256"]) else None


def _evidence(value: object, subject: Mapping[str, Any]) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    mode = value.get("mode")
    if mode == "producer_verifier_replay":
        row = _mapping(value, _PRODUCER_VERIFIER_KEYS)
        if row is None:
            return None
        ids = [
            row["producer_receipt_id"],
            row["verifier_receipt_id"],
            row["replay_receipt_id"],
        ]
        receipt_digests = [
            row["producer_receipt_sha256"],
            row["verifier_receipt_sha256"],
            row["replay_receipt_sha256"],
        ]
        subject_digests = [
            row["producer_subject_sha256"],
            row["verified_subject_sha256"],
            row["replayed_subject_sha256"],
        ]
        if (
            all(_opaque(item) for item in ids)
            and len(set(ids)) == len(ids)
            and all(_digest(item) for item in receipt_digests)
            and all(item == subject["content_sha256"] for item in subject_digests)
        ):
            return row
        return None
    if mode == "source_separated_current_body":
        row = _mapping(value, _SOURCE_SEPARATED_VERIFIED_KEYS)
        verified_receipt_digests = row is not None
        if row is None:
            row = _mapping(value, _SOURCE_SEPARATED_LEGACY_KEYS)
        if row is None:
            return None
        ids = [
            row["source_receipt_id"],
            row["current_body_receipt_id"],
            row["comparison_receipt_id"],
        ]
        if not (
            all(
                _opaque(row[field])
                for field in (
                    "source_channel_id",
                    "source_revision_id",
                    "current_body_channel_id",
                    "current_body_revision_id",
                )
            )
            and row["source_channel_id"] != row["current_body_channel_id"]
            and all(_opaque(item) for item in ids)
            and len(set(ids)) == len(ids)
            and all(
                _digest(row[field])
                for field in (
                    "source_content_sha256",
                    "current_body_content_sha256",
                    "comparison_receipt_sha256",
                )
            )
            and row["current_body_revision_id"] == subject["revision_id"]
            and row["current_body_content_sha256"] == subject["content_sha256"]
            and (
                not verified_receipt_digests
                or (
                    _digest(row["source_receipt_sha256"])
                    and _digest(row["current_body_receipt_sha256"])
                )
            )
        ):
            return None
        return row
    return None


def _context(value: object) -> dict[str, Any]:
    row = _mapping(value, _CONTEXT_KEYS)
    if (
        row is None
        or row["schema_version"] != CONTRACT_VERSION
        or row["artifact_kind"] != "exact_subject_premise_context"
    ):
        raise ValueError("exact-subject premise context schema is invalid")
    binding = _binding(row["current_binding"])
    owner = _owner(row["canonical_owner"])
    baseline = _mapping(row["freshness_baseline"], {"baseline_id", "subject"})
    if binding is None or owner is None or baseline is None:
        raise ValueError("exact-subject premise context values are invalid")
    if not _opaque(baseline["baseline_id"]):
        raise ValueError("freshness baseline ID must be a bounded opaque ID")
    baseline_subject = baseline["subject"]
    if baseline_subject is not None and _subject(baseline_subject) is None:
        raise ValueError("freshness baseline subject is invalid")
    if not _opaque(row["first_failing_invariant_id"]):
        raise ValueError("first-failing invariant ID must be a bounded opaque ID")
    row["current_binding"] = binding
    row["canonical_owner"] = owner
    row["freshness_baseline"] = {
        "baseline_id": baseline["baseline_id"],
        "subject": _subject(baseline_subject) if baseline_subject is not None else None,
    }
    return row


def _accepted_premise(
    submission: object, context: Mapping[str, Any]
) -> tuple[dict[str, Any] | None, str | None]:
    row = _mapping(submission, _SUBMISSION_KEYS)
    if (
        row is None
        or row["schema_version"] != CONTRACT_VERSION
        or row["artifact_kind"] != "exact_subject_premise_submission"
        or not _opaque(row["premise_id"])
    ):
        return None, "submission_schema_invalid"
    binding = _binding(row["binding"])
    subject = _subject(row["subject"])
    owner = _owner(row["canonical_owner"])
    invariant = _invariant(row["first_failing_invariant"])
    if binding is None or subject is None or owner is None or invariant is None:
        return None, "submission_schema_invalid"
    if binding != context["current_binding"]:
        return None, "current_binding_mismatch"
    baseline = context["freshness_baseline"]
    if row["freshness_baseline_id"] != baseline["baseline_id"]:
        return None, "freshness_baseline_mismatch"
    previous = baseline["subject"]
    if previous is not None:
        if subject["content_sha256"] == previous["content_sha256"]:
            return None, "premise_not_fresh"
        if (
            subject["subject_id"] == previous["subject_id"]
            and subject["revision_id"] == previous["revision_id"]
        ):
            return None, "premise_revision_not_advanced"
    if owner != context["canonical_owner"]:
        return None, "canonical_writable_owner_mismatch"
    if invariant["invariant_id"] != context["first_failing_invariant_id"]:
        return None, "first_failing_invariant_mismatch"
    evidence = _evidence(row["evidence"], subject)
    if evidence is None:
        return None, "premise_evidence_invalid"
    return (
        {
            "premise_id": row["premise_id"],
            "binding": binding,
            "subject": subject,
            "freshness": {
                "baseline_id": baseline["baseline_id"],
                "baseline_subject": previous,
                "status": "fresh",
            },
            "canonical_owner": owner,
            "first_failing_invariant": invariant,
            "evidence": evidence,
        },
        None,
    )


def _receipt(
    *,
    context: Mapping[str, Any],
    submission_sha256: str,
    replay_identity_sha256: str,
    accepted_premise: dict[str, Any] | None,
    reason_code: str | None,
) -> dict[str, Any]:
    status = "consumed" if accepted_premise is not None else "rejected"
    body: dict[str, Any] = {
        "schema_version": CONTRACT_VERSION,
        "artifact_kind": "exact_subject_premise_validation_receipt",
        "status": status,
        "reason_code": reason_code,
        "context_sha256": _sha256(context),
        "submission_sha256": submission_sha256,
        "replay_identity_sha256": replay_identity_sha256,
        "outcome_identity": f"{status}:{replay_identity_sha256}",
        "current_binding": context["current_binding"],
        "accepted_premise": accepted_premise,
        "source_body_persisted": False,
        "source_path_persisted": False,
    }
    body["receipt_id"] = "exact-premise-" + _sha256(body)[:32]
    body["receipt_sha256"] = _sha256(body)
    return body


def validate_exact_subject_premise_receipt(value: object) -> dict[str, Any]:
    """Validate and return one immutable premise validation receipt."""
    row = _mapping(value, _RECEIPT_KEYS)
    if row is None or row["schema_version"] != CONTRACT_VERSION:
        raise ValueError("exact-subject premise receipt schema is invalid")
    if row["artifact_kind"] != "exact_subject_premise_validation_receipt":
        raise ValueError("exact-subject premise receipt kind is invalid")
    status = row["status"]
    if status not in {"consumed", "rejected"}:
        raise ValueError("exact-subject premise receipt status is invalid")
    if not all(
        _digest(row[field])
        for field in (
            "context_sha256",
            "submission_sha256",
            "replay_identity_sha256",
            "receipt_sha256",
        )
    ):
        raise ValueError("exact-subject premise receipt digest is invalid")
    if _binding(row["current_binding"]) is None:
        raise ValueError("exact-subject premise receipt binding is invalid")
    if (
        row["source_body_persisted"] is not False
        or row["source_path_persisted"] is not False
    ):
        raise ValueError("exact-subject premise receipt retained source material")
    expected_outcome = f"{status}:{row['replay_identity_sha256']}"
    if row["outcome_identity"] != expected_outcome:
        raise ValueError("exact-subject premise outcome identity is invalid")
    accepted = row["accepted_premise"]
    reason = row["reason_code"]
    if status == "consumed":
        accepted_row = _mapping(
            accepted,
            {
                "premise_id",
                "binding",
                "subject",
                "freshness",
                "canonical_owner",
                "first_failing_invariant",
                "evidence",
            },
        )
        freshness = (
            _mapping(
                accepted_row["freshness"], {"baseline_id", "baseline_subject", "status"}
            )
            if accepted_row is not None
            else None
        )
        accepted_subject = _subject(accepted_row["subject"]) if accepted_row else None
        baseline_subject = (
            _subject(freshness["baseline_subject"])
            if freshness is not None and freshness["baseline_subject"] is not None
            else None
        )
        accepted_valid = (
            accepted_row is not None
            and reason is None
            and _opaque(accepted_row["premise_id"])
            and _binding(accepted_row["binding"]) == row["current_binding"]
            and accepted_subject is not None
            and _owner(accepted_row["canonical_owner"]) is not None
            and _invariant(accepted_row["first_failing_invariant"]) is not None
            and _evidence(accepted_row["evidence"], accepted_subject) is not None
            and freshness is not None
            and _opaque(freshness["baseline_id"])
            and freshness["status"] == "fresh"
            and (freshness["baseline_subject"] is None or baseline_subject is not None)
            and (
                baseline_subject is None
                or (
                    accepted_subject["content_sha256"]
                    != baseline_subject["content_sha256"]
                    and (
                        accepted_subject["subject_id"] != baseline_subject["subject_id"]
                        or accepted_subject["revision_id"]
                        != baseline_subject["revision_id"]
                    )
                )
            )
        )
        if not accepted_valid:
            raise ValueError("consumed exact-subject premise receipt is incomplete")
    elif accepted is not None or reason not in _REJECTION_REASONS:
        raise ValueError("rejected exact-subject premise receipt is incomplete")
    receipt_id = row["receipt_id"]
    without_hash = {key: child for key, child in row.items() if key != "receipt_sha256"}
    without_identity = {
        key: child for key, child in without_hash.items() if key != "receipt_id"
    }
    if receipt_id != "exact-premise-" + _sha256(without_identity)[:32] or row[
        "receipt_sha256"
    ] != _sha256(without_hash):
        raise ValueError("exact-subject premise receipt integrity check failed")
    return row


def validate_exact_subject_premise(
    submission: object,
    *,
    context: object,
    prior_receipts: Sequence[object] = (),
) -> dict[str, Any]:
    """Return a deterministic receipt plus exact consumed/rejected replay status."""
    normalized_context = _context(context)
    submission_sha256 = _sha256(submission)
    context_sha256 = _sha256(normalized_context)
    replay_identity = _sha256(
        {
            "contract_version": CONTRACT_VERSION,
            "context_sha256": context_sha256,
            "submission_sha256": submission_sha256,
        }
    )
    accepted, reason = _accepted_premise(submission, normalized_context)
    computed = _receipt(
        context=normalized_context,
        submission_sha256=submission_sha256,
        replay_identity_sha256=replay_identity,
        accepted_premise=accepted,
        reason_code=reason,
    )
    if len(prior_receipts) > MAX_PRIOR_RECEIPTS:
        raise ValueError(f"prior premise receipts exceed {MAX_PRIOR_RECEIPTS}")
    matches = [
        validated
        for value in prior_receipts
        if (validated := validate_exact_subject_premise_receipt(value))[
            "replay_identity_sha256"
        ]
        == replay_identity
    ]
    if len(matches) > 1:
        raise ValueError("exact-subject premise replay identity is ambiguous")
    if matches:
        if matches[0] != computed:
            raise ValueError("exact-subject premise replay outcome conflicts")
        receipt = matches[0]
        disposition = f"exact_{receipt['status']}_replay"
    else:
        receipt = computed
        disposition = f"new_{receipt['status']}"
    return {
        "receipt": receipt,
        "replay": {
            "identity_sha256": replay_identity,
            "disposition": disposition,
            "receipt_id": receipt["receipt_id"],
        },
    }


__all__ = (
    "CONTRACT_VERSION",
    "validate_exact_subject_premise",
    "validate_exact_subject_premise_receipt",
)
