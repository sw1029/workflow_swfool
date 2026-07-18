"""Grant, reservation, and pre-dispatch state artifact verification."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ._authority_artifact_io import (
    artifact_finding as _finding,
    authority_binding as _binding,
    read_bound_bytes as _read_bytes,
    read_bound_json as _read_json,
    safe_authority_path as _safe_path,
)


RESERVATION_KEYS = {
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
RESERVATION_STATE_KEYS = {
    "schema_version",
    "artifact_kind",
    "reservation_id",
    "status",
    "version",
    "last_event_id",
}
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
STATE_CHANGE_KEYS = {"ref", "before", "after"}


def _valid_state_changes(value: Any) -> bool:
    return bool(
        isinstance(value, list)
        and value
        and all(
            isinstance(row, dict)
            and set(row) == STATE_CHANGE_KEYS
            and (row.get("before") is None or isinstance(row.get("before"), dict))
            and isinstance(row.get("after"), dict)
            and isinstance(row.get("ref"), str)
            and row["ref"].startswith(".task/authorization/state/")
            for row in value
        )
    )


def verify_reservation(
    root: Path,
    packet: dict[str, Any],
    decision: dict[str, Any],
    findings: list[dict[str, Any]],
) -> None:
    reservation_binding = (
        packet.get("reservation_binding")
        if isinstance(packet.get("reservation_binding"), dict)
        else {}
    )
    preflight = (
        packet.get("dispatch_preflight")
        if isinstance(packet.get("dispatch_preflight"), dict)
        else {}
    )
    reservation_id = reservation_binding.get("reservation_id")
    expected_reservation_ref = f".task/authorization/reservations/{reservation_id}.json"
    reservation = _read_json(
        root,
        _binding(
            reservation_binding.get("artifact_ref"),
            reservation_binding.get("artifact_sha256"),
        ),
        "reservation",
        findings,
        expected_ref=expected_reservation_ref,
    )
    expected_state_ref = f".task/authorization/state/reservations/{reservation_id}.json"
    state = _read_json(
        root,
        _binding(
            reservation_binding.get("state_ref"),
            reservation_binding.get("state_sha256"),
        ),
        "reservation_state",
        findings,
        expected_ref=expected_state_ref,
    )
    verification_id = preflight.get("verification_id")
    expected_verification_ref = (
        f".task/authorization/verifications/{verification_id}.json"
    )
    verification = _read_json(
        root,
        _binding(preflight.get("artifact_ref"), preflight.get("artifact_sha256")),
        "pre_dispatch_verification",
        findings,
        expected_ref=expected_verification_ref,
    )
    if reservation is not None:
        expected = {
            "reservation_id": reservation_binding.get("reservation_id"),
            "request_id": (decision.get("request") or {}).get("request_id"),
            "request_sha256": decision.get("request_sha256"),
            "decision": _binding(
                (packet.get("decision_binding") or {}).get("artifact_ref"),
                (packet.get("decision_binding") or {}).get("artifact_sha256"),
            ),
            "effective_authority_fingerprint": decision.get(
                "effective_authority_fingerprint"
            ),
            "grant_uses": reservation_binding.get("grant_uses"),
        }
        mismatches = sorted(
            key for key, value in expected.items() if reservation.get(key) != value
        )
        if (
            set(reservation) != RESERVATION_KEYS
            or reservation.get("schema_version") != 2
            or reservation.get("artifact_kind") != "authority_reservation"
            or not _valid_state_changes(reservation.get("state_changes"))
            or mismatches
        ):
            findings.append(
                {
                    "code": "authority_owner_reservation_mismatch",
                    "message": "Reservation artifact does not exactly bind the owner decision and grant uses.",
                    "evidence": {"fields": mismatches},
                }
            )
    if state is not None:
        expected = {
            "reservation_id": reservation_id,
            "status": reservation_binding.get("status"),
            "version": reservation_binding.get("state_version"),
        }
        mismatches = sorted(
            key for key, value in expected.items() if state.get(key) != value
        )
        if (
            set(state) != RESERVATION_STATE_KEYS
            or state.get("schema_version") != 2
            or state.get("artifact_kind") != "authority_reservation_state"
            or mismatches
        ):
            findings.append(
                {
                    "code": "authority_owner_reservation_state_mismatch",
                    "message": "Current reservation CAS state does not match the packet.",
                    "evidence": {"fields": mismatches},
                }
            )
    if verification is not None:
        projected = {
            key: preflight.get(key)
            for key in VERIFICATION_KEYS - {"schema_version", "artifact_kind"}
        }
        expected = {
            **projected,
            "schema_version": 2,
            "artifact_kind": "authority_verification",
        }
        if set(verification) != VERIFICATION_KEYS or verification != expected:
            fields = sorted(
                key
                for key in VERIFICATION_KEYS
                if verification.get(key) != expected.get(key)
            )
            findings.append(
                {
                    "code": "authority_owner_verification_mismatch",
                    "message": "Pre-dispatch verification artifact does not exactly match the packet echo.",
                    "evidence": {"fields": fields},
                }
            )


def verify_grants(
    root: Path,
    packet: dict[str, Any],
    findings: list[dict[str, Any]],
) -> None:
    selected = (
        packet.get("selected_grants")
        if isinstance(packet.get("selected_grants"), list)
        else []
    )
    lineage = (
        packet.get("lineage_grants")
        if isinstance(packet.get("lineage_grants"), list)
        else []
    )
    uses = (packet.get("reservation_binding") or {}).get("grant_uses") or []
    states = (packet.get("dispatch_preflight") or {}).get("grant_states") or []
    use_map = {str(row.get("grant_id")): row for row in uses if isinstance(row, dict)}
    verification_map = {
        str(row.get("grant_id")): row for row in states if isinstance(row, dict)
    }
    mutating = (packet.get("operation_binding") or {}).get(
        "mutation_class"
    ) != "observe"
    allowed = (packet.get("decision_binding") or {}).get("decision") == "allowed"
    for row in [*selected, *lineage]:
        if not isinstance(row, dict):
            continue
        grant_id = str(row.get("grant_id") or "")
        grant = _read_json(
            root,
            _binding(
                f".task/authorization/grants/{grant_id}.json", row.get("grant_sha256")
            ),
            f"grant:{grant_id}",
            findings,
            expected_ref=f".task/authorization/grants/{grant_id}.json",
        )
        if grant is not None and grant.get("grant_id") != grant_id:
            findings.append(
                _finding(
                    "authority_owner_grant_mismatch",
                    "Grant artifact identity does not match its binding.",
                    f"grant:{grant_id}",
                )
            )
        if grant is not None and grant.get("policy_snapshot") != row.get(
            "policy_snapshot"
        ):
            findings.append(
                _finding(
                    "authority_owner_grant_mismatch",
                    "Grant policy snapshot does not match the decision binding.",
                    f"grant:{grant_id}",
                )
            )
        _read_bytes(
            root, row.get("policy_snapshot"), f"policy_snapshot:{grant_id}", findings
        )
        state_ref = f".task/authorization/state/grants/{grant_id}.json"
        path, reason = _safe_path(root, state_ref, state_ref)
        if path is None:
            findings.append(
                _finding(
                    "authority_artifact_path_unsafe",
                    "Grant state must be an exact non-symlink regular file.",
                    f"grant_state:{grant_id}",
                    reason,
                )
            )
            continue
        try:
            state = json.loads(path.read_bytes())
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            findings.append(
                _finding(
                    "authority_artifact_json_invalid",
                    "Grant state could not be reopened as JSON.",
                    f"grant_state:{grant_id}",
                )
            )
            continue
        expected_version = row.get("state_version")
        if allowed and mutating and grant_id in use_map:
            expected_version = use_map[grant_id].get("state_version_after")
        verification = verification_map.get(grant_id)
        mismatch = (
            not isinstance(state, dict)
            or state.get("grant_sha256") != row.get("grant_sha256")
            or state.get("status") != "active"
            or state.get("version") != expected_version
        )
        if verification is not None:
            mismatch = mismatch or any(
                state.get(key) != verification.get(target)
                for key, target in (
                    ("version", "state_version"),
                    ("status", "status"),
                    ("remaining_uses", "remaining_uses"),
                    ("reserved_uses", "reserved_uses"),
                )
            )
        if mismatch:
            findings.append(
                _finding(
                    "authority_owner_grant_state_mismatch",
                    "Current grant state no longer matches the selected/lineage binding and verification.",
                    f"grant_state:{grant_id}",
                )
            )


__all__ = ("verify_grants", "verify_reservation")
