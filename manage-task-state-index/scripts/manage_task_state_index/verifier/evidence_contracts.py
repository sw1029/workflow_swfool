"""Exact mapping, row, and resolution contracts."""

MAPPING_KEYS = {
    "schema_version",
    "mapping_policy_id",
    "mapping_method",
    "pattern_inference_used",
    "effective_at",
    "event_mappings",
    "status_mappings",
    "type_mappings",
    "reason_codes",
    "row_resolutions",
}
MAPPING_ENTRY_KEYS = {"to", "reason_code"}
ROW_RESOLUTION_KEYS = {
    "line",
    "raw_line_sha256",
    "disposition",
    "projection_impact",
    "reason_code",
    "deterministic_identity",
    "resolution",
}
ROW_KEYS = {
    "line",
    "raw_line_sha256",
    "raw_byte_length",
    "classification",
    "reason_codes",
    "projection_impact",
    "deterministic_identity",
    "resolution",
    "normalized_event_sha256",
    "correction_event_ids",
    "correction_event_sha256s",
}
