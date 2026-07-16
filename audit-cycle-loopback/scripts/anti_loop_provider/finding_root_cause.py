from __future__ import annotations

from .runtime_dependencies import (
    Any,
)

from .finding_acceptance import _collect_acceptance_findings
from .finding_root_resolution import _collect_root_resolution_findings


def _collect_root_cause_findings(state: dict[str, Any]) -> None:
    _collect_acceptance_findings(state)
    _collect_root_resolution_findings(state)
