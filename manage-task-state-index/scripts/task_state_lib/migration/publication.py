"""Crash-safe migration publication and forward recovery transaction."""
from __future__ import annotations

from typing import Any

from .classification import _merge_state, _versioned
from .contracts import (
    ANCHOR_KIND,
    INDEX_FORMAT_VERSION,
    INDEX_SCHEMA_VERSION,
    MIGRATION_EVENT_FIELD,
    RECEIPT_SCHEMA_VERSION,
    TOOL_VERSION,
)
from .storage import (
    _canonical_bytes,
    _sha256,
)
def _render_markdown(events: list[dict[str, Any]], generated_at: str) -> bytes:
    state = _merge_state(events)
    groups: dict[str, list[dict[str, Any]]] = {}
    for item in state.values():
        groups.setdefault(str(item.get("type", "unknown")), []).append(item)
    lines = [
        "# Task State Index", "", f"- Generated: {generated_at}",
        "- Canonical JSONL: `.task/index.jsonl`", f"- Format version: {INDEX_FORMAT_VERSION}",
        f"- Schema version: {INDEX_SCHEMA_VERSION}", f"- Artifact count: {len(state)}", "",
    ]
    for item_type in sorted(groups):
        lines.extend([f"## {item_type}", "", "| ID | Status | Title | Path | Parent | Links | Updated |", "| --- | --- | --- | --- | --- | --- | --- |"])
        for item in sorted(groups[item_type], key=lambda row: (str(row.get("status", "")), str(row.get("id", "")))):
            links = ", ".join(f"{link.get('rel')}:{link.get('id')}" for link in item.get("links", []))
            values = [item.get("id"), item.get("status"), item.get("title"), item.get("path"), item.get("parent_id"), links, item.get("updated_at")]
            escaped = [str(value or "").replace("|", "\\|").replace("\n", " ") for value in values]
            lines.append("| " + " | ".join(escaped) + " |")
        lines.append("")
    return ("\n".join(lines).rstrip() + "\n").encode("utf-8")


def _receipt_payload(
    plan: dict[str, Any], plan_sha: str, prepare_journal_sha: str,
    journal_sha: str, completion_marker_sha: str, render_sha: str,
    recovery_status: str, committed_at: str,
) -> dict[str, Any]:
    counts = plan["classification_counts"]
    projection = plan["projection"]
    return {
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "kind": "task_state_index_migration",
        "transaction_id": plan["migration_id"],
        "tool_version": TOOL_VERSION,
        "transaction_started_at": committed_at,
        "transaction_committed_at": committed_at,
        "status": "committed",
        "source_prefix_ref": plan["source_snapshot_ref"],
        "source_prefix_sha256": plan["source_prefix"]["sha256"],
        "source_prefix_byte_length": plan["source_prefix"]["byte_length"],
        "source_raw_row_count": plan["source_prefix"]["raw_row_count"],
        "accepted_current_count": counts["accepted_current"],
        "normalized_legacy_count": counts["normalized_legacy"],
        "mapped_legacy_count": counts["mapped_legacy"],
        "quarantined_historical_count": counts["quarantined_historical"],
        "blocked_count": counts["blocked_unknown_or_future"],
        "mapping_manifest_ref": plan["mapping_manifest"]["snapshot_ref"],
        "mapping_manifest_sha256": plan["mapping_manifest"]["sha256"],
        "resolution_manifest_ref": plan["resolution_manifest"]["ref"],
        "resolution_manifest_sha256": plan["resolution_manifest"]["sha256"],
        "plan_ref": plan["plan_snapshot_ref"],
        "plan_sha256": plan_sha,
        "plan_contract_sha256": plan["plan_contract_sha256"],
        "correction_suffix_ref": plan["correction_suffix"]["ref"],
        "correction_suffix_sha256": plan["correction_suffix"]["sha256"],
        "correction_suffix_byte_length": plan["correction_suffix"]["byte_length"],
        "correction_suffix_count": plan["correction_suffix"]["event_count"],
        "correction_suffix_offset": plan["correction_suffix"]["offset"],
        "seal_id": plan["seal"]["id"],
        "seal_sha256": plan["seal"]["line_sha256"],
        "seal_offset": plan["seal"]["offset"],
        "seal_byte_length": plan["seal"]["byte_length"],
        "commit_boundary_length": plan["expected_commit_boundary_byte_length"],
        "commit_boundary_sha256": plan["expected_after_index_sha256"],
        "prefix_preserved": True,
        "historical_rows_removed": 0,
        "historical_rows_reordered": 0,
        "original_row_bytes_modified": 0,
        "canonical_task": plan["anchors"]["current_task"],
        "canonical_pack": plan["anchors"]["current_pack"],
        "superseded_task_id_digest": _sha256(_canonical_bytes(projection["superseded_task_ids"])),
        "superseded_pack_id_digest": _sha256(_canonical_bytes(projection["superseded_pack_ids"])),
        "retracted_link_pair_digest": _sha256(_canonical_bytes(projection["retracted_links"])),
        "active_task_count": projection["active_task_count"],
        "active_pack_count": projection["active_pack_count"],
        "duplicate_active_alias_count": projection["duplicate_active_alias_count"],
        "current_broken_link_count": projection["current_broken_link_count"],
        "before_active_task_count": projection["before_active_task_count"],
        "before_active_pack_count": projection["before_active_pack_count"],
        "before_duplicate_active_alias_count": projection["before_duplicate_active_alias_count"],
        "before_current_broken_link_count": projection["before_current_broken_link_count"],
        "current_active_pack_indexed": projection["current_active_pack_indexed"],
        "current_projection_status": projection["current_projection_status"],
        "projection_completeness": projection["projection_completeness"],
        "current_surface_blocker_count": projection["current_surface_blocker_count"],
        "strict_reader_status": "pass",
        "append_simulation_status": "pass",
        "audit_status": "current_projection_pass_historical_debt_preserved",
        "rendered_index_ref": plan["render_snapshot_ref"],
        "rendered_index_sha256": render_sha,
        "prepare_journal_ref": plan["prepare_journal_ref"],
        "prepare_journal_sha256": prepare_journal_sha,
        "journal_ref": plan["journal_ref"],
        "journal_sha256": journal_sha,
        "completion_marker_ref": plan["completion_marker_ref"],
        "completion_marker_sha256": completion_marker_sha,
        "recovery_status": recovery_status,
    }


