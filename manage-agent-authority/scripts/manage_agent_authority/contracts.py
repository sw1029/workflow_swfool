from __future__ import annotations

import re
from typing import Any

from .canonical import normalized_time
from .canonical import parse_time


SOURCE_RANKS = ("S0", "S1", "S2", "S3", "S4")
RISK_TIERS = ("R0", "R1", "R2", "R3")
DECISION_CLASSES = ("D0", "D1", "D2", "D3")
DECISIONS = (
    "allowed",
    "approval_required",
    "denied",
    "waiting_external_input",
    "capability_unavailable",
    "blocked_by_goal_truth",
    "classification_repair",
    "conflict",
    "not_applicable",
)
CARDINALITIES = (
    "single_use",
    "bounded_reusable",
    "task_lease",
    "improvement_lease",
    "standing_policy",
)
INTENT_TYPES = (
    "grant_authority",
    "ratify_goal_truth",
    "accept_risk_or_cost",
    "supply_external_input",
    "select_design_option",
)
MUTATION_CLASSES = ("observe", "local_mutation", "external_mutation", "destructive")
REVERSIBILITY = ("reversible", "conditionally_reversible", "irreversible")
EXTERNAL_INPUT = (
    "not_required",
    "available",
    "missing_supplyable",
    "missing_unsupplyable",
    "unverified",
)
GOAL_TRUTH = ("aligned", "blocked", "unverified")
SEPARATE_DECISION_STATUS = ("not_required", "resolved", "unresolved", "unverified")
GRANT_STATES = (
    "draft",
    "active",
    "reserved",
    "suspended",
    "revoked",
    "expired",
    "exhausted",
)

IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
CAPABILITY_RE = re.compile(r"^[a-z][a-z0-9_-]*(?:\.[a-z][a-z0-9_-]*)+$")
SHA_RE = re.compile(r"^[0-9a-f]{64}$")

REQUEST_KEYS = {
    "schema_version",
    "request_kind",
    "request_id",
    "skill_id",
    "skill_version",
    "operation_id",
    "operation_version",
    "cycle_id",
    "task_id",
    "pack_id",
    "attempt_id",
    "actor_rank",
    "subject",
    "required_capabilities",
    "effect_class",
    "data_class",
    "mutation_class",
    "reversibility",
    "risk_tier",
    "decision_class",
    "intent_type",
    "cardinality_requested",
    "use_budget_requested",
    "reservation_units",
    "idempotency_key",
    "context",
    "composition_receipt",
}
REQUIRED_REQUEST_KEYS = REQUEST_KEYS - {"reservation_units"}
SUBJECT_KEYS = {"kind", "ref", "digest", "revision"}
CONTEXT_KEYS = {
    "external_input_status",
    "goal_truth_status",
    "risk_acceptance_status",
    "design_selection_status",
    "external_input_evidence",
    "risk_acceptance_evidence",
    "design_selection_evidence",
}
GRANT_KEYS = {
    "schema_version",
    "artifact_kind",
    "grant_id",
    "lineage_id",
    "parent_grant_id",
    "issuer_rank",
    "holder_rank",
    "capabilities",
    "subjects",
    "operations",
    "risk_ceiling",
    "decision_classes",
    "cardinality",
    "max_uses",
    "not_before",
    "expires_at",
    "session_id",
    "task_id",
    "improvement_id",
    "source_approval",
    "policy_snapshot",
    "created_at",
    "idempotency_key",
}
OPERATION_SCOPE_KEYS = {
    "skill_id",
    "skill_version",
    "operation_id",
    "operation_version",
}
BINDING_KEYS = {"ref", "sha256"}


def _closed(value: dict[str, Any], allowed: set[str], label: str) -> None:
    extra = sorted(set(value) - allowed)
    if extra:
        raise SystemExit(f"{label} contains unknown fields: {', '.join(extra)}")


def _required(value: dict[str, Any], fields: set[str], label: str) -> None:
    missing = sorted(field for field in fields if field not in value)
    if missing:
        raise SystemExit(f"{label} is missing fields: {', '.join(missing)}")


def _enum(value: Any, allowed: tuple[str, ...], label: str) -> str:
    normalized = str(value or "")
    if normalized not in allowed:
        raise SystemExit(f"{label} must be one of: {', '.join(allowed)}")
    return normalized


def _identifier(value: Any, label: str, *, nullable: bool = False) -> str | None:
    if value is None and nullable:
        return None
    normalized = str(value or "").strip()
    if not IDENTIFIER_RE.fullmatch(normalized):
        raise SystemExit(f"{label} must be a bounded opaque identifier.")
    return normalized


