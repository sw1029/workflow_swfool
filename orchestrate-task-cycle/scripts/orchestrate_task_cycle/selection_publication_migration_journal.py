"""Canonical WAL, completion, and visibility checks for storage-v4 migration."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .selection_publication_gc_fs import write_once_relative
from .selection_publication_producer_capability import (
    _SELECTION_PUBLICATION_PRODUCER_CAPABILITY,
)
from .selection_publication_migration_contract import (
    MAX_MIGRATION_JOURNAL_BYTES,
)
from .selection_publication_state import STORAGE_SCHEMA_VERSION
from .selection_publication_store import (
    SHA256,
    _canonical_json,
    _migration_path,
    _sha256_bytes,
)


MIGRATION_PREPARE_KEYS = {
    "schema_version",
    "kind",
    "storage_schema_version",
    "inventory",
    "intent_indexes",
    "state",
    "limits",
    "prepare_content_sha256",
}
MIGRATION_COMPLETE_KEYS = {
    "schema_version",
    "kind",
    "storage_schema_version",
    "migration_prepare",
    "state",
    "receipt_count",
    "pending_count",
    "intent_index_count",
    "visibility_rule",
    "completion_content_sha256",
}


def migration_binding(root: Path, path: Path, digest: str) -> dict[str, str]:
    return {"ref": path.relative_to(root).as_posix(), "sha256": digest}


def content_sha256(value: dict[str, Any], field: str) -> str:
    body = {key: item for key, item in value.items() if key != field}
    return _sha256_bytes(_canonical_json(body))


def read_canonical(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    if path.is_symlink():
        raise ValueError(f"{label} cannot be a symlink")
    try:
        observed = path.stat()
        if observed.st_size > MAX_MIGRATION_JOURNAL_BYTES:
            raise ValueError(f"{label} exceeds migration journal bound")
        payload = path.read_bytes()
        value = json.loads(payload)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is unreadable") from exc
    if (
        not isinstance(value, dict)
        or len(payload) != observed.st_size
        or payload != _canonical_json(value)
    ):
        raise ValueError(f"{label} is not canonical")
    return value, payload


def validate_prepare(value: dict[str, Any]) -> None:
    if (
        set(value) != MIGRATION_PREPARE_KEYS
        or value.get("schema_version") != 1
        or value.get("kind") != "selection_publication_storage_v4_migration_prepare"
        or value.get("storage_schema_version") != STORAGE_SCHEMA_VERSION
        or value.get("prepare_content_sha256")
        != content_sha256(value, "prepare_content_sha256")
        or not isinstance(value.get("inventory"), dict)
        or not isinstance(value.get("intent_indexes"), list)
        or not isinstance(value.get("state"), dict)
        or not isinstance(value.get("limits"), dict)
    ):
        raise ValueError("selection-publication migration prepare is invalid")


def validate_complete(value: dict[str, Any]) -> None:
    if (
        set(value) != MIGRATION_COMPLETE_KEYS
        or value.get("schema_version") != 1
        or value.get("kind") != "selection_publication_storage_v4_migration_complete"
        or value.get("storage_schema_version") != STORAGE_SCHEMA_VERSION
        or value.get("visibility_rule") != "indexes_then_state_then_completion_receipt"
        or value.get("completion_content_sha256")
        != content_sha256(value, "completion_content_sha256")
    ):
        raise ValueError("selection-publication migration completion is invalid")


def archive_completed_generation(
    root: Path, prepare_path: Path, complete_path: Path
) -> bool:
    """Retain an exact prior generation before replacing current WAL pointers."""

    if not prepare_path.is_file() or not complete_path.is_file():
        return False
    try:
        prepare, prepare_payload = read_canonical(
            prepare_path, "selection-publication prior migration prepare"
        )
        complete, complete_payload = read_canonical(
            complete_path, "selection-publication prior migration completion"
        )
        validate_prepare(prepare)
        validate_complete(complete)
    except ValueError:
        return False
    prepare_sha = _sha256_bytes(prepare_payload)
    if complete.get("migration_prepare") != migration_binding(
        root, prepare_path, prepare_sha
    ):
        return False
    generation = _sha256_bytes(complete_payload)
    base = (
        Path(".task/selection_publication/migrations/storage-v4/history") / generation
    )
    write_once_relative(
        root,
        (base / "prepare.json").as_posix(),
        prepare_payload,
        "selection-publication historical migration prepare",
        producer_capability=_SELECTION_PUBLICATION_PRODUCER_CAPABILITY,
    )
    write_once_relative(
        root,
        (base / "complete.json").as_posix(),
        complete_payload,
        "selection-publication historical migration completion",
        producer_capability=_SELECTION_PUBLICATION_PRODUCER_CAPABILITY,
    )
    return True


def validate_migration_visibility(
    root: Path, state: dict[str, Any]
) -> dict[str, Any] | None:
    """Require an exact completed migration generation before state use.

    The completion seals the migration-time state.  A later compact state is
    allowed to advance through the standard, independently validated
    publication writers; the historical completion is not a live-state CAS.
    """

    prepare_path = _migration_path(root, "prepare")
    complete_path = _migration_path(root, "complete")
    prepare_exists = prepare_path.exists() or prepare_path.is_symlink()
    complete_exists = complete_path.exists() or complete_path.is_symlink()
    if not prepare_exists and not complete_exists:
        return None
    if not prepare_exists or not complete_exists:
        raise ValueError(
            "selection publication state migration recovery required; "
            "completion receipt is absent"
        )
    prepare, prepare_payload = read_canonical(
        prepare_path, "selection-publication migration prepare"
    )
    complete, _complete_payload = read_canonical(
        complete_path, "selection-publication migration completion"
    )
    validate_prepare(prepare)
    validate_complete(complete)
    state_path = root / ".task/selection_publication/state.json"
    migration_state = prepare.get("state")
    if (
        not isinstance(migration_state, dict)
        or set(migration_state) != {"ref", "sha256"}
        or migration_state.get("ref") != state_path.relative_to(root).as_posix()
        or not isinstance(migration_state.get("sha256"), str)
        or not SHA256.fullmatch(migration_state["sha256"])
    ):
        raise ValueError("selection publication migration state binding is invalid")
    if (
        complete.get("migration_prepare")
        != migration_binding(root, prepare_path, _sha256_bytes(prepare_payload))
        or migration_state != complete.get("state")
        or complete.get("receipt_count") != prepare["inventory"].get("receipt_count")
        or complete.get("pending_count") != prepare["inventory"].get("pending_count")
        or complete.get("intent_index_count") != len(prepare["intent_indexes"])
    ):
        raise ValueError(
            "selection publication migration completion diverges from its WAL"
        )
    return complete


__all__ = (
    "archive_completed_generation",
    "content_sha256",
    "migration_binding",
    "validate_complete",
    "validate_migration_visibility",
    "validate_prepare",
)
