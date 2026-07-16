"""Strict parsing and classification for body-free session projections."""

from __future__ import annotations

import datetime as dt
import json
from typing import Any

from .session_common import (
    COUNT_KEYS,
    DuplicateKeyError,
    FINDINGS,
    MAX_LINES,
    TOOLS,
    digest,
)

def normalize_timestamp(value: Any) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return (
        parsed.astimezone(dt.timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def projected_text(content: Any, allowed: set[str]) -> str | None:
    if isinstance(content, str):
        return content if content.strip() else None
    if not isinstance(content, list) or not content:
        return None
    parts: list[str] = []
    for item in content:
        if (
            not isinstance(item, dict)
            or set(item) != {"type", "text"}
            or item.get("type") not in allowed
            or not isinstance(item.get("text"), str)
        ):
            return None
        if item["text"].strip():
            parts.append(item["text"])
    return "\n".join(parts) if parts else None


def strict_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateKeyError(f"duplicate key: {key}")
        result[key] = value
    return result


def classify(event: dict[str, Any]) -> tuple[str | None, str | None, str | None]:
    schema_version = event.get("schema_version", 1)
    if isinstance(schema_version, bool) or schema_version not in (1, "1"):
        return None, None, "unsupported_schema"
    kind = event.get("type")
    if kind == "event_msg":
        if not set(event) <= {"timestamp", "type", "payload", "schema_version"}:
            return "codex", None, "raw_or_tool_event"
        payload = event.get("payload")
        if not isinstance(payload, dict):
            return "codex", None, "unrecognized_event"
        forbidden = {
            "raw", "tool_call", "tool_calls", "tool_result", "tool_results",
            "reasoning", "thinking", "system", "instructions",
        }
        if forbidden & set(event) or forbidden & set(payload):
            return "codex", None, "raw_or_tool_event"
        payload_kind = payload.get("type")
        if payload_kind not in {"user_message", "agent_message"}:
            return "codex", None, "raw_or_tool_event"
        allowed_payload = (
            {"type", "message", "images", "local_images", "text_elements"}
            if payload_kind == "user_message"
            else {"type", "message", "phase", "memory_citation"}
        )
        if not set(payload) <= allowed_payload:
            return "codex", None, "raw_or_tool_event"
        if not isinstance(payload.get("message"), str) or not payload["message"].strip():
            return "codex", None, "raw_or_tool_event"
        if payload_kind == "user_message" and payload["message"].lstrip().lower().startswith(
            ("<permissions", "<environment_context", "<user_instructions", "<skill", "<developer")
        ):
            return "codex", None, "raw_or_tool_event"
        return "codex", (
            "user" if payload_kind == "user_message" else "assistant"
        ), None
    if kind == "response_item":
        if not set(event) <= {"timestamp", "type", "payload", "schema_version"}:
            return "codex", None, "raw_or_tool_event"
        payload = event.get("payload")
        if not isinstance(payload, dict) or payload.get("role") not in {
            "user", "assistant"
        }:
            return "codex", None, "raw_or_tool_event"
        if not set(payload) <= {"type", "role", "content", "phase", "id", "status"}:
            return "codex", None, "raw_or_tool_event"
        text = projected_text(
            payload.get("content"), {"input_text", "output_text", "text"}
        )
        if text is None:
            return "codex", None, "raw_or_tool_event"
        if payload["role"] == "user" and text.lstrip().lower().startswith(
            ("<permissions", "<environment_context", "<user_instructions", "<skill", "<developer", "<system")
        ):
            return "codex", None, "raw_or_tool_event"
        return "codex", payload["role"], None
    if kind in {"user", "assistant"}:
        claude_keys = {
            "parentUuid", "isSidechain", "userType", "cwd", "sessionId",
            "version", "gitBranch", "type", "message", "uuid", "timestamp",
            "isMeta", "isVisibleInTranscript", "requestId", "agentId",
            "schema_version",
        }
        if not set(event) <= claude_keys:
            return "claude-code", None, "raw_or_tool_event"
        message = event.get("message")
        if event.get("isMeta") is True:
            return "claude-code", None, "raw_or_tool_event"
        message_keys = {
            "role", "content", "model", "id", "type", "stop_reason",
            "stop_sequence", "usage", "context_management",
        }
        if (
            not isinstance(message, dict)
            or not set(message) <= message_keys
            or message.get("role") != kind
        ):
            return "claude-code", None, "raw_or_tool_event"
        text = projected_text(message.get("content"), {"text"})
        if text is None or (
            kind == "user"
            and text.lstrip().lower().startswith(("<system", "<permissions", "<environment_context"))
        ):
            return "claude-code", None, "raw_or_tool_event"
        return "claude-code", kind, None
    if kind in {
        "session_meta", "turn_context", "reasoning", "system", "progress",
        "file-history-snapshot", "queue-operation",
    }:
        inferred = (
            "claude-code"
            if kind in {"system", "progress", "file-history-snapshot", "queue-operation"}
            else "codex"
        )
        return inferred, None, "raw_or_tool_event"
    return None, None, "unrecognized_event"


def make_finding(code: str) -> dict[str, Any]:
    severity, evidence_class, message = FINDINGS[code]
    return {
        "code": code,
        "severity": severity,
        "message": message,
        "evidence_class": evidence_class,
        "resolved": False,
    }


def dedupe_findings(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        if item["code"] not in seen:
            result.append(item)
            seen.add(item["code"])
    return result


def parse(data: bytes | None, size: int, tool: str) -> dict[str, Any]:
    counts = {key: 0 for key in COUNT_KEYS}
    findings: list[dict[str, Any]] = []
    hashes: list[str] = []
    times: list[str] = []
    if data is None:
        findings.append(make_finding("source_too_large"))
        return {
            "mode": "unknown", "status": "failed", "counts": counts,
            "findings": findings, "hashes": hashes, "times": (None, None),
        }
    byte_lines = data.splitlines()
    if len(byte_lines) > MAX_LINES:
        counts["total_lines"] = len(byte_lines)
        findings.append(make_finding("source_too_many_lines"))
        return {
            "mode": "unknown", "status": "failed", "counts": counts,
            "findings": findings, "hashes": [], "times": (None, None),
        }
    hashes = [digest(line) for line in byte_lines]
    try:
        lines = data.decode("utf-8", errors="strict").splitlines()
    except UnicodeDecodeError:
        counts["total_lines"] = len(byte_lines)
        findings.append(make_finding("invalid_utf8"))
        return {
            "mode": "unknown", "status": "failed", "counts": counts,
            "findings": findings, "hashes": hashes, "times": (None, None),
        }
    counts["total_lines"] = len(lines)
    observed_tools: set[str] = set()
    quarantine = False
    partial = False
    for line in lines:
        if not line.strip():
            counts["blank_lines"] += 1
            findings.append(make_finding("blank_jsonl_line"))
            partial = True
            continue
        try:
            event = json.loads(line, object_pairs_hook=strict_json_object)
        except (json.JSONDecodeError, DuplicateKeyError):
            counts["malformed_events"] += 1
            findings.append(make_finding("malformed_jsonl"))
            quarantine = True
            continue
        if not isinstance(event, dict):
            counts["unrecognized_events"] += 1
            findings.append(make_finding("non_object_event"))
            quarantine = True
            continue
        event_tool, role, rejection = classify(event)
        if event_tool:
            observed_tools.add(event_tool)
        if rejection:
            counts["unrecognized_events"] += 1
            if rejection == "raw_or_tool_event":
                counts["tool_or_raw_events"] += 1
            findings.append(make_finding(rejection))
            quarantine = True
            continue
        assert event_tool in TOOLS and role in {"user", "assistant"}
        counts["recognized_events"] += 1
        counts["codex_events" if event_tool == "codex" else "claude_code_events"] += 1
        counts["user_events" if role == "user" else "assistant_events"] += 1
        timestamp = normalize_timestamp(event.get("timestamp"))
        if timestamp is None:
            counts["missing_timestamps"] += 1
            findings.append(make_finding("missing_timestamp"))
            partial = True
        else:
            times.append(timestamp)
    if len(observed_tools) > 1:
        findings.append(make_finding("mixed_tool_schemas"))
        quarantine = True
    elif observed_tools and tool not in observed_tools:
        findings.append(make_finding("declared_tool_mismatch"))
        quarantine = True
    if counts["recognized_events"] == 0:
        findings.append(make_finding("empty_projection"))
        partial = True
    status = "quarantined" if quarantine else "partial" if partial else "complete"
    times.sort()
    return {
        "mode": (
            "conversation_projection"
            if counts["recognized_events"]
            else "unknown"
        ),
        "status": status,
        "counts": counts,
        "findings": dedupe_findings(findings),
        "hashes": hashes,
        "times": (
            times[0] if times else None,
            times[-1] if times else None,
        ),
    }
