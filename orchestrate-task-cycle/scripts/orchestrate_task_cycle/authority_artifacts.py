"""Workspace-bound verification for authority-owner artifacts.

The closed packet validator in :mod:`authority_boundary` is intentionally pure.
This module supplies the consuming boundary: it reopens immutable owner output
and mutable CAS projections without following symbolic links, then compares
their exact contents with the packet projection.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ._authority_artifact_decision import verify_decision
from ._authority_artifact_io import (
    artifact_finding as _finding,
    read_bound_json as _read_json,
    workspace_root_from_metadata,
)
from ._authority_artifact_projection import (
    axis_projection,
    scope_projection,
)
from ._authority_artifact_state import verify_grants, verify_reservation
from ._authority_artifact_settlement import validate_authority_use_receipt_settlement
from ._authority_artifact_verification import (
    validate_authority_verification_binding,
)


def validate_authority_artifacts(
    packet: dict[str, Any], workspace_root: Path | None
) -> list[dict[str, Any]]:
    """Reopen and cross-check every owner artifact consumed by a v2 packet."""

    findings: list[dict[str, Any]] = []
    if workspace_root is None:
        return [
            _finding(
                "authority_artifact_verification_unavailable",
                "Authority consumer requires an explicit existing workspace root.",
                "workspace",
            )
        ]
    decision = verify_decision(workspace_root, packet, findings)
    if decision is None:
        return findings
    verify_grants(workspace_root, packet, findings)
    operation = (
        packet.get("operation_binding")
        if isinstance(packet.get("operation_binding"), dict)
        else {}
    )
    binding = (
        packet.get("decision_binding")
        if isinstance(packet.get("decision_binding"), dict)
        else {}
    )
    if (
        operation.get("mutation_class") != "observe"
        and binding.get("decision") == "allowed"
    ):
        verify_reservation(workspace_root, packet, decision, findings)
    return findings


def read_bound_authority_json(
    root: Path,
    binding: dict[str, Any],
    label: str,
    *,
    expected_ref: str | None = None,
) -> dict[str, Any]:
    """Read one safe owner artifact for deterministic packet construction."""

    findings: list[dict[str, Any]] = []
    value = _read_json(
        root.resolve(strict=True), binding, label, findings, expected_ref=expected_ref
    )
    if value is None or findings:
        codes = ", ".join(str(row["code"]) for row in findings)
        raise ValueError(f"invalid authority artifact {label}: {codes}")
    return value


def owner_axis_projection(decision: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return axis_projection(decision)


def owner_scope_projection(decision: dict[str, Any]) -> dict[str, Any]:
    request = (
        decision.get("request") if isinstance(decision.get("request"), dict) else {}
    )
    return scope_projection(request)


__all__ = (
    "owner_axis_projection",
    "owner_scope_projection",
    "read_bound_authority_json",
    "validate_authority_use_receipt_settlement",
    "validate_authority_artifacts",
    "validate_authority_verification_binding",
    "workspace_root_from_metadata",
)
