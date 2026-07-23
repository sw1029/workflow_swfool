"""Prepare producer-rendered ordinary root-grant approval plans."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from .artifact_store import verify_binding
from .canonical import (
    normalized_time,
    object_sha256,
    parse_time,
    read_object,
    sha256_file,
    write_immutable_json,
)
from .contracts import RISK_TIERS, SOURCE_RANKS
from .operation_batch import load_operation_batch
from .operation_compiler import compilation_inputs
from .source_approval import SOURCE_KINDS


ROOT_PLAN_SEMANTIC_KEYS = {
    "source_kind",
    "holder_rank",
    "expires_at",
    "session_id",
}
PLAN_KEYS = {
    "schema_version",
    "artifact_kind",
    "prepared_at",
    "operation_batch",
    "policy_snapshot",
    "grant_semantics",
    "approval_projection",
    "field_provenance",
    "plan_fingerprint",
}
LEGACY_DECISION_SEED_KEYS = {
    "schema_version",
    "artifact_kind",
    "approved",
    "approval_plan",
    "decided_at",
    "evidence_id",
}
DECISION_SEED_KEYS = LEGACY_DECISION_SEED_KEYS | {
    "authorization_evidence",
    "authorization_trust_class",
}
ROOT_PLAN_ROOT = Path(".task/authorization/root_approval_plans/sha256")


def _identifier(value: Any, label: str, *, nullable: bool = False) -> str | None:
    if value is None and nullable:
        return None
    normalized = str(value or "").strip()
    if (
        not normalized
        or len(normalized) > 128
        or "*" in normalized
        or "/" in normalized
    ):
        raise SystemExit(f"{label} must be a bounded exact identifier.")
    return normalized


def _normalize_semantics(value: Any, prepared_at: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != ROOT_PLAN_SEMANTIC_KEYS:
        raise SystemExit("Root-grant semantics must be a closed typed object.")
    source_kind = str(value["source_kind"])
    issuer_rank = SOURCE_KINDS.get(source_kind)
    if source_kind != "explicit_user_instruction" or issuer_rank != "S3":
        raise SystemExit(
            "Ordinary plan-bound root grants require "
            "explicit_user_instruction/S3; S4 requires a distinct "
            "platform-attested producer."
        )
    holder_rank = str(value["holder_rank"])
    if holder_rank not in SOURCE_RANKS or SOURCE_RANKS.index(
        issuer_rank
    ) <= SOURCE_RANKS.index(holder_rank):
        raise SystemExit("Root-grant holder rank must be below its source rank.")
    expires_at = normalized_time(value["expires_at"], "root grant expires_at")
    if parse_time(expires_at, "root grant expires_at") <= parse_time(
        prepared_at, "root grant prepared_at"
    ):
        raise SystemExit("Root-grant expiry must be after plan preparation.")
    return {
        "source_kind": source_kind,
        "holder_rank": holder_rank,
        "expires_at": expires_at,
        "session_id": _identifier(
            value["session_id"], "root grant session_id", nullable=True
        ),
    }


def _unique_objects(values: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduplicated = {object_sha256(item): copy.deepcopy(item) for item in values}
    return sorted(deduplicated.values(), key=lambda item: tuple(item.values()))


def _normalized_policy_binding(root: Path, binding: dict[str, str]) -> dict[str, str]:
    path = verify_binding(root, binding, "root approval policy snapshot")
    try:
        path.relative_to(root / ".task/authorization/policy_snapshots")
    except ValueError as exc:
        raise SystemExit(
            "Root approval plan requires a producer-owned policy snapshot."
        ) from exc
    normalized = {
        "ref": path.relative_to(root).as_posix(),
        "sha256": sha256_file(path),
    }
    if normalized != binding:
        raise SystemExit("Root approval policy binding is not canonical.")
    pointer_path = root / ".task/authorization/state/current_policy.json"
    if not pointer_path.is_file():
        raise SystemExit("Root approval requires a current policy pointer.")
    pointer = read_object(pointer_path, "current policy pointer")
    if (
        pointer.get("schema_version") != 2
        or pointer.get("artifact_kind") != "current_policy_pointer"
        or pointer.get("policy_snapshot") != normalized
    ):
        raise SystemExit(
            "Root approval policy snapshot is not the exact current policy."
        )
    return normalized


def _plan_scope(
    compilations: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    requests = [item["request"] for item in compilations]
    capabilities = sorted(
        {
            capability
            for request in requests
            for capability in request["required_capabilities"]
        }
    )
    operations = _unique_objects(
        [
            {
                key: request[key]
                for key in (
                    "skill_id",
                    "skill_version",
                    "operation_id",
                    "operation_version",
                )
            }
            for request in requests
        ]
    )
    scope = {
        "capabilities": capabilities,
        "subjects": _unique_objects([request["subject"] for request in requests]),
        "operations": operations,
        "risk_ceiling": max(
            [request["risk_tier"] for request in requests],
            key=RISK_TIERS.index,
        ),
        "decision_classes": sorted({request["decision_class"] for request in requests}),
        "request_digests": sorted(
            {compilation["request_sha256"] for compilation in compilations}
        ),
        "cardinalities": sorted(
            {request["cardinality_requested"] for request in requests}
        ),
    }
    return requests, scope


def _grant_projections(
    compilations: list[dict[str, Any]],
    requests: list[dict[str, Any]],
    semantics: dict[str, Any],
    identity: str,
    policy_snapshot: dict[str, str],
) -> list[dict[str, Any]]:
    grants = []
    for compilation, request in zip(compilations, requests):
        request_identity = object_sha256(
            {
                "plan_identity": identity,
                "request_sha256": compilation["request_sha256"],
            }
        )
        operation = {
            key: request[key]
            for key in (
                "skill_id",
                "skill_version",
                "operation_id",
                "operation_version",
            )
        }
        grants.append(
            {
                "grant_id": f"authg-{request_identity[:24]}",
                "lineage_id": f"authl-{request_identity[:24]}",
                "grant_idempotency_key": f"authgk-{request_identity[:24]}",
                "request_sha256": compilation["request_sha256"],
                "holder_rank": semantics["holder_rank"],
                "capabilities": request["required_capabilities"],
                "subjects": [request["subject"]],
                "operations": [operation],
                "risk_ceiling": request["risk_tier"],
                "decision_classes": [request["decision_class"]],
                "cardinality": request["cardinality_requested"],
                "max_uses": request["use_budget_requested"],
                "session_id": semantics["session_id"],
                "task_id": request["task_id"],
                "improvement_id": request["pack_id"],
                "policy_snapshot": policy_snapshot,
                "root_materialization_ref": (
                    ".task/authorization/root_grant_materializations/"
                    f"authrp-{identity[:24]}/receipt.json"
                ),
            }
        )
    return sorted(grants, key=lambda item: item["request_sha256"])


def _approval_projection(
    scope: dict[str, Any],
    grants: list[dict[str, Any]],
    semantics: dict[str, Any],
    identity: str,
    *,
    plan_schema_version: int,
) -> dict[str, Any]:
    source_coverage = {
        "capabilities": sorted(set(scope["capabilities"]) | {"authority.grant.issue"}),
        "subjects": scope["subjects"],
        "operations": scope["operations"],
        "risk_ceiling": scope["risk_ceiling"],
        "decision_classes": scope["decision_classes"],
        "cardinalities": scope["cardinalities"],
        "max_uses": max(grant["max_uses"] for grant in grants),
        "grant_ids": [grant["grant_id"] for grant in grants],
        "request_digests": scope["request_digests"],
        "lineage_ids": [grant["lineage_id"] for grant in grants],
    }
    return {
        "projection_id": f"authrp-{identity[:24]}",
        "typed_intent": "grant_authority",
        "source_kind": semantics["source_kind"],
        "source_rank": SOURCE_KINDS[semantics["source_kind"]],
        "approval_id": f"authsrc-{identity[:24]}",
        "source_coverage": source_coverage,
        "grants": grants,
        "validity": {
            "not_before_rule": "decision_time",
            "expires_at": semantics["expires_at"],
        },
        "decision_trust_class": (
            "host_user_signed_exact_plan"
            if plan_schema_version == 2
            else "caller_asserted_plan_decision"
        ),
        "excluded_effects": [
            (
                "no authority before signed exact-plan host/user evidence"
                if plan_schema_version == 2
                else "no authority before an explicit plan-bound approval seed"
            ),
            "no capability, subject, operation, risk, scope, budget, or time widening",
            (
                "no unsigned or caller-selected trust-anchor fallback"
                if plan_schema_version == 2
                else "no host or runtime attestation claim"
            ),
        ],
    }


def _build_plan(
    root: Path,
    operation_batch: dict[str, str],
    policy_snapshot: dict[str, str],
    grant_semantics: Any,
    *,
    prepared_at: str,
    skills_root: Path | None,
    plan_schema_version: int = 2,
) -> dict[str, Any]:
    root = root.resolve()
    at = normalized_time(prepared_at, "root approval prepared_at")
    batch_binding, batch, compilations = load_operation_batch(
        root, operation_batch, skills_root=skills_root
    )
    if batch.get("schema_version") == 2 and parse_time(
        at, "root approval prepared_at"
    ) <= parse_time(batch["compiled_at"], "projected operation batch compiled_at"):
        raise SystemExit(
            "Projected-operation root approval must be prepared after compilation."
        )
    for compilation in compilations:
        compilation_inputs(root, compilation, skills_root=skills_root)
        if not compilation["source_and_grant_requirements"]["requires_grant"]:
            raise SystemExit(
                "Root approval plans accept only grant-governed compilations."
            )
    policy_binding = _normalized_policy_binding(root, policy_snapshot)
    semantics = _normalize_semantics(grant_semantics, at)
    requests, scope = _plan_scope(compilations)
    if any(request["actor_rank"] != semantics["holder_rank"] for request in requests):
        raise SystemExit(
            "Root-grant holder rank must match every compiled operation actor."
        )
    if plan_schema_version not in {1, 2}:
        raise SystemExit("Root approval plan schema version is unsupported.")
    identity_seed = {
        "prepared_at": at,
        "operation_batch": batch_binding,
        "policy_snapshot": policy_binding,
        "grant_semantics": semantics,
        "capabilities": scope["capabilities"],
        "subjects": scope["subjects"],
        "operations": scope["operations"],
        "risk_ceiling": scope["risk_ceiling"],
        "decision_classes": scope["decision_classes"],
        "request_digests": scope["request_digests"],
    }
    if plan_schema_version == 2:
        identity_seed["authorization_trust_class"] = "host_user_signed_exact_plan"
    identity = object_sha256(identity_seed)
    grants = _grant_projections(
        compilations, requests, semantics, identity, policy_binding
    )
    projection = _approval_projection(
        scope,
        grants,
        semantics,
        identity,
        plan_schema_version=plan_schema_version,
    )
    body = {
        "schema_version": plan_schema_version,
        "artifact_kind": "authority_root_approval_plan",
        "prepared_at": at,
        "operation_batch": batch_binding,
        "policy_snapshot": policy_binding,
        "grant_semantics": semantics,
        "approval_projection": projection,
        "field_provenance": {
            "caller_semantic": sorted(ROOT_PLAN_SEMANTIC_KEYS),
            "batch_derived": [
                "capabilities",
                "subjects",
                "operations",
                "risk ceiling",
                "decision classes",
                "request digests",
            ],
            "compiler_derived": [
                "schema markers",
                "approval/grant/lineage/replay IDs",
                "projection and plan fingerprints",
                "CAS path",
            ],
            "authority_effect": "none",
            **(
                {"authorization_evidence": "host_user_signed_exact_plan_required"}
                if plan_schema_version == 2
                else {}
            ),
        },
    }
    return {**body, "plan_fingerprint": object_sha256(body)}


def prepare_root_approval_plan(
    root: Path,
    operation_batch: dict[str, str],
    policy_snapshot: dict[str, str],
    grant_semantics: Any,
    *,
    prepared_at: str,
    skills_root: Path | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    plan = _build_plan(
        root,
        operation_batch,
        policy_snapshot,
        grant_semantics,
        prepared_at=prepared_at,
        skills_root=skills_root,
    )
    fingerprint = plan["plan_fingerprint"]
    path = root / ROOT_PLAN_ROOT / f"{fingerprint}.json"
    digest = write_immutable_json(path, plan, "root approval plan")
    return {
        "status": "approval_required",
        "should_prompt": True,
        "root_approval_plan": {
            "ref": path.relative_to(root).as_posix(),
            "sha256": digest,
        },
        "approval_summary": {
            "projection_id": plan["approval_projection"]["projection_id"],
            "operation_count": len(plan["approval_projection"]["grants"]),
            "grant_count": len(plan["approval_projection"]["grants"]),
            "expires_at": plan["approval_projection"]["validity"]["expires_at"],
            "decision_seed_contract": {
                "schema_version": 3,
                "artifact_kind": "authority_root_approval_decision_seed",
                "required_binding": "authorization_evidence",
                "authorization_trust_class": "host_user_signed_exact_plan",
                "approval_plan": {
                    "ref": path.relative_to(root).as_posix(),
                    "sha256": digest,
                },
            },
        },
        "authority_effects_applied": False,
        "model_authored_mechanical_bytes": 0,
    }


def load_root_approval_plan(
    root: Path,
    binding: dict[str, str],
    *,
    skills_root: Path | None = None,
) -> tuple[dict[str, str], dict[str, Any]]:
    root = root.resolve()
    path = verify_binding(root, binding, "root approval plan")
    try:
        path.relative_to(root / ROOT_PLAN_ROOT)
    except ValueError as exc:
        raise SystemExit("Root approval plan is outside its producer CAS.") from exc
    value = read_object(path, "root approval plan")
    if not isinstance(value, dict) or set(value) != PLAN_KEYS:
        raise SystemExit("Root approval plan is not a closed typed object.")
    expected = _build_plan(
        root,
        value["operation_batch"],
        value["policy_snapshot"],
        value["grant_semantics"],
        prepared_at=value["prepared_at"],
        skills_root=skills_root,
        plan_schema_version=value.get("schema_version"),
    )
    if value != expected:
        raise SystemExit("Root approval plan differs from compiler rendering.")
    if path.name != f"{value['plan_fingerprint']}.json":
        raise SystemExit("Root approval plan CAS path is invalid.")
    normalized = {
        "ref": path.relative_to(root).as_posix(),
        "sha256": sha256_file(path),
    }
    if normalized != binding:
        raise SystemExit("Root approval plan binding is not canonical.")
    return normalized, value


__all__ = (
    "ROOT_PLAN_ROOT",
    "load_root_approval_plan",
    "prepare_root_approval_plan",
)
