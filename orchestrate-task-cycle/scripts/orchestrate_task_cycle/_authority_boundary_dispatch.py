"""Pre-dispatch lease and TOCTOU validation for authority packets."""

from __future__ import annotations

from typing import Any

from ._authority_boundary_schema import (
    GRANT_STATE_KEYS,
    PREFLIGHT_KEYS,
    RESERVATION_STATE_KEYS,
)
from ._authority_boundary_validation import (
    binding,
    closed,
    finding,
    identifier,
    nonnegative_int,
    sha,
)


def _not_applicable_preflight(
    preflight: dict[str, Any],
    reason: str,
    findings: list[dict[str, Any]],
) -> None:
    populated = any(
        preflight.get(field) not in (None, "", [])
        for field in PREFLIGHT_KEYS - {"status"}
    )
    if preflight.get("status") != "not_applicable" or populated:
        findings.append(
            finding(
                "authority_preflight_not_applicable_invalid",
                f"{reason} cannot carry dispatch verification state.",
            )
        )


def _dispatch_is_applicable(
    decision: dict[str, Any],
    operation: dict[str, Any],
    reservation: dict[str, Any],
    preflight: dict[str, Any],
    findings: list[dict[str, Any]],
) -> bool:
    if operation.get("mutation_class") == "observe":
        if reservation.get("applicability") != "not_applicable":
            findings.append(
                finding(
                    "authority_observe_reservation_invalid",
                    "Observe-only operations cannot carry a reservation.",
                )
            )
        _not_applicable_preflight(preflight, "Observe-only operations", findings)
        return False
    if decision.get("decision") != "allowed":
        if reservation.get("applicability") != "not_applicable":
            findings.append(
                finding(
                    "authority_non_dispatch_reservation_invalid",
                    "A non-allowed decision cannot reserve grant use.",
                )
            )
        _not_applicable_preflight(preflight, "A non-allowed decision", findings)
        return False
    return True


def _reservation_is_dispatchable(
    operation: dict[str, Any],
    reservation: dict[str, Any],
    uses: list[dict[str, Any]],
    findings: list[dict[str, Any]],
) -> bool:
    if operation.get("manifest_status") != "verified":
        findings.append(
            finding(
                "authority_unknown_mutating_operation",
                "Unknown or unverified mutating operation fails closed.",
            )
        )
    if reservation.get("applicability") != "required" or not uses:
        findings.append(
            finding(
                "authority_mutating_reservation_missing",
                "Mutating dispatch requires an exact reservation lease/use binding.",
            )
        )
        return False
    return True


def _validate_reservation_binding(
    decision: dict[str, Any],
    grants: list[dict[str, Any]],
    reservation: dict[str, Any],
    uses: list[dict[str, Any]],
    findings: list[dict[str, Any]],
) -> None:
    grant_map = {str(row.get("grant_id")): row for row in grants}
    if set(grant_map) != {str(row.get("grant_id")) for row in uses} or any(
        grant_map[str(row["grant_id"])].get("state_version")
        != row.get("state_version_before")
        for row in uses
        if str(row.get("grant_id")) in grant_map
    ):
        findings.append(
            finding(
                "authority_reservation_grant_mismatch",
                "Reservation uses must exactly cover selected grant versions.",
            )
        )
    if reservation.get("effective_authority_fingerprint") != decision.get(
        "effective_authority_fingerprint"
    ):
        findings.append(
            finding(
                "authority_reservation_fingerprint_mismatch",
                "Reservation must preserve the authority owner's decision fingerprint.",
            )
        )


def _validate_grant_state_row(
    row: dict[str, Any],
    index: int,
    findings: list[dict[str, Any]],
) -> None:
    remaining_uses = row.get("remaining_uses")
    if (
        not identifier(row.get("grant_id"))
        or sha(row.get("grant_sha256")) is None
        or not nonnegative_int(row.get("state_version"))
        or not nonnegative_int(row.get("reserved_uses"))
        or (remaining_uses is not None and not nonnegative_int(remaining_uses))
    ):
        findings.append(
            finding(
                "authority_verification_grant_state_invalid",
                f"verification grant state {index} is invalid.",
            )
        )


