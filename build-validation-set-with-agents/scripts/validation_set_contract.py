#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Iterable


MANIFEST_SCHEMA_VERSION = 2
ROOT_SCHEMA_VERSION = 2
ORACLE_RESULTS_SCHEMA_VERSION = 1
FINALIZATION_SCHEMA_VERSION = 1
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

ARTIFACT_FIELDS = {
    "items": "items_path",
    "labels": "labels_path",
    "oracle_manifest": "oracle_manifest_path",
    "oracle_results": "oracle_results_path",
    "split_manifest": "split_manifest_path",
    "leakage_report": "leakage_report_path",
}

FINALIZED_MANIFEST_FIELDS = (
    "manifest_schema_version",
    "validation_set_id",
    "task_id",
    "cycle_id",
    "validation_set_status",
    "quality_tier",
    "not_gold",
    "item_count",
    "label_count",
    "oracle_count",
    "source_class_distribution",
    "items_path",
    "labels_path",
    "oracle_manifest_path",
    "oracle_results_path",
    "split_manifest_path",
    "leakage_report_path",
    "no_overclaim_flags",
    "forbidden_promotions",
    "scenario_coverage",
    "scenario_uncovered",
    "acceptance_inversion_candidate",
)


class ContractError(ValueError):
    pass


def canonical_sha256(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def get_dotted_value(record: dict[str, Any], field: str) -> Any:
    current: Any = record
    for key in field.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def evaluate_deterministic_oracle(record: dict[str, Any], oracle: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    for field in oracle.get("required_fields") or []:
        value = get_dotted_value(record, str(field))
        if value in (None, "", [], {}):
            failures.append(f"missing_required_field:{field}")
    for field in oracle.get("forbidden_fields") or []:
        value = get_dotted_value(record, str(field))
        if value not in (None, "", [], {}):
            failures.append(f"forbidden_field_present:{field}")
    for field, allowed in (oracle.get("allowed_values") or {}).items():
        value = get_dotted_value(record, str(field))
        if value not in allowed:
            failures.append(f"disallowed_value:{field}:{value}")
    return failures


def required_item_oracle_pairs(
    items: list[dict[str, Any]],
    oracles: list[dict[str, Any]],
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    by_id = {
        oracle.get("oracle_id"): oracle
        for oracle in oracles
        if isinstance(oracle, dict) and isinstance(oracle.get("oracle_id"), str)
    }
    default_ids = [
        oracle.get("oracle_id")
        for oracle in oracles
        if isinstance(oracle, dict) and oracle.get("target") == "item" and isinstance(oracle.get("oracle_id"), str)
    ]
    pairs: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for item in items:
        requested = item.get("oracle_ids")
        oracle_ids = requested if isinstance(requested, list) and requested else default_ids
        for oracle_id in oracle_ids:
            oracle = by_id.get(oracle_id)
            if oracle is not None:
                pairs.append((item, oracle))
    return pairs


def deterministic_result_record(item: dict[str, Any], oracle: dict[str, Any]) -> dict[str, Any]:
    failures = evaluate_deterministic_oracle(item, oracle)
    return {
        "item_id": item.get("item_id") or item.get("id") or "unknown",
        "oracle_id": oracle.get("oracle_id"),
        "item_content_sha256": canonical_sha256(item),
        "oracle_definition_sha256": canonical_sha256(oracle),
        "status": "failed" if failures else "passed",
        "failures": failures,
    }


def sha256_file(path: Path) -> str:
    if not path.is_file():
        raise ContractError(f"required file is missing: {path}")
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise ContractError(f"required file cannot be hashed: {path}: {exc}") from exc
    return digest.hexdigest()


def within_root(root: Path, candidate: Path) -> Path | None:
    resolved = candidate.resolve(strict=False)
    try:
        resolved.relative_to(root.resolve())
    except ValueError:
        return None
    return resolved


def resolve_root_path(root: Path, value: Any, label: str, *, require_file: bool = False) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{label} must be a non-empty root-relative path")
    raw = Path(value)
    if raw.is_absolute() or ".." in raw.parts:
        raise ContractError(f"{label} must be root-relative without parent traversal: {value}")
    resolved = within_root(root, root / raw)
    if resolved is None:
        raise ContractError(f"{label} escapes the declared root, including through a symlink: {value}")
    if require_file and not resolved.is_file():
        raise ContractError(f"{label} does not resolve to a file: {value}")
    return resolved


def resolve_root_file(root: Path, value: Any, label: str) -> Path:
    return resolve_root_path(root, value, label, require_file=True)


def atomic_write_text(path: Path, data: str, *, root: Path | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    parent = path.parent.resolve(strict=True)
    if root is not None:
        bounded_root = root.resolve()
        try:
            parent.relative_to(bounded_root)
        except ValueError as exc:
            raise ContractError(f"atomic output parent escapes the declared root: {parent}") from exc
    target = parent / path.name
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.tmp-", dir=parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
        directory_fd = os.open(parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if temporary.exists():
            temporary.unlink()


def atomic_write_json(path: Path, value: dict[str, Any], *, root: Path | None = None) -> None:
    atomic_write_text(path, json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", root=root)


def atomic_write_jsonl(path: Path, records: Iterable[dict[str, Any]], *, root: Path | None = None) -> None:
    data = "".join(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n" for record in records)
    atomic_write_text(path, data, root=root)


def manifest_projection(manifest: dict[str, Any]) -> dict[str, Any]:
    return {field: manifest.get(field) for field in FINALIZED_MANIFEST_FIELDS}


def build_finalization_record(
    manifest: dict[str, Any],
    artifact_paths: dict[str, Path],
    oracle_results: dict[str, Any],
) -> dict[str, Any]:
    input_hashes = {name: sha256_file(artifact_paths[name]) for name in ARTIFACT_FIELDS}
    record: dict[str, Any] = {
        "finalization_schema_version": FINALIZATION_SCHEMA_VERSION,
        "finalizer": "finalize_validation_set.py",
        "validation_set_id": manifest.get("validation_set_id"),
        "validation_set_status": manifest.get("validation_set_status"),
        "manifest_state_sha256": canonical_sha256(manifest_projection(manifest)),
        "input_hashes": input_hashes,
        "item_count": manifest.get("item_count"),
        "label_count": manifest.get("label_count"),
        "oracle_count": manifest.get("oracle_count"),
        "source_binding_status": "verified",
        "leakage_status": "nonblocking",
        "oracle_execution_status": oracle_results.get("execution_status"),
        "oracle_status": oracle_results.get("status"),
        "oracle_result_count": oracle_results.get("result_count"),
        "oracle_failed_count": oracle_results.get("failed_count"),
    }
    record["finalization_sha256"] = canonical_sha256(record)
    return record
