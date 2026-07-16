"""Fail-closed append preflight."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .contracts import AgentLogIntegrityError
from .index import _parse_index
from .inspection import inspect_agent_log_store


def validate_store_for_append(
    root: Path, payload: bytes, index_path: Path
) -> list[dict[str, Any]]:
    records = _parse_index(payload, index_path)
    inspection, _, _ = inspect_agent_log_store(root)
    if inspection["status"] in {"unsafe", "invalid"}:
        findings = inspection.get("findings", [])
        if any(item.get("code") == "agent_log_body_hash_mismatch" for item in findings):
            raise AgentLogIntegrityError("agent-log body SHA-256 mismatch")
        duplicate = next(
            (
                item
                for item in findings
                if str(item.get("code", "")).startswith("agent_log_duplicate_")
            ),
            None,
        )
        if duplicate:
            field = str(duplicate["code"]).removeprefix("agent_log_duplicate_")
            raise AgentLogIntegrityError(f"duplicate {field} in agent-log index")
        if inspection.get("orphan_count"):
            raise AgentLogIntegrityError("orphan agent-log Markdown is not indexed")
        detail = (
            findings[0].get("detail")
            if findings
            else "agent-log integrity validation failed"
        )
        raise AgentLogIntegrityError(str(detail))
    return records
