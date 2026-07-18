from __future__ import annotations

from ...scoped_progress import validate_scoped_progress
from .shared import add
from .state import DeriveFacts


def check_scoped_progress(facts: DeriveFacts) -> None:
    def emit(
        code: str,
        message: str,
        evidence: dict[str, object] | None,
    ) -> None:
        add(
            facts.findings,
            "block" if facts.mode == "block" else "warn",
            code,
            message,
            evidence,
        )

    validate_scoped_progress(facts.result, "derive", emit)
