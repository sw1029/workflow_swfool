"""Agent-log integrity package with explicit read and append boundaries."""

from .append import validate_store_for_append
from .contracts import (
    CONTENT_ID_RE as CONTENT_ID_RE,
    LOG_FORMAT_VERSION,
    LOG_SCHEMA_VERSION,
    LOG_STATUSES,
    MIGRATION_KIND as MIGRATION_KIND,
    RECORD_ID_RE as RECORD_ID_RE,
    SHA256_RE as SHA256_RE,
    AgentLogIntegrityError,
)
from .core import (
    _directory_projection as _directory_projection,
    _safe_relative_path as _safe_relative_path,
    canonical_record_bytes,
    content_id_for,
    ensure_log_root,
    ensure_safe_directory,
    expected_content_id,
    expected_record_id,
    safe_log_file,
    sha256_bytes,
    sha256_file,
    workspace_root,
)
from .index import (
    _parse_index as _parse_index,
    _walk_store as _walk_store,
    parse_index,
)
from .inspection import inspect_agent_log_store
from .migration import (
    _read_json_object as _read_json_object,
    _safe_migration_sidecar as _safe_migration_sidecar,
    _verify_committed_migration as _verify_committed_migration,
)

__all__ = (
    "AgentLogIntegrityError",
    "LOG_FORMAT_VERSION",
    "LOG_SCHEMA_VERSION",
    "LOG_STATUSES",
    "canonical_record_bytes",
    "content_id_for",
    "ensure_log_root",
    "ensure_safe_directory",
    "expected_content_id",
    "expected_record_id",
    "inspect_agent_log_store",
    "parse_index",
    "safe_log_file",
    "sha256_bytes",
    "sha256_file",
    "validate_store_for_append",
    "workspace_root",
)
