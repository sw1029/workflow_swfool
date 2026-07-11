#!/usr/bin/env python3
"""Create and validate body-free, non-authoritative session audit packets."""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
from typing import Any, Iterator


VERSION = 1
KIND = "session_governance_audit"
PARSER_VERSION = "session-audit/1"
MAX_BYTES = 10 * 1024 * 1024
MAX_ALLOWED_BYTES = 100 * 1024 * 1024
MAX_LINES = 10_000
TOOLS = {"codex", "claude-code"}
SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
SHA = re.compile(r"^[0-9a-f]{64}$")
AUDIT_ID = re.compile(r"^audit-[0-9a-f]{32}$")
TOP_KEYS = {
    "format_version", "artifact_kind", "parser_version", "audit_id", "tool",
    "session_id", "source", "capture_mode", "capture_status",
    "integrity_status", "binding", "consumable", "not_goal_truth",
    "not_validation_evidence", "repair_class", "auto_repair_allowed",
    "findings", "event_counts", "timestamp_bounds", "evidence_paths",
}
COUNT_KEYS = {
    "total_lines", "recognized_events", "unrecognized_events",
    "malformed_events", "blank_lines", "user_events", "assistant_events",
    "codex_events", "claude_code_events", "missing_timestamps",
    "tool_or_raw_events",
}
FINDINGS: dict[str, tuple[str, str, str]] = {
    "source_too_large": (
        "block", "transcript_observation",
        "Source exceeds the bounded inspection size.",
    ),
    "source_too_many_lines": (
        "block", "transcript_observation",
        "Source exceeds the bounded JSONL line count.",
    ),
    "invalid_utf8": (
        "block", "transcript_observation", "Source is not strict UTF-8.",
    ),
    "malformed_jsonl": (
        "block", "transcript_observation", "A source line is not valid JSON.",
    ),
    "blank_jsonl_line": (
        "warn", "transcript_observation", "A blank JSONL line was observed.",
    ),
    "non_object_event": (
        "block", "transcript_observation", "A JSONL event is not an object.",
    ),
    "unsupported_schema": (
        "block", "transcript_observation",
        "An event declares an unsupported schema version.",
    ),
    "raw_or_tool_event": (
        "block", "transcript_observation",
        "A raw, tool, reasoning, or metadata event was observed.",
    ),
    "unrecognized_event": (
        "block", "transcript_observation",
        "An event is outside the conversation projection allowlist.",
    ),
    "mixed_tool_schemas": (
        "block", "transcript_observation",
        "Events from multiple tool schemas were observed.",
    ),
    "declared_tool_mismatch": (
        "block", "transcript_observation",
        "Recognized events do not match the declared tool.",
    ),
    "missing_timestamp": (
        "warn", "absence_unknown",
        "A recognized event has no valid timestamp observation.",
    ),
    "empty_projection": (
        "warn", "absence_unknown",
        "No supported conversation event was observed.",
    ),
    "ambiguous_binding": (
        "warn", "absence_unknown",
        "Cycle and task binding must be supplied together.",
    ),
}


class AuditError(ValueError):
    pass


class DuplicateKeyError(ValueError):
    pass


def canonical(value: Any) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        + "\n"
    ).encode("utf-8")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def derived_id(prefix: str, value: Any) -> str:
    return f"{prefix}-{digest(canonical(value))[:32]}"


def root_path(raw: str | Path) -> Path:
    lexical = Path(raw).expanduser().absolute()
    if lexical.is_symlink():
        raise AuditError("repository root must not be a symlink")
    try:
        root = lexical.resolve(strict=True)
    except OSError as exc:
        raise AuditError(f"repository root is unavailable: {exc}") from exc
    if not root.is_dir():
        raise AuditError("repository root must be a directory")
    return root


