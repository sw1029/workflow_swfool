from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..base import RuleContext
from ..common import add, value_for
from ..session_audit import (
    ARTIFACT_KIND,
    CANONICAL_EVIDENCE_CLASSES,
    canonical_evidence_ref_hashes,
    validate_collection_projection,
    validate_session_audit_packet,
)


CLOSE_TARGETS = {"validate", "report"}
SUCCESS_VALIDATION_VERDICTS = {
    "complete",
    "completed",
    "pass",
    "passed",
    "success",
}


@dataclass(slots=True)
class SessionAuditCheck:
    context: RuleContext
    supplied: list[tuple[Any, bool]]
    required: bool
    positive_close: bool
    current_task_id: str | None
    current_cycle_id: str | None
    projected_packets: list[dict[str, Any]] = field(default_factory=list)

    @property
    def severity(self) -> str:
        return "block" if self.required and self.positive_close else "warn"


def positive_close_claim(target: str, result: dict[str, Any]) -> bool:
    if target == "validate":
        validation = str(value_for(result, "validation_verdict") or "").strip().lower()
        progress = str(value_for(result, "progress_verdict") or "").strip().lower()
        return validation in SUCCESS_VALIDATION_VERDICTS or progress == "advanced"
    if target == "report":
        return (
            str(value_for(result, "completion_status") or "").strip().lower()
            == "complete_verified"
        )
    return False


def audit_inputs(
    result: dict[str, Any], contract_context: Any
) -> list[tuple[Any, bool]]:
    """Return audit values paired with caller-context provenance."""

    values: list[tuple[Any, bool]] = []

    def append(value: Any, *, from_contract_context: bool) -> None:
        if value is None:
            return
        if isinstance(value, list):
            values.extend((item, from_contract_context) for item in value)
        else:
            values.append((value, from_contract_context))

    if isinstance(contract_context, dict):
        if contract_context.get("artifact_kind") in {
            ARTIFACT_KIND,
            "session_audit_collection_projection",
        }:
            append(contract_context, from_contract_context=True)
        append(contract_context.get("session_audit"), from_contract_context=True)
        append(contract_context.get("session_audits"), from_contract_context=True)
    append(result.get("session_audit"), from_contract_context=False)
    append(result.get("session_audits"), from_contract_context=False)
    return values


def projection_packets(value: dict[str, Any]) -> list[dict[str, Any]]:
    packets = value.get("packets")
    return (
        [packet for packet in packets if isinstance(packet, dict)]
        if isinstance(packets, list)
        else []
    )


def direct_packet_projection(packet: dict[str, Any]) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    for finding in packet.get("findings", []):
        if not isinstance(finding, dict):
            continue
        findings.append(
            {
                "code": finding.get("code"),
                "severity": finding.get("severity"),
                "evidence_class": finding.get("evidence_class"),
                "resolved": finding.get("resolved") is True,
                "canonical_evidence_ref_hashes": canonical_evidence_ref_hashes(finding),
            }
        )
    return {
        "audit_id": packet.get("audit_id"),
        "capture_status": packet.get("capture_status"),
        "integrity_status": packet.get("integrity_status"),
        "consumable": packet.get("consumable"),
        "binding": packet.get("binding"),
        "source_projection_verified": False,
        "canonical_refs_verified": False,
        "findings": findings,
    }


def current_binding(
    result: dict[str, Any], contract_context: Any
) -> tuple[str | None, str | None]:
    task_candidates = [
        value_for(result, "task_id"),
        value_for(result, "completed_task_id"),
    ]
    cycle_candidates = [value_for(result, "cycle_id")]
    if isinstance(contract_context, dict):
        task_candidates.append(contract_context.get("task_id"))
        cycle_candidates.append(contract_context.get("cycle_id"))
        cycle_state = contract_context.get("cycle_state")
        if isinstance(cycle_state, dict):
            cycle_candidates.append(cycle_state.get("latest_cycle_id"))
            current_stage = cycle_state.get("current_stage")
            if isinstance(current_stage, dict):
                task_candidates.append(current_stage.get("task_id"))
                cycle_candidates.append(current_stage.get("cycle_id"))

    def first(values: list[Any]) -> str | None:
        for value in values:
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    return first(task_candidates), first(cycle_candidates)


def run_session_audit_check(context: RuleContext) -> None:
    contract_context = context.get("contract_context")
    supplied = audit_inputs(context.result, contract_context)
    required = bool(
        isinstance(contract_context, dict)
        and contract_context.get("session_audit_required") is True
    )
    positive_close = context.target in CLOSE_TARGETS and positive_close_claim(
        context.target, context.result
    )
    task_id, cycle_id = current_binding(context.result, contract_context)
    state = SessionAuditCheck(
        context,
        supplied,
        required,
        positive_close,
        task_id,
        cycle_id,
    )
    if required and not supplied:
        add(
            context.findings,
            "block" if positive_close else "warn",
            "required_session_audit_missing",
            "Caller-required session audit is absent; transcript absence cannot establish that an action did not occur.",
        )
        return
    for index, (value, trusted) in enumerate(supplied):
        _consume_audit_input(state, index, value, trusted)
    if required and not state.projected_packets:
        add(
            context.findings,
            "block" if positive_close else "warn",
            "required_session_audit_not_consumable",
            "Caller-required session audit has no structurally valid packet available for close evaluation.",
        )
    for packet in state.projected_packets:
        _route_projected_packet(state, packet)


