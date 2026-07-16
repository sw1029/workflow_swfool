from __future__ import annotations

from .runtime_dependencies import (
    Any,
)

from .finding_adapter import _collect_adapter_findings
from .finding_policy import _collect_policy_findings
from .finding_progress import _collect_progress_findings
from .finding_root_cause import _collect_root_cause_findings
from .finding_terminal import _collect_terminal_findings


def apply_disposition_and_findings(ns: dict[str, Any]) -> dict[str, Any]:
    state = dict(ns)
    _collect_policy_findings(state)
    _collect_root_cause_findings(state)
    _collect_progress_findings(state)
    _collect_adapter_findings(state)
    return _collect_terminal_findings(state)
