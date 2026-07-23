"""Publish selected-successor authority projections and proof packets."""

from __future__ import annotations

from pathlib import Path
import sys
from typing import Any

from .isolated_python import isolated_module_argv
from .selected_successor_authority_artifacts import (
    packet_candidate,
    publish_index,
    publish_locator,
    publish_packet,
    publish_projection,
)
from .workflow_launcher import OWNER_SPECS, owner_import_roots


def supplied_grant_matches(
    decision: dict[str, Any], descriptor: dict[str, Any]
) -> bool:
    selected = decision.get("selected_grants")
    if descriptor.get("status") != "bound" or not isinstance(selected, list):
        return False
    binding = descriptor["binding"]
    return (
        len(selected) == 1
        and selected[0].get("grant_sha256") == binding["sha256"]
        and binding["ref"]
        == (f".task/authorization/grants/{selected[0].get('grant_id')}.json")
    )


def _argv(
    root: Path,
    command: str,
    packet: dict[str, str],
    at: str,
    skills_root: Path | None,
) -> list[str]:
    arguments = [
        "selected-successor",
        "--root",
        str(root),
        command,
        "--authority-packet-ref",
        packet["ref"],
        "--authority-packet-sha256",
        packet["sha256"],
        "--at",
        at,
    ]
    if skills_root is not None:
        arguments.extend(("--skills-root", str(skills_root.resolve())))
    roots = owner_import_roots(OWNER_SPECS["cycle"])
    return isolated_module_argv(
        sys.executable,
        "orchestrate_task_cycle",
        arguments,
        roots,
    )


def result_from_index(
    root: Path,
    index: dict[str, Any],
    at: str,
    *,
    skills_root: Path | None = None,
) -> dict[str, Any]:
    from .selected_successor_authority_validation import (
        validate_authority_packet,
        validate_authority_projection,
    )

    outcome = index["outcome"]
    if index["outcome_kind"] == "packet":
        packet = validate_authority_packet(root, outcome, skills_root=skills_root)
        artifact = packet
    else:
        artifact = validate_authority_projection(root, outcome, skills_root=skills_root)
    expected_fields = (
        "prepared_at",
        "bundle",
        "request_context",
        "evaluation_context",
        "grants",
        "operation_manifests",
    )
    if any(key in index and artifact.get(key) != index[key] for key in expected_fields):
        raise ValueError("Authority input index points to a cross-bound outcome")
    if index["outcome_kind"] == "packet":
        return {
            "result_kind": "selected_successor_authority_preparation_result",
            "schema_version": 1,
            "status": "prepared",
            "bundle": packet["bundle"],
            "authority_packet": outcome,
            "execute_argv": _argv(root, "execute", outcome, at, skills_root),
            "recover_argv": _argv(root, "recover", outcome, at, skills_root),
            "idempotent_replay": True,
            "mutation_performed": False,
            "model_authored_mechanical_bytes": 0,
        }
    return {
        "result_kind": "selected_successor_authority_preparation_result",
        "schema_version": 1,
        "status": "approval_required",
        "bundle": artifact["bundle"],
        "approval_projection": outcome,
        "idempotent_replay": True,
        "mutation_performed": False,
        "model_authored_mechanical_bytes": 0,
    }


def publish_projection_result(
    root: Path,
    *,
    at: str,
    bundle: dict[str, str],
    request_context: dict[str, str],
    evaluation_context: dict[str, str],
    grants: dict[str, dict[str, Any]],
    operation_manifests: dict[str, dict[str, str]],
    rows: list[dict[str, Any]],
    compilations: list[dict[str, Any]],
    compilation_bindings: list[dict[str, str]],
    decisions: list[dict[str, Any]],
    identity: dict[str, Any],
    input_sha: str,
    reason_overrides: dict[str, list[str]] | None = None,
) -> dict[str, Any]:
    operations = [
        derived_projection_operation(
            row,
            compilation,
            compilation_binding,
            decision,
            grants[row["action"]],
            forced_reasons=(reason_overrides or {}).get(row["action"]),
        )
        for row, compilation, compilation_binding, decision in zip(
            rows, compilations, compilation_bindings, decisions
        )
    ]
    body = {
        "schema_version": 1,
        "artifact_kind": "selected_successor_authority_approval_projection",
        "status": "approval_required_no_authority_effect",
        "prepared_at": at,
        "bundle": bundle,
        "request_context": request_context,
        "evaluation_context": evaluation_context,
        "grants": grants,
        "operation_manifests": operation_manifests,
        "operations": operations,
        "authority_effects": {
            "renderer_created_source_approvals": False,
            "renderer_created_grants": False,
            "decisions_published": False,
            "reservations_created": False,
            "pre_commit_verifications_published": False,
            "selected_successor_effects_applied": False,
        },
    }
    _projection, projection_binding, _created = publish_projection(root, body)
    publish_index(
        root,
        identity,
        input_sha,
        outcome_kind="approval_projection",
        outcome=projection_binding,
    )
    return {
        "result_kind": "selected_successor_authority_preparation_result",
        "schema_version": 1,
        "status": "approval_required",
        "bundle": bundle,
        "approval_projection": projection_binding,
        "idempotent_replay": False,
        "mutation_performed": True,
        "model_authored_mechanical_bytes": 0,
    }


