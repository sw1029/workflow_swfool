"""Deterministic CAS transition checks for authority use receipts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ._authority_artifact_io import (
    artifact_finding as _finding,
    safe_authority_path as _safe_path,
)
from ._authority_settlement_contracts import (
    RESERVATION_STATE_KEYS,
    expected_grant_after,
    is_positive_int,
    valid_grant_state,
)


def validate_receipt_state_changes(
    root: Path,
    packet: dict[str, Any],
    receipt: dict[str, Any],
    reservation_artifact: dict[str, Any] | None,
    receipt_id: str,
    phase: str,
    findings: list[dict[str, Any]],
) -> None:
    """Check reservation and consume deltas, plus activation-time CAS state."""

    maps = _packet_maps(packet)
    if maps is None:
        findings.append(_invalid_packet_finding())
        return
    use_map, preflight_map = maps
    changes = receipt["state_changes"]
    change_map = _unique_ref_map(changes)
    reservation_changes = (
        reservation_artifact.get("state_changes")
        if isinstance(reservation_artifact, dict)
        and isinstance(reservation_artifact.get("state_changes"), list)
        else []
    )
    reserve_map = _unique_ref_map(reservation_changes)
    reservation = packet["reservation_binding"]
    reservation_id = str(reservation.get("reservation_id") or "")
    expected_refs = {
        f".task/authorization/state/grants/{grant_id}.json" for grant_id in use_map
    }
    reservation_ref = f".task/authorization/state/reservations/{reservation_id}.json"
    expected_refs.add(reservation_ref)
    invalid = _map_shapes_invalid(
        changes, change_map, reservation_changes, reserve_map, expected_refs
    )
    expected_versions, grants_invalid = _validate_grant_changes(
        root,
        use_map,
        preflight_map,
        change_map,
        reserve_map,
        reservation_id,
        receipt_id,
        phase,
        findings,
    )
    reservation_invalid = _validate_reservation_change(
        root,
        reservation,
        reservation_ref,
        change_map.get(reservation_ref),
        reserve_map.get(reservation_ref),
        receipt_id,
        phase,
        findings,
    )
    invalid = bool(
        invalid
        or grants_invalid
        or reservation_invalid
        or receipt.get("grant_versions_after") != expected_versions
    )
    if invalid:
        findings.append(
            _finding(
                "authority_use_receipt_state_changes_invalid",
                "Use receipt state changes do not encode the exact deterministic consumption deltas.",
                "use_receipt",
            )
        )


def _packet_maps(
    packet: dict[str, Any],
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]] | None:
    uses = packet["reservation_binding"].get("grant_uses")
    states = packet["dispatch_preflight"].get("grant_states")
    if not isinstance(uses, list) or not isinstance(states, list):
        return None
    use_map = {
        str(row.get("grant_id")): row
        for row in uses
        if isinstance(row, dict) and isinstance(row.get("grant_id"), str)
    }
    state_map = {
        str(row.get("grant_id")): row
        for row in states
        if isinstance(row, dict) and isinstance(row.get("grant_id"), str)
    }
    if (
        len(use_map) != len(uses)
        or len(state_map) != len(states)
        or set(use_map) != set(state_map)
    ):
        return None
    return use_map, state_map


def _unique_ref_map(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        str(row.get("ref")): row
        for row in rows
        if isinstance(row, dict) and isinstance(row.get("ref"), str)
    }


def _map_shapes_invalid(
    changes: list[dict[str, Any]],
    change_map: dict[str, dict[str, Any]],
    reservation_changes: list[dict[str, Any]],
    reserve_map: dict[str, dict[str, Any]],
    expected_refs: set[str],
) -> bool:
    return bool(
        len(changes) != len(expected_refs)
        or len(change_map) != len(changes)
        or set(change_map) != expected_refs
        or len(reservation_changes) != len(expected_refs)
        or len(reserve_map) != len(reservation_changes)
        or set(reserve_map) != expected_refs
    )


def _validate_grant_changes(
    root: Path,
    uses: dict[str, dict[str, Any]],
    states: dict[str, dict[str, Any]],
    changes: dict[str, dict[str, Any]],
    reserve_changes: dict[str, dict[str, Any]],
    reservation_id: str,
    receipt_id: str,
    phase: str,
    findings: list[dict[str, Any]],
) -> tuple[dict[str, int], bool]:
    versions: dict[str, int] = {}
    invalid = False
    for grant_id, use in uses.items():
        ref = f".task/authorization/state/grants/{grant_id}.json"
        version, row_invalid = _validate_grant_change(
            root,
            grant_id,
            use,
            states[grant_id],
            changes.get(ref),
            reserve_changes.get(ref),
            reservation_id,
            receipt_id,
            phase,
            findings,
        )
        invalid = invalid or row_invalid
        if version is not None:
            versions[grant_id] = version
    return versions, invalid


def _validate_grant_change(
    root: Path,
    grant_id: str,
    use: dict[str, Any],
    verified: dict[str, Any],
    change: dict[str, Any] | None,
    reserve_change: dict[str, Any] | None,
    reservation_id: str,
    receipt_id: str,
    phase: str,
    findings: list[dict[str, Any]],
) -> tuple[int | None, bool]:
    units = use.get("units")
    if change is None or reserve_change is None or not is_positive_int(units):
        return None, True
    before = change.get("before")
    after = change.get("after")
    grant_sha = str(use.get("grant_sha256") or "")
    if not valid_grant_state(before, grant_id, grant_sha):
        return None, True
    reserve_before = reserve_change.get("before")
    expected_reserved = _expected_reserved_state(
        reserve_before, grant_id, grant_sha, units, use, reservation_id
    )
    verified_mismatch = any(
        before.get(source) != verified.get(target)
        for source, target in (
            ("grant_sha256", "grant_sha256"),
            ("version", "state_version"),
            ("status", "status"),
            ("remaining_uses", "remaining_uses"),
            ("reserved_uses", "reserved_uses"),
        )
    )
    transition_mismatch = bool(
        reserve_change.get("after") != before
        or expected_reserved != before
        or before.get("version") != use.get("state_version_after")
        or use.get("state_version_after") != use.get("state_version_before") + 1
    )
    expected_after = expected_grant_after(before, units, receipt_id)
    if expected_after is None or after != expected_after:
        return None, True
    if phase == "activation":
        _compare_current_state(
            root,
            f".task/authorization/state/grants/{grant_id}.json",
            expected_after,
            f"grant_state:{grant_id}",
            findings,
        )
    return expected_after["version"], verified_mismatch or transition_mismatch


def _expected_reserved_state(
    before: Any,
    grant_id: str,
    grant_sha: str,
    units: int,
    use: dict[str, Any],
    reservation_id: str,
) -> dict[str, Any] | None:
    if (
        not valid_grant_state(before, grant_id, grant_sha)
        or before.get("status") != "active"
        or before.get("version") != use.get("state_version_before")
    ):
        return None
    return {
        **before,
        "reserved_uses": before["reserved_uses"] + units,
        "version": before["version"] + 1,
        "last_event_id": reservation_id,
    }


def _validate_reservation_change(
    root: Path,
    reservation: dict[str, Any],
    ref: str,
    change: dict[str, Any] | None,
    reserve_change: dict[str, Any] | None,
    receipt_id: str,
    phase: str,
    findings: list[dict[str, Any]],
) -> bool:
    if change is None or reserve_change is None:
        return True
    reservation_id = str(reservation.get("reservation_id") or "")
    before = change.get("before")
    valid_before = bool(
        isinstance(before, dict)
        and set(before) == RESERVATION_STATE_KEYS
        and before.get("schema_version") == 2
        and before.get("artifact_kind") == "authority_reservation_state"
        and before.get("reservation_id") == reservation_id
        and before.get("status") == "reserved"
        and before.get("version") == reservation.get("state_version")
        and before.get("last_event_id") == reservation_id
        and reserve_change.get("before") is None
        and reserve_change.get("after") == before
    )
    expected_after = (
        {
            **before,
            "status": "consumed",
            "version": before["version"] + 1,
            "last_event_id": receipt_id,
        }
        if valid_before
        else None
    )
    if expected_after is None or change.get("after") != expected_after:
        return True
    if phase == "activation":
        _compare_current_state(root, ref, expected_after, "reservation_state", findings)
    return False


def _compare_current_state(
    root: Path,
    ref: str,
    expected: dict[str, Any],
    label: str,
    findings: list[dict[str, Any]],
) -> None:
    current = _read_current_state(root, ref, findings, label)
    if current is not None and current != expected:
        findings.append(
            _finding(
                "authority_settlement_state_mismatch",
                "Current authority projection does not equal the use receipt after image.",
                label,
            )
        )


def _read_current_state(
    root: Path,
    ref: str,
    findings: list[dict[str, Any]],
    label: str,
) -> dict[str, Any] | None:
    path, reason = _safe_path(root, ref, ref)
    if path is None:
        findings.append(
            _finding(
                "authority_settlement_state_unavailable",
                "Settled authority state must remain an exact non-symlink regular file.",
                label,
                reason,
            )
        )
        return None
    try:
        value = json.loads(path.read_bytes())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        findings.append(
            _finding(
                "authority_settlement_state_invalid",
                "Settled authority state is not a readable JSON object.",
                label,
            )
        )
        return None
    if isinstance(value, dict):
        return value
    findings.append(
        _finding(
            "authority_settlement_state_invalid",
            "Settled authority state is not a readable JSON object.",
            label,
        )
    )
    return None


def _invalid_packet_finding() -> dict[str, Any]:
    return _finding(
        "authority_settlement_packet_invalid",
        "Packet reservation uses and verified grant states must form the same unique set.",
        "use_receipt",
    )


__all__ = ("validate_receipt_state_changes",)
