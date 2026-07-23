"""Verify schema-v3/v4 approvals against registered decision producers."""

from __future__ import annotations

from contextvars import ContextVar
from pathlib import Path
from typing import Any

from .canonical import (
    object_sha256,
    parse_time,
    read_object,
    resolve_workspace_path,
    sha256_file,
)
from .source_approval_contract import _delegation_binding


_ACTIVE_DECISION_VALIDATIONS: ContextVar[
    frozenset[tuple[str, str, str]]
] = ContextVar("active_authority_source_decision_validations", default=frozenset())


def _bound_object(
    root: Path, binding: dict[str, str], label: str
) -> tuple[Path, dict[str, Any]]:
    normalized = _delegation_binding(binding, True)
    assert normalized is not None
    path = resolve_workspace_path(root.resolve(), normalized["ref"], f"{label}.ref")
    if sha256_file(path) != normalized["sha256"]:
        raise SystemExit(f"{label} digest mismatch.")
    return path, read_object(path, label)


def _require_source_fields(
    approval: dict[str, Any], expected: dict[str, Any], label: str
) -> None:
    differing = sorted(
        field
        for field, expected_value in expected.items()
        if approval.get(field) != expected_value
    )
    if differing:
        raise SystemExit(
            f"{label} does not derive the exact source fields: {', '.join(differing)}."
        )


def _canonical_exact_values(value: Any) -> Any:
    """Mirror source-approval normalization for set-valued exact IDs."""

    return sorted(value) if isinstance(value, list) else value


def _root_decision_mode(
    approval: dict[str, Any], decision: dict[str, Any]
) -> str:
    kind = decision.get("artifact_kind")
    legacy = kind == "authority_root_approval_decision"
    decision_keys = (
        {
            "schema_version",
            "artifact_kind",
            "decision",
            "approval_plan",
            "approval_projection",
            "decided_at",
            "evidence_id",
        }
        if legacy
        else {
            "schema_version",
            "artifact_kind",
            "approved",
            "approval_plan",
            "decided_at",
            "evidence_id",
        }
        | (
            {"authorization_evidence", "authorization_trust_class"}
            if decision.get("schema_version") == 3
            else set()
        )
    )
    if legacy:
        valid_decision = (
            decision.get("schema_version") == 1
            and decision.get("decision") == "approved"
            and approval.get("schema_version") == 3
            and approval.get("decision_trust_class")
            == "caller_asserted_exact_echo"
        )
    else:
        if decision.get("schema_version") == 2:
            valid_decision = (
                kind == "authority_root_approval_decision_seed"
                and decision.get("approved") is True
                and approval.get("schema_version") == 4
                and approval.get("decision_trust_class")
                == "caller_asserted_plan_decision"
            )
        else:
            valid_decision = (
                kind == "authority_root_approval_decision_seed"
                and decision.get("schema_version") == 3
                and decision.get("approved") is True
                and decision.get("authorization_trust_class")
                == "host_user_signed_exact_plan"
                and approval.get("schema_version") == 5
                and approval.get("decision_trust_class")
                == "host_user_signed_exact_plan"
            )
    if set(decision) != decision_keys or not valid_decision:
        raise SystemExit("Root source decision contract is invalid.")
    if legacy:
        return "legacy_full_echo"
    return (
        "legacy_caller_seed"
        if decision.get("schema_version") == 2
        else "host_user_signed_seed"
    )


def _validate_compiled_root_seed(
    root: Path,
    approval: dict[str, Any],
    decision: dict[str, Any],
    *,
    mode: str,
) -> None:
    if mode == "legacy_full_echo":
        return
    from .root_decision_seed import load_root_decision_seed

    normalized_seed_binding, rendered_seed, _rendered_plan = (
        load_root_decision_seed(root, approval["decision_binding"])
    )
    if (
        normalized_seed_binding != approval["decision_binding"]
        or rendered_seed != decision
    ):
        raise SystemExit(
            "Root source decision is not a producer-rendered seed."
        )


