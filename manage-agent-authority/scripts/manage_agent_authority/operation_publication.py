"""Immutable publication for non-authoritative operation compilations."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .canonical import write_immutable_json
from .operation_compiler import validate_compilation


COMPILATION_ROOT = Path(".task/authorization/operation_compilations")


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


__all__ = ["COMPILATION_ROOT", "publish_compilation"]
