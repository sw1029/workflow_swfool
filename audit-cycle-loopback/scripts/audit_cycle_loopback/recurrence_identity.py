from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from typing import Any

from .recurrence_delta import (
    canonical_material_delta_receipt_sha256,
    validate_input_delta,
)


SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
OPAQUE_ID_RE = re.compile(r"^[^\x00-\x20/\\]{1,255}$")
APPLICABILITY = {"applicable", "not_applicable"}
TRANSITION_KINDS = {"none", "split", "merge", "reclassification", "correction"}
FindingAdder = Callable[[str, str, object], None]


def _opaque(value: object) -> bool:
    return isinstance(value, str) and bool(OPAQUE_ID_RE.fullmatch(value.strip()))


def _count(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _ids(value: object) -> bool:
    return (
        isinstance(value, list)
        and bool(value)
        and all(_opaque(item) for item in value)
        and len(value) == len(set(value))
    )


def canonical_root_identity_sha256(
    stable_root_id: object,
    root_predicate_id: object,
    root_scope_id: object,
) -> str:
    raw = json.dumps(
        {
            "stable_root_id": stable_root_id,
            "root_predicate_id": root_predicate_id,
            "root_scope_id": root_scope_id,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _validate_core(value: dict[str, Any], block: FindingAdder) -> None:
    required_ids = (
        "stable_root_id",
        "root_predicate_id",
        "root_scope_id",
        "facet_id",
        "local_family_id",
    )
    invalid_ids = [field for field in required_ids if not _opaque(value.get(field))]
    if invalid_ids:
        block(
            "recurrence_identity_ids_invalid",
            "applicable recurrence identity requires opaque stable root, facet, and local-family IDs",
            {"fields": invalid_ids},
        )
    count_fields = (
        "root_recurrence_count",
        "facet_recurrence_count",
        "local_family_attempt_count",
        "evaluation_debt_streak",
    )
    invalid_counts = [field for field in count_fields if not _count(value.get(field))]
    if invalid_counts:
        block(
            "recurrence_identity_counts_invalid",
            "recurrence and evaluation-debt counts must be non-negative integers",
            {"fields": invalid_counts},
        )
    for field, code in (
        ("prior_root_recurrence_count", "recurrence_prior_root_count_invalid"),
        ("prior_evaluation_debt_streak", "recurrence_prior_evaluation_debt_invalid"),
    ):
        if value.get(field) is not None and not _count(value.get(field)):
            block(code, f"{field} must be a non-negative integer when supplied", None)


def _validate_root_identity(
    value: dict[str, Any], transition_kind: str, block: FindingAdder
) -> bool | None:
    current = (
        value.get("stable_root_id"),
        value.get("root_predicate_id"),
        value.get("root_scope_id"),
    )
    current_digest = value.get("root_identity_sha256")
    current_valid = bool(
        all(_opaque(item) for item in current)
        and SHA256_RE.fullmatch(str(current_digest or ""))
        and current_digest == canonical_root_identity_sha256(*current)
    )
    if not current_valid:
        block(
            "recurrence_root_identity_binding_invalid",
            "stable root identity must bind root ID, violated-relation predicate, and applicable scope",
            None,
        )
    prior = (
        value.get("prior_stable_root_id"),
        value.get("prior_root_predicate_id"),
        value.get("prior_root_scope_id"),
    )
    prior_digest = value.get("prior_root_identity_sha256")
    prior_required = value.get("prior_root_recurrence_count") is not None or any(
        item is not None for item in (*prior, prior_digest)
    )
    prior_valid = bool(
        prior_required
        and all(_opaque(item) for item in prior)
        and SHA256_RE.fullmatch(str(prior_digest or ""))
        and prior_digest == canonical_root_identity_sha256(*prior)
    )
    if prior_required and not prior_valid:
        block(
            "recurrence_prior_root_identity_binding_invalid",
            "prior recurrence count requires a content-bound prior stable-root predicate and scope identity",
            None,
        )
    if not current_valid or not prior_valid:
        return None
    unchanged = current == prior
    declared_unchanged = value.get("root_predicate_unchanged")
    if isinstance(declared_unchanged, bool) and declared_unchanged is not unchanged:
        block(
            "recurrence_root_identity_echo_mismatch",
            "root_predicate_unchanged must be derived from the bound current and prior root identities",
            None,
        )
    if not unchanged and transition_kind == "none":
        block(
            "recurrence_root_identity_changed_without_lineage",
            "stable-root predicate or scope changes require split, merge, reclassification, or correction lineage",
            None,
        )
    if not unchanged and transition_kind != "none":
        transition = value.get("lineage_transition")
        parents = (
            transition.get("parent_root_ids") if isinstance(transition, dict) else []
        )
        children = (
            transition.get("child_root_ids") if isinstance(transition, dict) else []
        )
        if prior[0] not in parents or current[0] not in children:
            block(
                "recurrence_root_lineage_binding_mismatch",
                "lineage transition must connect the bound prior stable root to the current stable root",
                None,
            )
    return unchanged


def _validate_transition(transition: object, block: FindingAdder) -> str:
    if transition is None:
        return "none"
    if not isinstance(transition, dict):
        block(
            "recurrence_lineage_transition_invalid",
            "lineage_transition must be an object",
            None,
        )
        return "none"
    kind = str(transition.get("kind") or "")
    if kind not in TRANSITION_KINDS:
        block(
            "recurrence_lineage_transition_kind_invalid",
            "lineage transition kind is invalid",
            None,
        )
        return kind
    if kind == "none":
        return kind
    required = (
        _opaque(transition.get("transition_id")),
        _ids(transition.get("parent_root_ids")),
        _ids(transition.get("child_root_ids")),
        _count(transition.get("prior_attempt_lower_bound")),
        _count(transition.get("aggregate_recurrence_count")),
    )
    if not all(required):
        block(
            "recurrence_lineage_transition_incomplete",
            "lineage transition requires parent/child identity and conservative counts",
            None,
        )
    elif int(transition["aggregate_recurrence_count"]) < int(
        transition["prior_attempt_lower_bound"]
    ):
        block(
            "recurrence_lineage_attempts_lost",
            "aggregate recurrence cannot fall below the prior-attempt lower bound",
            None,
        )
    if kind == "correction":
        revision = transition.get("attempt_revision")
        supersedes = transition.get("supersedes_attempt_revision")
        revision_valid = (
            isinstance(revision, int)
            and not isinstance(revision, bool)
            and isinstance(supersedes, int)
            and not isinstance(supersedes, bool)
            and revision == supersedes + 1
        )
        if not _opaque(transition.get("logical_attempt_id")) or not revision_valid:
            block(
                "recurrence_correction_lineage_invalid",
                "correction must preserve one logical attempt and increment its revision",
                None,
            )
    return kind


def _validate_count_changes(
    value: dict[str, Any],
    transition: object,
    transition_kind: str,
    material_reset_allowed: bool,
    root_identity_unchanged: bool | None,
    block: FindingAdder,
) -> None:
    root_count = value.get("root_recurrence_count")
    prior_root_count = value.get("prior_root_recurrence_count")
    lower_root_count = bool(
        _count(root_count)
        and _count(prior_root_count)
        and int(root_count) < int(prior_root_count)
    )
    if (
        lower_root_count
        and root_identity_unchanged is not False
        and not material_reset_allowed
    ):
        block(
            "recurrence_root_count_reset_without_material_delta",
            "an unchanged stable root cannot reset from facet or label novelty",
            None,
        )
    if lower_root_count and transition_kind in {
        "split",
        "merge",
        "reclassification",
        "correction",
    }:
        aggregate = (
            transition.get("aggregate_recurrence_count")
            if isinstance(transition, dict)
            else None
        )
        if (
            not _count(aggregate)
            or not _count(prior_root_count)
            or int(aggregate) < int(prior_root_count)
        ):
            block(
                "recurrence_lineage_count_reset",
                "lineage transition must preserve the prior recurrence lower bound",
                None,
            )
    prior_debt = value.get("prior_evaluation_debt_streak")
    current_debt = value.get("evaluation_debt_streak")
    if (
        value.get("binding_status") == "not_evaluated"
        and _count(prior_debt)
        and _count(current_debt)
        and int(current_debt) <= int(prior_debt)
    ):
        block(
            "recurrence_evaluation_debt_not_incremented",
            "repeated not-evaluated binding must increase evaluation debt",
            None,
        )


def _projection(value: dict[str, Any]) -> dict[str, Any]:
    fields = (
        "applicability",
        "stable_root_id",
        "root_predicate_id",
        "root_scope_id",
        "root_identity_sha256",
        "prior_stable_root_id",
        "prior_root_predicate_id",
        "prior_root_scope_id",
        "prior_root_identity_sha256",
        "facet_id",
        "local_family_id",
        "root_recurrence_count",
        "prior_root_recurrence_count",
        "facet_recurrence_count",
        "local_family_attempt_count",
        "evaluation_debt_streak",
        "prior_evaluation_debt_streak",
        "root_predicate_unchanged",
        "binding_status",
    )
    projection = {field: value[field] for field in fields if field in value}
    nested_fields = {
        "supplied_input_delta": (
            "classification",
            "delta_id",
            "rationale_id",
            "full_content_sha256",
            "typed_difference_ids",
            "violated_relation_effect",
            "authority_premise_changed",
            "external_state_changed",
            "toolchain_premise_changed",
            "rationale_evidence_digest",
            "delta_receipt_sha256",
        ),
        "lineage_transition": (
            "kind",
            "transition_id",
            "parent_root_ids",
            "child_root_ids",
            "prior_attempt_lower_bound",
            "aggregate_recurrence_count",
            "logical_attempt_id",
            "attempt_revision",
            "supersedes_attempt_revision",
        ),
    }
    for key, allowed in nested_fields.items():
        nested = value.get(key)
        if isinstance(nested, dict):
            projection[key] = {
                field: nested[field] for field in allowed if field in nested
            }
    return projection


def evaluate_recurrence_identity(value: object) -> dict[str, Any]:
    """Validate caller-owned root/facet/local recurrence without inferring semantics."""

    if value is None:
        return {
            "applicability": "not_supplied",
            "status": "not_evaluated",
            "durable_update_required": False,
            "findings": [],
        }
    findings: list[dict[str, Any]] = []

    def block(code: str, message: str, evidence: object = None) -> None:
        row: dict[str, Any] = {"severity": "block", "code": code, "message": message}
        if evidence is not None:
            row["evidence"] = evidence
        findings.append(row)

    if not isinstance(value, dict):
        block("recurrence_identity_invalid", "recurrence identity must be an object")
        return {
            "applicability": "missing_required",
            "status": "block",
            "durable_update_required": False,
            "findings": findings,
        }
    applicability = str(value.get("applicability") or "")
    if applicability not in APPLICABILITY:
        block(
            "recurrence_identity_applicability_invalid",
            "recurrence identity requires explicit applicable or not_applicable state",
        )
    if applicability == "not_applicable":
        return {
            "applicability": applicability,
            "status": "pass" if not findings else "block",
            "durable_update_required": False,
            "findings": findings,
        }
    _validate_core(value, block)
    material_reset_allowed = validate_input_delta(
        value.get("supplied_input_delta"), block
    )
    transition = value.get("lineage_transition")
    transition_kind = _validate_transition(transition, block)
    root_identity_unchanged = _validate_root_identity(value, transition_kind, block)
    _validate_count_changes(
        value,
        transition,
        transition_kind,
        material_reset_allowed,
        root_identity_unchanged,
        block,
    )
    return {
        "applicability": applicability or "missing_required",
        "status": "block" if findings else "pass",
        "durable_update_required": applicability == "applicable" and not findings,
        "projection": _projection(value),
        "findings": findings,
    }


__all__ = (
    "canonical_material_delta_receipt_sha256",
    "canonical_root_identity_sha256",
    "evaluate_recurrence_identity",
)
