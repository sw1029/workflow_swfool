"""Immutable provenance for cycle initialization contract selection."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .constants import COMPILER_FIRST_WORKFLOW_CONTRACT_PROFILE
from .support import (
    canonical_json_bytes,
    canonical_sha256,
    current_stage_path,
    cycle_dir,
    immutable_write_bytes,
    ledger_path,
)


PROVENANCE_SCHEMA_VERSION = 1
PROVENANCE_ARTIFACT_KIND = "cycle_initialization_provenance"
PROVENANCE_VERSION_FIELD = "initialization_provenance_version"


def provenance_path(root: Path, cycle_id: str) -> Path:
    return cycle_dir(root, cycle_id) / "initialization.provenance.json"


def _contract_class(metadata: dict[str, Any]) -> str:
    profile = metadata.get("workflow_contract_profile")
    protocol = metadata.get("stage_compiler_protocol_version")
    if (
        profile == COMPILER_FIRST_WORKFLOW_CONTRACT_PROFILE
        and protocol == 2
    ):
        return "compiler_first_v2"
    if profile is None and protocol == 1:
        return "explicit_legacy_v1"
    raise ValueError(
        "new cycle initialization requires compiler-first v2 or explicit legacy v1"
    )


def _provenance(metadata: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": PROVENANCE_SCHEMA_VERSION,
        "artifact_kind": PROVENANCE_ARTIFACT_KIND,
        "cycle_id": metadata.get("cycle_id"),
        "contract_class": _contract_class(metadata),
        "initialization_sha256": canonical_sha256(metadata),
    }


def publish_initialization_provenance(
    root: Path, cycle_id: str, metadata: dict[str, Any]
) -> dict[str, Any]:
    path = provenance_path(root, cycle_id)
    if (
        path.exists()
        or path.is_symlink()
        or current_stage_path(root, cycle_id).exists()
        or ledger_path(root, cycle_id).exists()
    ):
        raise ValueError(
            "initialization provenance may be published only during first init"
        )
    value = _provenance(metadata)
    payload = canonical_json_bytes(value) + b"\n"
    immutable_write_bytes(path, payload)
    return value


def _load_provenance(path: Path) -> dict[str, Any]:
    try:
        payload = path.read_bytes()
        value = json.loads(payload)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("cycle initialization provenance is unreadable") from exc
    if (
        not isinstance(value, dict)
        or payload != canonical_json_bytes(value) + b"\n"
    ):
        raise ValueError("cycle initialization provenance is not canonical JSON")
    return value


def verify_initialization_provenance(
    root: Path, cycle_id: str, metadata: dict[str, Any]
) -> None:
    """Verify sealed new cycles; allow only explicit unsealed historical classes."""

    path = provenance_path(root, cycle_id)
    declared = metadata.get(PROVENANCE_VERSION_FIELD)
    if not path.is_file():
        if declared is not None or metadata.get("workflow_contract_profile") is not None:
            raise ValueError(
                "declared cycle initialization provenance is missing"
            )
        if metadata.get("stage_compiler_protocol_version") not in {1, 2}:
            raise ValueError(
                "unsealed cycle initialization lacks an explicit legacy protocol"
            )
        return
    if declared != PROVENANCE_SCHEMA_VERSION:
        raise ValueError("cycle initialization provenance declaration is invalid")
    expected = _provenance(metadata)
    if _load_provenance(path) != expected:
        raise ValueError(
            "cycle initialization metadata differs from immutable provenance"
        )


__all__ = [
    "provenance_path",
    "verify_initialization_provenance",
]
