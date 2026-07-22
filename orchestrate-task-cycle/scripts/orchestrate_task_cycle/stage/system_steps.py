"""Deterministic canonical pseudo-stage event rendering."""

from __future__ import annotations

from typing import Any

from .contracts import canonical_sha256, state_fingerprint
from .specs import TargetCompileSpec
from .v2_specs import SYSTEM_STEPS


SYSTEM_REASONS = {
    "route_plan": "deterministic target routing checkpoint",
    "result_contract": "deterministic result contract checkpoint",
    "ledger_append": "deterministic ledger publication checkpoint",
}


def compile_derived_values(
    spec: TargetCompileSpec,
    cycle_id: str,
    target: str,
    task_id: str | None,
    model: dict[str, Any],
) -> dict[str, Any]:
    advice = model.get("advice") if isinstance(model.get("advice"), dict) else {}
    candidates: dict[str, Any] = {
        "step": target,
        "cycle_id": cycle_id,
        "task_id": task_id,
        "used_goal_truth": list(
            (model.get("goal_truth") or {}).get("used_goal_truth") or []
        ),
        "used_advice": [
            item.get("advice_id")
            for item in advice.get("items") or []
            if isinstance(item, dict) and item.get("advice_id")
        ],
    }
    return {
        field: candidates[field]
        for field in spec.derived_fields
        if candidates.get(field) is not None
    }


def render_context_event(
    cycle_id: str,
    task_id: str | None,
    full: dict[str, Any],
    model: dict[str, Any],
) -> dict[str, Any]:
    identity = {
        "cycle_id": cycle_id,
        "task": model.get("task"),
        "goal_truth": model.get("goal_truth"),
        "advice_digest": (model.get("advice") or {}).get("advice_packet_digest"),
    }
    return {
        "step": "context",
        "status": "completed",
        "event_id": "stage-context-" + canonical_sha256(identity)[:32],
        "reason": "deterministic cycle context projection",
        "task_id": task_id,
        "task_absent": task_id is None,
        "task_md": full.get("task_md"),
        "used_goal_truth": (model.get("goal_truth") or {}).get("used_goal_truth", []),
        "used_advice": [
            item.get("advice_id")
            for item in (model.get("advice") or {}).get("items", [])
            if isinstance(item, dict) and item.get("advice_id")
        ],
        "context_fingerprint": state_fingerprint(model),
    }


def render_system_event(
    cycle_id: str,
    target: str,
    task_id: str | None,
    events: list[dict[str, Any]],
) -> dict[str, Any]:
    if target not in SYSTEM_STEPS - {"context"}:
        raise ValueError(f"unsupported deterministic system step: {target}")
    predecessor = events[-1].get("event_id") if events else None
    identity = {
        "cycle_id": cycle_id,
        "step": target,
        "predecessor_event_id": predecessor,
    }
    return {
        "step": target,
        "status": "completed",
        "event_id": f"stage-system-{target}-{canonical_sha256(identity)[:24]}",
        "reason": SYSTEM_REASONS[target],
        "task_id": task_id,
        "compiler_protocol_version": 2,
        "predecessor_event_id": predecessor,
    }


__all__ = [
    "compile_derived_values",
    "render_context_event",
    "render_system_event",
]
