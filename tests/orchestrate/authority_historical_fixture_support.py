"""Test-only fixtures for historical authority artifacts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from manage_agent_authority import artifact_store as artifact_store_module
from manage_agent_authority.artifact_store import (
    _register_compiled_grant as _production_register_grant,
)
from manage_agent_authority.canonical import sha256_file
from manage_agent_authority.source_approval import validate_for_grant
from manage_agent_authority.producer_capability import (
    _AUTHORITY_PRODUCER_CAPABILITY,
)


def snapshot_historical_source(
    root: Path, source: Path
) -> dict[str, str]:
    payload = source.read_bytes()
    digest = sha256_file(source)
    snapshot = (
        root
        / ".task/authorization/source_snapshots"
        / f"source_approval-{digest}.json"
    )
    snapshot.parent.mkdir(parents=True, exist_ok=True)
    if snapshot.exists() and snapshot.read_bytes() != payload:
        raise AssertionError("historical source fixture conflicts")
    snapshot.write_bytes(payload)
    return {"ref": snapshot.relative_to(root).as_posix(), "sha256": digest}


def register_historical_grant(
    root: Path, raw: dict[str, Any], *, parent_id: str | None = None
) -> dict[str, Any]:
    original = artifact_store_module.validate_for_grant

    def validate_historical(
        fixture_root: Path,
        approval: dict[str, Any],
        grant: dict[str, Any],
    ) -> None:
        validate_for_grant(
            fixture_root,
            approval,
            grant,
            prospective=approval["schema_version"] != 2,
        )

    artifact_store_module.validate_for_grant = validate_historical
    try:
        return _production_register_grant(
            root,
            raw,
            parent_id=parent_id,
            producer_capability=_AUTHORITY_PRODUCER_CAPABILITY,
        )
    finally:
        artifact_store_module.validate_for_grant = original


__all__ = ("register_historical_grant", "snapshot_historical_source")
