"""Exact bindings and immutable CAS storage for compiler artifacts."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from ..cycle_ledger import cycle_dir, immutable_write_bytes
from ..ledger.support import initialization_path, rel_path
from .contracts import canonical_bytes
from .publication_origin import publish_compiler_artifact_origin
from .stage_input_store import (
    MAX_SEMANTIC_BYTES,
    MAX_STAGE_INPUT_BYTES,
    MAX_USAGE_BYTES,
    load_routing_receipt,
    load_stage_input,
    load_usage_observation,
    project_stage_input,
    stage_input_path,
    write_stage_input,
)
from .storage_common import (
    SHA256_PATTERN,
    _read_exact_json,
    _resolved_ref,
    cas_write_receipt,
    read_exact_json,
)


MAX_CONTEXT_BYTES = 384 * 1024
MAX_WORK_ORDER_BYTES = 128 * 1024
MAX_MACHINE_INPUT_BYTES = 128 * 1024
MAX_DETERMINISTIC_COMMIT_RECEIPT_BYTES = 64 * 1024
ARTIFACT_LIMITS = {
    "context": MAX_CONTEXT_BYTES,
    "work_order": MAX_WORK_ORDER_BYTES,
    "machine_input": MAX_MACHINE_INPUT_BYTES,
    "deterministic_commit_receipt": MAX_DETERMINISTIC_COMMIT_RECEIPT_BYTES,
}
COMPILER_IO_METRIC_FIELDS = (
    "cas_newly_written_bytes",
    "cas_reused_bytes",
    "files_written_count",
)


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
    origin_preparation: dict[str, Any] | None = None,
    _legacy_recovery: bool = False,
) -> dict[str, Any]:
    payload = canonical_bytes(value) + b"\n"
    maximum = ARTIFACT_LIMITS[artifact_type]
    if len(payload) > maximum:
        raise ValueError(
            f"{artifact_type}_artifact_budget_exceeded: "
            f"{len(payload)} > {maximum} bytes"
        )
    digest = hashlib.sha256(payload).hexdigest()
    path = compiler_artifact_path(root, cycle_id, artifact_type, digest)
    duplicate = path.exists()
    mutation_performed = False
    origin_publication = None
    if persist:
        compiler_origin_kind = artifact_type in {
            "context",
            "work_order",
            "machine_input",
        }
        initialized = initialization_path(root, cycle_id).is_file()
        if compiler_origin_kind and initialized:
            from .protocol import cycle_preparation_version

            enforced_schema = cycle_preparation_version(root, cycle_id, None)
            if enforced_schema in {2, 3} and origin_id is None:
                raise ValueError(
                    "compiler-first artifact publication requires its exact "
                    "origin preparation"
                )
        elif compiler_origin_kind and not _legacy_recovery:
            raise ValueError(
                "unbound compiler artifact persistence is recovery-only; "
                "pass _legacy_recovery=True for an explicit legacy replay"
            )
        if origin_id is not None:
            if (
                not isinstance(origin_preparation, dict)
                or origin_preparation.get("preparation_id") != origin_id
            ):
                raise ValueError(
                    "compiler artifact origin requires its exact preparation"
                )
            origin_publication = publish_compiler_artifact_origin(
                root,
                origin_preparation,
                artifact_type,
                path,
                payload,
            )
            mutation_performed = bool(
                origin_publication["target_write_receipt"][
                    "mutation_performed"
                ]
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
    origin_preparation: dict[str, Any] | None = None,
    _legacy_recovery: bool = False,
) -> dict[str, Any]:
    return compiler_artifact_binding(
        root,
        cycle_id,
        artifact_type,
        value,
        persist=True,
        origin_id=origin_id,
        origin_preparation=origin_preparation,
        _legacy_recovery=_legacy_recovery,
    )


def load_compiler_artifact(
    root: Path, cycle_id: str, binding: Any, artifact_type: str
) -> dict[str, Any]:
    if not isinstance(binding, dict):
        raise ValueError(f"{artifact_type}_binding must be an object")
    if binding.get("artifact_type") != artifact_type:
        raise ValueError(
            f"{artifact_type}_binding has an invalid artifact_type"
        )
    ref = str(binding.get("ref") or "")
    digest = str(binding.get("sha256") or "")
    value, payload, path = read_exact_json(
        root, ref, digest, ARTIFACT_LIMITS[artifact_type]
    )
    expected = compiler_artifact_path(
        root, cycle_id, artifact_type, digest
    ).resolve(strict=True)
    if path != expected or ref != expected.relative_to(root).as_posix():
        raise ValueError(
            f"{artifact_type}_binding does not match its content address"
        )
    if payload != canonical_bytes(value) + b"\n":
        raise ValueError(
            f"{artifact_type}_binding is not canonical immutable JSON"
        )
    if binding.get("size_bytes") != len(payload):
        raise ValueError(
            f"{artifact_type}_binding size does not match exact input"
        )
    return value


__all__ = [
    "COMPILER_IO_METRIC_FIELDS",
    "MAX_CONTEXT_BYTES",
    "MAX_DETERMINISTIC_COMMIT_RECEIPT_BYTES",
    "MAX_MACHINE_INPUT_BYTES",
    "MAX_SEMANTIC_BYTES",
    "MAX_STAGE_INPUT_BYTES",
    "MAX_USAGE_BYTES",
    "MAX_WORK_ORDER_BYTES",
    "_read_exact_json",
    "_resolved_ref",
    "cas_write_receipt",
    "compiler_artifact_binding",
    "load_compiler_artifact",
    "load_routing_receipt",
    "load_stage_input",
    "load_usage_observation",
    "merge_compiler_io_metrics",
    "project_stage_input",
    "stage_input_path",
    "write_compiler_artifact",
    "write_stage_input",
]
