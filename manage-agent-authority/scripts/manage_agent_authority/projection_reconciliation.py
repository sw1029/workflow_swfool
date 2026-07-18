from __future__ import annotations

from pathlib import Path
from typing import Any

from .canonical import object_sha256, parse_time
from .execution_results import validate_pre_commit_verification
from .projection_contracts import AUTHORIZATION_ROOT
from .projection_contracts import RECONCILIATION_RECEIPT_KEYS
from .projection_contracts import STATE_ROOT
from .projection_contracts import closed, identifier
from .projection_contracts import sha
from .projection_io import changes_by_ref, expected_path, intent_changes
from .projection_io import load_grant_artifact, validate_grant_state
from .projection_io import validate_reservation_state, verify_file_binding
from .projection_io import load_bound_json
from .projection_reservations import load_bound_reservation


RECONCILIATION_EVIDENCE_KEYS = {
    "schema_version",
    "artifact_kind",
    "evidence_id",
    "reservation",
    "operation",
    "subject_before",
    "observed_subject",
    "outcome",
    "owner_result",
    "observed_at",
}


def validate_reconciliation_evidence(
    root: Path,
    binding_value: dict[str, str],
    reservation: dict[str, Any],
    reservation_binding: dict[str, str],
    outcome: str,
    *,
    require_current_subject: bool,
) -> dict[str, Any]:
    evidence, path, normalized = load_bound_json(
        root, binding_value, "effect reconciliation evidence"
    )
    evidence = closed(
        evidence, RECONCILIATION_EVIDENCE_KEYS, "effect reconciliation evidence"
    )
    if (
        evidence["schema_version"] != 2
        or evidence["artifact_kind"] != "authority_effect_reconciliation_evidence"
    ):
        raise SystemExit("Effect reconciliation evidence type is invalid.")
    core = {key: value for key, value in evidence.items() if key != "evidence_id"}
    expected_id = f"authe-{object_sha256(core)[:24]}"
    expected_ref = (
        AUTHORIZATION_ROOT / "reconciliation_evidence" / f"{expected_id}.json"
    ).as_posix()
    if (
        evidence["evidence_id"] != expected_id
        or normalized["ref"] != expected_ref
        or evidence["reservation"] != reservation_binding
        or evidence["outcome"] != outcome
    ):
        raise SystemExit("Effect reconciliation evidence identity or scope is invalid.")
    decision, _, _ = load_bound_json(
        root, reservation["decision"], "reconciliation evidence decision"
    )
    request = decision.get("request") or {}
    expected_operation = {
        key: request.get(key)
        for key in ("skill_id", "skill_version", "operation_id", "operation_version")
    }
    if (
        evidence["operation"] != expected_operation
        or evidence["subject_before"] != request.get("subject")
    ):
        raise SystemExit("Effect reconciliation evidence operation binding is invalid.")
    observed = evidence["observed_subject"]
    if (
        not isinstance(observed, dict)
        or set(observed) != {"ref", "sha256"}
        or observed.get("ref") != request.get("subject", {}).get("ref")
        or sha(observed.get("sha256"), "observed_subject.sha256")
        != observed.get("sha256")
    ):
        raise SystemExit("Effect reconciliation observed subject is invalid.")
    if outcome == "confirmed_no_effect" and observed["sha256"] != request["subject"]["digest"]:
        raise SystemExit("No-effect evidence does not preserve the exact subject digest.")
    if require_current_subject:
        _, observed_path = verify_file_binding(
            root,
            {"ref": observed["ref"], "sha256": observed["sha256"]},
            "observed reconciliation subject",
        )
        if observed_path != (root.resolve() / observed["ref"]).resolve():
            raise SystemExit("Observed reconciliation subject path is invalid.")
    owner_result = evidence["owner_result"]
    if outcome in {"confirmed_effect", "confirmed_no_effect"}:
        if owner_result is None:
            raise SystemExit("Settled reconciliation requires a typed owner result.")
        owner, _, _ = load_bound_json(root, owner_result, "reconciliation owner result")
        if (
            not isinstance(owner.get("schema_version"), int)
            or not isinstance(owner.get("artifact_kind"), str)
            or not owner["artifact_kind"]
        ):
            raise SystemExit("Reconciliation owner result is not typed.")
    elif owner_result is not None:
        raise SystemExit("Still-unknown evidence must not claim an owner result.")
    parse_time(evidence["observed_at"], "reconciliation evidence.observed_at")
    return evidence


