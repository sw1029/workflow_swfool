"""Immutable content-addressed storage for compiled stage preparations."""

from __future__ import annotations

import json
import hashlib
import re
from pathlib import Path
from typing import Any

from ..cycle_ledger import cycle_dir, immutable_write_bytes
from ..ledger.support import read_initialization_metadata, rel_path
from ..ledger.workflow_contract import require_cycle_mutation_contract
from .artifact_store import (
    cas_write_receipt,
    load_compiler_artifact,
    merge_compiler_io_metrics,
)
from .contracts import (
    PREPARATION_SCHEMA_VERSION_V2,
    PREPARATION_SCHEMA_VERSION_V3,
    canonical_bytes,
    canonical_sha256,
    durable_preparation_projection,
    require_expected_preparation,
    validate_preparation,
)
from .specs import TARGET_COMPILE_SPECS
from .preparation_publication_receipt import ensure_receipt, load_receipt
from .protocol import cycle_preparation_version


MAX_PREPARATION_BYTES = 2 * 1024 * 1024
MAX_V2_PREPARATION_BYTES = 256 * 1024
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
PUBLICATION_OPERATION = {
    "skill_id": "orchestrate-task-cycle",
    "operation_id": "publish_compiled_stage_projection",
    "operation_version": "1",
    "authority_applicability": "none",
}


def _validated_collection_limits(
    preparation: dict[str, Any],
) -> tuple[int, int]:
    metrics = preparation.get("compiler_metrics")
    limits = (
        metrics.get("collection_limits")
        if isinstance(metrics, dict)
        else None
    )
    if (
        not isinstance(limits, dict)
        or set(limits) != {"max_files", "max_paths"}
        or any(
            isinstance(limits.get(key), bool)
            or not isinstance(limits.get(key), int)
            or limits[key] < 1
            for key in ("max_files", "max_paths")
        )
    ):
        raise ValueError(
            "compiled preparation lacks exact collection limits"
        )
    return int(limits["max_files"]), int(limits["max_paths"])


