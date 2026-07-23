"""Closed contract selection for cycle initialization and recovery."""

from __future__ import annotations

from pathlib import Path

from .constants import (
    COMPILER_FIRST_WORKFLOW_CONTRACT_PROFILE,
    STAGE_COMPILER_PROTOCOL_VERSION,
    STAGE_PREPARATION_SCHEMA_VERSION,
)
from .current_projection import stage_compiler_protocol_version as _protocol_version
from .support import initialization_path, validate_cycle_id


def require_existing_v1_recovery(
    root: Path,
    cycle_id: str | None,
    requested_protocol: int | None,
) -> None:
    """Reject a new protocol-v1 contract before any terminal or cycle effect."""

    if requested_protocol != 1:
        return
    if cycle_id is None or not initialization_path(
        root, validate_cycle_id(cycle_id)
    ).is_file():
        raise ValueError(
            "new cycle initialization requires compiler-first protocol v2; "
            "protocol v1 is accepted only for an existing sealed cycle"
        )


def requested_contract_versions(
    *,
    metadata_exists: bool,
    protocol: int | None,
    preparation: int | None,
    profile: str | None,
) -> tuple[int | None, int | None, str | None]:
    requested_protocol = (
        None
        if metadata_exists and protocol is None
        else _protocol_version(
            {
                "stage_compiler_protocol_version": (
                    protocol
                    if protocol is not None
                    else STAGE_COMPILER_PROTOCOL_VERSION
                )
            }
        )
    )
    if not metadata_exists and requested_protocol == 1:
        raise ValueError(
            "new cycle initialization requires compiler-first protocol v2; "
            "protocol v1 is accepted only for an existing sealed cycle"
        )
    requested_profile = (
        None
        if metadata_exists and profile is None
        else (
            COMPILER_FIRST_WORKFLOW_CONTRACT_PROFILE
            if not metadata_exists
            and profile is None
            and requested_protocol == STAGE_COMPILER_PROTOCOL_VERSION
            else profile
        )
    )
    if requested_profile not in {
        None,
        COMPILER_FIRST_WORKFLOW_CONTRACT_PROFILE,
    }:
        raise ValueError("unsupported workflow_contract_profile")
    if (
        requested_profile is not None
        and requested_protocol != STAGE_COMPILER_PROTOCOL_VERSION
    ):
        raise ValueError("compiler-first workflow contract requires protocol v2")
    requested_preparation = preparation
    if not metadata_exists and requested_preparation is None:
        requested_preparation = (
            STAGE_PREPARATION_SCHEMA_VERSION if requested_protocol == 2 else 1
        )
    if requested_preparation is not None:
        if isinstance(requested_preparation, bool) or requested_preparation not in {
            1,
            2,
            STAGE_PREPARATION_SCHEMA_VERSION,
        }:
            raise ValueError("unsupported stage_preparation_schema_version")
        effective_protocol = requested_protocol or 1
        if effective_protocol == 1 and requested_preparation != 1:
            raise ValueError("protocol v1 requires preparation schema v1")
        if effective_protocol == 2 and requested_preparation not in {2, 3}:
            raise ValueError("protocol v2 requires preparation schema v2 or v3")
    return requested_protocol, requested_preparation, requested_profile


__all__ = ["requested_contract_versions", "require_existing_v1_recovery"]
