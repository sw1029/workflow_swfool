from __future__ import annotations

from pathlib import Path
from typing import Any

from .artifact_store import AUTHORIZATION_ROOT, verify_binding
from .canonical import object_sha256, parse_time, read_object
from .canonical import resolve_workspace_path, sha256_file, write_immutable_json
from .lifecycle import load_reservation
from .projection_reconciliation import validate_reconciliation_evidence


def _typed_owner_result(
    root: Path, binding: dict[str, str] | None, outcome: str
) -> dict[str, str] | None:
    if outcome == "still_unknown":
        if binding is not None:
            raise SystemExit("Still-unknown evidence must not bind an owner result.")
        return None
    if binding is None:
        raise SystemExit("Settled reconciliation evidence requires an owner result.")
    path = verify_binding(root, binding, "reconciliation owner_result")
    artifact = read_object(path, "reconciliation owner result")
    if (
        not isinstance(artifact.get("schema_version"), int)
        or not isinstance(artifact.get("artifact_kind"), str)
        or not artifact["artifact_kind"]
    ):
        raise SystemExit("Reconciliation owner result is not typed.")
    return binding


def prepare_reconciliation_evidence(
    root: Path,
    reservation_ref: str,
    reservation_sha256: str,
    *,
    outcome: str,
    owner_result: dict[str, str] | None,
    observed_at: str,
    expected_version: int,
) -> dict[str, Any]:
    if outcome not in {"confirmed_effect", "confirmed_no_effect", "still_unknown"}:
        raise SystemExit("Reconciliation evidence outcome is invalid.")
    root = root.resolve()
    reservation, reservation_path, state = load_reservation(
        root, reservation_ref, reservation_sha256
    )
    if (
        state.get("status") != "quarantined_unknown_effect"
        or state.get("version") != expected_version
    ):
        raise SystemExit(
            "Reconciliation evidence requires the expected quarantined CAS state."
        )
    normalized_owner = _typed_owner_result(root, owner_result, outcome)
    decision_path = verify_binding(root, reservation["decision"], "reservation decision")
    decision = read_object(decision_path, "reservation decision")
    request = decision.get("request") or {}
    subject = request.get("subject") or {}
    subject_path = resolve_workspace_path(
        root,
        subject.get("ref"),
        "reconciliation observed subject",
        must_exist=True,
        regular_file=True,
    )
    reservation_binding = {
        "ref": reservation_path.relative_to(root).as_posix(),
        "sha256": reservation_sha256,
    }
    core = {
        "schema_version": 2,
        "artifact_kind": "authority_effect_reconciliation_evidence",
        "reservation": reservation_binding,
        "operation": {
            key: request.get(key)
            for key in (
                "skill_id",
                "skill_version",
                "operation_id",
                "operation_version",
            )
        },
        "subject_before": subject,
        "observed_subject": {
            "ref": subject["ref"],
            "sha256": sha256_file(subject_path),
        },
        "outcome": outcome,
        "owner_result": normalized_owner,
        "observed_at": parse_time(observed_at, "observed_at").isoformat(),
    }
    evidence = {"evidence_id": f"authe-{object_sha256(core)[:24]}", **core}
    path = (
        root
        / AUTHORIZATION_ROOT
        / "reconciliation_evidence"
        / f"{evidence['evidence_id']}.json"
    )
    digest = write_immutable_json(path, evidence, "effect reconciliation evidence")
    binding = {"ref": path.relative_to(root).as_posix(), "sha256": digest}
    validate_reconciliation_evidence(
        root,
        binding,
        reservation,
        reservation_binding,
        outcome,
        require_current_subject=True,
    )
    return {
        "status": "prepared",
        "effect_evidence": binding,
        "evidence": evidence,
    }
