from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any


FORMAT_VERSION = 1
ARTIFACT_KIND = "session_governance_audit"
INDEX_ARTIFACT_KIND = "session_governance_audit_index"
MAX_PACKET_BYTES = 1024 * 1024
PARSER_VERSION = "session-audit/1"
AUTO_REPAIR_TARGET = ".task/session_audit/index.json"
TOOLS = {"codex", "claude-code"}
CAPTURE_MODES = {"conversation_projection", "structured_telemetry", "unknown"}
CAPTURE_STATUSES = {"complete", "partial", "quarantined", "failed"}
INTEGRITY_STATUSES = {"source_hash_only", "hash_chain_verified", "unverified"}
BINDING_STATUSES = {"bound", "ambiguous", "unbound"}
REPAIR_CLASSES = {"none", "derived_metadata_only", "proposal_only"}
FINDING_SEVERITIES = {"warn", "block"}
EVIDENCE_CLASSES = {
    "transcript_observation",
    "cross_source_mismatch",
    "canonical_fact",
    "absence_unknown",
}
CANONICAL_EVIDENCE_CLASSES = {"cross_source_mismatch", "canonical_fact"}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
HASH_URN_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
AUDIT_ID_RE = re.compile(r"^audit-[0-9a-f]{32}$")
CANONICAL_EXACT_PATHS = {"task.md", ".task/index.md", ".task/index.jsonl"}
CANONICAL_PATH_PREFIXES = (
    ".agent_goal/",
    ".agent_log/",
    ".contract/",
    ".issue/",
    ".schema/",
    ".validation/",
    ".task/acceptance/",
    ".task/cycle/",
    ".task/delta/",
    ".task/task_pack/",
    ".task/validation/",
    ".task/validation_scope/",
)

REQUIRED_TOP_LEVEL_FIELDS = {
    "format_version",
    "artifact_kind",
    "audit_id",
    "tool",
    "session_id",
    "source",
    "capture_mode",
    "capture_status",
    "integrity_status",
    "binding",
    "consumable",
    "not_goal_truth",
    "not_validation_evidence",
    "repair_class",
    "auto_repair_allowed",
    "findings",
    "event_counts",
    "timestamp_bounds",
    "evidence_paths",
    "parser_version",
}
ALLOWED_TOP_LEVEL_FIELDS = REQUIRED_TOP_LEVEL_FIELDS
FORBIDDEN_BODY_KEYS = {
    "body",
    "content",
    "conversation",
    "conversation_body",
    "messages",
    "prompt",
    "raw",
    "raw_body",
    "raw_body_text",
    "response",
    "thinking",
    "tool_calls",
    "tool_results",
    "transcript",
    "transcripts",
}


def _is_non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _is_string_list(value: Any) -> bool:
    return isinstance(value, list) and all(_is_non_empty_string(item) for item in value)


def _is_safe_relative_path(value: Any) -> bool:
    if not _is_non_empty_string(value) or len(value) > 1024 or "\x00" in value:
        return False
    path = Path(value)
    return (
        not path.is_absolute()
        and value == path.as_posix()
        and all(part not in {"", ".", ".."} for part in path.parts)
    )


def _canonical_packet_bytes(packet: dict[str, Any]) -> bytes:
    payload = {key: value for key, value in packet.items() if key != "audit_id"}
    text = (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    )
    return text.encode("utf-8")


def expected_audit_id(packet: dict[str, Any]) -> str:
    return "audit-" + hashlib.sha256(_canonical_packet_bytes(packet)).hexdigest()[:32]


def _is_governed_canonical_path(value: Any) -> bool:
    return _is_safe_relative_path(value) and (
        value in CANONICAL_EXACT_PATHS
        or any(str(value).startswith(prefix) for prefix in CANONICAL_PATH_PREFIXES)
    )


def expected_index_id(index: dict[str, Any]) -> str:
    payload = {key: value for key, value in index.items() if key != "index_id"}
    encoded = (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")
    return "index-" + hashlib.sha256(encoded).hexdigest()[:32]


def _add(errors: list[dict[str, Any]], code: str, path: str, detail: str) -> None:
    errors.append({"code": code, "path": path, "detail": detail})


def _forbidden_body_paths(
    value: Any, path: str = "", *, allow_message: bool = False
) -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, nested in value.items():
            normalized = str(key).strip().lower().replace("-", "_")
            child = f"{path}.{key}" if path else str(key)
            if normalized in FORBIDDEN_BODY_KEYS or (
                normalized == "message" and not allow_message
            ):
                found.append(child)
                continue
            found.extend(_forbidden_body_paths(nested, child, allow_message=False))
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            child = f"{path}.{index}" if path else str(index)
            found.extend(
                _forbidden_body_paths(nested, child, allow_message=path == "findings")
            )
    return found


def canonical_evidence_refs(finding: dict[str, Any]) -> list[dict[str, Any]]:
    evidence = finding.get("evidence")
    if not isinstance(evidence, dict):
        return []
    value = evidence.get("canonical_evidence_refs")
    return (
        [item for item in value if isinstance(item, dict)]
        if isinstance(value, list)
        else []
    )


def canonical_evidence_ref_hashes(finding: dict[str, Any]) -> list[str]:
    hashes = []
    for ref in canonical_evidence_refs(finding):
        encoded = json.dumps(
            ref, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        hashes.append(hashlib.sha256(encoded).hexdigest())
    return sorted(set(hashes))
