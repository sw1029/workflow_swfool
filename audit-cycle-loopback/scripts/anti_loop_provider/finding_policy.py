from __future__ import annotations

from .runtime_dependencies import (
    Any,
)

from .finding_policy_base import _collect_policy_base
from .finding_policy_enforcement import _collect_policy_enforcement


def _collect_policy_findings(state: dict[str, Any]) -> None:
    _collect_policy_base(state)
    _collect_policy_enforcement(state)
