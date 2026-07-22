from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .canonical import object_sha256
from .canonical import parse_time
from .canonical import resolve_workspace_path
from .execution_results import validate_execution_result
from .execution_results import validate_pre_commit_verification
from .projection_contracts import AUTHORIZATION_ROOT
from .projection_contracts import MAX_INTENT_BYTES
from .projection_contracts import RELEASE_RECEIPT_KEYS
from .projection_contracts import STATE_ROOT
from .projection_contracts import USE_RECEIPT_KEYS
from .projection_contracts import TYPED_USE_RECEIPT_KEYS
from .projection_contracts import closed
from .projection_contracts import identifier
from .projection_io import changes_by_ref
from .projection_io import expected_path
from .projection_io import intent_changes
from .projection_io import load_bound_json
from .projection_io import load_grant_artifact
from .projection_io import read_bound_bytes
from .projection_io import safe_json
from .projection_io import validate_grant_state
from .projection_io import validate_reservation_state
from .projection_io import verify_file_binding
from .projection_reservations import load_bound_reservation


def _validate_registered_release_evidence(
    root: Path,
    receipt: dict[str, Any],
    reservation: dict[str, Any],
    reservation_binding: dict[str, str],
    *,
    expected_version: int,
    skills_root: Path | None,
    allow_settled_registered_legacy: bool,
) -> bool:
    from .registered_release import registered_release_required
    from .registered_release import validate_registered_release

    if not registered_release_required(root, reservation):
        return False
    evidence_binding = receipt["no_effect_evidence"]
    evidence_ref = evidence_binding.get("ref")
    _, _, evidence_payload = read_bound_bytes(
        root,
        evidence_binding,
        "release receipt.no_effect_evidence",
        max_bytes=MAX_INTENT_BYTES,
    )
    claims_owner_validation = str(evidence_ref).startswith(
        ".task/authorization/owner_validations/owner-validation-"
    )
    try:
        evidence = json.loads(evidence_payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        evidence = None
    if isinstance(evidence, dict) and evidence.get(
        "artifact_kind"
    ) == "owner_validation_receipt":
        claims_owner_validation = True
    if allow_settled_registered_legacy and not claims_owner_validation:
        return True
    validate_registered_release(
        root,
        reservation,
        reservation_binding,
        receipt["no_effect_evidence"],
        receipt["effect_status"],
        expected_version,
        skills_root,
        require_current_state=False,
    )
    return False


def _require_exact_terminal_projection(
    root: Path, changes: list[dict[str, Any]], label: str
) -> None:
    """Keep historical schema-v2 compatibility strictly read-only."""

    for change in changes:
        path = resolve_workspace_path(
            root,
            change["ref"],
            f"{label} terminal projection",
            must_exist=False,
        )
        if not path.is_file():
            raise SystemExit(f"{label} is not already settled at its exact after-state.")
        current, _ = safe_json(root, path, f"{label} terminal projection")
        if current != change["after"]:
            raise SystemExit(f"{label} is not already settled at its exact after-state.")


def _validate_typed_use_receipt(
    root: Path,
    receipt: dict[str, Any],
    reservation: dict[str, Any],
    reservation_binding: dict[str, str],
    *,
    skills_root: Path | None,
    allow_settled_registered_legacy: bool,
) -> bool:
    from .registered_release import registered_release_required
    from .registered_release import validate_registered_owner_receipt

    decision, _, _ = load_bound_json(
        root, reservation["decision"], "use receipt.decision"
    )
    validate_pre_commit_verification(
        root,
        reservation,
        reservation_binding,
        receipt["pre_commit_verification"],
        expected_version=0,
        require_current_state=False,
    )
    result = validate_execution_result(
        root,
        receipt["execution_result"],
        reservation,
        reservation_binding,
        receipt["pre_commit_verification"],
        decision["request"]["subject"],
    )
    if result["owner_result"] != receipt["owner_execution_result"]:
        raise SystemExit("Authority use receipt owner result binding is invalid.")
    request = decision.get("request")
    if not isinstance(request, dict):
        raise SystemExit("Authority use receipt request is invalid.")
    if not registered_release_required(root, reservation):
        if result.get("schema_version") != 2:
            raise SystemExit(
                "Unregistered owner use receipts cannot claim schema-v3 settlement."
            )
        return False
    if result.get("schema_version") != 3:
        if allow_settled_registered_legacy and result.get("schema_version") == 2:
            return True
        raise SystemExit(
            "Registered owner use receipts require schema-v3 settlement evidence."
        )
    owner_validation = result.get("owner_validation")
    if not isinstance(owner_validation, dict):
        raise SystemExit("Registered owner use receipt lacks owner validation.")
    validate_registered_owner_receipt(
        root,
        reservation,
        reservation_binding,
        owner_validation,
        expected_version=0,
        require_current_state=False,
        skills_root=skills_root,
        expected_outcomes={"confirmed_effect"},
        owner_result=receipt["owner_execution_result"],
        pre_commit_verification=receipt["pre_commit_verification"],
    )
    return False


def _validate_use_settlement_evidence(
    root: Path,
    receipt: dict[str, Any],
    reservation: dict[str, Any],
    reservation_binding: dict[str, str],
    *,
    typed: bool,
    skills_root: Path | None,
    allow_settled_registered_legacy: bool,
) -> bool:
    if typed:
        return _validate_typed_use_receipt(
            root,
            receipt,
            reservation,
            reservation_binding,
            skills_root=skills_root,
            allow_settled_registered_legacy=allow_settled_registered_legacy,
        )
    from .registered_release import registered_release_required

    registered_legacy = registered_release_required(root, reservation)
    if registered_legacy and not allow_settled_registered_legacy:
        raise SystemExit(
            "Registered owner use receipts require typed schema-v3 settlement evidence."
        )
    # Preserve validation of immutable receipts issued before typed settlement.
    verify_file_binding(
        root, receipt["execution_result"], "use receipt.execution_result"
    )
    return registered_legacy


def validate_use_receipt(
    root: Path,
    artifact: dict[str, Any],
    path: Path,
    *,
    skills_root: Path | None = None,
    allow_settled_registered_legacy: bool = False,
) -> list[dict[str, Any]]:
    typed = set(artifact) == TYPED_USE_RECEIPT_KEYS
    receipt = closed(
        artifact,
        TYPED_USE_RECEIPT_KEYS if typed else USE_RECEIPT_KEYS,
        "authority use receipt",
    )
    if (
        receipt["schema_version"] != 2
        or receipt["artifact_kind"] != "authority_use_receipt"
    ):
        raise SystemExit("Authority use receipt contract is invalid.")
    receipt_id = identifier(receipt["receipt_id"], "use receipt ID")
    expected_path(
        root,
        path,
        AUTHORIZATION_ROOT / "use_receipts" / f"{receipt_id}.json",
        "authority use receipt",
    )
    reservation, uses, reservation_binding = load_bound_reservation(
        root, receipt["reservation"], "use receipt.reservation"
    )
    key = identifier(receipt["idempotency_key"], "use receipt.idempotency_key")
    expected_id = (
        "authu-"
        + object_sha256({"reservation": reservation_binding["sha256"], "key": key})[:24]
    )
    if receipt_id != expected_id:
        raise SystemExit(
            "Authority use receipt ID is not deterministic for its binding."
        )
    registered_legacy = _validate_use_settlement_evidence(
        root,
        receipt,
        reservation,
        reservation_binding,
        typed=typed,
        skills_root=skills_root,
        allow_settled_registered_legacy=allow_settled_registered_legacy,
    )
    parse_time(receipt["consumed_at"], "use receipt.consumed_at")
    versions = receipt["grant_versions_after"]
    if not isinstance(versions, dict) or set(versions) != {
        use["grant_id"] for use in uses
    }:
        raise SystemExit("Authority use receipt grant_versions_after is invalid.")
    changes = intent_changes(root, receipt, path)
    by_ref = changes_by_ref(changes)
    expected_refs: set[str] = set()
    for use in uses:
        grant, digest = load_grant_artifact(root, use["grant_id"])
        ref = (STATE_ROOT / "grants" / f"{use['grant_id']}.json").as_posix()
        expected_refs.add(ref)
        change = by_ref.get(ref)
        if change is None or change["before"] is None:
            raise SystemExit("Authority use receipt is missing an exact grant change.")
        before = validate_grant_state(
            change["before"], grant, digest, f"use receipt {receipt_id} before"
        )
        after = validate_grant_state(
            change["after"], grant, digest, f"use receipt {receipt_id} after"
        )
        remaining = before["remaining_uses"]
        new_remaining = remaining - use["units"] if remaining is not None else None
        if before["reserved_uses"] < use["units"] or (
            remaining is not None and remaining < use["units"]
        ):
            raise SystemExit("Authority use receipt spends unavailable grant units.")
        expected_after = {
            **before,
            "remaining_uses": new_remaining,
            "reserved_uses": before["reserved_uses"] - use["units"],
            "consumed_uses": before["consumed_uses"] + use["units"],
            "status": "exhausted" if new_remaining == 0 else "active",
            "version": before["version"] + 1,
            "last_event_id": receipt_id,
        }
        if (
            before["status"] != "active"
            or after != expected_after
            or versions[use["grant_id"]] != after["version"]
        ):
            raise SystemExit("Authority use receipt grant transition is forged.")
    reservation_ref = (
        STATE_ROOT / "reservations" / f"{reservation['reservation_id']}.json"
    ).as_posix()
    expected_refs.add(reservation_ref)
    change = by_ref.get(reservation_ref)
    if change is None or change["before"] is None:
        raise SystemExit("Authority use receipt is missing its reservation change.")
    before_state = validate_reservation_state(
        change["before"],
        reservation["reservation_id"],
        "use receipt reservation before",
    )
    after_state = validate_reservation_state(
        change["after"], reservation["reservation_id"], "use receipt reservation after"
    )
    expected_before = {
        "schema_version": 2,
        "artifact_kind": "authority_reservation_state",
        "reservation_id": reservation["reservation_id"],
        "status": "reserved",
        "version": 0,
        "last_event_id": reservation["reservation_id"],
    }
    if (
        before_state != expected_before
        or after_state
        != {
            **before_state,
            "status": "consumed",
            "version": 1,
            "last_event_id": receipt_id,
        }
        or set(by_ref) != expected_refs
    ):
        raise SystemExit(
            "Authority use receipt reservation transition is forged or unknown."
        )
    if registered_legacy:
        _require_exact_terminal_projection(
            root, changes, "Historical registered schema-v2 use receipt"
        )
    return changes


def validate_release_receipt(
    root: Path,
    artifact: dict[str, Any],
    path: Path,
    *,
    skills_root: Path | None = None,
    allow_settled_registered_legacy: bool = False,
) -> list[dict[str, Any]]:
    receipt = closed(artifact, RELEASE_RECEIPT_KEYS, "authority release receipt")
    if (
        receipt["schema_version"] != 2
        or receipt["artifact_kind"] != "authority_release_receipt"
    ):
        raise SystemExit("Authority release receipt contract is invalid.")
    receipt_id = identifier(receipt["receipt_id"], "release receipt ID")
    expected_path(
        root,
        path,
        AUTHORIZATION_ROOT / "release_receipts" / f"{receipt_id}.json",
        "authority release receipt",
    )
    reservation, uses, reservation_binding = load_bound_reservation(
        root, receipt["reservation"], "release receipt.reservation"
    )
    key = identifier(receipt["idempotency_key"], "release receipt.idempotency_key")
    expected_id = (
        "authx-"
        + object_sha256({"reservation": reservation_binding["sha256"], "key": key})[:24]
    )
    if receipt_id != expected_id:
        raise SystemExit(
            "Authority release receipt ID is not deterministic for its binding."
        )
    from .registered_release import registered_release_required

    if not registered_release_required(root, reservation):
        verify_file_binding(
            root, receipt["no_effect_evidence"], "release receipt.no_effect_evidence"
        )
    parse_time(receipt["released_at"], "release receipt.released_at")
    if receipt["effect_status"] not in {
        "not_started",
        "verified_no_effect",
        "unknown_effect",
    }:
        raise SystemExit("Authority release receipt effect_status is invalid.")
    released = receipt["effect_status"] != "unknown_effect"
    if (
        not isinstance(receipt["release_applied"], bool)
        or receipt["release_applied"] != released
    ):
        raise SystemExit("Authority release receipt release_applied is invalid.")
    changes = intent_changes(root, receipt, path)
    by_ref = changes_by_ref(changes)
    expected_refs: set[str] = set()
    if released:
        for use in uses:
            grant, digest = load_grant_artifact(root, use["grant_id"])
            ref = (STATE_ROOT / "grants" / f"{use['grant_id']}.json").as_posix()
            expected_refs.add(ref)
            change = by_ref.get(ref)
            if change is None or change["before"] is None:
                raise SystemExit(
                    "Authority release receipt is missing an exact grant change."
                )
            before = validate_grant_state(
                change["before"], grant, digest, f"release receipt {receipt_id} before"
            )
            after = validate_grant_state(
                change["after"], grant, digest, f"release receipt {receipt_id} after"
            )
            if before["reserved_uses"] < use["units"]:
                raise SystemExit(
                    "Authority release receipt releases unavailable units."
                )
            expected_after = {
                **before,
                "reserved_uses": before["reserved_uses"] - use["units"],
                "version": before["version"] + 1,
                "last_event_id": receipt_id,
            }
            if before["status"] != "active" or after != expected_after:
                raise SystemExit(
                    "Authority release receipt grant transition is forged."
                )
    reservation_ref = (
        STATE_ROOT / "reservations" / f"{reservation['reservation_id']}.json"
    ).as_posix()
    expected_refs.add(reservation_ref)
    change = by_ref.get(reservation_ref)
    if change is None or change["before"] is None:
        raise SystemExit("Authority release receipt is missing its reservation change.")
    before_state = validate_reservation_state(
        change["before"],
        reservation["reservation_id"],
        "release receipt reservation before",
    )
    after_state = validate_reservation_state(
        change["after"],
        reservation["reservation_id"],
        "release receipt reservation after",
    )
    expected_before = {
        "schema_version": 2,
        "artifact_kind": "authority_reservation_state",
        "reservation_id": reservation["reservation_id"],
        "status": "reserved",
        "version": 0,
        "last_event_id": reservation["reservation_id"],
    }
    next_status = "released" if released else "quarantined_unknown_effect"
    if (
        before_state != expected_before
        or after_state
        != {
            **before_state,
            "status": next_status,
            "version": 1,
            "last_event_id": receipt_id,
        }
        or set(by_ref) != expected_refs
    ):
        raise SystemExit(
            "Authority release receipt reservation transition is forged or unknown."
        )
    registered_legacy = _validate_registered_release_evidence(
        root,
        receipt,
        reservation,
        reservation_binding,
        expected_version=before_state["version"],
        skills_root=skills_root,
        allow_settled_registered_legacy=allow_settled_registered_legacy,
    )
    if registered_legacy:
        _require_exact_terminal_projection(
            root, changes, "Historical registered schema-v2 release receipt"
        )
    return changes
