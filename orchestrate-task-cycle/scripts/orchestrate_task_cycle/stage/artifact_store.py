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
from .publication_origin import publish_origin_object


SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
MAX_CONTEXT_BYTES = 384 * 1024
MAX_WORK_ORDER_BYTES = 128 * 1024
MAX_MACHINE_INPUT_BYTES = 128 * 1024
MAX_STAGE_INPUT_BYTES = 2 * 1024 * 1024
MAX_SEMANTIC_BYTES = 64 * 1024
MAX_USAGE_BYTES = 16 * 1024
ARTIFACT_LIMITS = {
    "context": MAX_CONTEXT_BYTES,
    "work_order": MAX_WORK_ORDER_BYTES,
    "machine_input": MAX_MACHINE_INPUT_BYTES,
}
COMPILER_IO_METRIC_FIELDS = (
    "cas_newly_written_bytes",
    "cas_reused_bytes",
    "files_written_count",
)


def cas_write_receipt(
    size_bytes: int, mutation_performed: bool, *, attempted: bool = True
) -> dict[str, Any]:
    """Describe actual immutable-CAS mutation without a racy existence guess."""

    return {
        "write_attempted": attempted,
        "mutation_performed": mutation_performed,
        "cas_newly_written_bytes": (
            size_bytes if attempted and mutation_performed else 0
        ),
        "cas_reused_bytes": size_bytes if attempted and not mutation_performed else 0,
        "files_written_count": 1 if attempted and mutation_performed else 0,
    }


def merge_compiler_io_metrics(
    base: dict[str, Any] | None, *receipts: dict[str, Any] | None
) -> dict[str, Any]:
    """Add closed CAS counters while preserving unrelated compiler metrics."""

    merged = dict(base or {})
    for field in COMPILER_IO_METRIC_FIELDS:
        total = merged.get(field, 0)
        if isinstance(total, bool) or not isinstance(total, int) or total < 0:
            total = 0
        for receipt in receipts:
            value = (receipt or {}).get(field, 0)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                continue
            total += value
        merged[field] = total
    return merged


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
    origin_id: str | None = None,
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
    mutation_performed = False
    origin_publication = None
    if persist:
        if origin_id is not None:
            origin_publication = publish_origin_object(
                root,
                cycle_id,
                origin_id,
                artifact_type,
                path,
                payload,
            )
            mutation_performed = bool(
                origin_publication["target_write_receipt"]["mutation_performed"]
            )
        else:
            mutation_performed = immutable_write_bytes(path, payload)
    write_receipt = cas_write_receipt(
        len(payload), mutation_performed, attempted=persist
    )
    return {
        "artifact_type": artifact_type,
        "ref": rel_path(root, path),
        "sha256": digest,
        "size_bytes": len(payload),
        "duplicate": duplicate,
        "write_receipt": write_receipt,
        "compiler_io_receipt": (
            origin_publication["attempt_metrics"]
            if origin_publication is not None
            else write_receipt
        ),
        "origin_intent_binding": (
            origin_publication["intent_binding"]
            if origin_publication is not None
            else None
        ),
    }


