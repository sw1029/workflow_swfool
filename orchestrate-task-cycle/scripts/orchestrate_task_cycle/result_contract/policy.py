from __future__ import annotations

from typing import Any

from .common import first_present, non_empty, value_for

PENDING_LONG_RUN_STATUSES = {
    "launching",
    "running",
    "completed_pending_validation",
    "stale",
    "not_running",
}
PENDING_RUN_BINDING_FIELDS = {
    "task_id",
    "cycle_reachability_sha256",
    "acceptance_scale_id",
    "throughput_evidence_id",
    "harvest_plan_id",
    "residual_acceptance_id",
}


def has_explicit_empty(
    result: dict[str, Any],
    field: str,
    expected_type: type[list[Any]] | type[dict[str, Any]],
) -> bool:
    containers = [result]
    for key in ("result", "packet"):
        nested = result.get(key)
        if isinstance(nested, dict):
            containers.append(nested)
    return any(
        field in container
        and isinstance(container.get(field), expected_type)
        and not container[field]
        for container in containers
    )


def reasoned_na_allows_explicit_empty(
    target: str, field: str, result: dict[str, Any]
) -> bool:
    if target == "qualitative_review":
        status = (
            str(value_for(result, "review_status") or value_for(result, "status") or "")
            .strip()
            .lower()
        )
        reason = first_present(
            result,
            [
                "reason",
                "review_skipped_reason",
                "qualitative_review_pending_reason",
                "reviewer_delegation_unavailable_reason",
                "blockers",
            ],
        )
        if status in {"not_applicable", "blocked"} and non_empty(reason):
            if field == "reviewer_routing":
                return has_explicit_empty(result, field, dict)
            if field == "evidence_paths":
                return has_explicit_empty(result, field, list)
    if target == "validation_set_build":
        status = (
            str(
                value_for(result, "validation_set_status")
                or value_for(result, "status")
                or ""
            )
            .strip()
            .lower()
        )
        reason = first_present(
            result,
            [
                "validation_set_not_applicable_reason",
                "validation_set_skipped_reason",
                "validation_set_blocked_reason",
                "reason",
                "blockers",
            ],
        )
        return (
            status == "not_applicable"
            and non_empty(reason)
            and field == "evidence_paths"
            and has_explicit_empty(result, field, list)
        )
    if target == "schema_post_derive":
        status = (
            str(value_for(result, "schema_status") or value_for(result, "status") or "")
            .strip()
            .lower()
        )
        reason = first_present(
            result,
            [
                "schema_skipped_reason",
                "schema_terminal_reason",
                "schema_blocked_reason",
                "reason",
                "blockers",
            ],
        )
        terminal = {
            "terminal",
            "terminal_blocked",
            "skipped",
            "not_applicable",
            "blocked",
            "deferred",
        }
        return (
            status in terminal
            and non_empty(reason)
            and field == "evidence_paths"
            and has_explicit_empty(result, field, list)
        )
    return False


def long_run_state_checked(
    contract_context: dict[str, Any] | None, result: dict[str, Any]
) -> bool:
    markers: list[Any] = [result.get("long_run_state_checked")]
    if isinstance(contract_context, dict):
        markers.append(contract_context.get("long_run_state_checked"))
        cycle_state = contract_context.get("cycle_state")
        if isinstance(cycle_state, dict):
            markers.append(cycle_state.get("long_run_state_checked"))
        long_run_state = contract_context.get("long_run_state")
        if isinstance(long_run_state, dict):
            markers.append(long_run_state.get("checked"))
    return any(value is True for value in markers)


def _pending_identity(row: dict[str, Any], fallback_index: int) -> tuple[str, str]:
    run_id = str(row.get("run_id") or "").strip()
    if run_id:
        return "run", run_id
    task_id = str(row.get("task_id") or "").strip()
    if task_id:
        return "task", task_id
    return "anonymous", str(fallback_index)


def _merge_pending_row(existing: dict[str, Any], incoming: dict[str, Any]) -> None:
    conflicts = existing.setdefault("binding_conflicts", [])
    for field, value in incoming.items():
        if field in {"binding_conflict", "binding_conflicts"} or value in (None, ""):
            continue
        prior = existing.get(field)
        if prior in (None, ""):
            existing[field] = value
            continue
        if field in PENDING_RUN_BINDING_FIELDS and prior != value:
            conflict = {
                "field": field,
                "observed_values": sorted({str(prior), str(value)}),
            }
            if conflict not in conflicts:
                conflicts.append(conflict)
            continue
        if field in {"execution_status", "event_kind", "remaining_validation"}:
            existing[field] = value
    existing["binding_conflict"] = bool(conflicts)


