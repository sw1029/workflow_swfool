from __future__ import annotations

from pathlib import Path
from typing import Any

from .artifact_store import AUTHORIZATION_ROOT, load_grant, state_path
from .canonical import authority_lock, object_sha256, parse_time
from .canonical import sha256_file, write_immutable_json
from .execution_results import validate_pre_commit_verification
from .lifecycle import load_reservation
from .projection_reconciliation import validate_reconciliation_evidence
from .projection_recovery import apply_projection_changes, projection_change
from .projection_recovery import recover_projection_intents, validated_settled_intent


def _binding(root: Path, path: Path) -> dict[str, str]:
    return {"ref": path.relative_to(root).as_posix(), "sha256": sha256_file(path)}


def _reservation_state_path(root: Path, reservation_id: str) -> Path:
    return (
        root
        / AUTHORIZATION_ROOT
        / "state"
        / "reservations"
        / f"{reservation_id}.json"
    )


def _settle_grants(
    root: Path,
    reservation: dict[str, Any],
    outcome: str,
    receipt_id: str,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    changes: list[dict[str, Any]] = []
    versions: dict[str, int] = {}
    if outcome == "still_unknown":
        return changes, versions
    for use in reservation["grant_uses"]:
        _, _, state = load_grant(root, use["grant_id"])
        if state["status"] != "active" or state["reserved_uses"] < use["units"]:
            raise SystemExit(
                "Quarantined reservation no longer retains its grant units."
            )
        updated = {
            **state,
            "reserved_uses": state["reserved_uses"] - use["units"],
            "version": state["version"] + 1,
            "last_event_id": receipt_id,
        }
        if outcome == "confirmed_effect":
            remaining = state["remaining_uses"]
            next_remaining = remaining - use["units"] if remaining is not None else None
            if next_remaining is not None and next_remaining < 0:
                raise SystemExit(
                    "Confirmed effect reconciliation exceeds remaining budget."
                )
            updated.update(
                {
                    "remaining_uses": next_remaining,
                    "consumed_uses": state["consumed_uses"] + use["units"],
                    "status": "exhausted" if next_remaining == 0 else "active",
                }
            )
        versions[use["grant_id"]] = updated["version"]
        changes.append(
            projection_change(root, state_path(root, use["grant_id"]), state, updated)
        )
    return changes, versions


def reconcile_quarantine(
    root: Path,
    reservation_ref: str,
    reservation_sha256: str,
    effect_evidence: dict[str, str],
    *,
    outcome: str,
    pre_commit_verification: dict[str, str] | None,
    reconciled_at: str,
    expected_version: int,
    idempotency_key: str,
) -> dict[str, Any]:
    if outcome not in {"confirmed_effect", "confirmed_no_effect", "still_unknown"}:
        raise SystemExit("Reconciliation outcome is invalid.")
    root = root.resolve()
    receipt_id = f"authq-{object_sha256({'reservation': reservation_sha256, 'key': idempotency_key})[:24]}"
    receipt_path = root / AUTHORIZATION_ROOT / "reconciliation_receipts" / f"{receipt_id}.json"
    with authority_lock(root):
        recover_projection_intents(root)
        reservation, reservation_path, state = load_reservation(
            root, reservation_ref, reservation_sha256
        )
        if receipt_path.exists():
            receipt = validated_settled_intent(root, receipt_path)
            expected = {
                "outcome": outcome,
                "effect_evidence": effect_evidence,
                "pre_commit_verification": pre_commit_verification,
                "idempotency_key": idempotency_key,
            }
            if any(receipt.get(key) != value for key, value in expected.items()):
                raise SystemExit("Reconciliation idempotency conflict.")
            return {
                "reconciliation_receipt": receipt,
                "ref": receipt_path.relative_to(root).as_posix(),
                "sha256": sha256_file(receipt_path),
            }
        if state.get("status") != "quarantined_unknown_effect" or state.get(
            "version"
        ) != expected_version:
            raise SystemExit("Reservation is not in the expected quarantined CAS state.")
        reservation_binding = _binding(root, reservation_path)
        validate_reconciliation_evidence(
            root,
            effect_evidence,
            reservation,
            reservation_binding,
            outcome,
            require_current_subject=True,
        )
        if outcome == "confirmed_effect":
            if pre_commit_verification is None:
                raise SystemExit(
                    "Confirmed effect reconciliation requires pre_commit verification."
                )
            validate_pre_commit_verification(
                root,
                reservation,
                reservation_binding,
                pre_commit_verification,
                expected_version=0,
                require_current_state=False,
            )
        elif pre_commit_verification is not None:
            raise SystemExit(
                "Non-effect reconciliation must not bind pre_commit verification."
            )
        changes, versions = _settle_grants(
            root, reservation, outcome, receipt_id
        )
        next_status = {
            "confirmed_effect": "consumed",
            "confirmed_no_effect": "released",
            "still_unknown": "quarantined_unknown_effect",
        }[outcome]
        reservation_after = {
            **state,
            "status": next_status,
            "version": state["version"] + 1,
            "last_event_id": receipt_id,
        }
        changes.append(
            projection_change(
                root,
                _reservation_state_path(root, reservation["reservation_id"]),
                state,
                reservation_after,
            )
        )
        receipt = {
            "schema_version": 2,
            "artifact_kind": "authority_reconciliation_receipt",
            "receipt_id": receipt_id,
            "reservation": reservation_binding,
            "effect_evidence": effect_evidence,
            "pre_commit_verification": pre_commit_verification,
            "outcome": outcome,
            "reconciled_at": parse_time(reconciled_at, "reconciled_at").isoformat(),
            "grant_versions_after": versions,
            "idempotency_key": idempotency_key,
            "state_changes": changes,
        }
        write_immutable_json(receipt_path, receipt, "authority reconciliation receipt")
        apply_projection_changes(root, changes)
    return {
        "reconciliation_receipt": receipt,
        "ref": receipt_path.relative_to(root).as_posix(),
        "sha256": sha256_file(receipt_path),
    }
