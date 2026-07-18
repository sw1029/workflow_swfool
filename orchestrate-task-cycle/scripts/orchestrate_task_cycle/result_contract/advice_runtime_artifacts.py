"""Safe cycle-local storage checks for advice runtime artifacts."""

from __future__ import annotations

import hashlib
import json
import stat
from pathlib import Path, PurePosixPath
from typing import Any


MAX_ARTIFACT_BYTES = 4 * 1024 * 1024
RUNTIME_ARTIFACT_STORE_KIND = "cycle_local_canonical_json"


def canonical_json_bytes(value: object) -> bytes:
    """Return the sole accepted byte representation for a runtime artifact."""
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def workspace_root(
    result: dict[str, Any],
    context: dict[str, Any] | None = None,
    explicit_root: str | Path | None = None,
) -> Path:
    values: tuple[object, ...] = (
        explicit_root,
        (context or {}).get("workspace_root"),
        (context or {}).get("workspace"),
        (context or {}).get("root"),
    )
    value = next(
        (
            item
            for item in values
            if isinstance(item, (str, Path)) and str(item).strip()
        ),
        ".",
    )
    return Path(value).resolve()


def decision_cycle_id(result: dict[str, Any]) -> str | None:
    analysis = result.get("improvement_analysis_manifest")
    manifest = (
        analysis.get("shared_evidence_manifest") if isinstance(analysis, dict) else None
    )
    identities = (
        manifest,
        result.get("decision_input_identity"),
        result.get("decision_artifact_ref"),
        result,
    )
    for identity in identities:
        if isinstance(identity, dict) and _safe_component(identity.get("cycle_id")):
            return str(identity["cycle_id"])
    return None


def cycle_artifact_ref(cycle_id: str, filename: str) -> str:
    if not _safe_component(cycle_id) or not _safe_filename(filename):
        raise ValueError("cycle artifact identifiers must be safe path components")
    return f".task/cycle/{cycle_id}/agent_receipts/{filename}"


def verify_cycle_artifact(
    root: Path,
    cycle_id: str,
    artifact_ref: object,
    expected_value: object,
) -> dict[str, Any] | None:
    """Verify one exact canonical JSON file without following symbolic links."""
    path = _artifact_path(root, cycle_id, artifact_ref)
    if path is None:
        return None
    expected = canonical_json_bytes(expected_value)
    if len(expected) > MAX_ARTIFACT_BYTES:
        return None
    try:
        with path.open("rb") as handle:
            observed = handle.read(MAX_ARTIFACT_BYTES + 1)
    except OSError:
        return None
    if len(observed) > MAX_ARTIFACT_BYTES or observed != expected:
        return None
    return {
        "artifact_ref": str(artifact_ref),
        "artifact_sha256": hashlib.sha256(observed).hexdigest(),
        "artifact_byte_count": len(observed),
    }


def _artifact_path(root: Path, cycle_id: str, artifact_ref: object) -> Path | None:
    if not _safe_component(cycle_id) or not isinstance(artifact_ref, str):
        return None
    raw = artifact_ref.strip()
    if raw != artifact_ref or "\\" in raw:
        return None
    pure = PurePosixPath(raw)
    expected_prefix = (".task", "cycle", cycle_id, "agent_receipts")
    if (
        pure.is_absolute()
        or len(pure.parts) != len(expected_prefix) + 1
        or pure.parts[: len(expected_prefix)] != expected_prefix
        or not _safe_filename(pure.name)
    ):
        return None
    path = root.joinpath(*pure.parts)
    current = root
    try:
        for part in pure.parts:
            current = current / part
            if current.is_symlink():
                return None
        resolved = path.resolve(strict=True)
        resolved.relative_to(root)
        mode = path.lstat().st_mode
    except (OSError, ValueError):
        return None
    if (
        resolved != path
        or not stat.S_ISREG(mode)
        or path.stat().st_size > MAX_ARTIFACT_BYTES
    ):
        return None
    return path


def _safe_component(value: object) -> bool:
    if not isinstance(value, str) or value != value.strip():
        return False
    return bool(
        value
        and len(value) <= 256
        and value not in {".", ".."}
        and "/" not in value
        and "\\" not in value
        and "\x00" not in value
    )


def _safe_filename(value: object) -> bool:
    return _safe_component(value) and str(value).endswith(".json")


__all__ = (
    "RUNTIME_ARTIFACT_STORE_KIND",
    "canonical_json_bytes",
    "cycle_artifact_ref",
    "decision_cycle_id",
    "verify_cycle_artifact",
    "workspace_root",
)
