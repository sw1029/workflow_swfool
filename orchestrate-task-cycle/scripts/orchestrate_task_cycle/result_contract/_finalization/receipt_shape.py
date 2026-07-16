from __future__ import annotations

from pathlib import Path
from typing import Any

from .core import (
    RECEIPT_KIND,
    SHA256_FIELDS,
    canonical_digest,
    full_sha256,
    opaque_id,
)


def receipt_shape_errors(receipt: dict[str, Any]) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    _validate_receipt_identity_and_hashes(receipt, errors)
    _validate_receipt_lineage(receipt, errors)
    return errors


def _error(
    errors: list[dict[str, Any]],
    code: str,
    message: str,
    evidence: Any = None,
) -> None:
    row: dict[str, Any] = {"code": code, "message": message}
    if evidence is not None:
        row["evidence"] = evidence
    errors.append(row)


def _validate_receipt_identity_and_hashes(
    receipt: dict[str, Any], errors: list[dict[str, Any]]
) -> None:
    if receipt.get("schema_version") != 1 or receipt.get("kind") != RECEIPT_KIND:
        _error(
            errors,
            "finalization_receipt_schema_invalid",
            "Finalization receipt requires schema_version=1 and kind=cycle_finalization_receipt.",
        )
    for field in (
        "cycle_id",
        "attempt_id",
        "authoritative_final",
        "authoritative_projection_id",
    ):
        if not opaque_id(receipt.get(field)):
            _error(
                errors,
                "finalization_receipt_identity_invalid",
                "Finalization receipt identity fields must be bounded opaque strings.",
                {"field": field},
            )
    if receipt.get("authoritative_final") not in {
        "success",
        "failure",
        "blocked",
        "partial",
        "not_evaluated",
    }:
        _error(
            errors,
            "finalization_receipt_authoritative_final_invalid",
            "Authoritative final verdict is outside the producer's closed enum.",
        )
    revision = receipt.get("attempt_revision")
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 1:
        _error(
            errors,
            "finalization_receipt_revision_invalid",
            "Finalization receipt attempt_revision must be a positive integer.",
            {"field": "attempt_revision"},
        )
    for field in ("supersedes_revision", "expected_previous_revision"):
        value = receipt.get(field)
        if value is not None and (
            isinstance(value, bool) or not isinstance(value, int) or value < 1
        ):
            _error(
                errors,
                "finalization_receipt_revision_invalid",
                "Supersession revisions must be null or positive integers.",
                {"field": field},
            )
    for field in (
        "supersedes_finalization_token",
        "expected_previous_finalization_token",
    ):
        value = receipt.get(field)
        if value is not None and not full_sha256(value):
            _error(
                errors,
                "finalization_receipt_supersession_invalid",
                "Supersession tokens must be null or full lowercase SHA-256 digests.",
                {"field": field},
            )
    previous_attempt = receipt.get("expected_previous_attempt_id")
    if previous_attempt is not None and not opaque_id(previous_attempt):
        _error(
            errors,
            "finalization_receipt_supersession_invalid",
            "Expected previous attempt ID must be null or a bounded opaque string.",
        )
    if receipt.get("state_commit_status") != "committed":
        _error(
            errors,
            "finalization_receipt_not_committed",
            "Only a committed finalization receipt may be consumed.",
        )
    for field in SHA256_FIELDS:
        if not full_sha256(receipt.get(field)):
            _error(
                errors,
                "finalization_receipt_hash_invalid",
                "Receipt hash fields require full lowercase SHA-256 digests.",
                {"field": field},
            )
    if (
        receipt.get("finalization_token")
        and receipt.get("snapshot_sha256")
        and receipt.get("finalization_token") != receipt.get("snapshot_sha256")
    ):
        _error(
            errors,
            "finalization_receipt_snapshot_token_mismatch",
            "Finalization token and immutable snapshot digest must match.",
        )
    if (
        receipt.get("authoritative_projection_id")
        != f"sha256:{receipt.get('authoritative_projection_digest')}"
    ):
        _error(
            errors,
            "finalization_receipt_projection_id_mismatch",
            "Authoritative projection ID must be derived from its full digest.",
        )
    snapshot_ref = receipt.get("snapshot_ref")
    if (
        not opaque_id(snapshot_ref, max_length=512)
        or Path(str(snapshot_ref)).is_absolute()
        or ".." in Path(str(snapshot_ref)).parts
    ):
        _error(
            errors,
            "finalization_receipt_snapshot_ref_invalid",
            "Snapshot reference must be a bounded workspace-relative path.",
        )
    if full_sha256(receipt.get("receipt_hash")):
        unhashed = {
            key: value for key, value in receipt.items() if key != "receipt_hash"
        }
        if canonical_digest(unhashed) != receipt.get("receipt_hash"):
            _error(
                errors,
                "finalization_receipt_self_hash_mismatch",
                "Receipt hash does not bind the supplied receipt body.",
            )


def _validate_receipt_lineage(
    receipt: dict[str, Any], errors: list[dict[str, Any]]
) -> None:
    expected_lineage = (
        receipt.get("expected_previous_revision"),
        receipt.get("expected_previous_attempt_id"),
        receipt.get("expected_previous_finalization_token"),
    )
    expected_empty = all(value is None for value in expected_lineage)
    expected_complete = all(value is not None for value in expected_lineage)
    if not expected_empty and not expected_complete:
        _error(
            errors,
            "finalization_receipt_previous_binding_partial",
            "CAS predecessor revision, attempt, and token must be all null or all populated.",
        )
    same_attempt = bool(
        expected_complete
        and receipt.get("expected_previous_attempt_id") == receipt.get("attempt_id")
    )
    supersession = (
        receipt.get("supersedes_revision"),
        receipt.get("supersedes_finalization_token"),
    )
    if same_attempt:
        _validate_same_attempt_lineage(receipt, supersession, errors)
    else:
        if receipt.get("attempt_revision") != 1:
            _error(
                errors,
                "finalization_receipt_new_attempt_revision_invalid",
                "A first or cross-attempt finalization must start at revision 1.",
            )
        if any(value is not None for value in supersession):
            _error(
                errors,
                "finalization_receipt_cross_attempt_supersession_invalid",
                "Cross-attempt CAS binding must not claim same-attempt supersession.",
            )


def _validate_same_attempt_lineage(
    receipt: dict[str, Any],
    supersession: tuple[Any, Any],
    errors: list[dict[str, Any]],
) -> None:
    if (
        receipt.get("attempt_revision")
        != receipt.get("expected_previous_revision", 0) + 1
    ):
        _error(
            errors,
            "finalization_receipt_revision_sequence_invalid",
            "Same-attempt correction revision must increment the expected previous revision by one.",
        )
    if any(value is None for value in supersession):
        _error(
            errors,
            "finalization_receipt_supersession_incomplete",
            "Same-attempt corrections must preserve complete supersession lineage.",
        )
    if receipt.get("supersedes_revision") != receipt.get("expected_previous_revision"):
        _error(
            errors,
            "finalization_receipt_supersession_mismatch",
            "Superseded and expected previous revisions must match.",
        )
    if receipt.get("supersedes_finalization_token") != receipt.get(
        "expected_previous_finalization_token"
    ):
        _error(
            errors,
            "finalization_receipt_supersession_mismatch",
            "Superseded and expected previous finalization tokens must match.",
        )
