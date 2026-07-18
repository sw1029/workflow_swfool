"""Read-only verification of authority use-receipt settlement."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ._authority_artifact_io import (
    artifact_finding as _finding,
    read_bound_bytes as _read_bytes,
    read_bound_json as _read_json,
)
from ._authority_settlement_contracts import (
    closed_binding,
    packet_contract_findings,
    packet_is_settleable,
    receipt_contract_valid,
    reservation_artifact_binding,
)
from ._authority_settlement_immutable import read_immutable_packet_lease
from ._authority_settlement_state import validate_receipt_state_changes
from .authority_boundary import canonical_sha256


def validate_authority_use_receipt_settlement(
    packet: dict[str, Any],
    binding: dict[str, Any],
    workspace_root: Path | None,
    *,
    execution_result: dict[str, Any],
    idempotency_key: str,
    phase: str = "activation",
) -> list[dict[str, Any]]:
    """Validate that an owner use receipt settled this exact effect.

    ``activation`` requires current projections to equal the receipt after
    images. ``historical`` checks the immutable chain and deterministic deltas
    while allowing later legitimate grant-state progress.
    """

    findings: list[dict[str, Any]] = []
    root = _workspace_root(workspace_root)
    if root is None:
        return [_workspace_finding()]
    phase_finding = _validate_phase_and_packet(packet, phase)
    if phase_finding is not None:
        return [phase_finding]
    packet_findings = packet_contract_findings(packet)
    if packet_findings:
        return packet_findings
    _verify_execution_result(root, execution_result, findings)
    if not isinstance(idempotency_key, str) or not idempotency_key:
        findings.append(
            _finding(
                "authority_settlement_idempotency_invalid",
                "Settlement requires a non-empty exact idempotency key.",
                "use_receipt",
            )
        )
        return findings
    receipt_id = _receipt_id(packet, idempotency_key)
    receipt_ref = f".task/authorization/use_receipts/{receipt_id}.json"
    receipt = _read_json(
        root,
        binding,
        "use_receipt",
        findings,
        expected_ref=receipt_ref,
    )
    if receipt is None:
        return findings
    reservation = read_immutable_packet_lease(root, packet, findings)
    if not receipt_contract_valid(receipt):
        findings.append(
            _finding(
                "authority_use_receipt_contract_invalid",
                "Authority use receipt must satisfy the closed owner contract.",
                "use_receipt",
            )
        )
        return findings
    mismatches = _receipt_binding_mismatches(
        packet, receipt, receipt_id, execution_result, idempotency_key
    )
    if mismatches:
        findings.append(
            {
                "code": "authority_use_receipt_binding_mismatch",
                "message": "Use receipt does not settle the packet's exact reservation and execution result.",
                "evidence": {"artifact": "use_receipt", "fields": mismatches},
            }
        )
    validate_receipt_state_changes(
        root,
        packet,
        receipt,
        reservation,
        receipt_id,
        phase,
        findings,
    )
    return findings


def _workspace_root(value: Path | None) -> Path | None:
    if value is None:
        return None
    try:
        return value.resolve(strict=True)
    except OSError:
        return None


def _workspace_finding() -> dict[str, Any]:
    return _finding(
        "authority_artifact_verification_unavailable",
        "Authority settlement requires an explicit existing workspace root.",
        "use_receipt",
    )


def _validate_phase_and_packet(
    packet: dict[str, Any], phase: str
) -> dict[str, Any] | None:
    if phase not in {"activation", "historical"}:
        return _finding(
            "authority_settlement_phase_invalid",
            "Use-receipt settlement phase must be activation or historical.",
            "use_receipt",
        )
    if not packet_is_settleable(packet):
        return _finding(
            "authority_settlement_packet_invalid",
            "Only an allowed mutating packet with a reserved lease can be settled.",
            "use_receipt",
        )
    return None


def _verify_execution_result(
    root: Path,
    execution_result: dict[str, Any],
    findings: list[dict[str, Any]],
) -> None:
    if not closed_binding(execution_result):
        findings.append(
            _finding(
                "authority_execution_result_binding_invalid",
                "Execution result must contain an exact workspace-relative ref and SHA-256.",
                "execution_result",
            )
        )
        return
    _read_bytes(
        root,
        execution_result,
        "execution_result",
        findings,
        authorization_only=False,
    )


def _receipt_id(packet: dict[str, Any], idempotency_key: str) -> str:
    reservation_sha256 = reservation_artifact_binding(packet).get("sha256")
    return (
        "authu-"
        + canonical_sha256({"reservation": reservation_sha256, "key": idempotency_key})[
            :24
        ]
    )


def _receipt_binding_mismatches(
    packet: dict[str, Any],
    receipt: dict[str, Any],
    receipt_id: str,
    execution_result: dict[str, Any],
    idempotency_key: str,
) -> list[str]:
    expected = {
        "receipt_id": receipt_id,
        "reservation": reservation_artifact_binding(packet),
        "execution_result": execution_result,
        "idempotency_key": idempotency_key,
    }
    return sorted(
        field for field, value in expected.items() if receipt.get(field) != value
    )


__all__ = ("validate_authority_use_receipt_settlement",)
