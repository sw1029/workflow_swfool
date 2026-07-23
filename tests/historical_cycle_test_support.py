"""Test-only writers for exact sealed protocol-v1 cycle fixtures."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from orchestrate_task_cycle.cycle_ledger import init_cycle
from orchestrate_task_cycle.ledger.initialization_provenance import provenance_path
from orchestrate_task_cycle.ledger.support import (
    canonical_json_bytes,
    canonical_sha256,
    cycle_dir,
    initialization_path,
)


def create_sealed_legacy_v1_cycle(
    root: Path,
    cycle_id: str,
    task_id: str | None,
    reason: str,
    *,
    allow_missing_task_for_bootstrap: bool = False,
) -> dict[str, Any]:
    """Materialize historical bytes before exercising the recovery reader."""

    metadata = {
        "format_version": 1,
        "cycle_id": cycle_id,
        "initialized_at": "2000-01-01T00:00:00+00:00",
        "task_id": task_id,
        "reason": reason,
        "storage_bootstrap_only": True,
        "first_canonical_step": "context",
        "allow_missing_task_for_bootstrap": allow_missing_task_for_bootstrap,
        "initialization_provenance_version": 1,
        "stage_compiler_protocol_version": 1,
        "stage_preparation_schema_version": 1,
    }
    directory = cycle_dir(root, cycle_id)
    (directory / "packets").mkdir(parents=True, exist_ok=True)
    initialization_path(root, cycle_id).write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    provenance = {
        "schema_version": 1,
        "artifact_kind": "cycle_initialization_provenance",
        "cycle_id": cycle_id,
        "contract_class": "explicit_legacy_v1",
        "initialization_sha256": canonical_sha256(metadata),
    }
    provenance_path(root, cycle_id).write_bytes(
        canonical_json_bytes(provenance) + b"\n"
    )
    return init_cycle(
        root,
        cycle_id,
        task_id,
        reason,
        allow_missing_task_for_bootstrap=allow_missing_task_for_bootstrap,
        stage_compiler_protocol_version=1,
        stage_preparation_schema_version=1,
    )


__all__ = ["create_sealed_legacy_v1_cycle"]
