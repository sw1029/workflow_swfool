"""Compile small lifecycle intents into canonical transition requests."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path
import stat
import sys
from typing import Any

from .artifacts import extract_advice_fields, extract_task_pack_fields
from .contracts import LIFECYCLE_STATUSES, NON_ACTIVE_STATUSES, PREFIXES
from .events import load_events_read_only, merge_state
from .storage import jsonl_path, read_title, sha256_file, slugify
from .transition_plan_contract import canonical_bytes, workspace_path


COMPILATION_KIND = "task_state_transition_compilation"
COMPILATION_SCHEMA_VERSION = 1
INTENT_FIELDS = {"schema_version", "expected_index_revision", "actions"}
ACTION_FIELDS = {
    "action",
    "artifact_ref",
    "artifact_type",
    "identity",
    "status",
    "relationships",
    "note",
}
RELATIONSHIP_FIELDS = {
    "rel",
    "target_ref",
    "target_type",
    "target_identity",
}
IDENTITIES = {"auto", "current", "new"}


def _load_json(value: str) -> dict[str, Any]:
    if value == "-":
        payload = sys.stdin.read()
    elif value.lstrip().startswith("{"):
        payload = value
    else:
        path = Path(value)
        if not path.exists() and not path.is_symlink():
            raise ValueError("Transition intent must be JSON text, '-', or an existing file")
        mode = path.lstat().st_mode
        if stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
            raise ValueError("Transition intent path must be a regular non-symlink file")
        payload = path.read_text(encoding="utf-8")
    try:
        parsed = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Transition intent must contain valid UTF-8 JSON") from exc
    if not isinstance(parsed, dict):
        raise ValueError("Transition intent must be a JSON object")
    return parsed


def load_transition_intent(value: str) -> dict[str, Any]:
    """Load one compact intent without accepting implicit path fallbacks."""

    return _load_json(value)


def _timestamp(value: str) -> tuple[str, dt.datetime]:
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("--at must be a timezone-aware RFC3339 timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError("--at must be a timezone-aware RFC3339 timestamp")
    return value, parsed


def _artifact_file(root: Path, ref: Any) -> tuple[str, Path]:
    if not isinstance(ref, str):
        raise ValueError("Every transition action requires artifact_ref")
    path = workspace_path(root, ref)
    if not path.exists() and not path.is_symlink():
        raise ValueError(f"Transition artifact is missing: {ref}")
    mode = path.lstat().st_mode
    if stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
        raise ValueError(f"Transition artifact must be a regular file: {ref}")
    return ref, path


def _current_matches(
    state: dict[str, dict[str, Any]], ref: str, artifact_type: str
) -> list[tuple[str, dict[str, Any]]]:
    return sorted(
        (
            (item_id, item)
            for item_id, item in state.items()
            if item.get("path") == ref
            and item.get("type") == artifact_type
            and item.get("status") not in NON_ACTIVE_STATUSES
        ),
        key=lambda pair: pair[0],
    )


def _embedded_id(path: Path, artifact_type: str) -> tuple[str | None, dict[str, Any]]:
    if artifact_type == "external_advice":
        fields = extract_advice_fields(path)
        return str(fields.get("advice_id") or "") or None, fields
    if artifact_type == "task_pack":
        fields = extract_task_pack_fields(path)
        return str(fields.get("pack_id") or "") or None, fields
    return None, {}


def _generated_id(
    artifact_type: str,
    title: str,
    timestamp: dt.datetime,
    occupied: set[str],
) -> str:
    prefix = PREFIXES.get(artifact_type, slugify(artifact_type, "item"))
    base = (
        f"{prefix}-{timestamp.strftime('%Y%m%d-%H%M%S')}-"
        f"{slugify(title, artifact_type)}"
    )
    candidate = base
    suffix = 2
    while candidate in occupied:
        candidate = f"{base}-{suffix}"
        suffix += 1
    return candidate


def _validate_relationships(value: Any) -> list[dict[str, str]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("Transition action relationships must be a list")
    normalized: list[dict[str, str]] = []
    for row in value:
        if not isinstance(row, dict) or set(row) - RELATIONSHIP_FIELDS:
            raise ValueError("Transition relationship has unsupported fields")
        required = ("rel", "target_ref")
        if any(not isinstance(row.get(field), str) or not row[field] for field in required):
            raise ValueError("Transition relationship requires rel and target_ref")
        target_type = row.get("target_type")
        if target_type is not None and (
            not isinstance(target_type, str) or not target_type
        ):
            raise ValueError("Transition relationship target_type must be non-empty")
        identity = row.get("target_identity", "auto")
        if identity not in IDENTITIES:
            raise ValueError("Transition relationship target_identity is invalid")
        normalized.append(
            {
                "rel": row["rel"],
                "target_ref": row["target_ref"],
                "target_type": target_type or "",
                "target_identity": identity,
            }
        )
    return normalized


def _validated_actions(intent: dict[str, Any]) -> list[dict[str, Any]]:
    if set(intent) != INTENT_FIELDS or intent.get("schema_version") != 1:
        raise ValueError("Transition intent fields or schema_version are unsupported")
    actions = intent.get("actions")
    if not isinstance(actions, list) or not actions:
        raise ValueError("Transition intent requires a non-empty actions list")
    normalized: list[dict[str, Any]] = []
    for row in actions:
        if not isinstance(row, dict) or set(row) - ACTION_FIELDS:
            raise ValueError("Transition action has unsupported fields")
        if row.get("action") != "set_lifecycle":
            raise ValueError("Transition action must be set_lifecycle")
        artifact_type = row.get("artifact_type")
        status = row.get("status")
        identity = row.get("identity", "auto")
        if not isinstance(artifact_type, str) or not artifact_type:
            raise ValueError("Transition action requires artifact_type")
        if status not in LIFECYCLE_STATUSES:
            raise ValueError("Transition action has an invalid lifecycle status")
        if identity not in IDENTITIES:
            raise ValueError("Transition action identity is invalid")
        note = row.get("note")
        if note is not None and (not isinstance(note, str) or not note):
            raise ValueError("Transition action note must be non-empty text")
        normalized.append(
            {
                "action": "set_lifecycle",
                "artifact_ref": row.get("artifact_ref"),
                "artifact_type": artifact_type,
                "identity": identity,
                "status": status,
                "relationships": _validate_relationships(row.get("relationships")),
                "note": note,
            }
        )
    return normalized


def _revision(root: Path, expected: Any) -> tuple[list[dict[str, Any]], str | None]:
    workspace_path(root, ".task/index.jsonl")
    events, observed = load_events_read_only(root)
    if expected == "current":
        return events, observed
    valid = expected is None or (
        isinstance(expected, str)
        and len(expected) == 64
        and all(character in "0123456789abcdef" for character in expected)
    )
    if not valid:
        raise ValueError("expected_index_revision must be 'current', null, or SHA-256")
    if expected != observed:
        raise ValueError("Task-state index revision changed; recompile_required")
    return events, observed


def _selector(ref: str, artifact_type: str, identity: str) -> tuple[str, str, str]:
    return ref, artifact_type, identity


def _resolve_target(
    relationship: dict[str, str],
    bindings: dict[tuple[str, str, str], dict[str, Any]],
    state: dict[str, dict[str, Any]],
) -> str:
    ref = relationship["target_ref"]
    artifact_type = relationship["target_type"]
    identity = relationship["target_identity"]
    candidates = [
        binding
        for (bound_ref, bound_type, bound_identity), binding in bindings.items()
        if bound_ref == ref
        and (not artifact_type or bound_type == artifact_type)
        and (identity == "auto" or bound_identity == identity)
    ]
    if len(candidates) == 1:
        return str(candidates[0]["artifact_id"])
    if len(candidates) > 1:
        raise ValueError(f"Relationship target is ambiguous: {ref}")
    current = [
        item_id
        for item_id, item in state.items()
        if item.get("path") == ref
        and (not artifact_type or item.get("type") == artifact_type)
        and item.get("status") not in NON_ACTIVE_STATUSES
    ]
    if len(current) != 1 or identity == "new":
        raise ValueError(f"Relationship target cannot be resolved exactly: {ref}")
    return current[0]


def compile_transition_intent(
    root: Path, intent: dict[str, Any], *, at: str
) -> dict[str, Any]:
    """Compile an exact, zero-write event request from semantic lifecycle actions."""

    root = root.resolve()
    timestamp, parsed_timestamp = _timestamp(at)
    actions = _validated_actions(intent)
    existing, observed_revision = _revision(
        root, intent.get("expected_index_revision")
    )
    state = merge_state(existing)
    occupied = set(state)
    bindings: dict[tuple[str, str, str], dict[str, Any]] = {}
    normalized_actions: list[dict[str, Any]] = []
    for row in actions:
        ref, path = _artifact_file(root, row["artifact_ref"])
        before_digest = sha256_file(path)
        artifact_type = row["artifact_type"]
        matches = _current_matches(state, ref, artifact_type)
        if len(matches) > 1:
            raise ValueError(f"Current artifact identity is not unique: {ref}")
        identity = row["identity"]
        if identity == "auto":
            identity = "current" if len(matches) == 1 else "new"
        if identity == "current":
            if len(matches) != 1:
                raise ValueError(f"Current artifact identity is not unique: {ref}")
            artifact_id, current = matches[0]
            title = str(current.get("title") or read_title(path))
            fields: dict[str, Any] = {}
        else:
            title = read_title(path)
            embedded_id, fields = _embedded_id(path, artifact_type)
            artifact_id = embedded_id or _generated_id(
                artifact_type, title, parsed_timestamp, occupied
            )
            prior = state.get(artifact_id)
            reactivation = bool(
                prior
                and prior.get("type") == artifact_type
                and prior.get("path") == ref
                and prior.get("status") in NON_ACTIVE_STATUSES
            )
            if prior and not reactivation:
                raise ValueError("Derived artifact identity is already active or bound elsewhere")
            if embedded_id and artifact_id in occupied and not reactivation:
                raise ValueError("Derived artifact identity is duplicated in this intent")
        _verified_ref, verified_path = _artifact_file(root, ref)
        content_sha256 = sha256_file(verified_path)
        if content_sha256 != before_digest:
            raise ValueError(f"Transition artifact changed during compilation: {ref}")
        key = _selector(ref, artifact_type, identity)
        if key in bindings:
            raise ValueError("Transition intent has duplicate artifact selectors")
        occupied.add(artifact_id)
        binding = {
            "artifact_ref": ref,
            "artifact_type": artifact_type,
            "identity": identity,
            "artifact_id": artifact_id,
            "content_sha256": content_sha256,
        }
        bindings[key] = binding
        normalized_actions.append(
            {**row, "artifact_ref": ref, "identity": identity, "title": title,
             "fields": fields, "binding": binding}
        )

    events: list[dict[str, Any]] = []
    for row in normalized_actions:
        binding = row["binding"]
        links = [
            {
                "rel": relationship["rel"],
                "id": _resolve_target(relationship, bindings, state),
            }
            for relationship in row["relationships"]
        ]
        event: dict[str, Any] = {
            "event": "upsert",
            "id": binding["artifact_id"],
            "status": row["status"],
        }
        if row["identity"] == "new":
            event.update(
                {
                    "type": row["artifact_type"],
                    "path": row["artifact_ref"],
                    "title": row["title"],
                    "content_sha256": binding["content_sha256"],
                }
            )
            if row["fields"]:
                event["fields"] = row["fields"]
        if links:
            event["links"] = links
        if row["note"]:
            event["note"] = row["note"]
        events.append(event)

    request = {
        "schema_version": 1,
        "updated_at": timestamp,
        "render": True,
        "events": events,
    }
    intent_sha256 = hashlib.sha256(canonical_bytes(intent)).hexdigest()
    body = {
        "schema_version": COMPILATION_SCHEMA_VERSION,
        "result_kind": COMPILATION_KIND,
        "intent_sha256": intent_sha256,
        "index_revision": {
            "path": jsonl_path(root).relative_to(root).as_posix(),
            "sha256": observed_revision,
            "event_count": len(existing),
        },
        "artifact_bindings": sorted(
            bindings.values(),
            key=lambda value: (
                value["artifact_ref"], value["artifact_type"], value["identity"]
            ),
        ),
        "request": request,
        "request_sha256": hashlib.sha256(canonical_bytes(request)).hexdigest(),
    }
    return {
        **body,
        "compilation_sha256": hashlib.sha256(canonical_bytes(body)).hexdigest(),
    }


def verify_transition_compilation(
    root: Path, compilation: dict[str, Any]
) -> None:
    """Reopen every compiler binding before a plan consumes its request."""

    root = root.resolve()
    revision = compilation.get("index_revision")
    if not isinstance(revision, dict):
        raise ValueError("Transition compilation lacks an index revision")
    workspace_path(root, ".task/index.jsonl")
    _events, observed_revision = load_events_read_only(root)
    if revision.get("sha256") != observed_revision:
        raise ValueError("Task-state index revision changed; recompile_required")
    bindings = compilation.get("artifact_bindings")
    if not isinstance(bindings, list) or not bindings:
        raise ValueError("Transition compilation lacks artifact bindings")
    for binding in bindings:
        if not isinstance(binding, dict):
            raise ValueError("Transition compilation artifact binding is malformed")
        ref, path = _artifact_file(root, binding.get("artifact_ref"))
        if sha256_file(path) != binding.get("content_sha256"):
            raise ValueError(f"Transition artifact changed; recompile_required: {ref}")


__all__ = (
    "COMPILATION_KIND",
    "compile_transition_intent",
    "load_transition_intent",
    "verify_transition_compilation",
)
