"""Trusted validation shared by registered owner settlement and recovery."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .evaluator import load_bound_decision
from .execution_results import validate_pre_commit_verification
from .owner_validators import OWNER_VALIDATORS, invoke_registered_owner_validator
from .owner_validators import operation_identity
from .owner_validators import validate_owner_validation_receipt
from .owner_validation_io import read_bound_owner_validation_receipt


def registered_release_required(
    root: Path, reservation: dict[str, Any]
) -> bool:
    """Return whether the public lifecycle API must dispatch through settlement."""

    decision, _ = load_bound_decision(
        root, reservation["decision"]["ref"], reservation["decision"]["sha256"]
    )
    request = decision.get("request")
    return isinstance(request, dict) and operation_identity(request) in OWNER_VALIDATORS


def _receipt_inputs(
    candidate: dict[str, Any],
) -> tuple[dict[str, str], dict[str, str]]:
    """Recover exact validation inputs from an already bounded acquisition."""

    owner_result = candidate.get("owner_result")
    pre_commit = candidate.get("pre_commit_verification")
    if not isinstance(owner_result, dict) or not isinstance(pre_commit, dict):
        raise SystemExit("Registered owner validation bindings are missing.")
    return owner_result, pre_commit


def validate_registered_owner_receipt(
    root: Path,
    reservation: dict[str, Any],
    reservation_binding: dict[str, str],
    owner_validation: dict[str, str],
    *,
    expected_version: int,
    require_current_state: bool,
    skills_root: Path | None,
    expected_outcomes: set[str],
    owner_result: dict[str, str] | None = None,
    pre_commit_verification: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Reproduce one canonical historical receipt before trusting its projection."""

    decision, _ = load_bound_decision(
        root, reservation["decision"]["ref"], reservation["decision"]["sha256"]
    )
    request = decision.get("request")
    if (
        not isinstance(request, dict)
        or operation_identity(request) not in OWNER_VALIDATORS
    ):
        raise SystemExit("Authority reservation has no registered owner validator.")
    _, candidate = read_bound_owner_validation_receipt(root, owner_validation)
    if owner_result is None or pre_commit_verification is None:
        owner_result, pre_commit_verification = _receipt_inputs(
            candidate
        )
    receipt = validate_owner_validation_receipt(
        candidate,
        request=request,
        owner_result=owner_result,
        reservation=reservation_binding,
        pre_commit_verification=pre_commit_verification,
        phase="historical",
    )
    validate_pre_commit_verification(
        root,
        reservation,
        reservation_binding,
        pre_commit_verification,
        expected_version=expected_version,
        require_current_state=require_current_state,
    )
    recomputed = invoke_registered_owner_validator(
        root,
        request,
        owner_result,
        reservation_binding,
        pre_commit_verification,
        phase="historical",
        skills_root=skills_root,
    )
    if recomputed != receipt:
        raise SystemExit(
            "Registered owner validation receipt is not reproducible by its fixed validator."
        )
    if receipt.get("outcome") not in expected_outcomes:
        raise SystemExit(
            "Registered owner validation outcome does not permit this settlement."
        )
    return receipt


def validate_registered_release(
    root: Path,
    reservation: dict[str, Any],
    reservation_binding: dict[str, str],
    evidence_binding: dict[str, str],
    effect_status: str,
    expected_version: int,
    skills_root: Path | None,
    *,
    require_current_state: bool,
) -> None:
    """Re-run the registered owner before accepting a no-effect release."""
    if effect_status == "not_started":
        raise SystemExit(
            "Registered owner operations require authority settle before release."
        )
    expected_outcome = {
        "confirmed_no_effect": "verified_no_effect",
        "unknown_effect": "unknown_effect",
    }
    allowed = {
        outcome for outcome, status in expected_outcome.items()
        if status == effect_status
    }
    validate_registered_owner_receipt(
        root,
        reservation,
        reservation_binding,
        evidence_binding,
        expected_version=expected_version,
        require_current_state=require_current_state,
        skills_root=skills_root,
        expected_outcomes=allowed,
    )


__all__ = (
    "registered_release_required",
    "validate_registered_owner_receipt",
    "validate_registered_release",
)
