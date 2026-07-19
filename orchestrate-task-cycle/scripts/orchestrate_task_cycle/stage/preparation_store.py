"""Immutable content-addressed storage for compiled stage preparations."""

from __future__ import annotations

import json
import hashlib
import re
from pathlib import Path
from typing import Any

from ..cycle_ledger import cycle_dir, immutable_write_bytes
from ..ledger.support import rel_path
from .contracts import canonical_bytes, canonical_sha256, validate_preparation
from .specs import TARGET_COMPILE_SPECS


MAX_PREPARATION_BYTES = 2 * 1024 * 1024
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
PUBLICATION_OPERATION = {
    "skill_id": "orchestrate-task-cycle",
    "operation_id": "publish_compiled_stage_projection",
    "operation_version": "1",
    "authority_applicability": "none",
}


def preparation_path(root: Path, cycle_id: str, target: str, digest: str) -> Path:
    if target not in TARGET_COMPILE_SPECS:
        raise ValueError(f"unsupported stage target: {target}")
    if not SHA256_PATTERN.fullmatch(digest):
        raise ValueError("preparation digest must be a lowercase SHA-256 value")
    return cycle_dir(root, cycle_id) / "packets" / f"preparation-{target}-{digest}.json"


def publish_preparation(
    root: str | Path, preparation: dict[str, Any]
) -> dict[str, Any]:
    workspace = Path(root).resolve(strict=True)
    validated = validate_preparation(preparation)
    payload = canonical_bytes(validated) + b"\n"
    if len(payload) > MAX_PREPARATION_BYTES:
        raise ValueError(
            f"preparation_artifact_budget_exceeded: {len(payload)} > "
            f"{MAX_PREPARATION_BYTES} bytes"
        )
    body_digest = canonical_sha256(validated)
    digest = hashlib.sha256(payload).hexdigest()
    path = preparation_path(
        workspace,
        str(validated["cycle_id"]),
        str(validated["target"]),
        digest,
    )
    duplicate = path.exists()
    immutable_write_bytes(path, payload)
    next_action = validated.get("next_action") or {}
    blocked = next_action.get("kind") == "stop"
    return {
        "status": "block" if blocked else "ok",
        "stop_reason": next_action.get("reason") if blocked else None,
        "preparation_id": validated["preparation_id"],
        "cycle_id": validated["cycle_id"],
        "target": validated["target"],
        "state_fingerprint": validated["state_fingerprint"],
        "preparation_ref": rel_path(workspace, path),
        "preparation_sha256": digest,
        "preparation_body_sha256": body_digest,
        "preparation_bytes": len(payload),
        "compiler_metrics": validated.get("compiler_metrics") or {},
        "publication_operation": dict(PUBLICATION_OPERATION),
        "applied": True,
        "artifact_duplicate": duplicate,
    }


def _resolved_ref(root: Path, ref: str) -> Path:
    relative = Path(str(ref))
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("preparation_ref must be a workspace-relative path")
    candidate = root
    for part in relative.parts:
        candidate = candidate / part
        if candidate.is_symlink():
            raise ValueError("preparation_ref must not traverse a symlink")
    path = candidate.resolve(strict=True)
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ValueError("preparation_ref escapes the workspace") from exc
    return path


def load_published_preparation(
    root: str | Path,
    ref: str,
    expected_sha256: str,
) -> dict[str, Any]:
    workspace = Path(root).resolve(strict=True)
    if not SHA256_PATTERN.fullmatch(str(expected_sha256)):
        raise ValueError("preparation_sha256 must be a lowercase SHA-256 value")
    path = _resolved_ref(workspace, ref)
    if not path.is_file():
        raise ValueError("preparation_ref must identify a regular file")
    if path.stat().st_size > MAX_PREPARATION_BYTES:
        raise ValueError("preparation_artifact_budget_exceeded")
    payload = path.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    if digest != expected_sha256:
        raise ValueError("published preparation file digest does not match exact input")
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("published preparation is not valid UTF-8 JSON") from exc
    validated = validate_preparation(value)
    if payload != canonical_bytes(validated) + b"\n":
        raise ValueError("published preparation is not canonical immutable JSON")
    expected_path = preparation_path(
        workspace,
        str(validated["cycle_id"]),
        str(validated["target"]),
        expected_sha256,
    ).resolve(strict=True)
    expected_ref = expected_path.relative_to(workspace).as_posix()
    if str(ref) != expected_ref or path != expected_path:
        raise ValueError("preparation_ref does not match its content address")
    return validated


__all__ = [
    "MAX_PREPARATION_BYTES",
    "PUBLICATION_OPERATION",
    "load_published_preparation",
    "preparation_path",
    "publish_preparation",
]
