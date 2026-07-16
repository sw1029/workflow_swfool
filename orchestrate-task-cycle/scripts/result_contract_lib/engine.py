from __future__ import annotations

from typing import Any

from .base import RuleRegistry
from .validation_pipeline import run_validation
from .validation_pipeline.shared import SESSION_AUDIT_RULE  # noqa: F401 - compatibility re-export


def _validate(
    target: str,
    result: dict[str, Any],
    mode: str,
    rule_registry: RuleRegistry,
    contract_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run the ordered validation pipeline behind the stable facade."""

    return run_validation(target, result, mode, rule_registry, contract_context)
