from __future__ import annotations

from pathlib import Path
from typing import Any

from .artifact_store import AUTHORIZATION_ROOT
from .canonical import parse_time
from .contracts import cardinality_covers
from .contracts import rank_value
from .contracts import reservation_units
from .contracts import risk_value
from .evaluator import evaluate
from .projection_io import load_grant_artifact
from .projection_io import safe_json
from .projection_io import safe_owned_directory
from .projection_io import validate_grant_state


GrantRecord = tuple[dict[str, Any], str, dict[str, Any], dict[str, str]]
GrantRecords = dict[str, GrantRecord]


def validated_grants(root: Path) -> GrantRecords:
    root = root.resolve()
    directory = safe_owned_directory(
        root, AUTHORIZATION_ROOT / "grants", "Authority grant directory"
    )
    if directory is None:
        return {}
    records: GrantRecords = {}
    for path in sorted(directory.iterdir()):
        if path.suffix != ".json":
            continue
        if path.is_symlink() or not path.is_file():
            raise SystemExit("Authority grant directory contains a non-regular artifact.")
        grant, digest = load_grant_artifact(root, path.stem)
        state_path = (
            root
            / AUTHORIZATION_ROOT
            / "state"
            / "grants"
            / f"{grant['grant_id']}.json"
        )
        state, state_digest = safe_json(root, state_path, "authority grant state")
        state = validate_grant_state(state, grant, digest, "authority grant state")
        if grant["grant_id"] in records:
            raise SystemExit("Authority grant identities must be unique.")
        records[grant["grant_id"]] = (
            grant,
            digest,
            state,
            {
                "ref": state_path.relative_to(root).as_posix(),
                "sha256": state_digest,
            },
        )
    return records


def _temporal_blockers(
    grant: dict[str, Any], evaluated_at: Any, prefix: str
) -> list[str]:
    blockers: list[str] = []
    if evaluated_at < parse_time(grant["not_before"], "grant.not_before"):
        blockers.append(f"{prefix}not_yet_active")
    expires_at = grant["expires_at"]
    if expires_at and evaluated_at >= parse_time(expires_at, "grant.expires_at"):
        blockers.append(f"{prefix}time_expired")
    return blockers


