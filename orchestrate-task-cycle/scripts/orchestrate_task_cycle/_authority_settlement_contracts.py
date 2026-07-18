"""Closed schemas and pure helpers for authority lifecycle settlement."""

from __future__ import annotations

import datetime as dt
from typing import Any

from .authority_boundary import project_authority_packet


VERIFICATION_KEYS = {
    "schema_version",
    "artifact_kind",
    "verification_id",
    "stage",
    "reservation",
    "reservation_state",
    "grant_states",
    "request_id",
    "effective_authority_fingerprint",
    "verified_at",
}
VERIFICATION_CORE_KEYS = VERIFICATION_KEYS - {"verification_id"}
BINDING_KEYS = {"ref", "sha256"}
RESERVATION_STATE_BINDING_KEYS = {"ref", "sha256", "version", "status"}
GRANT_STATE_BINDING_KEYS = {
    "grant_id",
    "grant_sha256",
    "state_version",
    "status",
    "remaining_uses",
    "reserved_uses",
}
USE_RECEIPT_KEYS = {
    "schema_version",
    "artifact_kind",
    "receipt_id",
    "reservation",
    "execution_result",
    "consumed_at",
    "grant_versions_after",
    "state_changes",
    "idempotency_key",
}
TYPED_USE_RECEIPT_KEYS = USE_RECEIPT_KEYS | {
    "owner_execution_result",
    "pre_commit_verification",
}
STATE_CHANGE_KEYS = {"ref", "before", "after"}
GRANT_STATE_KEYS = {
    "schema_version",
    "artifact_kind",
    "grant_id",
    "grant_sha256",
    "status",
    "remaining_uses",
    "reserved_uses",
    "consumed_uses",
    "version",
    "last_event_id",
}
RESERVATION_STATE_KEYS = {
    "schema_version",
    "artifact_kind",
    "reservation_id",
    "status",
    "version",
    "last_event_id",
}
RESERVATION_ARTIFACT_KEYS = {
    "schema_version",
    "artifact_kind",
    "reservation_id",
    "request_id",
    "request_sha256",
    "decision",
    "effective_authority_fingerprint",
    "grant_uses",
    "state_changes",
    "reserved_at",
    "idempotency_key",
}


def is_nonnegative_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def is_positive_int(value: Any) -> bool:
    return is_nonnegative_int(value) and value > 0


