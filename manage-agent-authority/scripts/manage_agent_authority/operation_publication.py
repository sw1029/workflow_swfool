"""Immutable publication for non-authoritative operation compilations."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .canonical import (
    resolve_workspace_path,
    sha256_bytes,
    write_immutable_json,
)
from .operation_compiler import validate_compilation
from .stable_store import read_regular


COMPILATION_ROOT = Path(".task/authorization/operation_compilations")
MAX_COMPILATION_BYTES = 2 * 1024 * 1024


def publish_compilation(root: Path, value: Any) -> dict[str, str]:
    """Publish validated preparation bytes without issuing authority artifacts."""

    root = root.resolve()
    compilation = validate_compilation(value)
    fingerprint = compilation["compilation_fingerprint"]
    target = root / COMPILATION_ROOT / f"operation_compilation-{fingerprint}.json"
    digest = write_immutable_json(target, compilation, "operation compilation")
    return {
        "ref": target.relative_to(root).as_posix(),
        "sha256": digest,
        "compilation_fingerprint": fingerprint,
    }


def load_published_compilation(
    root: Path, binding: Any
) -> tuple[dict[str, str], dict[str, Any]]:
    """Reopen a compact binding only from the producer-owned compilation CAS."""

    if not isinstance(binding, dict) or set(binding) not in (
        {"ref", "sha256"},
        {"ref", "sha256", "compilation_fingerprint"},
    ):
        raise SystemExit(
            "Published operation compilation binding must contain exact "
            "ref and sha256, with only the optional compilation_fingerprint."
        )
    root = root.resolve()
    path = resolve_workspace_path(
        root, binding["ref"], "published operation compilation.ref"
    )
    expected_parent = root / COMPILATION_ROOT
    if path.parent != expected_parent:
        raise SystemExit(
            "Published operation compilation is outside its producer-owned CAS."
        )
    payload = read_regular(
        path,
        label="published operation compilation",
        max_bytes=MAX_COMPILATION_BYTES,
    )
    assert payload is not None
    digest = sha256_bytes(payload)
    if digest != binding["sha256"]:
        raise SystemExit(
            "Published operation compilation SHA-256 does not match its "
            "immutable artifact."
        )
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SystemExit(
            "Published operation compilation is not readable JSON."
        ) from exc
    compilation = validate_compilation(value)
    fingerprint = compilation["compilation_fingerprint"]
    normalized = {
        "ref": path.relative_to(root).as_posix(),
        "sha256": digest,
        "compilation_fingerprint": fingerprint,
    }
    if (
        path.name != f"operation_compilation-{fingerprint}.json"
        or binding["ref"] != normalized["ref"]
        or binding["sha256"] != normalized["sha256"]
        or (
            "compilation_fingerprint" in binding
            and binding["compilation_fingerprint"] != fingerprint
        )
    ):
        raise SystemExit(
            "Published operation compilation binding is not canonical."
        )
    return normalized, compilation


__all__ = [
    "COMPILATION_ROOT",
    "load_published_compilation",
    "publish_compilation",
]