def _validate_compiled_preparation_for_publication(
    root: Path,
    preparation: dict[str, Any],
) -> dict[str, Any]:
    """Re-derive the exact dependency-ready preparation without writing."""

    validated = validate_preparation(preparation)
    version = int(validated["schema_version"])
    if version not in {
        PREPARATION_SCHEMA_VERSION_V2,
        PREPARATION_SCHEMA_VERSION_V3,
    }:
        return validated
    cycle_id = str(validated["cycle_id"])
    cycle_preparation_version(root, cycle_id, version)
    max_files, max_paths = _validated_collection_limits(validated)
    from .service import prepare_stage

    expected = prepare_stage(
        root,
        cycle_id,
        str(validated["target"]),
        workflow_mode=str(validated["workflow_mode"]),
        max_files=max_files,
        max_paths=max_paths,
        preparation_schema_version=version,
        persist_compiler_artifacts=False,
    )
    require_expected_preparation(validated, expected)
    return validated


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
    require_cycle_mutation_contract(
        read_initialization_metadata(
            workspace, str(validated["cycle_id"])
        ),
        "publish preparation",
    )
    validated = _validate_compiled_preparation_for_publication(
        workspace, validated
    )
    if validated.get("schema_version") in {
        PREPARATION_SCHEMA_VERSION_V2,
        PREPARATION_SCHEMA_VERSION_V3,
    }:
        cycle_id = str(validated["cycle_id"])
        if validated.get("executor_kind") == "deterministic" and validated.get(
            "schema_version"
        ) == PREPARATION_SCHEMA_VERSION_V3:
            load_compiler_artifact(
                workspace,
                cycle_id,
                validated["machine_input_binding"],
                "machine_input",
            )
        else:
            load_compiler_artifact(
                workspace, cycle_id, validated["context_binding"], "context"
            )
            load_compiler_artifact(
                workspace, cycle_id, validated["work_order_binding"], "work_order"
            )
    durable = validate_preparation(durable_preparation_projection(validated))
    payload = canonical_bytes(durable) + b"\n"
    maximum = (
        MAX_V2_PREPARATION_BYTES
        if validated.get("schema_version")
        in {PREPARATION_SCHEMA_VERSION_V2, PREPARATION_SCHEMA_VERSION_V3}
        else MAX_PREPARATION_BYTES
    )
    if len(payload) > maximum:
        raise ValueError(
            f"preparation_artifact_budget_exceeded: {len(payload)} > "
            f"{maximum} bytes"
        )
    body_digest = canonical_sha256(durable)
    digest = hashlib.sha256(payload).hexdigest()
    path = preparation_path(
        workspace,
        str(durable["cycle_id"]),
        str(durable["target"]),
        digest,
    )
    publication_receipt = None
    if validated.get("schema_version") == PREPARATION_SCHEMA_VERSION_V3:
        from .publication_origin import publish_preparation_origin

        origin_publication = publish_preparation_origin(
            workspace,
            str(durable["cycle_id"]),
            str(durable["preparation_id"]),
            path,
            payload,
        )
        write_receipt = origin_publication["target_write_receipt"]
        mutation_performed = bool(write_receipt["mutation_performed"])
        preparation_io_receipt = origin_publication["attempt_metrics"]
    else:
        mutation_performed = immutable_write_bytes(path, payload)
        write_receipt = cas_write_receipt(len(payload), mutation_performed)
        preparation_io_receipt = write_receipt
    compiler_metrics = merge_compiler_io_metrics(
        validated.get("compiler_metrics") or {}, preparation_io_receipt
    )
    if validated.get("schema_version") == PREPARATION_SCHEMA_VERSION_V3:
        publication_receipt = ensure_receipt(
            workspace,
            durable,
            rel_path(workspace, path),
            digest,
            body_digest,
            len(payload),
        )
        receipt_binding = publication_receipt["receipt_binding"]
        compiler_metrics = merge_compiler_io_metrics(
            compiler_metrics,
            cas_write_receipt(
                int(receipt_binding["size_bytes"]),
                bool(publication_receipt["receipt_mutation_performed"]),
            ),
        )
    next_action = validated.get("next_action") or {}
    blocked = next_action.get("kind") == "stop"
    return {
        "status": "block" if blocked else "ok",
        "stop_reason": next_action.get("reason") if blocked else None,
        "preparation_id": durable["preparation_id"],
        "cycle_id": durable["cycle_id"],
        "target": durable["target"],
        "state_fingerprint": durable["state_fingerprint"],
        "preparation_ref": rel_path(workspace, path),
        "preparation_sha256": digest,
        "preparation_body_sha256": body_digest,
        "preparation_bytes": len(payload),
        "compiler_metrics": compiler_metrics,
        "preparation_write_receipt": write_receipt,
        "preparation_publication_receipt_binding": (
            publication_receipt or {}
        ).get("receipt_binding"),
        "publication_operation": dict(PUBLICATION_OPERATION),
        "applied": True,
        "artifact_duplicate": not mutation_performed,
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
    if (
        validated.get("schema_version")
        in {PREPARATION_SCHEMA_VERSION_V2, PREPARATION_SCHEMA_VERSION_V3}
        and len(payload) > MAX_V2_PREPARATION_BYTES
    ):
        raise ValueError("preparation_artifact_budget_exceeded")
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
    if validated.get("schema_version") in {
        PREPARATION_SCHEMA_VERSION_V2,
        PREPARATION_SCHEMA_VERSION_V3,
    }:
        binding_bytes = len(payload)
        for field in (
            "context_binding",
            "work_order_binding",
            "machine_input_binding",
        ):
            binding = validated.get(field)
            if isinstance(binding, dict):
                binding_bytes += int(binding.get("size_bytes") or 0)
        origin_metrics: dict[str, Any] = {}
        if validated.get("schema_version") == PREPARATION_SCHEMA_VERSION_V3:
            publication_receipt = load_receipt(
                workspace,
                validated,
                str(ref),
                expected_sha256,
                canonical_sha256(validated),
                len(payload),
            )
            origin_metrics = publication_receipt["compiler_io_metrics"]
            binding_bytes += int(
                publication_receipt["receipt_binding"]["size_bytes"]
            )
        validated["compiler_metrics"] = merge_compiler_io_metrics(
            validated.get("compiler_metrics") or {},
            origin_metrics,
            cas_write_receipt(binding_bytes, False),
        )
    return validated


__all__ = [
    "MAX_PREPARATION_BYTES",
    "MAX_V2_PREPARATION_BYTES",
    "PUBLICATION_OPERATION",
    "load_published_preparation",
    "preparation_path",
    "publish_preparation",
]
