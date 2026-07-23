"""Render an approved recovery recipe into exact authority artifacts.

This module does not decide approval.  It accepts only a separately supplied,
hash-bound user-decision artifact that echoes the complete approval projection.
All remaining source-approval, grant, request, and decision bytes are mechanical
derivations from the previously published recovery recipe.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .artifact_store import (
    _register_compiled_grant,
    snapshot_file,
    verify_binding,
)
from .canonical import object_sha256, parse_time, read_object, sha256_file
from .canonical import write_immutable_json
from .evaluator import evaluate
from .producer_capability import _AUTHORITY_PRODUCER_CAPABILITY
from .source_recovery import _validated_recipe_path


USER_DECISION_KEYS = {
    "schema_version",
    "artifact_kind",
    "decision",
    "recovery_recipe",
    "approval_projection",
    "decided_at",
    "evidence_id",
}


def validate_recovery_user_decision(
    value: Any,
    *,
    recipe_binding: dict[str, str],
    recipe: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != USER_DECISION_KEYS:
        raise SystemExit("Recovery user decision must be a closed typed object.")
    if (
        value.get("schema_version") != 1
        or value.get("artifact_kind") != "authority_recovery_user_decision"
        or value.get("decision") != "approved"
        or value.get("recovery_recipe") != recipe_binding
        or value.get("approval_projection") != recipe.get("approval_projection")
    ):
        raise SystemExit("Recovery user decision does not approve the exact projection.")
    decided_at = parse_time(value.get("decided_at"), "recovery user decided_at")
    prepared_at = parse_time(recipe.get("prepared_at"), "recovery recipe prepared_at")
    if decided_at < prepared_at:
        raise SystemExit("Recovery user decision predates the prepared projection.")
    expiry = recipe["source_approval_requirements"].get("expires_at_ceiling")
    if expiry and decided_at >= parse_time(expiry, "recovery approval expiry"):
        raise SystemExit("Recovery user decision is outside the approval window.")
    evidence_id = str(value.get("evidence_id") or "").strip()
    if not evidence_id or len(evidence_id) > 128 or "*" in evidence_id:
        raise SystemExit("Recovery user decision evidence_id is invalid.")
    return {**value, "decided_at": decided_at.isoformat(), "evidence_id": evidence_id}


def _load_validated_recipe(
    root: Path,
    binding: dict[str, str],
    *,
    evaluated_at: str,
    skills_root: Path | None,
) -> tuple[Path, dict[str, Any]]:
    path = verify_binding(root, binding, "source recovery recipe")
    recipe = read_object(path, "source recovery recipe")
    exhausted = recipe.get("exhausted_authority")
    decision_binding = exhausted.get("decision") if isinstance(exhausted, dict) else None
    request_sha256 = (
        decision_binding.get("request_sha256")
        if isinstance(decision_binding, dict)
        else None
    )
    if not isinstance(request_sha256, str):
        raise SystemExit("Source recovery recipe lacks its original request binding.")
    validated = _validated_recipe_path(
        root,
        path,
        request_sha256,
        evaluated_at,
        skills_root,
    )
    if validated is None or validated["continuation_status"] != "approval_actionable":
        raise SystemExit("Source recovery recipe is stale or no longer actionable.")
    return path, recipe


def _source_approval(
    recipe: dict[str, Any],
    decision: dict[str, Any],
    decision_binding: dict[str, str],
) -> dict[str, Any]:
    requirement = recipe["source_approval_requirements"]
    return {
        "schema_version": 3,
        "artifact_kind": "authority_source_approval",
        "approval_id": requirement["approval_id"],
        "source_kind": requirement["source_kind_required"],
        "source_rank": requirement["source_rank_required"],
        "decision_type": requirement["decision_type_required"],
        "capabilities": requirement["capabilities_required"],
        "subjects": requirement["subjects_required"],
        "operations": requirement["operations_required"],
        "risk_ceiling": requirement["risk_ceiling_required"],
        "decision_classes": requirement["decision_classes_required"],
        "cardinalities": requirement["cardinalities_required"],
        "max_uses": requirement["max_uses_required"],
        "grant_ids": requirement["grant_ids_required"],
        "request_digests": requirement["request_digests_required"],
        "lineage_ids": requirement["lineage_ids_required"],
        "delegation_binding": requirement["delegation_binding_required"],
        "not_before": decision["decided_at"],
        "expires_at": requirement["expires_at_ceiling"],
        "evidence_id": decision["evidence_id"],
        "decision_binding": decision_binding,
        "decision_trust_class": "caller_asserted_exact_echo",
    }


def _grant(
    recipe: dict[str, Any],
    decision: dict[str, Any],
    source_binding: dict[str, str],
) -> dict[str, Any]:
    requirement = recipe["grant_requirements"]
    return {
        "schema_version": 2,
        "artifact_kind": "authority_grant",
        "grant_id": requirement["grant_id"],
        "lineage_id": requirement["lineage_id"],
        "parent_grant_id": requirement["parent_grant_id_required"],
        "issuer_rank": requirement["issuer_rank_required"],
        "holder_rank": requirement["holder_rank_required"],
        "capabilities": requirement["capabilities_required"],
        "subjects": requirement["subjects_required"],
        "operations": requirement["operations_required"],
        "risk_ceiling": requirement["risk_ceiling_required"],
        "decision_classes": requirement["decision_classes_required"],
        "cardinality": requirement["cardinality_required"],
        "max_uses": requirement["max_uses_required"],
        "not_before": decision["decided_at"],
        "expires_at": requirement["expires_at_ceiling"],
        "session_id": requirement["session_id_required"],
        "task_id": requirement["task_id_required"],
        "improvement_id": requirement["improvement_id_required"],
        "source_approval": source_binding,
        "policy_snapshot": requirement["policy_snapshot_required"],
        "created_at": decision["decided_at"],
        "idempotency_key": requirement["idempotency_key_required"],
    }


def materialize_approved_recovery(
    root: Path,
    recipe_binding: dict[str, str],
    user_decision_binding: dict[str, str],
    *,
    skills_root: Path | None,
) -> dict[str, Any]:
    root = root.resolve()
    user_path = verify_binding(root, user_decision_binding, "recovery user decision")
    normalized_user_decision_binding = {
        "ref": user_path.relative_to(root).as_posix(),
        "sha256": sha256_file(user_path),
    }
    if normalized_user_decision_binding != user_decision_binding:
        raise SystemExit("Recovery user decision binding is not canonical.")
    raw_user_decision = read_object(user_path, "recovery user decision")
    decided_at = str(raw_user_decision.get("decided_at") or "")
    recipe_path, recipe = _load_validated_recipe(
        root,
        recipe_binding,
        evaluated_at=decided_at,
        skills_root=skills_root,
    )
    normalized_recipe_binding = {
        "ref": recipe_path.relative_to(root).as_posix(),
        "sha256": sha256_file(recipe_path),
    }
    if normalized_recipe_binding != recipe_binding:
        raise SystemExit("Recovery recipe binding is not canonical.")
    user_decision = validate_recovery_user_decision(
        raw_user_decision,
        recipe_binding=recipe_binding,
        recipe=recipe,
    )
    identity = recipe["recovery_identity"]
    directory = root / ".task/authorization/recovery_materializations" / identity
    source = _source_approval(
        recipe, user_decision, normalized_user_decision_binding
    )
    source_path = directory / "source_approval.json"
    write_immutable_json(source_path, source, "approved recovery source approval")
    source_binding = snapshot_file(
        root, source_path.relative_to(root).as_posix(), "source_approval"
    )
    grant = _grant(recipe, user_decision, source_binding)
    registered = _register_compiled_grant(
        root,
        grant,
        producer_capability=_AUTHORITY_PRODUCER_CAPABILITY,
    )

    exhausted_decision = recipe["exhausted_authority"]["decision"]
    original_path = verify_binding(
        root,
        {key: exhausted_decision[key] for key in ("ref", "sha256")},
        "exhausted authority decision",
    )
    original_decision = read_object(original_path, "exhausted authority decision")
    replacement_request = recipe["replacement_request"]
    replacement = evaluate(
        root,
        replacement_request,
        original_decision["evaluation_context"],
        evaluated_at=user_decision["decided_at"],
        skills_root=skills_root,
    )
    decision_path = (
        root
        / ".task/authorization/decisions"
        / f"{replacement['decision_id']}.json"
    )
    decision_digest = write_immutable_json(
        decision_path, replacement, "approved recovery authority decision"
    )
    if replacement["decision"] != "allowed":
        raise SystemExit("Approved recovery materialization did not yield an allowed decision.")
    core = {
        "schema_version": 1,
        "artifact_kind": "authority_recovery_materialization_receipt",
        "recovery_recipe": recipe_binding,
        "user_decision": user_decision_binding,
        "source_approval": source_binding,
        "grant": {
            "ref": f".task/authorization/grants/{grant['grant_id']}.json",
            "sha256": registered["grant_sha256"],
        },
        "replacement_request_sha256": object_sha256(replacement_request),
        "decision": {
            "ref": decision_path.relative_to(root).as_posix(),
            "sha256": decision_digest,
        },
        "materialized_at": user_decision["decided_at"],
    }
    receipt = {
        "receipt_id": f"authrm-{object_sha256(core)[:24]}",
        **core,
    }
    receipt_path = directory / "receipt.json"
    receipt_digest = write_immutable_json(
        receipt_path, receipt, "approved recovery materialization receipt"
    )
    return {
        "status": "materialized",
        "authority_status": "allowed",
        "recovery_materialization": {
            "ref": receipt_path.relative_to(root).as_posix(),
            "sha256": receipt_digest,
        },
        "receipt": receipt,
        "replacement_request": replacement_request,
        "decision": replacement,
    }


__all__ = ("materialize_approved_recovery", "validate_recovery_user_decision")
