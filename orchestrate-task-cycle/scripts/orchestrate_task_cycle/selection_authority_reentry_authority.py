"""Authority-owner validation for selection authority re-entry."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence

from .authority_artifacts import validate_authority_artifacts
from .authority_boundary import (
    canonical_sha256 as authority_canonical_sha256,
    project_authority_packet,
)
from .selection_authority_reentry_contracts import (
    _operation,
    _operation_key,
    _request_semantic_sha256,
    _subject,
)
from .selection_decision_store import (
    canonical_sha256,
    normalize_binding,
    read_bound_json,
)


def _historical_authority_request(root: Path, packet: dict[str, Any]) -> dict[str, Any]:
    projection = packet.get("decision_binding")
    if not isinstance(projection, dict):
        raise ValueError("source authority packet lacks its decision binding")
    binding = normalize_binding(
        {
            "ref": projection.get("artifact_ref"),
            "sha256": projection.get("artifact_sha256"),
        },
        "source authority decision",
    )
    path, decision = read_bound_json(root, binding, "source authority decision")
    request = decision.get("request")
    request_sha256 = projection.get("request_sha256")
    expected_ref = f".task/authorization/decisions/{projection.get('decision_id')}.json"
    if (
        path.relative_to(root).as_posix() != binding["ref"]
        or binding["ref"] != expected_ref
        or decision.get("decision_id") != projection.get("decision_id")
        or decision.get("decision") != "approval_required"
        or projection.get("decision") != "approval_required"
        or not isinstance(request, dict)
        or decision.get("request_sha256") != request_sha256
        or authority_canonical_sha256(request) != request_sha256
    ):
        raise ValueError("source authority decision or exact request binding differs")
    return {
        "decision": binding,
        "request_sha256": request_sha256,
        "request_semantic_sha256": _request_semantic_sha256(request),
    }


def _old_authority_scope(
    root: Path, source_result: dict[str, Any]
) -> tuple[
    dict[str, str],
    dict[str, str],
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
]:
    packet = source_result.get("authority_packet")
    projection = project_authority_packet(packet)
    findings = list(projection.findings)
    if isinstance(packet, dict):
        findings.extend(validate_authority_artifacts(packet, root))
    if findings:
        codes = ", ".join(sorted({str(row.get("code")) for row in findings}))
        raise ValueError(f"source authority packet is invalid: {codes}")
    axes = packet.get("axes") if isinstance(packet, dict) else None
    authority_axis = axes.get("authority") if isinstance(axes, dict) else None
    approval = packet.get("approval_projection") if isinstance(packet, dict) else None
    scope = packet.get("scope") if isinstance(packet, dict) else None
    if (
        projection.decision != "approval_required"
        or projection.intent_type != "grant_authority"
        or not isinstance(authority_axis, dict)
        or authority_axis.get("status") != "approval_required"
        or not isinstance(approval, dict)
        or approval.get("typed_intent") != "grant_authority"
        or not isinstance(scope, dict)
    ):
        raise ValueError("source authority packet is not an approval-required scope")
    subject = _subject(approval.get("subject"), "source authority subject")
    if packet.get("subject") != subject:
        raise ValueError("source authority packet subject projection differs")
    old_operation = _operation(approval.get("operation") or {})
    packet_operation = _operation(packet.get("operation_binding") or {})
    if old_operation != packet_operation:
        raise ValueError("source authority packet operation projection differs")
    return (
        subject,
        old_operation,
        approval,
        scope,
        _historical_authority_request(root, packet),
    )


def _validate_authority_subject_identity(
    root: Path,
    *,
    subject: dict[str, str],
    candidate: dict[str, Any],
    source_cycle_id: str,
    source_task_id: str,
    approval: dict[str, Any],
    packet_scope: dict[str, Any],
) -> dict[str, Any]:
    identity_keys = (
        "candidate_id",
        "exact_subject_work_id",
        "task_kind",
        "expected_blocker_transition",
    )
    candidate_identity = {key: candidate.get(key) for key in identity_keys}
    if any(
        not isinstance(value, str) or not value for value in candidate_identity.values()
    ):
        raise ValueError(
            "authority reentry candidate lacks exact subject identity fields"
        )
    approval_scope = approval.get("scope")
    for label, scope in (
        ("source authority packet", packet_scope),
        ("source approval projection", approval_scope),
    ):
        if (
            not isinstance(scope, dict)
            or scope.get("cycle_id") != source_cycle_id
            or scope.get("task_id") != source_task_id
        ):
            raise ValueError(
                f"{label} scope differs from the frozen derive predecessor"
            )
    _, payload = read_bound_json(
        root,
        {"ref": subject["ref"], "sha256": subject["digest"]},
        "authority reentry subject payload",
    )
    if (
        subject["revision"] != candidate_identity["candidate_id"]
        or payload.get("cycle_id") != source_cycle_id
        or payload.get("task_id") != source_task_id
        or any(payload.get(key) != value for key, value in candidate_identity.items())
    ):
        raise ValueError(
            "authority reentry subject payload differs from the frozen "
            "candidate or derive predecessor"
        )
    return payload


def _authority_owner_tools() -> dict[str, Any]:
    try:
        from manage_agent_authority.canonical import (
            normalized_time,
            parse_time,
        )
        from manage_agent_authority.lifecycle_preflight import (
            decision_grant_bindings,
            validate_selected_grants,
        )
        from manage_agent_authority.projection_io import (
            load_grant_artifact,
            safe_json,
            validate_grant_state,
        )
        from manage_agent_authority.projection_reservations import (
            validate_decision_artifact,
        )
        from manage_agent_authority.root_grant_transaction import (
            validate_root_grant_receipt_chain,
        )
        from manage_agent_authority.root_grant_request_binding import (
            root_grant_request_binding_covers,
        )
        from manage_agent_authority.workflow_candidates import (
            current_allowed_decision,
        )
    except ImportError as exc:  # pragma: no cover - launcher supplies this owner.
        raise ValueError("authority owner validator is unavailable") from exc
    return {
        "current_allowed_decision": current_allowed_decision,
        "decision_grant_bindings": decision_grant_bindings,
        "load_grant_artifact": load_grant_artifact,
        "normalized_time": normalized_time,
        "parse_time": parse_time,
        "root_grant_request_binding_covers": root_grant_request_binding_covers,
        "safe_json": safe_json,
        "validate_decision_artifact": validate_decision_artifact,
        "validate_grant_state": validate_grant_state,
        "validate_root_grant_receipt_chain": validate_root_grant_receipt_chain,
        "validate_selected_grants": validate_selected_grants,
    }


def _normalized_reentry_at(value: str) -> str:
    tools = _authority_owner_tools()
    try:
        return tools["normalized_time"](value, "authority reentry at")
    except SystemExit as exc:
        raise ValueError(str(exc)) from exc


def _validate_root_materialized_grant(
    root: Path,
    *,
    grant_id: str,
    record: dict[str, Any],
    request: dict[str, Any],
    decision: dict[str, Any],
    skills_root: Path,
    assets_by_ref: dict[str, dict[str, Any]],
    tools: dict[str, Any],
) -> tuple[tuple[str, str], str]:
    try:
        grant, digest = tools["load_grant_artifact"](root, grant_id)
    except SystemExit as exc:
        raise ValueError(str(exc)) from exc
    if digest != record.get("grant_sha256"):
        raise ValueError("authority reentry grant binding differs")
    if grant.get("request_sha256") != decision.get("request_sha256") or not tools[
        "root_grant_request_binding_covers"
    ](grant, request):
        raise ValueError(
            "authority reentry grant does not bind the exact decision request"
        )
    source_approval = normalize_binding(
        grant.get("source_approval"), "authority reentry source approval"
    )
    root_ref = grant.get("root_materialization_ref")
    if (
        grant.get("schema_version") != 3
        or not isinstance(root_ref, str)
        or not root_ref.startswith(".task/authorization/root_grant_materializations/")
        or not root_ref.endswith("/receipt.json")
    ):
        raise ValueError("authority reentry requires signed root-materialized grants")
    try:
        assets = assets_by_ref.get(root_ref)
        if assets is None:
            assets = tools["validate_root_grant_receipt_chain"](
                root,
                root_ref,
                skills_root=skills_root,
            )
            assets_by_ref[root_ref] = assets
        matching = [
            item
            for item in assets["grant_assets"]
            if item["grant"]["grant_id"] == grant_id
        ]
        if (
            len(matching) != 1
            or matching[0]["grant"] != grant
            or matching[0]["grant_sha256"] != digest
        ):
            raise ValueError(
                "root materialization receipt does not bind the exact grant"
            )
        state_path = root / ".task/authorization/state/grants" / f"{grant_id}.json"
        state, _state_digest = tools["safe_json"](
            root,
            state_path,
            "authority reentry grant state",
        )
        state = tools["validate_grant_state"](
            state,
            grant,
            digest,
            "authority reentry grant state",
        )
    except SystemExit as exc:
        raise ValueError(
            f"authority reentry root materialization lineage is invalid: {exc}"
        ) from exc
    if state.get("status") != "active":
        raise ValueError("authority reentry requires an active root-materialized grant")
    return (source_approval["ref"], source_approval["sha256"]), root_ref


def _validate_decision(
    root: Path,
    binding: dict[str, str],
    *,
    skills_root: Path,
    subject: dict[str, str],
    source_cycle_id: str,
    source_task_id: str,
    reentry_at: str,
    assets_by_ref: dict[str, dict[str, Any]],
    tools: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, str], set[tuple[str, str]], set[str]]:
    path, decision = read_bound_json(root, binding, "authority reentry decision")
    try:
        request, grant_bindings = tools["validate_decision_artifact"](
            root,
            decision,
            path,
            skills_root=skills_root,
        )
    except SystemExit as exc:
        raise ValueError(str(exc)) from exc
    if decision.get("decision") != "allowed":
        raise ValueError("authority reentry decision is not allowed")
    if (
        request.get("cycle_id") != source_cycle_id
        or request.get("task_id") != source_task_id
        or request.get("subject") != subject
    ):
        raise ValueError("authority reentry decision scope differs")
    context = request.get("context")
    expected_evidence = {"ref": subject["ref"], "sha256": subject["digest"]}
    if (
        not isinstance(context, dict)
        or context.get("design_selection_status") != "resolved"
        or context.get("design_selection_evidence") != expected_evidence
    ):
        raise ValueError(
            "authority reentry decision lacks exact resolved design evidence"
        )
    operation = _operation(request)
    request_semantic_sha256 = _request_semantic_sha256(request)
    approvals: set[tuple[str, str]] = set()
    materializations: set[str] = set()
    for grant_id, record in grant_bindings.items():
        approval, root_ref = _validate_root_materialized_grant(
            root,
            grant_id=grant_id,
            record=record,
            request=request,
            decision=decision,
            skills_root=skills_root,
            assets_by_ref=assets_by_ref,
            tools=tools,
        )
        approvals.add(approval)
        materializations.add(root_ref)
    try:
        evaluated_at = tools["parse_time"](reentry_at, "authority reentry at")
        decision_at = tools["parse_time"](
            decision.get("evaluated_at"), "authority decision evaluated_at"
        )
    except SystemExit as exc:
        raise ValueError(str(exc)) from exc
    if evaluated_at < decision_at:
        raise ValueError("authority reentry cannot precede its authority decision")
    current, blockers = tools["current_allowed_decision"](
        root,
        decision,
        evaluated_at,
        skills_root,
    )
    if not current:
        raise ValueError(
            "authority reentry decision is no longer currently allowed: "
            + ", ".join(blockers)
        )
    try:
        tools["validate_selected_grants"](
            root,
            tools["decision_grant_bindings"](decision),
            request=request,
            at=reentry_at,
        )
    except SystemExit as exc:
        raise ValueError(
            f"authority reentry current grant preflight failed: {exc}"
        ) from exc
    entry = {
        "decision": binding,
        "decision_id": decision["decision_id"],
        "request_sha256": decision["request_sha256"],
        "request_semantic_sha256": request_semantic_sha256,
        "operation": operation,
    }
    return entry, operation, approvals, materializations


def _validated_authority_decisions(
    root: Path,
    values: Sequence[dict[str, str]],
    *,
    skills_root: Path,
    subject: dict[str, str],
    source_cycle_id: str,
    source_task_id: str,
    required_operation: dict[str, str],
    required_request_semantic_sha256: str,
    at: str,
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, str]],
    dict[str, str],
    str,
]:
    if not values or len(values) > 32:
        raise ValueError("authority reentry requires 1..32 authority decisions")
    normalized = [
        normalize_binding(value, "authority reentry decision") for value in values
    ]
    if len({canonical_sha256(item) for item in normalized}) != len(normalized):
        raise ValueError("authority reentry decisions must be unique")
    entries: list[dict[str, Any]] = []
    operations: dict[tuple[str, str, str, str], dict[str, str]] = {}
    approvals: set[tuple[str, str]] = set()
    materializations: set[str] = set()
    assets_by_ref: dict[str, dict[str, Any]] = {}
    tools = _authority_owner_tools()
    try:
        reentry_at = tools["normalized_time"](
            at,
            "authority reentry at",
        )
    except SystemExit as exc:
        raise ValueError(str(exc)) from exc
    for binding in normalized:
        entry, operation, found_approvals, found_materializations = _validate_decision(
            root,
            binding,
            skills_root=skills_root,
            subject=subject,
            source_cycle_id=source_cycle_id,
            source_task_id=source_task_id,
            reentry_at=reentry_at,
            assets_by_ref=assets_by_ref,
            tools=tools,
        )
        key = _operation_key(operation)
        if key in operations:
            raise ValueError("authority reentry operations must be unique")
        operations[key] = operation
        approvals.update(found_approvals)
        materializations.update(found_materializations)
        entries.append(entry)
    if _operation_key(required_operation) not in operations:
        raise ValueError("authority reentry does not resolve the requested operation")
    required_entry = next(
        row
        for row in entries
        if _operation_key(row["operation"]) == _operation_key(required_operation)
    )
    if (
        not isinstance(required_request_semantic_sha256, str)
        or len(required_request_semantic_sha256) != 64
        or required_entry["request_semantic_sha256"] != required_request_semantic_sha256
    ):
        raise ValueError(
            "authority reentry allowed request semantically differs from "
            "the frozen historical request"
        )
    if len(approvals) != 1 or len(materializations) != 1:
        raise ValueError(
            "authority reentry decisions do not share one signed root lineage"
        )
    entries.sort(
        key=lambda row: (
            _operation_key(row["operation"]),
            row["request_sha256"],
            row["decision"]["ref"],
        )
    )
    source_ref, source_sha = next(iter(approvals))
    return (
        entries,
        [operations[key] for key in sorted(operations)],
        {"ref": source_ref, "sha256": source_sha},
        next(iter(materializations)),
    )


__all__ = ()
