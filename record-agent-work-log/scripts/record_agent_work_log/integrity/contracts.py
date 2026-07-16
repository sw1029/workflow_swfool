"""Stable agent-log store contracts."""

from __future__ import annotations

import re


LOG_FORMAT_VERSION = 3
LOG_SCHEMA_VERSION = 2
LOG_STATUSES = ("blocked", "completed", "failed", "informational", "partial")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
CONTENT_ID_RE = re.compile(r"^log-content-[0-9a-f]{32}$")
RECORD_ID_RE = re.compile(r"^log-record-[0-9a-f]{32}$")
MIGRATION_KIND = "agent_log_legacy_migration"


class AgentLogIntegrityError(ValueError):
    """Raised when an agent-log store cannot be safely consumed or extended."""