def grant_status_records(
    records: GrantRecords, grant_id: str | None, evaluated_at: Any
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for current_id in sorted(records):
        if grant_id is not None and current_id != grant_id:
            continue
        grant, digest, state, state_binding = records[current_id]
        blockers: list[str] = []
        if state["status"] != "active":
            blockers.append(f"grant_status_{state['status']}")
        blockers.extend(_temporal_blockers(grant, evaluated_at, "grant_"))
        seen = {current_id}
        parent_id = grant["parent_grant_id"]
        while parent_id:
            if parent_id in seen:
                blockers.append("lineage_cycle")
                break
            seen.add(parent_id)
            parent_record = records.get(parent_id)
            if parent_record is None:
                blockers.append(f"ancestor_grant_missing:{parent_id}")
                break
            parent, _, parent_state, _ = parent_record
            if parent_state["status"] != "active":
                blockers.append(
                    f"ancestor_grant_{parent_state['status']}:{parent_id}"
                )
            blockers.extend(
                f"{code}:{parent_id}"
                for code in _temporal_blockers(
                    parent, evaluated_at, "ancestor_grant_"
                )
            )
            parent_id = parent["parent_grant_id"]
        result.append(
            {
                "grant": grant,
                "grant_sha256": digest,
                "state": state,
                "state_binding": state_binding,
                "effective_usable": not blockers,
                "effective_status": "usable" if not blockers else "blocked",
                "lineage_blocker_codes": blockers,
            }
        )
    return result


def reservation_authority_blockers(
    reservation: dict[str, Any],
    decision: dict[str, Any],
    records: GrantRecords,
    evaluated_at: Any,
) -> list[str]:
    selected = {item["grant_id"] for item in decision["selected_grants"]}
    lineage = {item["grant_id"] for item in decision["lineage_grants"]}
    blockers: list[str] = []
    for use in reservation["grant_uses"]:
        grant_id = use["grant_id"]
        role = "selected" if grant_id in selected else "ancestor"
        if grant_id not in selected | lineage:
            raise SystemExit("Authority reservation has an uncorrelated grant use.")
        record = records.get(grant_id)
        if record is None:
            blockers.append(f"{role}_grant_missing:{grant_id}")
            continue
        grant, digest, state, _ = record
        if digest != use["grant_sha256"]:
            raise SystemExit("Authority reservation current grant binding is invalid.")
        if state["status"] != "active":
            blockers.append(f"{role}_grant_status_{state['status']}:{grant_id}")
        blockers.extend(
            f"{code}:{grant_id}"
            for code in _temporal_blockers(
                grant, evaluated_at, f"{role}_grant_"
            )
        )
        if state["reserved_uses"] < use["units"]:
            blockers.append(f"{role}_grant_reserved_units_missing:{grant_id}")
    return blockers


def _budget_blockers(
    grant: dict[str, Any], state: dict[str, Any], request: dict[str, Any], prefix: str
) -> list[str]:
    blockers: list[str] = []
    if grant["max_uses"] is not None and (
        grant["max_uses"] < request["use_budget_requested"]
    ):
        blockers.append(f"{prefix}grant_budget_too_small")
    remaining = state["remaining_uses"]
    if remaining is not None and (
        remaining - state["reserved_uses"] < reservation_units(request)
    ):
        blockers.append(f"{prefix}grant_available_units_insufficient")
    return blockers


def grant_covers_request(
    records: GrantRecords,
    grant_id: str,
    request: dict[str, Any],
    evaluated_at: Any,
    *,
    rank_floor: str,
    session_id: str,
) -> tuple[bool, list[str]]:
    record = records.get(grant_id)
    if record is None:
        return False, ["grant_missing"]
    grant, _, state, _ = record
    blockers: list[str] = []
    if state["status"] != "active":
        blockers.append(f"grant_status_{state['status']}")
    blockers.extend(_temporal_blockers(grant, evaluated_at, "grant_"))
    if grant["holder_rank"] != request["actor_rank"]:
        blockers.append("holder_rank_mismatch")
    if rank_value(grant["issuer_rank"]) < rank_value(rank_floor):
        blockers.append("issuer_rank_below_operation_floor")
    if not set(request["required_capabilities"]).issubset(grant["capabilities"]):
        blockers.append("capabilities_not_covered")
    if request["subject"] not in grant["subjects"]:
        blockers.append("subject_not_covered")
    operation = {
        key: request[key]
        for key in ("skill_id", "skill_version", "operation_id", "operation_version")
    }
    if operation not in grant["operations"]:
        blockers.append("operation_not_covered")
    if risk_value(request["risk_tier"]) > risk_value(grant["risk_ceiling"]):
        blockers.append("risk_not_covered")
    if request["decision_class"] not in grant["decision_classes"]:
        blockers.append("decision_class_not_covered")
    if not cardinality_covers(
        grant["cardinality"], request["cardinality_requested"]
    ):
        blockers.append("cardinality_not_covered")
    if grant["session_id"] and grant["session_id"] != session_id:
        blockers.append("session_scope_mismatch")
    if grant["task_id"] and grant["task_id"] != request["task_id"]:
        blockers.append("task_scope_mismatch")
    if grant["improvement_id"] and grant["improvement_id"] != request["pack_id"]:
        blockers.append("improvement_scope_mismatch")
    blockers.extend(_budget_blockers(grant, state, request, ""))

    seen = {grant_id}
    parent_id = grant["parent_grant_id"]
    while parent_id:
        if parent_id in seen:
            blockers.append("lineage_cycle")
            break
        seen.add(parent_id)
        parent_record = records.get(parent_id)
        if parent_record is None:
            blockers.append(f"ancestor_grant_missing:{parent_id}")
            break
        parent, _, parent_state, _ = parent_record
        if parent_state["status"] != "active":
            blockers.append(f"ancestor_grant_status_{parent_state['status']}:{parent_id}")
        blockers.extend(
            f"{code}:{parent_id}"
            for code in _temporal_blockers(
                parent, evaluated_at, "ancestor_grant_"
            )
        )
        if parent["session_id"] and parent["session_id"] != session_id:
            blockers.append(f"ancestor_session_scope_mismatch:{parent_id}")
        if parent["task_id"] and parent["task_id"] != request["task_id"]:
            blockers.append(f"ancestor_task_scope_mismatch:{parent_id}")
        if parent["improvement_id"] and (
            parent["improvement_id"] != request["pack_id"]
        ):
            blockers.append(f"ancestor_improvement_scope_mismatch:{parent_id}")
        blockers.extend(
            f"{code}:{parent_id}"
            for code in _budget_blockers(parent, parent_state, request, "ancestor_")
        )
        parent_id = parent["parent_grant_id"]
    return not blockers, blockers


def current_allowed_decision(
    root: Path,
    decision: dict[str, Any],
    evaluated_at: Any,
    skills_root: Path | None,
) -> tuple[bool, list[str]]:
    if decision["decision"] != "allowed":
        return False, ["persisted_decision_not_allowed"]
    try:
        current = evaluate(
            root,
            decision["request"],
            decision["evaluation_context"],
            evaluated_at=evaluated_at.isoformat(),
            skills_root=skills_root,
        )
    except SystemExit:
        return False, ["decision_re_evaluation_failed"]
    blockers: list[str] = []
    if current["decision"] != "allowed":
        blockers.append(f"current_decision_{current['decision']}")
    if (
        current["effective_authority_fingerprint"]
        != decision["effective_authority_fingerprint"]
    ):
        blockers.append("effective_authority_fingerprint_changed")
    if current["selected_grants"] != decision["selected_grants"]:
        blockers.append("selected_grants_changed")
    if current["lineage_grants"] != decision["lineage_grants"]:
        blockers.append("lineage_grants_changed")
    return not blockers, blockers


__all__ = [
    "current_allowed_decision",
    "grant_covers_request",
    "grant_status_records",
    "reservation_authority_blockers",
    "validated_grants",
]