def _collect_pending_candidates(
    contract_context: dict[str, Any],
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    seen_objects: set[int] = set()

    def append(value: Any) -> None:
        if isinstance(value, dict) and id(value) not in seen_objects:
            candidates.append(value)
            seen_objects.add(id(value))
            append(value.get("run"))
            append(value.get("monitor_result"))

    events = contract_context.get("events")
    if isinstance(events, list):
        for value in events:
            append(value)
    cycle_state = contract_context.get("cycle_state")
    if isinstance(cycle_state, dict):
        nested_events = cycle_state.get("events")
        if isinstance(nested_events, list):
            for value in nested_events:
                append(value)
    steps = contract_context.get("steps")
    if isinstance(steps, dict):
        for value in steps.values():
            append(value)
    append(contract_context)
    append(cycle_state)
    latest_events = contract_context.get("latest_events")
    if isinstance(latest_events, list):
        for value in latest_events:
            append(value)
    if isinstance(cycle_state, dict):
        nested_latest_events = cycle_state.get("latest_events")
        if isinstance(nested_latest_events, list):
            for value in nested_latest_events:
                append(value)
    append(contract_context.get("latest_event"))
    if isinstance(cycle_state, dict):
        append(cycle_state.get("latest_event"))
    return candidates


def _pending_row(candidate: dict[str, Any]) -> dict[str, Any] | None:
    status = (
        str(
            candidate.get("execution_status")
            or candidate.get("source_status")
            or candidate.get("status")
            or ""
        )
        .strip()
        .lower()
    )
    event_kind = str(candidate.get("event_kind") or "").strip().lower()
    role = str(candidate.get("long_run_role") or "").strip().lower()
    run_id = str(candidate.get("run_id") or "").strip()
    is_long_run = (
        bool(candidate.get("long_run_branch"))
        or event_kind.startswith("long_run_")
        or role in {"launch", "monitor", "harvest", "finalize"}
    )
    if status not in PENDING_LONG_RUN_STATUSES or not (is_long_run or run_id):
        return None
    task_id = str(
        candidate.get("owner_task_id") or candidate.get("task_id") or ""
    ).strip()
    gate = candidate.get("cycle_reachability_gate")
    plan = candidate.get("harvest_validation_plan")
    residual = candidate.get("residual_acceptance")
    gate = gate if isinstance(gate, dict) else {}
    plan = plan if isinstance(plan, dict) else {}
    residual = residual if isinstance(residual, dict) else {}
    scale = (
        gate.get("acceptance_scale")
        if isinstance(gate.get("acceptance_scale"), dict)
        else {}
    )
    throughput = (
        gate.get("throughput_evidence")
        if isinstance(gate.get("throughput_evidence"), dict)
        else {}
    )
    return {
        "run_id": run_id or None,
        "task_id": task_id or None,
        "execution_status": status,
        "event_kind": event_kind or None,
        "remaining_validation": candidate.get("remaining_validation"),
        "cycle_reachability_sha256": gate.get("cycle_reachability_sha256"),
        "acceptance_scale_id": scale.get("acceptance_scale_id"),
        "throughput_evidence_id": throughput.get("throughput_evidence_id"),
        "harvest_plan_id": plan.get("harvest_plan_id"),
        "residual_acceptance_id": residual.get("residual_acceptance_id"),
        "binding_conflict": False,
        "binding_conflicts": [],
    }


def pending_long_run_context(
    contract_context: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Extract and merge scalar pending-run evidence from cycle context."""

    if not isinstance(contract_context, dict):
        return []
    pending: list[dict[str, Any]] = []
    pending_index: dict[tuple[str, str], int] = {}
    for candidate in _collect_pending_candidates(contract_context):
        row = _pending_row(candidate)
        if row is None:
            continue
        identity = _pending_identity(row, len(pending))
        if identity in pending_index:
            existing = pending[pending_index[identity]]
            _merge_pending_row(existing, row)
            continue
        pending_index[identity] = len(pending)
        pending.append(row)
    return pending
