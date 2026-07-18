"""Closed authority-phase packet validation and scoped terminal-wait projection.

The authority owner evaluates grants and owns reservations.  This module only
validates the exact, versioned handoff consumed at the existing orchestrator
``authority`` boundary; it never grants authority itself.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from ._authority_boundary_dispatch import validate_mutating_dispatch
from ._authority_boundary_grants import (
    validate_approval,
    validate_grants,
    validate_relations,
    validate_reservation,
)
from ._authority_boundary_schema import DECISIONS, PREFLIGHT_KEYS, TOP_KEYS
from ._authority_boundary_validation import (
    canonical_digest,
    closed,
    evidence_ids,
    finding,
    identifier,
    scope_identity,
    sha,
    validate_axes,
    validate_decision,
    validate_scope,
)


@dataclass(frozen=True, slots=True)
class AuthorityProjection:
    status: str
    decision: str
    scope_id: str | None
    effective_authority_fingerprint: str | None
    axes: dict[str, str]
    mutation_class: str | None
    intent_type: str | None
    findings: tuple[dict[str, Any], ...]

    @property
    def valid(self) -> bool:
        return self.status == "pass"


def canonical_sha256(value: Any) -> str:
    """Return the canonical JSON SHA-256 used by authority handoffs."""

    return canonical_digest(value)


def _fingerprint_material(packet: dict[str, Any]) -> dict[str, Any]:
    decision = (
        packet.get("decision_binding")
        if isinstance(packet.get("decision_binding"), dict)
        else {}
    )
    axes = packet.get("axes") if isinstance(packet.get("axes"), dict) else {}
    reservation = (
        packet.get("reservation_binding")
        if isinstance(packet.get("reservation_binding"), dict)
        else {}
    )
    return {
        "decision": {
            "request_sha256": decision.get("request_sha256"),
            "decision": decision.get("decision"),
            "effective_authority_fingerprint": decision.get(
                "effective_authority_fingerprint"
            ),
        },
        "operation_binding": packet.get("operation_binding"),
        "subject": packet.get("subject"),
        "scope": packet.get("scope"),
        "authority_axis": axes.get("authority"),
        "selected_grants": packet.get("selected_grants"),
        "lineage_grants": packet.get("lineage_grants"),
        "approval_projection": packet.get("approval_projection"),
        "composition_receipt": packet.get("composition_receipt"),
        "reservation": {
            key: reservation.get(key)
            for key in (
                "applicability",
                "reservation_id",
                "artifact_sha256",
                "state_sha256",
                "state_version",
                "status",
                "effective_authority_fingerprint",
                "grant_uses",
            )
        },
    }


def effective_authority_fingerprint(packet: dict[str, Any]) -> str:
    """Hash exact effective authority while excluding unrelated mutable policy."""

    return canonical_sha256(_fingerprint_material(packet))


def _legacy_projection() -> AuthorityProjection:
    return AuthorityProjection(
        "legacy_unverified",
        "classification_repair",
        None,
        None,
        {},
        None,
        None,
        (
            finding(
                "authority_legacy_unverified",
                "Legacy authority material is diagnostic only and cannot authorize or retroactively pass.",
            ),
        ),
    )


def project_authority_packet(value: Any) -> AuthorityProjection:
    findings: list[dict[str, Any]] = []
    if (
        not isinstance(value, dict)
        or value.get("schema_version") != 2
        or value.get("artifact_kind") != "orchestrator_authority_packet"
    ):
        return _legacy_projection()
    packet = closed(value, TOP_KEYS, "authority packet", findings)
    if packet.get("step") != "authority":
        findings.append(
            finding(
                "authority_step_invalid", "Authority packet requires step=authority."
            )
        )
    if not identifier(packet.get("packet_id")):
        findings.append(
            finding(
                "authority_identity_invalid",
                "packet_id must be a bounded opaque ID.",
            )
        )
    decision, operation, _subject = validate_decision(packet, findings)
    scope = validate_scope(packet, findings)
    statuses = validate_axes(packet.get("axes"), findings)
    selected_grants, lineage_grants = validate_grants(packet, findings)
    validate_approval(packet, decision, findings)
    reservation, uses = validate_reservation(packet, findings)
    preflight = closed(
        packet.get("dispatch_preflight"),
        PREFLIGHT_KEYS,
        "dispatch_preflight",
        findings,
    )
    evidence_ids(packet.get("evidence_ids"), "evidence_ids", findings)
    validate_relations(packet, statuses, selected_grants, findings)
    validate_mutating_dispatch(
        decision,
        operation,
        selected_grants + lineage_grants,
        reservation,
        uses,
        preflight,
        findings,
    )
    expected_fingerprint = effective_authority_fingerprint(packet)
    declared_fingerprint = sha(packet.get("effective_authority_fingerprint"))
    if declared_fingerprint != expected_fingerprint:
        findings.append(
            finding(
                "authority_scoped_fingerprint_mismatch",
                "Effective authority fingerprint must bind only exact decision/grant/reservation scope.",
            )
        )
    expected_packet_sha = canonical_sha256(
        {key: child for key, child in packet.items() if key != "packet_sha256"}
    )
    if sha(packet.get("packet_sha256")) != expected_packet_sha:
        findings.append(
            finding(
                "authority_packet_sha256_mismatch",
                "Authority packet SHA-256 does not match its closed body.",
            )
        )
    resolved_scope_id = scope_identity(packet)
    if resolved_scope_id is None:
        findings.append(
            finding(
                "authority_scope_identity_invalid",
                "Exact request/operation/subject scope cannot be derived.",
            )
        )
    return AuthorityProjection(
        "invalid" if findings else "pass",
        str(decision.get("decision") or "classification_repair"),
        resolved_scope_id,
        expected_fingerprint if not findings else declared_fingerprint,
        statuses,
        str(operation.get("mutation_class") or "") or None,
        str(scope.get("intent_type") or "") or None,
        tuple(findings),
    )


def authority_watch_row(value: Any) -> dict[str, Any]:
    projection = project_authority_packet(value)
    if (
        not projection.valid
        or projection.scope_id is None
        or projection.effective_authority_fingerprint is None
    ):
        codes = ", ".join(item["code"] for item in projection.findings)
        raise ValueError(f"authority packet is not a valid scoped v2 packet: {codes}")
    return {
        "watch_id": "watch-"
        + hashlib.sha256(projection.scope_id.encode("utf-8")).hexdigest()[:24],
        "kind": "effective_authority",
        "evidence_class": "authority",
        "authority_scope_id": projection.scope_id,
        "effective_authority_fingerprint": projection.effective_authority_fingerprint,
        "decision": projection.decision,
        "axis_statuses": projection.axes,
    }


__all__ = (
    "AuthorityProjection",
    "DECISIONS",
    "authority_watch_row",
    "canonical_sha256",
    "effective_authority_fingerprint",
    "project_authority_packet",
)