def derived_projection_operation(
    row: dict[str, Any],
    compilation: dict[str, Any],
    compilation_binding: dict[str, str],
    decision: dict[str, Any],
    grant: dict[str, Any],
    *,
    forced_reasons: list[str] | None = None,
) -> dict[str, Any]:
    """Render one projection row only from canonical compiler/evaluator output."""

    from manage_agent_authority.approval_projection import build_approval_projection

    exact = supplied_grant_matches(decision, grant)
    mismatch = (
        {"supplied_grant_mismatch"}
        if decision["decision"] == "allowed" and not exact
        else set()
    )
    reasons = sorted(set(decision["reason_codes"]) | mismatch)
    projected_decision = decision["decision"]
    approval = decision.get("approval_projection")
    if forced_reasons:
        reasons = sorted(set(forced_reasons))
        approval = build_approval_projection(
            compilation["request"], compilation["evaluation_context"], reasons
        )
    elif mismatch:
        approval = build_approval_projection(
            compilation["request"], compilation["evaluation_context"], reasons
        )
    return {
        "action": row["action"],
        "operation": row["operation"],
        "request_sha256": compilation["request_sha256"],
        "compilation": compilation_binding,
        "operation_manifest": compilation["operation_manifest"],
        "decision": projected_decision,
        "reason_codes": reasons,
        "approval_projection": approval,
    }


def aggregate_budget_reasons(
    root: Path,
    rows: list[dict[str, Any]],
    decisions: list[dict[str, Any]],
    compilations: list[dict[str, Any]],
    existing: list[dict[str, Any] | None] | None = None,
) -> dict[str, list[str]]:
    """Derive aggregate grant blockers without writing lifecycle artifacts."""

    from manage_agent_authority.artifact_store import load_grant
    from manage_agent_authority.lifecycle_preflight import decision_grant_bindings

    present = existing or [None] * len(rows)
    required: dict[str, int] = {}
    actions: dict[str, set[str]] = {}
    for row, decision, compilation, prior in zip(
        rows, decisions, compilations, present
    ):
        if prior is not None or decision.get("decision") != "allowed":
            continue
        units = int(compilation["request"].get("reservation_units", 1))
        for grant_binding in decision_grant_bindings(decision):
            grant_id = grant_binding["grant_id"]
            required[grant_id] = required.get(grant_id, 0) + units
            actions.setdefault(grant_id, set()).add(row["action"])
    blocked_actions: set[str] = set()
    for grant_id, units in required.items():
        grant, _digest, state = load_grant(root, grant_id)
        remaining = state.get("remaining_uses")
        unavailable = remaining is not None and (
            remaining - int(state.get("reserved_uses", 0)) < units
        )
        if unavailable or (
            grant.get("max_uses") is not None and grant["max_uses"] < units
        ):
            blocked_actions.update(actions[grant_id])
    return {
        action: ["aggregate_grant_budget_insufficient"]
        for action in sorted(blocked_actions)
    }


def _reservation_closure_hook(stage: str, root: Path, closure: dict[str, Any]) -> None:
    """Test seam for a mutable-task swap after closure but before reservation."""

    _ = stage, root, closure


