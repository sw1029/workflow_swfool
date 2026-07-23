"""Reopen the immutable authority chain needed for use-receipt settlement."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ._authority_artifact_io import (
    artifact_finding as _finding,
    read_bound_bytes as _read_bytes,
    read_bound_json as _read_json,
)
from ._authority_settlement_contracts import (
    RESERVATION_ARTIFACT_KEYS,
    STATE_CHANGE_KEYS,
    VERIFICATION_CORE_KEYS,
    VERIFICATION_KEYS,
    reservation_artifact_binding,
    valid_timestamp,
    verification_shape_valid,
)
from .authority_boundary import canonical_sha256


def read_immutable_packet_lease(
    root: Path,
    packet: dict[str, Any],
    findings: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Reopen the immutable decision, grant, reservation, and preflight chain."""

    _verify_decision(root, packet, findings)
    _verify_grants(root, packet, findings)
    reservation = _verify_reservation(root, packet, findings)
    _verify_preflight(root, packet, findings)
    return reservation


def _verify_decision(
    root: Path, packet: dict[str, Any], findings: list[dict[str, Any]]
) -> None:
    binding = packet["decision_binding"]
    decision_id = binding.get("decision_id")
    decision = _read_json(
        root,
        {"ref": binding.get("artifact_ref"), "sha256": binding.get("artifact_sha256")},
        "decision",
        findings,
        expected_ref=f".task/authorization/decisions/{decision_id}.json",
    )
    if decision is None:
        return
    request = decision.get("request")
    request = request if isinstance(request, dict) else {}
    mismatch = bool(
        decision.get("schema_version") != 2
        or decision.get("artifact_kind") != "authority_decision"
        or decision.get("decision_id") != decision_id
        or request.get("request_id") != binding.get("request_id")
        or decision.get("request_sha256") != binding.get("request_sha256")
        or decision.get("decision") != binding.get("decision")
        or decision.get("effective_authority_fingerprint")
        != binding.get("effective_authority_fingerprint")
        or decision.get("selected_grants") != packet.get("selected_grants")
        or decision.get("lineage_grants") != packet.get("lineage_grants")
    )
    if mismatch:
        findings.append(
            _finding(
                "authority_settlement_decision_invalid",
                "Immutable decision does not exactly bind the authority packet.",
                "decision",
            )
        )


def _verify_grants(
    root: Path, packet: dict[str, Any], findings: list[dict[str, Any]]
) -> None:
    rows = [
        *(packet.get("selected_grants") or []),
        *(packet.get("lineage_grants") or []),
    ]
    for row in rows:
        if not isinstance(row, dict):
            continue
        grant_id = row.get("grant_id")
        grant = _read_json(
            root,
            {
                "ref": f".task/authorization/grants/{grant_id}.json",
                "sha256": row.get("grant_sha256"),
            },
            f"grant:{grant_id}",
            findings,
            expected_ref=f".task/authorization/grants/{grant_id}.json",
        )
        if grant is not None and _grant_mismatch(grant, row):
            findings.append(
                _finding(
                    "authority_settlement_grant_invalid",
                    "Immutable grant does not exactly bind the packet grant projection.",
                    f"grant:{grant_id}",
                )
            )
        _read_bytes(
            root,
            row.get("policy_snapshot"),
            f"policy_snapshot:{grant_id}",
            findings,
        )


def _grant_mismatch(grant: dict[str, Any], row: dict[str, Any]) -> bool:
    return bool(
        grant.get("schema_version") not in {2, 3}
        or grant.get("artifact_kind") != "authority_grant"
        or grant.get("grant_id") != row.get("grant_id")
        or grant.get("policy_snapshot") != row.get("policy_snapshot")
    )


def _verify_reservation(
    root: Path, packet: dict[str, Any], findings: list[dict[str, Any]]
) -> dict[str, Any] | None:
    binding = packet["reservation_binding"]
    reservation_id = binding.get("reservation_id")
    reservation = _read_json(
        root,
        reservation_artifact_binding(packet),
        "reservation",
        findings,
        expected_ref=f".task/authorization/reservations/{reservation_id}.json",
    )
    if reservation is None:
        return None
    decision = packet["decision_binding"]
    expected = {
        "reservation_id": reservation_id,
        "request_id": decision.get("request_id"),
        "request_sha256": decision.get("request_sha256"),
        "decision": {
            "ref": decision.get("artifact_ref"),
            "sha256": decision.get("artifact_sha256"),
        },
        "effective_authority_fingerprint": binding.get(
            "effective_authority_fingerprint"
        ),
        "grant_uses": binding.get("grant_uses"),
    }
    changes = reservation.get("state_changes")
    invalid = bool(
        set(reservation) != RESERVATION_ARTIFACT_KEYS
        or reservation.get("schema_version") != 2
        or reservation.get("artifact_kind") != "authority_reservation"
        or not valid_timestamp(reservation.get("reserved_at"))
        or not isinstance(reservation.get("idempotency_key"), str)
        or not reservation.get("idempotency_key")
        or not _reservation_changes_valid(changes)
        or any(reservation.get(key) != value for key, value in expected.items())
    )
    if invalid:
        findings.append(
            _finding(
                "authority_settlement_reservation_invalid",
                "Immutable reservation does not exactly bind the packet lease.",
                "reservation",
            )
        )
    return reservation


def _reservation_changes_valid(value: Any) -> bool:
    return bool(
        isinstance(value, list)
        and value
        and all(
            isinstance(row, dict)
            and set(row) == STATE_CHANGE_KEYS
            and isinstance(row.get("ref"), str)
            and row["ref"].startswith(".task/authorization/state/")
            and (row.get("before") is None or isinstance(row.get("before"), dict))
            and isinstance(row.get("after"), dict)
            for row in value
        )
    )


def _verify_preflight(
    root: Path, packet: dict[str, Any], findings: list[dict[str, Any]]
) -> None:
    preflight = packet["dispatch_preflight"]
    verification_id = preflight.get("verification_id")
    verification = _read_json(
        root,
        {
            "ref": preflight.get("artifact_ref"),
            "sha256": preflight.get("artifact_sha256"),
        },
        "pre_dispatch_verification",
        findings,
        expected_ref=f".task/authorization/verifications/{verification_id}.json",
    )
    if verification is None:
        return
    expected = {
        "schema_version": 2,
        "artifact_kind": "authority_verification",
        **{
            key: preflight.get(key)
            for key in VERIFICATION_KEYS - {"schema_version", "artifact_kind"}
        },
    }
    core = {key: verification.get(key) for key in VERIFICATION_CORE_KEYS}
    invalid = bool(
        not verification_shape_valid(verification)
        or verification.get("stage") != "pre_dispatch"
        or verification != expected
        or verification.get("verification_id") != "authv-" + canonical_sha256(core)[:24]
    )
    if invalid:
        findings.append(
            _finding(
                "authority_settlement_preflight_invalid",
                "Immutable pre-dispatch verification does not exactly bind the packet.",
                "pre_dispatch_verification",
            )
        )


__all__ = ("read_immutable_packet_lease",)
