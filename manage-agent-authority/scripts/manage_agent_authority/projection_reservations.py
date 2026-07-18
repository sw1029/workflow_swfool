from __future__ import annotations

from pathlib import Path
from typing import Any

from .canonical import object_sha256
from .canonical import parse_time
from .contracts import validate_request
from .projection_contracts import AUTHORIZATION_ROOT
from .projection_contracts import DECISION_GRANT_KEYS
from .projection_contracts import DECISION_KEYS
from .projection_contracts import RESERVATION_KEYS
from .projection_contracts import STATE_ROOT
from .projection_contracts import closed
from .projection_contracts import identifier
from .projection_contracts import nonnegative_int
from .projection_contracts import sha
from .projection_io import binding
from .projection_io import changes_by_ref
from .projection_io import expected_path
from .projection_io import grant_use
from .projection_io import intent_changes
from .projection_io import load_bound_json
from .projection_io import load_grant_artifact
from .projection_io import validate_grant_state
from .projection_io import verify_file_binding


def _validate_decision(
    root: Path, artifact: dict[str, Any], path: Path
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    decision = closed(artifact, DECISION_KEYS, "authority decision")
    if (
        decision["schema_version"] != 2
        or decision["artifact_kind"] != "authority_decision"
    ):
        raise SystemExit("Authority decision contract is invalid.")
    decision_id = identifier(decision["decision_id"], "decision_id")
    expected_path(
        root,
        path,
        AUTHORIZATION_ROOT / "decisions" / f"{decision_id}.json",
        "authority decision",
    )
    core = {key: value for key, value in decision.items() if key != "decision_id"}
    if decision_id != f"authd-{object_sha256(core)[:24]}":
        raise SystemExit("Authority decision ID is not deterministic for its body.")
    request = validate_request(decision["request"])
    if decision["request_sha256"] != object_sha256(request):
        raise SystemExit("Authority decision request binding is invalid.")
    if not isinstance(decision["evaluation_context"], dict) or decision[
        "evaluation_context_sha256"
    ] != object_sha256(decision["evaluation_context"]):
        raise SystemExit("Authority decision context binding is invalid.")
    if decision["decision"] != "allowed":
        raise SystemExit("A recovery reservation must bind an allowed decision.")
    sha(
        decision["effective_authority_fingerprint"],
        "effective_authority_fingerprint",
    )
    parse_time(decision["evaluated_at"], "evaluated_at")
    bindings: dict[str, dict[str, Any]] = {}
    for field in ("selected_grants", "lineage_grants"):
        items = decision[field]
        if not isinstance(items, list):
            raise SystemExit(f"authority decision.{field} must be a list.")
        for index, item in enumerate(items):
            record = closed(
                item, DECISION_GRANT_KEYS, f"authority decision.{field}[{index}]"
            )
            grant_id = identifier(record["grant_id"], f"{field}[{index}].grant_id")
            sha(record["grant_sha256"], f"{field}[{index}].grant_sha256")
            nonnegative_int(record["state_version"], f"{field}[{index}].state_version")
            verify_file_binding(
                root, record["policy_snapshot"], f"{field}[{index}].policy_snapshot"
            )
            existing = bindings.get(grant_id)
            if existing is not None:
                if existing != record:
                    raise SystemExit(
                        "Authority decision has conflicting grant bindings."
                    )
                raise SystemExit("Authority decision has duplicate grant bindings.")
            bindings[grant_id] = record
    if not bindings:
        raise SystemExit("Allowed authority decision has no grant bindings.")
    return request, bindings


def validate_reservation(
    root: Path, artifact: dict[str, Any], path: Path
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    reservation = closed(artifact, RESERVATION_KEYS, "authority reservation")
    if (
        reservation["schema_version"] != 2
        or reservation["artifact_kind"] != "authority_reservation"
    ):
        raise SystemExit("Authority reservation contract is invalid.")
    reservation_id = identifier(reservation["reservation_id"], "reservation_id")
    expected_path(
        root,
        path,
        AUTHORIZATION_ROOT / "reservations" / f"{reservation_id}.json",
        "authority reservation",
    )
    idempotency_key = identifier(
        reservation["idempotency_key"], "reservation.idempotency_key"
    )
    decision_binding = binding(reservation["decision"], "reservation.decision")
    decision, decision_path, _ = load_bound_json(
        root, decision_binding, "reservation.decision"
    )
    request, decision_grants = _validate_decision(root, decision, decision_path)
    expected_id = (
        "authz-"
        + object_sha256(
            {"request": decision["request_sha256"], "key": idempotency_key}
        )[:24]
    )
    if reservation_id != expected_id:
        raise SystemExit(
            "Authority reservation ID is not deterministic for its binding."
        )
    if (
        reservation["request_id"] != request["request_id"]
        or reservation["request_sha256"] != decision["request_sha256"]
        or reservation["effective_authority_fingerprint"]
        != decision["effective_authority_fingerprint"]
    ):
        raise SystemExit("Authority reservation does not match its decision binding.")
    parse_time(reservation["reserved_at"], "reservation.reserved_at")
    raw_uses = reservation["grant_uses"]
    if not isinstance(raw_uses, list) or not raw_uses:
        raise SystemExit("Authority reservation grant_uses must be non-empty.")
    uses = [
        grant_use(item, f"reservation.grant_uses[{index}]")
        for index, item in enumerate(raw_uses)
    ]
    use_ids = [item["grant_id"] for item in uses]
    if len(set(use_ids)) != len(use_ids):
        raise SystemExit("Authority reservation has duplicate grant uses.")
    if set(use_ids) != set(decision_grants):
        raise SystemExit("Authority reservation grant uses do not match its decision.")
    changes = intent_changes(root, reservation, path)
    by_ref = changes_by_ref(changes)
    expected_refs: set[str] = set()
    for use in uses:
        grant, grant_digest = load_grant_artifact(root, use["grant_id"])
        if grant_digest != use["grant_sha256"]:
            raise SystemExit("Authority reservation grant digest is invalid.")
        decision_grant = decision_grants[use["grant_id"]]
        if (
            decision_grant["grant_sha256"] != grant_digest
            or decision_grant["state_version"] != use["state_version_before"]
            or use["units"] != request["use_budget_requested"]
        ):
            raise SystemExit("Authority reservation grant use is not decision-bound.")
        ref = (STATE_ROOT / "grants" / f"{use['grant_id']}.json").as_posix()
        expected_refs.add(ref)
        change = by_ref.get(ref)
        if change is None or change["before"] is None:
            raise SystemExit("Authority reservation is missing an exact grant change.")
        before = validate_grant_state(
            change["before"],
            grant,
            grant_digest,
            f"reservation {reservation_id} before",
        )
        after = validate_grant_state(
            change["after"], grant, grant_digest, f"reservation {reservation_id} after"
        )
        expected_after = {
            **before,
            "reserved_uses": before["reserved_uses"] + use["units"],
            "version": before["version"] + 1,
            "last_event_id": reservation_id,
        }
        if (
            before["status"] != "active"
            or before["version"] != use["state_version_before"]
            or after != expected_after
            or after["version"] != use["state_version_after"]
        ):
            raise SystemExit("Authority reservation grant transition is forged.")
    reservation_ref = (
        STATE_ROOT / "reservations" / f"{reservation_id}.json"
    ).as_posix()
    expected_refs.add(reservation_ref)
    reservation_change = by_ref.get(reservation_ref)
    expected_state = {
        "schema_version": 2,
        "artifact_kind": "authority_reservation_state",
        "reservation_id": reservation_id,
        "status": "reserved",
        "version": 0,
        "last_event_id": reservation_id,
    }
    if (
        reservation_change is None
        or reservation_change["before"] is not None
        or reservation_change["after"] != expected_state
        or set(by_ref) != expected_refs
    ):
        raise SystemExit("Authority reservation state transition is forged or unknown.")
    return reservation, uses, changes


def load_bound_reservation(
    root: Path, value: Any, label: str
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, str]]:
    normalized = binding(value, label)
    artifact, path, _ = load_bound_json(root, normalized, label)
    reservation, uses, _ = validate_reservation(root, artifact, path)
    expected_ref = (
        AUTHORIZATION_ROOT / "reservations" / f"{reservation['reservation_id']}.json"
    ).as_posix()
    if normalized["ref"] != expected_ref:
        raise SystemExit(
            f"{label} does not identify the deterministic reservation path."
        )
    return reservation, uses, normalized
