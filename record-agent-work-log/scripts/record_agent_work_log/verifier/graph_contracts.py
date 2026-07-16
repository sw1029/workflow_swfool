"""Exact document and recovery-observation graph contracts."""

RECEIPT_KEYS = frozenset(
    "after_index_sha256 after_index_size after_row_count appendability_status before_index_sha256 before_row_count body_alias_count body_mutation_count canonicalized_count committed_at duplicate_alias_count foreign_event_count historical_claims_upgraded journal_ref kind legacy_import_count migration_id missing_body_count orphan_count plan_ref plan_sha256 post_duplicate_count post_integrity_status post_legacy_count post_orphan_count prepared_at recovery_status resolution_manifest_ref resolution_manifest_sha256 schema_version source_index_ref source_index_sha256 source_index_size source_inventory_sha256 source_snapshot_ref source_snapshot_sha256 status_map_ref status_map_sha256 tool_version transaction_status unresolved_count".split()
)
PLAN_KEYS = frozenset(
    "body_mutation_count body_resolutions classification_counts expected_after_index_sha256 expected_after_index_size expected_after_row_count historical_claims_upgraded migration_id orphans root_identity rows schema_version source_index source_inventory_sha256 source_markdown_count status_map tool_version unresolved_count".split()
)
MANIFEST_KEYS = frozenset(
    "body_mutation_count classification_counts historical_claims_upgraded kind markdown_inventory markdown_resolutions migration_id orphans schema_version source_index_sha256 source_inventory_sha256 source_rows unresolved_count".split()
)
JOURNAL_KEYS = frozenset(
    "after_index_sha256 after_index_size after_row_count committed_at kind manifest_ref manifest_sha256 migration_id phase plan_ref plan_sha256 prepared_at receipt_ref receipt_sha256 recovery_status root_identity schema_version source_index_sha256 source_index_size source_inventory_sha256 source_snapshot_ref source_snapshot_sha256 staged_index_ref status_map_ref status_map_sha256 tool_version".split()
)
JOURNAL_FORWARD_KEYS = (JOURNAL_KEYS - {"committed_at"}) | {"recovered_at"}
JOURNAL_FORWARD_AFTER_COMMIT_KEYS = JOURNAL_KEYS | {"recovered_at"}


BOUNDARY_OBSERVATION_FIELDS = (
    "schema_version",
    "kind",
    "evaluation_status",
    "status",
    "migration_id",
    "journal_phase",
    "journal_sha256",
    "plan_sha256",
    "after_index_sha256",
    "after_index_size",
    "publication_state",
    "index_switched",
    "source_index_intact",
    "marker_present",
    "receipt_present",
    "forward_recovery_required",
    "exact_replay_noop_eligible",
    "read_only",
)