def safe_file(
    root: Path, raw: str | Path, *, packet: bool = False
) -> tuple[Path, Path]:
    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        candidate = root / candidate
    lexical = candidate.absolute()
    try:
        relative = lexical.relative_to(root)
    except ValueError as exc:
        raise AuditError("path must stay inside repository root") from exc
    if ".." in relative.parts:
        raise AuditError("path traversal is not allowed")
    current = root
    for part in relative.parts:
        current /= part
        try:
            mode = current.lstat().st_mode
        except OSError as exc:
            raise AuditError(f"path is unavailable: {relative.as_posix()}") from exc
        if stat.S_ISLNK(mode):
            raise AuditError("symlink path components are not allowed")
    try:
        resolved = lexical.resolve(strict=True)
        resolved_relative = resolved.relative_to(root)
    except (OSError, ValueError) as exc:
        raise AuditError("resolved path must stay inside repository root") from exc
    if not stat.S_ISREG(resolved.lstat().st_mode):
        raise AuditError("path must name a regular file")
    audit_parent = Path(".task/session_audit")
    if packet:
        if resolved_relative.parent != audit_parent or resolved_relative.suffix != ".json":
            raise AuditError("packet must be directly under .task/session_audit")
    elif resolved_relative == audit_parent or audit_parent in resolved_relative.parents:
        raise AuditError("source must not be inside session-audit output")
    return resolved, resolved_relative


def audit_dir(root: Path) -> Path:
    current = root
    for part in (".task", "session_audit"):
        current /= part
        if current.exists() or current.is_symlink():
            mode = current.lstat().st_mode
            if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
                raise AuditError("session-audit output path is unsafe")
        else:
            current.mkdir(mode=0o700)
    return current


@contextlib.contextmanager
def locked(directory: Path, key: str) -> Iterator[None]:
    lock_dir = directory / ".locks"
    if lock_dir.exists() or lock_dir.is_symlink():
        mode = lock_dir.lstat().st_mode
        if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
            raise AuditError("session-audit lock directory is unsafe")
    else:
        lock_dir.mkdir(mode=0o700)
    lock_path = lock_dir / f"{digest(key.encode('utf-8'))}.lock"
    flags = os.O_CREAT | os.O_RDWR
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(lock_path, flags, 0o600)
    except OSError as exc:
        raise AuditError(f"cannot open audit lock: {exc}") from exc
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise AuditError("audit lock must be a regular file")
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)


def atomic_write(path: Path, data: bytes, *, immutable: bool = False) -> None:
    if path.exists() or path.is_symlink():
        mode = path.lstat().st_mode
        if stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
            raise AuditError("audit output target is unsafe")
        if immutable:
            if path.read_bytes() == data:
                return
            raise AuditError("content-addressed audit output already has conflicting bytes")
    fd, temp_name = tempfile.mkstemp(prefix=".session-audit-", dir=path.parent)
    temp = Path(temp_name)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if temp.exists():
            temp.unlink()


