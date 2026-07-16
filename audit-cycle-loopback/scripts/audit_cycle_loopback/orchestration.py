"""Lazy adapter for the orchestration package's verified ledger API."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def load_current_finalized_state(root: Path, cycle_id: str) -> dict[str, Any]:
    try:
        from orchestrate_task_cycle import load_current_finalized_state as load_state
    except (AttributeError, ImportError) as exc:
        raise RuntimeError("orchestrate_task_cycle ledger API is unavailable") from exc
    return load_state(root, cycle_id)


__all__ = ("load_current_finalized_state",)
