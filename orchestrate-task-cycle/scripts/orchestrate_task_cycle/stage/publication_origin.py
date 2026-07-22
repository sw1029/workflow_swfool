"""Crash-recoverable write-ahead provenance for stage publication objects."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from ..cycle_ledger import cycle_dir, immutable_write_bytes, ledger_lock
from ..ledger.support import rel_path
from .contracts import canonical_bytes


INTENT_KIND = "orchestrate_stage_publication_origin_intent"
INTENT_SCHEMA_VERSION = 1
MAX_INTENT_BYTES = 16 * 1024
ORIGIN_ID_PATTERN = re.compile(r"stageprep-[0-9a-f]{32}")
OBJECT_KINDS = frozenset({"context", "work_order", "machine_input", "preparation"})
_BINDING_FIELDS = ("ref", "sha256", "size_bytes")


def _empty_metrics() -> dict[str, int]:
    return {
        "cas_newly_written_bytes": 0,
        "cas_reused_bytes": 0,
        "files_written_count": 0,
    }


def _merge_metrics(*values: dict[str, Any]) -> dict[str, int]:
    merged = _empty_metrics()
    for value in values:
        for field in merged:
            item = value.get(field, 0)
            if isinstance(item, bool) or not isinstance(item, int) or item < 0:
                raise ValueError("publication origin metrics are invalid")
            merged[field] += item
    return merged


def _write_metrics(size_bytes: int, mutation_performed: bool) -> dict[str, int]:
    return {
        "cas_newly_written_bytes": size_bytes if mutation_performed else 0,
        "cas_reused_bytes": 0 if mutation_performed else size_bytes,
        "files_written_count": 1 if mutation_performed else 0,
    }


def _normalized_binding(value: dict[str, Any]) -> dict[str, Any]:
    binding = {field: value.get(field) for field in _BINDING_FIELDS}
    if not isinstance(binding["ref"], str) or not binding["ref"]:
        raise ValueError("publication origin object ref is invalid")
    relative = Path(binding["ref"])
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("publication origin object ref must be workspace-relative")
    if not re.fullmatch(r"[0-9a-f]{64}", str(binding["sha256"] or "")):
        raise ValueError("publication origin object digest is invalid")
    size = binding["size_bytes"]
    if isinstance(size, bool) or not isinstance(size, int) or size < 1:
        raise ValueError("publication origin object size is invalid")
    return binding


def _validate_scope(cycle_id: str, origin_id: str, object_kind: str) -> None:
    if not cycle_id:
        raise ValueError("publication origin cycle_id is required")
    if not ORIGIN_ID_PATTERN.fullmatch(origin_id):
        raise ValueError("publication origin id is invalid")
    if object_kind not in OBJECT_KINDS:
        raise ValueError("publication origin object kind is invalid")


def intent_path(
    root: Path,
    cycle_id: str,
    origin_id: str,
    object_kind: str,
    object_sha256: str,
) -> Path:
    _validate_scope(cycle_id, origin_id, object_kind)
    if not re.fullmatch(r"[0-9a-f]{64}", object_sha256):
        raise ValueError("publication origin object digest is invalid")
    return (
        cycle_dir(root, cycle_id)
        / "compiler"
        / "publication-origin"
        / origin_id
        / f"{object_kind}-{object_sha256}.intent.json"
    )


def _intent_value(
    cycle_id: str,
    origin_id: str,
    object_kind: str,
    object_binding: dict[str, Any],
    classification: str,
) -> dict[str, Any]:
    if classification not in {"new", "reused"}:
        raise ValueError("publication origin classification is invalid")
    return {
        "schema_version": INTENT_SCHEMA_VERSION,
        "artifact_kind": INTENT_KIND,
        "cycle_id": cycle_id,
        "origin_id": origin_id,
        "object_kind": object_kind,
        "object_binding": _normalized_binding(object_binding),
        "origin_classification": classification,
    }


def _resolved_target(root: Path, target: Path) -> Path:
    candidate = target if target.is_absolute() else root / target
    try:
        relative = candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError("publication origin target escapes the workspace") from exc
    if ".." in relative.parts:
        raise ValueError("publication origin target escapes the workspace")
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError("publication origin target must not traverse a symlink")
    return candidate


def _target_status(target: Path, payload: bytes) -> bool:
    if target.exists():
        if not target.is_file() or target.is_symlink():
            raise ValueError("publication origin target must be a regular file")
        if target.read_bytes() != payload:
            raise ValueError("publication origin target content conflicts")
        return True
    return False


def _intent_binding(root: Path, path: Path, payload: bytes) -> dict[str, Any]:
    return {
        "ref": rel_path(root, path),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "size_bytes": len(payload),
    }


def _read_intent(path: Path) -> tuple[dict[str, Any], bytes]:
    if (
        path.is_symlink()
        or not path.is_file()
        or path.stat().st_size > MAX_INTENT_BYTES
    ):
        raise ValueError("publication origin intent is missing or oversized")
    payload = path.read_bytes()
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("publication origin intent is invalid JSON") from exc
    if not isinstance(value, dict) or payload != canonical_bytes(value) + b"\n":
        raise ValueError("publication origin intent is not canonical JSON")
    return value, payload


def load_origin_intent(
    root: Path,
    cycle_id: str,
    origin_id: str,
    object_kind: str,
    object_binding: dict[str, Any],
) -> dict[str, Any]:
    """Load and verify one immutable origin intent and its bound object."""

    binding = _normalized_binding(object_binding)
    path = intent_path(root, cycle_id, origin_id, object_kind, str(binding["sha256"]))
    value, payload = _read_intent(path)
    expected_keys = {
        "schema_version",
        "artifact_kind",
        "cycle_id",
        "origin_id",
        "object_kind",
        "object_binding",
        "origin_classification",
    }
    if set(value) != expected_keys or value != _intent_value(
        cycle_id,
        origin_id,
        object_kind,
        binding,
        str(value.get("origin_classification") or ""),
    ):
        raise ValueError("publication origin intent scope is invalid")
    target = _resolved_target(root, root / str(binding["ref"]))
    if not target.is_file() or target.is_symlink():
        raise ValueError("publication origin target is missing")
    if target.stat().st_size != binding["size_bytes"]:
        raise ValueError("publication origin target size differs")
    target_payload = target.read_bytes()
    if hashlib.sha256(target_payload).hexdigest() != binding["sha256"]:
        raise ValueError("publication origin target digest differs")
    intent_binding = _intent_binding(root, path, payload)
    target_new = value["origin_classification"] == "new"
    origin_metrics = _merge_metrics(
        _write_metrics(len(payload), True),
        _write_metrics(int(binding["size_bytes"]), target_new),
    )
    return {
        "intent": value,
        "intent_binding": intent_binding,
        "origin_metrics": origin_metrics,
    }


def publish_origin_object(
    root: Path,
    cycle_id: str,
    origin_id: str,
    object_kind: str,
    target: Path,
    payload: bytes,
) -> dict[str, Any]:
    """Write intent before object so retry preserves the original I/O class."""

    _validate_scope(cycle_id, origin_id, object_kind)
    target = _resolved_target(root, target)
    object_binding = {
        "ref": rel_path(root, target),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "size_bytes": len(payload),
    }
    path = intent_path(root, cycle_id, origin_id, object_kind, object_binding["sha256"])
    with ledger_lock(root, cycle_id, exclusive=True):
        intent_existed = path.exists()
        target_existed = _target_status(target, payload)
        if intent_existed:
            loaded, intent_payload = _read_intent(path)
            expected = _intent_value(
                cycle_id,
                origin_id,
                object_kind,
                object_binding,
                str(loaded.get("origin_classification") or ""),
            )
            if loaded != expected:
                raise ValueError("publication origin intent scope is invalid")
            classification = str(loaded["origin_classification"])
            if classification == "reused" and not target_existed:
                raise ValueError("reused publication origin target disappeared")
        else:
            classification = "reused" if target_existed else "new"
            intent_payload = (
                canonical_bytes(
                    _intent_value(
                        cycle_id,
                        origin_id,
                        object_kind,
                        object_binding,
                        classification,
                    )
                )
                + b"\n"
            )
        intent_mutation = immutable_write_bytes(path, intent_payload)
        if intent_existed and intent_mutation:
            raise RuntimeError("publication origin intent replay created a new file")
        target_mutation = immutable_write_bytes(target, payload)
        if classification == "reused" and target_mutation:
            raise RuntimeError(
                "reused publication origin unexpectedly created its target"
            )
        if not intent_existed and classification == "new" and not target_mutation:
            raise RuntimeError(
                "publication origin target raced with its write-ahead intent"
            )
    loaded = load_origin_intent(root, cycle_id, origin_id, object_kind, object_binding)
    return {
        **loaded,
        "object_binding": object_binding,
        "intent_write_receipt": {
            "write_attempted": True,
            "mutation_performed": intent_mutation,
            **_write_metrics(len(intent_payload), intent_mutation),
        },
        "target_write_receipt": {
            "write_attempted": True,
            "mutation_performed": target_mutation,
            **_write_metrics(len(payload), target_mutation),
        },
        "attempt_metrics": _merge_metrics(
            _write_metrics(len(intent_payload), intent_mutation),
            _write_metrics(len(payload), target_mutation),
        ),
    }


__all__ = [
    "INTENT_KIND",
    "load_origin_intent",
    "publish_origin_object",
]
