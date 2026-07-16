from __future__ import annotations

from .runtime_dependencies import (
    Any,
)

from .finding_progress_routing import _collect_progress_routing_findings
from .finding_mutation import _collect_mutation_findings


def _collect_progress_findings(state: dict[str, Any]) -> None:
    _collect_progress_routing_findings(state)
    _collect_mutation_findings(state)