def _consume_audit_input(
    state: SessionAuditCheck,
    index: int,
    value: Any,
    from_contract_context: bool,
) -> None:
    if isinstance(value, dict) and value.get("artifact_kind") == ARTIFACT_KIND:
        errors = validate_session_audit_packet(value)
        if errors:
            for error in errors:
                add(
                    state.context.findings,
                    state.severity,
                    str(error.get("code") or "session_audit_packet_invalid"),
                    "Supplied session-audit packet violates the closed, body-free contract.",
                    {
                        "audit_index": index,
                        "path": error.get("path"),
                        "detail": error.get("detail"),
                    },
                )
            return
        state.projected_packets.append(direct_packet_projection(value))
        return
    if (
        isinstance(value, dict)
        and value.get("artifact_kind") == "session_audit_collection_projection"
    ):
        _consume_collection(state, index, value, from_contract_context)
        return
    add(
        state.context.findings,
        state.severity,
        "session_audit_envelope_invalid",
        "Supplied session-audit input is neither a validated packet nor a body-free collection projection.",
        {"audit_index": index},
    )


def _consume_collection(
    state: SessionAuditCheck,
    index: int,
    value: dict[str, Any],
    from_contract_context: bool,
) -> None:
    errors = validate_collection_projection(value)
    if errors or value.get("invalid_packets"):
        diagnostics = errors or [
            {
                "code": "session_audit_collection_contains_invalid_packets",
                "path": "invalid_packets",
                "detail": "collector observed malformed, unsafe, or contract-invalid audit packets",
            }
        ]
        for error in diagnostics:
            add(
                state.context.findings,
                state.severity,
                str(error.get("code") or "session_audit_projection_invalid"),
                "Supplied session-audit collection is malformed or reports invalid packets.",
                {
                    "audit_index": index,
                    "path": error.get("path"),
                    "detail": error.get("detail"),
                },
            )
        if errors:
            return
    _route_collection_metadata(state, index, value)
    packets = projection_packets(value)
    if not from_contract_context:
        add(
            state.context.findings,
            state.severity,
            "session_audit_collection_projection_untrusted_origin",
            "A subskill result cannot self-promote a collection projection to trusted-collector evidence.",
            {"audit_index": index},
        )
        packets = [
            {**packet, "source_projection_verified": False} for packet in packets
        ]
    state.projected_packets.extend(packets)


def _route_collection_metadata(
    state: SessionAuditCheck, index: int, value: dict[str, Any]
) -> None:
    index_projection = value.get("index")
    if isinstance(index_projection, dict) and index_projection.get(
        "contract_status"
    ) in {"invalid", "malformed"}:
        add(
            state.context.findings,
            "warn",
            "session_audit_index_requires_rebuild",
            "Derived session-audit index is invalid or malformed and may be deterministically rebuilt without changing workflow truth.",
            {
                "contract_status": index_projection.get("contract_status"),
                "error_codes": index_projection.get("error_codes"),
                "auto_repair_target": ".task/session_audit/index.json",
            },
        )
    if value.get("truncated") is True:
        add(
            state.context.findings,
            state.severity,
            "session_audit_collection_truncated",
            "Session-audit collection was truncated; omitted packets cannot be assumed clean or absent.",
            {
                "audit_index": index,
                "total_packet_count": value.get("total_packet_count"),
                "scanned_packet_count": value.get("scanned_packet_count"),
                "truncated_count": value.get("truncated_count"),
            },
        )


def _route_projected_packet(state: SessionAuditCheck, packet: dict[str, Any]) -> None:
    audit_id = packet.get("audit_id")
    capture_status = packet.get("capture_status")
    integrity_status = packet.get("integrity_status")
    consumable = packet.get("consumable") is True
    if state.required and packet.get("source_projection_verified") is not True:
        add(
            state.context.findings,
            "block" if state.positive_close else "warn",
            "required_session_audit_source_projection_unverified",
            "Caller-required audit must come from the trusted collector after bundled deterministic source-projection validation.",
            {"audit_id": audit_id},
        )
    if state.required and (
        capture_status != "complete"
        or integrity_status == "unverified"
        or not consumable
    ):
        add(
            state.context.findings,
            "block" if state.positive_close else "warn",
            "required_session_audit_capture_incomplete",
            "Caller-required audit capture is incomplete, quarantined, failed, unverified, or non-consumable.",
            {
                "audit_id": audit_id,
                "capture_status": capture_status,
                "integrity_status": integrity_status,
                "consumable": consumable,
            },
        )
    for finding in packet.get("findings", []):
        _route_packet_finding(state, audit_id, finding)


def _route_packet_finding(
    state: SessionAuditCheck, audit_id: Any, finding: Any
) -> None:
    if not isinstance(finding, dict) or finding.get("resolved") is True:
        return
    evidence_class = str(finding.get("evidence_class") or "")
    severity = str(finding.get("severity") or "")
    code = str(finding.get("code") or "session_audit_observation")
    if severity == "block" and evidence_class in CANONICAL_EVIDENCE_CLASSES:
        add(
            state.context.findings,
            "warn",
            "session_audit_cross_source_claim_routes_review",
            "A session-owned cross-source claim is advisory until a distinct deterministic comparator contract establishes the relation.",
            {
                "audit_id": audit_id,
                "finding_code": code,
                "evidence_class": evidence_class,
                "canonical_evidence_ref_hashes": finding.get(
                    "canonical_evidence_ref_hashes"
                ),
                "current_task_id": state.current_task_id,
                "current_cycle_id": state.current_cycle_id,
            },
        )
    elif severity == "block":
        add(
            state.context.findings,
            "warn",
            "session_audit_observation_routes_review",
            "Transcript-only or absence-unknown findings route review but cannot establish or negate workflow facts.",
            {
                "audit_id": audit_id,
                "finding_code": code,
                "evidence_class": evidence_class,
            },
        )
