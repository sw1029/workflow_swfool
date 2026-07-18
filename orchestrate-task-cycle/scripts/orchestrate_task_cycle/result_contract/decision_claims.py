from __future__ import annotations

from typing import Any

from .common import boolish, first_present, list_values
from .receipts import _declared_values, _normalized_verdict_status


def semantic_claim(result: dict[str, Any]) -> bool:
    direct_read_scope = {
        str(item).strip().lower()
        for item in list_values(
            first_present(
                result,
                [
                    "direct_read_scope",
                    "quality_review.direct_read_scope",
                    "qualitative_review.direct_read_scope",
                    "result.direct_read_scope",
                ],
            )
        )
        if str(item).strip()
    }
    semantic_values = _declared_values(
        result,
        (
            "artifact_semantic_verdict",
            "verdict_axes.artifact_semantic_verdict",
            "result.artifact_semantic_verdict",
            "result.verdict_axes.artifact_semantic_verdict",
            "goal_readiness_verdict",
            "verdict_axes.goal_readiness_verdict",
            "result.goal_readiness_verdict",
            "result.verdict_axes.goal_readiness_verdict",
        ),
    )
    return bool(
        "artifact_body" in direct_read_scope
        or any(_normalized_verdict_status(value) == "pass" for value in semantic_values)
        or boolish(
            first_present(
                result,
                ["semantic_progress", "authoritative_semantic_progress"],
            )
        )
        or str(
            first_present(result, ["progress_kind", "effective_progress_kind"]) or ""
        )
        .strip()
        .lower()
        == "goal_productive"
    )


__all__ = ["semantic_claim"]
