from __future__ import annotations

from pathlib import Path
from typing import Any

from .artifact_store import AUTHORIZATION_ROOT
from .canonical import authority_lock, object_sha256, parse_time
from .canonical import write_immutable_json
from .contracts import validate_request
from .projection_io import load_bound_json, load_grant_artifact, safe_json
from .projection_io import safe_owned_directory
from .projection_reservations import validate_decision_artifact
from .source_approval import validate_source_approval
from .workflow_candidates import validated_grants
from .workflow_interaction import projection_wait_identity
from .workflow_sources import source_approvals_covering, source_recovery_identity


RECOVERY_ROOT = AUTHORIZATION_ROOT / "recovery_recipes"


def _decision_binding(
    root: Path, decision: dict[str, Any], path: Path, digest: str
) -> dict[str, str]:
    return {
        "ref": path.relative_to(root).as_posix(),
        "sha256": digest,
        "decision_id": decision["decision_id"],
        "request_sha256": decision["request_sha256"],
    }


def _exhausted_evidence(
    decision_binding: dict[str, str],
    sources: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "decision": decision_binding,
        "source_approvals": [
            {
                "approval_id": source["approval_id"],
                "source_rank": source["source_rank"],
                "lineage_ids": source["lineage_ids"],
                "ref": source["ref"],
                "sha256": source["sha256"],
                "materialization_status": source["materialization_status"],
                "unavailable_grants": source["unavailable_grants"],
            }
            for source in sorted(sources, key=lambda item: (item["ref"], item["sha256"]))
        ],
    }


def _replacement_ids(seed: dict[str, Any]) -> dict[str, str]:
    digest = object_sha256(seed)[:24]
    return {
        "request_id": f"authrq-{digest}",
        "attempt_id": f"authra-{digest}",
        "source_approval_id": f"authsa-{digest}",
        "grant_id": f"authg-{digest}",
        "lineage_id": f"authl-{digest}",
        "exact_replay_key": f"authrk-{digest}",
    }


def _replacement_request(
    request: dict[str, Any], identifiers: dict[str, str]
) -> dict[str, Any]:
    replacement = {
        **request,
        "request_id": identifiers["request_id"],
        "attempt_id": identifiers["attempt_id"],
        "idempotency_key": identifiers["exact_replay_key"],
    }
    return validate_request(replacement)


def _source_approval_requirements(
    request: dict[str, Any],
    identifiers: dict[str, str],
    prepared_at: str,
    expires_at: str | None,
) -> dict[str, Any]:
    operation = {
        key: request[key]
        for key in ("skill_id", "skill_version", "operation_id", "operation_version")
    }
    return {
        "requirement_kind": "post_user_decision_source_approval",
        "approval_id": identifiers["source_approval_id"],
        "source_kind_required": "explicit_user_instruction",
        "source_rank_required": "S3",
        "decision_type_required": "grant_authority",
        "capabilities_required": sorted(
            {*request["required_capabilities"], "authority.grant.issue"}
        ),
        "subjects_required": [request["subject"]],
        "operations_required": [operation],
        "risk_ceiling_required": request["risk_tier"],
        "decision_classes_required": [request["decision_class"]],
        "cardinalities_required": [request["cardinality_requested"]],
        "max_uses_required": request["use_budget_requested"],
        "grant_ids_required": [identifiers["grant_id"]],
        "request_digests_required": [object_sha256(request)],
        "lineage_ids_required": [identifiers["lineage_id"]],
        "delegation_binding_required": None,
        "prepared_at_floor": prepared_at,
        "not_before_requirement": "actual_explicit_user_decision_time",
        "actual_user_decision_time_requirement": "RFC3339_at_or_after_prepared_at",
        "expires_at_ceiling": expires_at,
        "evidence_id_requirement": "exact_explicit_user_decision_evidence_id",
        "integrity_status_requirement": "verify_after_exact_user_decision",
        "source_binding_requirement": "snapshot_actual_post_approval_bytes",
    }


