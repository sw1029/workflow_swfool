"""Exact key contracts for independent source-row verification."""

ROW_BASE_KEYS = frozenset(
    "source_line source_row_sha256 original_status source_path source_body_sha256 classification normalized_status status_mapping_reason canonical_target_path canonical_target_source_line disposition unresolved_reason".split()
)
ROW_DUPLICATE_KEYS = frozenset(
    {"duplicate_candidate_count", "duplicate_candidate_score", "duplicate_selection_basis"}
)
ROW_BODY_CANONICAL_KEYS = frozenset(
    {"body_alias_selection_basis", "body_alias_candidate_count"}
)
ROW_BODY_ALIAS_KEYS = frozenset(
    {"alias_reason", "body_alias_candidate_score", "body_alias_selection_basis"}
)
