"""Reopen terminal owner and authority evidence before reporting completion."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .authority import validate_completion
from .common import require


def validate_terminal_operations(root: Path, journal: dict[str, Any]) -> None:
    """Fail closed when a terminal journal row lacks current typed evidence."""

    for operation_id, state in journal["operation_state"].items():
        if state["status"] not in {"complete", "skipped"}:
            continue
        evidence = state.get("result_evidence")
        require(isinstance(evidence, dict), "invalid_journal",
                f"terminal operation {operation_id} lacks completion evidence")
        _completion, effect = validate_completion(
            root, journal, operation_id, evidence.get("ref", ""),
            evidence.get("sha256", ""),
        )
        if state["status"] == "skipped":
            require(effect == "confirmed_no_effect", "invalid_journal",
                    f"skipped operation {operation_id} lacks verified no-effect proof")


__all__ = ["validate_terminal_operations"]
