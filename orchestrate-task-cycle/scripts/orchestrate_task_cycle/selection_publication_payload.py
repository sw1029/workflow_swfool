"""Task payload identity and immutable blob storage for selection publication."""
from __future__ import annotations

from pathlib import Path
import re
from typing import Any

from .selection_decision_store import read_bound_bytes
from .selection_publication_plan import MAX_TARGET_BYTES, OPAQUE_ID
from .selection_publication_store import (
    _blob_path,
    _sha256_bytes,
    _write_once_with_status,
)


TASK_ID_LINE = re.compile(
    r"(?m)^\s*-\s*Task ID:\s*(?:`([^`\r\n]+)`|([^\s`\r\n]+))\s*$"
)


def task_id(payload: bytes) -> str:
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("selection task source must be UTF-8 Markdown") from exc
    matches = TASK_ID_LINE.findall(text)
    identifiers = [left or right for left, right in matches]
    if len(identifiers) != 1 or not OPAQUE_ID.fullmatch(identifiers[0]):
        raise ValueError("selection task source requires exactly one bounded Task ID")
    return identifiers[0]


def persist_blob(
    root: Path,
    payload: bytes,
    *,
    producer_capability: object,
) -> tuple[Path, str, bool]:
    digest = _sha256_bytes(payload)
    path = _blob_path(root, digest)
    persisted, created = _write_once_with_status(
        path,
        payload,
        "selection publication task blob",
        producer_capability=producer_capability,
    )
    if persisted != digest:
        raise ValueError("selection publication task blob digest drifted")
    return path, persisted, created


def payload_for_target(root: Path, target: dict[str, Any]) -> bytes:
    binding = {
        "ref": target["payload_ref"],
        "sha256": target["payload_sha256"],
    }
    _, payload = read_bound_bytes(root, binding, "selection publication task blob")
    if len(payload) != target["payload_size"] or len(payload) > MAX_TARGET_BYTES:
        raise ValueError("selection publication task blob size is inconsistent")
    return payload


__all__ = ("payload_for_target", "persist_blob", "task_id")
