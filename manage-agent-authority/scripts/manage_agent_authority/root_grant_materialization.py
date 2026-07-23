"""Materialize one plan-bound root decision as a recoverable transaction."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .root_decision_seed import normalize_root_decision_seed
from .root_grant_transaction import commit_root_grant_transaction


def validate_root_approval_decision(
    value: Any,
    *,
    plan_binding: dict[str, str],
    plan: dict[str, Any],
) -> dict[str, Any]:
    return normalize_root_decision_seed(
        value, plan_binding=plan_binding, plan=plan
    )


def materialize_exact_echo_root_grant(
    root: Path,
    plan_binding: dict[str, str],
    decision_binding: dict[str, str],
    *,
    skills_root: Path | None = None,
) -> dict[str, Any]:
    return commit_root_grant_transaction(
        root.resolve(),
        plan_binding,
        decision_binding,
        skills_root=skills_root,
    )


materialize_plan_bound_root_grant = materialize_exact_echo_root_grant


__all__ = (
    "materialize_exact_echo_root_grant",
    "materialize_plan_bound_root_grant",
    "validate_root_approval_decision",
)
