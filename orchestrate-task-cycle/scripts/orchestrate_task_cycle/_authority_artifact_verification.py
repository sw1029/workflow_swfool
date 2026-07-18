"""Read-only validation of the authority pre-commit phase."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ._authority_artifact_io import (
    artifact_finding as _finding,
    read_bound_json as _read_json,
)
from ._authority_settlement_contracts import (
    VERIFICATION_CORE_KEYS,
    packet_contract_findings,
    packet_is_settleable,
    reservation_artifact_binding,
    verification_shape_valid,
)
from .authority_boundary import canonical_sha256


def validate_authority_verification_binding(
    packet: dict[str, Any],
    binding: dict[str, Any],
    workspace_root: Path | None,
    *,
    expected_stage: str = "pre_commit",
) -> list[dict[str, Any]]:
    """Validate one exact post-dispatch verification against ``packet``."""

    findings: list[dict[str, Any]] = []
    if workspace_root is None:
        return [_workspace_finding()]
    try:
        root = workspace_root.resolve(strict=True)
    except OSError:
        return [_workspace_finding()]
    if not packet_is_settleable(packet):
        return [
            _finding(
                "authority_settlement_packet_invalid",
                "Only an allowed mutating packet with a reserved lease can bind a later verification.",
                "pre_commit_verification",
            )
        ]
    packet_findings = packet_contract_findings(packet)
    if packet_findings:
        return packet_findings
    if expected_stage != "pre_commit":
        return [
            _finding(
                "authority_verification_stage_invalid",
                "The post-dispatch consumer only accepts the pre_commit phase.",
                "pre_commit_verification",
            )
        ]
    verification = _read_json(root, binding, "pre_commit_verification", findings)
    if verification is None:
        return findings
    verification_id = verification.get("verification_id")
    expected_ref = (
        f".task/authorization/verifications/{verification_id}.json"
        if isinstance(verification_id, str) and verification_id
        else None
    )
    if expected_ref is None or binding.get("ref") != expected_ref:
        findings.append(
            _finding(
                "authority_verification_ref_mismatch",
                "Verification binding must use the deterministic owner artifact path.",
                "pre_commit_verification",
            )
        )
    if not verification_shape_valid(verification):
        findings.append(
            _finding(
                "authority_owner_verification_contract_invalid",
                "Authority verification must satisfy the closed owner contract.",
                "pre_commit_verification",
            )
        )
        return findings
    core = {key: verification[key] for key in VERIFICATION_CORE_KEYS}
    if verification_id != "authv-" + canonical_sha256(core)[:24]:
        findings.append(
            _finding(
                "authority_verification_id_mismatch",
                "Verification ID must be derived from its exact canonical core.",
                "pre_commit_verification",
            )
        )
    mismatches = _packet_mismatches(packet, verification, expected_stage)
    if mismatches:
        findings.append(
            {
                "code": "authority_verification_packet_mismatch",
                "message": "Verification does not exactly bind the packet's reserved phase.",
                "evidence": {
                    "artifact": "pre_commit_verification",
                    "fields": mismatches,
                },
            }
        )
    return findings


def _workspace_finding() -> dict[str, Any]:
    return _finding(
        "authority_artifact_verification_unavailable",
        "Authority verification requires an explicit existing workspace root.",
        "pre_commit_verification",
    )


def _packet_mismatches(
    packet: dict[str, Any], verification: dict[str, Any], expected_stage: str
) -> list[str]:
    preflight = packet["dispatch_preflight"]
    reservation = packet["reservation_binding"]
    decision = packet["decision_binding"]
    expected_values = {
        "stage": expected_stage,
        "reservation": reservation_artifact_binding(packet),
        "reservation_state": preflight.get("reservation_state"),
        "grant_states": preflight.get("grant_states"),
        "request_id": decision.get("request_id"),
        "effective_authority_fingerprint": reservation.get(
            "effective_authority_fingerprint"
        ),
    }
    return sorted(
        key
        for key, expected in expected_values.items()
        if verification.get(key) != expected
    )


__all__ = ("validate_authority_verification_binding",)
