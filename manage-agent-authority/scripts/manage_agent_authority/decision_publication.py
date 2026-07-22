"""Evaluate one closed authority request and publish only that canonical result."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .artifact_store import AUTHORIZATION_ROOT
from .canonical import write_immutable_json
from .evaluator import evaluate


def evaluate_and_publish(
    root: Path,
    raw_request: dict[str, Any],
    raw_context: dict[str, Any],
    *,
    evaluated_at: str,
    skills_root: Path | None = None,
) -> dict[str, Any]:
    """Evaluate canonical inputs and immutably publish the derived decision."""

    root = root.resolve()
    decision = evaluate(
        root,
        raw_request,
        raw_context,
        evaluated_at=evaluated_at,
        skills_root=skills_root,
    )
    path = root / AUTHORIZATION_ROOT / "decisions" / f"{decision['decision_id']}.json"
    digest = write_immutable_json(path, decision, "authority decision")
    return {
        **decision,
        "decision_ref": path.relative_to(root).as_posix(),
        "decision_sha256": digest,
    }


__all__ = ("evaluate_and_publish",)
