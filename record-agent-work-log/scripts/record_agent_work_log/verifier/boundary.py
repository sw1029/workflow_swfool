"""Read-only transaction-boundary observation."""

from __future__ import annotations

from pathlib import Path
import re
from typing import Any

from .core import (
    _canonical_json,
    _is_int,
    _load_json,
    _regular_file,
    _require,
    _root,
    _sha256,
)

from .graph_contracts import BOUNDARY_OBSERVATION_FIELDS


def _boundary_observation_sha256(value: dict[str, Any]) -> str:
    basis = {field: value.get(field) for field in BOUNDARY_OBSERVATION_FIELDS}
    return _sha256(_canonical_json(basis))

def inspect_transaction_boundary(
    root_raw: str | Path,
    migration_id: str,
    *,
    expected_status_map_raw: str | Path | None = None,
    expected_recovery_status: str | None = None,
    recovery_observation: dict[str, Any] | None = None,
    expected_recovery_observation_sha256: str | None = None,
) -> dict[str, Any]:
    """Observe crash/publication state without invoking producer recovery code."""

    root = _root(root_raw)
    _require(
        isinstance(migration_id, str)
        and re.fullmatch(r"agent-log-migration-[A-Za-z0-9._-]+", migration_id)
        is not None,
        "transaction identity is invalid",
    )
    transaction = root / ".agent_log" / "migrations" / migration_id
    _require(transaction.exists() and transaction.is_dir() and not transaction.is_symlink(), "transaction directory is unavailable")
    journal_path = _regular_file(transaction / "journal.json", "journal")
    journal, journal_payload = _load_json(journal_path, "journal")
    _require(journal.get("migration_id") == migration_id, "journal migration identity mismatch")
    _require(
        _is_int(journal.get("schema_version")) and journal["schema_version"] == 1,
        "journal schema mismatch",
    )
    phase = journal.get("phase")
    _require(phase in {"prepared", "switched", "committed"}, "journal phase is invalid")
    index_payload = _regular_file(root / ".agent_log" / "index.jsonl", "current index").read_bytes()
    switched = False
    after_size = journal.get("after_index_size")
    after_sha = journal.get("after_index_sha256")
    if _is_int(after_size) and after_size >= 0 and isinstance(after_sha, str):
        switched = len(index_payload) >= after_size and _sha256(index_payload[:after_size]) == after_sha
    source_size = journal.get("source_index_size")
    source_sha = journal.get("source_index_sha256")
    source_intact = (
        _is_int(source_size)
        and source_size >= 0
        and isinstance(source_sha, str)
        and len(index_payload) == source_size
        and _sha256(index_payload) == source_sha
    )
    marker_path = root / ".agent_log" / "migrations" / "active.json"
    marker_present = marker_path.exists() and not marker_path.is_symlink()
    receipt_path = transaction / "receipt.json"
    receipt_present = receipt_path.exists() and not receipt_path.is_symlink()
    committed_candidate = (
        phase == "committed" and switched and marker_present and receipt_present
    )
    committed = False
    if committed_candidate:
        # Keep the boundary reader independent until a committed graph must be
        # checked; this avoids an eager boundary/orchestrator import cycle.
        from .graph import verify_migration

        _require(
            expected_status_map_raw is not None,
            "committed boundary observation requires the external exact status map",
        )
        verify_migration(
            root,
            receipt_path,
            expected_status_map_raw=expected_status_map_raw,
            expected_recovery_status=expected_recovery_status,
            recovery_observation=recovery_observation,
            expected_recovery_observation_sha256=expected_recovery_observation_sha256,
        )
        committed = True
    _require(
        switched or source_intact,
        "current index matches neither the pre-switch source nor committed prefix",
    )
    _require(
        phase != "switched" or switched,
        "switched journal does not match the committed index prefix",
    )
    _require(
        phase != "committed" or committed or (switched and not marker_present),
        "committed journal lacks a complete publication boundary",
    )
    if committed:
        publication_state = "committed"
    elif switched:
        publication_state = "post_switch_incomplete"
    else:
        publication_state = "pre_switch_incomplete"
    result = {
        "schema_version": 1,
        "kind": "agent_log_migration_transaction_boundary_observation",
        "evaluation_status": "observed",
        "status": "observed",
        "migration_id": migration_id,
        "journal_phase": phase,
        "journal_sha256": _sha256(journal_payload),
        "plan_sha256": journal.get("plan_sha256"),
        "after_index_sha256": after_sha,
        "after_index_size": after_size,
        "publication_state": publication_state,
        "index_switched": switched,
        "source_index_intact": source_intact,
        "marker_present": marker_present,
        "receipt_present": receipt_present,
        "forward_recovery_required": switched and not committed,
        "exact_replay_noop_eligible": committed,
        "read_only": True,
    }
    result["observation_sha256"] = _boundary_observation_sha256(result)
    return result