def _committed_journal_payload(
    plan: dict[str, Any], prepare: dict[str, Any], committed_at: str,
    render_sha: str, recovery_status: str,
) -> dict[str, Any]:
    return {
        **prepare,
        "kind": "task_state_index_migration_journal",
        "state": "committed",
        "journal_updated_at": committed_at,
        "receipt_ref": plan["receipt_ref"],
        "seal_sha256": plan["seal"]["line_sha256"],
        "commit_boundary_sha256": plan["expected_after_index_sha256"],
        "rendered_index_ref": plan["render_snapshot_ref"],
        "rendered_index_sha256": render_sha,
        "recovery_status": recovery_status,
    }


def _completion_marker_payload(
    plan: dict[str, Any], prepare_sha: str, journal_sha: str,
    render_sha: str, recovery_status: str, committed_at: str, plan_sha: str,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": "task_state_index_migration_completion_marker",
        "transaction_id": plan["migration_id"],
        "state": "committed",
        "committed_at": committed_at,
        "prepare_journal_ref": plan["prepare_journal_ref"],
        "prepare_journal_sha256": prepare_sha,
        "journal_ref": plan["journal_ref"],
        "journal_sha256": journal_sha,
        "receipt_ref": plan["receipt_ref"],
        "plan_ref": plan["plan_snapshot_ref"],
        "plan_sha256": plan_sha,
        "seal_sha256": plan["seal"]["line_sha256"],
        "commit_boundary_length": plan["expected_commit_boundary_byte_length"],
        "commit_boundary_sha256": plan["expected_after_index_sha256"],
        "rendered_index_ref": plan["render_snapshot_ref"],
        "rendered_index_sha256": render_sha,
        "recovery_status": recovery_status,
    }
def _anchor_event(
    plan: dict[str, Any], receipt_sha: str, journal_sha: str = "0" * 64,
    completion_marker_sha: str = "0" * 64,
) -> dict[str, Any]:
    return _versioned({
        "event": "upsert", "id": plan["receipt_anchor_id"], "type": "schema_contract",
        "status": "informational", "path": plan["receipt_ref"],
        "title": "Task state legacy migration seal", "updated_at": plan["effective_at"],
        "fields": {
            MIGRATION_EVENT_FIELD: ANCHOR_KIND,
            "migration_id": plan["migration_id"],
            "receipt_ref": plan["receipt_ref"],
            "receipt_sha256": receipt_sha,
            "seal_sha256": plan["seal"]["line_sha256"],
            "commit_boundary_sha256": plan["expected_after_index_sha256"],
            "journal_ref": plan["journal_ref"],
            "journal_sha256": journal_sha,
            "completion_marker_ref": plan["completion_marker_ref"],
            "completion_marker_sha256": completion_marker_sha,
        },
    })

