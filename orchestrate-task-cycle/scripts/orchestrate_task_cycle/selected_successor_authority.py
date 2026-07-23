"""Compile existing authority into a selected-successor proof packet."""

from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Any

from .selected_successor import load_selected_successor_bundle
from .selected_successor_authority_artifacts import (
    authority_input_identity,
    load_index,
    load_locator,
)
from .selected_successor_authority_context import (
    load_evaluation_context,
    load_request_context,
    normalize_grant_inputs,
)
from .selected_successor_authority_publication import (
    aggregate_budget_reasons,
    publish_packet_result,
    publish_projection_result,
    result_from_index,
    supplied_grant_matches,
)
from .selected_successor_execution_support import (
    checkpoint_states,
    validate_pristine_source,
)


def _cycle_id(root: Path, bundle: dict[str, Any]) -> str:
    from .selection_decision_store import read_bound_json

    _path, receipt = read_bound_json(
        root, bundle["source_decision"], "selected-successor source decision"
    )
    trigger_binding = receipt.get("selection_trigger")
    _trigger_path, trigger = read_bound_json(
        root, trigger_binding, "selected-successor selection trigger"
    )
    cycle_id = trigger.get("cycle_id")
    if not isinstance(cycle_id, str) or not cycle_id:
        raise ValueError("Selected-successor source lacks an exact cycle ID")
    return cycle_id


def _actor_rank(
    selected_grants: dict[str, tuple[dict[str, Any], str, dict[str, Any]]],
    asserted_rank: str,
) -> str:
    holder_ranks = {record[0]["holder_rank"] for record in selected_grants.values()}
    if holder_ranks and holder_ranks != {asserted_rank}:
        raise ValueError(
            "Selected-successor grant holder ranks differ from request actor_rank"
        )
    return asserted_rank


def _located_packet_exists(root: Path, binding: dict[str, str]) -> bool:
    from .selection_decision_store import normalize_binding

    normalized = normalize_binding(binding, "located authority packet")
    current = root
    for part in PurePosixPath(normalized["ref"]).parts:
        current /= part
        if current.is_symlink():
            raise ValueError("Located authority packet cannot traverse a symlink")
    return current.exists()


def _compilations(
    root: Path,
    bundle: dict[str, Any],
    rows: list[dict[str, Any]],
    *,
    actor_rank: str,
    cycle_id: str,
    request_context: dict[str, Any],
    evaluation_context: dict[str, Any],
    session: dict[str, Any],
    envelope: dict[str, Any],
    at: str,
    skills_root: Path | None,
) -> list[dict[str, Any]]:
    from manage_agent_authority.operation_compiler import compile_operation

    result = []
    for row in rows:
        operation = row["operation"]
        subject = row["subject"]
        seed = {
            "skill_id": operation["skill_id"],
            "skill_version": operation["skill_version"],
            "operation_id": operation["operation_id"],
            "operation_version": operation["operation_version"],
            "subject": {
                "ref": subject["ref"],
                "revision": subject["revision"],
                "kind": subject["kind"],
            },
            "scope": {
                "cycle_id": cycle_id,
                "task_id": bundle["selected_task_id"],
                "pack_id": None,
            },
            "actor_rank": actor_rank,
            "context": request_context,
            "session_ceiling": session,
            "goal_autonomy_envelope": envelope,
            "cardinality_requested": "single_use",
            "use_budget_requested": 1,
            "reservation_units": 1,
            "classification": {"subject_kind": subject["kind"]},
        }
        compiled = compile_operation(
            root,
            seed,
            compiled_at=at,
            trusted_request_idempotency_key=row["idempotency_key"],
            skills_root=skills_root,
        )
        request = compiled["request"]
        if (
            request["subject"] != subject
            or request["idempotency_key"] != row["idempotency_key"]
            or compiled["evaluation_context"] != evaluation_context
        ):
            raise ValueError(f"Selected-successor {row['action']} compilation differs")
        result.append(compiled)
    return result


def _existing_reservation(
    root: Path,
    compilation: dict[str, Any],
    row: dict[str, Any],
    *,
    expected_at: str,
) -> dict[str, Any] | None:
    from manage_agent_authority.canonical import object_sha256, sha256_file
    from manage_agent_authority.evaluator import load_bound_decision
    from manage_agent_authority.lifecycle import load_reservation
    from manage_agent_authority.lifecycle_paths import reservation_path

    reservation_id = (
        "authz-"
        + object_sha256(
            {"request": compilation["request_sha256"], "key": row["idempotency_key"]}
        )[:24]
    )
    path = reservation_path(root, reservation_id)
    if not path.exists():
        return None
    digest = sha256_file(path)
    reservation, observed_path, state = load_reservation(
        root, path.relative_to(root).as_posix(), digest
    )
    decision, decision_path = load_bound_decision(
        root, reservation["decision"]["ref"], reservation["decision"]["sha256"]
    )
    if (
        observed_path != path
        or reservation.get("request_sha256") != compilation["request_sha256"]
        or reservation.get("idempotency_key") != row["idempotency_key"]
        or decision.get("request") != compilation["request"]
        or decision.get("evaluation_context") != compilation["evaluation_context"]
        or decision.get("evaluated_at") != expected_at
        or reservation.get("reserved_at") != expected_at
    ):
        raise ValueError(f"Selected-successor {row['action']} reservation conflicts")
    if state.get("status") != "reserved" or state.get("version") != 0:
        raise ValueError(
            f"Selected-successor {row['action']} reservation is not preparable"
        )
    return {
        "reservation": reservation,
        "reservation_binding": {
            "ref": path.relative_to(root).as_posix(),
            "sha256": digest,
        },
        "decision": decision,
        "decision_binding": {
            "ref": decision_path.relative_to(root).as_posix(),
            "sha256": reservation["decision"]["sha256"],
        },
    }


