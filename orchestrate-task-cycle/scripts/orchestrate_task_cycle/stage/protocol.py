"""Cycle-bound stage compiler protocol selection."""

from __future__ import annotations

from pathlib import Path

from ..cycle_ledger import read_initialization_metadata
from .contracts import SUPPORTED_PREPARATION_SCHEMA_VERSIONS


def cycle_preparation_version(
    root: Path, cycle_id: str, requested: int | None
) -> int:
    metadata = read_initialization_metadata(root, cycle_id)
    initialized = metadata.get("stage_preparation_schema_version")
    if initialized is None:
        initialized = (
            2 if metadata.get("stage_compiler_protocol_version", 1) == 2 else 1
        )
    if initialized not in SUPPORTED_PREPARATION_SCHEMA_VERSIONS:
        raise ValueError("cycle has an unsupported stage compiler protocol")
    if requested is not None and requested != initialized:
        raise ValueError(
            "stage preparation schema_version must match cycle initialization protocol"
        )
    return int(initialized)


__all__ = ["cycle_preparation_version"]