def read_snapshot(path: Path, limit: int) -> tuple[bytes | None, str, int]:
    before = path.stat()
    hasher = hashlib.sha256()
    chunks: list[bytes] | None = []
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
            if chunks is not None:
                if sum(map(len, chunks)) + len(chunk) <= limit:
                    chunks.append(chunk)
                else:
                    chunks = None
    after = path.stat()
    def identity(value: os.stat_result) -> tuple[int, int, int, int]:
        return value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns
    if identity(before) != identity(after):
        raise AuditError("source changed during inspection")
    return (
        b"".join(chunks) if chunks is not None else None,
        hasher.hexdigest(),
        after.st_size,
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


def make_binding(
    cycle_id: str | None, task_id: str | None
) -> tuple[dict[str, str], bool]:
    for name, value in (("cycle_id", cycle_id), ("task_id", task_id)):
        if value is not None and not SAFE_ID.fullmatch(value):
            raise AuditError(f"{name} must be a path-safe identifier")
    if cycle_id and task_id:
        return {
            "status": "bound", "cycle_id": cycle_id, "task_id": task_id
        }, False
    if cycle_id or task_id:
        return {"status": "ambiguous"}, True
    return {"status": "unbound"}, False


def build_packet(
    source: Path,
    relative: Path,
    *,
    tool: str,
    session_id: str | None,
    cycle_id: str | None,
    task_id: str | None,
    max_bytes: int,
) -> dict[str, Any]:
    if tool not in TOOLS:
        raise AuditError("tool must be codex or claude-code")
    if max_bytes != MAX_BYTES:
        raise AuditError(f"max-bytes must equal the contract limit {MAX_BYTES}")
    if session_id is not None and not SAFE_ID.fullmatch(session_id):
        raise AuditError("session-id must be a path-safe identifier")
    data, source_hash, size = read_snapshot(source, max_bytes)
    parsed = parse(data, size, tool)
    bound, ambiguous = make_binding(cycle_id, task_id)
    findings = list(parsed["findings"])
    if ambiguous:
        findings.append(make_finding("ambiguous_binding"))
    findings = dedupe_findings(findings)
    status = parsed["status"]
    consumable = status == "complete" and bound["status"] == "bound"
    repair = "none" if status == "complete" else "proposal_only"
    source_path = relative.as_posix()
    evidence = [source_path] + [
        f"sha256:{value}" for value in parsed["hashes"]
    ]
    packet: dict[str, Any] = {
        "format_version": VERSION,
        "artifact_kind": KIND,
        "parser_version": PARSER_VERSION,
        "tool": tool,
        "session_id": session_id or (
            "session-" + digest(source_path.encode("utf-8"))[:24]
        ),
        "source": {
            "path": source_path, "sha256": source_hash, "size_bytes": size,
        },
        "capture_mode": parsed["mode"],
        "capture_status": status,
        "integrity_status": "source_hash_only",
        "binding": bound,
        "consumable": consumable,
        "not_goal_truth": True,
        "not_validation_evidence": True,
        "repair_class": repair,
        "auto_repair_allowed": False,
        "findings": findings,
        "event_counts": parsed["counts"],
        "timestamp_bounds": {
            "first": parsed["times"][0], "last": parsed["times"][1],
        },
        "evidence_paths": evidence,
    }
    packet["audit_id"] = derived_id("audit", packet)
    return packet


def validate_packet(
    packet: Any, root: Path, *, verify_source: bool = True
) -> list[str]:
    errors: list[str] = []
    if not isinstance(packet, dict):
        return ["packet must be an object"]
    if set(packet) != TOP_KEYS:
        return ["packet top-level schema is not closed"]
    if packet["format_version"] != VERSION or packet["artifact_kind"] != KIND:
        errors.append("packet version or kind is invalid")
    if packet["parser_version"] != PARSER_VERSION:
        errors.append("parser version is invalid")
    if packet["tool"] not in TOOLS:
        errors.append("tool is invalid")
    if (
        not isinstance(packet["audit_id"], str)
        or not AUDIT_ID.fullmatch(packet["audit_id"])
    ):
        errors.append("audit-id is invalid")
    if (
        not isinstance(packet["session_id"], str)
        or not SAFE_ID.fullmatch(packet["session_id"])
    ):
        errors.append("session-id is invalid")
    if packet["not_goal_truth"] is not True:
        errors.append("packet must remain non-goal-truth")
    if packet["not_validation_evidence"] is not True:
        errors.append("packet must remain non-validation-evidence")
    if packet["capture_mode"] not in {
        "conversation_projection", "structured_telemetry", "unknown"
    }:
        errors.append("capture mode is invalid")
    if packet["capture_status"] not in {
        "complete", "partial", "quarantined", "failed"
    }:
        errors.append("capture status is invalid")
    if packet["integrity_status"] != "source_hash_only":
        errors.append("inspector packets require source-hash-only integrity")
    source = packet["source"]
    if (
        not isinstance(source, dict)
        or set(source) != {"path", "sha256", "size_bytes"}
        or not isinstance(source.get("path"), str)
        or not isinstance(source.get("sha256"), str)
        or not SHA.fullmatch(source["sha256"])
        or not isinstance(source.get("size_bytes"), int)
        or isinstance(source.get("size_bytes"), bool)
        or source["size_bytes"] < 0
    ):
        errors.append("source schema is invalid")
        source_relative = None
    else:
        source_relative = Path(source["path"])
        if (
            source_relative.is_absolute()
            or ".." in source_relative.parts
            or source_relative.as_posix() != source["path"]
        ):
            errors.append("source path is not canonical repository-relative")
    binding = packet["binding"]
    if not isinstance(binding, dict) or "status" not in binding:
        errors.append("binding schema is invalid")
        binding_status = None
    else:
        binding_status = binding.get("status")
        if binding_status == "bound":
            if set(binding) != {"status", "cycle_id", "task_id"}:
                errors.append("bound packet requires cycle and task identifiers")
            elif any(
                not isinstance(binding.get(key), str)
                or not SAFE_ID.fullmatch(binding[key])
                for key in ("cycle_id", "task_id")
            ):
                errors.append("bound identifiers are invalid")
        elif binding_status in {"ambiguous", "unbound"}:
            if set(binding) != {"status"}:
                errors.append("non-bound packet cannot claim identifiers")
        else:
            errors.append("binding status is invalid")
    expected_consumable = (
        packet["capture_status"] == "complete" and binding_status == "bound"
    )
    if packet["consumable"] is not expected_consumable:
        errors.append("consumable state is inconsistent")
    expected_repair = (
        "none" if packet["capture_status"] == "complete" else "proposal_only"
    )
    if packet["repair_class"] != expected_repair:
        errors.append("repair class is inconsistent")
    if packet["auto_repair_allowed"] is not False:
        errors.append("auto repair exceeds derived metadata")
    counts = packet["event_counts"]
    if (
        not isinstance(counts, dict)
        or set(counts) != COUNT_KEYS
        or any(
            not isinstance(value, int) or isinstance(value, bool) or value < 0
            for value in counts.values()
        )
    ):
        errors.append("event counts are invalid")
    bounds = packet["timestamp_bounds"]
    if (
        not isinstance(bounds, dict)
        or set(bounds) != {"first", "last"}
        or any(
            value is not None
            and (
                not isinstance(value, str)
                or normalize_timestamp(value) != value
            )
            for value in bounds.values()
        )
        or ((bounds.get("first") is None) != (bounds.get("last") is None))
    ):
        errors.append("timestamp bounds are invalid")
    findings = packet["findings"]
    if not isinstance(findings, list):
        errors.append("findings are invalid")
    else:
        for item in findings:
            if (
                not isinstance(item, dict)
                or set(item)
                != {"code", "severity", "message", "evidence_class", "resolved"}
                or item.get("code") not in FINDINGS
            ):
                errors.append("finding schema is invalid")
                continue
            spec = FINDINGS[item["code"]]
            if (
                (item["severity"], item["evidence_class"], item["message"]) != spec
                or not isinstance(item["resolved"], bool)
                or item["evidence_class"]
                not in {"transcript_observation", "absence_unknown"}
            ):
                errors.append("finding content is invalid")
    evidence = packet["evidence_paths"]
    if (
        not isinstance(evidence, list)
        or not evidence
        or not all(isinstance(value, str) and value for value in evidence)
        or source_relative is not None
        and evidence[0] != source_relative.as_posix()
        or any(
            not value.startswith("sha256:")
            or not SHA.fullmatch(value.removeprefix("sha256:"))
            for value in evidence[1:]
        )
    ):
        errors.append("evidence paths or event hashes are invalid")
    if isinstance(counts, dict):
        expected_hashes = (
            0
            if packet["capture_status"] == "failed"
            and any(
                item.get("code") in {"source_too_large", "source_too_many_lines"}
                for item in packet["findings"]
            )
            else counts.get("total_lines")
        )
        if isinstance(expected_hashes, int) and len(evidence) - 1 != expected_hashes:
            errors.append("event-hash count is inconsistent")
    body = dict(packet)
    claimed = body.pop("audit_id")
    if claimed != derived_id("audit", body):
        errors.append("audit-id does not match packet content")
    if verify_source and source_relative is not None and isinstance(source, dict):
        try:
            path, relative = safe_file(root, source_relative)
            _, actual_hash, actual_size = read_snapshot(path, MAX_ALLOWED_BYTES)
            if (
                relative != source_relative
                or actual_hash != source["sha256"]
                or actual_size != source["size_bytes"]
            ):
                errors.append("source snapshot does not match packet")
            elif (
                packet["tool"] in TOOLS
                and isinstance(packet["session_id"], str)
                and SAFE_ID.fullmatch(packet["session_id"])
                and isinstance(binding, dict)
                and binding_status in {"bound", "ambiguous", "unbound"}
            ):
                expected = build_packet(
                    path,
                    relative,
                    tool=packet["tool"],
                    session_id=packet["session_id"],
                    cycle_id=(
                        binding.get("cycle_id")
                        if binding_status == "bound"
                        else "ambiguous-binding"
                        if binding_status == "ambiguous"
                        else None
                    ),
                    task_id=(binding.get("task_id") if binding_status == "bound" else None),
                    max_bytes=MAX_BYTES,
                )
                if expected != packet:
                    errors.append("packet does not match deterministic source projection")
        except AuditError as exc:
            errors.append(f"source verification failed: {exc}")
    return errors


def inspect(
    root_raw: str | Path,
    source_raw: str | Path,
    *,
    tool: str,
    session_id: str | None = None,
    cycle_id: str | None = None,
    task_id: str | None = None,
    max_bytes: int = MAX_BYTES,
) -> tuple[dict[str, Any], Path]:
    root = root_path(root_raw)
    source, relative = safe_file(root, source_raw)
    packet = build_packet(
        source, relative, tool=tool, session_id=session_id,
        cycle_id=cycle_id, task_id=task_id, max_bytes=max_bytes,
    )
    errors = validate_packet(packet, root)
    if errors:
        raise AuditError("generated packet is invalid: " + "; ".join(errors))
    directory = audit_dir(root)
    output = directory / f"{packet['audit_id']}.json"
    with locked(directory, packet["session_id"]):
        atomic_write(output, canonical(packet), immutable=True)
    return packet, output


def load_json(path: Path) -> tuple[Any, bytes]:
    data, _, _ = read_snapshot(path, 2 * 1024 * 1024)
    if data is None:
        raise AuditError("JSON artifact exceeds size limit")
    try:
        return json.loads(
            data.decode("utf-8", errors="strict"),
            object_pairs_hook=strict_json_object,
        ), data
    except (UnicodeDecodeError, json.JSONDecodeError, DuplicateKeyError) as exc:
        raise AuditError(f"invalid strict JSON artifact: {exc}") from exc


def validate_file(
    root_raw: str | Path, packet_raw: str | Path
) -> tuple[dict[str, Any], list[str]]:
    root = root_path(root_raw)
    path, _ = safe_file(root, packet_raw, packet=True)
    packet, _ = load_json(path)
    return packet, validate_packet(packet, root)


def rebuild_index(root_raw: str | Path) -> tuple[dict[str, Any], Path]:
    root = root_path(root_raw)
    directory = audit_dir(root)
    entries: list[dict[str, Any]] = []
    evidence: list[str] = []
    with locked(directory, "index"):
        for path in sorted(directory.glob("audit-*.json")):
            if path.is_symlink() or not path.is_file():
                raise AuditError("index input must be a regular non-symlink packet")
            packet, packet_bytes = load_json(path)
            errors = validate_packet(packet, root)
            if errors:
                raise AuditError(f"invalid packet {path.name}: {'; '.join(errors)}")
            relative = path.relative_to(root).as_posix()
            entries.append({
                "audit_id": packet["audit_id"],
                "path": relative,
                "packet_sha256": digest(packet_bytes),
                "session_id": packet["session_id"],
                "tool": packet["tool"],
                "capture_status": packet["capture_status"],
                "binding_status": packet["binding"]["status"],
                "consumable": packet["consumable"],
            })
            evidence.append(relative)
        entries.sort(key=lambda item: item["audit_id"])
        evidence.sort()
        index: dict[str, Any] = {
            "format_version": VERSION,
            "artifact_kind": "session_governance_audit_index",
            "not_goal_truth": True,
            "not_validation_evidence": True,
            "repair_class": "derived_metadata_only",
            "auto_repair_allowed": True,
            "entries": entries,
            "evidence_paths": evidence,
        }
        index["index_id"] = derived_id("index", index)
        output = directory / "index.json"
        atomic_write(output, canonical(index))
    return index, output


def _load_mode_resolution_validator() -> Any:
    script = (
        Path(__file__).resolve().parents[2]
        / "orchestrate-task-cycle"
        / "scripts"
        / "mode_profile.py"
    )
    if script.is_symlink() or not script.is_file():
        raise AuditError("tracked mode-profile validator is unavailable")
    spec = importlib.util.spec_from_file_location(
        "_session_audit_mode_profile_validator",
        script,
    )
    if spec is None or spec.loader is None:
        raise AuditError("tracked mode-profile validator cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        raise AuditError("tracked mode-profile validator failed to load") from exc
    validator = getattr(module, "validate_resolution", None)
    if not callable(validator):
        raise AuditError("tracked mode-profile resolution validator is missing")
    return validator


def auto_rebuild_index(
    root_raw: str | Path,
    resolution_raw: str | Path,
) -> tuple[dict[str, Any], Path]:
    """Perform the sole unattended repair under a validated mode resolution."""

    root = root_path(root_raw)
    resolution_path, _ = safe_file(root, resolution_raw)
    resolution_value, _ = load_json(resolution_path)
    try:
        resolution = _load_mode_resolution_validator()(resolution_value)
    except (OSError, ValueError) as exc:
        raise AuditError(f"mode resolution is invalid: {exc}") from exc
    effective = resolution.get("effective_profile")
    repairs = effective.get("allowed_repairs") if isinstance(effective, dict) else None
    if (
        resolution.get("activation_source") == "default"
        or resolution.get("repair_receipt_required") is not True
        or resolution.get("allowed_effects", {}).get("derived_metadata_repair_allowed") is not True
        or repairs
        != [
            {
                "operation": "rebuild_index",
                "target": ".task/session_audit/index.json",
            }
        ]
    ):
        raise AuditError("mode resolution does not authorize exact audit-index repair")

    index_path = root / ".task" / "session_audit" / "index.json"
    before_sha256: str | None = None
    if index_path.exists() or index_path.is_symlink():
        mode = index_path.lstat().st_mode
        if stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
            raise AuditError("session-audit index target is unsafe")
        before_sha256 = digest(index_path.read_bytes())

    index, output = rebuild_index(root)
    after_sha256 = digest(output.read_bytes())
    receipt: dict[str, Any] = {
        "format_version": 1,
        "artifact_kind": "workflow_mode_repair_receipt",
        "status": "complete",
        "resolution_id": resolution["resolution_id"],
        "activation_source": resolution["activation_source"],
        "operation": "rebuild_index",
        "target": ".task/session_audit/index.json",
        "before_sha256": before_sha256,
        "after_sha256": after_sha256,
        "index_id": index["index_id"],
        "not_goal_truth": True,
        "not_validation_evidence": True,
    }
    receipt["receipt_id"] = derived_id("repair-receipt", receipt)
    return receipt, output


def cli_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    inspect_cmd = commands.add_parser("inspect")
    inspect_cmd.add_argument("--root", required=True)
    inspect_cmd.add_argument("--source", required=True)
    inspect_cmd.add_argument("--tool", required=True, choices=sorted(TOOLS))
    inspect_cmd.add_argument("--session-id")
    inspect_cmd.add_argument("--cycle-id")
    inspect_cmd.add_argument("--task-id")
    inspect_cmd.add_argument("--max-bytes", type=int, default=MAX_BYTES)
    validate_cmd = commands.add_parser("validate")
    validate_cmd.add_argument("--root", required=True)
    validate_cmd.add_argument("--packet", required=True)
    index_cmd = commands.add_parser("rebuild-index")
    index_cmd.add_argument("--root", required=True)
    auto_index_cmd = commands.add_parser("auto-rebuild-index")
    auto_index_cmd.add_argument("--root", required=True)
    auto_index_cmd.add_argument("--mode-resolution", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = cli_parser().parse_args(argv)
    try:
        if args.command == "inspect":
            packet, output = inspect(
                args.root, args.source, tool=args.tool,
                session_id=args.session_id, cycle_id=args.cycle_id,
                task_id=args.task_id, max_bytes=args.max_bytes,
            )
            result = {
                "audit_id": packet["audit_id"],
                "capture_status": packet["capture_status"],
                "consumable": packet["consumable"],
                "output": str(output),
            }
            print(json.dumps(result, sort_keys=True, separators=(",", ":")))
            return 0
        if args.command == "validate":
            packet, errors = validate_file(args.root, args.packet)
            print(json.dumps({
                "audit_id": packet.get("audit_id"),
                "valid": not errors,
                "errors": errors,
            }, sort_keys=True, separators=(",", ":")))
            return 0 if not errors else 2
        if args.command == "auto-rebuild-index":
            receipt, output = auto_rebuild_index(
                args.root,
                args.mode_resolution,
            )
            print(json.dumps({**receipt, "output": str(output)}, sort_keys=True, separators=(",", ":")))
            return 0
        index, output = rebuild_index(args.root)
        print(json.dumps({
            "index_id": index["index_id"],
            "entry_count": len(index["entries"]),
            "output": str(output),
        }, sort_keys=True, separators=(",", ":")))
        return 0
    except AuditError as exc:
        print(f"session_audit: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
