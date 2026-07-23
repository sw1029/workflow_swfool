from __future__ import annotations

from pathlib import Path
from typing import Any

from .artifact_store import list_grants
from .artifact_store import load_grant
from .approval_projection import build_approval_projection
from .canonical import object_sha256
from .canonical import parse_time
from .canonical import read_object
from .canonical import resolve_workspace_path
from .canonical import sha256_file
from .composition import composition_covers
from .composition import load_bound_composition
from .contracts import MUTATION_CLASSES
from .contracts import cardinality_covers
from .contracts import rank_value
from .contracts import reservation_units
from .contracts import risk_value
from .root_grant_request_binding import root_grant_request_binding_covers
from .contracts import validate_request
from .evaluation_context import context_decision
from .evaluation_context import validate_evaluation_context
from .evaluation_context import verify_request_evidence
from .operations import load_operation
from .grant_diagnostics import near_miss_reasons
from .decision_integrity import effective_authority_fingerprint


def manifest_reasons(request: dict[str, Any], operation: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    if not set(operation["required_capabilities"]).issubset(
        request["required_capabilities"]
    ):
        reasons.append("request_understates_manifest_capabilities")
    if risk_value(request["risk_tier"]) < risk_value(operation["risk_floor"]):
        reasons.append("request_understates_manifest_risk")
    mutation_order = {item: index for index, item in enumerate(MUTATION_CLASSES)}
    if (
        mutation_order[request["mutation_class"]]
        < mutation_order[operation["mutation_class"]]
    ):
        reasons.append("request_understates_manifest_mutation")
    reversibility_order = {
        "reversible": 0,
        "conditionally_reversible": 1,
        "irreversible": 2,
    }
    if (
        reversibility_order[request["reversibility"]]
        < reversibility_order[operation["reversibility"]]
    ):
        reasons.append("request_overstates_reversibility")
    if request["decision_class"] != operation["decision_class"]:
        reasons.append("decision_class_mismatch")
    if request["effect_class"] not in operation["effect_classes"]:
        reasons.append("effect_class_not_manifested")
    if request["data_class"] not in operation["data_classes"]:
        reasons.append("data_class_not_manifested")
    if request["subject"]["kind"] not in operation["subject_kinds"]:
        reasons.append("subject_kind_not_manifested")
    return reasons


def _covers(
    request: dict[str, Any],
    grant: dict[str, Any],
    state: dict[str, Any],
    at: Any,
    rank_floor: str,
    session_id: str,
) -> bool:
    if state.get("status") != "active" or grant["holder_rank"] != request["actor_rank"]:
        return False
    if not root_grant_request_binding_covers(grant, request):
        return False
    if parse_time(grant["not_before"], "grant.not_before") > at:
        return False
    if (
        grant.get("expires_at")
        and parse_time(grant["expires_at"], "grant.expires_at") <= at
    ):
        return False
    if rank_value(grant["issuer_rank"]) < rank_value(rank_floor):
        return False
    if not set(request["required_capabilities"]).issubset(grant["capabilities"]):
        return False
    if request["subject"] not in grant["subjects"]:
        return False
    operation = {
        key: request[key]
        for key in ("skill_id", "skill_version", "operation_id", "operation_version")
    }
    if operation not in grant["operations"]:
        return False
    if risk_value(request["risk_tier"]) > risk_value(grant["risk_ceiling"]):
        return False
    if request["decision_class"] not in grant["decision_classes"]:
        return False
    if not cardinality_covers(grant["cardinality"], request["cardinality_requested"]):
        return False
    if grant["session_id"] and grant["session_id"] != session_id:
        return False
    if grant["task_id"] and grant["task_id"] != request["task_id"]:
        return False
    if grant["improvement_id"] and grant["improvement_id"] != request["pack_id"]:
        return False
    if grant["cardinality"] == "task_lease" and grant["task_id"] != request["task_id"]:
        return False
    if (
        grant["cardinality"] == "improvement_lease"
        and grant["improvement_id"] != request["pack_id"]
    ):
        return False
    available = state.get("remaining_uses")
    if grant.get("max_uses") is not None and (
        grant["max_uses"] < request["use_budget_requested"]
    ):
        return False
    if available is not None and available - int(
        state.get("reserved_uses", 0)
    ) < reservation_units(request):
        return False
    return True


def _selected_binding(
    grant: dict[str, Any], digest: str, state: dict[str, Any]
) -> dict[str, Any]:
    return {
        "grant_id": grant["grant_id"],
        "grant_sha256": digest,
        "state_version": state["version"],
        "policy_snapshot": grant["policy_snapshot"],
    }


def _lineage_records(
    root: Path, grant: dict[str, Any]
) -> list[tuple[dict[str, Any], str, dict[str, Any]]]:
    records: list[tuple[dict[str, Any], str, dict[str, Any]]] = []
    seen = {grant["grant_id"]}
    parent_id = grant.get("parent_grant_id")
    while parent_id:
        if parent_id in seen:
            raise SystemExit("Authority grant lineage is circular.")
        seen.add(parent_id)
        parent, digest, state = load_grant(root, parent_id)
        records.append((parent, digest, state))
        parent_id = parent.get("parent_grant_id")
    return records


def _lineage_covers(
    records: list[tuple[dict[str, Any], str, dict[str, Any]]],
    request: dict[str, Any],
    at: Any,
    session_id: str,
) -> bool:
    for grant, _, state in records:
        if state["status"] != "active":
            return False
        if not root_grant_request_binding_covers(grant, request):
            return False
        if parse_time(grant["not_before"], "ancestor.not_before") > at:
            return False
        if (
            grant["expires_at"]
            and parse_time(grant["expires_at"], "ancestor.expires_at") <= at
        ):
            return False
        if grant["session_id"] and grant["session_id"] != session_id:
            return False
        if grant["task_id"] and grant["task_id"] != request["task_id"]:
            return False
        if grant["improvement_id"] and grant["improvement_id"] != request["pack_id"]:
            return False
        remaining = state["remaining_uses"]
        if grant.get("max_uses") is not None and (
            grant["max_uses"] < request["use_budget_requested"]
        ):
            return False
        if remaining is not None and (
            remaining - state["reserved_uses"] < reservation_units(request)
        ):
            return False
    return True


def _grant_decision(
    root: Path,
    request: dict[str, Any],
    operation: dict[str, Any],
    at: Any,
    session_id: str,
) -> tuple[str, list[str], list[dict[str, Any]], list[dict[str, Any]]]:
    records = list_grants(root)
    candidates = []
    for grant, digest, state in records:
        if not _covers(
            request,
            grant,
            state,
            at,
            operation["source_rank_floor"],
            session_id,
        ):
            continue
        lineage = _lineage_records(root, grant)
        if _lineage_covers(lineage, request, at, session_id):
            candidates.append((grant, digest, state, lineage))
    if candidates:
        candidates.sort(
            key=lambda item: (
                risk_value(item[0]["risk_ceiling"]),
                len(item[0]["capabilities"]),
                len(item[0]["subjects"]),
                len(item[0]["operations"]),
                item[0]["grant_id"],
            )
        )
        chosen = candidates[0]
        lineage = [_selected_binding(*record) for record in chosen[3]]
        return "allowed", [], [_selected_binding(*chosen[:3])], lineage
    if request["composition_receipt"] is None:
        return (
            "approval_required",
            ["no_single_covering_active_grant"]
            + near_miss_reasons(
                request,
                records,
                at,
                operation["source_rank_floor"],
                session_id,
            ),
            [],
            [],
        )
    base_request_sha = object_sha256({**request, "composition_receipt": None})
    composition = load_bound_composition(
        root, request["composition_receipt"], base_request_sha
    )
    records_by_id = {
        grant["grant_id"]: (grant, digest, state) for grant, digest, state in records
    }
    if any(grant_id not in records_by_id for grant_id in composition["grant_ids"]):
        return "conflict", ["composition_grant_missing"], [], []
    composed = [records_by_id[grant_id] for grant_id in composition["grant_ids"]]
    lineages = [_lineage_records(root, record[0]) for record in composed]
    if not composition_covers(
        request,
        composed,
        at=at,
        rank_floor_index=rank_value(operation["source_rank_floor"]),
        session_id=session_id,
    ) or any(
        not _lineage_covers(lineage, request, at, session_id) for lineage in lineages
    ):
        return "conflict", ["composition_no_longer_covers_request"], [], []
    lineage_by_id = {
        record[0]["grant_id"]: _selected_binding(*record)
        for lineage in lineages
        for record in lineage
    }
    return (
        "allowed",
        [],
        [_selected_binding(*record) for record in composed],
        [lineage_by_id[key] for key in sorted(lineage_by_id)],
    )


def evaluate(
    root: Path,
    raw_request: dict[str, Any],
    raw_context: dict[str, Any],
    *,
    evaluated_at: str,
    skills_root: Path | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    request = validate_request(raw_request)
    verify_request_evidence(root, request)
    context = validate_evaluation_context(root, raw_context)
    request_sha = object_sha256(request)
    at = parse_time(evaluated_at, "evaluated_at")
    operation, manifest_binding = load_operation(
        request["skill_id"],
        request["skill_version"],
        request["operation_id"],
        request["operation_version"],
        skills_root=skills_root,
    )
    decision: str
    reasons: list[str]
    selected: list[dict[str, Any]] = []
    lineage: list[dict[str, Any]] = []
    if operation is None:
        if request["mutation_class"] == "observe":
            decision, reasons = "classification_repair", ["operation_manifest_missing"]
        else:
            decision, reasons = "denied", ["unknown_mutating_operation_fail_closed"]
    else:
        request_manifest_reasons = manifest_reasons(request, operation)
        if request_manifest_reasons:
            decision, reasons = "conflict", request_manifest_reasons
        elif operation["authorization_mechanism"] == "none":
            decision, reasons = (
                "not_applicable",
                ["operation_manifest_marks_authority_not_applicable"],
            )
        elif operation["authorization_mechanism"] == "typed_source_approval":
            decision, reasons = (
                "not_applicable",
                ["operation_requires_typed_source_approval_verifier"],
            )
        elif operation["authorization_mechanism"] == "bound_lifecycle_artifact":
            decision, reasons = (
                "not_applicable",
                ["operation_requires_bound_lifecycle_artifact_verifier"],
            )
        else:
            context_result, context_reasons = context_decision(request, context)
            if context_result:
                decision, reasons = context_result, context_reasons
            else:
                decision, reasons, selected, lineage = _grant_decision(
                    root,
                    request,
                    operation,
                    at,
                    context["session_ceiling"]["evidence_id"],
                )
    context_sha = object_sha256(context)
    fingerprint = effective_authority_fingerprint(
        request, context, manifest_binding, selected, lineage
    )
    approval_projection = (
        build_approval_projection(request, context, reasons)
        if decision == "approval_required"
        else None
    )
    core = {
        "schema_version": 2,
        "artifact_kind": "authority_decision",
        "request": request,
        "request_sha256": request_sha,
        "evaluation_context": context,
        "evaluation_context_sha256": context_sha,
        "decision": decision,
        "reason_codes": sorted(reasons),
        "approval_projection": approval_projection,
        "selected_grants": selected,
        "lineage_grants": lineage,
        "operation_manifest": manifest_binding,
        "effective_authority_fingerprint": fingerprint,
        "evaluated_at": at.isoformat(),
    }
    return {"decision_id": f"authd-{object_sha256(core)[:24]}", **core}


def load_bound_decision(
    root: Path, ref: str, digest: str
) -> tuple[dict[str, Any], Path]:
    path = resolve_workspace_path(root, ref, "authority decision")
    if sha256_file(path) != digest:
        raise SystemExit("Authority decision digest mismatch.")
    decision = read_object(path, "authority decision")
    if (
        decision.get("schema_version") != 2
        or decision.get("artifact_kind") != "authority_decision"
    ):
        raise SystemExit("Authority decision contract is invalid.")
    if decision.get("request_sha256") != object_sha256(decision.get("request")):
        raise SystemExit("Authority decision request binding is invalid.")
    if decision.get("evaluation_context_sha256") != object_sha256(
        decision.get("evaluation_context")
    ):
        raise SystemExit("Authority decision context binding is invalid.")
    return decision, path
