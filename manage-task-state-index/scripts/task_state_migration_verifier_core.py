"""Read-only primitives for independent task-state migration verification.

This module deliberately shares no imports with ``task_state_migration.py``.
The constants below describe the public on-disk contract; no producer result
or recovery helper is used as verification truth.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import stat
from typing import Any, Iterable


TOOL_VERSIONS = {"1.1.0"}
PLAN_SCHEMA_VERSION = 2
MAPPING_SCHEMA_VERSION = 1
MANIFEST_SCHEMA_VERSION = 2
RECEIPT_SCHEMA_VERSION = 2
INDEX_FORMAT_VERSION = 2
INDEX_SCHEMA_VERSION = 1
MISSING_TOKEN = "__MISSING__"
INFER_TOKEN = "__INFER__"
MIGRATION_EVENT_FIELD = "task_state_migration_event"
SEAL_KIND = "task_state_migration_seal"
ANCHOR_KIND = "task_state_migration_receipt_anchor"
EVENT_KINDS = {"upsert", "link"}
CURRENT_EVENT_KEYS = {
    "format_version", "schema_version", "event", "id", "updated_at", "type",
    "status", "path", "title", "parent_id", "content_sha256", "created_at",
    "note", "links", "fields",
}
LIFECYCLE_STATUSES = {
    "active", "applied", "archived", "blocked", "candidate", "closed",
    "complete", "completed", "deferred", "deleted", "deprecated", "failed",
    "in_progress", "informational", "logged", "needs_review", "not_applicable",
    "obsolete", "open", "partial", "partially_resolved", "passed", "raw",
    "rejected", "resolved", "running", "skipped", "stale", "superseded",
    "terminal_blocked",
}
CLASSIFICATIONS = {
    "accepted_current",
    "normalized_legacy",
    "mapped_legacy",
    "quarantined_historical",
    "blocked_unknown_or_future",
}
PROJECTION_IMPACTS = {"independent", "affected", "unknown"}
NON_ACTIVE_STATUSES = {
    "applied",
    "archived",
    "closed",
    "deleted",
    "deprecated",
    "obsolete",
    "rejected",
    "resolved",
    "superseded",
}
ARTIFACT_TYPES = {
    "task",
    "task_pack",
    "past_task",
    "candidate_task",
    "task_miss",
    "agent_log",
    "execution",
    "audit",
    "validation",
    "goal",
    "goal_prompt",
    "interview",
    "environment",
    "external_advice",
    "issue",
    "issue_resolution",
    "issue_map",
    "schema_contract",
    "schema_map",
}
SHA256_LENGTH = 64
OPAQUE_ID_SOURCE_MAX_BYTES = 160
OPAQUE_ID_NAMESPACES = frozenset({"task", "pack"})
VERIFICATION_ERROR_CODES = frozenset({
    "arguments_invalid",
    "internal_verification_failure",
    "invalid_verification_input",
    "io_failure",
    "unsafe_output_identity",
    "verification_failed",
})


class VerificationError(ValueError):
    """The supplied evidence does not prove the sealed migration contract."""

    def __init__(
        self,
        message: str = "verification failed",
        *,
        error_code: str = "verification_failed",
    ) -> None:
        self.error_code = (
            error_code
            if error_code in VERIFICATION_ERROR_CODES
            else "verification_failed"
        )
        super().__init__(message)


def _fail(
    message: str, *, error_code: str = "verification_failed"
) -> None:
    raise VerificationError(message, error_code=error_code)


def _require(
    condition: bool,
    message: str,
    *,
    error_code: str = "verification_failed",
) -> None:
    if not condition:
        _fail(message, error_code=error_code)


def _is_int(value: Any) -> bool:
    return type(value) is int


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == SHA256_LENGTH
        and all(character in "0123456789abcdef" for character in value)
    )


def _opaque_identity_token(value: Any, namespace: str) -> str:
    """Project an internal identity to a bounded body-free output token."""
    _require(
        type(namespace) is str and namespace in OPAQUE_ID_NAMESPACES,
        "output identity namespace is invalid",
        error_code="unsafe_output_identity",
    )
    if type(value) is not str:
        _fail(
            "output identity is not a safe opaque token",
            error_code="unsafe_output_identity",
        )
    try:
        encoded = value.encode("utf-8")
    except UnicodeEncodeError:
        _fail(
            "output identity is not a safe opaque token",
            error_code="unsafe_output_identity",
        )
    valid = (
        0 < len(encoded) <= OPAQUE_ID_SOURCE_MAX_BYTES
        and all(
            character.isprintable() and not character.isspace()
            for character in value
        )
    )
    _require(
        valid,
        "output identity is not a safe opaque token",
        error_code="unsafe_output_identity",
    )
    return f"{namespace}-sha256-{_sha256(encoded)}"


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


def _event_bytes(events: Iterable[dict[str, Any]]) -> bytes:
    return b"".join(_canonical_json(event) for event in events)


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


def _workspace_ref(root: Path, value: Any, label: str, *, must_exist: bool = True) -> Path:
    _require(isinstance(value, str) and value and "\x00" not in value, f"{label} ref is invalid")
    relative = Path(value)
    _require(not relative.is_absolute(), f"{label} ref must be workspace-relative")
    _require(value == relative.as_posix(), f"{label} ref is not normalized")
    _require(all(part not in {"", ".", ".."} for part in relative.parts), f"{label} ref is unsafe")
    current = root
    for part in relative.parts:
        current /= part
        _require(not current.is_symlink(), f"{label} ref contains a symlink")
    target = root / relative
    if must_exist:
        _regular_file(target, label)
        try:
            target.resolve(strict=True).relative_to(root)
        except (OSError, ValueError) as exc:
            raise VerificationError(f"{label} ref escapes the workspace") from exc
    return target


def _transaction_ref(
    root: Path,
    value: Any,
    transaction_id: str,
    label: str,
    *,
    must_exist: bool = True,
) -> Path:
    target = _workspace_ref(root, value, label, must_exist=must_exist)
    relative = target.relative_to(root)
    _require(
        relative.parts[:3] == (".task", "migrations", transaction_id),
        f"{label} ref is outside the transaction",
    )
    return target


def _load_json(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    payload = _regular_file(path, label).read_bytes()
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise VerificationError(f"{label} is not valid UTF-8 JSON: {exc}") from exc
    _require(isinstance(value, dict), f"{label} must be an object")
    return value, payload


def _hashed_transaction_ref(
    root: Path,
    owner: dict[str, Any],
    ref_field: str,
    sha_field: str,
    transaction_id: str,
    label: str,
) -> tuple[Path, bytes]:
    expected = owner.get(sha_field)
    _require(
        _is_sha256(expected),
        f"{label} hash is invalid",
    )
    path = _transaction_ref(root, owner.get(ref_field), transaction_id, label)
    payload = path.read_bytes()
    _require(_sha256(payload) == expected, f"{label} hash mismatch")
    return path, payload


def _physical_lines(payload: bytes) -> list[bytes]:
    if not payload:
        return []
    return payload.splitlines(keepends=True)


def _normalize_links(value: Any) -> list[dict[str, str]] | None:
    if value is None:
        return []
    if not isinstance(value, list):
        return None
    normalized: list[dict[str, str]] = []
    for link in value:
        if (
            isinstance(link, dict)
            and isinstance(link.get("rel"), str)
            and isinstance(link.get("id"), str)
        ):
            normalized.append({"rel": link["rel"], "id": link["id"]})
            continue
        if isinstance(link, str) and ":" in link:
            relation, target = link.split(":", 1)
            if relation and target:
                normalized.append({"rel": relation, "id": target})
                continue
        return None
    return normalized


def _validate_current_event(
    event: dict[str, Any], *, allow_sparse_upsert: bool = False,
    exact_top_level_fields: bool = False,
) -> None:
    if exact_top_level_fields:
        _require(not (set(event) - CURRENT_EVENT_KEYS), "current event has unknown fields")
    _require(
        _is_int(event.get("format_version"))
        and event["format_version"] == INDEX_FORMAT_VERSION
        and _is_int(event.get("schema_version"))
        and event["schema_version"] == INDEX_SCHEMA_VERSION,
        "current event has unsupported version",
    )
    _require(event.get("event") in EVENT_KINDS, "current event has unsupported discriminator")
    _require(
        isinstance(event.get("id"), str)
        and bool(event["id"])
        and isinstance(event.get("updated_at"), str)
        and bool(event["updated_at"]),
        "current event lacks identity or timestamp",
    )
    if event["event"] == "upsert":
        if allow_sparse_upsert and "type" not in event:
            pass
        else:
            _require(event.get("type") in ARTIFACT_TYPES, "current upsert has unsupported type")
        if not allow_sparse_upsert:
            for field in ("type", "status", "path"):
                _require(
                    isinstance(event.get(field), str) and bool(event[field]),
                    f"current upsert lacks {field}",
                )
    if event.get("status") is not None:
        _require(
            isinstance(event["status"], str) and event["status"] in LIFECYCLE_STATUSES,
            "current event status is invalid",
        )
    links = _normalize_links(event.get("links"))
    _require(event.get("links") is None or links is not None, "current event links are invalid")
    fields = event.get("fields")
    _require(fields is None or isinstance(fields, dict), "current event fields are invalid")
    if isinstance(fields, dict) and "link_tombstones" in fields:
        _require(
            _normalize_links(fields["link_tombstones"]) is not None,
            "current event link tombstones are invalid",
        )


def _writer_sparse_upsert_kind(event: dict[str, Any]) -> str | None:
    if event.get("event") != "upsert":
        return None
    base = {"format_version", "schema_version", "event", "id", "updated_at"}
    payload = set(event) - base
    if payload == {"status"}:
        return "status"
    if payload == {"fields"}:
        return "fields"
    return None


def _validate_suffix_event(event: dict[str, Any], known_ids: set[str]) -> None:
    sparse = _writer_sparse_upsert_kind(event)
    if sparse is not None:
        _validate_current_event(
            event, allow_sparse_upsert=True, exact_top_level_fields=True
        )
        _require(event["id"] in known_ids, "sparse suffix upsert references an unknown ID")
        if sparse == "status":
            _require(
                isinstance(event.get("status"), str) and bool(event["status"]),
                "sparse status update is invalid",
            )
        return
    _validate_current_event(event, exact_top_level_fields=True)
    if event["event"] == "upsert":
        known_ids.add(event["id"])


def _merge_event_into_state(
    state: dict[str, dict[str, Any]], event: dict[str, Any]
) -> None:
    item_id = event.get("id")
    if not isinstance(item_id, str) or not item_id:
        return
    current = state.setdefault(item_id, {"id": item_id, "links": [], "fields": {}})
    for key in ("type", "status", "path", "title", "parent_id", "content_sha256", "note", "updated_at"):
        if event.get(key) is not None:
            current[key] = event[key]
    fields = event.get("fields") if isinstance(event.get("fields"), dict) else {}
    removed = {
        (item["rel"], item["id"])
        for item in (_normalize_links(fields.get("link_tombstones")) or [])
    }
    if removed:
        current["links"] = [
            link for link in current.get("links", [])
            if (link.get("rel"), link.get("id")) not in removed
        ]
    current.setdefault("fields", {}).update(fields)
    seen = {(link.get("rel"), link.get("id")) for link in current.setdefault("links", [])}
    for link in _normalize_links(event.get("links")) or []:
        pair = (link["rel"], link["id"])
        if pair not in seen:
            current["links"].append(link)
            seen.add(pair)


def _merge_state(events: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    state: dict[str, dict[str, Any]] = {}
    for event in events:
        _merge_event_into_state(state, event)
    return state


def _broken_links(state: dict[str, dict[str, Any]], item_id: str) -> list[dict[str, str]]:
    return [
        {"rel": link["rel"], "id": link["id"]}
        for link in state.get(item_id, {}).get("links", [])
        if isinstance(link, dict) and link.get("id") not in state
    ]


def _versioned(event: dict[str, Any]) -> dict[str, Any]:
    return {
        **event,
        "format_version": INDEX_FORMAT_VERSION,
        "schema_version": INDEX_SCHEMA_VERSION,
    }
