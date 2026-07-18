"""Exact settlement validation for read-only task-doctor authority UX."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .authority import (
    _authority_call,
    _binding,
    _current_settled_state,
    _owner_effect,
    _receipt,
    _reservation_id,
    _reservation_scope,
)
from .common import read_json, require, workspace_file

from manage_agent_authority.projection_receipts import validate_release_receipt


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
    kind = receipt.get("artifact_kind")
    if kind == "authority_release_receipt":
        _authority_call(
            "invalid_authority_settlement", "authority release receipt",
            lambda: validate_release_receipt(root, receipt, receipt_path),
        )
        effect_status = receipt.get("effect_status")
        if effect_status == "not_started":
            _current_settled_state(
                root, _reservation_id(root, reservation), "released",
                receipt["receipt_id"], receipt,
            )
            return "not_started"
        require(effect_status == "verified_no_effect",
                "invalid_authority_settlement",
                "released state is neither not-started nor verified no-effect")
        owner, body = _owner_effect(
            root, journal, item, receipt.get("no_effect_evidence")
        )
        require(body["effect_status"] == "confirmed_no_effect",
                "authority_settlement_mismatch",
                "verified no-effect release lacks an exact owner result")
        _receipt(root, receipt_binding, reservation, owner, "confirmed_no_effect")
        return "confirmed_no_effect"
    if kind == "authority_use_receipt":
        owner, body = _owner_effect(
            root, journal, item, receipt.get("owner_execution_result")
        )
        require(body["effect_status"] == "confirmed_effect",
                "authority_settlement_mismatch",
                "consumed settlement lacks an exact owner result")
        _receipt(root, receipt_binding, reservation, owner, "confirmed_effect")
        return "confirmed_effect"
    require(kind == "authority_reconciliation_receipt",
            "invalid_authority_settlement",
            "live settlement receipt has an unsupported type")
    evidence_binding = _binding(
        receipt.get("effect_evidence"), "settlement_projection.effect_evidence"
    )
    evidence_path = workspace_file(
        root, evidence_binding["ref"], evidence_binding["sha256"],
        "settlement_projection.effect_evidence",
    )
    evidence = read_json(evidence_path, "invalid_authority_settlement")
    effect_status = receipt.get("outcome")
    require(effect_status in {"confirmed_effect", "confirmed_no_effect"},
            "invalid_authority_settlement",
            "terminal reconciliation lacks a settled outcome")
    owner, body = _owner_effect(root, journal, item, evidence.get("owner_result"))
    require(body["effect_status"] == effect_status,
            "authority_settlement_mismatch",
            "reconciliation outcome differs from the exact owner result")
    _receipt(root, receipt_binding, reservation, owner, effect_status)
    return effect_status


__all__ = ["validate_settlement_projection"]
