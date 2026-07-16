"""Stable schemas and errors for agent-log migration."""

from __future__ import annotations

import re


TOOL_VERSION = "1.0.0"
PLAN_SCHEMA_VERSION = 1
STATUS_MAP_SCHEMA_VERSION = 1
MANIFEST_SCHEMA_VERSION = 1
RECEIPT_SCHEMA_VERSION = 1
MARKER_SCHEMA_VERSION = 1
JOURNAL_SCHEMA_VERSION = 1
MISSING_STATUS_KEY = "__MISSING_STATUS__"
MIGRATION_KIND = "agent_log_legacy_migration"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class MigrationError(ValueError):
    """Raised when a migration cannot proceed without weakening evidence."""
