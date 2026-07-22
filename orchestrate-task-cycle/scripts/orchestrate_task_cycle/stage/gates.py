"""Existing-validator gates for compiled stage publication."""

from __future__ import annotations

from typing import Any

from ..validate_cycle_transition import validate as validate_transition


MODEL_JUDGMENT_TARGETS = frozenset(
    {"qualitative_review", "loopback_audit", "derive", "validate", "report"}
)


def boundary_reason(target: str, schema_version: int = 1) -> str:
    if target == "authority":
        return "awaiting_authority"
    if schema_version == 2:
        from .specs import TARGET_COMPILE_SPECS

        kind = TARGET_COMPILE_SPECS[target].executor_kind
        if kind == "hybrid":
            return "awaiting_model_judgment"
        if kind == "deterministic":
            return "awaiting_deterministic_result"
        return "awaiting_owner_result"
    if target in MODEL_JUDGMENT_TARGETS:
        return "awaiting_model_judgment"
    return "awaiting_owner_result"


def validate_submission_transition(
    context: dict[str, Any],
    preparation: dict[str, Any],
    routing: dict[str, Any] | None = None,
) -> dict[str, Any]:
    stage = (context.get("cycle_state") or {}).get("current_stage") or {}
    target = str(preparation["target"])
    return validate_transition(
        context,
        stage,
        f"pre_{target}",
        preparation.get("model_packet") if routing is None else routing,
        str(preparation["workflow_mode"]),
    )


__all__ = ["boundary_reason", "validate_submission_transition"]
