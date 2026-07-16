from __future__ import annotations

from pathlib import Path
from typing import Any

from .aggregation import build_audit_state
from .contracts import normalize_convention_contract
from .report import render_result


def audit(
    root: Path,
    files: list[str],
    thresholds: dict[str, int],
    task_id: str | None,
    convention_contract: dict[str, Any] | None = None,
) -> dict[str, Any]:
    contract = convention_contract or normalize_convention_contract(None)
    state = build_audit_state(root, files, thresholds, contract)
    return render_result(state, thresholds, task_id, contract)
