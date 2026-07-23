"""Continue one selected-successor projection with signed plan-bound grants."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .selection_decision_store import normalize_binding
from .selected_successor import load_selected_successor_bundle
from .selected_successor_authority_artifacts import (
    authority_input_identity,
    load_index,
    load_locator,
)
from .selected_successor_authority_context import (
    load_request_context,
    normalize_grant_inputs,
)
from .selected_successor_authority_publication import (
    aggregate_budget_reasons,
    publish_packet_result,
    result_from_index,
    supplied_grant_matches,
)
from .selected_successor_authority_validation import (
    validate_authority_projection_snapshot,
)
from .selected_successor_execution_support import (
    checkpoint_states,
    validate_pristine_source,
)


def _materialized_grants(
    root: Path,
    projection_binding: dict[str, str],
    materialization_binding: dict[str, str],
    *,
    skills_root: Path | None,
) -> tuple[dict[str, Any], dict[str, str], dict[str, dict[str, Any]]]:
    from manage_agent_authority.operation_batch import load_operation_batch
    from manage_agent_authority.root_grant_plan import load_root_approval_plan
    from manage_agent_authority.root_grant_transaction import (
        payload_binding,
        validate_root_grant_receipt_chain,
    )

    projection_ref, projection, selected = validate_authority_projection_snapshot(
        root, projection_binding, skills_root=skills_root
    )
    receipt_ref = normalize_binding(
        materialization_binding, "root grant materialization"
    )
    assets = validate_root_grant_receipt_chain(
        root, receipt_ref["ref"], skills_root=skills_root
    )
    if receipt_ref != payload_binding(
        root, assets["receipt_path"], assets["receipt_payload"]
    ):
        raise ValueError("Root grant materialization binding differs")
    _plan_ref, plan = load_root_approval_plan(
        root,
        assets["receipt"]["root_approval_plan"],
        skills_root=skills_root,
    )
    _batch_ref, batch, batch_compilations = load_operation_batch(
        root, plan["operation_batch"], skills_root=skills_root
    )
    selected_bindings = [binding for binding, _compilation in selected]
    selected_requests = [
        compilation["request_sha256"] for _binding, compilation in selected
    ]
    if (
        batch.get("schema_version") != 2
        or batch.get("projection_source", {}).get("binding") != projection_ref
        or [row["compilation"] for row in batch["operation_compilations"]]
        != selected_bindings
        or [item["request_sha256"] for item in batch_compilations] != selected_requests
    ):
        raise ValueError("Root grant plan is not bound to this exact projection")
    materialized = {
        asset["grant"]["request_sha256"]: {
            "ref": asset["artifact_path"].relative_to(root).as_posix(),
            "sha256": asset["grant_sha256"],
        }
        for asset in assets["grant_assets"]
    }
    if set(materialized) != set(selected_requests):
        raise ValueError("Root grant materialization request set differs")
    descriptors: dict[str, dict[str, Any]] = {}
    for operation in projection["operations"]:
        action = operation["action"]
        if operation["approval_projection"] is None:
            descriptors[action] = projection["grants"][action]
        else:
            descriptors[action] = {
                "status": "bound",
                "binding": materialized[operation["request_sha256"]],
            }
    return projection, receipt_ref, descriptors


def _projection_compilations(
    root: Path,
    projection: dict[str, Any],
) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
    from manage_agent_authority.operation_publication import (
        load_published_compilation,
    )

    bindings: list[dict[str, str]] = []
    compilations: list[dict[str, Any]] = []
    for operation in projection["operations"]:
        binding, compilation = load_published_compilation(
            root, operation["compilation"]
        )
        bindings.append({"ref": binding["ref"], "sha256": binding["sha256"]})
        compilations.append(compilation)
    return bindings, compilations


def resume_selected_successor_authority(
    root: Path,
    *,
    projection_binding: dict[str, str],
    materialization_binding: dict[str, str],
    at: str,
    skills_root: Path | None = None,
) -> dict[str, Any]:
    """Reuse T1 requests and evaluate their signed grants at a later T2."""

    from manage_agent_authority.canonical import normalized_time, parse_time
    from manage_agent_authority.evaluator import evaluate

    from .selected_successor_authority import (
        _actor_rank,
        _existing_reservation,
        _replay_located_packet,
    )

    root = root.expanduser().resolve(strict=True)
    prepared_at = normalized_time(at, "selected-successor continuation prepared_at")
    projection, receipt_binding, grant_inputs = _materialized_grants(
        root,
        projection_binding,
        materialization_binding,
        skills_root=skills_root,
    )
    projection_binding = normalize_binding(
        projection_binding, "selected-successor source projection"
    )
    if parse_time(prepared_at, "continuation prepared_at") <= parse_time(
        projection["prepared_at"], "projection prepared_at"
    ):
        raise ValueError("Authority continuation must follow request compilation")
    bundle_binding = projection["bundle"]
    bundle = load_selected_successor_bundle(root, bundle_binding)
    rows, states = checkpoint_states(root, bundle)
    request_binding, _request, _seed, asserted_rank = load_request_context(
        root, projection["request_context"], bundle_binding
    )
    grant_descriptors, selected_grants = normalize_grant_inputs(root, grant_inputs)
    _actor_rank(selected_grants, asserted_rank)
    if any(
        parse_time(record[0]["not_before"], "root grant not_before")
        > parse_time(prepared_at, "continuation prepared_at")
        for record in selected_grants.values()
    ):
        raise ValueError("Authority continuation predates its signed decision")
    compilation_bindings, compilations = _projection_compilations(root, projection)
    manifests = {
        row["action"]: compilation["operation_manifest"]
        for row, compilation in zip(rows, compilations)
    }
    identity, input_sha = authority_input_identity(
        bundle=bundle_binding,
        request_context=request_binding,
        evaluation_context=projection["evaluation_context"],
        grants=grant_descriptors,
        operation_manifests=manifests,
        prepared_at=prepared_at,
        source_projection=projection_binding,
        root_grant_materialization=receipt_binding,
    )
    indexed = load_index(root, identity, input_sha)
    if indexed is not None:
        return result_from_index(root, indexed, prepared_at, skills_root=skills_root)
    located = _replay_located_packet(
        root,
        load_locator(root, input_sha),
        identity,
        input_sha,
        prepared_at,
        skills_root,
    )
    if located is not None:
        return located
    if states != ["missing", "missing", "missing"]:
        raise ValueError("Authority continuation requires a pristine successor")
    validate_pristine_source(root, bundle, states)
    existing = [
        _existing_reservation(
            root,
            compilation,
            row,
            expected_at=prepared_at,
        )
        for compilation, row in zip(compilations, rows)
    ]
    decisions = [
        present["decision"]
        if present is not None
        else evaluate(
            root,
            compilation["request"],
            compilation["evaluation_context"],
            evaluated_at=prepared_at,
            skills_root=skills_root,
        )
        for present, compilation in zip(existing, compilations)
    ]
    if not all(
        decision.get("decision") == "allowed"
        and supplied_grant_matches(decision, grant_descriptors[row["action"]])
        for row, decision in zip(rows, decisions)
    ):
        raise ValueError("Signed projection grants do not cover all three operations")
    if aggregate_budget_reasons(root, rows, decisions, compilations, existing):
        raise ValueError("Signed projection grants lack aggregate reservation budget")
    return publish_packet_result(
        root,
        at=prepared_at,
        bundle=bundle_binding,
        request_context=request_binding,
        evaluation_context=projection["evaluation_context"],
        grants=grant_descriptors,
        operation_manifests=manifests,
        rows=rows,
        compilations=compilations,
        compilation_bindings=compilation_bindings,
        existing=existing,
        identity=identity,
        input_sha=input_sha,
        skills_root=skills_root,
        source_projection=projection_binding,
        root_grant_materialization=receipt_binding,
    )


__all__ = ("resume_selected_successor_authority",)
