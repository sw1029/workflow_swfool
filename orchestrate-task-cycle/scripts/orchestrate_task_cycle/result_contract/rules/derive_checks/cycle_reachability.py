"""Route cycle-unreachable targets by launch state and exact run binding."""

from __future__ import annotations

from ...cycle_reachability import (
    assess_harvest_completion,
    assess_launch_contract,
    cycle_gate_from_result,
    first_declared,
    unreachable_declared,
    validate_unreachable_gate,
)
from .shared import add
from .state import DeriveFacts


PRELAUNCH_KINDS = {
    "long_run_launch",
    "throughput_improvement",
    "residual_descope",
    "descope_with_residual",
    "terminal_blocked",
    "terminal_blocker",
    "user_escalation",
}
SAFETY_KINDS = {"terminal_blocked", "terminal_blocker", "user_escalation"}


def _route_binding(result: dict[str, object]) -> dict[str, object]:
    value = first_declared(
        result,
        (
            "cycle_reachability_route_binding",
            "selected_task.cycle_reachability_route_binding",
            "selected_task.cycle_reachability_binding",
            "derive.cycle_reachability_route_binding",
            "result.cycle_reachability_route_binding",
        ),
    )
    return value if isinstance(value, dict) else {}


def _expected_active_kinds(status: str, harvest_complete: bool) -> set[str]:
    if status in {"launching", "running", "stale", "not_running"}:
        return {"long_run_monitor", *SAFETY_KINDS}
    if status == "completed_pending_validation":
        role = "long_run_finalize" if harvest_complete else "long_run_harvest"
        return {role, *SAFETY_KINDS}
    return set(SAFETY_KINDS)


def _add(
    facts: DeriveFacts,
    code: str,
    message: str,
    evidence: dict[str, object] | None = None,
) -> None:
    add(
        facts.findings,
        "block" if facts.mode == "block" else "warn",
        code,
        message,
        evidence,
    )


def _check_prelaunch(
    facts: DeriveFacts, digest: object, binding: dict[str, object]
) -> None:
    selected = facts.selected_kind
    if not facts.terminal_selected and selected not in PRELAUNCH_KINDS:
        _add(
            facts,
            "derive_cycle_reachability_prelaunch_route_invalid",
            "Before a bound run exists, cycle-unreachable work permits launch, throughput improvement, residual descope, terminal, or escalation—not monitor/harvest/finalize.",
            {"selected_task_kind": selected or None},
        )
    if binding.get("cycle_reachability_sha256") != digest:
        _add(
            facts,
            "derive_cycle_reachability_route_binding_missing",
            "The selected prelaunch route must bind the exact cycle-reachability calculation digest.",
        )
    if selected == "long_run_launch":
        assessment = assess_launch_contract(facts.result)
        if assessment.issues:
            _add(
                facts,
                "derive_long_run_launch_contract_invalid",
                "Long-run launch selection requires a matching run id, residual acceptance, and harvest validation plan.",
                {"contract_issues": assessment.issues},
            )


def _matching_pending_rows(
    pending: list[dict[str, object]],
    digest: object,
) -> list[dict[str, object]]:
    return [row for row in pending if row.get("cycle_reachability_sha256") == digest]


def _active_route_declared(
    binding: dict[str, object],
    pending: list[dict[str, object]],
    digest: object,
) -> bool:
    return bool(_matching_pending_rows(pending, digest)) or any(
        binding.get(key) not in (None, "") for key in ("run_id", "harvest_plan_id")
    )


def _check_active(
    facts: DeriveFacts,
    digest: object,
    binding: dict[str, object],
    pending: list[dict[str, object]],
) -> None:
    matches = _matching_pending_rows(pending, digest)
    if len(matches) != 1:
        _add(
            facts,
            "derive_pending_run_reachability_binding_missing",
            "A cycle-unreachable active-run route requires exactly one pending run bound to the same reachability digest.",
            {"matching_pending_run_count": len(matches)},
        )
        return
    row = matches[0]
    if row.get("binding_conflict"):
        _add(
            facts,
            "derive_pending_run_reachability_binding_conflict",
            "Conflicting identities for the same pending run must be repaired before monitor, harvest, finalize, terminal, or escalation routing.",
            {"binding_conflicts": row.get("binding_conflicts") or []},
        )
        return
    status = str(row.get("execution_status") or "").strip().lower()
    harvest_complete = assess_harvest_completion(facts.result).complete
    allowed = _expected_active_kinds(status, harvest_complete)
    if facts.selected_kind not in allowed:
        _add(
            facts,
            "derive_cycle_reachability_active_route_invalid",
            "Active cycle-unreachable work must monitor a live/stale run, harvest completed output, finalize a validated harvest, or take an explicit safety route.",
            {
                "execution_status": status or None,
                "selected_task_kind": facts.selected_kind or None,
                "allowed_task_kinds": sorted(allowed),
            },
        )
    expected = {
        "cycle_reachability_sha256": digest,
        "run_id": row.get("run_id"),
        "harvest_plan_id": row.get("harvest_plan_id"),
    }
    mismatches = [
        key
        for key, value in expected.items()
        if value is None or binding.get(key) != value
    ]
    if mismatches:
        _add(
            facts,
            "derive_cycle_reachability_active_binding_mismatch",
            "Monitor, harvest, finalize, terminal, and escalation routes must bind the exact pending run and harvest plan.",
            {"mismatched_fields": mismatches},
        )


def check_cycle_reachability(facts: DeriveFacts) -> None:
    if not unreachable_declared(facts.result):
        return
    gate = cycle_gate_from_result(facts.result)
    gate_issues = validate_unreachable_gate(gate)
    if gate_issues:
        _add(
            facts,
            "derive_cycle_reachability_contract_invalid",
            "Derive cannot route a cycle-unreachable claim without its valid content-bound calculation.",
            {"contract_issues": gate_issues},
        )
        return
    digest = gate.get("cycle_reachability_sha256") if isinstance(gate, dict) else None
    binding = _route_binding(facts.result)
    pending = [
        row
        for row in facts.context.get("pending_long_runs", [])
        if isinstance(row, dict)
    ]
    if _active_route_declared(binding, pending, digest):
        _check_active(facts, digest, binding, pending)
    else:
        _check_prelaunch(facts, digest, binding)


__all__ = ["check_cycle_reachability"]
