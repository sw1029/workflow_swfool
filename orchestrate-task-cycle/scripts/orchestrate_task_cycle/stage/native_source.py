"""Revalidate native owner sources behind preparation-bound stage wrappers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .contracts import canonical_bytes
from .native_results import (
    native_owner_artifact_kind,
    normalize_native_owner_result,
)
from .storage_common import read_exact_json


def native_source_result(
    root: Path,
    source_binding: Any,
    *,
    target: str,
    cycle_id: str,
    sealed_body: dict[str, Any],
    maximum_bytes: int,
    publish_native_artifacts: bool,
    predict_native_artifacts: bool,
) -> dict[str, Any]:
    if (
        native_owner_artifact_kind(target) is None
        or not isinstance(source_binding, dict)
        or set(source_binding) != {"ref", "sha256", "size_bytes"}
    ):
        raise ValueError("owner result source binding is invalid")
    source_value, source_payload, _source_path = read_exact_json(
        root,
        str(source_binding.get("ref") or ""),
        str(source_binding.get("sha256") or ""),
        maximum_bytes,
    )
    if (
        source_binding.get("size_bytes") != len(source_payload)
        or source_payload != canonical_bytes(source_value) + b"\n"
    ):
        raise ValueError("owner result source binding differs from exact bytes")
    source_body = source_value
    if (
        source_value.get("artifact_kind") == "stage_owner_result"
        and source_value.get("schema_version") == 1
        and source_value.get("cycle_id") == cycle_id
        and source_value.get("target") == target
        and isinstance(source_value.get("result"), dict)
    ):
        source_body = source_value["result"]
    normalized = normalize_native_owner_result(
        target,
        source_body,
        root=root,
        cycle_id=cycle_id,
        source_ref=str(source_binding["ref"]),
        publish_auxiliary=False,
        include_auxiliary_binding=False,
    )
    if canonical_bytes(normalized) != canonical_bytes(sealed_body):
        raise ValueError(
            "owner result differs from its native source reconstruction"
        )
    if not (publish_native_artifacts or predict_native_artifacts):
        return normalized
    return normalize_native_owner_result(
        target,
        source_body,
        root=root,
        cycle_id=cycle_id,
        source_ref=str(source_binding["ref"]),
        publish_auxiliary=publish_native_artifacts,
        include_auxiliary_binding=True,
    )


__all__ = ["native_source_result"]
