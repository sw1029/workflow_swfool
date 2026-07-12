"""Source-separated primitives for agent-log migration verification."""

from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import stat
from typing import Any


MIGRATION_KIND = "agent_log_legacy_migration"
MISSING_STATUS = "__MISSING_STATUS__"
ALLOWED_CLASSIFICATIONS = {"canonical_log", "duplicate_alias", "foreign_event"}
ALLOWED_RECOVERY = {"not_needed", "forward_completed"}
CURRENT_STATUSES = {"blocked", "completed", "failed", "informational", "partial"}
SUPPORTED_TOOL_VERSIONS = {"1.0.0"}
SHA256_LENGTH = 64


class VerificationError(ValueError):
    """Raised when independent evidence does not prove the migration graph."""


def _fail(message: str) -> None:
    raise VerificationError(message)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_json(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def _require(condition: bool, message: str) -> None:
    if not condition:
        _fail(message)


def _is_int(value: Any) -> bool:
    return type(value) is int


def _root(raw: str | Path) -> Path:
    lexical = Path(raw).expanduser().absolute()
    _require(not lexical.is_symlink(), "workspace root must not be a symlink")
    try:
        resolved = lexical.resolve(strict=True)
    except OSError as exc:
        raise VerificationError(f"workspace root is unavailable: {exc}") from exc
    _require(resolved.is_dir(), "workspace root must be a directory")
    return resolved


def _regular_file(path: Path, label: str) -> Path:
    _require(path.exists() and not path.is_symlink(), f"{label} is missing or a symlink")
    _require(stat.S_ISREG(path.lstat().st_mode), f"{label} is not a regular file")
    return path


def _migration_ref(root: Path, value: Any, migration_id: str, label: str) -> Path:
    _require(isinstance(value, str) and value and "\x00" not in value, f"{label} ref is invalid")
    relative = Path(value)
    _require(not relative.is_absolute(), f"{label} ref must be workspace-relative")
    _require(value == relative.as_posix(), f"{label} ref is not normalized")
    _require(all(part not in {"", ".", ".."} for part in relative.parts), f"{label} ref is unsafe")
    expected = (".agent_log", "migrations", migration_id)
    _require(relative.parts[:3] == expected, f"{label} ref is outside the migration transaction")
    current = root
    for part in relative.parts:
        current /= part
        _require(not current.is_symlink(), f"{label} ref contains a symlink")
    target = _regular_file(root / relative, label)
    try:
        target.resolve(strict=True).relative_to(root)
    except (OSError, ValueError) as exc:
        raise VerificationError(f"{label} ref escapes the workspace") from exc
    return target


def _load_json(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    payload = _regular_file(path, label).read_bytes()
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise VerificationError(f"{label} is not valid UTF-8 JSON: {exc}") from exc
    _require(isinstance(value, dict), f"{label} must be an object")
    return value, payload


def _hashed_ref(
    root: Path,
    owner: dict[str, Any],
    ref_field: str,
    sha_field: str,
    migration_id: str,
    label: str,
) -> tuple[Path, bytes]:
    expected = owner.get(sha_field)
    _require(isinstance(expected, str) and len(expected) == SHA256_LENGTH, f"{label} hash is invalid")
    path = _migration_ref(root, owner.get(ref_field), migration_id, label)
    payload = path.read_bytes()
    _require(_sha256(payload) == expected, f"{label} hash mismatch")
    return path, payload


def _source_rows(payload: bytes) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    offset = 0
    for line_number, raw in enumerate(payload.splitlines(keepends=True), start=1):
        start = offset
        offset += len(raw)
        content = raw.rstrip(b"\r\n")
        if not content.strip():
            continue
        parsed: dict[str, Any] | None = None
        error: str | None = None
        try:
            candidate = json.loads(content.decode("utf-8"))
            if not isinstance(candidate, dict):
                raise ValueError("row is not an object")
            parsed = candidate
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            error = str(exc)
        rows.append(
            {
                "source_line": line_number,
                "source_byte_start": start,
                "source_byte_end": offset,
                "source_row_sha256": _sha256(raw),
                "parsed": parsed,
                "parse_error": error,
            }
        )
    _require(offset == len(payload), "source snapshot byte accounting is incomplete")
    return rows


def _walk_markdown(root: Path) -> list[dict[str, Any]]:
    log_root = root / ".agent_log"
    _require(log_root.exists() and log_root.is_dir() and not log_root.is_symlink(), ".agent_log is unsafe")
    entries: list[dict[str, Any]] = []
    pending = [log_root]
    while pending:
        directory = pending.pop()
        for item in directory.iterdir():
            _require(not item.is_symlink(), f"agent-log inventory contains a symlink: {item}")
            if item.is_dir():
                pending.append(item)
            elif item.is_file():
                if item.suffix.lower() == ".md":
                    entries.append(
                        {
                            "path": item.relative_to(root).as_posix(),
                            "body_sha256": _sha256_path(item),
                            "size": item.stat().st_size,
                        }
                    )
            else:
                _fail(f"agent-log inventory contains a non-regular entry: {item}")
    return sorted(entries, key=lambda item: item["path"])


def _status_mappings(document: dict[str, Any]) -> dict[str | None, dict[str, Any]]:
    _require(
        set(document) == {"schema_version", "mapping_policy_id", "version", "entries"},
        "status map is not the exact schema-v1 projection",
    )
    _require(_is_int(document.get("schema_version")) and document["schema_version"] == 1, "status map schema mismatch")
    _require(isinstance(document.get("mapping_policy_id"), str) and document["mapping_policy_id"], "status map policy is missing")
    version = document.get("version")
    _require(isinstance(version, (str, int)) and not isinstance(version, bool), "status map version is invalid")
    entries = document.get("entries")
    _require(isinstance(entries, list), "status map entries are missing")
    mappings: dict[str | None, dict[str, Any]] = {}
    for position, entry in enumerate(entries, start=1):
        _require(isinstance(entry, dict), f"status map entry {position} is invalid")
        _require(
            set(entry)
            in (
                {"original_status", "normalized_status", "reason"},
                {
                    "original_status",
                    "normalized_status",
                    "reason",
                    "status_evidence",
                },
            ),
            f"status map entry {position} has unknown or missing fields",
        )
        original = entry.get("original_status")
        _require(original is None or (isinstance(original, str) and original), f"status map entry {position} original status is invalid")
        _require(original not in mappings, f"status map has duplicate exact status {original!r}")
        normalized = entry.get("normalized_status")
        _require(normalized in CURRENT_STATUSES, f"status map entry {position} normalized status is invalid")
        reason = entry.get("reason")
        _require(isinstance(reason, str) and reason, f"status map entry {position} reason is missing")
        _require(not (normalized == "completed" and original != "completed"), "status map upgrades a historical completion claim")
        _require(original is not None or normalized == "informational", "missing status must map to informational")
        _require(original is not None or entry.get("status_evidence") == "not_evaluated", "missing status evidence is not fail-closed")
        mappings[original] = entry
    return mappings


def _current_prefix(index_payload: bytes, size: Any, expected_sha: Any) -> bytes:
    _require(_is_int(size) and size >= 0, "committed index size is invalid")
    _require(isinstance(expected_sha, str), "committed index hash is invalid")
    _require(len(index_payload) >= size, "current index is shorter than committed prefix")
    prefix = index_payload[:size]
    _require(_sha256(prefix) == expected_sha, "committed index prefix hash mismatch")
    return prefix


def _records(payload: bytes) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for line_number, raw in enumerate(payload.splitlines(keepends=True), start=1):
        _require(raw.endswith((b"\n", b"\r")), f"committed index row {line_number} is unterminated")
        try:
            row = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise VerificationError(f"committed index row {line_number} is invalid: {exc}") from exc
        _require(isinstance(row, dict), f"committed index row {line_number} is not an object")
        result.append(row)
    return result


def _expected_record_id(record: dict[str, Any]) -> str:
    body = {key: value for key, value in record.items() if key != "record_id"}
    return "log-record-" + _sha256(_canonical_json(body))[:32]


def _body_metadata(path: Path) -> dict[str, str]:
    metadata: dict[str, str] = {}
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                stripped = line.rstrip("\r\n")
                if line_number == 1 and stripped.startswith("# "):
                    metadata["title"] = stripped[2:].strip()
                match = re.match(
                    r"^-\s*(log[ _-]?id|timestamp|updated_at|status)\s*:\s*(.*?)\s*$",
                    stripped,
                    flags=re.IGNORECASE,
                )
                if match:
                    raw_key = match.group(1).lower().replace("-", "_").replace(" ", "_")
                    key = "log_id" if raw_key in {"logid", "log_id"} else raw_key
                    metadata[key] = match.group(2).strip().strip("`").strip()
                if line_number >= 80:
                    break
    except UnicodeDecodeError:
        return {}
    return metadata


def _body_text(path: Path) -> str:
    try:
        value = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return ""
    return re.sub(r"\s+", " ", value.replace("`", "").lower()).strip()


def _candidate_score(
    parsed: dict[str, Any], body_sha: str, metadata: dict[str, str], text: str
) -> tuple[int, ...] | None:
    declared_sha = parsed.get("body_sha256")
    if declared_sha is not None:
        if not isinstance(declared_sha, str) or declared_sha != body_sha:
            return None
        total = 20
    else:
        total = 0
    matched = 0
    mismatched = 0
    for key, weight in (("log_id", 8), ("status", 6), ("timestamp", 3), ("title", 1)):
        row_value = parsed.get(key)
        body_value = metadata.get(key)
        alternate = metadata.get("updated_at") if key == "timestamp" else None
        if row_value is None or (body_value is None and alternate is None):
            continue
        if isinstance(row_value, str) and row_value in {body_value, alternate}:
            total += weight
            matched += 1
        else:
            total -= weight
            mismatched += 1
    content_hits = 0
    content_score = 0
    normalized_values: list[str] = []
    if text:
        values: list[str] = []
        for field in ("task_intent", "work_performed", "result", "shortcomings", "title"):
            value = parsed.get(field)
            if isinstance(value, str):
                values.append(value)
        for field in ("commands", "agent_notes", "follow_ups", "tags"):
            value = parsed.get(field)
            if isinstance(value, list):
                values.extend(item for item in value if isinstance(item, str))
        for value in values:
            normalized = re.sub(r"\s+", " ", value.replace("`", "").lower()).strip()
            normalized_values.append(normalized)
            if len(normalized) >= 12 and normalized in text:
                content_hits += 1
                content_score += 2 + min(len(normalized), 240) // 80
    total += content_score
    body_tokens = Counter(re.findall(r"[a-z0-9_./-]{4,}", text))
    candidate_tokens = Counter(
        token
        for value in normalized_values
        for token in re.findall(r"[a-z0-9_./-]{4,}", value)
    )
    overlap = sum(min(count, body_tokens.get(token, 0)) for token, count in candidate_tokens.items())
    token_total = sum(candidate_tokens.values())
    precision = overlap * 1000 // token_total if token_total else 0
    return total, content_hits, overlap, precision, matched, -mismatched


def _is_current_record(parsed: dict[str, Any], body_sha: str) -> bool:
    return (
        parsed.get("format_version") == 3
        and parsed.get("schema_version") == 2
        and parsed.get("content_id_scheme") is None
        and parsed.get("body_sha256") == body_sha
        and parsed.get("content_id") == "log-content-" + body_sha[:32]
        and parsed.get("record_id") == _expected_record_id(parsed)
    )
