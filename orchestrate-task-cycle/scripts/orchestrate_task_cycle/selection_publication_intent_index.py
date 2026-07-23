"""Immutable O(1) lookup records for selection-publication intents."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .selection_publication_store import (
    SHA256,
    TRANSACTION_ID,
    _canonical_json,
    _intent_index_path,
    _prepare_path,
    _receipt_path,
    _sha256_bytes,
    _sha256_file,
    _write_once,
)
from .selection_publication_producer_capability import (
    _SELECTION_PUBLICATION_PRODUCER_CAPABILITY,
)


INDEX_SCHEMA_VERSION = 1
BINDING_KEYS = {"ref", "sha256"}
PREPARE_KEYS = {
    "schema_version",
    "kind",
    "intent_sha256",
    "transaction_id",
    "prepare",
    "index_content_sha256",
}
COMMIT_KEYS = PREPARE_KEYS | {"receipt"}


def _binding(root: Path, path: Path, digest: str) -> dict[str, str]:
    return {"ref": path.relative_to(root).as_posix(), "sha256": digest}


def _content(value: dict[str, Any]) -> str:
    body = {key: item for key, item in value.items() if key != "index_content_sha256"}
    return _sha256_bytes(_canonical_json(body))


def _read(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is unreadable") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def _validate_binding(root: Path, value: Any, label: str) -> dict[str, str]:
    if not isinstance(value, dict) or set(value) != BINDING_KEYS:
        raise ValueError(f"{label} binding is invalid")
    ref = value.get("ref")
    digest = value.get("sha256")
    if not isinstance(ref, str) or not isinstance(digest, str) or not SHA256.fullmatch(digest):
        raise ValueError(f"{label} binding is invalid")
    path = root / ref
    try:
        path.resolve(strict=False).relative_to(root)
    except ValueError as exc:
        raise ValueError(f"{label} escapes the workspace") from exc
    if path.is_symlink() or _sha256_file(path) != digest:
        raise ValueError(f"{label} binding has drifted")
    return {"ref": ref, "sha256": digest}


def _validate(
    root: Path, value: dict[str, Any], intent_sha256: str, *, committed: bool
) -> dict[str, Any]:
    expected = COMMIT_KEYS if committed else PREPARE_KEYS
    if set(value) != expected:
        raise ValueError("selection publication intent index fields are invalid")
    transaction_id = value.get("transaction_id")
    if (
        value.get("schema_version") != INDEX_SCHEMA_VERSION
        or value.get("kind")
        != (
            "selection_publication_intent_commit_index"
            if committed
            else "selection_publication_intent_prepare_index"
        )
        or value.get("intent_sha256") != intent_sha256
        or not isinstance(transaction_id, str)
        or not TRANSACTION_ID.fullmatch(transaction_id)
        or value.get("index_content_sha256") != _content(value)
    ):
        raise ValueError("selection publication intent index integrity failed")
    prepare = _validate_binding(
        root, value.get("prepare"), "selection publication prepare"
    )
    expected_prepare_ref = _prepare_path(root, transaction_id).relative_to(root).as_posix()
    if prepare["ref"] != expected_prepare_ref:
        raise ValueError("selection publication intent index prepare path differs")
    if committed:
        receipt = _validate_binding(
            root, value.get("receipt"), "selection publication receipt"
        )
        expected_receipt_ref = _receipt_path(root, transaction_id).relative_to(root).as_posix()
        if receipt["ref"] != expected_receipt_ref:
            raise ValueError("selection publication intent index receipt path differs")
    return value


def load_intent_index(
    root: Path, intent_sha256: str, *, committed: bool
) -> dict[str, Any] | None:
    path = _intent_index_path(
        root, intent_sha256, "commit" if committed else "prepare"
    )
    if not path.exists():
        return None
    return _validate(
        root,
        _read(path, "selection publication intent index"),
        intent_sha256,
        committed=committed,
    )


def prepare_index_value(
    root: Path,
    intent_sha256: str,
    transaction_id: str,
    prepare_path: Path,
    prepare_sha256: str,
) -> dict[str, Any]:
    body = {
        "schema_version": INDEX_SCHEMA_VERSION,
        "kind": "selection_publication_intent_prepare_index",
        "intent_sha256": intent_sha256,
        "transaction_id": transaction_id,
        "prepare": _binding(root, prepare_path, prepare_sha256),
    }
    return {**body, "index_content_sha256": _content(body)}


def write_prepare_index(
    root: Path,
    intent_sha256: str,
    transaction_id: str,
    prepare_path: Path,
    prepare_sha256: str,
) -> dict[str, Any]:
    value = prepare_index_value(
        root,
        intent_sha256,
        transaction_id,
        prepare_path,
        prepare_sha256,
    )
    _write_once(
        _intent_index_path(root, intent_sha256, "prepare"),
        _canonical_json(value),
        "selection-publication intent prepare index",
        producer_capability=_SELECTION_PUBLICATION_PRODUCER_CAPABILITY,
    )
    return value


def commit_index_value(
    root: Path,
    intent_sha256: str,
    transaction_id: str,
    prepare_path: Path,
    prepare_sha256: str,
    receipt_path: Path,
    receipt_sha256: str,
) -> dict[str, Any]:
    body = {
        "schema_version": INDEX_SCHEMA_VERSION,
        "kind": "selection_publication_intent_commit_index",
        "intent_sha256": intent_sha256,
        "transaction_id": transaction_id,
        "prepare": _binding(root, prepare_path, prepare_sha256),
        "receipt": _binding(root, receipt_path, receipt_sha256),
    }
    return {**body, "index_content_sha256": _content(body)}


def write_commit_index(
    root: Path,
    intent_sha256: str,
    transaction_id: str,
    prepare_path: Path,
    prepare_sha256: str,
    receipt_path: Path,
    receipt_sha256: str,
) -> dict[str, Any]:
    value = commit_index_value(
        root,
        intent_sha256,
        transaction_id,
        prepare_path,
        prepare_sha256,
        receipt_path,
        receipt_sha256,
    )
    _write_once(
        _intent_index_path(root, intent_sha256, "commit"),
        _canonical_json(value),
        "selection-publication intent commit index",
        producer_capability=_SELECTION_PUBLICATION_PRODUCER_CAPABILITY,
    )
    return value


__all__ = (
    "commit_index_value",
    "load_intent_index",
    "prepare_index_value",
    "write_commit_index",
    "write_prepare_index",
)