def is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def valid_timestamp(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None


def closed_binding(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and set(value) == BINDING_KEYS
        and isinstance(value.get("ref"), str)
        and is_sha256(value.get("sha256"))
    )


def packet_is_settleable(packet: dict[str, Any]) -> bool:
    operation = packet.get("operation_binding")
    decision = packet.get("decision_binding")
    reservation = packet.get("reservation_binding")
    preflight = packet.get("dispatch_preflight")
    return bool(
        isinstance(operation, dict)
        and operation.get("mutation_class") != "observe"
        and isinstance(decision, dict)
        and decision.get("decision") == "allowed"
        and isinstance(reservation, dict)
        and reservation.get("applicability") == "required"
        and isinstance(preflight, dict)
        and preflight.get("status") == "verified"
        and preflight.get("stage") == "pre_dispatch"
    )


def packet_contract_findings(packet: dict[str, Any]) -> list[dict[str, Any]]:
    return list(project_authority_packet(packet).findings)


def reservation_artifact_binding(packet: dict[str, Any]) -> dict[str, Any]:
    reservation = packet.get("reservation_binding")
    reservation = reservation if isinstance(reservation, dict) else {}
    return {
        "ref": reservation.get("artifact_ref"),
        "sha256": reservation.get("artifact_sha256"),
    }


def verification_shape_valid(value: dict[str, Any]) -> bool:
    reservation_state = value.get("reservation_state")
    grant_states = value.get("grant_states")
    valid_reservation = bool(
        isinstance(reservation_state, dict)
        and set(reservation_state) == RESERVATION_STATE_BINDING_KEYS
        and closed_binding(
            {
                "ref": reservation_state.get("ref"),
                "sha256": reservation_state.get("sha256"),
            }
        )
        and is_nonnegative_int(reservation_state.get("version"))
        and reservation_state.get("status") == "reserved"
    )
    valid_grants = bool(
        isinstance(grant_states, list)
        and all(grant_state_binding_valid(row) for row in grant_states)
        and len({row["grant_id"] for row in grant_states}) == len(grant_states)
    )
    return bool(
        set(value) == VERIFICATION_KEYS
        and value.get("schema_version") == 2
        and value.get("artifact_kind") == "authority_verification"
        and closed_binding(value.get("reservation"))
        and valid_reservation
        and valid_grants
        and isinstance(value.get("request_id"), str)
        and bool(value["request_id"])
        and is_sha256(value.get("effective_authority_fingerprint"))
        and valid_timestamp(value.get("verified_at"))
    )


def grant_state_binding_valid(row: Any) -> bool:
    return bool(
        isinstance(row, dict)
        and set(row) == GRANT_STATE_BINDING_KEYS
        and isinstance(row.get("grant_id"), str)
        and bool(row["grant_id"])
        and is_sha256(row.get("grant_sha256"))
        and is_nonnegative_int(row.get("state_version"))
        and row.get("status") == "active"
        and (
            row.get("remaining_uses") is None
            or is_nonnegative_int(row.get("remaining_uses"))
        )
        and is_nonnegative_int(row.get("reserved_uses"))
    )


def valid_grant_state(state: Any, grant_id: str, grant_sha256: str) -> bool:
    return bool(
        isinstance(state, dict)
        and set(state) == GRANT_STATE_KEYS
        and state.get("schema_version") == 2
        and state.get("artifact_kind") == "authority_grant_state"
        and state.get("grant_id") == grant_id
        and state.get("grant_sha256") == grant_sha256
        and state.get("status") in {"active", "exhausted"}
        and (
            state.get("remaining_uses") is None
            or is_nonnegative_int(state.get("remaining_uses"))
        )
        and is_nonnegative_int(state.get("reserved_uses"))
        and is_nonnegative_int(state.get("consumed_uses"))
        and is_nonnegative_int(state.get("version"))
        and (
            state.get("last_event_id") is None
            or isinstance(state.get("last_event_id"), str)
        )
    )


def expected_grant_after(
    before: dict[str, Any], units: int, receipt_id: str
) -> dict[str, Any] | None:
    remaining = before["remaining_uses"]
    if remaining is not None and remaining < units:
        return None
    if before["reserved_uses"] < units:
        return None
    next_remaining = remaining - units if remaining is not None else None
    return {
        **before,
        "remaining_uses": next_remaining,
        "reserved_uses": before["reserved_uses"] - units,
        "consumed_uses": before["consumed_uses"] + units,
        "status": "exhausted" if next_remaining == 0 else "active",
        "version": before["version"] + 1,
        "last_event_id": receipt_id,
    }


def receipt_contract_valid(value: dict[str, Any]) -> bool:
    changes = value.get("state_changes")
    versions = value.get("grant_versions_after")
    return bool(
        frozenset(value)
        in {frozenset(USE_RECEIPT_KEYS), frozenset(TYPED_USE_RECEIPT_KEYS)}
        and value.get("schema_version") == 2
        and value.get("artifact_kind") == "authority_use_receipt"
        and closed_binding(value.get("reservation"))
        and closed_binding(value.get("execution_result"))
        and (
            set(value) == USE_RECEIPT_KEYS
            or (
                closed_binding(value.get("owner_execution_result"))
                and closed_binding(value.get("pre_commit_verification"))
            )
        )
        and valid_timestamp(value.get("consumed_at"))
        and isinstance(versions, dict)
        and all(
            isinstance(key, str) and key and is_nonnegative_int(version)
            for key, version in versions.items()
        )
        and isinstance(changes, list)
        and bool(changes)
        and all(state_change_shape_valid(row) for row in changes)
        and isinstance(value.get("idempotency_key"), str)
        and bool(value["idempotency_key"])
    )


def state_change_shape_valid(row: Any) -> bool:
    return bool(
        isinstance(row, dict)
        and set(row) == STATE_CHANGE_KEYS
        and isinstance(row.get("ref"), str)
        and row["ref"].startswith(".task/authorization/state/")
        and isinstance(row.get("before"), dict)
        and isinstance(row.get("after"), dict)
    )


__all__ = (
    "RESERVATION_ARTIFACT_KEYS",
    "RESERVATION_STATE_KEYS",
    "STATE_CHANGE_KEYS",
    "VERIFICATION_CORE_KEYS",
    "VERIFICATION_KEYS",
    "closed_binding",
    "expected_grant_after",
    "is_nonnegative_int",
    "is_positive_int",
    "packet_contract_findings",
    "packet_is_settleable",
    "receipt_contract_valid",
    "reservation_artifact_binding",
    "valid_grant_state",
    "valid_timestamp",
    "verification_shape_valid",
)