def _read_preflight_state(
    preflight: dict[str, Any],
    findings: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any], list[Any]]:
    verification_reservation = binding(
        preflight.get("reservation"),
        "dispatch_preflight.reservation",
        findings,
    )
    verification_state = closed(
        preflight.get("reservation_state"),
        RESERVATION_STATE_KEYS,
        "dispatch_preflight.reservation_state",
        findings,
    )
    grant_states = preflight.get("grant_states")
    if not isinstance(grant_states, list):
        findings.append(
            finding(
                "authority_verification_grant_states_invalid",
                "dispatch_preflight.grant_states must be a list.",
            )
        )
        grant_states = []
    for index, value in enumerate(grant_states):
        row = closed(
            value,
            GRANT_STATE_KEYS,
            f"dispatch_preflight.grant_states[{index}]",
            findings,
        )
        _validate_grant_state_row(row, index, findings)
    return verification_reservation, verification_state, grant_states


def _grant_states_mismatch(
    grant_states: list[Any],
    uses: list[dict[str, Any]],
) -> bool:
    use_map = {str(row["grant_id"]): row for row in uses if row.get("grant_id")}
    state_map = {
        str(row.get("grant_id")): row
        for row in grant_states
        if isinstance(row, dict) and row.get("grant_id")
    }
    grant_mismatch = set(use_map) != set(state_map) or any(
        state_map[grant_id].get("grant_sha256") != use.get("grant_sha256")
        or state_map[grant_id].get("state_version") != use.get("state_version_after")
        or state_map[grant_id].get("status") != "active"
        or int(state_map[grant_id].get("reserved_uses") or 0)
        < int(use.get("units") or 0)
        for grant_id, use in use_map.items()
        if grant_id in state_map
    )
    return grant_mismatch


def _preflight_mismatches(
    decision: dict[str, Any],
    reservation: dict[str, Any],
    preflight: dict[str, Any],
    verification_reservation: dict[str, Any],
    verification_state: dict[str, Any],
    grant_mismatch: bool,
) -> list[str]:
    expected = {
        "status": "verified",
        "stage": "pre_dispatch",
        "request_id": decision.get("request_id"),
        "effective_authority_fingerprint": decision.get(
            "effective_authority_fingerprint"
        ),
    }
    mismatches = sorted(
        field
        for field, expected_value in expected.items()
        if preflight.get(field) != expected_value
    )
    if verification_reservation.get("ref") != reservation.get(
        "artifact_ref"
    ) or verification_reservation.get("sha256") != reservation.get("artifact_sha256"):
        mismatches.append("reservation")
    for source, target in (
        ("ref", "state_ref"),
        ("sha256", "state_sha256"),
        ("version", "state_version"),
        ("status", "status"),
    ):
        if verification_state.get(source) != reservation.get(target):
            mismatches.append("reservation_state")
    if grant_mismatch:
        mismatches.append("grant_states")
    if (
        not identifier(preflight.get("verification_id"))
        or not preflight.get("verified_at")
        or not preflight.get("artifact_ref")
        or sha(preflight.get("artifact_sha256")) is None
    ):
        mismatches.append("verification_artifact")
    return sorted(set(mismatches))


def validate_mutating_dispatch(
    decision: dict[str, Any],
    operation: dict[str, Any],
    grants: list[dict[str, Any]],
    reservation: dict[str, Any],
    uses: list[dict[str, Any]],
    preflight: dict[str, Any],
    findings: list[dict[str, Any]],
) -> None:
    if not _dispatch_is_applicable(
        decision, operation, reservation, preflight, findings
    ):
        return
    if not _reservation_is_dispatchable(operation, reservation, uses, findings):
        return
    _validate_reservation_binding(decision, grants, reservation, uses, findings)
    verification_reservation, verification_state, grant_states = _read_preflight_state(
        preflight, findings
    )
    mismatches = _preflight_mismatches(
        decision,
        reservation,
        preflight,
        verification_reservation,
        verification_state,
        _grant_states_mismatch(grant_states, uses),
    )
    if mismatches:
        findings.append(
            finding(
                "authority_dispatch_toctou_mismatch",
                "Pre-dispatch grant, reservation, revocation, expiry, or usage verification is stale.",
                {"fields": mismatches},
            )
        )


__all__ = ("validate_mutating_dispatch",)
