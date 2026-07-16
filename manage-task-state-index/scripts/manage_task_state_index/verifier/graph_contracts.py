"""Exact sealed-graph document shapes."""

PLAN_KEYS = {
    "schema_version", "kind", "tool_version", "migration_id", "root_identity",
    "source_prefix", "mapping_manifest", "resolution_manifest", "source_snapshot_ref",
    "plan_snapshot_ref", "classification_counts", "unclassified_count", "rows",
    "correction_events", "projection", "anchors", "effective_at",
    "transaction_directory_ref", "historical_rows_removed", "historical_rows_reordered",
    "original_row_bytes_modified", "prefix_preserved", "plan_contract_sha256",
    "correction_suffix", "seal", "expected_after_index_sha256",
    "expected_commit_boundary_byte_length", "receipt_ref", "receipt_anchor_id",
    "journal_ref", "prepare_journal_ref", "completion_marker_ref", "render_snapshot_ref",
}
PLAN_CORE_KEYS = {
    "schema_version", "kind", "tool_version", "migration_id", "root_identity",
    "source_prefix", "mapping_manifest", "resolution_manifest", "source_snapshot_ref",
    "plan_snapshot_ref", "classification_counts", "unclassified_count", "rows",
    "correction_events", "projection", "anchors", "effective_at",
    "transaction_directory_ref", "historical_rows_removed", "historical_rows_reordered",
    "original_row_bytes_modified", "prefix_preserved",
}
RECEIPT_KEYS = {
    "schema_version", "kind", "transaction_id", "tool_version", "transaction_started_at",
    "transaction_committed_at", "status", "source_prefix_ref", "source_prefix_sha256",
    "source_prefix_byte_length", "source_raw_row_count", "accepted_current_count",
    "normalized_legacy_count", "mapped_legacy_count", "quarantined_historical_count",
    "blocked_count", "mapping_manifest_ref", "mapping_manifest_sha256",
    "resolution_manifest_ref", "resolution_manifest_sha256", "plan_ref", "plan_sha256",
    "plan_contract_sha256", "correction_suffix_ref", "correction_suffix_sha256",
    "correction_suffix_byte_length", "correction_suffix_count", "correction_suffix_offset",
    "seal_id", "seal_sha256", "seal_offset", "seal_byte_length", "commit_boundary_length",
    "commit_boundary_sha256", "prefix_preserved", "historical_rows_removed",
    "historical_rows_reordered", "original_row_bytes_modified", "canonical_task",
    "canonical_pack", "superseded_task_id_digest", "superseded_pack_id_digest",
    "retracted_link_pair_digest", "active_task_count", "active_pack_count",
    "duplicate_active_alias_count", "current_broken_link_count", "before_active_task_count",
    "before_active_pack_count", "before_duplicate_active_alias_count",
    "before_current_broken_link_count", "current_active_pack_indexed",
    "current_projection_status", "projection_completeness", "current_surface_blocker_count",
    "strict_reader_status", "append_simulation_status", "audit_status", "rendered_index_ref",
    "rendered_index_sha256", "prepare_journal_ref", "prepare_journal_sha256", "journal_ref",
    "journal_sha256", "completion_marker_ref", "completion_marker_sha256", "recovery_status",
}
MANIFEST_KEYS = {
    "schema_version", "kind", "migration_id", "source_prefix_sha256",
    "source_prefix_byte_length", "source_raw_row_count", "classification_counts",
    "rows", "raw_row_bodies_included",
}
PREPARE_KEYS = {
    "schema_version", "kind", "transaction_id", "state", "prefix_sha256",
    "prefix_byte_length", "expected_boundary_sha256", "expected_boundary_byte_length",
    "plan_ref", "plan_sha256",
}
JOURNAL_KEYS = PREPARE_KEYS | {
    "journal_updated_at", "receipt_ref", "seal_sha256", "commit_boundary_sha256",
    "rendered_index_ref", "rendered_index_sha256", "recovery_status",
}
MARKER_KEYS = {
    "schema_version", "kind", "transaction_id", "state", "committed_at",
    "prepare_journal_ref", "prepare_journal_sha256", "journal_ref", "journal_sha256",
    "receipt_ref", "plan_ref", "plan_sha256", "seal_sha256", "commit_boundary_length",
    "commit_boundary_sha256", "rendered_index_ref", "rendered_index_sha256", "recovery_status",
}
SOURCE_PREFIX_KEYS = {"ref", "sha256", "byte_length", "raw_row_count"}
MAPPING_BINDING_KEYS = {"source_ref", "sha256", "schema_version", "mapping_policy_id", "snapshot_ref"}
REF_SHA_KEYS = {"ref", "sha256"}
CORRECTION_KEYS = {"ref", "sha256", "byte_length", "event_count", "offset"}
SEAL_KEYS = {"id", "event", "line_sha256", "offset", "byte_length"}
ANCHOR_KEYS = {"id", "path", "sha256"}
ROOT_IDENTITY_KEYS = {"resolved_path", "device", "inode"}
