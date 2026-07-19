"""Closed request assembly for the authority operation compiler."""

from __future__ import annotations

from typing import Any

from .contracts import validate_request


def build_request(
    manifest: dict[str, Any],
    operation: dict[str, Any],
    seed_core: dict[str, Any],
    classification: dict[str, Any],
    seed_fingerprint: str,
) -> dict[str, Any]:
    scope = seed_core["scope"]
    return validate_request({
        "schema_version": 2,
        "request_kind": "authority_operation",
        "request_id": f"authr-{seed_fingerprint[:24]}",
        "skill_id": manifest["skill_id"],
        "skill_version": manifest["skill_version"],
        "operation_id": operation["operation_id"],
        "operation_version": operation["operation_version"],
        "cycle_id": scope.get("cycle_id"),
        "task_id": scope.get("task_id"),
        "pack_id": scope.get("pack_id"),
        "attempt_id": f"attempt-{seed_fingerprint[:24]}",
        "actor_rank": seed_core["actor_rank"],
        "subject": seed_core["subject"],
        "required_capabilities": classification["required_capabilities"],
        "effect_class": classification["effect_class"],
        "data_class": classification["data_class"],
        "mutation_class": classification["mutation_class"],
        "reversibility": classification["reversibility"],
        "risk_tier": classification["risk_tier"],
        "decision_class": classification["decision_class"],
        "intent_type": seed_core["intent_type"],
        "cardinality_requested": seed_core["cardinality_requested"],
        "use_budget_requested": seed_core["use_budget_requested"],
        "reservation_units": seed_core["reservation_units"],
        "idempotency_key": f"request-{seed_fingerprint[:24]}",
        "context": seed_core["request_context"],
        "composition_receipt": seed_core["composition_receipt"],
    })


__all__ = ["build_request"]