def _grant_requirements(
    request: dict[str, Any],
    context: dict[str, Any],
    identifiers: dict[str, str],
    policy_binding: dict[str, str],
    prepared_at: str,
    expires_at: str | None,
) -> dict[str, Any]:
    operation = {
        key: request[key]
        for key in ("skill_id", "skill_version", "operation_id", "operation_version")
    }
    return {
        "requirement_kind": "post_user_approval_grant",
        "grant_id": identifiers["grant_id"],
        "lineage_id": identifiers["lineage_id"],
        "parent_grant_id_required": None,
        "issuer_rank_required": "S3",
        "holder_rank_required": request["actor_rank"],
        "capabilities_required": request["required_capabilities"],
        "subjects_required": [request["subject"]],
        "operations_required": [operation],
        "risk_ceiling_required": request["risk_tier"],
        "decision_classes_required": [request["decision_class"]],
        "cardinality_required": request["cardinality_requested"],
        "max_uses_required": request["use_budget_requested"],
        "prepared_at_floor": prepared_at,
        "not_before_requirement": "at_or_after_actual_explicit_user_decision_time",
        "expires_at_ceiling": expires_at,
        "session_id_required": context["session_ceiling"]["evidence_id"],
        "task_id_required": request["task_id"],
        "improvement_id_required": request["pack_id"],
        "source_approval_binding_requirement": {
            "approval_id": identifiers["source_approval_id"],
            "binding": "actual_post_user_approval_snapshot_ref_and_sha256",
        },
        "policy_snapshot_required": policy_binding,
        "created_at_requirement": "at_or_after_actual_explicit_user_decision_time",
        "idempotency_key_required": identifiers["exact_replay_key"],
    }


def _approval_projection(
    request: dict[str, Any],
    identifiers: dict[str, str],
    recovery_identity: str,
    exhausted_sha256: str,
) -> dict[str, Any]:
    core = {
        "schema_version": 2,
        "artifact_kind": "authority_recovery_approval_projection",
        "typed_intent": "grant_authority",
        "recovery_identity": recovery_identity,
        "replacement_request_id": identifiers["request_id"],
        "replacement_request_sha256": object_sha256(request),
        "source_approval_id": identifiers["source_approval_id"],
        "grant_id": identifiers["grant_id"],
        "lineage_id": identifiers["lineage_id"],
        "operation": {
            key: request[key]
            for key in (
                "skill_id",
                "skill_version",
                "operation_id",
                "operation_version",
            )
        },
        "subject": request["subject"],
        "capabilities": sorted(
            {*request["required_capabilities"], "authority.grant.issue"}
        ),
        "scope": {
            "cardinality": request["cardinality_requested"],
            "use_budget": request["use_budget_requested"],
            "task_id": request["task_id"],
            "improvement_id": request["pack_id"],
            "attempt_id": identifiers["attempt_id"],
        },
        "exhausted_evidence_sha256": exhausted_sha256,
        "excluded_effects": [
            "accept_risk_or_cost",
            "broaden_subject_operation_capabilities_or_budget",
            "change_goal_truth",
            "reuse_exhausted_identifiers",
            "select_design_option",
            "supply_external_input",
        ],
        "safe_alternative": "keep_the_original_operation_unexecuted",
        "reason_codes": ["source_authority_replacement_requires_exact_user_approval"],
        "exact_replay_key": identifiers["exact_replay_key"],
    }
    return {"projection_id": f"authp-{object_sha256(core)[:24]}", **core}


def _post_approval_handoff(
    original_request_sha256: str, replacement: dict[str, Any]
) -> dict[str, Any]:
    return {
        "handoff_kind": "existing_public_authority_commands",
        "authority_status": "non_authoritative_until_actual_user_decision",
        "blocked_until": "exact_explicit_user_decision_evidence",
        "commands": ["snapshot-source", "register-grant", "evaluate"],
        "requirements": ["source_approval_requirements", "grant_requirements"],
        "original_request_sha256": original_request_sha256,
        "continuation_request_id": replacement["request_id"],
        "continuation_request_sha256": object_sha256(replacement),
        "continuation_rule": (
            "after exact approval and artifact materialization, evaluate and poll "
            "the replacement request digest instead of the exhausted original digest"
        ),
    }


