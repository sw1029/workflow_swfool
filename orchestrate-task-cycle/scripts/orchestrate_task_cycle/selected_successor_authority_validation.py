"""Historical validation for compact selected-successor authority artifacts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .selection_decision_store import normalize_binding, read_bound_json
from .selected_successor import load_selected_successor_bundle
from .selected_successor_authority_artifacts import load_packet, load_projection
from .selected_successor_authority_context import (
    load_evaluation_context,
    load_request_context,
    normalize_grant_inputs,
)
from .selected_successor_authority_publication import supplied_grant_matches
from .selected_successor_execution import _proofs
from .selected_successor_execution_support import ACTIONS, execution_rows


PACKET_OPERATION_KEYS = {
    "action",
    "compilation",
    "request_sha256",
    "decision",
    "selected_grant",
}
PROJECTION_OPERATION_KEYS = {
    "action",
    "operation",
    "compilation",
    "request_sha256",
    "operation_manifest",
    "decision",
    "reason_codes",
    "approval_projection",
}
PACKET_EFFECTS = {
    "renderer_created_source_approvals": False,
    "renderer_created_grants": False,
    "decisions_issued_by": "manage-agent-authority:evaluate_and_publish",
    "selected_successor_effects_applied": False,
}
PROJECTION_EFFECTS = {
    "renderer_created_source_approvals": False,
    "renderer_created_grants": False,
    "decisions_published": False,
    "reservations_created": False,
    "pre_commit_verifications_published": False,
    "selected_successor_effects_applied": False,
}


def _inputs(
    root: Path, artifact: dict[str, Any]
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any], str]:
    bundle_binding = normalize_binding(artifact.get("bundle"), "authority bundle")
    bundle = load_selected_successor_bundle(root, bundle_binding)
    rows = execution_rows(bundle)
    _request_binding, request_value, _seed, actor_rank = load_request_context(
        root, artifact.get("request_context"), bundle_binding
    )
    _evaluation_binding, evaluation, _session, _envelope = load_evaluation_context(
        root, artifact.get("evaluation_context")
    )
    descriptors, records = normalize_grant_inputs(root, artifact.get("grants"))
    holder_ranks = {record[0]["holder_rank"] for record in records.values()}
    if holder_ranks and holder_ranks != {actor_rank}:
        raise ValueError("Authority artifact grant ranks differ from actor_rank")
    if descriptors != artifact.get("grants"):
        raise ValueError("Authority artifact grant descriptors are not closed")
    manifests = artifact.get("operation_manifests")
    if not isinstance(manifests, dict) or set(manifests) != set(ACTIONS):
        raise ValueError("Authority artifact manifest set is not closed")
    for action in ACTIONS:
        normalize_binding(manifests[action], f"{action} operation manifest")
    return bundle, rows, {
        "request_context": request_value["context"],
        "evaluation_context": evaluation,
    }, actor_rank


def _compilation(
    root: Path,
    binding_value: Any,
    row: dict[str, Any],
    contexts: dict[str, Any],
    actor_rank: str,
    *,
    skills_root: Path | None,
) -> tuple[dict[str, str], dict[str, Any]]:
    from manage_agent_authority.operation_compiler import (
        compilation_inputs,
        validate_compilation,
    )
    from manage_agent_authority.operation_publication import COMPILATION_ROOT

    binding = normalize_binding(binding_value, f"{row['action']} compilation")
    path, raw = read_bound_json(root, binding, f"{row['action']} compilation")
    compilation = validate_compilation(raw)
    expected = (
        COMPILATION_ROOT
        / f"operation_compilation-{compilation['compilation_fingerprint']}.json"
    )
    if path.relative_to(root).as_posix() != expected.as_posix():
        raise ValueError(f"Selected-successor {row['action']} compilation path differs")
    request, evaluation = compilation_inputs(
        root, compilation, skills_root=skills_root
    )
    operation = row["operation"]
    expected_operation = {
        key: operation[key]
        for key in ("skill_id", "skill_version", "operation_id", "operation_version")
    }
    if (
        any(request[key] != item for key, item in expected_operation.items())
        or request["subject"] != row["subject"]
        or request["idempotency_key"] != row["idempotency_key"]
        or request["actor_rank"] != actor_rank
        or request["context"] != contexts["request_context"]
        or evaluation != contexts["evaluation_context"]
    ):
        raise ValueError(f"Selected-successor {row['action']} compilation is cross-bound")
    return binding, compilation


def validate_authority_packet(
    root: Path,
    binding_value: Any,
    *,
    skills_root: Path | None = None,
) -> dict[str, Any]:
    """Validate packet bytes and all historical proof cross-bindings read-only."""

    from manage_agent_authority.historical_proof_chain import (
        validate_historical_proof_chains,
    )

    root = root.expanduser().resolve(strict=True)
    _binding, packet = load_packet(root, binding_value)
    _bundle, rows, contexts, actor_rank = _inputs(root, packet)
    operations = packet.get("operations")
    if (
        packet.get("status") != "all_three_owner_proofs_current"
        or packet.get("authority_effects") != PACKET_EFFECTS
        or not isinstance(operations, list)
        or len(operations) != len(ACTIONS)
    ):
        raise ValueError("Selected-successor authority packet contract differs")
    proofs = _proofs(packet.get("authority_proofs"))
    chains = validate_historical_proof_chains(
        root,
        [
            (
                proofs[action]["reservation"],
                proofs[action]["pre_commit_verification"],
                proofs[action]["expected_version"],
            )
            for action in ACTIONS
        ],
        skills_root=skills_root,
    )
    for row, operation, chain in zip(rows, operations, chains):
        action = row["action"]
        if (
            not isinstance(operation, dict)
            or set(operation) != PACKET_OPERATION_KEYS
            or operation.get("action") != action
            or operation.get("selected_grant") != packet["grants"][action]
        ):
            raise ValueError(f"Selected-successor {action} packet row is invalid")
        compilation_binding, compilation = _compilation(
            root,
            operation["compilation"],
            row,
            contexts,
            actor_rank,
            skills_root=skills_root,
        )
        if operation["request_sha256"] != compilation["request_sha256"]:
            raise ValueError(f"Selected-successor {action} request digest differs")
        if (
            packet["operation_manifests"][action]
            != compilation["operation_manifest"]
            or compilation.get("compiled_at") != packet.get("prepared_at")
        ):
            raise ValueError(f"Selected-successor {action} manifest binding differs")
        decision_binding = normalize_binding(operation["decision"], f"{action} decision")
        decision = chain["decision"]
        if (
            chain["decision_binding"] != decision_binding
            or decision_binding["ref"]
            != f".task/authorization/decisions/{decision['decision_id']}.json"
            or decision.get("decision") != "allowed"
            or decision.get("request") != compilation["request"]
            or decision.get("evaluation_context") != compilation["evaluation_context"]
            or not supplied_grant_matches(decision, packet["grants"][action])
            or decision.get("evaluated_at") != packet.get("prepared_at")
        ):
            raise ValueError(f"Selected-successor {action} decision is cross-bound")
        proof = proofs[action]
        reservation = chain["reservation"]
        state = chain["current_state"]
        if (
            chain["reservation_binding"] != proof["reservation"]
            or reservation.get("decision") != decision_binding
            or reservation.get("request_sha256") != compilation["request_sha256"]
            or reservation.get("idempotency_key") != row["idempotency_key"]
            or reservation.get("reserved_at") != packet.get("prepared_at")
            or (state.get("status"), state.get("version"))
            not in {("reserved", 0), ("consumed", 1)}
        ):
            raise ValueError(f"Selected-successor {action} reservation is cross-bound")
        verification = chain["verification"]
        if chain["verification_binding"] != proof["pre_commit_verification"]:
            raise ValueError(f"Selected-successor {action} verification binding differs")
        if verification.get("verified_at") != packet.get("prepared_at"):
            raise ValueError(f"Selected-successor {action} verification time differs")
        if compilation_binding != operation["compilation"]:
            raise ValueError(f"Selected-successor {action} compilation binding differs")
    return packet


def validate_authority_projection(
    root: Path,
    binding_value: Any,
    *,
    skills_root: Path | None = None,
) -> dict[str, Any]:
    from manage_agent_authority.evaluator import evaluate

    from .selected_successor_authority_publication import (
        aggregate_budget_reasons,
        derived_projection_operation,
    )

    root = root.expanduser().resolve(strict=True)
    _binding, projection = load_projection(root, binding_value)
    _bundle, rows, contexts, actor_rank = _inputs(root, projection)
    operations = projection.get("operations")
    if (
        projection.get("status") != "approval_required_no_authority_effect"
        or projection.get("authority_effects") != PROJECTION_EFFECTS
        or not isinstance(operations, list)
        or len(operations) != len(ACTIONS)
    ):
        raise ValueError("Selected-successor authority projection contract differs")
    validated: list[tuple[dict[str, Any], dict[str, Any], dict[str, Any]]] = []
    for row, operation in zip(rows, operations):
        action = row["action"]
        if (
            not isinstance(operation, dict)
            or set(operation) != PROJECTION_OPERATION_KEYS
            or operation.get("action") != action
            or operation.get("operation") != row["operation"]
        ):
            raise ValueError(f"Selected-successor {action} projection row is invalid")
        _binding, compilation = _compilation(
            root,
            operation["compilation"],
            row,
            contexts,
            actor_rank,
            skills_root=skills_root,
        )
        if (
            operation["request_sha256"] != compilation["request_sha256"]
            or operation["operation_manifest"] != compilation["operation_manifest"]
            or projection["operation_manifests"][action]
            != compilation["operation_manifest"]
            or compilation.get("compiled_at") != projection.get("prepared_at")
        ):
            raise ValueError(f"Selected-successor {action} projection is cross-bound")
        canonical = evaluate(
            root,
            compilation["request"],
            compilation["evaluation_context"],
            evaluated_at=projection["prepared_at"],
            skills_root=skills_root,
        )
        if canonical["decision"] == "allowed" and not supplied_grant_matches(
            canonical, projection["grants"][action]
        ):
            raise ValueError(
                "Canonical authority selected a grant that conflicts with the exact input"
            )
        validated.append((operation, compilation, canonical))
    budget_reasons = aggregate_budget_reasons(
        root,
        rows,
        [item[2] for item in validated],
        [item[1] for item in validated],
    )
    blocked = False
    for row, (operation, compilation, canonical) in zip(rows, validated):
        action = row["action"]
        expected = derived_projection_operation(
            row,
            compilation,
            operation["compilation"],
            canonical,
            projection["grants"][action],
            forced_reasons=budget_reasons.get(action),
        )
        if operation != expected:
            raise ValueError(
                f"Selected-successor {action} projection is not canonically derived"
            )
        blocked |= canonical["decision"] != "allowed" or (
            "supplied_grant_mismatch" in expected["reason_codes"]
        ) or action in budget_reasons
    if not blocked:
        raise ValueError("Authority projection cannot represent an all-allowed packet")
    return projection


__all__ = ("validate_authority_packet", "validate_authority_projection")