def _replay_located_packet(
    root: Path,
    locator: dict[str, Any] | None,
    identity: dict[str, Any],
    input_sha: str,
    at: str,
    skills_root: Path | None,
) -> dict[str, Any] | None:
    if locator is None:
        return None
    if locator.get("operation_manifests") != identity["operation_manifests"]:
        raise ValueError("Authority packet locator manifest set differs")
    if not _located_packet_exists(root, locator["packet"]):
        return None
    replay = result_from_index(
        root,
        {**identity, "outcome_kind": "packet", "outcome": locator["packet"]},
        at,
        skills_root=skills_root,
    )
    from .selected_successor_authority_artifacts import publish_index

    publish_index(
        root,
        identity,
        input_sha,
        outcome_kind="packet",
        outcome=locator["packet"],
    )
    return {**replay, "index_repaired": True, "mutation_performed": True}


def prepare_selected_successor_authority(
    root: Path,
    *,
    bundle_binding: dict[str, str],
    request_context_binding: dict[str, str],
    evaluation_context_binding: dict[str, str],
    grants: dict[str, Any],
    at: str,
    skills_root: Path | None = None,
) -> dict[str, Any]:
    """Prepare all three proofs from existing authority, or a no-effect projection."""

    from manage_agent_authority.canonical import normalized_time
    from manage_agent_authority.evaluator import evaluate
    from manage_agent_authority.operation_publication import publish_compilation

    root = root.expanduser().resolve(strict=True)
    at = normalized_time(at, "selected-successor authority prepared_at")
    bundle = load_selected_successor_bundle(root, bundle_binding)
    rows, states = checkpoint_states(root, bundle)
    request_binding, _request_value, request_seed, asserted_rank = load_request_context(
        root, request_context_binding, bundle_binding
    )
    evaluation_binding, evaluation, session, envelope = load_evaluation_context(
        root, evaluation_context_binding
    )
    grant_descriptors, selected_grants = normalize_grant_inputs(root, grants)
    actor_rank = _actor_rank(selected_grants, asserted_rank)
    compilations = _compilations(
        root,
        bundle,
        rows,
        actor_rank=actor_rank,
        cycle_id=_cycle_id(root, bundle),
        request_context=request_seed,
        evaluation_context=evaluation,
        session=session,
        envelope=envelope,
        at=at,
        skills_root=skills_root,
    )
    operation_manifests = {
        row["action"]: compilation["operation_manifest"]
        for row, compilation in zip(rows, compilations)
    }
    identity, input_sha = authority_input_identity(
        bundle=bundle_binding,
        request_context=request_binding,
        evaluation_context=evaluation_binding,
        grants=grant_descriptors,
        operation_manifests=operation_manifests,
        prepared_at=at,
    )
    indexed = load_index(root, identity, input_sha)
    if indexed is not None:
        return result_from_index(root, indexed, at, skills_root=skills_root)
    located = _replay_located_packet(
        root, load_locator(root, input_sha), identity, input_sha, at, skills_root
    )
    if located is not None:
        return located
    if states != ["missing", "missing", "missing"]:
        raise ValueError("New authority preparation requires a pristine successor")
    validate_pristine_source(root, bundle, states)
    existing = [
        _existing_reservation(root, compilation, row, expected_at=at)
        for compilation, row in zip(compilations, rows)
    ]
    decisions = [
        present["decision"]
        if present is not None
        else evaluate(
            root,
            compilation["request"],
            compilation["evaluation_context"],
            evaluated_at=at,
            skills_root=skills_root,
        )
        for present, compilation in zip(existing, compilations)
    ]
    all_exact = all(
        decision.get("decision") == "allowed"
        and supplied_grant_matches(decision, grant_descriptors[row["action"]])
        for row, decision in zip(rows, decisions)
    )
    allowed_mismatch = any(
        decision.get("decision") == "allowed"
        and not supplied_grant_matches(decision, grant_descriptors[row["action"]])
        for row, decision in zip(rows, decisions)
    )
    if allowed_mismatch:
        raise ValueError(
            "Canonical authority selected a grant that conflicts with the exact input"
        )
    compilation_bindings = [
        {"ref": published["ref"], "sha256": published["sha256"]}
        for published in (publish_compilation(root, item) for item in compilations)
    ]
    common = {
        "at": at,
        "bundle": bundle_binding,
        "request_context": request_binding,
        "evaluation_context": evaluation_binding,
        "grants": grant_descriptors,
        "operation_manifests": operation_manifests,
        "rows": rows,
        "compilations": compilations,
        "compilation_bindings": compilation_bindings,
        "identity": identity,
        "input_sha": input_sha,
    }
    budget_reasons = (
        aggregate_budget_reasons(root, rows, decisions, compilations, existing)
        if all_exact
        else {}
    )
    if not all_exact or budget_reasons:
        if any(item is not None for item in existing):
            raise ValueError(
                "Partial authority preparation cannot be converted to a no-effect projection"
            )
        return publish_projection_result(
            root,
            decisions=decisions,
            reason_overrides=budget_reasons or None,
            **common,
        )
    return publish_packet_result(
        root,
        existing=existing,
        skills_root=skills_root,
        **common,
    )


__all__ = ("prepare_selected_successor_authority",)