def _build_recipe(
    root: Path,
    decision: dict[str, Any],
    decision_binding: dict[str, str],
    sources: list[dict[str, Any]],
    prepared_at: str,
) -> dict[str, Any]:
    request = decision["request"]
    recovery_identity = source_recovery_identity(decision["request_sha256"], sources)
    exhausted = _exhausted_evidence(decision_binding, sources)
    exhausted_sha = object_sha256(exhausted)
    seed = {
        "recovery_identity": recovery_identity,
        "exhausted_evidence_sha256": exhausted_sha,
        "prepared_at": prepared_at,
    }
    identifiers = _replacement_ids(seed)
    replacement = _replacement_request(request, identifiers)
    selected_source = sorted(sources, key=lambda item: (item["ref"], item["sha256"]))[0]
    source_raw, _, _ = load_bound_json(
        root,
        {key: selected_source[key] for key in ("ref", "sha256")},
        "exhausted source approval",
    )
    source = validate_source_approval(source_raw)
    old_grant_id = selected_source["unavailable_grants"][0]["grant_id"]
    old_grant, _ = load_grant_artifact(root, old_grant_id)
    source_requirements = _source_approval_requirements(
        replacement,
        identifiers,
        prepared_at,
        source["expires_at"],
    )
    grant_requirements = _grant_requirements(
        replacement,
        decision["evaluation_context"],
        identifiers,
        old_grant["policy_snapshot"],
        prepared_at,
        source["expires_at"],
    )
    projection = _approval_projection(
        replacement, identifiers, recovery_identity, exhausted_sha
    )
    old_ids = {
        request["request_id"],
        request.get("attempt_id"),
        request["idempotency_key"],
        decision["approval_projection"]["projection_id"],
        decision["approval_projection"]["exact_replay_key"],
        *(item["approval_id"] for item in sources),
        *(
            grant["grant_id"]
            for item in sources
            for grant in item["unavailable_grants"]
        ),
        *(lineage for item in sources for lineage in item["lineage_ids"]),
    }
    if len(set(identifiers.values())) != len(identifiers) or old_ids.intersection(
        identifiers.values()
    ):
        raise SystemExit("Recovery replacement identities are not distinct and fresh.")
    core = {
        "schema_version": 2,
        "artifact_kind": "authority_source_recovery_recipe",
        "recovery_identity": recovery_identity,
        "prepared_at": prepared_at,
        "authority_status": "non_authoritative_prepare_only",
        "exhausted_authority": exhausted,
        "replacement_ids": identifiers,
        "replacement_request": replacement,
        "replacement_request_sha256": object_sha256(replacement),
        "approval_requirements": {
            "status": "requires_exact_user_approval",
            "approval_projection_id": projection["projection_id"],
            "exact_replay_key": projection["exact_replay_key"],
            "materialization_rule": "derive artifacts only from post-approval evidence",
        },
        "source_approval_requirements": source_requirements,
        "grant_requirements": grant_requirements,
        "approval_projection": projection,
        "post_approval_handoff": _post_approval_handoff(
            decision["request_sha256"], replacement
        ),
    }
    return {"recipe_id": f"authrecipe-{object_sha256(core)[:24]}", **core}


def _load_decision(
    root: Path,
    binding: dict[str, str],
    skills_root: Path | None,
) -> tuple[dict[str, Any], Path, dict[str, str]]:
    decision, path, normalized = load_bound_json(
        root, binding, "exhausted authority decision"
    )
    validate_decision_artifact(root, decision, path, skills_root=skills_root)
    if decision["decision"] != "approval_required":
        raise SystemExit("Source recovery requires an approval_required decision.")
    return decision, path, normalized


def _exhausted_sources(
    root: Path,
    decision: dict[str, Any],
    at: str,
    skills_root: Path | None,
) -> list[dict[str, Any]]:
    sources = source_approvals_covering(
        root,
        decision["request"],
        decision["request_sha256"],
        decision["evaluation_context"],
        at,
        skills_root,
        validated_grants(root),
    )
    if not sources or any(
        item["materialization_status"] != "fresh_authority_required"
        for item in sources
    ):
        raise SystemExit("Exact source authority is not in a recoverable exhausted state.")
    return sources


