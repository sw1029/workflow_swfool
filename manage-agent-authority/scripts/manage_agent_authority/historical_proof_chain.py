"""Read-only historical validation for authority reservation proof chains."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

from .artifact_store import _validate_child, grant_path, verify_binding
from .canonical import parse_time
from .evaluation_context import context_decision, validate_evaluation_context
from .evaluator import effective_authority_fingerprint, manifest_reasons
from .execution_results import validate_pre_commit_verification
from .operations import load_operation
from .projection_contracts import AUTHORIZATION_ROOT, STATE_ROOT
from .projection_io import (
    binding,
    changes_by_ref,
    load_bound_json,
    load_grant_artifact,
    safe_json,
    validate_grant_state,
    validate_reservation_state,
)
from .projection_recovery import validated_inventory_intents
from .projection_reservations import validate_decision_artifact, validate_reservation
from .source_approval import load_source_approval, validate_for_grant
from .workflow_candidates import GrantRecords, grant_covers_request


ProofInput = tuple[dict[str, str], dict[str, str], int]


def _display_sha256(value: dict[str, Any]) -> str:
    payload = (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _settled_reservations(
    root: Path, skills_root: Path | None
) -> dict[str, dict[str, Any]]:
    settled: dict[str, dict[str, Any]] = {}
    for path, artifact in validated_inventory_intents(root, skills_root=skills_root):
        if artifact.get("artifact_kind") != "authority_reservation":
            continue
        ref = path.relative_to(root).as_posix()
        if ref in settled:
            raise SystemExit("Authority reservation intent paths must be unique.")
        settled[ref] = artifact
    return settled


def _reservation_intent(
    root: Path,
    binding_value: Any,
    settled: dict[str, dict[str, Any]],
) -> tuple[
    dict[str, Any],
    dict[str, str],
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    normalized = binding(binding_value, "historical authority reservation")
    artifact, path, observed = load_bound_json(
        root, normalized, "historical authority reservation"
    )
    reservation, uses, changes = validate_reservation(root, artifact, path)
    expected_ref = (
        AUTHORIZATION_ROOT / "reservations" / f"{reservation['reservation_id']}.json"
    ).as_posix()
    if observed["ref"] != expected_ref or settled.get(expected_ref) != reservation:
        raise SystemExit(
            "Historical authority reservation is not a validated settled owner intent."
        )
    return reservation, observed, uses, changes


def _historical_records(
    root: Path,
    uses: list[dict[str, Any]],
    changes: list[dict[str, Any]],
) -> tuple[GrantRecords, dict[str, dict[str, Any]]]:
    by_ref = changes_by_ref(changes)
    records: GrantRecords = {}
    after_states: dict[str, dict[str, Any]] = {}
    for use in uses:
        grant_id = use["grant_id"]
        grant, digest = load_grant_artifact(root, grant_id)
        ref = (STATE_ROOT / "grants" / f"{grant_id}.json").as_posix()
        change = by_ref.get(ref)
        if change is None or change.get("before") is None:
            raise SystemExit("Historical authority proof lacks a grant before-state.")
        before = validate_grant_state(
            change["before"], grant, digest, f"historical {grant_id} before-state"
        )
        after = validate_grant_state(
            change["after"], grant, digest, f"historical {grant_id} after-state"
        )
        records[grant_id] = (
            grant,
            digest,
            before,
            {"ref": ref, "sha256": _display_sha256(before)},
        )
        after_states[grant_id] = after
    return records, after_states


def _validate_grant_bases(root: Path, records: GrantRecords) -> None:
    for grant_id, (grant, _digest, _before, _state_binding) in records.items():
        verify_binding(root, grant["policy_snapshot"], f"{grant_id} policy_snapshot")
        parent_id = grant["parent_grant_id"]
        if parent_id is None:
            source_path = verify_binding(
                root, grant["source_approval"], f"{grant_id} source_approval"
            )
            validate_for_grant(
                root,
                load_source_approval(source_path),
                grant,
                prospective=False,
            )
            continue
        parent_record = records.get(parent_id)
        if parent_record is None:
            raise SystemExit("Historical authority proof omits a lineage grant.")
        parent, parent_digest, parent_before, _binding = parent_record
        expected_source = {
            "ref": grant_path(root, parent_id).relative_to(root).as_posix(),
            "sha256": parent_digest,
        }
        if grant["source_approval"] != expected_source:
            raise SystemExit("Delegated historical grant source binding is invalid.")
        _validate_child(parent, parent_before, grant)


def _expected_lineage(
    records: GrantRecords, selected_id: str
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen = {selected_id}
    parent_id = records[selected_id][0]["parent_grant_id"]
    while parent_id:
        if parent_id in seen or parent_id not in records:
            raise SystemExit("Historical authority lineage is missing or circular.")
        seen.add(parent_id)
        grant, digest, state, _binding = records[parent_id]
        result.append(
            {
                "grant_id": parent_id,
                "grant_sha256": digest,
                "state_version": state["version"],
                "policy_snapshot": grant["policy_snapshot"],
            }
        )
        parent_id = grant["parent_grant_id"]
    return result


def _require_historical_coverage(
    records: GrantRecords,
    selected_id: str,
    request: dict[str, Any],
    context: dict[str, Any],
    operation: dict[str, Any],
    decision_at: Any,
    reserved_at: Any,
) -> None:
    if reserved_at < decision_at:
        raise SystemExit("Authority reservation cannot predate its decision.")
    for label, moment in (("decision", decision_at), ("reservation", reserved_at)):
        covers, blockers = grant_covers_request(
            records,
            selected_id,
            request,
            moment,
            rank_floor=operation["source_rank_floor"],
            session_id=context["session_ceiling"]["evidence_id"],
        )
        if not covers:
            raise SystemExit(
                f"Historical selected grant failed {label}-time coverage: "
                + ", ".join(sorted(blockers))
            )


def _decision_authority(
    root: Path,
    reservation: dict[str, Any],
    records: GrantRecords,
    *,
    skills_root: Path | None,
) -> tuple[dict[str, Any], dict[str, str]]:
    decision, path, decision_binding = load_bound_json(
        root, reservation["decision"], "historical authority decision"
    )
    request, _grants = validate_decision_artifact(
        root, decision, path, skills_root=skills_root, verify_manifest=True
    )
    context = validate_evaluation_context(root, decision["evaluation_context"])
    if context != decision["evaluation_context"] or decision["decision"] != "allowed":
        raise SystemExit("Historical authority decision is not an allowed exact context.")
    selected = decision["selected_grants"]
    if len(selected) != 1:
        raise SystemExit("Historical proof chain requires one selected covering grant.")
    selected_id = selected[0]["grant_id"]
    record = records.get(selected_id)
    if record is None:
        raise SystemExit("Historical selected grant has no captured before-state.")
    grant, digest, state, _state_binding = record
    expected_selected = {
        "grant_id": selected_id,
        "grant_sha256": digest,
        "state_version": state["version"],
        "policy_snapshot": grant["policy_snapshot"],
    }
    if selected != [expected_selected] or decision["lineage_grants"] != _expected_lineage(
        records, selected_id
    ):
        raise SystemExit("Historical decision grant bindings are not exact.")
    operation, manifest = load_operation(
        request["skill_id"],
        request["skill_version"],
        request["operation_id"],
        request["operation_version"],
        skills_root=skills_root,
    )
    if operation is None or manifest != decision["operation_manifest"]:
        raise SystemExit("Historical authority operation manifest is stale.")
    if (
        operation["authorization_mechanism"] != "grant"
        or manifest_reasons(request, operation)
        or context_decision(request, context) != (None, [])
    ):
        raise SystemExit("Historical allowed decision was not canonically grant-eligible.")
    _require_historical_coverage(
        records,
        selected_id,
        request,
        context,
        operation,
        parse_time(decision["evaluated_at"], "decision.evaluated_at"),
        parse_time(reservation["reserved_at"], "reservation.reserved_at"),
    )
    expected_fingerprint = effective_authority_fingerprint(
        request,
        context,
        manifest,
        selected,
        decision["lineage_grants"],
    )
    if decision["effective_authority_fingerprint"] != expected_fingerprint:
        raise SystemExit("Historical effective authority fingerprint is invalid.")
    return decision, decision_binding


def _verification(
    root: Path,
    reservation: dict[str, Any],
    reservation_binding: dict[str, str],
    pre_commit_binding: Any,
    changes: list[dict[str, Any]],
    after_states: dict[str, dict[str, Any]],
    *,
    expected_version: int,
) -> tuple[dict[str, Any], dict[str, str], dict[str, Any]]:
    normalized = binding(pre_commit_binding, "historical pre_commit verification")
    verification = validate_pre_commit_verification(
        root,
        reservation,
        reservation_binding,
        normalized,
        expected_version=expected_version,
        require_current_state=False,
    )
    by_ref = changes_by_ref(changes)
    state_ref = (
        STATE_ROOT / "reservations" / f"{reservation['reservation_id']}.json"
    ).as_posix()
    reserved_state = by_ref[state_ref]["after"]
    if (
        reserved_state.get("status") != "reserved"
        or reserved_state.get("version") != expected_version
        or verification["reservation_state"]["sha256"]
        != _display_sha256(reserved_state)
    ):
        raise SystemExit("Historical pre_commit reservation-state digest is invalid.")
    expected_grants = [
        {
            "grant_id": grant_id,
            "grant_sha256": state["grant_sha256"],
            "state_version": state["version"],
            "status": state["status"],
            "remaining_uses": state["remaining_uses"],
            "reserved_uses": state["reserved_uses"],
        }
        for grant_id, state in sorted(after_states.items())
    ]
    if verification["grant_states"] != expected_grants:
        raise SystemExit("Historical pre_commit grant-state projection is invalid.")
    state_path = root / state_ref
    current, _digest = safe_json(root, state_path, "authority reservation state")
    current = validate_reservation_state(
        current, reservation["reservation_id"], "authority reservation state"
    )
    return verification, normalized, current


def _validate_one(
    root: Path,
    proof: ProofInput,
    settled: dict[str, dict[str, Any]],
    *,
    skills_root: Path | None,
) -> dict[str, Any]:
    reservation_input, pre_commit_input, expected_version = proof
    reservation, reservation_binding, uses, changes = _reservation_intent(
        root, reservation_input, settled
    )
    records, after_states = _historical_records(root, uses, changes)
    _validate_grant_bases(root, records)
    decision, decision_binding = _decision_authority(
        root, reservation, records, skills_root=skills_root
    )
    verification, verification_binding, current = _verification(
        root,
        reservation,
        reservation_binding,
        pre_commit_input,
        changes,
        after_states,
        expected_version=expected_version,
    )
    return {
        "reservation": reservation,
        "reservation_binding": reservation_binding,
        "decision": decision,
        "decision_binding": decision_binding,
        "verification": verification,
        "verification_binding": verification_binding,
        "current_state": current,
    }


def validate_historical_proof_chains(
    root: Path,
    proofs: Iterable[ProofInput],
    *,
    skills_root: Path | None = None,
) -> list[dict[str, Any]]:
    """Validate multiple proof chains with one settled-intent graph scan."""

    root = root.expanduser().resolve(strict=True)
    selected_skills = skills_root.resolve() if skills_root is not None else None
    proof_list = list(proofs)
    if not proof_list:
        raise SystemExit("Historical authority proof-chain input cannot be empty.")
    settled = _settled_reservations(root, selected_skills)
    return [
        _validate_one(root, proof, settled, skills_root=selected_skills)
        for proof in proof_list
    ]


def validate_historical_proof_chain(
    root: Path,
    reservation_binding: dict[str, str],
    pre_commit_binding: dict[str, str],
    *,
    expected_version: int,
    skills_root: Path | None = None,
) -> dict[str, Any]:
    """Validate one original proof chain without requiring current grant budget."""

    return validate_historical_proof_chains(
        root,
        [(reservation_binding, pre_commit_binding, expected_version)],
        skills_root=skills_root,
    )[0]


__all__ = (
    "validate_historical_proof_chain",
    "validate_historical_proof_chains",
)
