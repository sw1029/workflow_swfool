"""Exact settlement validation for read-only task-doctor authority UX."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .authority import (
    _binding,
    _owner_effect,
    _reservation_scope,
)
from .common import read_json, require, workspace_file
from .authority_settlement import (
    validate_not_started_receipt,
    validate_settlement_artifact,
)
from .owner_results import verify_owner_result


def validate_settlement_projection(
    root: Path, journal: dict[str, Any], item: dict[str, Any],
    reservation_value: Any, receipt_value: Any,
) -> str:
    """Validate a live terminal authority projection and its exact owner result."""

    reservation = _binding(reservation_value, "settlement_projection.reservation")
    receipt_binding = _binding(receipt_value, "settlement_projection.receipt")
    _reservation_scope(root, item, reservation, phase="structural")
    receipt_path = workspace_file(
        root, receipt_binding["ref"], receipt_binding["sha256"],
        "settlement_projection.receipt",
    )
    receipt = read_json(receipt_path, "invalid_authority_settlement")
    require(receipt.get("reservation") == reservation,
            "authority_settlement_mismatch",
            "live settlement receipt binds a different reservation")
    if (
        receipt.get("artifact_kind") == "authority_release_receipt"
        and receipt.get("effect_status") == "not_started"
    ):
        validate_not_started_receipt(root, receipt_binding, reservation)
        return "not_started"
    effect_status = (
        "confirmed_effect"
        if receipt.get("artifact_kind") == "authority_use_receipt"
        else receipt.get("outcome", "confirmed_no_effect")
    )
    require(effect_status in {"confirmed_effect", "confirmed_no_effect"},
            "invalid_authority_settlement",
            "terminal settlement lacks a settled outcome")
    owner = validate_settlement_artifact(
        root, receipt_binding, reservation, effect_status
    )
    owner_path = workspace_file(
        root, owner["ref"], owner["sha256"], "settlement owner artifact"
    )
    owner_body = read_json(owner_path, "invalid_authority_settlement")
    if owner_body.get("artifact_kind") == "task_doctor_owner_effect_result":
        _owner, wrapper = _owner_effect(root, journal, item, owner)
        require(wrapper["effect_status"] == effect_status,
                "authority_settlement_mismatch",
                "settlement wrapper outcome differs from owner result")
    else:
        verify_owner_result(root, item, owner, effect_status)
    return effect_status


__all__ = ["validate_settlement_projection"]