def validate_reconciliation_receipt(
    root: Path, artifact: dict[str, Any], path: Path
) -> list[dict[str, Any]]:
    receipt = closed(
        artifact, RECONCILIATION_RECEIPT_KEYS, "authority reconciliation receipt"
    )
    if (
        receipt["schema_version"] != 2
        or receipt["artifact_kind"] != "authority_reconciliation_receipt"
    ):
        raise SystemExit("Authority reconciliation receipt contract is invalid.")
    receipt_id = identifier(receipt["receipt_id"], "reconciliation receipt ID")
    expected_path(
        root,
        path,
        AUTHORIZATION_ROOT / "reconciliation_receipts" / f"{receipt_id}.json",
        "authority reconciliation receipt",
    )
    reservation, uses, reservation_binding = load_bound_reservation(
        root, receipt["reservation"], "reconciliation receipt.reservation"
    )
    key = identifier(receipt["idempotency_key"], "reconciliation idempotency_key")
    expected_id = (
        "authq-"
        + object_sha256({"reservation": reservation_binding["sha256"], "key": key})[
            :24
        ]
    )
    if receipt_id != expected_id:
        raise SystemExit("Authority reconciliation receipt ID is not deterministic.")
    outcome = receipt["outcome"]
    if outcome not in {"confirmed_effect", "confirmed_no_effect", "still_unknown"}:
        raise SystemExit("Authority reconciliation outcome is invalid.")
    validate_reconciliation_evidence(
        root,
        receipt["effect_evidence"],
        reservation,
        reservation_binding,
        outcome,
        require_current_subject=False,
    )
    if outcome == "confirmed_effect":
        if receipt["pre_commit_verification"] is None:
            raise SystemExit("Confirmed effect reconciliation requires pre_commit verification.")
        validate_pre_commit_verification(
            root,
            reservation,
            reservation_binding,
            receipt["pre_commit_verification"],
            expected_version=0,
            require_current_state=False,
        )
    elif receipt["pre_commit_verification"] is not None:
        raise SystemExit("Non-effect reconciliation must not bind pre_commit verification.")
    parse_time(receipt["reconciled_at"], "reconciliation.reconciled_at")
    versions = receipt["grant_versions_after"]
    expected_version_ids = {use["grant_id"] for use in uses} if outcome != "still_unknown" else set()
    if not isinstance(versions, dict) or set(versions) != expected_version_ids:
        raise SystemExit("Reconciliation grant_versions_after is invalid.")
    changes = intent_changes(root, receipt, path)
    by_ref = changes_by_ref(changes)
    expected_refs: set[str] = set()
    if outcome != "still_unknown":
        for use in uses:
            grant, digest = load_grant_artifact(root, use["grant_id"])
            ref = (STATE_ROOT / "grants" / f"{use['grant_id']}.json").as_posix()
            expected_refs.add(ref)
            change = by_ref.get(ref)
            if change is None or change["before"] is None:
                raise SystemExit("Reconciliation is missing an exact grant change.")
            before = validate_grant_state(
                change["before"], grant, digest, "reconciliation grant before"
            )
            after = validate_grant_state(
                change["after"], grant, digest, "reconciliation grant after"
            )
            if before["status"] != "active" or before["reserved_uses"] < use["units"]:
                raise SystemExit("Reconciliation grant does not retain reserved units.")
            expected_after = {
                **before,
                "reserved_uses": before["reserved_uses"] - use["units"],
                "version": before["version"] + 1,
                "last_event_id": receipt_id,
            }
            if outcome == "confirmed_effect":
                remaining = before["remaining_uses"]
                new_remaining = remaining - use["units"] if remaining is not None else None
                expected_after.update(
                    {
                        "remaining_uses": new_remaining,
                        "consumed_uses": before["consumed_uses"] + use["units"],
                        "status": "exhausted" if new_remaining == 0 else "active",
                    }
                )
            if after != expected_after or versions[use["grant_id"]] != after["version"]:
                raise SystemExit("Reconciliation grant transition is forged.")
    reservation_ref = (
        STATE_ROOT / "reservations" / f"{reservation['reservation_id']}.json"
    ).as_posix()
    expected_refs.add(reservation_ref)
    change = by_ref.get(reservation_ref)
    if change is None or change["before"] is None:
        raise SystemExit("Reconciliation is missing its reservation change.")
    before_state = validate_reservation_state(
        change["before"], reservation["reservation_id"], "reconciliation before"
    )
    after_state = validate_reservation_state(
        change["after"], reservation["reservation_id"], "reconciliation after"
    )
    next_status = {
        "confirmed_effect": "consumed",
        "confirmed_no_effect": "released",
        "still_unknown": "quarantined_unknown_effect",
    }[outcome]
    if (
        before_state["status"] != "quarantined_unknown_effect"
        or after_state
        != {
            **before_state,
            "status": next_status,
            "version": before_state["version"] + 1,
            "last_event_id": receipt_id,
        }
        or set(by_ref) != expected_refs
    ):
        raise SystemExit("Reconciliation reservation transition is forged or unknown.")
    return changes
