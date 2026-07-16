"""Static recovery observation and publication-state contracts."""

ZERO_SHA256 = "0" * 64
OBSERVATION_FIELDS = (
    "schema_version", "kind", "evaluation_status", "status", "transaction_id",
    "journal_state", "journal_updated_at", "journal_sha256", "journal_base_sha256",
    "journal_owned_append_byte_length",
    "journal_owned_append_sha256", "plan_sha256", "index_sha256",
    "index_byte_length", "source_prefix_intact", "sealed_boundary_present",
    "anchor_present", "anchor_sha256", "receipt_present", "receipt_sha256",
    "receipt_recovery_status", "receipt_committed_at",
    "completion_marker_present", "completion_marker_sha256",
    "rendered_snapshot_present", "rendered_snapshot_sha256",
    "live_projection_present", "live_projection_sha256", "publication_state",
    "forward_recovery_required", "exact_replay_noop_eligible",
    "recovery_owned_write_set_sha256", "recovery_owned_write_path_count",
    "immutable_transaction_sha256", "immutable_transaction_path_count",
    "outside_owned_tree_sha256", "protected_anchor_aggregate_sha256", "read_only",
)
RECOVERY_JOURNAL_STATES = {
    "prepared", "partial_suffix", "sealed", "receipt_written",
    "receipt_anchored", "committed_render_pending", "committed",
}
RECEIPT_RECOVERY_STATUSES = {"not_required", "forward_completed"}