def _sha(value: Any, label: str) -> str:
    normalized = str(value or "").removeprefix("sha256:").lower()
    if not SHA_RE.fullmatch(normalized):
        raise SystemExit(f"{label} must be a lowercase SHA-256 digest.")
    return normalized


def _capabilities(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise SystemExit(f"{label} must be a non-empty capability list.")
    normalized = sorted(set(str(item) for item in value))
    if len(normalized) != len(value) or any(
        not CAPABILITY_RE.fullmatch(item) for item in normalized
    ):
        raise SystemExit(
            f"{label} must contain unique namespaced capabilities without wildcards."
        )
    return normalized


def validate_subject(value: Any, label: str = "subject") -> dict[str, str]:
    if not isinstance(value, dict):
        raise SystemExit(f"{label} must be an object.")
    _closed(value, SUBJECT_KEYS, label)
    _required(value, SUBJECT_KEYS, label)
    kind = _identifier(value["kind"], f"{label}.kind")
    ref = str(value["ref"] or "").strip()
    revision = str(value["revision"] or "").strip()
    if not ref or len(ref) > 512 or "*" in ref:
        raise SystemExit(
            f"{label}.ref must be an exact bounded reference without wildcards."
        )
    if not revision or len(revision) > 256 or "*" in revision:
        raise SystemExit(f"{label}.revision must be exact and bounded.")
    return {
        "kind": kind,
        "ref": ref,
        "digest": _sha(value["digest"], f"{label}.digest"),
        "revision": revision,
    }


def validate_request(value: dict[str, Any]) -> dict[str, Any]:
    _closed(value, REQUEST_KEYS, "authority request")
    _required(value, REQUIRED_REQUEST_KEYS, "authority request")
    if (
        value.get("schema_version") != 2
        or value.get("request_kind") != "authority_operation"
    ):
        raise SystemExit(
            "Authority request requires schema_version=2 and request_kind=authority_operation."
        )
    context = value.get("context")
    if not isinstance(context, dict):
        raise SystemExit("authority request.context must be an object.")
    _closed(context, CONTEXT_KEYS, "authority request.context")
    _required(context, CONTEXT_KEYS, "authority request.context")
    budget = value.get("use_budget_requested")
    if not isinstance(budget, int) or isinstance(budget, bool) or budget < 1:
        raise SystemExit("use_budget_requested must be a positive integer.")
    raw_reservation_units = value.get("reservation_units")
    if raw_reservation_units is not None and (
        not isinstance(raw_reservation_units, int)
        or isinstance(raw_reservation_units, bool)
        or raw_reservation_units < 1
    ):
        raise SystemExit("reservation_units must be a positive integer when present.")
    # Requests written before reservation_units existed retain their historical
    # semantics. New callers must set reservation_units explicitly (normally 1)
    # so a reusable approval budget is not spent by one dispatch.
    units = budget if raw_reservation_units is None else raw_reservation_units
    if units > budget:
        raise SystemExit("reservation_units cannot exceed use_budget_requested.")
    cardinality = _enum(
        value["cardinality_requested"], CARDINALITIES, "cardinality_requested"
    )
    task_id = _identifier(value["task_id"], "task_id", nullable=True)
    pack_id = _identifier(value["pack_id"], "pack_id", nullable=True)
    if cardinality == "single_use" and budget != 1:
        raise SystemExit("single_use requests require use_budget_requested=1.")
    if cardinality == "single_use" and units != 1:
        raise SystemExit("single_use requests require reservation_units=1.")
    if cardinality == "task_lease" and task_id is None:
        raise SystemExit("task_lease requests require an exact task_id.")
    if cardinality == "improvement_lease" and pack_id is None:
        raise SystemExit("improvement_lease requests require an exact pack_id.")
    composition = value.get("composition_receipt")
    if composition is not None:
        if not isinstance(composition, dict):
            raise SystemExit("composition_receipt must be null or a ref/sha256 object.")
        _closed(composition, BINDING_KEYS, "composition_receipt")
        _required(composition, BINDING_KEYS, "composition_receipt")
        composition = {
            "ref": str(composition["ref"]),
            "sha256": _sha(composition["sha256"], "composition_receipt.sha256"),
        }
    evidence: dict[str, dict[str, str] | None] = {}
    evidence_rules = {
        "external_input_evidence": context["external_input_status"]
        in {"available", "missing_supplyable", "missing_unsupplyable"},
        "risk_acceptance_evidence": context["risk_acceptance_status"] == "resolved",
        "design_selection_evidence": context["design_selection_status"] == "resolved",
    }
    for field, required in evidence_rules.items():
        candidate = context[field]
        if required and candidate is None:
            raise SystemExit(
                f"context.{field} is required for the asserted positive/resolved status."
            )
        if not required and candidate is not None:
            raise SystemExit(
                f"context.{field} must be null when its decision/status is not evidence-backed."
            )
        evidence[field] = (
            _binding(candidate, f"context.{field}") if candidate is not None else None
        )
    normalized = {
        "schema_version": 2,
        "request_kind": "authority_operation",
        "request_id": _identifier(value["request_id"], "request_id"),
        "skill_id": _identifier(value["skill_id"], "skill_id"),
        "skill_version": _identifier(value["skill_version"], "skill_version"),
        "operation_id": _identifier(value["operation_id"], "operation_id"),
        "operation_version": _identifier(
            value["operation_version"], "operation_version"
        ),
        "cycle_id": _identifier(value["cycle_id"], "cycle_id", nullable=True),
        "task_id": task_id,
        "pack_id": pack_id,
        "attempt_id": _identifier(value["attempt_id"], "attempt_id", nullable=True),
        "actor_rank": _enum(value["actor_rank"], SOURCE_RANKS, "actor_rank"),
        "subject": validate_subject(value["subject"]),
        "required_capabilities": _capabilities(
            value["required_capabilities"], "required_capabilities"
        ),
        "effect_class": _identifier(value["effect_class"], "effect_class"),
        "data_class": _identifier(value["data_class"], "data_class"),
        "mutation_class": _enum(
            value["mutation_class"], MUTATION_CLASSES, "mutation_class"
        ),
        "reversibility": _enum(value["reversibility"], REVERSIBILITY, "reversibility"),
        "risk_tier": _enum(value["risk_tier"], RISK_TIERS, "risk_tier"),
        "decision_class": _enum(
            value["decision_class"], DECISION_CLASSES, "decision_class"
        ),
        "intent_type": _enum(value["intent_type"], INTENT_TYPES, "intent_type"),
        "cardinality_requested": cardinality,
        "use_budget_requested": budget,
        "idempotency_key": _identifier(value["idempotency_key"], "idempotency_key"),
        "context": {
            "external_input_status": _enum(
                context["external_input_status"],
                EXTERNAL_INPUT,
                "context.external_input_status",
            ),
            "goal_truth_status": _enum(
                context["goal_truth_status"], GOAL_TRUTH, "context.goal_truth_status"
            ),
            "risk_acceptance_status": _enum(
                context["risk_acceptance_status"],
                SEPARATE_DECISION_STATUS,
                "context.risk_acceptance_status",
            ),
            "design_selection_status": _enum(
                context["design_selection_status"],
                SEPARATE_DECISION_STATUS,
                "context.design_selection_status",
            ),
            **evidence,
        },
        "composition_receipt": composition,
    }
    if raw_reservation_units is not None:
        normalized["reservation_units"] = units
    return normalized


def reservation_units(request: dict[str, Any]) -> int:
    """Return dispatch units while preserving pre-field request semantics."""
    return int(request.get("reservation_units", request["use_budget_requested"]))


def _binding(value: Any, label: str) -> dict[str, str]:
    if not isinstance(value, dict):
        raise SystemExit(f"{label} must be a ref/sha256 object.")
    _closed(value, BINDING_KEYS, label)
    _required(value, BINDING_KEYS, label)
    ref = str(value["ref"] or "").strip()
    if not ref or PathLikeUnsafe(ref):
        raise SystemExit(f"{label}.ref must be an exact workspace-relative reference.")
    return {"ref": ref, "sha256": _sha(value["sha256"], f"{label}.sha256")}


def PathLikeUnsafe(value: str) -> bool:
    return value.startswith("/") or "*" in value or ".." in value.split("/")


def validate_grant(value: dict[str, Any]) -> dict[str, Any]:
    _closed(value, GRANT_KEYS, "authority grant")
    _required(value, GRANT_KEYS, "authority grant")
    if (
        value.get("schema_version") != 2
        or value.get("artifact_kind") != "authority_grant"
    ):
        raise SystemExit(
            "Authority grant requires schema_version=2 and artifact_kind=authority_grant."
        )
    subjects = value.get("subjects")
    if not isinstance(subjects, list) or not subjects:
        raise SystemExit("authority grant.subjects must be non-empty.")
    normalized_subjects = [
        validate_subject(item, f"subjects[{index}]")
        for index, item in enumerate(subjects)
    ]
    if len({tuple(item.values()) for item in normalized_subjects}) != len(
        normalized_subjects
    ):
        raise SystemExit("authority grant.subjects must be unique.")
    operations = value.get("operations")
    if not isinstance(operations, list) or not operations:
        raise SystemExit("authority grant.operations must be non-empty.")
    normalized_operations: list[dict[str, str]] = []
    for index, operation in enumerate(operations):
        if not isinstance(operation, dict):
            raise SystemExit(f"operations[{index}] must be an object.")
        _closed(operation, OPERATION_SCOPE_KEYS, f"operations[{index}]")
        _required(operation, OPERATION_SCOPE_KEYS, f"operations[{index}]")
        normalized_operations.append(
            {
                key: _identifier(operation[key], f"operations[{index}].{key}")
                for key in sorted(OPERATION_SCOPE_KEYS)
            }
        )
    cardinality = _enum(value["cardinality"], CARDINALITIES, "cardinality")
    max_uses = value.get("max_uses")
    if max_uses is not None and (
        not isinstance(max_uses, int) or isinstance(max_uses, bool) or max_uses < 1
    ):
        raise SystemExit("max_uses must be null or a positive integer.")
    if cardinality == "single_use" and max_uses != 1:
        raise SystemExit("single_use grants require max_uses=1.")
    if cardinality == "bounded_reusable" and max_uses is None:
        raise SystemExit("bounded_reusable grants require a finite max_uses.")
    if cardinality == "task_lease" and not value.get("task_id"):
        raise SystemExit("task_lease grants require task_id.")
    if cardinality == "improvement_lease" and not value.get("improvement_id"):
        raise SystemExit("improvement_lease grants require improvement_id.")
    not_before = normalized_time(value["not_before"], "not_before")
    expires_at = (
        normalized_time(value["expires_at"], "expires_at")
        if value.get("expires_at") is not None
        else None
    )
    if expires_at and parse_time(expires_at, "expires_at") <= parse_time(
        not_before, "not_before"
    ):
        raise SystemExit("expires_at must be after not_before.")
    issuer = _enum(value["issuer_rank"], SOURCE_RANKS, "issuer_rank")
    holder = _enum(value["holder_rank"], SOURCE_RANKS, "holder_rank")
    if SOURCE_RANKS.index(issuer) <= SOURCE_RANKS.index(holder):
        raise SystemExit("issuer_rank must be higher than holder_rank.")
    decisions = value.get("decision_classes")
    if not isinstance(decisions, list) or not decisions:
        raise SystemExit("decision_classes must be non-empty.")
    normalized_decisions = sorted(set(str(item) for item in decisions))
    if len(normalized_decisions) != len(decisions) or any(
        item not in DECISION_CLASSES for item in normalized_decisions
    ):
        raise SystemExit(
            "decision_classes must contain unique closed decision classes."
        )
    return {
        "schema_version": 2,
        "artifact_kind": "authority_grant",
        "grant_id": _identifier(value["grant_id"], "grant_id"),
        "lineage_id": _identifier(value["lineage_id"], "lineage_id"),
        "parent_grant_id": _identifier(
            value["parent_grant_id"], "parent_grant_id", nullable=True
        ),
        "issuer_rank": issuer,
        "holder_rank": holder,
        "capabilities": _capabilities(value["capabilities"], "capabilities"),
        "subjects": sorted(normalized_subjects, key=lambda item: tuple(item.values())),
        "operations": sorted(
            normalized_operations, key=lambda item: tuple(item.values())
        ),
        "risk_ceiling": _enum(value["risk_ceiling"], RISK_TIERS, "risk_ceiling"),
        "decision_classes": normalized_decisions,
        "cardinality": cardinality,
        "max_uses": max_uses,
        "not_before": not_before,
        "expires_at": expires_at,
        "session_id": _identifier(value["session_id"], "session_id", nullable=True),
        "task_id": _identifier(value["task_id"], "task_id", nullable=True),
        "improvement_id": _identifier(
            value["improvement_id"], "improvement_id", nullable=True
        ),
        "source_approval": _binding(value["source_approval"], "source_approval"),
        "policy_snapshot": _binding(value["policy_snapshot"], "policy_snapshot"),
        "created_at": normalized_time(value["created_at"], "created_at"),
        "idempotency_key": _identifier(value["idempotency_key"], "idempotency_key"),
    }


def rank_value(rank: str) -> int:
    return SOURCE_RANKS.index(rank)


def risk_value(risk: str) -> int:
    return RISK_TIERS.index(risk)


def cardinality_covers(grant: str, requested: str) -> bool:
    compatibility = {
        "single_use": set(CARDINALITIES),
        "bounded_reusable": {"bounded_reusable", "standing_policy"},
        "task_lease": {"task_lease", "standing_policy"},
        "improvement_lease": {"improvement_lease", "standing_policy"},
        "standing_policy": {"standing_policy"},
    }
    return grant in compatibility[requested]
