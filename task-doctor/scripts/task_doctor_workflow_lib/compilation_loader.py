"""Load inline or published non-authoritative operation compilations."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from manage_agent_authority.operation_compiler import (
    compilation_inputs,
    validate_compilation,
)

from .common import HEX64, WorkflowError, read_json, require, workspace_file


def _publication(root: Path, value: dict[str, Any]) -> tuple[Any, str | None]:
    keys = set(value)
    if keys not in (
        {"ref", "sha256"},
        {"ref", "sha256", "compilation_fingerprint"},
    ):
        return value, None
    ref = value["ref"]
    digest = value["sha256"]
    require(isinstance(ref, str) and bool(ref), "invalid_intent",
            "compiled_operation.ref is required")
    require(isinstance(digest, str) and HEX64.fullmatch(digest) is not None,
            "invalid_intent", "compiled_operation.sha256 must be SHA-256")
    fingerprint = value.get("compilation_fingerprint")
    require(fingerprint is None or (
                isinstance(fingerprint, str) and HEX64.fullmatch(fingerprint) is not None
            ), "invalid_intent",
            "compiled_operation.compilation_fingerprint must be SHA-256")
    path = workspace_file(root, ref, digest, "compiled_operation")
    return read_json(path, "invalid_intent"), fingerprint


def load_compilation(
    root: Path, value: Any, *, skills_root: Path,
) -> dict[str, Any]:
    """Validate a compilation and its optional immutable publication receipt."""

    publication_fingerprint = None
    if isinstance(value, dict):
        value, publication_fingerprint = _publication(root, value)
    try:
        compilation = validate_compilation(value)
        compilation_inputs(root, compilation, skills_root=skills_root)
        require(
            publication_fingerprint is None
            or compilation["compilation_fingerprint"] == publication_fingerprint,
            "invalid_intent",
            "compiled operation publication fingerprint mismatch",
        )
        return compilation
    except (SystemExit, KeyError, TypeError, ValueError) as error:
        raise WorkflowError(
            "invalid_intent", f"compiled operation is invalid: {error}"
        ) from error


__all__ = ["load_compilation"]