def _load_root_decision_plan(
    root: Path, decision: dict[str, Any]
) -> dict[str, Any]:
    plan_path, plan = _bound_object(
        root, decision["approval_plan"], "source root approval plan"
    )
    plan_keys = {
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
    if (
        set(plan) != plan_keys
        or plan.get("schema_version") not in {1, 2}
        or plan.get("artifact_kind") != "authority_root_approval_plan"
    ):
        raise SystemExit(
            "Root source decision does not bind an exact root approval plan."
        )
    plan_body = {
        key: plan[key] for key in plan_keys if key != "plan_fingerprint"
    }
    expected_parent = (
        root.resolve() / ".task/authorization/root_approval_plans/sha256"
    )
    if (
        plan["plan_fingerprint"] != object_sha256(plan_body)
        or plan_path.parent != expected_parent
        or plan_path.name != f"{plan['plan_fingerprint']}.json"
    ):
        raise SystemExit("Source root approval plan CAS is invalid.")
    from .root_grant import load_root_approval_plan

    normalized_plan_binding, rendered_plan = load_root_approval_plan(
        root, decision["approval_plan"]
    )
    if normalized_plan_binding != decision["approval_plan"] or rendered_plan != plan:
        raise SystemExit(
            "Source root approval plan is not producer-rendered."
        )
    return plan


def _root_projection_source_fields(
    projection: dict[str, Any],
    coverage: dict[str, Any],
    decision: dict[str, Any],
    *,
    decided_at: str,
    expires_at: Any,
    mode: str,
) -> dict[str, Any]:
    return {
        "approval_id": projection.get("approval_id"),
        "source_kind": "explicit_user_instruction",
        "source_rank": "S3",
        "decision_type": "grant_authority",
        "capabilities": coverage.get("capabilities"),
        "subjects": coverage.get("subjects"),
        "operations": coverage.get("operations"),
        "risk_ceiling": coverage.get("risk_ceiling"),
        "decision_classes": coverage.get("decision_classes"),
        "cardinalities": coverage.get("cardinalities"),
        "max_uses": coverage.get("max_uses"),
        "grant_ids": _canonical_exact_values(coverage.get("grant_ids")),
        "request_digests": coverage.get("request_digests"),
        "lineage_ids": _canonical_exact_values(coverage.get("lineage_ids")),
        "delegation_binding": None,
        "not_before": decided_at,
        "expires_at": (
            parse_time(
                expires_at, "root source expires_at"
            ).isoformat()
            if expires_at
            else None
        ),
        "evidence_id": str(decision.get("evidence_id") or ""),
        **(
            {"grant_projections": projection.get("grants")}
            if mode != "legacy_full_echo"
            else {}
        ),
    }


def _validate_root_projection(
    approval: dict[str, Any],
    decision: dict[str, Any],
    plan: dict[str, Any],
    *,
    mode: str,
) -> None:
    projection = plan["approval_projection"]
    if (
        mode == "legacy_full_echo"
        and projection != decision.get("approval_projection")
    ):
        raise SystemExit(
            "Historical root source decision does not echo its exact projection."
        )
    if not isinstance(projection, dict):
        raise SystemExit("Source root approval projection is invalid.")
    coverage = projection.get("source_coverage")
    validity = projection.get("validity")
    if (
        not isinstance(coverage, dict)
        or not isinstance(validity, dict)
        or projection.get("typed_intent") != "grant_authority"
        or projection.get("source_kind") != "explicit_user_instruction"
        or projection.get("source_rank") != "S3"
        or projection.get("decision_trust_class")
        != {
            "legacy_full_echo": "caller_asserted_exact_echo",
            "legacy_caller_seed": "caller_asserted_plan_decision",
            "host_user_signed_seed": "host_user_signed_exact_plan",
        }[mode]
    ):
        raise SystemExit(
            "Source root approval projection has an invalid trust boundary."
        )
    decided_at = parse_time(
        decision.get("decided_at"), "root decision decided_at"
    ).isoformat()
    if parse_time(decided_at, "root decision decided_at") < parse_time(
        plan["prepared_at"], "root plan prepared_at"
    ):
        raise SystemExit("Source root decision predates its plan.")
    expires_at = validity.get("expires_at")
    if expires_at and parse_time(
        decided_at, "root decision decided_at"
    ) >= parse_time(expires_at, "root decision expires_at"):
        raise SystemExit("Source root decision is outside its window.")
    _require_source_fields(
        approval,
        _root_projection_source_fields(
            projection,
            coverage,
            decision,
            decided_at=decided_at,
            expires_at=expires_at,
            mode=mode,
        ),
        "Root source approval",
    )


def _validate_root_decision_relationship(
    root: Path,
    approval: dict[str, Any],
    decision: dict[str, Any],
) -> None:
    mode = _root_decision_mode(approval, decision)
    _validate_compiled_root_seed(
        root, approval, decision, mode=mode
    )
    plan = _load_root_decision_plan(root, decision)
    _validate_root_projection(
        approval, decision, plan, mode=mode
    )


def _validate_recovery_decision_relationship(
    root: Path,
    approval: dict[str, Any],
    decision: dict[str, Any],
) -> None:
    decision_keys = {
        "schema_version",
        "artifact_kind",
        "decision",
        "recovery_recipe",
        "approval_projection",
        "decided_at",
        "evidence_id",
    }
    if (
        set(decision) != decision_keys
        or decision.get("schema_version") != 1
        or decision.get("artifact_kind") != "authority_recovery_user_decision"
        or decision.get("decision") != "approved"
    ):
        raise SystemExit("Schema-v3 source recovery decision contract is invalid.")
    recipe_path, recipe = _bound_object(
        root, decision["recovery_recipe"], "schema-v3 source recovery recipe"
    )
    if (
        recipe.get("schema_version") != 2
        or recipe.get("artifact_kind") != "authority_source_recovery_recipe"
        or recipe.get("approval_projection") != decision.get("approval_projection")
    ):
        raise SystemExit(
            "Schema-v3 source decision does not bind an exact recovery recipe."
        )
    identity = str(recipe.get("recovery_identity") or "")
    recipe_id = str(recipe.get("recipe_id") or "")
    recipe_body = {
        key: value for key, value in recipe.items() if key != "recipe_id"
    }
    if (
        recipe_id != f"authrecipe-{object_sha256(recipe_body)[:24]}"
        or recipe_path.parent
        != root.resolve() / ".task/authorization/recovery_recipes"
        or recipe_path.name != f"{identity}.json"
    ):
        raise SystemExit("Schema-v3 source recovery recipe identity is invalid.")
    exhausted = recipe.get("exhausted_authority")
    exhausted_decision = (
        exhausted.get("decision") if isinstance(exhausted, dict) else None
    )
    original_request_sha256 = (
        exhausted_decision.get("request_sha256")
        if isinstance(exhausted_decision, dict)
        else None
    )
    if not isinstance(original_request_sha256, str):
        raise SystemExit(
            "Schema-v3 source recovery recipe lacks its original request binding."
        )
    from .source_recovery import _validated_recipe_path

    rendered_recipe = _validated_recipe_path(
        root,
        recipe_path,
        original_request_sha256,
        str(decision.get("decided_at") or ""),
        None,
    )
    if rendered_recipe is None:
        raise SystemExit(
            "Schema-v3 source recovery recipe is not producer-rendered."
        )
    requirements = recipe.get("source_approval_requirements")
    if not isinstance(requirements, dict):
        raise SystemExit("Schema-v3 source recovery requirements are missing.")
    if (
        requirements.get("source_kind_required") != "explicit_user_instruction"
        or requirements.get("source_rank_required") != "S3"
    ):
        raise SystemExit("Schema-v3 recovery source is not an S3 user decision.")
    decided_at = parse_time(
        decision.get("decided_at"), "schema-v3 recovery decision decided_at"
    ).isoformat()
    if parse_time(decided_at, "schema-v3 recovery decision decided_at") < parse_time(
        recipe.get("prepared_at"), "schema-v3 recovery recipe prepared_at"
    ):
        raise SystemExit("Schema-v3 source recovery decision predates its recipe.")
    expiry = requirements.get("expires_at_ceiling")
    if expiry and parse_time(
        decided_at, "schema-v3 recovery decision decided_at"
    ) >= parse_time(expiry, "schema-v3 recovery source expires_at"):
        raise SystemExit("Schema-v3 source recovery decision is outside its window.")
    _require_source_fields(
        approval,
        {
            "approval_id": requirements.get("approval_id"),
            "source_kind": "explicit_user_instruction",
            "source_rank": "S3",
            "decision_type": requirements.get("decision_type_required"),
            "capabilities": requirements.get("capabilities_required"),
            "subjects": requirements.get("subjects_required"),
            "operations": requirements.get("operations_required"),
            "risk_ceiling": requirements.get("risk_ceiling_required"),
            "decision_classes": requirements.get("decision_classes_required"),
            "cardinalities": requirements.get("cardinalities_required"),
            "max_uses": requirements.get("max_uses_required"),
            "grant_ids": requirements.get("grant_ids_required"),
            "request_digests": requirements.get("request_digests_required"),
            "lineage_ids": requirements.get("lineage_ids_required"),
            "delegation_binding": requirements.get("delegation_binding_required"),
            "not_before": decided_at,
            "expires_at": (
                parse_time(
                    expiry, "schema-v3 recovery source expires_at"
                ).isoformat()
                if expiry
                else None
            ),
            "evidence_id": str(decision.get("evidence_id") or ""),
        },
        "Schema-v3 recovery approval",
    )


def validate_source_decision_binding(
    root: Path, approval: dict[str, Any]
) -> str | None:
    """Reopen a schema-v3/v4/v5 decision and prove its producer relationship."""

    if approval["schema_version"] != 3:
        if approval["schema_version"] not in {4, 5}:
            return None
    if approval["decision_trust_class"] not in {
        "caller_asserted_exact_echo",
        "caller_asserted_plan_decision",
        "host_user_signed_exact_plan",
    }:
        raise SystemExit("Source approval trust class is invalid.")
    identity = (
        str(approval["decision_binding"]["ref"]),
        str(approval["decision_binding"]["sha256"]),
        object_sha256(approval),
    )
    active = _ACTIVE_DECISION_VALIDATIONS.get()
    if identity in active:
        return
    token = _ACTIVE_DECISION_VALIDATIONS.set(active | {identity})
    try:
        _path, decision = _bound_object(
            root, approval["decision_binding"], "source decision"
        )
        kind = decision.get("artifact_kind")
        if kind == "authority_root_approval_decision":
            _validate_root_decision_relationship(root, approval, decision)
        elif kind == "authority_root_approval_decision_seed":
            _validate_root_decision_relationship(root, approval, decision)
        elif kind == "authority_recovery_user_decision":
            _validate_recovery_decision_relationship(root, approval, decision)
        else:
            raise SystemExit(
                "Source decision lacks a registered producer verifier."
            )
    finally:
        _ACTIVE_DECISION_VALIDATIONS.reset(token)
    return str(kind)


__all__ = ("validate_source_decision_binding",)
