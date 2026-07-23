"""Content-addressed artifact helpers for selection authority re-entry."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from .selection_decision_store import canonical_bytes, normalize_binding
from .selection_publication import publication_status
from .selection_publication_gc_fs import read_relative
from .selection_publication_state import load_state
from .selection_publication_store import _bounded_payload


MAX_REENTRY_ARTIFACT_BYTES = 1024 * 1024


def _binding_for_payload(
    category: str, payload: bytes, *, suffix: str
) -> dict[str, str]:
    digest = hashlib.sha256(payload).hexdigest()
    return {
        "ref": f".task/selection_reentry/{category}/sha256/{digest}{suffix}",
        "sha256": digest,
    }


def _artifact(
    category: str,
    value: dict[str, Any] | bytes,
    *,
    suffix: str = ".json",
) -> dict[str, Any]:
    payload = value if isinstance(value, bytes) else canonical_bytes(value)
    payload = _bounded_payload(
        payload,
        MAX_REENTRY_ARTIFACT_BYTES,
        f"selection authority reentry {category}",
    )
    return {
        "category": category,
        "binding": _binding_for_payload(category, payload, suffix=suffix),
        "payload": payload,
    }


def _current_publication_head(root: Path) -> dict[str, str]:
    status = publication_status(root)
    head = status.get("current_head")
    if (
        status.get("status") != "clear"
        or not isinstance(head, dict)
        or head.get("status") != "current"
        or head.get("head_count") != 1
        or not isinstance(head.get("head_transaction_id"), str)
    ):
        raise ValueError(
            "authority reentry requires one existing committed publication head"
        )
    state = load_state(root)
    state_head = state.get("head") if isinstance(state, dict) else None
    if (
        not isinstance(state_head, dict)
        or state_head.get("transaction_id") != head["head_transaction_id"]
    ):
        raise ValueError(
            "authority reentry publication status differs from its exact state head"
        )
    binding = normalize_binding(
        state_head.get("receipt"),
        "authority reentry publication head",
    )
    expected_ref = (
        f".task/selection_publication/receipts/{head['head_transaction_id']}.json"
    )
    if binding["ref"] != expected_ref:
        raise ValueError(
            "authority reentry publication head is outside its exact receipt path"
        )
    payload = read_relative(
        root,
        binding["ref"],
        "authority reentry publication head",
        max_bytes=MAX_REENTRY_ARTIFACT_BYTES,
    )
    assert payload is not None
    if hashlib.sha256(payload).hexdigest() != binding["sha256"]:
        raise ValueError(
            "authority reentry publication head differs from its state binding"
        )
    return binding


def _validate_artifact_binding(
    binding: dict[str, str],
    *,
    category: str,
) -> str:
    expected_prefix = f".task/selection_reentry/{category}/sha256/"
    ref = binding.get("ref")
    digest = binding.get("sha256")
    if (
        not isinstance(ref, str)
        or not ref.startswith(expected_prefix)
        or not isinstance(digest, str)
        or len(digest) != 64
    ):
        raise ValueError("authority reentry output binding is outside its CAS")
    return ref


__all__ = ()
