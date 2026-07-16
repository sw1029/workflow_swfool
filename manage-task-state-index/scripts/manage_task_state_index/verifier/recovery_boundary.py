"""Read-only inspection of an interrupted migration publication boundary."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .core import (
    _canonical_json,
    _is_int,
    _is_sha256,
    _load_json,
    _regular_file,
    _require,
    _root,
    _sha256,
    _transaction_ref,
)
from .recovery_contracts import RECOVERY_JOURNAL_STATES
from .recovery_documents import (
    _anchor_observation,
    _journal_base,
    _journal_base_sha,
    _load_plan,
    _pending_journal,
    _planned_boundary,
)
from .recovery_fingerprints import (
    _immutable_transaction_sha,
    _observation_sha256,
    _optional_receipt,
    _optional_sha,
    _outside_owned_tree_sha,
    _owned_write_paths,
    _owned_write_set_sha,
    _protected_anchor_sha,
)

def inspect_transaction_boundary(
    root_raw: str | Path, transaction_id: str, *,
    expected_mapping_raw: str | Path | None = None,
    expected_recovery_status: str | None = None,
    recovery_observation: dict[str, Any] | None = None,
    expected_recovery_observation_sha256: str | None = None,
) -> dict[str, Any]:
    """Capture the exact body-free state before caller-owned forward recovery."""
    del expected_mapping_raw, expected_recovery_status, recovery_observation, expected_recovery_observation_sha256
    root = _root(root_raw)
    plan, plan_payload = _load_plan(root, transaction_id)
    journal_path = _transaction_ref(root, plan["journal_ref"], transaction_id, "journal")
    journal, journal_payload = _load_json(journal_path, "journal")
    index = _regular_file(root / ".task/index.jsonl", "current task-state index").read_bytes()
    plan_sha = _sha256(plan_payload)
    journal_state = journal.get("state")
    _require(journal_state in RECOVERY_JOURNAL_STATES, "recovery journal state is unsupported")
    committed_journal = journal_state == "committed"
    journal_base = _journal_base(plan, plan_sha, committed=committed_journal)
    _require(all(journal.get(key) == value for key, value in journal_base.items()), "recovery journal base differs from the immutable plan")
    boundary = _planned_boundary(root, plan)
    prefix_length = plan["source_prefix"]["byte_length"]
    boundary_length = len(boundary)
    prefix_intact = len(index) >= prefix_length and index[:prefix_length] == boundary[:prefix_length]
    sealed = len(index) >= boundary_length and index[:boundary_length] == boundary
    anchor_present, anchor_sha = _anchor_observation(index, boundary_length, transaction_id)
    receipt_path = _transaction_ref(
        root, plan["receipt_ref"], transaction_id, "optional recovery receipt",
        must_exist=False,
    )
    receipt_present, receipt_sha, receipt_status, receipt_committed_at = (
        _optional_receipt(receipt_path, transaction_id)
    )
    marker_present, marker_sha = _optional_sha(root / plan["completion_marker_ref"])
    render_present, render_sha = _optional_sha(root / plan["render_snapshot_ref"])
    live_present, live_sha = _optional_sha(root / ".task/index.md")
    committed_graph = (
        committed_journal and sealed and anchor_present and receipt_present
        and marker_present and render_present
    )
    live_projection_exact = live_present and live_sha == render_sha
    committed = committed_graph and live_projection_exact
    if committed:
        publication_state = "committed"
    elif committed_graph:
        publication_state = "committed_render_pending"
    elif sealed:
        publication_state = "post_seal_incomplete"
    elif prefix_intact:
        publication_state = "pre_seal_incomplete"
    else:
        publication_state = "conflicting"
    _require(publication_state != "conflicting", "current ledger matches neither source prefix nor sealed boundary")
    append_length = journal.get("appended_byte_length", 0)
    append_sha = journal.get("appended_sha256", _sha256(b""))
    _require(_is_int(append_length) and append_length >= 0 and _is_sha256(append_sha), "journal-owned append contract is invalid")
    if journal_state == "partial_suffix":
        _require(0 < append_length < boundary_length - prefix_length, "partial journal append length is invalid")
        tail = index[prefix_length:]
        _require(len(tail) == append_length and _sha256(tail) == append_sha and index == boundary[:len(index)], "partial journal does not own the exact ledger tail")
    elif journal_state == "prepared":
        _require(index == boundary[:prefix_length], "prepared recovery state contains a foreign ledger tail")
    elif journal_state in {"sealed", "receipt_written"}:
        _require(index == boundary, "pre-anchor recovery state contains a foreign ledger tail")
    journal_updated_at = journal.get("journal_updated_at")
    _require(isinstance(journal_updated_at, str) and journal_updated_at, "recovery journal update time is missing")
    if not committed_journal:
        expected_pending = _pending_journal(
            plan, plan_sha, str(journal.get("state")), journal_updated_at,
            append_length, append_sha, receipt_sha,
        )
        _require(journal_payload == _canonical_json(expected_pending), "pending recovery journal is not canonical for its phase")
    immutable_sha, immutable_count = _immutable_transaction_sha(root, plan)
    owned = _owned_write_paths(
        root, plan,
        journal_state=journal_state,
        publication_state=publication_state,
    )
    result = {
        "schema_version": 1, "kind": "task_state_migration_recovery_boundary_observation",
        "evaluation_status": "observed", "status": "observed", "transaction_id": transaction_id,
        "journal_state": journal_state, "journal_updated_at": journal_updated_at,
        "journal_sha256": _sha256(journal_payload),
        "journal_base_sha256": _journal_base_sha(plan, plan_sha, committed=committed_journal),
        "journal_owned_append_byte_length": append_length, "journal_owned_append_sha256": append_sha,
        "plan_sha256": plan_sha, "index_sha256": _sha256(index), "index_byte_length": len(index),
        "source_prefix_intact": prefix_intact, "sealed_boundary_present": sealed,
        "anchor_present": anchor_present, "anchor_sha256": anchor_sha,
        "receipt_present": receipt_present, "receipt_sha256": receipt_sha,
        "receipt_recovery_status": receipt_status,
        "receipt_committed_at": receipt_committed_at,
        "completion_marker_present": marker_present, "completion_marker_sha256": marker_sha,
        "rendered_snapshot_present": render_present, "rendered_snapshot_sha256": render_sha,
        "live_projection_present": live_present, "live_projection_sha256": live_sha,
        "publication_state": publication_state, "forward_recovery_required": not committed,
        "exact_replay_noop_eligible": committed,
        "recovery_owned_write_set_sha256": _owned_write_set_sha(owned),
        "recovery_owned_write_path_count": len(owned),
        "immutable_transaction_sha256": immutable_sha, "immutable_transaction_path_count": immutable_count,
        "outside_owned_tree_sha256": _outside_owned_tree_sha(root, set(owned)),
        "protected_anchor_aggregate_sha256": _protected_anchor_sha(root, plan), "read_only": True,
    }
    result["observation_sha256"] = _observation_sha256(result)
    return result