def write_compiler_artifact(
    root: Path,
    cycle_id: str,
    artifact_type: str,
    value: dict[str, Any],
    *,
    origin_id: str | None = None,
) -> dict[str, Any]:
    return compiler_artifact_binding(
        root,
        cycle_id,
        artifact_type,
        value,
        persist=True,
        origin_id=origin_id,
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
    maximum = MAX_SEMANTIC_BYTES if input_kind == "semantic" else MAX_STAGE_INPUT_BYTES
    value, payload, _path = _read_exact_json(root, ref, sha256, maximum)
    if payload != canonical_bytes(value) + b"\n":
        raise ValueError(f"{input_kind} input must be canonical immutable JSON")
    expected_kind = f"stage_{input_kind}"
    if value.get("artifact_kind") == expected_kind:
        wrapper_fields = {
            "schema_version",
            "artifact_kind",
            "cycle_id",
            "target",
            "result" if input_kind == "owner_result" else "semantic",
        }
        if input_kind == "semantic":
            wrapper_fields.add("reasoned_not_applicable")
        required_wrapper_fields = wrapper_fields - {"reasoned_not_applicable"}
        if set(value) not in (required_wrapper_fields, wrapper_fields):
            raise ValueError(f"{input_kind} wrapper has unsupported fields")
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


def write_stage_input(
    root: Path,
    cycle_id: str,
    target: str,
    input_kind: str,
    body: dict[str, Any],
) -> dict[str, Any]:
    """Publish one canonical exact stage input generated by a registered executor."""

    if input_kind not in {"owner_result", "semantic"}:
        raise ValueError("unsupported stage input kind")
    wrapper = {
        "schema_version": 1,
        "artifact_kind": f"stage_{input_kind}",
        "cycle_id": cycle_id,
        "target": target,
        "result" if input_kind == "owner_result" else "semantic": body,
    }
    payload = canonical_bytes(wrapper) + b"\n"
    maximum = MAX_SEMANTIC_BYTES if input_kind == "semantic" else MAX_STAGE_INPUT_BYTES
    if len(payload) > maximum:
        raise ValueError("generated stage input exceeds its byte budget")
    digest = hashlib.sha256(payload).hexdigest()
    path = (
        cycle_dir(root, cycle_id)
        / "compiler"
        / input_kind
        / "sha256"
        / f"{digest}.json"
    )
    mutation_performed = immutable_write_bytes(path, payload)
    return {
        "ref": rel_path(root, path),
        "sha256": digest,
        "size_bytes": len(payload),
        "duplicate": not mutation_performed,
        "write_receipt": cas_write_receipt(len(payload), mutation_performed),
    }


def load_usage_observation(
    root: Path,
    ref: str,
    sha256: str,
    *,
    cycle_id: str,
    target: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Load caller-asserted token observations without treating them as verified."""

    value, payload, _path = _read_exact_json(root, ref, sha256, MAX_USAGE_BYTES)
    if payload != canonical_bytes(value) + b"\n":
        raise ValueError("model usage observation must be canonical immutable JSON")
    v1_fields = {
        "schema_version",
        "artifact_kind",
        "cycle_id",
        "target",
        "input_tokens",
        "cached_input_tokens",
        "output_tokens",
    }
    v2_fields = v1_fields | {
        "provider_id",
        "runtime_id",
        "model_id",
        "request_id",
    }
    version = value.get("schema_version")
    expected_fields = v2_fields if version == 2 else v1_fields
    if set(value) != expected_fields:
        raise ValueError("model usage observation has unsupported fields")
    if (
        version not in {1, 2}
        or value.get("artifact_kind") != "model_usage_observation"
        or value.get("cycle_id") != cycle_id
        or value.get("target") != target
    ):
        raise ValueError("model usage observation scope is invalid")
    counts: dict[str, Any] = {}
    for field in ("input_tokens", "cached_input_tokens", "output_tokens"):
        count = value.get(field)
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise ValueError("model usage token counts must be non-negative integers")
        counts[field] = count
    if counts["cached_input_tokens"] > counts["input_tokens"]:
        raise ValueError("cached input tokens cannot exceed input tokens")
    if version == 2:
        for field in ("provider_id", "runtime_id", "model_id", "request_id"):
            item = value.get(field)
            if not isinstance(item, str) or not item.strip() or len(item.encode()) > 256:
                raise ValueError("usage v2 provenance IDs must be bounded strings")
            counts[field] = item
        counts["usage_aggregate_eligible"] = False
        counts["usage_provenance_status"] = "caller_asserted_unverified"
    else:
        counts["usage_aggregate_eligible"] = False
        counts["usage_provenance_status"] = "legacy_unverified"
    return counts, {
        "ref": ref,
        "sha256": sha256,
        "size_bytes": len(payload),
        "schema_version": version,
    }


def load_routing_receipt(
    root: Path,
    ref: str,
    sha256: str,
    *,
    cycle_id: str,
    target: str,
    preparation_id: str,
    state_fingerprint: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Load one closed, current-target routing decision receipt."""

    value, payload, _path = _read_exact_json(root, ref, sha256, MAX_USAGE_BYTES)
    if payload != canonical_bytes(value) + b"\n":
        raise ValueError("stage routing receipt must be canonical immutable JSON")
    fields = {
        "schema_version",
        "artifact_kind",
        "cycle_id",
        "target",
        "preparation_id",
        "state_fingerprint",
        "policy_id",
        "profile_id",
        "routing_tier",
        "requested_model_ref",
        "requested_model",
        "requested_reasoning_effort",
        "routing_reason_codes",
    }
    if set(value) != fields:
        raise ValueError("stage routing receipt has unsupported fields")
    if (
        value.get("schema_version") != 1
        or value.get("artifact_kind") != "stage_routing_receipt"
        or value.get("cycle_id") != cycle_id
        or value.get("target") != target
        or value.get("preparation_id") != preparation_id
        or value.get("state_fingerprint") != state_fingerprint
    ):
        raise ValueError("stage routing receipt scope is stale or invalid")
    tier = value.get("routing_tier")
    if isinstance(tier, bool) or not isinstance(tier, int) or tier not in range(1, 6):
        raise ValueError("stage routing receipt requires routing_tier 1..5")
    for field in (
        "policy_id",
        "profile_id",
        "requested_model_ref",
        "requested_model",
        "requested_reasoning_effort",
    ):
        item = value.get(field)
        if not isinstance(item, str) or not item.strip() or len(item.encode()) > 256:
            raise ValueError("stage routing receipt requires bounded routing claims")
    reasons = value.get("routing_reason_codes")
    if not reasons or not isinstance(reasons, list) or any(
        not isinstance(item, str) or not item or len(item.encode()) > 128
        for item in reasons
    ) or len(set(reasons)) != len(reasons):
        raise ValueError("stage routing receipt reason codes are invalid")
    return value, {"ref": ref, "sha256": sha256, "size_bytes": len(payload)}


__all__ = [
    "COMPILER_IO_METRIC_FIELDS",
    "MAX_CONTEXT_BYTES",
    "MAX_STAGE_INPUT_BYTES",
    "MAX_SEMANTIC_BYTES",
    "MAX_MACHINE_INPUT_BYTES",
    "MAX_USAGE_BYTES",
    "MAX_WORK_ORDER_BYTES",
    "cas_write_receipt",
    "compiler_artifact_binding",
    "load_compiler_artifact",
    "load_stage_input",
    "load_routing_receipt",
    "load_usage_observation",
    "merge_compiler_io_metrics",
    "write_stage_input",
    "write_compiler_artifact",
]
