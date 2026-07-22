"""Immutable origin I/O receipt for a published compiler preparation."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from ..cycle_ledger import cycle_dir, immutable_write_bytes
from ..ledger.support import rel_path
from .artifact_store import (
    COMPILER_IO_METRIC_FIELDS,
    cas_write_receipt,
    merge_compiler_io_metrics,
)
from .contracts import canonical_bytes
from .publication_origin import load_origin_intent


RECEIPT_KIND = "orchestrate_stage_preparation_publication_receipt"
RECEIPT_SCHEMA_VERSION = 2
MAX_RECEIPT_BYTES = 32 * 1024
_BINDING_FIELDS = ("context_binding", "work_order_binding", "machine_input_binding")


def receipt_path(root: Path, cycle_id: str, target: str, digest: str) -> Path:
    return (
        cycle_dir(root, cycle_id)
        / "packets"
        / f"preparation-publication-{target}-{digest}.receipt.json"
    )


def _artifact_bindings(preparation: dict[str, Any]) -> dict[str, Any]:
    return {
        field: preparation[field]
        for field in _BINDING_FIELDS
        if isinstance(preparation.get(field), dict)
    }


def _closed_metrics(value: Any, sizes: list[int]) -> dict[str, int]:
    if not isinstance(value, dict):
        raise ValueError("preparation publication receipt metrics must be an object")
    metrics: dict[str, int] = {}
    for field in COMPILER_IO_METRIC_FIELDS:
        item = value.get(field)
        if isinstance(item, bool) or not isinstance(item, int) or item < 0:
            raise ValueError("preparation publication receipt metrics are invalid")
        metrics[field] = item
    if metrics["cas_newly_written_bytes"] + metrics["cas_reused_bytes"] != sum(sizes):
        raise ValueError("preparation publication receipt byte accounting is invalid")
    possible = {(0, 0)}
    for size in sizes:
        possible |= {(total + size, count + 1) for total, count in tuple(possible)}
    if (
        metrics["cas_newly_written_bytes"],
        metrics["files_written_count"],
    ) not in possible:
        raise ValueError("preparation publication receipt write accounting is invalid")
    return metrics


def _expected_scope(
    preparation: dict[str, Any],
    preparation_ref: str,
    preparation_sha256: str,
    preparation_body_sha256: str,
    preparation_bytes: int,
    *,
    schema_version: int,
    origin_intent_bindings: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    scope = {
        "schema_version": schema_version,
        "artifact_kind": RECEIPT_KIND,
        "cycle_id": preparation["cycle_id"],
        "target": preparation["target"],
        "preparation_id": preparation["preparation_id"],
        "preparation_binding": {
            "ref": preparation_ref,
            "sha256": preparation_sha256,
            "body_sha256": preparation_body_sha256,
            "size_bytes": preparation_bytes,
        },
        "bound_compiler_artifacts": _artifact_bindings(preparation),
    }
    if schema_version == RECEIPT_SCHEMA_VERSION:
        scope["origin_intent_bindings"] = list(origin_intent_bindings or [])
    return scope


def _origin_objects(
    preparation: dict[str, Any],
    preparation_ref: str,
    preparation_sha256: str,
    preparation_bytes: int,
) -> list[tuple[str, dict[str, Any]]]:
    objects = [
        (str(binding["artifact_type"]), binding)
        for binding in _artifact_bindings(preparation).values()
    ]
    objects.append(
        (
            "preparation",
            {
                "ref": preparation_ref,
                "sha256": preparation_sha256,
                "size_bytes": preparation_bytes,
            },
        )
    )
    return objects


def _origin_records(
    root: Path,
    preparation: dict[str, Any],
    preparation_ref: str,
    preparation_sha256: str,
    preparation_bytes: int,
) -> list[dict[str, Any]]:
    objects = _origin_objects(
        preparation,
        preparation_ref,
        preparation_sha256,
        preparation_bytes,
    )
    object_kinds = [object_kind for object_kind, _binding in objects]
    if len(object_kinds) != len(set(object_kinds)):
        raise ValueError("preparation publication origin object kinds are duplicated")
    records = [
        load_origin_intent(
            root,
            str(preparation["cycle_id"]),
            str(preparation["preparation_id"]),
            object_kind,
            binding,
        )
        for object_kind, binding in objects
    ]
    ordered = sorted(
        records,
        key=lambda item: str(item["intent"]["object_kind"]),
    )
    intent_refs = [str(item["intent_binding"]["ref"]) for item in ordered]
    if len(intent_refs) != len(set(intent_refs)):
        raise ValueError("preparation publication origin intent bindings are duplicated")
    return ordered


def _merged_origin_metrics(records: list[dict[str, Any]]) -> dict[str, int]:
    return merge_compiler_io_metrics(
        {}, *(record["origin_metrics"] for record in records)
    )


def _load(path: Path) -> tuple[dict[str, Any], bytes]:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_RECEIPT_BYTES:
        raise ValueError("preparation publication receipt is missing or oversized")
    payload = path.read_bytes()
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("preparation publication receipt is invalid JSON") from exc
    if not isinstance(value, dict) or payload != canonical_bytes(value) + b"\n":
        raise ValueError("preparation publication receipt is not canonical JSON")
    return value, payload


def load_receipt(
    root: Path,
    preparation: dict[str, Any],
    preparation_ref: str,
    preparation_sha256: str,
    preparation_body_sha256: str,
    preparation_bytes: int,
) -> dict[str, Any]:
    path = receipt_path(
        root,
        str(preparation["cycle_id"]),
        str(preparation["target"]),
        preparation_sha256,
    )
    value, payload = _load(path)
    version = value.get("schema_version")
    if version == 1:
        expected = _expected_scope(
            preparation,
            preparation_ref,
            preparation_sha256,
            preparation_body_sha256,
            preparation_bytes,
            schema_version=1,
        )
        sizes = [
            *(
                int(binding["size_bytes"])
                for binding in _artifact_bindings(preparation).values()
            ),
            preparation_bytes,
            len(payload),
        ]
        metrics = _closed_metrics(value.get("compiler_io_metrics"), sizes)
    elif version == RECEIPT_SCHEMA_VERSION:
        records = _origin_records(
            root,
            preparation,
            preparation_ref,
            preparation_sha256,
            preparation_bytes,
        )
        expected = _expected_scope(
            preparation,
            preparation_ref,
            preparation_sha256,
            preparation_body_sha256,
            preparation_bytes,
            schema_version=RECEIPT_SCHEMA_VERSION,
            origin_intent_bindings=[
                record["intent_binding"] for record in records
            ],
        )
        metrics = merge_compiler_io_metrics(
            _merged_origin_metrics(records),
            cas_write_receipt(len(payload), True),
        )
        if value.get("compiler_io_metrics") != metrics:
            raise ValueError("preparation publication receipt metrics are invalid")
    else:
        raise ValueError("preparation publication receipt scope is invalid")
    if {key: value.get(key) for key in expected} != expected or set(value) != {
        *expected,
        "compiler_io_metrics",
    }:
        raise ValueError("preparation publication receipt scope is invalid")
    value["compiler_io_metrics"] = metrics
    value["receipt_binding"] = {
        "ref": rel_path(root, path),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "size_bytes": len(payload),
    }
    return value


def ensure_receipt(
    root: Path,
    preparation: dict[str, Any],
    preparation_ref: str,
    preparation_sha256: str,
    preparation_body_sha256: str,
    preparation_bytes: int,
) -> dict[str, Any]:
    path = receipt_path(
        root,
        str(preparation["cycle_id"]),
        str(preparation["target"]),
        preparation_sha256,
    )
    mutation_performed = False
    if not path.exists():
        records = _origin_records(
            root,
            preparation,
            preparation_ref,
            preparation_sha256,
            preparation_bytes,
        )
        base_metrics = _merged_origin_metrics(records)
        scope = _expected_scope(
            preparation,
            preparation_ref,
            preparation_sha256,
            preparation_body_sha256,
            preparation_bytes,
            schema_version=RECEIPT_SCHEMA_VERSION,
            origin_intent_bindings=[
                record["intent_binding"] for record in records
            ],
        )
        receipt_metrics = dict(base_metrics)
        for _attempt in range(8):
            receipt = {**scope, "compiler_io_metrics": receipt_metrics}
            payload = canonical_bytes(receipt) + b"\n"
            updated = merge_compiler_io_metrics(
                base_metrics, cas_write_receipt(len(payload), True)
            )
            if updated == receipt_metrics:
                break
            receipt_metrics = updated
        else:
            raise RuntimeError("preparation publication receipt size did not converge")
        receipt = {**scope, "compiler_io_metrics": receipt_metrics}
        mutation_performed = immutable_write_bytes(
            path, canonical_bytes(receipt) + b"\n"
        )
    loaded = load_receipt(
        root,
        preparation,
        preparation_ref,
        preparation_sha256,
        preparation_body_sha256,
        preparation_bytes,
    )
    loaded["receipt_mutation_performed"] = mutation_performed
    return loaded


__all__ = ["ensure_receipt", "load_receipt", "receipt_path"]
