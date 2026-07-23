"""Post-gate publication and equality checks for native owner projections."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from .builder import ResultBuilder
from .contracts import canonical_bytes
from .native_results import native_owner_artifact_kind


ExactJudgmentLoader = Callable[..., tuple[
    dict[str, Any],
    dict[str, Any],
    dict[str, Any] | None,
]]
ResultValidator = Callable[
    [str, dict[str, Any], str, dict[str, Any] | None],
    dict[str, Any],
]


def publish_validated_projection(
    root: Path,
    preparation: dict[str, Any],
    predicted_judgment: dict[str, Any],
    predicted_routing: dict[str, Any] | None,
    predicted_result: dict[str, Any],
    predicted_validation: dict[str, Any],
    full: dict[str, Any],
    mode: str,
    *,
    exact_loader: ExactJudgmentLoader,
    result_validator: ResultValidator,
    owner_result_ref: str | None,
    owner_result_sha256: str | None,
    semantic_ref: str | None,
    semantic_sha256: str | None,
    routing_ref: str | None,
    routing_sha256: str | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if native_owner_artifact_kind(str(preparation["target"])) is None:
        return predicted_judgment, predicted_result
    judgment, _bindings, routing = exact_loader(
        root,
        preparation,
        owner_result_ref=owner_result_ref,
        owner_result_sha256=owner_result_sha256,
        semantic_ref=semantic_ref,
        semantic_sha256=semantic_sha256,
        routing_ref=routing_ref,
        routing_sha256=routing_sha256,
        publish_native_artifacts=True,
    )
    if canonical_bytes(
        {"judgment": judgment, "routing": routing}
    ) != canonical_bytes(
        {"judgment": predicted_judgment, "routing": predicted_routing}
    ):
        raise RuntimeError(
            "published native projection differs from validated prediction"
        )
    result = ResultBuilder().build(preparation, judgment)
    validation = result_validator(
        str(preparation["target"]), result, mode, full
    )
    if (
        canonical_bytes(result) != canonical_bytes(predicted_result)
        or canonical_bytes(validation)
        != canonical_bytes(predicted_validation)
    ):
        raise RuntimeError(
            "published native result differs from validated prediction"
        )
    return judgment, result


__all__ = ["publish_validated_projection"]
