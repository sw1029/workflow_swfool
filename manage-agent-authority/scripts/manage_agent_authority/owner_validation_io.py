"""Bounded stable reads for authority-owned owner-validation receipts."""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any

from .canonical import resolve_workspace_path, sha256_bytes
from .stable_store import read_regular


MAX_OWNER_VALIDATION_RECEIPT_BYTES = 256 * 1024
MAX_REGISTERED_OWNER_RESULT_BYTES = 1024 * 1024
OWNER_VALIDATION_REF = re.compile(
    r"\.task/authorization/owner_validations/"
    r"owner-validation-([0-9a-f]{64})\.json"
)


def _binding(value: Any, label: str) -> dict[str, str]:
    if not isinstance(value, dict) or set(value) != {"ref", "sha256"}:
        raise SystemExit(f"{label} must be an exact ref/sha256 binding.")
    ref, digest = value.get("ref"), value.get("sha256")
    if (
        not isinstance(ref, str)
        or not ref
        or not isinstance(digest, str)
        or len(digest) != 64
        or any(character not in "0123456789abcdef" for character in digest)
    ):
        raise SystemExit(f"{label} binding is invalid.")
    return {"ref": ref, "sha256": digest}


def _read_bound_bytes(
    root: Path,
    binding: dict[str, str],
    label: str,
    *,
    max_bytes: int,
) -> tuple[dict[str, str], Path, bytes]:
    normalized = _binding(binding, label)
    path = resolve_workspace_path(root, normalized["ref"], f"{label}.ref")
    payload = read_regular(path, label=label, max_bytes=max_bytes)
    assert payload is not None
    if sha256_bytes(payload) != normalized["sha256"]:
        raise SystemExit(f"{label} SHA-256 does not match its artifact.")
    return normalized, path, payload


def _read_bound_json(
    root: Path,
    binding: dict[str, str],
    label: str,
    *,
    max_bytes: int,
) -> tuple[dict[str, str], Path, dict[str, Any]]:
    normalized, path, payload = _read_bound_bytes(
        root, binding, label, max_bytes=max_bytes
    )
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SystemExit(f"{label} is unreadable JSON.") from exc
    if not isinstance(value, dict):
        raise SystemExit(f"{label} is unreadable JSON.")
    return normalized, path, value


def read_bound_owner_validation_receipt(
    root: Path, binding: dict[str, str]
) -> tuple[Path, dict[str, Any]]:
    """Read one exact receipt once, with a strict acquisition-time size cap."""

    normalized = _binding(binding, "owner_validation")
    match = OWNER_VALIDATION_REF.fullmatch(normalized["ref"])
    if match is None:
        raise SystemExit("owner_validation is not at its canonical receipt path.")
    _, path, receipt = _read_bound_json(
        root,
        normalized,
        "owner_validation",
        max_bytes=MAX_OWNER_VALIDATION_RECEIPT_BYTES,
    )
    seal = receipt.get("receipt_sha256")
    if seal != match.group(1):
        raise SystemExit("owner_validation is not at its canonical receipt path.")
    return path, receipt


def preflight_registered_owner_result(
    root: Path, binding: dict[str, str]
) -> None:
    """Reject oversized or mismatched registered owner results before dispatch."""

    _read_bound_bytes(
        root,
        binding,
        "registered owner_result",
        max_bytes=MAX_REGISTERED_OWNER_RESULT_BYTES,
    )


__all__ = (
    "MAX_OWNER_VALIDATION_RECEIPT_BYTES",
    "MAX_REGISTERED_OWNER_RESULT_BYTES",
    "preflight_registered_owner_result",
    "read_bound_owner_validation_receipt",
)
