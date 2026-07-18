"""Closed field and relation validation for authority boundary packets."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from ._authority_boundary_schema import (
    AUTHORITY_STATUSES,
    AXIS_KEYS,
    AXIS_ROW_KEYS,
    BINDING_KEYS,
    DECISION_CLASSES,
    DECISION_KEYS,
    DECISIONS,
    EXTERNAL_STATUSES,
    GOAL_STATUSES,
    ID_RE,
    INTENT_TYPES,
    LOCAL_STATUSES,
    MUTATION_CLASSES,
    OPERATION_KEYS,
    RANKS,
    RISKS,
    RISK_STATUSES,
    SCOPE_KEYS,
    SCOPE_KINDS,
    SHA_RE,
    SUBJECT_KEYS,
)


def canonical_digest(value: Any) -> str:
    body = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(body).hexdigest()


def finding(code: str, message: str, evidence: Any = None) -> dict[str, Any]:
    result: dict[str, Any] = {"code": code, "message": message}
    if evidence is not None:
        result["evidence"] = evidence
    return result


def closed(
    value: Any,
    keys: set[str],
    label: str,
    findings: list[dict[str, Any]],
) -> dict[str, Any]:
    if not isinstance(value, dict):
        findings.append(
            finding("authority_packet_object_invalid", f"{label} must be an object.")
        )
        return {}
    unknown = sorted(set(value) - keys)
    missing = sorted(keys - set(value))
    if unknown:
        findings.append(
            finding(
                "authority_packet_unknown_fields",
                f"{label} has unknown fields.",
                {"path": label, "fields": unknown},
            )
        )
    if missing:
        findings.append(
            finding(
                "authority_packet_missing_fields",
                f"{label} is missing fields.",
                {"path": label, "fields": missing},
            )
        )
    return value


def sha(value: Any) -> str | None:
    text = str(value or "").lower().removeprefix("sha256:")
    return text if SHA_RE.fullmatch(text) else None


def identifier(value: Any, *, nullable: bool = False) -> str | None:
    if value is None and nullable:
        return None
    text = str(value or "").strip()
    return text if ID_RE.fullmatch(text) else None


def nonnegative_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def evidence_ids(
    value: Any,
    label: str,
    findings: list[dict[str, Any]],
) -> list[str]:
    if not isinstance(value, list):
        findings.append(
            finding("authority_axis_evidence_invalid", f"{label} must be a list.")
        )
        return []
    normalized = [identifier(item) for item in value]
    if any(item is None for item in normalized) or len(set(normalized)) != len(
        normalized
    ):
        findings.append(
            finding(
                "authority_axis_evidence_invalid",
                f"{label} must contain unique bounded IDs.",
            )
        )
        return []
    return [str(item) for item in normalized]


def binding(
    value: Any,
    label: str,
    findings: list[dict[str, Any]],
) -> dict[str, Any]:
    row = closed(value, BINDING_KEYS, label, findings)
    if not str(row.get("ref") or "").strip() or sha(row.get("sha256")) is None:
        findings.append(
            finding(
                "authority_binding_invalid",
                f"{label} requires an exact ref and SHA-256.",
            )
        )
    return row


def validate_axes(value: Any, findings: list[dict[str, Any]]) -> dict[str, str]:
    packet = closed(value, AXIS_KEYS, "axes", findings)
    allowed = {
        "authority": AUTHORITY_STATUSES,
        "local_resolution": LOCAL_STATUSES,
        "external_input": EXTERNAL_STATUSES,
        "risk_cost": RISK_STATUSES,
        "goal_truth": GOAL_STATUSES,
    }
    statuses: dict[str, str] = {}
    evidence: dict[str, set[str]] = {}
    for name, values in allowed.items():
        row = closed(packet.get(name), AXIS_ROW_KEYS, f"axes.{name}", findings)
        status = str(row.get("status") or "")
        if status not in values:
            findings.append(
                finding(
                    "authority_axis_status_invalid",
                    f"axes.{name}.status is invalid.",
                )
            )
        ids = evidence_ids(
            row.get("evidence_ids"), f"axes.{name}.evidence_ids", findings
        )
        if status not in {"not_required", "not_applicable", "unverified"} and not ids:
            findings.append(
                finding(
                    "authority_axis_evidence_missing",
                    f"axes.{name} requires axis-owned evidence.",
                )
            )
        statuses[name] = status
        evidence[name] = set(ids)
    names = list(evidence)
    overlaps = sorted(
        {
            item
            for index, name in enumerate(names)
            for other in names[index + 1 :]
            for item in evidence[name] & evidence[other]
        }
    )
    if overlaps:
        findings.append(
            finding(
                "authority_axes_evidence_conflated",
                "Axis evidence IDs must be disjoint.",
                {"evidence_ids": overlaps},
            )
        )
    return statuses


def scope_identity(packet: dict[str, Any]) -> str | None:
    decision = packet.get("decision_binding")
    operation = packet.get("operation_binding")
    subject = packet.get("subject")
    if not all(isinstance(item, dict) for item in (decision, operation, subject)):
        return None
    material = {
        "request_id": decision.get("request_id"),
        "operation": {
            key: operation.get(key)
            for key in (
                "skill_id",
                "skill_version",
                "operation_id",
                "operation_version",
            )
        },
        "subject": subject,
    }
    if not material["request_id"] or not all(material["operation"].values()):
        return None
    return "authority-scope-" + canonical_digest(material)[:32]


def validate_decision(
    packet: dict[str, Any],
    findings: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    decision = closed(
        packet.get("decision_binding"), DECISION_KEYS, "decision_binding", findings
    )
    operation = closed(
        packet.get("operation_binding"),
        OPERATION_KEYS,
        "operation_binding",
        findings,
    )
    subject = closed(packet.get("subject"), SUBJECT_KEYS, "subject", findings)
    if not all(
        identifier(decision.get(field)) for field in ("decision_id", "request_id")
    ):
        findings.append(
            finding(
                "authority_identity_invalid",
                "Decision and request IDs must be bounded opaque IDs.",
            )
        )
    for label, raw in (
        ("decision artifact", decision.get("artifact_sha256")),
        ("request", decision.get("request_sha256")),
        ("owner fingerprint", decision.get("effective_authority_fingerprint")),
        ("subject", subject.get("digest")),
    ):
        if sha(raw) is None:
            findings.append(
                finding(
                    "authority_digest_invalid",
                    f"{label} requires a SHA-256 digest.",
                )
            )
    if decision.get("decision") not in DECISIONS:
        findings.append(
            finding(
                "authority_decision_invalid",
                "Decision is outside the closed vocabulary.",
            )
        )
    if operation.get("mutation_class") not in MUTATION_CLASSES:
        findings.append(
            finding("authority_mutation_class_invalid", "mutation_class is invalid.")
        )
    if operation.get("manifest_status") not in {
        "verified",
        "missing",
        "unknown",
        "invalid",
    }:
        findings.append(
            finding("authority_manifest_status_invalid", "manifest_status is invalid.")
        )
    if not all(
        identifier(operation.get(field))
        for field in (
            "skill_id",
            "skill_version",
            "operation_id",
            "operation_version",
        )
    ):
        findings.append(
            finding(
                "authority_operation_identity_invalid",
                "Operation identity must be exact bounded IDs.",
            )
        )
    if not str(decision.get("artifact_ref") or "").strip():
        findings.append(
            finding(
                "authority_artifact_ref_invalid",
                "Decision artifact ref must be exact and non-empty.",
            )
        )
    manifest_ref = operation.get("manifest_ref")
    manifest_sha = operation.get("manifest_sha256")
    if operation.get("manifest_status") == "verified":
        if (
            not str(manifest_ref or "").strip()
            or "*" in str(manifest_ref)
            or sha(manifest_sha) is None
        ):
            findings.append(
                finding(
                    "authority_manifest_binding_invalid",
                    "A verified operation requires an exact manifest ref and SHA-256.",
                )
            )
    elif manifest_ref is not None or manifest_sha is not None:
        findings.append(
            finding(
                "authority_unverified_manifest_populated",
                "An unverified operation cannot claim a manifest binding.",
            )
        )
    if (
        not str(subject.get("ref") or "").strip()
        or not str(subject.get("revision") or "").strip()
        or "*" in str(subject.get("ref") or "")
    ):
        findings.append(
            finding(
                "authority_subject_invalid",
                "Subject ref and revision must be exact and wildcard-free.",
            )
        )
    return decision, operation, subject


def validate_scope(
    packet: dict[str, Any], findings: list[dict[str, Any]]
) -> dict[str, Any]:
    scope = closed(packet.get("scope"), SCOPE_KEYS, "scope", findings)
    if (
        scope.get("scope_kind") not in SCOPE_KINDS
        or scope.get("intent_type") not in INTENT_TYPES
    ):
        findings.append(
            finding("authority_scope_invalid", "scope_kind or intent_type is invalid.")
        )
    if (
        scope.get("decision_class") not in DECISION_CLASSES
        or scope.get("required_source_rank") not in RANKS
        or scope.get("risk_tier") not in RISKS
    ):
        findings.append(
            finding(
                "authority_tier_invalid",
                "Decision, source-rank, or risk tier is invalid.",
            )
        )
    expected_class = {
        "goal": "D0",
        "authority_policy": "D0",
        "design": "D1",
        "task": "D2",
        "improvement": "D2",
        "action": "D3",
    }.get(scope.get("scope_kind"))
    if expected_class and scope.get("decision_class") != expected_class:
        findings.append(
            finding(
                "authority_scope_class_mismatch",
                "scope_kind must use its deterministic decision class.",
            )
        )
    for field in ("cycle_id", "task_id", "pack_id", "attempt_id"):
        if identifier(scope.get(field), nullable=True) != scope.get(field):
            findings.append(
                finding(
                    "authority_scope_id_invalid",
                    f"scope.{field} must be null or a bounded opaque ID.",
                )
            )
    return scope


__all__ = (
    "binding",
    "canonical_digest",
    "closed",
    "evidence_ids",
    "finding",
    "identifier",
    "nonnegative_int",
    "scope_identity",
    "sha",
    "validate_axes",
    "validate_decision",
    "validate_scope",
)
