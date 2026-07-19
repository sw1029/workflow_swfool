"""Validate legacy exact and v2 JIT reservation timing recipes."""

from __future__ import annotations

from typing import Any

from manage_agent_authority.canonical import parse_time

from .common import WorkflowError, require


def _time(value: Any, label: str):
    try:
        return parse_time(value, label)
    except SystemExit as error:
        raise WorkflowError(
            "invalid_authority_contract", f"{label} is invalid: {error}"
        ) from error


def verify_reservation_recipe(
    reservation: dict[str, Any], recipe: dict[str, Any],
) -> None:
    require(
        reservation["idempotency_key"] == recipe["idempotency_key"],
        "authority_binding_mismatch",
        "reservation idempotency recipe mismatch",
    )
    actual = _time(reservation["reserved_at"], "reservation.reserved_at")
    if "reserved_at" in recipe:
        require(
            actual == _time(recipe["reserved_at"], "planned reservation.reserved_at"),
            "authority_binding_mismatch",
            "reservation materialization recipe mismatch",
        )
        return
    not_before = _time(recipe["not_before"], "reservation.not_before")
    expires_at = _time(recipe["expires_at"], "reservation.expires_at")
    require(
        not_before <= actual < expires_at,
        "authority_binding_mismatch",
        "actual reservation time falls outside the planned JIT window",
    )


__all__ = ["verify_reservation_recipe"]