def _publish_chains(
    root: Path,
    bundle: dict[str, str],
    rows: list[dict[str, Any]],
    compilations: list[dict[str, Any]],
    compilation_bindings: list[dict[str, str]],
    grants: dict[str, dict[str, Any]],
    existing: list[dict[str, Any] | None],
    *,
    at: str,
    skills_root: Path | None,
) -> tuple[list[dict[str, str]], dict[str, dict[str, Any]]]:
    from manage_agent_authority.decision_publication import evaluate_and_publish
    from manage_agent_authority.evaluator import evaluate
    from manage_agent_authority.lifecycle import reserve
    from manage_agent_authority.verification_publication import (
        verify_and_publish_precommit,
    )
    from .executable_closure_snapshot import (
        assert_executable_closure_epoch_current,
    )
    from .executable_closure_topology import (
        selected_successor_reservation_scope,
    )

    decisions: list[dict[str, str] | None] = []
    closure_bindings: list[dict[str, str]] = []
    closure_values: list[dict[str, Any]] = []
    for row, compilation, present in zip(rows, compilations, existing):
        if present is None:
            current = evaluate(
                root,
                compilation["request"],
                compilation["evaluation_context"],
                evaluated_at=at,
                skills_root=skills_root,
            )
            if current.get("decision") != "allowed" or not supplied_grant_matches(
                current, grants[row["action"]]
            ):
                raise ValueError("Authority changed after the all-three pure preflight")
            closure_values.append(current)
            decisions.append(None)
        else:
            closure_bindings.append(present["decision_binding"])
            decisions.append(present["decision_binding"])

    proofs = {}
    with selected_successor_reservation_scope(
        root,
        bundle_binding=bundle,
        compilation_bindings=compilation_bindings,
        decision_bindings=closure_bindings,
        decision_values=closure_values,
        skills_root=skills_root,
    ) as closure:
        _reservation_closure_hook("after_pure_preflight", root, closure)
        assert_executable_closure_epoch_current(root, closure)
        for index, (row, compilation, present, prior_binding) in enumerate(
            zip(rows, compilations, existing, decisions)
        ):
            if present is None:
                current = evaluate_and_publish(
                    root,
                    compilation["request"],
                    compilation["evaluation_context"],
                    evaluated_at=at,
                    skills_root=skills_root,
                )
                if current.get("decision") != "allowed" or not supplied_grant_matches(
                    current, grants[row["action"]]
                ):
                    raise ValueError(
                        "Authority changed after executable-closure preflight"
                    )
                decision_binding = {
                    "ref": current["decision_ref"],
                    "sha256": current["decision_sha256"],
                }
                decisions[index] = decision_binding
                assert_executable_closure_epoch_current(root, closure)
                reserved = reserve(
                    root,
                    decision_binding["ref"],
                    decision_binding["sha256"],
                    reserved_at=at,
                    idempotency_key=row["idempotency_key"],
                    skills_root=skills_root,
                )
                reservation = {
                    "ref": reserved["reservation_ref"],
                    "sha256": reserved["reservation_sha256"],
                }
            else:
                assert prior_binding is not None
                decision_binding = prior_binding
                reservation = present["reservation_binding"]
            verified = verify_and_publish_precommit(
                root,
                reservation["ref"],
                reservation["sha256"],
                verified_at=at,
                expected_version=0,
                skills_root=skills_root,
            )
            proofs[row["action"]] = {
                "reservation": reservation,
                "pre_commit_verification": {
                    "ref": verified["verification_ref"],
                    "sha256": verified["verification_sha256"],
                },
                "expected_version": 0,
            }
    if any(item is None for item in decisions):
        raise ValueError(
            "Selected-successor authority decision publication is incomplete"
        )
    return [item for item in decisions if item is not None], proofs


def publish_packet_result(
    root: Path,
    *,
    at: str,
    bundle: dict[str, str],
    request_context: dict[str, str],
    evaluation_context: dict[str, str],
    grants: dict[str, dict[str, Any]],
    operation_manifests: dict[str, dict[str, str]],
    rows: list[dict[str, Any]],
    compilations: list[dict[str, Any]],
    compilation_bindings: list[dict[str, str]],
    existing: list[dict[str, Any] | None],
    identity: dict[str, Any],
    input_sha: str,
    skills_root: Path | None,
) -> dict[str, Any]:
    decisions, proofs = _publish_chains(
        root,
        bundle,
        rows,
        compilations,
        compilation_bindings,
        grants,
        existing,
        at=at,
        skills_root=skills_root,
    )
    body = {
        "schema_version": 1,
        "artifact_kind": "selected_successor_authority_packet",
        "status": "all_three_owner_proofs_current",
        "prepared_at": at,
        "bundle": bundle,
        "request_context": request_context,
        "evaluation_context": evaluation_context,
        "grants": grants,
        "operation_manifests": operation_manifests,
        "operations": [
            {
                "action": row["action"],
                "compilation": {"ref": binding["ref"], "sha256": binding["sha256"]},
                "request_sha256": compilation["request_sha256"],
                "decision": decision,
                "selected_grant": grants[row["action"]],
            }
            for row, binding, compilation, decision in zip(
                rows, compilation_bindings, compilations, decisions
            )
        ],
        "authority_proofs": proofs,
        "authority_effects": {
            "renderer_created_source_approvals": False,
            "renderer_created_grants": False,
            "decisions_issued_by": "manage-agent-authority:evaluate_and_publish",
            "selected_successor_effects_applied": False,
        },
    }
    _candidate, expected_binding = packet_candidate(root, body)
    publish_locator(root, input_sha, expected_binding, operation_manifests)
    _packet, packet_binding, _created = publish_packet(root, body)
    if packet_binding != expected_binding:
        raise ValueError("Authority packet publication differs from its locator")
    publish_index(
        root, identity, input_sha, outcome_kind="packet", outcome=packet_binding
    )
    return {
        "result_kind": "selected_successor_authority_preparation_result",
        "schema_version": 1,
        "status": "prepared",
        "bundle": bundle,
        "authority_packet": packet_binding,
        "execute_argv": _argv(root, "execute", packet_binding, at, skills_root),
        "recover_argv": _argv(root, "recover", packet_binding, at, skills_root),
        "idempotent_replay": False,
        "mutation_performed": True,
        "model_authored_mechanical_bytes": 0,
    }


__all__ = (
    "aggregate_budget_reasons",
    "derived_projection_operation",
    "publish_packet_result",
    "publish_projection_result",
    "result_from_index",
    "supplied_grant_matches",
)
