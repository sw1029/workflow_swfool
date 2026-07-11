from __future__ import annotations

import functools
import hashlib
import importlib.util
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
    return not path.is_absolute() and value == path.as_posix() and all(part not in {"", ".", ".."} for part in path.parts)


def _canonical_packet_bytes(packet: dict[str, Any]) -> bytes:
    payload = {key: value for key, value in packet.items() if key != "audit_id"}
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    return text.encode("utf-8")


def expected_audit_id(packet: dict[str, Any]) -> str:
    return "audit-" + hashlib.sha256(_canonical_packet_bytes(packet)).hexdigest()[:32]


def _is_governed_canonical_path(value: Any) -> bool:
    return _is_safe_relative_path(value) and (
        value in CANONICAL_EXACT_PATHS or any(str(value).startswith(prefix) for prefix in CANONICAL_PATH_PREFIXES)
    )


def expected_index_id(index: dict[str, Any]) -> str:
    payload = {key: value for key, value in index.items() if key != "index_id"}
    encoded = (json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    return "index-" + hashlib.sha256(encoded).hexdigest()[:32]


def _add(errors: list[dict[str, Any]], code: str, path: str, detail: str) -> None:
    errors.append({"code": code, "path": path, "detail": detail})


def _forbidden_body_paths(value: Any, path: str = "", *, allow_message: bool = False) -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, nested in value.items():
            normalized = str(key).strip().lower().replace("-", "_")
            child = f"{path}.{key}" if path else str(key)
            if normalized in FORBIDDEN_BODY_KEYS or (normalized == "message" and not allow_message):
                found.append(child)
                continue
            found.extend(_forbidden_body_paths(nested, child, allow_message=False))
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            child = f"{path}.{index}" if path else str(index)
            found.extend(_forbidden_body_paths(nested, child, allow_message=path == "findings"))
    return found


def canonical_evidence_refs(finding: dict[str, Any]) -> list[dict[str, Any]]:
    evidence = finding.get("evidence")
    if not isinstance(evidence, dict):
        return []
    value = evidence.get("canonical_evidence_refs")
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def canonical_evidence_ref_hashes(finding: dict[str, Any]) -> list[str]:
    hashes = []
    for ref in canonical_evidence_refs(finding):
        encoded = json.dumps(ref, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        hashes.append(hashlib.sha256(encoded).hexdigest())
    return sorted(set(hashes))


def validate_session_audit_packet(packet: Any) -> list[dict[str, Any]]:
    """Validate a body-free audit sidecar without treating it as workflow truth."""

    errors: list[dict[str, Any]] = []
    if not isinstance(packet, dict):
        _add(errors, "session_audit_not_object", "$", "session audit packet must be a JSON object")
        return errors

    for field in sorted(REQUIRED_TOP_LEVEL_FIELDS - set(packet)):
        _add(errors, "session_audit_required_field_missing", field, "required field is absent")
    for field in sorted(set(packet) - ALLOWED_TOP_LEVEL_FIELDS):
        _add(errors, "session_audit_unknown_field", field, "top-level field is outside the closed schema")
    for path in _forbidden_body_paths(packet):
        _add(errors, "session_audit_body_field_forbidden", path, "transcript, message, or raw-body fields are forbidden")

    if packet.get("format_version") != FORMAT_VERSION:
        _add(errors, "session_audit_format_version_invalid", "format_version", "expected format_version 1")
    if packet.get("artifact_kind") != ARTIFACT_KIND:
        _add(errors, "session_audit_artifact_kind_invalid", "artifact_kind", "unexpected artifact kind")
    if packet.get("parser_version") != PARSER_VERSION:
        _add(errors, "session_audit_parser_version_invalid", "parser_version", f"expected parser_version {PARSER_VERSION}")
    for field in ("audit_id", "session_id"):
        if not _is_non_empty_string(packet.get(field)):
            _add(errors, "session_audit_identifier_invalid", field, "identifier must be a non-empty string")
    if not isinstance(packet.get("audit_id"), str) or not AUDIT_ID_RE.fullmatch(packet["audit_id"]):
        _add(errors, "session_audit_identifier_invalid", "audit_id", "audit_id must use the content-derived format")
    if not isinstance(packet.get("session_id"), str) or not SAFE_ID_RE.fullmatch(packet["session_id"]):
        _add(errors, "session_audit_identifier_invalid", "session_id", "session_id must be a path-safe identifier")
    if packet.get("tool") not in TOOLS:
        _add(errors, "session_audit_tool_invalid", "tool", "tool is outside the closed vocabulary")
    if packet.get("capture_mode") not in CAPTURE_MODES:
        _add(errors, "session_audit_capture_mode_invalid", "capture_mode", "capture mode is outside the closed vocabulary")
    if packet.get("capture_status") not in CAPTURE_STATUSES:
        _add(errors, "session_audit_capture_status_invalid", "capture_status", "capture status is outside the closed vocabulary")
    if packet.get("integrity_status") not in INTEGRITY_STATUSES:
        _add(errors, "session_audit_integrity_status_invalid", "integrity_status", "integrity status is outside the closed vocabulary")
    if packet.get("repair_class") not in REPAIR_CLASSES:
        _add(errors, "session_audit_repair_class_invalid", "repair_class", "repair class is outside the closed vocabulary")

    if packet.get("not_goal_truth") is not True:
        _add(errors, "session_audit_goal_truth_flag_invalid", "not_goal_truth", "audit packets must assert not_goal_truth=true")
    if packet.get("not_validation_evidence") is not True:
        _add(
            errors,
            "session_audit_validation_evidence_flag_invalid",
            "not_validation_evidence",
            "audit packets must assert not_validation_evidence=true",
        )
    if not isinstance(packet.get("consumable"), bool):
        _add(errors, "session_audit_consumable_invalid", "consumable", "consumable must be boolean")
    if not isinstance(packet.get("auto_repair_allowed"), bool):
        _add(errors, "session_audit_auto_repair_flag_invalid", "auto_repair_allowed", "auto-repair flag must be boolean")
    elif packet.get("auto_repair_allowed") is not (packet.get("repair_class") == "derived_metadata_only"):
        _add(
            errors,
            "session_audit_auto_repair_scope_invalid",
            "auto_repair_allowed",
            "auto-repair is allowed if and only if repair_class is derived_metadata_only",
        )

    source = packet.get("source")
    if not isinstance(source, dict) or set(source) != {"path", "sha256", "size_bytes"}:
        _add(errors, "session_audit_source_invalid", "source", "source must contain only path, sha256, and size_bytes")
    else:
        if not _is_safe_relative_path(source.get("path")) or source.get("path") == AUTO_REPAIR_TARGET or str(source.get("path", "")).startswith(".task/session_audit/"):
            _add(errors, "session_audit_source_path_invalid", "source.path", "source path must be safe and workspace-relative")
        if not isinstance(source.get("sha256"), str) or not SHA256_RE.fullmatch(source["sha256"]):
            _add(errors, "session_audit_source_hash_invalid", "source.sha256", "source SHA-256 must be lowercase hexadecimal")
        if not isinstance(source.get("size_bytes"), int) or isinstance(source.get("size_bytes"), bool) or source["size_bytes"] < 0:
            _add(errors, "session_audit_source_size_invalid", "source.size_bytes", "source size must be a non-negative integer")

    binding = packet.get("binding")
    if not isinstance(binding, dict) or not set(binding) <= {"status", "cycle_id", "task_id"}:
        _add(errors, "session_audit_binding_invalid", "binding", "binding must use only status, cycle_id, and task_id")
    else:
        binding_status = binding.get("status")
        if binding_status not in BINDING_STATUSES:
            _add(errors, "session_audit_binding_status_invalid", "binding.status", "binding status is outside the closed vocabulary")
        identifiers = [binding.get("cycle_id"), binding.get("task_id")]
        if any(value is not None and (not isinstance(value, str) or not SAFE_ID_RE.fullmatch(value)) for value in identifiers):
            _add(errors, "session_audit_binding_identifier_invalid", "binding", "binding identifiers must be non-empty strings")
        if binding_status == "bound" and not all(_is_non_empty_string(value) for value in identifiers):
            _add(errors, "session_audit_bound_identifier_missing", "binding", "bound status requires both cycle_id and task_id")
        if binding_status in {"ambiguous", "unbound"} and any(_is_non_empty_string(value) for value in identifiers):
            _add(errors, "session_audit_unbound_identifier_claimed", "binding", "non-bound status cannot claim a cycle or task binding")

    consumable = packet.get("consumable")
    expected_consumable = (
        packet.get("capture_status") == "complete"
        and packet.get("integrity_status") != "unverified"
        and packet.get("capture_mode") != "unknown"
        and isinstance(binding, dict)
        and binding.get("status") == "bound"
    )
    if isinstance(consumable, bool) and consumable is not expected_consumable:
        _add(
            errors,
            "session_audit_consumability_inconsistent",
            "consumable",
            "consumable=true requires complete capture, known mode, and evaluated integrity",
        )
    if packet.get("capture_status") in {"quarantined", "failed"} and consumable is not False:
        _add(errors, "session_audit_quarantine_consumable", "consumable", "quarantined or failed capture must not be consumable")

    findings = packet.get("findings")
    if not isinstance(findings, list):
        _add(errors, "session_audit_findings_invalid", "findings", "findings must be a JSON list")
    else:
        for index, finding in enumerate(findings):
            path = f"findings.{index}"
            if not isinstance(finding, dict):
                _add(errors, "session_audit_finding_invalid", path, "finding must be an object")
                continue
            allowed = {"code", "severity", "message", "evidence_class", "resolved", "evidence"}
            if not set(finding) <= allowed:
                _add(errors, "session_audit_finding_unknown_field", path, "finding contains a field outside the closed schema")
            for field in ("code", "message"):
                if not _is_non_empty_string(finding.get(field)):
                    _add(errors, "session_audit_finding_field_invalid", f"{path}.{field}", "finding field must be non-empty")
            if finding.get("severity") not in FINDING_SEVERITIES:
                _add(errors, "session_audit_finding_severity_invalid", f"{path}.severity", "finding severity is outside the closed vocabulary")
            if finding.get("evidence_class") not in EVIDENCE_CLASSES:
                _add(errors, "session_audit_finding_evidence_class_invalid", f"{path}.evidence_class", "evidence class is outside the closed vocabulary")
            if "resolved" in finding and not isinstance(finding.get("resolved"), bool):
                _add(errors, "session_audit_finding_resolution_invalid", f"{path}.resolved", "resolved must be boolean when supplied")
            if (
                finding.get("severity") == "block"
                and finding.get("evidence_class") in CANONICAL_EVIDENCE_CLASSES
            ):
                refs = canonical_evidence_refs(finding)
                if not refs:
                    _add(
                        errors,
                        "session_audit_canonical_evidence_missing",
                        f"{path}.evidence",
                        "blocking cross-source or canonical findings require structured canonical evidence references",
                    )
                for ref_index, ref in enumerate(refs):
                    ref_path = f"{path}.evidence.canonical_evidence_refs.{ref_index}"
                    if set(ref) != {"path", "sha256", "cycle_id", "task_id"}:
                        _add(errors, "session_audit_canonical_evidence_ref_invalid", ref_path, "canonical reference has an invalid shape")
                        continue
                    if not _is_governed_canonical_path(ref.get("path")) or not isinstance(ref.get("sha256"), str) or not SHA256_RE.fullmatch(ref["sha256"]):
                        _add(errors, "session_audit_canonical_evidence_ref_invalid", ref_path, "canonical reference path or hash is invalid")
                    if not isinstance(binding, dict) or any(ref.get(key) != binding.get(key) for key in ("cycle_id", "task_id")):
                        _add(errors, "session_audit_canonical_evidence_binding_invalid", ref_path, "canonical reference is not bound to the packet task and cycle")

    event_counts = packet.get("event_counts")
    if not isinstance(event_counts, dict) or any(
        not isinstance(value, int) or isinstance(value, bool) or value < 0 for value in event_counts.values()
    ):
        _add(errors, "session_audit_event_counts_invalid", "event_counts", "event counts must be a string-keyed map of non-negative integers")
    timestamp_bounds = packet.get("timestamp_bounds")
    if not isinstance(timestamp_bounds, dict) or set(timestamp_bounds) != {"first", "last"}:
        _add(errors, "session_audit_timestamp_bounds_invalid", "timestamp_bounds", "timestamp bounds must contain only first and last")
    elif any(value is not None and not _is_non_empty_string(value) for value in timestamp_bounds.values()):
        _add(errors, "session_audit_timestamp_value_invalid", "timestamp_bounds", "timestamp values must be strings or null")
    evidence_paths = packet.get("evidence_paths")
    if not _is_string_list(evidence_paths) or not evidence_paths:
        _add(errors, "session_audit_evidence_paths_invalid", "evidence_paths", "evidence_paths must be a non-empty string list")
    elif not isinstance(source, dict) or evidence_paths[0] != source.get("path") or not _is_safe_relative_path(evidence_paths[0]):
        _add(errors, "session_audit_evidence_source_mismatch", "evidence_paths.0", "first evidence path must equal the safe source path")
    elif any(not HASH_URN_RE.fullmatch(item) for item in evidence_paths[1:]):
        _add(errors, "session_audit_evidence_hash_urn_invalid", "evidence_paths", "remaining evidence entries must be SHA-256 URNs")
    if isinstance(packet.get("audit_id"), str) and packet["audit_id"] != expected_audit_id(packet):
        _add(errors, "session_audit_id_content_mismatch", "audit_id", "audit_id does not match canonical packet content")
    return errors


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_packet_source(root: Path, packet: dict[str, Any]) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    source = packet.get("source")
    if not isinstance(source, dict) or not _is_safe_relative_path(source.get("path")):
        return [{"code": "session_audit_source_path_invalid", "path": "source.path", "detail": "source path is invalid"}]
    relative = Path(source["path"])
    path = root / relative
    current = root
    try:
        for part in relative.parts:
            current /= part
            if current.is_symlink():
                raise ValueError("symlink path component")
        resolved = path.resolve(strict=True)
        resolved.relative_to(root.resolve())
        if not resolved.is_file():
            raise ValueError("source is not a regular file")
    except (OSError, ValueError):
        _add(errors, "session_audit_source_unavailable", "source.path", "source is unavailable, unsafe, or outside the workspace")
        return errors
    try:
        stat = resolved.stat()
        actual_hash = sha256_file(resolved)
    except OSError:
        _add(errors, "session_audit_source_unavailable", "source.path", "source could not be read for verification")
        return errors
    if stat.st_size != source.get("size_bytes") or actual_hash != source.get("sha256"):
        _add(errors, "session_audit_source_snapshot_mismatch", "source", "source size or SHA-256 no longer matches the packet")
    return errors


@functools.lru_cache(maxsize=1)
def _bundled_projection_validator() -> Any:
    """Load the tracked producer validator that owns projection semantics."""

    script = (
        Path(__file__).resolve().parents[3]
        / "audit-session-governance"
        / "scripts"
        / "session_audit.py"
    )
    if script.is_symlink() or not script.is_file():
        raise RuntimeError("bundled session-audit validator is unavailable")
    spec = importlib.util.spec_from_file_location(
        "_bundled_session_audit_projection_validator", script
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("bundled session-audit validator cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    validator = getattr(module, "validate_packet", None)
    if not callable(validator):
        raise RuntimeError("bundled session-audit validator has no validate_packet")
    return validator


def verify_deterministic_source_projection(
    root: Path, packet: dict[str, Any]
) -> list[dict[str, Any]]:
    """Require exact parity with the bundled body-free source projection."""

    try:
        validator = _bundled_projection_validator()
        producer_errors = validator(packet, root, verify_source=True)
    except Exception:  # Fail closed if the tracked validator cannot execute.
        return [
            {
                "code": "session_audit_source_projection_validator_unavailable",
                "path": "source",
                "detail": "bundled deterministic source-projection validation was unavailable",
            }
        ]
    if producer_errors:
        return [
            {
                "code": "session_audit_source_projection_mismatch",
                "path": "source",
                "detail": "packet does not match the bundled deterministic source projection",
            }
        ]
    return []


def verify_canonical_evidence_refs(root: Path, packet: dict[str, Any]) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    source = packet.get("source") if isinstance(packet.get("source"), dict) else {}
    source_path = source.get("path")
    for finding_index, finding in enumerate(packet.get("findings", [])):
        if not isinstance(finding, dict):
            continue
        if finding.get("severity") != "block" or finding.get("evidence_class") not in CANONICAL_EVIDENCE_CLASSES:
            continue
        for ref_index, ref in enumerate(canonical_evidence_refs(finding)):
            path_value = ref.get("path")
            path_label = f"findings.{finding_index}.evidence.canonical_evidence_refs.{ref_index}"
            if not _is_governed_canonical_path(path_value) or path_value == source_path:
                _add(errors, "session_audit_canonical_ref_outside_governed_artifacts", path_label, "canonical reference is outside the governed artifact allowlist")
                continue
            relative = Path(path_value)
            path = root / relative
            current = root
            try:
                for part in relative.parts:
                    current /= part
                    if current.is_symlink():
                        raise ValueError("symlink path component")
                resolved = path.resolve(strict=True)
                resolved.relative_to(root.resolve())
                if not resolved.is_file() or sha256_file(resolved) != ref.get("sha256"):
                    raise ValueError("reference missing or hash mismatch")
            except (OSError, ValueError):
                _add(errors, "session_audit_canonical_ref_verification_failed", path_label, "canonical reference could not be independently verified")
    return errors


def _safe_file_metadata(root: Path, path: Path) -> dict[str, Any]:
    stat = path.stat()
    return {
        "path": path.relative_to(root).as_posix(),
        "sha256": sha256_file(path),
        "size_bytes": stat.st_size,
    }


def project_valid_packet(packet: dict[str, Any], file_metadata: dict[str, Any]) -> dict[str, Any]:
    binding = packet.get("binding") if isinstance(packet.get("binding"), dict) else {}
    source = packet.get("source") if isinstance(packet.get("source"), dict) else {}
    findings = []
    for finding in packet.get("findings", []):
        if not isinstance(finding, dict):
            continue
        findings.append(
            {
                "code": finding.get("code"),
                "severity": finding.get("severity"),
                "evidence_class": finding.get("evidence_class"),
                "resolved": finding.get("resolved") is True,
                "canonical_evidence_ref_hashes": canonical_evidence_ref_hashes(finding),
            }
        )
    return {
        "contract_status": "valid",
        "file": file_metadata,
        "format_version": packet.get("format_version"),
        "artifact_kind": packet.get("artifact_kind"),
        "parser_version": packet.get("parser_version"),
        "audit_id": packet.get("audit_id"),
        "tool": packet.get("tool"),
        "session_id": packet.get("session_id"),
        "source_sha256": source.get("sha256"),
        "source_size_bytes": source.get("size_bytes"),
        "capture_mode": packet.get("capture_mode"),
        "capture_status": packet.get("capture_status"),
        "integrity_status": packet.get("integrity_status"),
        "binding": {
            key: binding[key]
            for key in ("status", "cycle_id", "task_id")
            if key in binding
        },
        "source_projection_verified": True,
        "canonical_refs_verified": True,
        "consumable": packet.get("consumable"),
        "not_goal_truth": packet.get("not_goal_truth"),
        "not_validation_evidence": packet.get("not_validation_evidence"),
        "repair_class": packet.get("repair_class"),
        "auto_repair_allowed": packet.get("auto_repair_allowed"),
        "auto_repair_target": AUTO_REPAIR_TARGET if packet.get("auto_repair_allowed") is True else None,
        "event_counts": packet.get("event_counts"),
        "timestamp_bounds": packet.get("timestamp_bounds"),
        "evidence_path_hashes": [
            hashlib.sha256(str(value).encode("utf-8")).hexdigest()
            for value in packet.get("evidence_paths", [])
        ],
        "findings": findings,
    }


def _invalid_projection(
    file_metadata: dict[str, Any],
    status: str,
    errors: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "contract_status": status,
        "file": file_metadata,
        "error_codes": sorted({str(error.get("code")) for error in errors}),
    }


def validate_session_audit_index(root: Path, value: Any) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    required = {
        "format_version",
        "artifact_kind",
        "not_goal_truth",
        "not_validation_evidence",
        "repair_class",
        "auto_repair_allowed",
        "entries",
        "evidence_paths",
        "index_id",
    }
    if not isinstance(value, dict) or set(value) != required:
        return [{"code": "session_audit_index_schema_invalid", "path": "index.json", "detail": "index schema is not closed"}]
    if value.get("format_version") != FORMAT_VERSION or value.get("artifact_kind") != INDEX_ARTIFACT_KIND:
        _add(errors, "session_audit_index_identity_invalid", "index.json", "index version or kind is invalid")
    if value.get("not_goal_truth") is not True or value.get("not_validation_evidence") is not True:
        _add(errors, "session_audit_index_truth_flags_invalid", "index.json", "index truth flags are invalid")
    if value.get("repair_class") != "derived_metadata_only" or value.get("auto_repair_allowed") is not True:
        _add(errors, "session_audit_index_repair_scope_invalid", "index.json", "only the derived index is auto-repairable")
    if value.get("index_id") != expected_index_id(value):
        _add(errors, "session_audit_index_id_mismatch", "index.json", "index_id does not match canonical index content")
    entries = value.get("entries")
    evidence_paths = value.get("evidence_paths")
    if not isinstance(entries, list) or not isinstance(evidence_paths, list):
        _add(errors, "session_audit_index_entries_invalid", "index.json", "index entries and evidence_paths must be lists")
        return errors
    expected_paths: list[str] = []
    seen: set[str] = set()
    for index, entry in enumerate(entries):
        path = f"entries.{index}"
        expected_fields = {
            "audit_id",
            "path",
            "packet_sha256",
            "session_id",
            "tool",
            "capture_status",
            "binding_status",
            "consumable",
        }
        if not isinstance(entry, dict) or set(entry) != expected_fields:
            _add(errors, "session_audit_index_entry_invalid", path, "index entry schema is invalid")
            continue
        audit_id = entry.get("audit_id")
        expected_path = f".task/session_audit/{audit_id}.json"
        if not isinstance(audit_id, str) or not AUDIT_ID_RE.fullmatch(audit_id) or audit_id in seen:
            _add(errors, "session_audit_index_entry_id_invalid", path, "index audit_id is invalid or duplicated")
        seen.add(str(audit_id))
        if entry.get("path") != expected_path or not _is_safe_relative_path(entry.get("path")):
            _add(errors, "session_audit_index_entry_path_invalid", path, "index packet path is invalid")
        if not isinstance(entry.get("packet_sha256"), str) or not SHA256_RE.fullmatch(entry["packet_sha256"]):
            _add(errors, "session_audit_index_entry_hash_invalid", path, "index packet hash is invalid")
        if not isinstance(entry.get("session_id"), str) or not SAFE_ID_RE.fullmatch(entry["session_id"]):
            _add(errors, "session_audit_index_entry_session_invalid", path, "index session_id is invalid")
        if entry.get("tool") not in TOOLS or entry.get("capture_status") not in CAPTURE_STATUSES or entry.get("binding_status") not in BINDING_STATUSES:
            _add(errors, "session_audit_index_entry_vocabulary_invalid", path, "index entry vocabulary is invalid")
        if not isinstance(entry.get("consumable"), bool):
            _add(errors, "session_audit_index_entry_consumable_invalid", path, "index consumable flag is invalid")
        packet_path = root / expected_path
        try:
            if packet_path.is_symlink() or not packet_path.is_file() or sha256_file(packet_path) != entry.get("packet_sha256"):
                raise OSError("packet unavailable or hash mismatch")
        except OSError:
            _add(errors, "session_audit_index_entry_packet_mismatch", path, "index entry does not match its packet file")
        expected_paths.append(expected_path)
    if entries != sorted(entries, key=lambda item: str(item.get("audit_id")) if isinstance(item, dict) else ""):
        _add(errors, "session_audit_index_order_invalid", "entries", "index entries must be audit_id sorted")
    if evidence_paths != sorted(expected_paths):
        _add(errors, "session_audit_index_evidence_invalid", "evidence_paths", "index evidence paths must exactly match indexed packets")
    return errors


def _index_metadata(root: Path, directory: Path) -> dict[str, Any]:
    path = directory / "index.json"
    if path.is_symlink() or not path.is_file():
        return {}
    metadata = _safe_file_metadata(root, path)
    if path.stat().st_size > MAX_PACKET_BYTES:
        return {**metadata, "contract_status": "invalid", "error_codes": ["session_audit_index_oversize"]}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {**metadata, "contract_status": "malformed", "error_codes": ["session_audit_index_malformed"]}
    errors = validate_session_audit_index(root, value)
    if errors:
        return {
            **metadata,
            "contract_status": "invalid",
            "error_codes": sorted({str(error.get("code")) for error in errors}),
        }
    entries = value.get("entries") if isinstance(value.get("entries"), list) else []
    return {
        **metadata,
        "contract_status": "valid",
        "index_id": value.get("index_id"),
        "entry_count": len(entries),
        "repair_class": "derived_metadata_only",
        "auto_repair_allowed": True,
        "auto_repair_target": AUTO_REPAIR_TARGET,
        "not_goal_truth": True,
        "not_validation_evidence": True,
        "evidence_path_hashes": [
            hashlib.sha256(str(path_value).encode("utf-8")).hexdigest()
            for path_value in value.get("evidence_paths", [])
        ],
    }


def collect_session_audit_directory(root: Path, max_files: int) -> dict[str, Any]:
    """Collect only validated packet projections and body-free invalid-file diagnostics."""

    root = root.resolve()
    directory = root / ".task" / "session_audit"
    base: dict[str, Any] = {
        "artifact_kind": "session_audit_collection_projection",
        "not_goal_truth": True,
        "not_validation_evidence": True,
        "directory": {"path": ".task/session_audit", "exists": directory.exists()},
        "packet_count": 0,
        "total_packet_count": 0,
        "scanned_packet_count": 0,
        "truncated_count": 0,
        "truncated": False,
        "valid_count": 0,
        "invalid_count": 0,
        "malformed_count": 0,
        "packets": [],
        "invalid_packets": [],
        "index": {},
    }
    if not directory.exists():
        return base
    if directory.is_symlink() or not directory.is_dir():
        base["directory"]["status"] = "unsafe_or_not_directory"
        base["packet_count"] = 1
        base["total_packet_count"] = 1
        base["scanned_packet_count"] = 1
        base["invalid_count"] = 1
        base["invalid_packets"] = [{"contract_status": "unsafe", "file": {"path": ".task/session_audit"}, "error_codes": ["session_audit_directory_unsafe"]}]
        return base
    try:
        directory.resolve().relative_to(root)
    except ValueError:
        base["directory"]["status"] = "outside_workspace"
        base["packet_count"] = 1
        base["total_packet_count"] = 1
        base["scanned_packet_count"] = 1
        base["invalid_count"] = 1
        base["invalid_packets"] = [{"contract_status": "unsafe", "file": {"path": ".task/session_audit"}, "error_codes": ["session_audit_directory_outside_workspace"]}]
        return base

    candidates = [
        path
        for path in directory.glob("*.json")
        if path.name != "index.json"
    ]
    def safe_mtime(path: Path) -> float:
        if path.is_symlink():
            return 0
        try:
            return path.stat().st_mtime
        except OSError:
            return 0

    ordered = sorted(candidates, key=safe_mtime, reverse=True)
    selected = ordered[: max(0, max_files)]
    base["packet_count"] = len(ordered)
    base["total_packet_count"] = len(ordered)
    base["scanned_packet_count"] = len(selected)
    base["truncated_count"] = len(ordered) - len(selected)
    base["truncated"] = bool(base["truncated_count"])
    for path in selected:
        relative = {"path": path.relative_to(root).as_posix()}
        if path.is_symlink() or not path.is_file():
            base["invalid_packets"].append(
                _invalid_projection(relative, "unsafe", [{"code": "session_audit_packet_file_unsafe"}])
            )
            continue
        try:
            path.resolve().relative_to(directory.resolve())
            metadata = _safe_file_metadata(root, path)
            if path.stat().st_size > MAX_PACKET_BYTES:
                base["invalid_packets"].append(
                    _invalid_projection(metadata, "invalid", [{"code": "session_audit_packet_oversize"}])
                )
                continue
            packet = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            metadata = relative
            try:
                metadata = _safe_file_metadata(root, path)
            except OSError:
                pass
            base["invalid_packets"].append(
                _invalid_projection(metadata, "malformed", [{"code": "session_audit_packet_malformed"}])
            )
            continue
        errors = validate_session_audit_packet(packet)
        if isinstance(packet, dict) and packet.get("audit_id") and path.name != f"{packet['audit_id']}.json":
            _add(errors, "session_audit_filename_mismatch", "audit_id", "packet filename must equal its content-derived audit_id")
        if not errors and isinstance(packet, dict):
            errors.extend(verify_packet_source(root, packet))
        if not errors and isinstance(packet, dict):
            errors.extend(verify_deterministic_source_projection(root, packet))
        if not errors and isinstance(packet, dict):
            errors.extend(verify_canonical_evidence_refs(root, packet))
        if errors:
            base["invalid_packets"].append(_invalid_projection(metadata, "invalid", errors))
        else:
            base["packets"].append(project_valid_packet(packet, metadata))
    base["valid_count"] = len(base["packets"])
    base["invalid_count"] = len(base["invalid_packets"])
    base["malformed_count"] = sum(
        1 for packet in base["invalid_packets"] if packet.get("contract_status") == "malformed"
    )
    base["index"] = _index_metadata(root, directory)
    return base


def sanitize_collection_summary(value: Any, max_packets: int | None = None) -> dict[str, Any] | None:
    """Re-project a collector summary before embedding it in a subskill packet."""

    if not isinstance(value, dict) or value.get("artifact_kind") != "session_audit_collection_projection":
        return None
    result: dict[str, Any] = {
        "artifact_kind": "session_audit_collection_projection",
        "not_goal_truth": value.get("not_goal_truth") is True,
        "not_validation_evidence": value.get("not_validation_evidence") is True,
        "packet_count": value.get("packet_count") if isinstance(value.get("packet_count"), int) else 0,
        "total_packet_count": value.get("total_packet_count") if isinstance(value.get("total_packet_count"), int) else 0,
        "scanned_packet_count": 0,
        "truncated_count": value.get("truncated_count") if isinstance(value.get("truncated_count"), int) else 0,
        "truncated": value.get("truncated") is True,
        "valid_count": 0,
        "invalid_count": 0,
        "malformed_count": 0,
        "packets": [],
        "invalid_packets": [],
        "index": {},
    }
    packet_limit = max_packets if max_packets is not None else 10_000
    valid_source = value.get("packets", []) if isinstance(value.get("packets"), list) else []
    invalid_source = value.get("invalid_packets", []) if isinstance(value.get("invalid_packets"), list) else []
    selected_valid = valid_source[:packet_limit]
    selected_invalid = invalid_source[: max(0, packet_limit - len(selected_valid))]
    omitted = len(valid_source) + len(invalid_source) - len(selected_valid) - len(selected_invalid)
    result["truncated_count"] += omitted
    result["truncated"] = bool(result["truncated_count"])
    for packet in selected_valid:
        if not isinstance(packet, dict):
            continue
        projected = {
            key: packet.get(key)
            for key in (
                "contract_status",
                "format_version",
                "artifact_kind",
                "parser_version",
                "audit_id",
                "tool",
                "session_id",
                "source_sha256",
                "source_size_bytes",
                "capture_mode",
                "capture_status",
                "integrity_status",
                "source_projection_verified",
                "canonical_refs_verified",
                "consumable",
                "not_goal_truth",
                "not_validation_evidence",
                "repair_class",
                "auto_repair_allowed",
                "auto_repair_target",
            )
        }
        file_metadata = packet.get("file")
        projected["file"] = (
            {key: file_metadata.get(key) for key in ("path", "sha256", "size_bytes") if key in file_metadata}
            if isinstance(file_metadata, dict)
            else {}
        )
        binding = packet.get("binding")
        projected["binding"] = (
            {key: binding.get(key) for key in ("status", "cycle_id", "task_id") if key in binding}
            if isinstance(binding, dict)
            else {}
        )
        event_counts = packet.get("event_counts")
        projected["event_counts"] = (
            {
                str(key): count
                for key, count in event_counts.items()
                if isinstance(count, int) and not isinstance(count, bool) and count >= 0
            }
            if isinstance(event_counts, dict)
            else {}
        )
        timestamp_bounds = packet.get("timestamp_bounds")
        projected["timestamp_bounds"] = (
            {key: timestamp_bounds.get(key) for key in ("first", "last") if key in timestamp_bounds}
            if isinstance(timestamp_bounds, dict)
            else {}
        )
        evidence_path_hashes = packet.get("evidence_path_hashes")
        projected["evidence_path_hashes"] = (
            [str(value) for value in evidence_path_hashes if isinstance(value, str) and SHA256_RE.fullmatch(value)]
            if isinstance(evidence_path_hashes, list)
            else []
        )
        projected["findings"] = [
            {
                key: finding.get(key)
                for key in ("code", "severity", "evidence_class", "resolved", "canonical_evidence_ref_hashes")
            }
            for finding in packet.get("findings", [])
            if isinstance(finding, dict)
        ]
        result["packets"].append(projected)
    for packet in selected_invalid:
        if isinstance(packet, dict):
            file_metadata = packet.get("file")
            result["invalid_packets"].append(
                {
                    "contract_status": packet.get("contract_status"),
                    "file": (
                        {key: file_metadata.get(key) for key in ("path", "sha256", "size_bytes") if key in file_metadata}
                        if isinstance(file_metadata, dict)
                        else {}
                    ),
                    "error_codes": [
                        str(code)
                        for code in packet.get("error_codes", [])
                        if isinstance(code, str) and code.strip()
                    ]
                    if isinstance(packet.get("error_codes"), list)
                    else [],
                }
            )
    result["valid_count"] = len(result["packets"])
    result["invalid_count"] = len(result["invalid_packets"])
    result["malformed_count"] = sum(
        1 for packet in result["invalid_packets"] if packet.get("contract_status") == "malformed"
    )
    result["scanned_packet_count"] = result["valid_count"] + result["invalid_count"]
    index = value.get("index")
    if isinstance(index, dict):
        result["index"] = {
            key: index.get(key)
            for key in (
                "path",
                "sha256",
                "size_bytes",
                "contract_status",
                "error_codes",
                "index_id",
                "entry_count",
                "repair_class",
                "auto_repair_allowed",
                "auto_repair_target",
                "not_goal_truth",
                "not_validation_evidence",
                "evidence_path_hashes",
            )
            if key in index
        }
    return result


PROJECTION_PACKET_FIELDS = {
    "contract_status",
    "file",
    "format_version",
    "artifact_kind",
    "parser_version",
    "audit_id",
    "tool",
    "session_id",
    "source_sha256",
    "source_size_bytes",
    "capture_mode",
    "capture_status",
    "integrity_status",
    "binding",
    "source_projection_verified",
    "canonical_refs_verified",
    "consumable",
    "not_goal_truth",
    "not_validation_evidence",
    "repair_class",
    "auto_repair_allowed",
    "auto_repair_target",
    "event_counts",
    "timestamp_bounds",
    "evidence_path_hashes",
    "findings",
}


def validate_collection_projection(value: Any) -> list[dict[str, Any]]:
    """Validate the body-free projection emitted by the local collectors."""

    errors: list[dict[str, Any]] = []
    if not isinstance(value, dict) or value.get("artifact_kind") != "session_audit_collection_projection":
        _add(errors, "session_audit_projection_invalid", "$", "collection projection has an invalid envelope")
        return errors
    if value.get("not_goal_truth") is not True:
        _add(errors, "session_audit_goal_truth_flag_invalid", "not_goal_truth", "collection must remain non-goal-truth")
    if value.get("not_validation_evidence") is not True:
        _add(errors, "session_audit_validation_evidence_flag_invalid", "not_validation_evidence", "collection must remain non-validation evidence")
    allowed = {
        "artifact_kind",
        "not_goal_truth",
        "not_validation_evidence",
        "directory",
        "packet_count",
        "total_packet_count",
        "scanned_packet_count",
        "truncated_count",
        "truncated",
        "valid_count",
        "invalid_count",
        "malformed_count",
        "packets",
        "invalid_packets",
        "index",
    }
    for field in sorted(set(value) - allowed):
        _add(errors, "session_audit_projection_unknown_field", field, "collection contains a field outside the closed projection schema")
    for path in _forbidden_body_paths(value):
        _add(errors, "session_audit_body_field_forbidden", path, "projection contains a forbidden body field")
    packets = value.get("packets")
    invalid_packets = value.get("invalid_packets")
    if not isinstance(packets, list) or not isinstance(invalid_packets, list):
        _add(errors, "session_audit_projection_lists_invalid", "$", "packets and invalid_packets must be lists")
        return errors
    for count_field in (
        "packet_count",
        "total_packet_count",
        "scanned_packet_count",
        "truncated_count",
        "valid_count",
        "invalid_count",
        "malformed_count",
    ):
        count = value.get(count_field)
        if not isinstance(count, int) or isinstance(count, bool) or count < 0:
            _add(errors, "session_audit_projection_count_invalid", count_field, "projection count must be non-negative")
    if not isinstance(value.get("truncated"), bool):
        _add(errors, "session_audit_projection_truncated_invalid", "truncated", "truncated must be boolean")
    if value.get("valid_count") != len(packets) or value.get("invalid_count") != len(invalid_packets):
        _add(errors, "session_audit_projection_count_mismatch", "$", "projection counts do not match packet lists")
    if value.get("scanned_packet_count") != len(packets) + len(invalid_packets):
        _add(errors, "session_audit_projection_scan_count_mismatch", "$", "scanned count does not match projected packets")
    count_values = [value.get(field) for field in ("packet_count", "total_packet_count", "scanned_packet_count", "truncated_count")]
    if all(isinstance(count, int) and not isinstance(count, bool) for count in count_values):
        if count_values[0] != count_values[1] or count_values[1] != count_values[2] + count_values[3]:
            _add(errors, "session_audit_projection_total_count_mismatch", "$", "total, scanned, and truncated counts are inconsistent")
    if value.get("truncated") is not bool(value.get("truncated_count")):
        _add(errors, "session_audit_projection_truncation_mismatch", "$", "truncation flag and count are inconsistent")
    for index, packet in enumerate(packets):
        path = f"packets.{index}"
        if not isinstance(packet, dict) or set(packet) != PROJECTION_PACKET_FIELDS:
            _add(errors, "session_audit_projection_packet_shape_invalid", path, "packet projection has a missing or unknown field")
            continue
        if packet.get("contract_status") != "valid":
            _add(errors, "session_audit_projection_packet_status_invalid", f"{path}.contract_status", "projected packets must be validated")
        if packet.get("format_version") != FORMAT_VERSION or packet.get("artifact_kind") != ARTIFACT_KIND:
            _add(errors, "session_audit_projection_packet_identity_invalid", path, "projected packet identity is invalid")
        if packet.get("parser_version") != PARSER_VERSION:
            _add(errors, "session_audit_parser_version_invalid", f"{path}.parser_version", "projected parser version is invalid")
        for field in ("audit_id", "session_id"):
            if not _is_non_empty_string(packet.get(field)):
                _add(errors, "session_audit_identifier_invalid", f"{path}.{field}", "projected identifier is invalid")
        if not isinstance(packet.get("audit_id"), str) or not AUDIT_ID_RE.fullmatch(packet["audit_id"]):
            _add(errors, "session_audit_identifier_invalid", f"{path}.audit_id", "projected audit_id is invalid")
        if not isinstance(packet.get("session_id"), str) or not SAFE_ID_RE.fullmatch(packet["session_id"]):
            _add(errors, "session_audit_identifier_invalid", f"{path}.session_id", "projected session_id is invalid")
        if packet.get("tool") not in TOOLS:
            _add(errors, "session_audit_tool_invalid", f"{path}.tool", "tool is outside the closed vocabulary")
        if packet.get("capture_mode") not in CAPTURE_MODES:
            _add(errors, "session_audit_capture_mode_invalid", f"{path}.capture_mode", "capture mode is outside the closed vocabulary")
        if packet.get("capture_status") not in CAPTURE_STATUSES:
            _add(errors, "session_audit_capture_status_invalid", f"{path}.capture_status", "capture status is outside the closed vocabulary")
        if packet.get("integrity_status") not in INTEGRITY_STATUSES:
            _add(errors, "session_audit_integrity_status_invalid", f"{path}.integrity_status", "integrity status is outside the closed vocabulary")
        if packet.get("repair_class") not in REPAIR_CLASSES:
            _add(errors, "session_audit_repair_class_invalid", f"{path}.repair_class", "repair class is outside the closed vocabulary")
        if packet.get("not_goal_truth") is not True or packet.get("not_validation_evidence") is not True:
            _add(errors, "session_audit_projection_truth_flags_invalid", path, "projected packet truth flags are invalid")
        if packet.get("source_projection_verified") is not True:
            _add(
                errors,
                "session_audit_source_projection_not_verified",
                path,
                "collector projection must assert bundled deterministic source validation",
            )
        if packet.get("canonical_refs_verified") is not True:
            _add(errors, "session_audit_canonical_refs_not_verified", path, "collector projection must assert independent canonical-ref verification")
        if not isinstance(packet.get("consumable"), bool) or not isinstance(packet.get("auto_repair_allowed"), bool):
            _add(errors, "session_audit_projection_boolean_invalid", path, "projected policy flags must be boolean")
        elif packet.get("auto_repair_allowed") is not (packet.get("repair_class") == "derived_metadata_only"):
            _add(errors, "session_audit_auto_repair_scope_invalid", path, "projected auto-repair scope is invalid")
        expected_repair_target = AUTO_REPAIR_TARGET if packet.get("auto_repair_allowed") is True else None
        if packet.get("auto_repair_target") != expected_repair_target:
            _add(errors, "session_audit_auto_repair_target_invalid", path, "auto-repair can target only the derived session-audit index")
        projected_expected_consumable = (
            packet.get("capture_status") == "complete"
            and packet.get("integrity_status") != "unverified"
            and packet.get("capture_mode") != "unknown"
            and isinstance(packet.get("binding"), dict)
            and packet["binding"].get("status") == "bound"
        )
        if isinstance(packet.get("consumable"), bool) and packet.get("consumable") is not projected_expected_consumable:
            _add(errors, "session_audit_consumability_inconsistent", path, "projected consumability is inconsistent")
        if not isinstance(packet.get("source_sha256"), str) or not SHA256_RE.fullmatch(packet["source_sha256"]):
            _add(errors, "session_audit_source_hash_invalid", f"{path}.source_sha256", "projected source hash is invalid")
        if (
            not isinstance(packet.get("source_size_bytes"), int)
            or isinstance(packet.get("source_size_bytes"), bool)
            or packet["source_size_bytes"] < 0
        ):
            _add(errors, "session_audit_source_size_invalid", f"{path}.source_size_bytes", "projected source size is invalid")
        binding = packet.get("binding")
        if (
            not isinstance(binding, dict)
            or not set(binding) <= {"status", "cycle_id", "task_id"}
            or binding.get("status") not in BINDING_STATUSES
        ):
            _add(errors, "session_audit_binding_status_invalid", f"{path}.binding", "projected binding is invalid")
        else:
            identifiers = [binding.get("cycle_id"), binding.get("task_id")]
            if any(value is not None and (not isinstance(value, str) or not SAFE_ID_RE.fullmatch(value)) for value in identifiers):
                _add(errors, "session_audit_binding_identifier_invalid", f"{path}.binding", "projected binding identifier is invalid")
            if binding.get("status") == "bound" and not all(
                isinstance(value, str) and SAFE_ID_RE.fullmatch(value) for value in identifiers
            ):
                _add(errors, "session_audit_bound_identifier_missing", f"{path}.binding", "bound projection lacks both identifiers")
            if binding.get("status") in {"ambiguous", "unbound"} and any(_is_non_empty_string(value) for value in identifiers):
                _add(errors, "session_audit_unbound_identifier_claimed", f"{path}.binding", "non-bound projection claims an identifier")
        event_counts = packet.get("event_counts")
        if not isinstance(event_counts, dict) or any(
            not isinstance(value, int) or isinstance(value, bool) or value < 0 for value in event_counts.values()
        ):
            _add(errors, "session_audit_event_counts_invalid", f"{path}.event_counts", "projected event counts are invalid")
        timestamp_bounds = packet.get("timestamp_bounds")
        if not isinstance(timestamp_bounds, dict) or set(timestamp_bounds) != {"first", "last"}:
            _add(errors, "session_audit_timestamp_bounds_invalid", f"{path}.timestamp_bounds", "projected timestamp bounds are invalid")
        elif any(value is not None and not _is_non_empty_string(value) for value in timestamp_bounds.values()):
            _add(errors, "session_audit_timestamp_value_invalid", f"{path}.timestamp_bounds", "projected timestamp value is invalid")
        evidence_path_hashes = packet.get("evidence_path_hashes")
        if not isinstance(evidence_path_hashes, list) or not evidence_path_hashes or any(
            not isinstance(value, str) or not SHA256_RE.fullmatch(value) for value in evidence_path_hashes
        ):
            _add(errors, "session_audit_evidence_hash_projection_invalid", f"{path}.evidence_path_hashes", "projected evidence hashes are invalid")
        file_metadata = packet.get("file")
        if not isinstance(file_metadata, dict) or not set(file_metadata) <= {"path", "sha256", "size_bytes"}:
            _add(errors, "session_audit_projection_file_invalid", f"{path}.file", "projected file metadata is invalid")
        elif (
            file_metadata.get("path") != f".task/session_audit/{packet.get('audit_id')}.json"
            or not isinstance(file_metadata.get("sha256"), str)
            or not SHA256_RE.fullmatch(file_metadata["sha256"])
            or not isinstance(file_metadata.get("size_bytes"), int)
            or isinstance(file_metadata.get("size_bytes"), bool)
            or file_metadata["size_bytes"] < 0
        ):
            _add(errors, "session_audit_projection_file_invalid", f"{path}.file", "projected file metadata values are invalid")
        findings = packet.get("findings")
        if not isinstance(findings, list):
            _add(errors, "session_audit_findings_invalid", f"{path}.findings", "projected findings must be a list")
        else:
            for finding_index, finding in enumerate(findings):
                finding_path = f"{path}.findings.{finding_index}"
                required = {"code", "severity", "evidence_class", "resolved", "canonical_evidence_ref_hashes"}
                if not isinstance(finding, dict) or set(finding) != required:
                    _add(errors, "session_audit_projection_finding_shape_invalid", finding_path, "projected finding shape is invalid")
                    continue
                if finding.get("severity") not in FINDING_SEVERITIES or finding.get("evidence_class") not in EVIDENCE_CLASSES:
                    _add(errors, "session_audit_projection_finding_vocabulary_invalid", finding_path, "projected finding vocabulary is invalid")
                if not _is_non_empty_string(finding.get("code")):
                    _add(errors, "session_audit_projection_finding_code_invalid", finding_path, "projected finding code is invalid")
                ref_hashes = finding.get("canonical_evidence_ref_hashes")
                if not isinstance(finding.get("resolved"), bool) or not isinstance(ref_hashes, list) or any(
                    not isinstance(value, str) or not SHA256_RE.fullmatch(value) for value in ref_hashes
                ):
                    _add(errors, "session_audit_projection_finding_value_invalid", finding_path, "projected finding values are invalid")
                if (
                    finding.get("severity") == "block"
                    and finding.get("evidence_class") in CANONICAL_EVIDENCE_CLASSES
                    and not ref_hashes
                ):
                    _add(errors, "session_audit_canonical_evidence_missing", finding_path, "canonical block finding lacks references")
    for index, packet in enumerate(invalid_packets):
        if (
            not isinstance(packet, dict)
            or set(packet) != {"contract_status", "file", "error_codes"}
            or packet.get("contract_status") not in {"invalid", "malformed", "unsafe"}
            or not _is_string_list(packet.get("error_codes"))
        ):
            _add(errors, "session_audit_invalid_projection_invalid", f"invalid_packets.{index}", "invalid packet diagnostic is malformed")
    index_projection = value.get("index")
    if not isinstance(index_projection, dict):
        _add(errors, "session_audit_index_projection_invalid", "index", "index projection must be an object")
    elif index_projection:
        status = index_projection.get("contract_status")
        base_fields = {"path", "sha256", "size_bytes", "contract_status"}
        valid_fields = base_fields | {
            "index_id",
            "entry_count",
            "repair_class",
            "auto_repair_allowed",
            "auto_repair_target",
            "not_goal_truth",
            "not_validation_evidence",
            "evidence_path_hashes",
        }
        invalid_fields = base_fields | {"error_codes"}
        expected_fields = valid_fields if status == "valid" else invalid_fields
        if set(index_projection) != expected_fields or status not in {"valid", "invalid", "malformed"}:
            _add(errors, "session_audit_index_projection_invalid", "index", "index projection schema is invalid")
        elif (
            index_projection.get("path") != AUTO_REPAIR_TARGET
            or not isinstance(index_projection.get("sha256"), str)
            or not SHA256_RE.fullmatch(index_projection["sha256"])
            or not isinstance(index_projection.get("size_bytes"), int)
            or isinstance(index_projection.get("size_bytes"), bool)
            or index_projection["size_bytes"] < 0
        ):
            _add(errors, "session_audit_index_projection_file_invalid", "index", "index file metadata is invalid")
        elif status == "valid":
            path_hashes = index_projection.get("evidence_path_hashes")
            if (
                not isinstance(index_projection.get("index_id"), str)
                or not re.fullmatch(r"index-[0-9a-f]{32}", index_projection["index_id"])
                or not isinstance(index_projection.get("entry_count"), int)
                or isinstance(index_projection.get("entry_count"), bool)
                or index_projection["entry_count"] < 0
                or index_projection.get("repair_class") != "derived_metadata_only"
                or index_projection.get("auto_repair_allowed") is not True
                or index_projection.get("auto_repair_target") != AUTO_REPAIR_TARGET
                or index_projection.get("not_goal_truth") is not True
                or index_projection.get("not_validation_evidence") is not True
                or not isinstance(path_hashes, list)
                or any(not isinstance(item, str) or not SHA256_RE.fullmatch(item) for item in path_hashes)
            ):
                _add(errors, "session_audit_index_projection_policy_invalid", "index", "validated index projection policy is invalid")
        elif not _is_string_list(index_projection.get("error_codes")):
            _add(errors, "session_audit_index_projection_errors_invalid", "index.error_codes", "invalid index diagnostics are malformed")
    return errors
