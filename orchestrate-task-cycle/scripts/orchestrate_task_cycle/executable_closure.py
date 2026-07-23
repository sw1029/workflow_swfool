"""Read-only executable-closure preflight for authority operation batches.

The authority compiler proves that an operation batch is exact.  This module
answers a different question: whether that exact batch is attached to a task
and cycle that may currently execute.  It never publishes, reserves, or
mutates workflow state.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable
from typing import Sequence

from .ledger.support import read_initialization_metadata
from .ledger.workflow_contract import workflow_contract_state
from .selection_decision_store import normalize_binding
from .selected_successor import load_selected_successor_bundle
from .selected_successor_execution_support import execution_rows
from .executable_closure_snapshot import (
    build_closure_epoch,
    current_task_alias,
    topology_predecessor_binding,
)


SCHEMA_VERSION = 1
ARTIFACT_KIND = "executable_closure_preflight"

READY = "ready"
BLOCKED = "blocked_prerequisite"
INVALID = "invalid"

CURRENT_CYCLE = "current_cycle"
SELECTED_SUCCESSOR_TOPOLOGY = "selected_successor_topology"
FRESH_CYCLE = "fresh_cycle"

HISTORICAL_STATES = {
    "historical_v1_read_only": "source_cycle_historical_v1_read_only",
    "historical_v2_read_only": "source_cycle_historical_v2_read_only",
}
COMPLETED_TASK_STATUSES = {"complete", "completed"}
OPERATION_IDENTITY_FIELDS = (
    "skill_id",
    "skill_version",
    "operation_id",
    "operation_version",
)


def _common_scope(
    compilations: list[dict[str, Any]],
) -> tuple[str, str]:
    if not compilations:
        raise ValueError("Executable closure requires at least one operation")
    requests = [
        item.get("request") if isinstance(item, dict) else None for item in compilations
    ]
    if any(not isinstance(item, dict) for item in requests):
        raise ValueError("Executable closure operation request is invalid")
    cycle_ids = {str(item.get("cycle_id") or "") for item in requests}
    task_ids = {str(item.get("task_id") or "") for item in requests}
    if (
        len(cycle_ids) != 1
        or len(task_ids) != 1
        or not next(iter(cycle_ids))
        or not next(iter(task_ids))
    ):
        raise ValueError(
            "Executable closure operation batch lacks one exact cycle and task"
        )
    return next(iter(cycle_ids)), next(iter(task_ids))


def _request_projection(request: dict[str, Any]) -> dict[str, Any]:
    return {
        "operation": {field: request.get(field) for field in OPERATION_IDENTITY_FIELDS},
        "subject": request.get("subject"),
        "idempotency_key": request.get("idempotency_key"),
    }


def _bundle_projection(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "operation": {
            field: row.get("operation", {}).get(field)
            for field in OPERATION_IDENTITY_FIELDS
        },
        "subject": row.get("subject"),
        "idempotency_key": row.get("idempotency_key"),
    }


def _topology_matches(
    root: Path,
    bundle: dict[str, Any],
    compilations: list[dict[str, Any]],
    *,
    cycle_id: str,
    task_id: str,
) -> bool:
    rows = execution_rows(bundle)
    if (
        bundle.get("selected_task_id") != task_id
        or len(rows) != len(compilations)
        or [_bundle_projection(row) for row in rows]
        != [_request_projection(item["request"]) for item in compilations]
    ):
        return False
    # Selected-successor authority is scoped to the exact derive trigger cycle,
    # not merely to a caller-supplied cycle string.
    from .selected_successor_authority import _cycle_id

    return _cycle_id(root, bundle) == cycle_id


def _load_decisions(
    root: Path,
    values: Iterable[dict[str, str]],
) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
    from manage_agent_authority.evaluator import load_bound_decision
    from manage_agent_authority.projection_reservations import (
        validate_decision_artifact,
    )

    bindings: list[dict[str, str]] = []
    decisions: list[dict[str, Any]] = []
    for index, value in enumerate(values):
        binding = normalize_binding(value, f"authority decision[{index}]")
        decision, path = load_bound_decision(root, binding["ref"], binding["sha256"])
        validate_decision_artifact(root, decision, path)
        canonical = {
            "ref": path.relative_to(root).as_posix(),
            "sha256": binding["sha256"],
        }
        if canonical != binding:
            raise ValueError("Authority decision binding is not canonical")
        bindings.append(canonical)
        decisions.append(decision)
    return bindings, decisions


def _topology_has_exact_allowed_decisions(
    decisions: list[dict[str, Any]],
    compilations: list[dict[str, Any]],
) -> bool:
    expected = {item["request_sha256"]: item for item in compilations}
    if len(expected) != len(compilations) or len(decisions) != len(expected):
        return False
    observed: dict[str, dict[str, Any]] = {}
    for decision in decisions:
        request_sha = decision.get("request_sha256")
        compilation = expected.get(request_sha)
        if (
            decision.get("decision") != "allowed"
            or not isinstance(request_sha, str)
            or request_sha in observed
            or not isinstance(compilation, dict)
            or compilation.get("request") != decision.get("request")
            or compilation.get("evaluation_context")
            != decision.get("evaluation_context")
            or compilation.get("evaluation_context_sha256")
            != decision.get("evaluation_context_sha256")
            or compilation.get("operation_manifest")
            != decision.get("operation_manifest")
        ):
            return False
        observed[request_sha] = decision
    return set(observed) == set(expected)


def _next_action(status: str, route: str, bundle_present: bool) -> str:
    if status == INVALID:
        return "repair_executable_closure_inputs"
    if status == READY:
        return (
            "execute_selected_successor_topology"
            if route == SELECTED_SUCCESSOR_TOPOLOGY
            else "execute_authority_operation_batch"
        )
    if route == FRESH_CYCLE:
        return "initialize_fresh_compiler_first_cycle"
    if route == SELECTED_SUCCESSOR_TOPOLOGY:
        return (
            "prepare_selected_successor_topology_authority"
            if bundle_present
            else "prepare_selected_successor_topology"
        )
    return "repair_executable_closure_prerequisites"


def _classify_route(
    *,
    topology_exact: bool,
    topology_shape_exact: bool,
    bundle_present: bool,
    alias: dict[str, Any] | None,
    alias_id: str | None,
    alias_status: str | None,
    alias_executable: bool,
    task_id: str,
    contract_state: str,
    metadata: dict[str, Any] | None,
    decision_mismatch: bool,
    decisions: list[dict[str, Any]],
    compilations: list[dict[str, Any]],
    reasons: set[str],
) -> tuple[str, str]:
    route = CURRENT_CYCLE
    status = READY
    historical_reason = HISTORICAL_STATES.get(contract_state)

    if topology_exact:
        route = SELECTED_SUCCESSOR_TOPOLOGY
        if not _topology_has_exact_allowed_decisions(decisions, compilations):
            reasons.add("selected_successor_topology_grants_required")
            status = BLOCKED
        if decision_mismatch or contract_state == "invalid":
            status = INVALID
    elif bundle_present:
        route = SELECTED_SUCCESSOR_TOPOLOGY
        if historical_reason is not None:
            reasons.add(historical_reason)
        reasons.add(
            "selected_successor_topology_predecessor_mismatch"
            if topology_shape_exact
            else "selected_successor_topology_bundle_mismatch"
        )
        reasons.add("operation_batch_task_not_executable")
        status = INVALID
    elif alias_status in COMPLETED_TASK_STATUSES:
        if historical_reason is not None:
            reasons.add(historical_reason)
        route = SELECTED_SUCCESSOR_TOPOLOGY
        reasons.update(
            {
                "current_task_completed_non_executable",
                "selected_successor_topology_required",
                "selected_successor_topology_bundle_missing",
            }
        )
        status = BLOCKED
    else:
        if historical_reason is not None:
            reasons.add(historical_reason)
        initialized_task = (
            str(metadata.get("task_id") or "") if metadata is not None else ""
        )
        if contract_state != "enforced":
            reasons.add("fresh_compiler_first_cycle_required")
            reasons.add("operation_batch_cycle_not_executable")
            route = FRESH_CYCLE
            status = (
                INVALID if contract_state == "invalid" or decision_mismatch else BLOCKED
            )
        if alias is None or alias_id != task_id or not alias_executable:
            reasons.add("operation_batch_task_not_executable")
            status = INVALID if alias is None else BLOCKED
        if initialized_task != task_id:
            reasons.add("operation_batch_task_not_executable")
            route = FRESH_CYCLE
            status = INVALID
        if decision_mismatch:
            status = INVALID

    if alias is None:
        status = INVALID
    if status == READY:
        reasons.add("executable_closure_ready")
    return status, route


def _preflight_loaded_closure(
    root: Path,
    compilations: list[dict[str, Any]],
    *,
    operation_batch: dict[str, Any],
    operation_count: int,
    selected_successor_bundle_binding: dict[str, str] | None = None,
    decision_bindings: Iterable[dict[str, str]] = (),
    decision_values: Iterable[dict[str, Any]] = (),
) -> dict[str, Any]:
    """Classify one already validated compilation set without mutating state."""

    cycle_id, task_id = _common_scope(compilations)
    normalized_decisions, decisions = _load_decisions(root, decision_bindings)
    for value in decision_values:
        if not isinstance(value, dict):
            raise ValueError("Ephemeral authority decision must be an object")
        decisions.append(value)
        normalized_decisions.append(
            {
                "applicability": "ephemeral_current_evaluation",
                "request_sha256": value.get("request_sha256"),
            }
        )

    reasons: set[str] = set()
    decision_cycle_ids = {
        str(item.get("request", {}).get("cycle_id") or "") for item in decisions
    }
    decision_task_ids = {
        str(item.get("request", {}).get("task_id") or "") for item in decisions
    }
    if decision_cycle_ids and decision_cycle_ids != {cycle_id}:
        reasons.add("authority_decision_cycle_mismatch")
    if decision_task_ids and decision_task_ids != {task_id}:
        reasons.add("authority_decision_task_mismatch")

    alias, task_source, index_source = current_task_alias(root)
    alias_id = str(alias.get("id") or "") if alias is not None else None
    alias_status = str(alias.get("status") or "") if alias is not None else None
    alias_executable = alias_status == "active"
    if alias is None:
        reasons.add("current_task_alias_missing_or_ambiguous")

    bundle_binding: dict[str, str] | None = None
    bundle: dict[str, Any] | None = None
    topology_shape_exact = topology_exact = False
    predecessor_snapshot: dict[str, str] | None = None
    if selected_successor_bundle_binding is not None:
        bundle_binding = normalize_binding(
            selected_successor_bundle_binding, "selected-successor bundle"
        )
        bundle = load_selected_successor_bundle(root, bundle_binding)
        topology_shape_exact = _topology_matches(
            root,
            bundle,
            compilations,
            cycle_id=cycle_id,
            task_id=task_id,
        )
        if topology_shape_exact:
            predecessor_snapshot = topology_predecessor_binding(
                root,
                bundle,
                alias=alias,
                task_source=task_source,
                index_source=index_source,
                task_id=task_id,
            )
        topology_exact = predecessor_snapshot is not None
    metadata: dict[str, Any] | None = None
    contract_state = "invalid"
    try:
        metadata = read_initialization_metadata(root, cycle_id)
        contract_state = workflow_contract_state(metadata)
    except (OSError, UnicodeError, ValueError):
        reasons.add("source_cycle_contract_invalid")
    if contract_state == "invalid":
        reasons.add("source_cycle_contract_invalid")
    decision_mismatch = bool(
        {
            "authority_decision_cycle_mismatch",
            "authority_decision_task_mismatch",
        }.intersection(reasons)
    )
    status, route = _classify_route(
        topology_exact=topology_exact,
        topology_shape_exact=topology_shape_exact,
        bundle_present=bundle is not None,
        alias=alias,
        alias_id=alias_id,
        alias_status=alias_status,
        alias_executable=alias_executable,
        task_id=task_id,
        contract_state=contract_state,
        metadata=metadata,
        decision_mismatch=decision_mismatch,
        decisions=decisions,
        compilations=compilations,
        reasons=reasons,
    )

    current_task = (
        {
            "task_id": alias_id,
            "status": alias_status,
            "executable": alias_executable,
            "source": task_source,
        }
        if alias is not None
        else None
    )
    closure_epoch = build_closure_epoch(
        alias_id=alias_id,
        task_source=task_source,
        index_source=index_source,
        bundle=bundle,
        topology_exact=topology_exact,
        predecessor_snapshot=predecessor_snapshot,
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "artifact_kind": ARTIFACT_KIND,
        "status": status,
        "route": route,
        "cycle_id": cycle_id,
        "task_id": task_id,
        "cycle_contract_state": contract_state,
        "current_task": current_task,
        "operation_batch": operation_batch,
        "operation_count": operation_count,
        "selected_successor_bundle": bundle_binding,
        "closure_epoch": closure_epoch,
        "authority_decisions": normalized_decisions,
        "reason_codes": sorted(reasons),
        "next_action": _next_action(status, route, bundle is not None),
        "mutation_performed": False,
    }


def preflight_executable_closure(
    root: Path,
    operation_batch_binding: dict[str, str],
    selected_successor_bundle_binding: dict[str, str] | None = None,
    decision_bindings: Iterable[dict[str, str]] = (),
) -> dict[str, Any]:
    """Verify that a compiled authority batch has an executable lifecycle route."""

    from manage_agent_authority.operation_batch import load_operation_batch

    workspace = root.expanduser().resolve(strict=True)
    batch_binding, batch, compilations = load_operation_batch(
        workspace, operation_batch_binding
    )
    return _preflight_loaded_closure(
        workspace,
        compilations,
        operation_batch=batch_binding,
        operation_count=batch["operation_count"],
        selected_successor_bundle_binding=selected_successor_bundle_binding,
        decision_bindings=decision_bindings,
    )


def main(argv: Sequence[str] | None = None) -> int:
    from .executable_closure_cli import main as cli_main

    return cli_main(argv)


__all__ = ("main", "preflight_executable_closure")


if __name__ == "__main__":
    raise SystemExit(main())
