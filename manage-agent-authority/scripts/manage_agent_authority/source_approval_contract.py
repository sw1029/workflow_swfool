"""Closed source-approval contracts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .canonical import parse_time
from .contracts import (
    CARDINALITIES,
    DECISION_CLASSES,
    RISK_TIERS,
    SOURCE_RANKS,
    validate_subject,
)


SOURCE_KINDS = {
    "platform_session_ceiling": "S4",
    "explicit_user_instruction": "S3",
    "delegated_policy_steward": "S2",
    "cycle_coordination_grant": "S1",
}
APPROVAL_V2_KEYS = {
    "schema_version",
    "artifact_kind",
    "approval_id",
    "source_kind",
    "source_rank",
    "decision_type",
    "capabilities",
    "subjects",
    "operations",
    "risk_ceiling",
    "decision_classes",
    "cardinalities",
    "max_uses",
    "grant_ids",
    "request_digests",
    "lineage_ids",
    "delegation_binding",
    "not_before",
    "expires_at",
    "evidence_id",
    "integrity_status",
}
APPROVAL_V3_KEYS = (APPROVAL_V2_KEYS - {"integrity_status"}) | {
    "decision_binding",
    "decision_trust_class",
}
APPROVAL_V4_KEYS = APPROVAL_V3_KEYS | {"grant_projections"}
APPROVAL_V5_KEYS = APPROVAL_V4_KEYS
OPERATION_KEYS = {"skill_id", "skill_version", "operation_id", "operation_version"}
DECISION_TRUST_CLASSES = {
    "caller_asserted_exact_echo",
    "caller_asserted_plan_decision",
    "host_user_signed_exact_plan",
}
ROOT_GRANT_PROJECTION_KEYS = {
    "grant_id",
    "lineage_id",
    "grant_idempotency_key",
    "request_sha256",
    "holder_rank",
    "capabilities",
    "subjects",
    "operations",
    "risk_ceiling",
    "decision_classes",
    "cardinality",
    "max_uses",
    "session_id",
    "task_id",
    "improvement_id",
    "policy_snapshot",
    "root_materialization_ref",
}


def _unique_strings(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise SystemExit(f"{label} must be a non-empty list.")
    normalized = sorted(set(str(item) for item in value))
    if len(normalized) != len(value) or any(
        not item or "*" in item for item in normalized
    ):
        raise SystemExit(f"{label} must contain unique exact values without wildcards.")
    return normalized


def _digests(value: Any) -> list[str]:
    if not isinstance(value, list):
        raise SystemExit("source approval request_digests must be a list.")
    normalized = sorted(set(str(item) for item in value))
    if len(normalized) != len(value) or any(
        len(item) != 64 or any(char not in "0123456789abcdef" for char in item)
        for item in normalized
    ):
        raise SystemExit(
            "source approval request_digests must be unique SHA-256 values."
        )
    return normalized


def _operations(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list) or not value:
        raise SystemExit("source approval operations must be non-empty.")
    normalized: list[dict[str, str]] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict) or set(item) != OPERATION_KEYS:
            raise SystemExit(f"source approval operations[{index}] is not closed.")
        operation = {key: str(item[key] or "") for key in sorted(OPERATION_KEYS)}
        if any(not field or "*" in field for field in operation.values()):
            raise SystemExit(
                "source approval operations must be exact without wildcards."
            )
        normalized.append(operation)
    if len({tuple(item.values()) for item in normalized}) != len(normalized):
        raise SystemExit("source approval operations must be unique.")
    return sorted(normalized, key=lambda item: tuple(item.values()))


def _delegation_binding(value: Any, required: bool) -> dict[str, str] | None:
    if value is None:
        if required:
            raise SystemExit("Delegated source approval requires delegation_binding.")
        return None
    if not isinstance(value, dict) or set(value) != {"ref", "sha256"}:
        raise SystemExit("delegation_binding must contain exact ref and sha256.")
    ref = str(value["ref"] or "").strip()
    digest = str(value["sha256"] or "")
    if not ref or Path(ref).is_absolute() or "*" in ref or ".." in Path(ref).parts:
        raise SystemExit("delegation_binding.ref must be workspace-relative and exact.")
    if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
        raise SystemExit("delegation_binding.sha256 must be a lowercase SHA-256.")
    return {"ref": ref, "sha256": digest}


def _exact_identifier(
    value: Any, label: str, *, nullable: bool = False
) -> str | None:
    if value is None:
        if nullable:
            return None
        raise SystemExit(f"{label} is required.")
    normalized = str(value or "").strip()
    if (
        not normalized
        or len(normalized) > 128
        or "*" in normalized
        or "/" in normalized
    ):
        raise SystemExit(f"{label} must be a bounded exact identifier.")
    return normalized


def _root_grant_projections(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value:
        raise SystemExit("Schema-v4 source approval grant_projections must be non-empty.")
    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(value):
        label = f"source approval grant_projections[{index}]"
        if not isinstance(item, dict) or set(item) != ROOT_GRANT_PROJECTION_KEYS:
            raise SystemExit(f"{label} is not closed.")
        request_sha256 = str(item["request_sha256"])
        if len(request_sha256) != 64 or any(
            char not in "0123456789abcdef" for char in request_sha256
        ):
            raise SystemExit(f"{label}.request_sha256 must be a lowercase SHA-256.")
        holder_rank = str(item["holder_rank"])
        if holder_rank not in SOURCE_RANKS:
            raise SystemExit(f"{label}.holder_rank is invalid.")
        risk_ceiling = str(item["risk_ceiling"])
        if risk_ceiling not in RISK_TIERS:
            raise SystemExit(f"{label}.risk_ceiling is invalid.")
        cardinality = str(item["cardinality"])
        if cardinality not in CARDINALITIES:
            raise SystemExit(f"{label}.cardinality is invalid.")
        max_uses = item["max_uses"]
        if (
            not isinstance(max_uses, int)
            or isinstance(max_uses, bool)
            or max_uses < 1
        ):
            raise SystemExit(f"{label}.max_uses must be positive.")
        subjects = item["subjects"]
        if not isinstance(subjects, list) or len(subjects) != 1:
            raise SystemExit(f"{label}.subjects must contain exactly one subject.")
        operations = item["operations"]
        if not isinstance(operations, list) or len(operations) != 1:
            raise SystemExit(
                f"{label}.operations must contain exactly one operation."
            )
        root_materialization_ref = str(
            item["root_materialization_ref"] or ""
        ).strip()
        if (
            not root_materialization_ref.startswith(
                ".task/authorization/root_grant_materializations/"
            )
            or not root_materialization_ref.endswith("/receipt.json")
            or "*" in root_materialization_ref
            or ".." in Path(root_materialization_ref).parts
        ):
            raise SystemExit(
                f"{label}.root_materialization_ref is invalid."
            )
        normalized.append(
            {
                "grant_id": _exact_identifier(
                    item["grant_id"], f"{label}.grant_id"
                ),
                "lineage_id": _exact_identifier(
                    item["lineage_id"], f"{label}.lineage_id"
                ),
                "grant_idempotency_key": _exact_identifier(
                    item["grant_idempotency_key"],
                    f"{label}.grant_idempotency_key",
                ),
                "request_sha256": request_sha256,
                "holder_rank": holder_rank,
                "capabilities": _unique_strings(
                    item["capabilities"], f"{label}.capabilities"
                ),
                "subjects": [
                    validate_subject(subject, f"{label}.subjects[{subject_index}]")
                    for subject_index, subject in enumerate(subjects)
                ],
                "operations": _operations(operations),
                "risk_ceiling": risk_ceiling,
                "decision_classes": _unique_strings(
                    item["decision_classes"], f"{label}.decision_classes"
                ),
                "cardinality": cardinality,
                "max_uses": max_uses,
                "session_id": _exact_identifier(
                    item["session_id"], f"{label}.session_id", nullable=True
                ),
                "task_id": _exact_identifier(
                    item["task_id"], f"{label}.task_id", nullable=True
                ),
                "improvement_id": _exact_identifier(
                    item["improvement_id"],
                    f"{label}.improvement_id",
                    nullable=True,
                ),
                "policy_snapshot": _delegation_binding(
                    item["policy_snapshot"], True
                ),
                "root_materialization_ref": root_materialization_ref,
            }
        )
    normalized.sort(key=lambda item: item["request_sha256"])
    for field in ("grant_id", "lineage_id", "request_sha256"):
        values = [item[field] for item in normalized]
        if len(values) != len(set(values)):
            raise SystemExit(
                f"Schema-v4 source approval has duplicate projection {field}."
            )
    return normalized


def _projection_union(
    projections: list[dict[str, Any]], field: str
) -> list[Any]:
    by_identity: dict[str, Any] = {}
    for projection in projections:
        for item in projection[field]:
            identity = (
                str(item)
                if isinstance(item, str)
                else json.dumps(item, sort_keys=True, separators=(",", ":"))
            )
            by_identity[identity] = item
    return [by_identity[key] for key in sorted(by_identity)]


def _validate_projection_coverage(
    approval: dict[str, Any], projections: list[dict[str, Any]]
) -> None:
    expected = {
        "capabilities": sorted(
            set(_projection_union(projections, "capabilities"))
            | {"authority.grant.issue"}
        ),
        "subjects": _projection_union(projections, "subjects"),
        "operations": _projection_union(projections, "operations"),
        "risk_ceiling": max(
            (item["risk_ceiling"] for item in projections),
            key=RISK_TIERS.index,
        ),
        "decision_classes": _projection_union(
            projections, "decision_classes"
        ),
        "cardinalities": sorted(
            {item["cardinality"] for item in projections}
        ),
        "max_uses": max(item["max_uses"] for item in projections),
        "grant_ids": sorted(item["grant_id"] for item in projections),
        "request_digests": sorted(
            item["request_sha256"] for item in projections
        ),
        "lineage_ids": sorted(item["lineage_id"] for item in projections),
    }
    differing: list[str] = []
    for field, value in expected.items():
        if field in {"subjects", "operations"}:
            actual_set = {
                json.dumps(item, sort_keys=True, separators=(",", ":"))
                for item in approval[field]
            }
            expected_set = {
                json.dumps(item, sort_keys=True, separators=(",", ":"))
                for item in value
            }
            if actual_set != expected_set or len(approval[field]) != len(value):
                differing.append(field)
        elif approval[field] != value:
            differing.append(field)
    if differing:
        raise SystemExit(
            "Schema-v4 source approval coverage is not the exact union of its "
            f"per-grant projections: {', '.join(differing)}."
        )


def validate_source_approval(value: dict[str, Any]) -> dict[str, Any]:
    schema_version = value.get("schema_version")
    expected = (
        APPROVAL_V2_KEYS
        if schema_version == 2
        else APPROVAL_V3_KEYS
        if schema_version == 3
        else APPROVAL_V4_KEYS
        if schema_version == 4
        else APPROVAL_V5_KEYS
        if schema_version == 5
        else set()
    )
    extra = sorted(set(value) - expected)
    missing = sorted(expected - set(value))
    if extra or missing:
        raise SystemExit(f"Source approval has unknown={extra} missing={missing}.")
    if (
        schema_version not in {2, 3, 4, 5}
        or value["artifact_kind"] != "authority_source_approval"
    ):
        raise SystemExit(
            "Source approval requires schema_version=2, 3, 4, or 5 and "
            "artifact_kind=authority_source_approval."
        )
    source_kind = str(value["source_kind"])
    source_rank = str(value["source_rank"])
    if SOURCE_KINDS.get(source_kind) != source_rank:
        raise SystemExit(
            "Source approval kind and rank do not match the closed source hierarchy."
        )
    if value["decision_type"] != "grant_authority":
        raise SystemExit(
            "Source approval cannot substitute for another typed decision."
        )
    if schema_version == 2:
        if value["integrity_status"] != "verified":
            raise SystemExit(
                "Historical schema-v2 source approval integrity must be verified."
            )
        decision_fields = {"integrity_status": "verified"}
    else:
        decision_binding = _delegation_binding(value["decision_binding"], True)
        trust_class = str(value["decision_trust_class"])
        if trust_class not in DECISION_TRUST_CLASSES:
            raise SystemExit(
                "Schema-v3 source approval decision trust class is unsupported."
            )
        decision_fields = {
            "decision_binding": decision_binding,
            "decision_trust_class": trust_class,
        }
    decisions = _unique_strings(
        value["decision_classes"], "source approval decision_classes"
    )
    cardinalities = _unique_strings(
        value["cardinalities"], "source approval cardinalities"
    )
    if any(item not in DECISION_CLASSES for item in decisions):
        raise SystemExit("Source approval contains an unknown decision class.")
    if any(item not in CARDINALITIES for item in cardinalities):
        raise SystemExit("Source approval contains an unknown cardinality.")
    risk = str(value["risk_ceiling"])
    if risk not in RISK_TIERS:
        raise SystemExit("Source approval risk ceiling is invalid.")
    max_uses = value["max_uses"]
    if max_uses is not None and (
        not isinstance(max_uses, int) or isinstance(max_uses, bool) or max_uses < 1
    ):
        raise SystemExit("Source approval max_uses must be null or positive.")
    subjects = value["subjects"]
    if not isinstance(subjects, list) or not subjects:
        raise SystemExit("Source approval subjects must be non-empty.")
    normalized = {
        "schema_version": schema_version,
        "artifact_kind": "authority_source_approval",
        "approval_id": str(value["approval_id"]),
        "source_kind": source_kind,
        "source_rank": source_rank,
        "decision_type": "grant_authority",
        "capabilities": _unique_strings(
            value["capabilities"], "source approval capabilities"
        ),
        "subjects": [
            validate_subject(item, f"source approval subjects[{index}]")
            for index, item in enumerate(subjects)
        ],
        "operations": _operations(value["operations"]),
        "risk_ceiling": risk,
        "decision_classes": decisions,
        "cardinalities": cardinalities,
        "max_uses": max_uses,
        "grant_ids": _unique_strings(
            value["grant_ids"], "source approval grant_ids"
        ),
        "request_digests": _digests(value["request_digests"]),
        "lineage_ids": _unique_strings(
            value["lineage_ids"], "source approval lineage_ids"
        ),
        "delegation_binding": _delegation_binding(
            value["delegation_binding"], source_rank in {"S1", "S2"}
        ),
        "not_before": parse_time(
            value["not_before"], "source approval not_before"
        ).isoformat(),
        "expires_at": (
            parse_time(
                value["expires_at"], "source approval expires_at"
            ).isoformat()
            if value["expires_at"]
            else None
        ),
        "evidence_id": str(value["evidence_id"]),
        **decision_fields,
    }
    if schema_version in {4, 5}:
        projections = _root_grant_projections(value["grant_projections"])
        normalized["grant_projections"] = projections
        expected_trust = (
            "host_user_signed_exact_plan"
            if schema_version == 5
            else "caller_asserted_plan_decision"
        )
        if normalized["decision_trust_class"] != expected_trust:
            raise SystemExit(
                f"Schema-v{schema_version} source approval requires its exact "
                "plan-bound decision trust class."
            )
        _validate_projection_coverage(normalized, projections)
    return normalized


def load_source_approval(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise SystemExit(f"Source approval must be closed JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise SystemExit("Source approval must be a JSON object.")
    return validate_source_approval(value)


__all__ = (
    "SOURCE_KINDS",
    "_delegation_binding",
    "load_source_approval",
    "validate_source_approval",
)