def prepare_source_recovery(
    root: Path,
    decision_ref: str,
    decision_sha256: str,
    *,
    prepared_at: str,
    skills_root: Path | None,
) -> dict[str, Any]:
    root = root.resolve()
    at = parse_time(prepared_at, "source recovery prepared_at").isoformat()
    decision, path, binding = _load_decision(
        root,
        {"ref": decision_ref, "sha256": decision_sha256},
        skills_root,
    )
    sources = _exhausted_sources(root, decision, at, skills_root)
    recipe = _build_recipe(
        root, decision, _decision_binding(root, decision, path, binding["sha256"]), sources, at
    )
    recipe_path = root / RECOVERY_ROOT / f"{recipe['recovery_identity']}.json"
    with authority_lock(root):
        digest = write_immutable_json(
            recipe_path, recipe, "authority source recovery recipe"
        )
    return {
        "status": "prepared",
        "authority_status": recipe["authority_status"],
        "recovery_recipe": {
            "ref": recipe_path.relative_to(root).as_posix(),
            "sha256": digest,
            "recipe_id": recipe["recipe_id"],
        },
        "recovery_identity": recipe["recovery_identity"],
        "approval_projection": recipe["approval_projection"],
        "post_approval_handoff": recipe["post_approval_handoff"],
        "wait_identity": projection_wait_identity(
            recipe["approval_projection"], decision["effective_authority_fingerprint"]
        ),
        "should_prompt": True,
        "next_action": {"actor": "user", "code": "approve_exact_recovery_projection"},
    }


def _validated_recipe_path(
    root: Path,
    path: Path,
    request_sha256: str,
    evaluated_at: str,
    skills_root: Path | None,
) -> dict[str, Any] | None:
    if path.is_symlink():
        raise SystemExit("Authority source recovery recipe must not be a symlink.")
    if not path.is_file():
        raise SystemExit("Authority source recovery recipe must be a regular JSON file.")
    recipe, digest = safe_json(root, path, "authority source recovery recipe")
    prepared_at = parse_time(recipe.get("prepared_at"), "recovery recipe prepared_at")
    if parse_time(evaluated_at, "recovery evaluated_at") < prepared_at:
        return None
    exhausted = recipe.get("exhausted_authority")
    if not isinstance(exhausted, dict) or not isinstance(exhausted.get("decision"), dict):
        raise SystemExit("Authority source recovery recipe evidence is not closed.")
    binding = exhausted["decision"]
    decision, decision_path, normalized = _load_decision(
        root,
        {"ref": binding.get("ref"), "sha256": binding.get("sha256")},
        skills_root,
    )
    if decision["request_sha256"] != request_sha256:
        return None
    historical_sources = _exhausted_sources(
        root, decision, prepared_at.isoformat(), skills_root
    )
    expected = _build_recipe(
        root,
        decision,
        _decision_binding(root, decision, decision_path, normalized["sha256"]),
        historical_sources,
        prepared_at.isoformat(),
    )
    recovery_identity = recipe.get("recovery_identity")
    if (
        expected != recipe
        or path.name != f"{recovery_identity}.json"
        or expected["recovery_identity"] != recovery_identity
    ):
        raise SystemExit("Authority source recovery recipe is conflicting or stale.")
    projection = recipe["approval_projection"]
    expiry = recipe["source_approval_requirements"]["expires_at_ceiling"]
    window_closed = bool(
        expiry
        and parse_time(evaluated_at, "recovery evaluated_at")
        >= parse_time(expiry, "recovery expires_at_ceiling")
    )
    return {
        "ref": path.relative_to(root).as_posix(),
        "sha256": digest,
        "recipe_id": recipe["recipe_id"],
        "recovery_identity": recovery_identity,
        "original_request_sha256": request_sha256,
        "approval_projection": projection,
        "post_approval_handoff": recipe["post_approval_handoff"],
        "historical_source_approvals": historical_sources,
        "continuation_status": (
            "replanning_required" if window_closed else "approval_actionable"
        ),
        "replan_reason": "recovery_continuation_window_closed"
        if window_closed
        else None,
        "wait_identity": projection_wait_identity(
            projection, decision["effective_authority_fingerprint"]
        ),
    }


def discover_source_recovery(
    root: Path,
    request_sha256: str,
    *,
    evaluated_at: str,
    skills_root: Path | None,
) -> dict[str, Any] | None:
    directory = safe_owned_directory(
        root.resolve(), RECOVERY_ROOT, "Authority source recovery recipe directory"
    )
    if directory is None:
        return None
    candidates = [
        recipe
        for path in sorted(directory.iterdir())
        if path.suffix == ".json"
        and (
            recipe := _validated_recipe_path(
                root, path, request_sha256, evaluated_at, skills_root
            )
        )
        is not None
    ]
    if len(candidates) > 1:
        raise SystemExit("Multiple source recovery recipes cover one exact request.")
    return candidates[0] if candidates else None


__all__ = ["discover_source_recovery", "prepare_source_recovery"]
