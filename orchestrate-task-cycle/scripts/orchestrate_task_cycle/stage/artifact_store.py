"""Exact bindings and immutable CAS storage for stage compiler artifacts."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from ..cycle_ledger import cycle_dir, immutable_write_bytes
from ..ledger.support import rel_path
from .contracts import canonical_bytes
from .native_results import normalize_native_owner_result


SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
MAX_CONTEXT_BYTES = 384 * 1024
MAX_WORK_ORDER_BYTES = 128 * 1024
MAX_STAGE_INPUT_BYTES = 2 * 1024 * 1024
MAX_USAGE_BYTES = 16 * 1024
ARTIFACT_LIMITS = {
    "context": MAX_CONTEXT_BYTES,
    "work_order": MAX_WORK_ORDER_BYTES,
}


def _resolved_ref(root: Path, ref: str) -> Path:
    relative = Path(str(ref))
    if relative.is_absolute() or not relative.parts or ".." in relative.parts:
        raise ValueError("artifact ref must be a workspace-relative path")
    candidate = root
    for part in relative.parts:
        candidate = candidate / part
        if candidate.is_symlink():
            raise ValueError("artifact ref must not traverse a symlink")
    try:
        path = candidate.resolve(strict=True)
    except FileNotFoundError as exc:
        raise ValueError("artifact ref does not exist") from exc
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ValueError("artifact ref escapes the workspace") from exc
    if not path.is_file():
        raise ValueError("artifact ref must identify a regular file")
    return path


def _read_exact_json(
    root: Path, ref: str, sha256: str, maximum: int
) -> tuple[dict[str, Any], bytes, Path]:
    if not SHA256_PATTERN.fullmatch(str(sha256)):
        raise ValueError("artifact sha256 must be a lowercase SHA-256 value")
    path = _resolved_ref(root, ref)
    if path.stat().st_size > maximum:
        raise ValueError("stage artifact byte budget exceeded")
    payload = path.read_bytes()
    if hashlib.sha256(payload).hexdigest() != sha256:
        raise ValueError("stage artifact file digest does not match exact input")
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("stage artifact is not valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise ValueError("stage artifact JSON must be an object")
    return value, payload, path


def compiler_artifact_path(
    root: Path, cycle_id: str, artifact_type: str, digest: str
) -> Path:
    if artifact_type not in ARTIFACT_LIMITS:
        raise ValueError(f"unsupported compiler artifact type: {artifact_type}")
    if not SHA256_PATTERN.fullmatch(digest):
        raise ValueError("compiler artifact digest must be lowercase SHA-256")
    return (
        cycle_dir(root, cycle_id)
        / "compiler"
        / artifact_type
        / "sha256"
        / f"{digest}.json"
    )


def compiler_artifact_binding(
    root: Path,
    cycle_id: str,
    artifact_type: str,
    value: dict[str, Any],
    *,
    persist: bool = False,
) -> dict[str, Any]:
    payload = canonical_bytes(value) + b"\n"
    maximum = ARTIFACT_LIMITS[artifact_type]
    if len(payload) > maximum:
        raise ValueError(
            f"{artifact_type}_artifact_budget_exceeded: {len(payload)} > {maximum} bytes"
        )
    digest = hashlib.sha256(payload).hexdigest()
    path = compiler_artifact_path(root, cycle_id, artifact_type, digest)
    duplicate = path.exists()
    if persist:
        immutable_write_bytes(path, payload)
    return {
        "artifact_type": artifact_type,
        "ref": rel_path(root, path),
        "sha256": digest,
        "size_bytes": len(payload),
        "duplicate": duplicate,
    }


def write_compiler_artifact(
    root: Path, cycle_id: str, artifact_type: str, value: dict[str, Any]
) -> dict[str, Any]:
    return compiler_artifact_binding(
        root, cycle_id, artifact_type, value, persist=True
    )


def load_compiler_artifact(
    root: Path, cycle_id: str, binding: Any, artifact_type: str
) -> dict[str, Any]:
    if not isinstance(binding, dict):
        raise ValueError(f"{artifact_type}_binding must be an object")
    if binding.get("artifact_type") != artifact_type:
        raise ValueError(f"{artifact_type}_binding has an invalid artifact_type")
    ref, digest = str(binding.get("ref") or ""), str(binding.get("sha256") or "")
    value, payload, path = _read_exact_json(root, ref, digest, ARTIFACT_LIMITS[artifact_type])
    expected = compiler_artifact_path(root, cycle_id, artifact_type, digest).resolve(
        strict=True
    )
    if path != expected or ref != expected.relative_to(root).as_posix():
        raise ValueError(f"{artifact_type}_binding does not match its content address")
    if payload != canonical_bytes(value) + b"\n":
        raise ValueError(f"{artifact_type}_binding is not canonical immutable JSON")
    if binding.get("size_bytes") != len(payload):
        raise ValueError(f"{artifact_type}_binding size does not match exact input")
    return value


def load_stage_input(
    root: Path,
    ref: str,
    sha256: str,
    *,
    cycle_id: str,
    target: str,
    input_kind: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    value, payload, _path = _read_exact_json(
        root, ref, sha256, MAX_STAGE_INPUT_BYTES
    )
    expected_kind = f"stage_{input_kind}"
    if value.get("artifact_kind") == expected_kind:
        if value.get("schema_version") != 1:
            raise ValueError(f"unsupported {input_kind} schema_version")
        if value.get("cycle_id") != cycle_id or value.get("target") != target:
            raise ValueError(f"{input_kind} binding scope does not match preparation")
        key = "result" if input_kind == "owner_result" else "semantic"
        body = value.get(key)
        if not isinstance(body, dict):
            raise ValueError(f"{input_kind} artifact {key} must be an object")
    elif input_kind == "owner_result":
        body = value
    else:
        raise ValueError("semantic input must use the stage_semantic wrapper")
    binding = {"ref": ref, "sha256": sha256, "size_bytes": len(payload)}
    if input_kind == "semantic":
        reasoned = value.get("reasoned_not_applicable") or {}
        if not isinstance(reasoned, dict):
            raise ValueError("semantic reasoned_not_applicable must be an object")
        return {"semantic": body, "reasoned_not_applicable": reasoned}, binding
    body = normalize_native_owner_result(
        target,
        body,
        cycle_id=cycle_id,
        source_ref=ref,
    )
    return {"owner_result": body}, binding


def load_usage_observation(
    root: Path,
    ref: str,
    sha256: str,
    *,
    cycle_id: str,
    target: str,
) -> tuple[dict[str, int], dict[str, Any]]:
    """Load actual provider token counts without accepting prices or estimates."""

    value, payload, _path = _read_exact_json(root, ref, sha256, MAX_USAGE_BYTES)
    expected_fields = {
        "schema_version",
        "artifact_kind",
        "cycle_id",
        "target",
        "input_tokens",
        "cached_input_tokens",
        "output_tokens",
    }
    if set(value) != expected_fields:
        raise ValueError("model usage observation has unsupported fields")
    if (
        value.get("schema_version") != 1
        or value.get("artifact_kind") != "model_usage_observation"
        or value.get("cycle_id") != cycle_id
        or value.get("target") != target
    ):
        raise ValueError("model usage observation scope is invalid")
    counts: dict[str, int] = {}
    for field in ("input_tokens", "cached_input_tokens", "output_tokens"):
        count = value.get(field)
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise ValueError("model usage token counts must be non-negative integers")
        counts[field] = count
    if counts["cached_input_tokens"] > counts["input_tokens"]:
        raise ValueError("cached input tokens cannot exceed input tokens")
    return counts, {"ref": ref, "sha256": sha256, "size_bytes": len(payload)}


__all__ = [
    "MAX_CONTEXT_BYTES",
    "MAX_STAGE_INPUT_BYTES",
    "MAX_USAGE_BYTES",
    "MAX_WORK_ORDER_BYTES",
    "compiler_artifact_binding",
    "load_compiler_artifact",
    "load_stage_input",
    "load_usage_observation",
    "write_compiler_artifact",
]
