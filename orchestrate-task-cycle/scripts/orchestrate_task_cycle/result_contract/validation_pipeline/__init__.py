from __future__ import annotations

from typing import Any

from ...acceptance_contract import consumer_projection
from ..base import RuleRegistry
from .artifact_class import check_artifact_class
from .common import check_common
from .consumers import check_consumers
from .finalize import check_finalize
from .ledger import check_ledger
from .reports import check_reports
from .routing import check_routing
from .state import ValidationState


def run_validation(
    target: str,
    result: dict[str, Any],
    mode: str,
    rule_registry: RuleRegistry,
    contract_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    projected, conflicts = consumer_projection(result)
    state = ValidationState(
        target, projected, mode, rule_registry, contract_context
    )
    check_common(state)
    for field in conflicts:
        state.findings.append(
            {
                "severity": "block",
                "code": "acceptance_contract_canonical_path_conflict",
                "message": (
                    "A legacy acceptance alias conflicts with the canonical "
                    "acceptance_contract path."
                ),
                "evidence": {"field": field},
            }
        )
    check_routing(state)
    check_ledger(state)
    check_reports(state)
    check_consumers(state)
    check_artifact_class(state)
    return check_finalize(state)
