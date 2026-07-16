"""Finalization contract public facade."""

# Compatibility facade intentionally re-exports imported symbols.
# ruff: noqa: F401

from __future__ import annotations

from typing import Any

from ._finalization.candidate import candidate_errors
from ._finalization.core import (
    CANDIDATE_KIND,
    RECEIPT_KIND,
    SHA256_FIELDS,
    SNAPSHOT_KIND,
    VERDICT_AXES,
    _value_at_path,
    canonical_digest,
    conflicting_finalization_receipt_aliases,
    extract_finalization_consumption,
    extract_finalization_receipt,
    finalization_receipt_aliases,
    finalization_required,
    full_sha256,
    opaque_id,
    projection_aliases,
    projection_conclusions,
    projection_from_result,
)
from ._finalization.receipt import (
    consumption_errors,
    load_current_projection,
    receipt_shape_errors,
    verify_current_receipt,
    workspace_root,
)


def validate_finalization_contract(
    target: str,
    result: dict[str, Any],
    contract_context: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    required = finalization_required(target, result)
    if target == "validate":
        candidate_present = (
            result.get("final_candidate") is not None
            or result.get("kind") == CANDIDATE_KIND
        )
        if required and not candidate_present:
            errors.append(
                {
                    "code": "final_candidate_missing",
                    "message": "Governed completion validation must emit an immutable final candidate before durable finalization.",
                }
            )
        if candidate_present:
            errors.extend(candidate_errors(result))
        return errors

    receipt = extract_finalization_receipt(result)
    receipt_present = receipt is not None
    if required and not receipt_present:
        errors.append(
            {
                "code": "finalization_receipt_missing",
                "message": "A predecessor final attempt cannot be consumed before its content-bound finalization receipt is verified.",
            }
        )
        return errors
    if not receipt_present:
        return errors
    if conflicting_finalization_receipt_aliases(result):
        errors.append(
            {
                "code": "finalization_receipt_alias_conflict",
                "message": "Finalization receipt aliases disagree; do not select a favorable or current-looking receipt.",
            }
        )
    errors.extend(receipt_shape_errors(receipt))
    aliases = projection_aliases(result)
    if len({canonical_digest(value) for value in aliases}) > 1:
        errors.append(
            {
                "code": "authoritative_projection_alias_conflict",
                "message": "Current authoritative projection aliases disagree; do not select the favorable projection.",
            }
        )
    projection = projection_from_result(result)
    consumption = extract_finalization_consumption(result)
    errors.extend(consumption_errors(receipt, consumption, projection))
    if errors:
        return errors
    verified, verification_errors = verify_current_receipt(
        workspace_root(result, contract_context), receipt
    )
    errors.extend(verification_errors)
    if verified is not None:
        snapshot = verified["snapshot"]
        snapshot_projection = snapshot.get("authoritative_projection")
        if snapshot.get("kind") != SNAPSHOT_KIND:
            errors.append(
                {
                    "code": "finalization_snapshot_schema_mismatch",
                    "message": "Verified finalization snapshot kind is invalid.",
                }
            )
        if snapshot_projection != projection:
            errors.append(
                {
                    "code": "authoritative_projection_snapshot_mismatch",
                    "message": "Consumer projection differs from the current immutable finalization snapshot.",
                }
            )
    return errors


def verified_projection(
    result: dict[str, Any],
    contract_context: dict[str, Any] | None = None,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None, list[dict[str, Any]]]:
    receipt = extract_finalization_receipt(result)
    if receipt is None:
        return None, None, []
    errors: list[dict[str, Any]] = []
    if conflicting_finalization_receipt_aliases(result):
        errors.append(
            {
                "code": "finalization_receipt_alias_conflict",
                "message": "Finalization receipt aliases disagree; current projection consumption is not evaluated.",
            }
        )
    errors.extend(receipt_shape_errors(receipt))
    if errors:
        return None, receipt, errors
    verified, verification_errors = verify_current_receipt(
        workspace_root(result, contract_context), receipt
    )
    errors.extend(verification_errors)
    if verified is None:
        return None, receipt, errors
    projection = verified["snapshot"].get("authoritative_projection")
    if not isinstance(projection, dict) or canonical_digest(projection) != receipt.get(
        "authoritative_projection_digest"
    ):
        errors.append(
            {
                "code": "authoritative_projection_snapshot_mismatch",
                "message": "Verified snapshot does not contain the receipt-bound authoritative projection.",
            }
        )
        return None, receipt, errors
    return projection, receipt, errors


__all__ = [
    "CANDIDATE_KIND",
    "RECEIPT_KIND",
    "SHA256_FIELDS",
    "SNAPSHOT_KIND",
    "VERDICT_AXES",
    "candidate_errors",
    "canonical_digest",
    "conflicting_finalization_receipt_aliases",
    "consumption_errors",
    "extract_finalization_consumption",
    "extract_finalization_receipt",
    "finalization_receipt_aliases",
    "finalization_required",
    "full_sha256",
    "load_current_projection",
    "opaque_id",
    "projection_aliases",
    "projection_conclusions",
    "projection_from_result",
    "receipt_shape_errors",
    "validate_finalization_contract",
    "verified_projection",
    "verify_current_receipt",
    "workspace_root",
]
