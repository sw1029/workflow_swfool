"""Test-only ledger fixture writer for orchestration tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from orchestrate_task_cycle.cycle_ledger import (
    init_cycle,
    read_events_raw,
    write_current,
)
from orchestrate_task_cycle.ledger.event_model import (
    complete_event,
    request_fingerprint,
)
from orchestrate_task_cycle.ledger.initialization_provenance import provenance_path
from orchestrate_task_cycle.ledger.support import (
    canonical_json_bytes,
    canonical_sha256,
    current_stage_path,
    cycle_dir,
    durable_append_json,
    initialization_path,
    ledger_path,
    rel_path,
)


def append_fixture_event(
    root: Path,
    cycle_id: str,
    event: dict[str, Any],
) -> dict[str, Any]:
    """Append one synthetic predecessor; never use outside test setup."""

    previous = read_events_raw(root, cycle_id)
    semantic = dict(event)
    completed = complete_event(cycle_id, semantic)
    completed["request_fingerprint"] = request_fingerprint(cycle_id, semantic)
    completed["ledger_sequence"] = len(previous) + 1
    durable_append_json(ledger_path(root, cycle_id), completed)
    current = write_current(root, cycle_id)
    return {
        "event": completed,
        "event_duplicate": False,
        "current_stage": current,
        "ledger_path": rel_path(root, ledger_path(root, cycle_id)),
        "current_stage_path": rel_path(root, current_stage_path(root, cycle_id)),
    }


def create_sealed_legacy_v1_cycle(
    root: Path,
    cycle_id: str,
    task_id: str | None,
    reason: str,
    *,
    allow_missing_task_for_bootstrap: bool = False,
) -> dict[str, Any]:
    """Materialize a historical sealed-v1 fixture, then exercise recovery."""

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


__all__ = ["append_fixture_event", "create_sealed_legacy_v1_cycle"]
