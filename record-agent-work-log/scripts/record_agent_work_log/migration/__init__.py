"""Agent-log migration package with explicit producer boundaries."""

from .classification import (
    _body_metadata as _body_metadata,
    _body_text_for_matching as _body_text_for_matching,
    _candidate_score as _candidate_score,
    _canonical_record as _canonical_record,
    _is_current_record_valid as _is_current_record_valid,
    _load_status_map as _load_status_map,
    _safe_source_path as _safe_source_path,
    _status_mapping as _status_mapping,
)
from .cli import build_parser, main
from .contracts import (
    JOURNAL_SCHEMA_VERSION as JOURNAL_SCHEMA_VERSION,
    MANIFEST_SCHEMA_VERSION as MANIFEST_SCHEMA_VERSION,
    MARKER_SCHEMA_VERSION as MARKER_SCHEMA_VERSION,
    MIGRATION_KIND as MIGRATION_KIND,
    MISSING_STATUS_KEY as MISSING_STATUS_KEY,
    PLAN_SCHEMA_VERSION as PLAN_SCHEMA_VERSION,
    RECEIPT_SCHEMA_VERSION as RECEIPT_SCHEMA_VERSION,
    SHA256_RE as SHA256_RE,
    STATUS_MAP_SCHEMA_VERSION as STATUS_MAP_SCHEMA_VERSION,
    TOOL_VERSION as TOOL_VERSION,
    MigrationError,
)
from .inventory import (
    _inventory_document as _inventory_document,
    _split_source_rows as _split_source_rows,
    _walk_markdown as _walk_markdown,
    inspect_store,
)
from .plan_builder import _build_plan as _build_plan
from .planning import (
    _canonical_records_from_plan as _canonical_records_from_plan,
    _load_plan as _load_plan,
    _manifest_for as _manifest_for,
    write_plan,
)
from .publication import (
    _active_marker as _active_marker,
    _current_prefix_matches as _current_prefix_matches,
    _ensure_directory as _ensure_directory,
    _failpoint as _failpoint,
    _journal_payload as _journal_payload,
    _marker_for as _marker_for,
    _publish_identical as _publish_identical,
    _receipt_from_journal as _receipt_from_journal,
)
from .recovery import (
    _load_journal as _load_journal,
    _verify_hashed_ref as _verify_hashed_ref,
    recover,
    validate_receipt,
)
from .storage import (
    _canonical_json_bytes as _canonical_json_bytes,
    _index_path as _index_path,
    _read_index as _read_index,
    _relative_or_absolute as _relative_or_absolute,
    _resolve_ref as _resolve_ref,
    _root_identity as _root_identity,
    _safe_migration_path as _safe_migration_path,
    _sha256_path as _sha256_path,
    _strict_atomic_replace as _strict_atomic_replace,
    _strict_fsync_directory as _strict_fsync_directory,
    _strict_publish_new as _strict_publish_new,
    _utc_now as _utc_now,
)
from .transaction import (
    _validate_existing_idempotent as _validate_existing_idempotent,
    apply_plan,
)

__all__ = (
    "MigrationError",
    "apply_plan",
    "build_parser",
    "inspect_store",
    "main",
    "recover",
    "validate_receipt",
    "write_plan",
)
