from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from .core import (
    VERDICT_AXES,
    canonical_digest,
)
from .receipt_shape import receipt_shape_errors


def consumption_errors(
    receipt: dict[str, Any],
    consumption: dict[str, Any] | None,
    projection: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []

    def error(code: str, message: str, evidence: Any = None) -> None:
        row: dict[str, Any] = {"code": code, "message": message}
        if evidence is not None:
            row["evidence"] = evidence
        errors.append(row)

    if not isinstance(consumption, dict):
        error(
            "finalization_consumption_missing",
            "Consumer must echo the exact finalization token, revision, projection, and receipt hash.",
        )
    else:
        bindings = {
            "finalization_token": receipt.get("finalization_token"),
            "attempt_id": receipt.get("attempt_id"),
            "attempt_revision": receipt.get("attempt_revision"),
            "authoritative_projection_id": receipt.get("authoritative_projection_id"),
            "authoritative_projection_digest": receipt.get(
                "authoritative_projection_digest"
            ),
            "receipt_hash": receipt.get("receipt_hash"),
        }
        mismatched = [
            field
            for field, expected in bindings.items()
            if consumption.get(field) != expected
        ]
        if mismatched:
            error(
                "finalization_consumption_binding_mismatch",
                "Consumer echo does not match the verified finalization receipt.",
                {"fields": mismatched},
            )
    if not isinstance(projection, dict):
        error(
            "authoritative_projection_missing",
            "Consumer must expose the finalized authoritative projection it consumed.",
        )
    else:
        expected_keys = {
            "verdict_contract_version",
            *VERDICT_AXES,
            "authoritative_final",
        }
        if set(projection) != expected_keys:
            error(
                "authoritative_projection_schema_mismatch",
                "Authoritative projection must contain exactly the version, six verdict axes, and authoritative final.",
                {
                    "missing": sorted(expected_keys - set(projection)),
                    "extra": sorted(set(projection) - expected_keys),
                },
            )
        if canonical_digest(projection) != receipt.get(
            "authoritative_projection_digest"
        ):
            error(
                "authoritative_projection_digest_mismatch",
                "Consumer projection does not match the receipt-bound authoritative projection digest.",
            )
        if projection.get("authoritative_final") != receipt.get("authoritative_final"):
            error(
                "authoritative_projection_verdict_mismatch",
                "Consumer projection and receipt expose different authoritative final verdicts.",
            )
    return errors


def workspace_root(
    result: dict[str, Any], contract_context: dict[str, Any] | None
) -> Path:
    values: Iterable[Any] = (
        (contract_context or {}).get("workspace_root"),
        (contract_context or {}).get("workspace"),
        (contract_context or {}).get("root"),
        result.get("workspace_root"),
        result.get("workspace"),
        result.get("root"),
    )
    value = next(
        (item for item in values if isinstance(item, str) and item.strip()), "."
    )
    return Path(value).resolve()


def verify_current_receipt(
    root: Path,
    receipt: dict[str, Any],
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    try:
        from ... import cycle_ledger

        verified = cycle_ledger.verify_finalization_receipt(
            root, str(receipt.get("cycle_id") or ""), receipt
        )
    except (
        ImportError,
        AttributeError,
        OSError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
    ) as exc:
        return None, [
            {
                "code": "finalization_receipt_current_verification_failed",
                "message": "Finalization receipt did not verify against the immutable snapshot and current pointer.",
                "evidence": {"reason": type(exc).__name__},
            }
        ]
    if (
        not isinstance(verified, dict)
        or verified.get("valid") is not True
        or not isinstance(verified.get("snapshot"), dict)
    ):
        return None, [
            {
                "code": "finalization_receipt_current_verification_failed",
                "message": "Finalization verifier did not return a valid current snapshot.",
            }
        ]
    return verified, []


def load_current_projection(
    root: Path,
    cycle_id: str,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None, list[dict[str, Any]]]:
    try:
        from ... import cycle_ledger

        state = cycle_ledger.load_current_finalized_state(root, cycle_id)
    except (
        ImportError,
        AttributeError,
        OSError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
    ) as exc:
        return (
            None,
            None,
            [
                {
                    "code": "current_finalization_projection_unavailable",
                    "message": "Current finalization pointer could not be verified and projected.",
                    "evidence": {"reason": type(exc).__name__},
                }
            ],
        )
    projection = (
        state.get("authoritative_projection") if isinstance(state, dict) else None
    )
    receipt = state.get("receipt") if isinstance(state, dict) else None
    errors: list[dict[str, Any]] = []
    if not isinstance(projection, dict) or not isinstance(receipt, dict):
        errors.append(
            {
                "code": "current_finalization_projection_invalid",
                "message": "Verified current finalization state omitted its projection or receipt.",
            }
        )
        return None, None, errors
    errors.extend(receipt_shape_errors(receipt))
    if canonical_digest(projection) != receipt.get("authoritative_projection_digest"):
        errors.append(
            {
                "code": "current_finalization_projection_digest_mismatch",
                "message": "Current pointer projection does not match its receipt-bound digest.",
            }
        )
    return (projection if not errors else None), receipt, errors
